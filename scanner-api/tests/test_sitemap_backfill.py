"""Regression coverage for explicitly gated, idle-frontier Standard 150 backfilling.

The small injected budget makes the same mechanics observable without a live
network or expensive 150-page review. No customer/production path is invoked.
"""
import asyncio
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


@pytest.mark.asyncio
async def test_parallel_workers_refill_without_duplicate_claims_or_overcap(
    monkeypatch, backfill_fixture,
):
    requested, selected, collapse = backfill_fixture
    original_fetch = scanner.fetch_and_extract

    async def yield_to_other_workers(*args, **kwargs):
        await asyncio.sleep(0)
        return await original_fetch(*args, **kwargs)

    monkeypatch.setattr(scanner, "fetch_and_extract", yield_to_other_workers)
    monkeypatch.setattr(scanner, "ENABLE_STANDARD150_SITEMAP_BACKFILL", True)

    result = await scanner.run_scan(
        f"{ORIGIN}/", scan_mode="advanced", job_mode=True, concurrency=8,
    )

    assert result["pages_crawled"] == 3
    assert result["scan_coverage"]["unique_retained_destinations"] == 3
    assert result["scan_coverage"]["urls_attempted"] == 5
    assert len(requested) == len(set(requested)) == 5
    assert set(requested[:3]) == {f"{ORIGIN}/", *selected}
    assert result["crawl_timing"]["sitemap_backfill_enqueued"] == 2
    assert result["crawl_timing"]["sitemap_backfill_skipped"] == 0
    assert result["pages_crawled"] <= scanner.SCAN_BUDGETS["advanced"]["max_pages"]


@pytest.mark.asyncio
async def test_backfill_obeys_robots_and_never_fetches_disallowed_reserve(
    monkeypatch, backfill_fixture,
):
    requested, selected, collapse = backfill_fixture

    class DenyReserve(_Policy):
        def allowed(self, user_agent, url):
            return url == f"{ORIGIN}/" or url in selected

    async def robots(client, origin):
        return DenyReserve()

    monkeypatch.setattr(scanner, "load_robots_policy", robots)
    monkeypatch.setattr(scanner, "ENABLE_STANDARD150_SITEMAP_BACKFILL", True)

    result = await scanner.run_scan(
        f"{ORIGIN}/", scan_mode="advanced", job_mode=True, concurrency=2,
    )

    assert len(requested) == 3
    assert set(requested) == {f"{ORIGIN}/", *selected}
    assert result["pages_crawled"] == 3
    denied = [page for page in result["pages"] if page.get("fetch_error") == "blocked_by_robots_txt"]
    assert len(denied) == 2
    assert result["scan_coverage"]["access_unverified_pages"] >= 2
    assert result["crawl_timing"]["sitemap_backfill_enqueued"] == 2


@pytest.mark.asyncio
async def test_alias_exhaustion_stops_at_shared_claim_budget(
    monkeypatch, backfill_fixture,
):
    requested, selected, collapse = backfill_fixture
    large_sitemap = [f"{ORIGIN}/products/alias-{i}" for i in range(70)]

    async def sitemap(*args, **kwargs):
        return list(large_sitemap)

    async def all_redirect_to_seed(client, url, discovery, robots_policy=None):
        requested.append(url)
        html = "<html><head><title>Home</title></head><body><h1>Home</h1></body></html>"
        return extract_page(
            html, url, f"{ORIGIN}/", 200, "text/html", discovery, include_links=True,
        )

    monkeypatch.setattr(scanner, "load_sitemap_urls", sitemap)
    monkeypatch.setattr(scanner, "fetch_and_extract", all_redirect_to_seed)
    monkeypatch.setattr(scanner, "ENABLE_STANDARD150_SITEMAP_BACKFILL", True)

    result = await scanner.run_scan(
        f"{ORIGIN}/", scan_mode="advanced", job_mode=True, concurrency=8,
    )

    request_cap = scanner.SCAN_BUDGETS["advanced"]["max_pages"] * 8
    assert len(requested) == len(set(requested)) == request_cap
    assert result["scan_coverage"]["urls_attempted"] == request_cap
    assert result["pages_crawled"] == result["scan_coverage"]["unique_retained_destinations"] == 1
    assert result["crawl_timing"]["final_url_duplicates_deduped"] == request_cap - 1
    assert result["crawl_timing"]["sitemap_backfill_enqueued"] == request_cap - 3
    assert result["crawl_timing"]["crawl_request_cap_reached"] is True
    assert result["crawl_timing"]["sitemap_backfill_reserve_truncated"] is True
    assert result["crawl_timing"]["sitemap_backfill_reserve_remaining"] > 0
    assert result["crawl_timing"]["queue_exhausted"] is False


