import httpx
import pytest

from app.robots_policy import SCANNER_USER_AGENT, load_robots_policy, owner_robots_override
from app.scanner import run_scan
from app.trust_discovery import enrich_scan_with_trust_pages


@pytest.mark.asyncio
async def test_crawl_uses_published_identity_across_discovery_and_page_requests(mock_network, monkeypatch):
    origin = "https://example.com"
    mock_network({
        "/robots.txt": {"body": "User-agent: *\nAllow: /", "content_type": "text/plain"},
        "/sitemap.xml": {"body": '<urlset><url><loc>https://example.com/about</loc></url></urlset>', "content_type": "application/xml"},
        "/": {"body": '<html><head><title>Home</title><link rel="canonical" href="https://example.com/canonical"></head><body><h1>Home</h1><a href="/about">About</a></body></html>'},
        "/about": {"status": 301, "headers": {"location": "/team"}},
        "/team": {"body": '<html><head><title>Team</title></head><body><h1>Team</h1></body></html>'},
        "/canonical": {"body": '<html><head><title>Canonical</title></head><body><h1>Canonical</h1></body></html>'},
    })
    requests = []
    # Observe real requests at the transport boundary, without replacing crawl logic.
    original = httpx.MockTransport.handle_async_request
    async def observe(self, request):
        requests.append(request)
        return await original(self, request)
    monkeypatch.setattr(httpx.MockTransport, "handle_async_request", observe)
    result = await run_scan(origin + "/", scan_mode="basic", concurrency=1)
    assert result["success"] is True
    assert {"/", "/robots.txt", "/sitemap.xml", "/about", "/team", "/canonical"} <= {r.url.path for r in requests}
    assert all(r.headers["user-agent"] == "FixListBot/1.0 (+https://getfixlist.com/crawler)" for r in requests)
    assert all(r.headers["host"] == "example.com" for r in requests)
    assert all(r.headers["connection"] == "close" for r in requests)


@pytest.mark.asyncio
async def test_matching_robots_group_remains_enforced_except_attested_override(mock_network):
    mock_network({"/robots.txt": {"body": "User-agent: FixListBot\nDisallow: /private\n\nUser-agent: *\nAllow: /", "content_type": "text/plain"}})
    async with httpx.AsyncClient() as client:
        policy = await load_robots_policy(client, "https://example.com")
    target = "https://example.com/private"
    assert policy.allowed(SCANNER_USER_AGENT, target) is False
    with owner_robots_override(True):
        assert policy.allowed(SCANNER_USER_AGENT, target) is True
        assert policy.directive_allowed(SCANNER_USER_AGENT, target) is False


@pytest.mark.asyncio
async def test_trust_enrichment_uses_same_published_identity(mock_network, monkeypatch):
    mock_network({"/": {"body": '<html><body><h1>Home</h1><a href="/contact">Contact</a></body></html>'}})
    observed = []
    original = httpx.MockTransport.handle_async_request
    async def observe(self, request):
        observed.append(request.headers["user-agent"])
        return await original(self, request)
    monkeypatch.setattr(httpx.MockTransport, "handle_async_request", observe)
    result = await enrich_scan_with_trust_pages({"success": True, "website_url": "https://example.com/", "pages": []})
    assert result["trust_page_discovery"]["attempted"] is True
    assert observed and set(observed) == {"FixListBot/1.0 (+https://getfixlist.com/crawler)"}


@pytest.mark.asyncio
async def test_rename_does_not_evade_legacy_scanner_disallow(mock_network):
    mock_network({"/robots.txt": {"body": "User-agent: FixListPythonScanner\nDisallow: /private\n\nUser-agent: *\nAllow: /", "content_type": "text/plain"}})
    async with httpx.AsyncClient() as client:
        policy = await load_robots_policy(client, "https://example.com")
    target = "https://example.com/private"
    assert policy.allowed(SCANNER_USER_AGENT, target) is False
    with owner_robots_override(True):
        assert policy.allowed(SCANNER_USER_AGENT, target) is True
        assert policy.directive_allowed(SCANNER_USER_AGENT, target) is False
        assert policy.allowed("Googlebot", target) is True
    assert policy.allowed(SCANNER_USER_AGENT, target) is False
