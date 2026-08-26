import pytest

from app import scanner
from app.extract import extract_page


class Policy:
    def allowed(self, user_agent, url):
        return True

    def evidence(self):
        return {}


class LandingResponse:
    def __init__(self, url):
        self.url = url


@pytest.mark.asyncio
async def test_final_url_dedup_keeps_one_homepage_and_backfills_unique_capacity(monkeypatch):
    monkeypatch.setattr(scanner, "is_public_http_url", lambda url: True)
    monkeypatch.setitem(
        scanner.SCAN_BUDGETS,
        "basic",
        {"max_pages": 2, "timeout": 20, "fetch_timeout": 3, "max_sitemap_fetches": 2},
    )

    async def fake_load_robots_policy(client, origin):
        return Policy()

    async def fake_safe_get(client, url, **_kwargs):
        return LandingResponse("https://example.com/")

    async def fake_load_sitemap_urls(*args, **kwargs):
        return ["https://example.com"]

    async def fake_fetch_and_extract(client, url, discovery, robots_policy=None):
        is_home = url.rstrip("/") == "https://example.com"
        final_url = "https://example.com/" if is_home else url
        html = (
            '<html><head><title>Home</title></head><body><h1>Home</h1>'
            '<a href="/about">About</a><p>Useful homepage content.</p></body></html>'
            if is_home
            else '<html><head><title>About</title></head><body><h1>About</h1><p>Useful about content.</p></body></html>'
        )
        return extract_page(
            html,
            url,
            final_url,
            200,
            "text/html",
            discovery,
            include_links=True,
        )

    async def fake_validate(*args, **kwargs):
        return {}

    async def fake_render_followup(*args, **kwargs):
        return {"attempted": 0}

    monkeypatch.setattr(scanner, "load_robots_policy", fake_load_robots_policy)
    monkeypatch.setattr(scanner, "safe_get", fake_safe_get)
    monkeypatch.setattr(scanner, "load_sitemap_urls", fake_load_sitemap_urls)
    monkeypatch.setattr(scanner, "fetch_and_extract", fake_fetch_and_extract)
    monkeypatch.setattr(scanner, "validate_canonical_targets", fake_validate)
    monkeypatch.setattr(scanner, "run_render_followup", fake_render_followup)

    result = await scanner.run_scan("https://example.com/", scan_mode="basic", concurrency=2)

    assert result["pages_crawled"] == 2
    assert [page["path"] for page in result["pages"]].count("/") == 1
    assert {page["path"] for page in result["pages"]} == {"/", "/about"}
    assert result["technical_audit_summary"]["final_url_dedup_version"] == scanner.FINAL_URL_DEDUP_VERSION
    assert result["technical_audit_summary"]["final_url_duplicates_deduped"] == 1
    homepage = next(page for page in result["pages"] if page["path"] == "/")
    assert set(homepage["discovered_from"]) == {"seed", "sitemap"}
    assert homepage["url_confidence"] == "confirmed_seed"
