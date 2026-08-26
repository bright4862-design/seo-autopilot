from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import socket

import httpx


REDIRECT_STATUSES = {301, 302, 303, 307, 308}
DEFAULT_MAX_REDIRECTS = 5
DEFAULT_MAX_DECODED_RESPONSE_BYTES = 5_000_000


class ResponseBodyTooLarge(Exception):
    """The decoded response body exceeded the caller's evidence budget."""


def _decoded_body_headers(headers: httpx.Headers) -> httpx.Headers:
    """Return headers that truthfully describe an already-decoded body."""
    decoded_headers = httpx.Headers(headers)
    # Response.aiter_bytes() applies HTTP content decoding. Reusing these wire
    # representation headers would decode the replacement body a second time
    # and retain the compressed wire length.
    decoded_headers.pop("content-encoding", None)
    decoded_headers.pop("content-length", None)
    return decoded_headers


async def _bounded_decoded_response(
    client,
    resolved: ResolvedHTTPHop,
    *,
    max_decoded_bytes: int,
):
    limit = max(1, int(max_decoded_bytes))
    async with client.stream(
        "GET",
        resolved.connect_url,
        headers={
            "Host": resolved.host_header,
            "Connection": "close",
        },
        extensions={"sni_hostname": resolved.hostname},
    ) as streamed:
        chunks: list[bytes] = []
        total = 0
        async for chunk in streamed.aiter_bytes():
            total += len(chunk)
            if total > limit:
                raise ResponseBodyTooLarge(
                    f"decoded_response_body_exceeded_{limit}_bytes"
                )
            chunks.append(chunk)
        body = b"".join(chunks)

        request = getattr(streamed, "request", None)
        if request is not None:
            request.url = resolved.logical_url
        return httpx.Response(
            status_code=streamed.status_code,
            headers=_decoded_body_headers(streamed.headers),
            content=body,
            request=request,
            extensions=dict(getattr(streamed, "extensions", {}) or {}),
        )


@dataclass(frozen=True)
class ResolvedHTTPHop:
    """A logical URL and the public address selected from one DNS snapshot."""

    logical_url: httpx.URL
    connect_url: httpx.URL
    hostname: str
    host_header: str
    ip_address: str


def _is_public_ip(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    # ``is_global`` alone is not sufficient on every supported Python release
    # (multicast has historically been classified as global). Keep the explicit
    # deny list as defence in depth for metadata, loopback and special-use space.
    return bool(
        address.is_global
        and not address.is_private
        and not address.is_loopback
        and not address.is_link_local
        and not address.is_reserved
        and not address.is_multicast
        and not address.is_unspecified
    )


def resolve_public_http_url(url: str) -> ResolvedHTTPHop | None:
    """Resolve one HTTP(S) hop once and pin it to an exclusively public result.

    All answers from the DNS snapshot must be public. Rejecting the complete hop
    when even one answer is private prevents an attacker from hiding a metadata
    or RFC1918 address among otherwise public A/AAAA records.
    """
    try:
        logical_url = httpx.URL(str(url or ""))
    except (TypeError, ValueError):
        return None

    if logical_url.scheme not in ("http", "https") or not logical_url.raw_host:
        return None
    if logical_url.username or logical_url.password:
        return None

    try:
        # HTTPX already IDNA-normalizes raw_host, which is also the exact ASCII
        # hostname needed for TLS SNI and the HTTP Host header.
        hostname = logical_url.raw_host.decode("ascii")
        port = logical_url.port or (443 if logical_url.scheme == "https" else 80)
        infos = socket.getaddrinfo(
            hostname,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
    except (socket.gaierror, UnicodeError, ValueError, OSError):
        return None

    addresses: list[str] = []
    for info in infos:
        try:
            candidate = str(ipaddress.ip_address(info[4][0]))
        except (IndexError, TypeError, ValueError):
            return None
        if candidate not in addresses:
            addresses.append(candidate)

    if not addresses or any(not _is_public_ip(candidate) for candidate in addresses):
        return None

    # Prefer IPv4 when both families are available. This is deterministic and
    # avoids selecting an unusable IPv6 route on hosts without IPv6 egress. The
    # full answer set above has already been validated before selecting either.
    selected_ip = next(
        (candidate for candidate in addresses if ipaddress.ip_address(candidate).version == 4),
        addresses[0],
    )
    host_header = hostname
    if ":" in hostname:
        host_header = f"[{hostname}]"
    if logical_url.port is not None:
        host_header = f"{host_header}:{logical_url.port}"

    return ResolvedHTTPHop(
        logical_url=logical_url,
        connect_url=logical_url.copy_with(host=selected_ip),
        hostname=hostname,
        host_header=host_header,
        ip_address=selected_ip,
    )


def is_public_http_url(url: str) -> bool:
    """True only when an HTTP(S) URL resolves exclusively to public IPs."""
    return resolve_public_http_url(url) is not None


async def safe_get_once(client, url: str, *, max_decoded_bytes: int | None = None):
    """Fetch one URL through its validated IP without a second DNS lookup.

    The socket connects to ``connect_url`` (the validated numeric address), while
    Host and TLS SNI retain the original hostname. HTTPX/httpcore therefore keeps
    normal certificate verification against the requested public hostname.
    """
    resolved = resolve_public_http_url(url)
    if resolved is None:
        return None

    if max_decoded_bytes is not None:
        return await _bounded_decoded_response(
            client,
            resolved,
            max_decoded_bytes=max_decoded_bytes,
        )

    # Preserve the existing HTTPX object and representation semantics for every
    # caller that did not request the decoded-body ceiling.
    response = await client.get(
        resolved.connect_url,
        headers={
            "Host": resolved.host_header,
            # A numeric-IP connection pool must never be reused for another
            # virtual host sharing that IP. Closing each pinned hop also prevents
            # an earlier SNI session from crossing logical host boundaries.
            "Connection": "close",
        },
        extensions={"sni_hostname": resolved.hostname},
    )

    # Callers and evidence contracts must continue to see the requested URL,
    # not the transport-only numeric address. The network request has completed,
    # so this cannot influence routing or trigger another resolution.
    request = getattr(response, "request", None)
    if request is not None:
        request.url = resolved.logical_url
    return response


async def safe_get(
    client,
    url: str,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    *,
    max_decoded_bytes: int | None = None,
):
    """GET with pinned DNS validation on every bounded redirect hop.

    The supplied client must have ``follow_redirects=False``. Returns the final
    response, or ``None`` for an unsafe/malformed hop or an overlong chain.
    """
    current = str(url or "")
    for _ in range(max(0, int(max_redirects)) + 1):
        response = await safe_get_once(
            client,
            current,
            max_decoded_bytes=max_decoded_bytes,
        )
        if response is None:
            return None
        if response.status_code in REDIRECT_STATUSES:
            location = response.headers.get("location")
            if not location:
                return response
            try:
                current = str(httpx.URL(current).join(location))
            except Exception:
                return None
            continue
        return response
    return None
