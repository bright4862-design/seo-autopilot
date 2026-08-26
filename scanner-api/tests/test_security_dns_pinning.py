import gzip
import ipaddress
import socket
import zlib

import httpx
import pytest

from app.security import (
    ResponseBodyTooLarge,
    resolve_public_http_url,
    safe_get,
    safe_get_once,
)


def _answer(address: str, port: int):
    parsed = ipaddress.ip_address(address)
    family = socket.AF_INET if parsed.version == 4 else socket.AF_INET6
    sockaddr = (address, port) if family == socket.AF_INET else (address, port, 0, 0)
    return (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr)


@pytest.mark.asyncio
async def test_bounded_plain_html_preserves_downstream_response_semantics(monkeypatch):
    payload = b"<html><head><title>Plain</title></head><body>ok</body></html>"
    observed = {}
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda _host, port, **_kwargs: [_answer("93.184.216.34", port)],
    )

    def handler(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["host"] = request.headers.get("host")
        return httpx.Response(
            200,
            headers={
                "content-type": "text/html; charset=utf-8",
                "content-length": str(len(payload)),
                "x-fixlist-test": "kept",
            },
            content=payload,
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    ) as client:
        response = await safe_get_once(
            client,
            "https://plain.example/catalog",
            max_decoded_bytes=1024,
        )

    assert observed == {
        "url": "https://93.184.216.34/catalog",
        "host": "plain.example",
    }
    assert response.status_code == 200
    assert response.content == payload
    assert response.text.startswith("<html>")
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    assert response.headers["x-fixlist-test"] == "kept"
    assert response.headers["content-length"] == str(len(payload))
    assert str(response.url) == "https://plain.example/catalog"
    assert response.request.headers["host"] == "plain.example"


@pytest.mark.asyncio
async def test_bounded_gzip_response_is_decoded_once_and_preserves_logical_request(
    monkeypatch,
):
    payload = b"<html><head><title>Compressed</title></head><body>ok</body></html>"
    compressed = gzip.compress(payload)
    observed = {}
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda _host, port, **_kwargs: [_answer("93.184.216.34", port)],
    )

    def handler(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["host"] = request.headers.get("host")
        return httpx.Response(
            200,
            headers={
                "content-type": "text/html; charset=utf-8",
                "content-encoding": "gzip",
                "content-length": str(len(compressed)),
                "x-fixlist-test": "kept",
            },
            content=compressed,
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    ) as client:
        response = await safe_get_once(
            client,
            "https://compressed.example/catalog",
            max_decoded_bytes=1024,
        )

    assert observed == {
        "url": "https://93.184.216.34/catalog",
        "host": "compressed.example",
    }
    assert response.status_code == 200
    assert response.content == payload
    assert response.text.startswith("<html>")
    assert "content-encoding" not in response.headers
    assert response.headers["content-length"] == str(len(payload))
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    assert response.headers["x-fixlist-test"] == "kept"
    assert str(response.url) == "https://compressed.example/catalog"
    assert response.request.headers["host"] == "compressed.example"


@pytest.mark.asyncio
async def test_bounded_decoded_response_rejects_content_past_the_limit(monkeypatch):
    payload = gzip.compress(b"x" * 2048)
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda _host, port, **_kwargs: [_answer("93.184.216.34", port)],
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-encoding": "gzip"},
            content=payload,
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    ) as client:
        with pytest.raises(
            ResponseBodyTooLarge,
            match="decoded_response_body_exceeded_512_bytes",
        ):
            await safe_get_once(
                client,
                "https://oversized.example/catalog",
                max_decoded_bytes=512,
            )


@pytest.mark.asyncio
async def test_bounded_gzip_limit_does_not_use_httpx_eager_decoding(monkeypatch):
    payload = gzip.compress(b"x" * 2_000_000)
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda _host, port, **_kwargs: [_answer("93.184.216.34", port)],
    )

    async def forbidden_aiter_bytes(_self, *args, **kwargs):
        raise AssertionError("bounded fetch must not let HTTPX eagerly decode a compressed block")

    monkeypatch.setattr(httpx.Response, "aiter_bytes", forbidden_aiter_bytes)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-encoding": "gzip"},
            content=payload,
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    ) as client:
        with pytest.raises(
            ResponseBodyTooLarge,
            match="decoded_response_body_exceeded_512_bytes",
        ):
            await safe_get_once(
                client,
                "https://single-block-bomb.example/catalog",
                max_decoded_bytes=512,
            )


