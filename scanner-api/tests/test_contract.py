import pytest

from app.scanner import run_scan, stable_id
from app.security import is_public_http_url


@pytest.mark.asyncio
async def test_invalid_url_contract():
    result = await run_scan("not a url", scan_mode="advanced")
    assert result["success"] is False
    assert "error" in result


@pytest.mark.parametrize("bad_url", [
    "https://exa mple.com/",   # whitespace in host
    "https://foo/",            # host without a dot, not allowlisted
    "http://",                 # missing host
])
@pytest.mark.asyncio
async def test_url_validation_rejects_malformed(bad_url):
    result = await run_scan(bad_url, scan_mode="advanced")
    assert result["success"] is False


@pytest.mark.parametrize("blocked_url", [
    "http://169.254.169.254/latest/meta-data/",  # cloud metadata / link-local
    "http://127.0.0.1/",                          # loopback
    "http://localhost/",                          # loopback by name
    "http://10.0.0.5/",                           # private range
])
@pytest.mark.asyncio
async def test_ssrf_guard_blocks_internal_hosts(blocked_url):
    result = await run_scan(blocked_url, scan_mode="advanced")
    assert result["success"] is False
    assert "public host" in result.get("error", "")


def test_ssrf_guard_unit(monkeypatch):
    import ipaddress
    import socket

    def fake_getaddrinfo(host, *args, **kwargs):
        # Literal IPs pass through unchanged; names resolve to a fixed public IP.
        try:
            ipaddress.ip_address(host)
            ip = host
        except ValueError:
            ip = "93.184.216.34"  # public
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    assert is_public_http_url("https://example.com/") is True
    assert is_public_http_url("http://169.254.169.254/") is False
    assert is_public_http_url("http://127.0.0.1/") is False
    assert is_public_http_url("ftp://example.com/") is False


class _FakeResponse:
    def __init__(self, status_code, headers=None, url="http://pub.example.com/", text=""):
        self.status_code = status_code
        self.headers = headers or {}
        self.url = url
        self.text = text


@pytest.mark.asyncio
async def test_safe_get_blocks_malformed_redirect_location(monkeypatch):
    from app.security import safe_get

    class _BadRedirectClient:
        def __init__(self):
            self.fetched = []

        async def get(self, url):
            self.fetched.append(url)
            return _FakeResponse(302, {"location": "ht!tp://[::bad::]/\x00"}, url)

    monkeypatch.setattr("app.security.is_public_http_url", lambda url: True)
    client = _BadRedirectClient()
    result = await safe_get(client, "http://pub.example.com/")
    assert result is None


def test_stable_id_is_deterministic():
    first = stable_id("missing_title|/|Add a clear search title")
    second = stable_id("missing_title|/|Add a clear search title")
    assert first == second
    assert first.startswith("finding_")
    assert len(first) == len("finding_") + 12
    assert first != stable_id("different|input|value")


@pytest.mark.asyncio
async def test_success_contract_keys(monkeypatch):
    # Keep hermetic: bypass live DNS in the SSRF guard for a known-good host.
    monkeypatch.setattr("app.scanner.is_public_http_url", lambda url: True)

    async def fake_load_sitemap_urls(*args, **kwargs):
        return []

    async def fake_fetch_and_extract(client, url, discovery):
        return {
            "url": url,
            "final_url": url,
            "path": "/",
            "status_code": 200,
            "fetch_error": "",
            "url_confidence": "confirmed_seed",
            "url_suspicion_reasons": [],
            "discovered_from": ["seed"],
            "source_pages": [],
            "link_text_samples": [],
            "title": "Home",
            "meta_description": "Description",
            "h1": "Home",
            "h1_count": 1,
            "canonical": url,
            "indexable": True,
            "estimated_page_intent": "standard",
            "image_missing_alt_count": 0,
            "_html": "",
        }

    monkeypatch.setattr("app.scanner.load_sitemap_urls", fake_load_sitemap_urls)
    monkeypatch.setattr("app.scanner.fetch_and_extract", fake_fetch_and_extract)

    result = await run_scan("https://example.com/", scan_mode="advanced")
    assert result["success"] is True
    assert isinstance(result["pages"], list)
    assert isinstance(result["recommendations"], list)
    assert isinstance(result["verified_failed_pages"], list)
    assert isinstance(result["suspicious_url_artifacts"], list)
    assert isinstance(result["technical_audit_summary"], dict)


class _FakeRedirectClient:
    """Returns a redirect to an internal host, then 200 if followed."""
    def __init__(self, location):
        self.location = location
        self.fetched = []

    async def get(self, url):
        self.fetched.append(url)
        if url == "http://pub.example.com/":
            return _FakeResponse(302, {"location": self.location}, url)
        return _FakeResponse(200, {"content-type": "text/html"}, url, "<html></html>")


@pytest.mark.asyncio
async def test_safe_get_blocks_redirect_to_internal(monkeypatch):
    from app.security import safe_get
    client = _FakeRedirectClient("http://169.254.169.254/latest/meta-data/")
    result = await safe_get(client, "http://pub.example.com/")
    # Must refuse before ever fetching the internal target.
    assert result is None
    assert "http://169.254.169.254/latest/meta-data/" not in client.fetched


@pytest.mark.asyncio
async def test_safe_get_allows_public_redirect(monkeypatch):
    from app.security import safe_get
    client = _FakeRedirectClient("https://example.com/final")
    monkeypatch.setattr("app.security.is_public_http_url", lambda url: True)
    result = await safe_get(client, "http://pub.example.com/")
    assert result is not None
    assert result.status_code == 200
