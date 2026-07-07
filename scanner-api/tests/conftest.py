"""Offline test harness.

Stubs all network I/O with httpx.MockTransport so the scanner never makes a
live call, and treats fixture hosts as public (no DNS) so the SSRF guard does
not block synthetic domains. Real SSRF behaviour is covered separately in
test_contract.py, which does NOT install this stub.
"""
import httpx
import pytest

# Capture the real class before any test monkeypatches httpx.AsyncClient.
_REAL_ASYNC_CLIENT = httpx.AsyncClient


def install_mock_network(monkeypatch, routes: dict):
    """Route every request to an in-memory fixture map.

    `routes` maps a full URL to {"body": str, "status": int, "content_type": str}.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        entry = routes.get(str(request.url)) or routes.get(request.url.path)
        if entry is None:
            return httpx.Response(404, text="")
        return httpx.Response(
            entry.get("status", 200),
            headers={"content-type": entry.get("content_type", "text/html")},
            text=entry.get("body", ""),
        )

    transport = httpx.MockTransport(handler)

    def factory(*args, **kwargs):
        kwargs.pop("follow_redirects", None)  # scanner manages redirects via safe_get
        kwargs["transport"] = transport
        return _REAL_ASYNC_CLIENT(*args, follow_redirects=False, **kwargs)

    monkeypatch.setattr("httpx.AsyncClient", factory)
    # Fixture hosts don't resolve in DNS; treat them as public for these tests.
    monkeypatch.setattr("app.scanner.is_public_http_url", lambda url: True)
    monkeypatch.setattr("app.security.is_public_http_url", lambda url: True)


@pytest.fixture
def mock_network(monkeypatch):
    def _install(routes):
        install_mock_network(monkeypatch, routes)
    return _install
