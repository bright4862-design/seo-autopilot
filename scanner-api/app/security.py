import ipaddress
import socket
from urllib.parse import urlparse


REDIRECT_STATUSES = {301, 302, 303, 307, 308}


def is_public_http_url(url: str) -> bool:
    """True only if url is http(s) and its host resolves exclusively to public IPs.

    Blocks SSRF vectors: loopback, private ranges, link-local (incl. cloud
    metadata 169.254.169.254), reserved, multicast, and unspecified addresses.
    """
    try:
        parsed = urlparse(str(url or ""))
    except Exception:
        return False
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except (socket.gaierror, UnicodeError, ValueError, OSError):
        return False
    if not infos:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False
    return True


async def safe_get(client, url: str, max_redirects: int = 5):
    """GET that validates every redirect hop against SSRF before touching it.

    Requires the client to NOT auto-follow redirects (follow_redirects=False),
    otherwise httpx would fetch the internal target before we can block it.
    Returns the final httpx.Response, or None if a hop is non-public or the
    redirect chain is too long.
    """
    import httpx

    current = str(url or "")
    for _ in range(max_redirects + 1):
        if not is_public_http_url(current):
            return None
        response = await client.get(current)
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
