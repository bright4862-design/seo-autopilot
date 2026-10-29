"""Private Extended 500 collection tests: raw crawler reuse, safety and privacy.

All URLs and HTML in this module are fixture-only; no live site, Base44 or
Cloud Tasks operations. The child process launcher is disabled in production.
"""
import asyncio
import json

import pytest

from app import scanner
from app.extract import extract_page
from app.extended500_private_collector import (
    COLLECTOR_VERSION,
    Extended500CollectionRefused,
    _collector_child,
    run_isolated_extended500_collection,
    validate_extended500_collection_request,
    validate_extended500_collection_result,
)

ORIGIN = "https://example.com"


def frozen():
    return {
        "id": "scan_one", "owner_user_id": "owner_one",
        "project_id": "project_one", "request_id": "request_one",
        "idempotency_key": "request_one", "scan_mode": "extended_500",
        "status": "queued", "attempt_count": 1,
        "website_url": f"{ORIGIN}/", "normalized_domain": "example.com",
        "respect_robots_txt": True, "owner_attested_robots_override": False,
        "path_prefix": None,
    }


def raw_result(n=2):
    pages = [
        {"url": f"{ORIGIN}/p-{i}", "final_url": f"{ORIGIN}/p-{i}",
         "status_code": 200, "content_type": "text/html",
         "title": "Fixture", "main_text": "private main text",
         "_reachability_links": [{"href": f"{ORIGIN}/"}],
         "future_secret_field": "do not leak"}
        for i in range(n)
    ]
    return {
        "success": True, "scan_mode": "extended_500",
        "pages": pages, "crawled_pages": [dict(p) for p in pages],
        "pages_crawled": n, "pages_found": n + 10,
        "scan_coverage": {"urls_attempted": n, "usable_html_pages": n,
                          "unique_retained_destinations": n},
        "release_gate_eligible": False,
    }


def test_private_crawl_is_disabled_before_process_creation(monkeypatch):
    def bomb(*args, **kwargs):
        raise AssertionError("must not create any subprocess")
    monkeypatch.setattr("app.extended500_private_collector.mp.get_context", bomb)
    with pytest.raises(Extended500CollectionRefused, match="collector_disabled"):
        run_isolated_extended500_collection(frozen())
    assert scanner.resolve_scan_budget("advanced")["max_pages"] == 150
    assert scanner.resolve_scan_budget("extended_500")["max_pages"] == 150


@pytest.mark.parametrize("change,expected", [
    ({"scan_mode": "standard_150"}, "frozen_extended500"),
    ({"scan_mode": "advanced"}, "frozen_extended500"),
    ({"status": "complete"}, "frozen_extended500"),
    ({"owner_user_id": "bad owner"}, "identity_invalid"),
    ({"request_id": "../request"}, "identity_invalid"),
    ({"attempt_count": True}, "scope_invalid"),
    ({"attempt_count": 0}, "scope_invalid"),
    ({"respect_robots_txt": False}, "scope_invalid"),
    ({"owner_attested_robots_override": True}, "scope_invalid"),
    ({"path_prefix": "/blog/"}, "scope_invalid"),
    ({"website_url": "https://localhost/"}, "root_url_invalid"),
    ({"website_url": "http://127.0.0.1/"}, "root_url_invalid"),
    ({"website_url": "https://example.com/private"}, "root_url_invalid"),
    ({"website_url": "https://example.com/?token=secret"}, "root_url_invalid"),
    ({"website_url": "https://user:pass@example.com/"}, "root_url_invalid"),
    ({"normalized_domain": "another.com"}, "domain_invalid"),
])
def test_request_fails_closed_for_wrong_owner_scope_mode_or_target(change, expected):
    with pytest.raises(Extended500CollectionRefused, match=expected):
        validate_extended500_collection_request({**frozen(), **change})


