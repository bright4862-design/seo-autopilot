"""Synthetic evidence for a private 500-page raw collector, NOT a product tier.

The test temporarily changes the in-process scanner budget for fixture-only
requests; it never changes the deployed Standard 150 mode, HTTP admission,
authority review, Base44 persistence, entitlement, or HMAC sealing. Passing
this test is only a necessary precondition for designing Extended 500.
"""
import asyncio

import pytest

from app import scanner
from app.extract import extract_page
from app.main import SCAN_RESPONSE_PAGE_LIMITS, enforce_scan_response_page_budget
from app.stage2_coverage_evidence import _bounded_pages


ORIGIN = "https://example.com"


class FakePolicy:
    def directive_allowed(self, _agent, _url):
        return True

    def allowed(self, _agent, _url):
        return True

    def evidence(self):
        return {}


class FakeLanding:
    def __init__(self, url):
        self.url = url


@pytest.mark.asyncio
async def test_synthetic_500_distinct_pages_are_retained_by_raw_collector(monkeypatch):
    baseline = scanner.resolve_scan_budget("advanced", job_mode=True)
    assert baseline["max_pages"] == 150

    seen_network = []
    sitemap = [f"{ORIGIN}/catalog/item-{n:04d}" for n in range(510)]

    async def robots(_client, _origin):
        return FakePolicy()

    async def landing(_client, url, **_kwargs):
        return FakeLanding(url)

    async def sitemap_loader(*_args, **_kwargs):
        return list(sitemap)

    async def fetch(_client, url, discovery, robots_policy=None):
        seen_network.append(url)
        await asyncio.sleep(0)
        html = (
            "<html><head><title>Catalog fixture</title></head>"
            "<body><h1>Catalog</h1>"
            "<p>Synthetic fixture page; no real website was scanned.</p>"
            "</body></html>"
        )
        return extract_page(html, url, url, 200, "text/html", discovery, include_links=True)

    async def validate(*_args, **_kwargs):
        return {}

    async def render(*_args, **_kwargs):
        return {"attempted": 0}

    monkeypatch.setattr(scanner, "is_public_http_url", lambda _url: True)
    monkeypatch.setitem(
        scanner.SCAN_BUDGETS, "advanced",
        {
            "max_pages": 500,
            "timeout": 120,
            "fetch_timeout": 10,
            "max_sitemap_fetches": 40,
        },
    )
    monkeypatch.setattr(scanner, "load_robots_policy", robots)
    monkeypatch.setattr(scanner, "safe_get", landing)
    monkeypatch.setattr(scanner, "load_sitemap_urls", sitemap_loader)
    monkeypatch.setattr(scanner, "fetch_and_extract", fetch)
    monkeypatch.setattr(scanner, "validate_canonical_targets", validate)
    monkeypatch.setattr(scanner, "run_render_followup", render)

    result = await scanner.run_scan(
        f"{ORIGIN}/", scan_mode="advanced", job_mode=True,
        timeout_seconds=120, concurrency=8,
    )

    assert result["success"] is True
    assert result["pages_crawled"] == 500
    assert len(result["pages"]) == 500
    assert len({page["final_url"] for page in result["pages"]}) == 500
    assert len(seen_network) == len(set(seen_network)) == 500
    assert result["scan_coverage"]["urls_attempted"] == 500
    assert result["scan_coverage"]["unique_retained_destinations"] == 500
    assert result["scan_coverage"]["usable_html_pages"] == 500
    assert result["pages_found"] >= 500

    # Deliberately demonstrate why passing this collector test cannot justify
    # publishing a 500-page tier. The live HTTP contract remains Standard 150.
    assert SCAN_RESPONSE_PAGE_LIMITS["advanced"] == 150
    published = enforce_scan_response_page_budget(dict(result), "advanced")
    assert published["pages_crawled"] == 150
    assert len(published["pages"]) == 150
    with pytest.raises(ValueError, match="at most 150"):
        _bounded_pages(result["pages"])


def test_public_budget_is_still_150_and_not_implicitly_extended():
    assert scanner.resolve_scan_budget("advanced")["max_pages"] == 150
    assert scanner.resolve_scan_budget("extended_500")["max_pages"] == 150
    assert SCAN_RESPONSE_PAGE_LIMITS["advanced"] == 150
