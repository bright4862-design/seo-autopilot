from app.main import SCANNER_BUILD_REVISION, ScanRequest, enforce_scan_response_page_budget
from app.scanner import resolve_scan_budget


def test_advanced_response_hard_caps_concurrent_overrun():
    pages = [{"url": f"https://example.com/{index}"} for index in range(151)]
    result = {
        "scan_mode": "advanced",
        "pages_crawled": 151,
        "pages": list(pages),
        "crawled_pages": list(pages),
        "technical_audit_summary": {"pages_crawled": 151},
        "scan_summary": {"pages_scanned": 151},
    }

    capped = enforce_scan_response_page_budget(result, "advanced")

    assert capped["pages_crawled"] == 150
    assert len(capped["pages"]) == 150
    assert len(capped["crawled_pages"]) == 150
    assert capped["technical_audit_summary"]["pages_crawled"] == 150
    assert capped["scan_summary"]["pages_scanned"] == 150
    assert capped["scanner_build_revision"] == SCANNER_BUILD_REVISION


def test_quick_response_uses_quick_mode_limit():
    pages = [{"url": f"https://example.com/{index}"} for index in range(50)]
    capped = enforce_scan_response_page_budget(
        {"pages_crawled": 50, "pages": pages, "crawled_pages": pages},
        "quick",
    )
    assert capped["pages_crawled"] == 40
    assert len(capped["pages"]) == 40


def test_standard_request_budget_keeps_150_page_cap():
    budget = resolve_scan_budget("advanced", 40)
    assert budget["max_pages"] == 150
    assert budget["timeout"] == 40
    assert budget["fetch_timeout"] <= 6
    assert budget["max_sitemap_fetches"] <= 20


def test_request_budget_cannot_raise_the_default_advanced_timeout():
    budget = resolve_scan_budget("advanced", 120)
    assert budget["max_pages"] == 150
    assert budget["timeout"] == 75


def test_scan_request_accepts_the_authenticated_gateway_cap():
    payload = ScanRequest(website_url="https://example.com", advisory_crawl_timeout_ms=40_000)
    assert payload.advisory_crawl_timeout_ms == 40_000
