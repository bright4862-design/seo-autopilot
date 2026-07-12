from app.extract import extract_page
from app.indexability_postprocess import apply_indexability_quality_to_result
from app.indexability_quality import annotate_indexability_quality
from app.navigation_indexability import (
    annotate_navigation_indexability,
    build_navigation_indexability_findings,
    summarize_navigation_indexability,
)
from app.scanner import create_finding


SITEMAP = {
    "discovered_from": ["sitemap"],
    "source_pages": ["/sitemap.xml"],
    "link_text_samples": [],
}
INTERNAL = {
    "discovered_from": ["sitemap", "internal_link"],
    "source_pages": ["/category"],
    "link_text_samples": ["Product"],
}


def _page(url: str, discovery=None):
    page = extract_page(
        "<html><head><title>Useful page</title></head><body><h1>Useful page</h1><p>Helpful content for visitors and search engines.</p></body></html>",
        url,
        url,
        200,
        "text/html",
        discovery or SITEMAP,
    )
    annotate_indexability_quality(page)
    annotate_navigation_indexability(page)
    return page


def test_sitemap_only_clean_url_is_a_verification_candidate():
    page = _page("https://example.com/products/alpha")

    assert page["potential_orphan_in_sample"] is True
    assert page["orphan_evidence_state"] == "candidate_needs_verification"


def test_internally_linked_page_is_not_an_orphan_candidate():
    page = _page("https://example.com/products/alpha", INTERNAL)

    assert page["potential_orphan_in_sample"] is False
    assert page["orphan_evidence_state"] == "internally_linked_in_sample"


def test_pagination_facets_and_tracking_are_excluded_from_orphan_evidence():
    pagination = _page("https://example.com/products?page=2")
    facet = _page("https://example.com/products?filter[color]=blue&sort=price")
    tracking = _page("https://example.com/products?utm_source=newsletter&gclid=abc")

    assert pagination["pagination_url"] is True
    assert pagination["orphan_evidence_state"] == "excluded_pagination"
    assert facet["faceted_navigation_url"] is True
    assert facet["indexable_faceted_url"] is True
    assert facet["orphan_evidence_state"] == "excluded_faceted_navigation"
    assert tracking["tracking_only_url"] is True
    assert tracking["orphan_evidence_state"] == "excluded_tracking_parameters"


def test_orphan_finding_requires_multiple_candidates_and_stays_non_scoring():
    one_page = [_page("https://example.com/products/one")]
    assert build_navigation_indexability_findings(one_page, create_finding) == []

    pages = [_page(f"https://example.com/products/{index}") for index in range(3)]
    finding = next(
        item
        for item in build_navigation_indexability_findings(pages, create_finding)
        if item["rule"] == "potential_orphan_pages"
    )

    assert finding["priority"] == "low"
    assert finding["evidence_status"] == "needs_verification"
    assert finding["limitation_code"] == "sampled_crawl_cannot_prove_orphan"
    assert finding["non_scoring"] is True
    assert finding["page_count"] == 3


def test_repeated_indexable_facets_create_one_strategy_review():
    pages = [
        _page(f"https://example.com/products?filter[color]=blue&page={index}")
        for index in range(1, 4)
    ]
    findings = build_navigation_indexability_findings(pages, create_finding)
    finding = next(item for item in findings if item["rule"] == "indexable_faceted_navigation")

    assert finding["priority"] == "low"
    assert finding["verification_state"] == "needs_verification"
    assert finding["page_count"] == 3
    assert all("?" in url for url in finding["affected_pages"])


def test_summary_reports_safeguards_and_candidates():
    pages = [
        _page("https://example.com/standalone"),
        _page("https://example.com/products?page=2"),
        _page("https://example.com/products?filter_brand=acme"),
        _page("https://example.com/products?utm_campaign=spring"),
    ]

    summary = summarize_navigation_indexability(pages)

    assert summary["potential_orphan_candidates"] == 1
    assert summary["pagination_pages"] == 1
    assert summary["faceted_navigation_pages"] == 1
    assert summary["tracking_only_pages"] == 1
    assert summary["orphan_evidence_state_counts"]["excluded_pagination"] == 1


def test_scan_postprocess_is_idempotent_and_exposes_navigation_evidence():
    pages = [_page(f"https://example.com/isolated/{index}") for index in range(3)]
    result = {
        "success": True,
        "pages": pages,
        "crawled_pages": pages,
        "raw_findings": [],
        "scan_summary": {},
        "technical_audit_summary": {},
    }

    first = apply_indexability_quality_to_result(result)
    second = apply_indexability_quality_to_result(first)

    rules = [item.get("rule") for item in second["raw_findings"]]
    assert rules.count("potential_orphan_pages") == 1
    assert second["navigation_indexability_evidence"]["potential_orphan_candidates"] == 3
    assert second["scan_summary"]["navigation_indexability_evidence"]["version"]
    assert second["technical_audit_summary"]["potential_orphan_candidates"] == 3