@pytest.mark.asyncio
async def test_backfill_preserves_requested_path_scope(
    monkeypatch, backfill_fixture,
):
    requested, selected, collapse = backfill_fixture
    sitemap_urls = [
        *(f"{ORIGIN}/products/item-{i}" for i in range(10)),
        *(f"{ORIGIN}/private/item-{i}" for i in range(10)),
    ]

    async def sitemap(*args, **kwargs):
        return list(sitemap_urls)

    monkeypatch.setattr(scanner, "load_sitemap_urls", sitemap)
    monkeypatch.setattr(scanner, "ENABLE_STANDARD150_SITEMAP_BACKFILL", True)
    result = await scanner.run_scan(
        f"{ORIGIN}/products/", path_prefix="/products/",
        scan_mode="advanced", job_mode=True, concurrency=4,
    )

    assert result["pages_crawled"] <= 3
    assert requested
    assert all(url.startswith(f"{ORIGIN}/products/") for url in requested)
    assert all(page["url"].startswith(f"{ORIGIN}/products/") for page in result["pages"])


@pytest.mark.asyncio
async def test_truncated_unusable_reserve_is_not_full_inventory_proof(
    monkeypatch, backfill_fixture,
):
    requested, selected, collapse = backfill_fixture
    # The sitemap fixture deliberately returns disallowed-scope URLs.
    # This checks the independent enqueue boundary even if an upstream
    # sitemap discovery implementation changes its scope filtering.
    async def sitemap(*args, **kwargs):
        return [f"{ORIGIN}/outside/item-{i}" for i in range(70)]

    monkeypatch.setattr(scanner, "load_sitemap_urls", sitemap)
    monkeypatch.setattr(scanner, "ENABLE_STANDARD150_SITEMAP_BACKFILL", True)
    result = await scanner.run_scan(
        f"{ORIGIN}/products/", path_prefix="/products/",
        scan_mode="advanced", job_mode=True, concurrency=8,
    )

    assert requested == [f"{ORIGIN}/products/"]
    assert result["pages_crawled"] == 1
    assert result["crawl_timing"]["sitemap_backfill_reserve_truncated"] is True
    assert result["crawl_timing"]["sitemap_backfill_reserve_remaining"] == 0
    # Exhaustion of a bounded reserve must never be marketed as inventory proof.
    assert result["crawl_timing"]["queue_exhausted"] is False


@pytest.mark.asyncio
async def test_full_standard_150_budget_is_unchanged_with_flag_enabled(
    monkeypatch, backfill_fixture,
):
    requested, selected, collapse = backfill_fixture
    collapse[0] = False
    large_sitemap = [f"{ORIGIN}/products/real-{i}" for i in range(800)]

    async def sitemap(*args, **kwargs):
        return list(large_sitemap)

    monkeypatch.setattr(scanner, "load_sitemap_urls", sitemap)
    monkeypatch.setitem(scanner.SCAN_BUDGETS, "advanced", {
        "max_pages": 150, "timeout": 75, "fetch_timeout": 10,
        "max_sitemap_fetches": 40,
    })
    monkeypatch.setattr(scanner, "ENABLE_STANDARD150_SITEMAP_BACKFILL", False)
    baseline = await scanner.run_scan(
        f"{ORIGIN}/", scan_mode="advanced", job_mode=True, concurrency=8,
    )
    baseline_requests = list(requested)
    requested.clear()

    monkeypatch.setattr(scanner, "ENABLE_STANDARD150_SITEMAP_BACKFILL", True)
    enabled = await scanner.run_scan(
        f"{ORIGIN}/", scan_mode="advanced", job_mode=True, concurrency=8,
    )

    assert baseline["pages_crawled"] == enabled["pages_crawled"] == 150
    assert len(requested) == len(baseline_requests) == 150
    assert requested == baseline_requests
    assert len(set(requested)) == 150
    assert enabled["crawl_timing"]["sitemap_backfill_enqueued"] == 0
    assert baseline["sampling_evidence"]["sampling_version"] == enabled["sampling_evidence"]["sampling_version"]