@pytest.mark.asyncio
async def test_bounded_raw_deflate_decodes_when_header_is_split_after_one_byte(monkeypatch):
    payload = b"<html><body>raw deflate works across chunk boundaries</body></html>"
    compressor = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    compressed = compressor.compress(payload) + compressor.flush()
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda _host, port, **_kwargs: [_answer("93.184.216.34", port)],
    )

    class SplitStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield compressed[:1]
            yield compressed[1:]

        async def aclose(self):
            return None

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-encoding": "deflate"},
            stream=SplitStream(),
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    ) as client:
        response = await safe_get_once(
            client,
            "https://raw-deflate.example/catalog",
            max_decoded_bytes=1024,
        )

    assert response.status_code == 200
    assert response.content == payload
    assert "content-encoding" not in response.headers


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("encoding", "compressed", "error_pattern"),
    [
        (
            "gzip",
            gzip.compress(b"<html><body>" + (b"x" * 1024) + b"</body></html>")[:-1],
            "incomplete_gzip_response_body",
        ),
        (
            "deflate",
            zlib.compress(b"<html><body>" + (b"x" * 1024) + b"</body></html>")[:-1],
            "incomplete_deflate_response_body",
        ),
        (
            "deflate",
            (
                lambda compressor: (
                    compressor.compress(
                        b"<html><body>" + (b"x" * 1024) + b"</body></html>"
                    )
                    + compressor.flush()
                )[:-1]
            )(zlib.compressobj(wbits=-zlib.MAX_WBITS)),
            "incomplete_deflate_response_body",
        ),
    ],
    ids=["gzip", "zlib-deflate", "raw-deflate"],
)
async def test_bounded_compressed_response_rejects_truncated_streams(
    monkeypatch,
    encoding,
    compressed,
    error_pattern,
):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda _host, port, **_kwargs: [_answer("93.184.216.34", port)],
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-encoding": encoding},
            content=compressed,
            request=request,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    ) as client:
        with pytest.raises(httpx.DecodingError, match=error_pattern):
            await safe_get_once(
                client,
                f"https://truncated-{encoding}.example/catalog",
                max_decoded_bytes=4096,
            )


@pytest.mark.asyncio
async def test_fetch_uses_the_single_validated_dns_snapshot_not_a_rebind(monkeypatch):
    resolutions = 0
    observed = {}

    def rebinding_dns(_host, port, **_kwargs):
        nonlocal resolutions
        resolutions += 1
        address = "93.184.216.34" if resolutions == 1 else "169.254.169.254"
        return [_answer(address, port)]

    def handler(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["host"] = request.headers.get("host")
        return httpx.Response(200, text="ok")

    monkeypatch.setattr(socket, "getaddrinfo", rebinding_dns)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False) as client:
        response = await safe_get_once(client, "https://public.example/path")

    assert response is not None
    assert resolutions == 1
    assert observed == {"url": "https://93.184.216.34/path", "host": "public.example"}
    assert str(response.url) == "https://public.example/path"


@pytest.mark.asyncio
async def test_mixed_public_private_dns_answers_reject_the_entire_hop(monkeypatch):
    requests = 0

    def mixed_dns(_host, port, **_kwargs):
        return [_answer("93.184.216.34", port), _answer("10.0.0.7", port)]

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(200)

    monkeypatch.setattr(socket, "getaddrinfo", mixed_dns)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        response = await safe_get_once(client, "https://mixed.example/")

    assert response is None
    assert requests == 0


@pytest.mark.asyncio
async def test_https_pinning_preserves_host_sni_and_logical_response_url(monkeypatch):
    observed = {}

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda _host, port, **_kwargs: [_answer("93.184.216.34", port)],
    )

    def handler(request: httpx.Request) -> httpx.Response:
        observed.update({
            "url": str(request.url),
            "host": request.headers.get("host"),
            "connection": request.headers.get("connection"),
            "sni": request.extensions.get("sni_hostname"),
        })
        return httpx.Response(200, text="secure")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False) as client:
        response = await safe_get_once(client, "https://secure.example:8443/report?q=1")

    assert observed == {
        "url": "https://93.184.216.34:8443/report?q=1",
        "host": "secure.example:8443",
        "connection": "close",
        "sni": "secure.example",
    }
    assert isinstance(observed["sni"], str)  # required by installed httpcore/AnyIO backend
    assert str(response.url) == "https://secure.example:8443/report?q=1"


@pytest.mark.asyncio
async def test_every_redirect_hop_is_resolved_and_private_destination_is_never_fetched(monkeypatch):
    resolved_hosts = []
    fetched_hosts = []

    def dns(host, port, **_kwargs):
        resolved_hosts.append(host)
        address = "93.184.216.34" if host == "public.example" else "192.168.1.20"
        return [_answer(address, port)]

    def handler(request: httpx.Request) -> httpx.Response:
        fetched_hosts.append(request.headers.get("host"))
        return httpx.Response(302, headers={"location": "http://private.example/admin"})

    monkeypatch.setattr(socket, "getaddrinfo", dns)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False) as client:
        response = await safe_get(client, "https://public.example/start")

    assert response is None
    assert resolved_hosts == ["public.example", "private.example"]
    assert fetched_hosts == ["public.example"]


@pytest.mark.asyncio
async def test_public_ipv6_answer_is_pinned_with_bracketed_transport_url(monkeypatch):
    observed = {}
    public_v6 = "2606:4700:4700::1111"
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda _host, port, **_kwargs: [_answer(public_v6, port)],
    )

    def handler(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["host"] = request.headers.get("host")
        observed["sni"] = request.extensions.get("sni_hostname")
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        response = await safe_get_once(client, "https://ipv6.example/v6")

    assert response is not None
    assert observed == {
        "url": "https://[2606:4700:4700::1111]/v6",
        "host": "ipv6.example",
        "sni": "ipv6.example",
    }


def test_non_public_ipv6_and_mixed_family_answers_are_rejected(monkeypatch):
    def private_v6(_host, port, **_kwargs):
        return [_answer("2001:db8::1", port)]

    monkeypatch.setattr(socket, "getaddrinfo", private_v6)
    assert resolve_public_http_url("https://private-v6.example/") is None

    def mixed_family(_host, port, **_kwargs):
        return [_answer("93.184.216.34", port), _answer("fd00::1", port)]

    monkeypatch.setattr(socket, "getaddrinfo", mixed_family)
    assert resolve_public_http_url("https://mixed-family.example/") is None