@pytest.mark.parametrize("timeout,concurrency", [(19, 4), (121, 4), (120, 0), (120, 9), (True, 4), (120, 1.0)])
def test_invalid_runtime_budgets_rejected(timeout, concurrency):
    with pytest.raises(Extended500CollectionRefused, match="budget_invalid"):
        validate_extended500_collection_request(frozen(), timeout_seconds=timeout, concurrency=concurrency)


@pytest.mark.parametrize("n", [1, 150, 500])
def test_valid_boundary_counts_are_unreviewed_and_private(n):
    projected = validate_extended500_collection_result(frozen(), raw_result(n))
    assert len(projected["pages"]) == projected["pages_crawled"] == n
    assert projected["review_status"] == "not_reviewed"
    assert projected["pages_reviewed"] == 0
    assert projected["release_gate_eligible"] is False
    assert projected["extended500_collector_version"] == COLLECTOR_VERSION
    assert projected["canonical_mode"] == "extended_500"
    assert projected["scan_id"] == "scan_one"
    assert projected["request_id"] == "request_one"
    for page in projected["pages"]:
        for hidden in ["main_text", "_reachability_links", "future_secret_field"]:
            assert hidden not in page
    assert "main_text" in raw_result(1)["pages"][0]


@pytest.mark.parametrize("change,expected", [
    ({"success": False}, "collection_failed"),
    ({"scan_mode": "standard_150"}, "foreign_collection_mode"),
    ({"release_gate_eligible": True}, "must_not_assert_review"),
    ({"review_status": "complete"}, "must_not_assert_review"),
    ({"pages_crawled": 3}, "assessed_count_invalid"),
    ({"pages_crawled": True}, "assessed_count_invalid"),
    ({"pages_found": 0}, "discovered_count_invalid"),
    ({"pages_found": True}, "discovered_count_invalid"),
    ({"scan_coverage": {}}, "coverage_invalid"),
    ({"scan_coverage": {"urls_attempted": 0, "usable_html_pages": 2,
                        "unique_retained_destinations": 2}}, "denominator_invalid"),
    ({"scan_coverage": {"urls_attempted": 2, "usable_html_pages": 3,
                        "unique_retained_destinations": 2}}, "denominator_invalid"),
    ({"scan_coverage": {"urls_attempted": 2, "usable_html_pages": 2,
                        "unique_retained_destinations": 1}}, "denominator_invalid"),
])
def test_untruthful_results_rejected(change, expected):
    with pytest.raises(Extended500CollectionRefused, match=expected):
        validate_extended500_collection_result(frozen(), {**raw_result(2), **change})


def test_reject_501_pages_and_empty_collection_and_duplicate_destinations():
    with pytest.raises(Extended500CollectionRefused, match="budget_exceeded"):
        validate_extended500_collection_result(frozen(), raw_result(501))
    with pytest.raises(Extended500CollectionRefused, match="empty"):
        validate_extended500_collection_result(frozen(), raw_result(0))
    result = raw_result(2)
    result["pages"][1]["final_url"] = result["pages"][0]["final_url"]
    result["crawled_pages"][1]["final_url"] = result["pages"][0]["final_url"]
    with pytest.raises(Extended500CollectionRefused, match="duplicate_destination"):
        validate_extended500_collection_result(frozen(), result)


def test_mirror_inconsistency_and_foreign_raw_page_rejected():
    result = raw_result(2)
    result["crawled_pages"].pop()
    with pytest.raises(Extended500CollectionRefused, match="mirror_mismatch"):
        validate_extended500_collection_result(frozen(), result)
    result = raw_result(2)
    result["pages"][1] = {"title": "missing destination"}
    result["crawled_pages"][1] = {"title": "missing destination"}
    with pytest.raises(Extended500CollectionRefused, match="page_identity_missing"):
        validate_extended500_collection_result(frozen(), result)


class FakeConn:
    def __init__(self):
        self.data = None
        self.closed = False

    def send_bytes(self, value):
        self.data = value

    def close(self):
        self.closed = True


