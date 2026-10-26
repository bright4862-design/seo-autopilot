"""Regression coverage for explicitly gated, idle-frontier Standard 150 backfilling.

The small injected budget makes the same mechanics observable without a live
network or expensive 150-page review. No customer/production path is invoked.
"""
from urllib.parse import urlparse

import pytest

from app import scanner
from app.extract import classify_template, extract_page


ORIGIN = "https://example.com"
SITEMAP = [f"{ORIGIN}/products/item-{index}" for index in range(9)]


class _Policy:
    def directive_allowed(self, user_agent, url):
        return True

    def allowed(self, user_agent, url):
        return True

    def evidence(self):
        return {"state": "allowed"}


class _Landing:
    def __init__(self):
        self.url = f"{ORIGIN}/"


def _selected_initial_sitemap():
    return set(scanner.select_balanced_urls(
        SITEMAP,
        lambda url: classify_template(urlparse(url).path),
        lambda url: urlparse(url).path,
        2,
    ))


@pytest.fixture
def backfill_fixture(monkeypatch):
    requested = []
    selected = _selected_initial_sitemap()
    monkeypatch.setattr(scanner, "is_public_http_url", lambda url: True)
    monkeypatch.setitem(scanner.SCAN_BUDGETS, "advanced", {
        "max_pages": 3, "timeout": 40, "fetch_timeout": 3, "max_sitemap_fetches": 2,
    })

    async def robots(client, origin):
        return _Policy()

    async def landing(client, url, **kwargs):
        return _Landing()

    async def sitemap(*args, **kwargs):
        return list(SITEMAP)

    async def fetch(client, url, discovery, robots_policy=None):
        requested.append(url)
        collapse = url in selected and backfill_fixture_collapse[0]
        final_url = f"{ORIGIN}/" if collapse else url
        title = "Homepage" if url == f"{ORIGIN}/" else "Product"
        html = (
            f"<html><head><title>{title}</title></head>"
            f"<body><h1>{title}</h1><p>Useful business text.</p></body></html>"
        )
        return extract_page(
            html, url, final_url, 200, "text/html", discovery, include_links=True,
        )

    async def validate(*args, **kwargs):
        return {}

    async def render(*args, **kwargs):
        return {"attempted": 0}

    # A single mutable switch lets each test reuse the exact sitemap, seed and
    # fetch code and vary only the behavior the test is meant to exercise.
    backfill_fixture_collapse = [True]
    monkeypatch.setattr(scanner, "load_robots_policy", robots)
    monkeypatch.setattr(scanner, "safe_get", landing)
    monkeypatch.setattr(scanner, "load_sitemap_urls", sitemap)
    monkeypatch.setattr(scanner, "fetch_and_extract", fetch)
    monkeypatch.setattr(scanner, "validate_canonical_targets", validate)
    monkeypatch.setattr(scanner, "run_render_followup", render)
    return requested, selected, backfill_fixture_collapse


@pytest.mark.asyncio
async def test_idle_frontier_fills_unique_slots_only_when_explicitly_enabled(
    monkeypatch, backfill_fixture,
):
    requested, selected, collapse = backfill_fixture
    monkeypatch.setattr(scanner, "ENABLE_STANDARD150_SITEMAP_BACKFILL", False)
    off = await scanner.run_scan(f"{ORIGIN}/", scan_mode="advanced", job_mode=True, concurrency=1)
    off_requests = list(requested)
    requested.clear()

    monkeypatch.setattr(scanner, "ENABLE_STANDARD150_SITEMAP_BACKFILL", True)
    on = await scanner.run_scan(f"{ORIGIN}/", scan_mode="advanced", job_mode=True, concurrency=1)
    on_requests = list(requested)

    assert off["pages_crawled"] == 1
    assert off["scan_coverage"]["urls_attempted"] == 3
    assert len(off_requests) == 3
    assert off_requests[0] == f"{ORIGIN}/"
    assert set(off_requests[1:]) == selected
    assert "sitemap_backfill_version" not in off["crawl_timing"]

    assert on["pages_crawled"] == 3
    assert len(on["pages"]) == 3
    assert len({page["final_url"] for page in on["pages"]}) == 3
    assert on["scan_coverage"]["urls_attempted"] == 5
    assert on["crawl_timing"]["final_url_duplicates_deduped"] == 2
    assert on["crawl_timing"]["sitemap_backfill_enqueued"] == 2
    assert on["crawl_timing"]["sitemap_backfill_reserve_candidates"] == len(SITEMAP) - 2
    assert on_requests[:3] == off_requests
    assert len(set(on_requests)) == len(on_requests)
    assert set(on_requests[3:]).isdisjoint(selected)
    assert on["pages_crawled"] <= scanner.SCAN_BUDGETS["advanced"]["max_pages"]


@pytest.mark.asyncio
async def test_at_cap_keeps_original_fetch_prefix_unchanged(
    monkeypatch, backfill_fixture,
):
    requested, selected, collapse = backfill_fixture
    collapse[0] = False
    monkeypatch.setattr(scanner, "ENABLE_STANDARD150_SITEMAP_BACKFILL", False)
    off = await scanner.run_scan(f"{ORIGIN}/", scan_mode="advanced", job_mode=True, concurrency=1)
    old_requests = list(requested)
    requested.clear()

    monkeypatch.setattr(scanner, "ENABLE_STANDARD150_SITEMAP_BACKFILL", True)
    on = await scanner.run_scan(f"{ORIGIN}/", scan_mode="advanced", job_mode=True, concurrency=1)

    assert off["pages_crawled"] == on["pages_crawled"] == 3
    assert requested == old_requests
    assert len(requested) == 3
    assert on["crawl_timing"]["sitemap_backfill_enqueued"] == 0
    assert on["crawl_timing"]["sitemap_backfill_reserve_remaining"] == len(SITEMAP) - 2


@pytest.mark.asyncio
async def test_synchronous_scan_stays_unmodified_even_when_flag_is_on(
    monkeypatch, backfill_fixture,
):
    requested, selected, collapse = backfill_fixture
    monkeypatch.setattr(scanner, "ENABLE_STANDARD150_SITEMAP_BACKFILL", True)
    result = await scanner.run_scan(f"{ORIGIN}/", scan_mode="advanced", job_mode=False, concurrency=1)

    assert result["pages_crawled"] == 1
    assert len(requested) == 3
    assert "sitemap_backfill_version" not in result["crawl_timing"]
