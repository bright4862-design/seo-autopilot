"""Offline test harness.

Stubs all network I/O with httpx.MockTransport so the scanner never makes a
live call, and treats fixture hosts as public (no DNS) so the SSRF guard does
not block synthetic domains. Real SSRF behaviour is covered separately in
test_contract.py, which does NOT install this stub.
"""
import httpx
import pytest
import socket

# Capture the real class before any test monkeypatches httpx.AsyncClient.
_REAL_ASYNC_CLIENT = httpx.AsyncClient


def install_mock_network(monkeypatch, routes: dict):
    """Route every request to an in-memory fixture map.

    `routes` maps a full URL to {"body": str, "status": int, "content_type": str}.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        # Production connects to the validated numeric IP. Rebuild the logical
        # fixture URL from the preserved Host header without changing that
        # transport behavior in application code.
        authority = request.headers.get("host", "")
        logical_url = f"{request.url.scheme}://{authority}{request.url.raw_path.decode('ascii')}"
        entry = routes.get(logical_url) or routes.get(request.url.path)
        if entry is None:
            return httpx.Response(404, text="")
        response_headers = {"content-type": entry.get("content_type", "text/html")}
        response_headers.update(entry.get("headers", {}))
        return httpx.Response(
            entry.get("status", 200),
            headers=response_headers,
            text=entry.get("body", ""),
        )

    transport = httpx.MockTransport(handler)

    def factory(*args, **kwargs):
        kwargs.pop("follow_redirects", None)  # scanner manages redirects via safe_get
        kwargs["transport"] = transport
        return _REAL_ASYNC_CLIENT(*args, follow_redirects=False, **kwargs)

    monkeypatch.setattr("httpx.AsyncClient", factory)
    # Fixture hosts don't resolve in DNS. Supply one deterministic public DNS
    # snapshot so the same IP-pinning path runs under tests.
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda _host, port, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", port))
        ],
    )


@pytest.fixture
def mock_network(monkeypatch):
    def _install(routes):
        install_mock_network(monkeypatch, routes)
    return _install