def test_child_injects_500_budget_only_for_extended_mode(monkeypatch):
    seen = {}
    async def fake_run_scan(url, **kwargs):
        seen["url"] = url
        seen["mode"] = kwargs["scan_mode"]
        seen["budget"] = scanner.resolve_scan_budget(kwargs["scan_mode"], kwargs["timeout_seconds"], job_mode=True)
        return raw_result(500)

    monkeypatch.setattr(scanner, "run_scan", fake_run_scan)
    assert scanner.resolve_scan_budget("extended_500")["max_pages"] == 150
    conn = FakeConn()
    try:
        _collector_child(conn, frozen(), 120, 4)
        outcome = json.loads(conn.data)
        assert outcome["ok"] is True, outcome
        assert len(outcome["result"]["pages"]) == 500
        assert outcome["result"]["review_status"] == "not_reviewed"
        assert seen["url"] == f"{ORIGIN}/"
        assert seen["mode"] == "extended_500"
        assert seen["budget"]["max_pages"] == 500
        assert scanner.resolve_scan_budget("advanced")["max_pages"] == 150
    finally:
        scanner.SCAN_BUDGETS.pop("extended_500", None)
    assert conn.closed
    assert scanner.resolve_scan_budget("extended_500")["max_pages"] == 150


@pytest.mark.asyncio
async def test_existing_real_scanner_sitemap_510_does_not_exceed_private_500(monkeypatch):
    """Run production scanner code with only network I/O faked; no public tier edits."""
    from app.extract import extract_page

    class Policy:
        def directive_allowed(self, agent, url):
            return True
        def allowed(self, agent, url):
            return True
        def evidence(self):
            return {}

    class Landing:
        def __init__(self, url):
            self.url = url

    sitemap = [f"{ORIGIN}/item-{i:04d}" for i in range(510)]
    seen = []
    async def robots(*args, **kwargs):
        return Policy()
    async def landing(client, url, **kwargs):
        return Landing(url)
    async def sitemap_loader(*args, **kwargs):
        return list(sitemap)
    async def fetch(client, url, discovery, robots_policy=None):
        seen.append(url)
        await asyncio.sleep(0)
        html = "<html><title>Fixture</title><h1>Item</h1><p>Test page.</p></html>"
        return extract_page(html, url, url, 200, "text/html", discovery, include_links=True)
    async def validate(*args, **kwargs):
        return {}
    async def render(*args, **kwargs):
        return {"attempted": 0}

    monkeypatch.setattr(scanner, "is_public_http_url", lambda url: True)
    monkeypatch.setattr(scanner, "load_robots_policy", robots)
    monkeypatch.setattr(scanner, "safe_get", landing)
    monkeypatch.setattr(scanner, "load_sitemap_urls", sitemap_loader)
    monkeypatch.setattr(scanner, "fetch_and_extract", fetch)
    monkeypatch.setattr(scanner, "validate_canonical_targets", validate)
    monkeypatch.setattr(scanner, "run_render_followup", render)
    monkeypatch.setitem(scanner.SCAN_BUDGETS, "extended_500",
                        {"max_pages": 500, "timeout": 120, "fetch_timeout": 10,
                         "max_sitemap_fetches": 60})
    raw = await scanner.run_scan(f"{ORIGIN}/", scan_mode="extended_500",
                                 job_mode=True, timeout_seconds=120, concurrency=8)
    assert raw["success"] is True
    assert raw["scan_mode"] == "extended_500"
    assert raw["pages_crawled"] == len(raw["pages"]) == 500
    assert len(set(seen)) == 500
    assert raw["pages_found"] >= 500
    result = validate_extended500_collection_result(frozen(), raw)
    assert result["review_status"] == "not_reviewed"
    assert result["release_gate_eligible"] is False
    assert result["scan_coverage"]["unique_retained_destinations"] == 500
    # The original Standard150 mode is not raised.
    assert scanner.resolve_scan_budget("advanced")["max_pages"] == 150
