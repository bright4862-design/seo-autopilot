from app.extract import extract_page
from app.review import (
    GROUPED_RECOMMENDATION_EVIDENCE_VERSION,
    build_page_pattern_findings,
)
from app.repair_coverage import PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION


DISCOVERY = {"discovered_from": ["sitemap"], "source_pages": ["/sitemap.xml"], "link_text_samples": []}


def page(url: str, metadata_markup: str) -> dict:
    evidence = extract_page(
        f'<html><head><title>Page</title><link rel="canonical" href="{url}">{metadata_markup}</head><body><h1>Page</h1><p>Useful page evidence.</p></body></html>',
        url,
        url,
        200,
        "text/html",
        DISCOVERY,
    )
    evidence["page_template_family"] = "activity_detail"
    return evidence


def metadata_fixes(pages: list[dict], **identity_context) -> list[dict]:
    return [fix for fix in build_page_pattern_findings(pages, **identity_context) if fix.get("category") == "meta_description"]


def test_mixed_metadata_states_become_one_evidence_specific_family_card():
    pages = [
        page("https://example.com/a", ""),
        page("https://example.com/b", ""),
        page("https://example.com/c", '<meta name="description" content="">'),
        page("https://example.com/d", '<meta name="description" content="">'),
        page("https://example.com/e", '<meta name="description" content="">'),
        page("https://example.com/f", '<meta name="description">'),
    ]

    [fix] = metadata_fixes(pages)

    assert fix["rule"] == "meta_description_unusable"
    assert fix["metadata_state_counts"] == {"missing": 2, "empty": 3, "malformed": 1}
    assert fix["combined_rules"] == [
        "missing_meta_description",
        "empty_meta_description",
        "malformed_meta_description",
    ]
    assert fix["page_count"] == 6
    assert "6 activity/detail pages" in fix["plain_english_explanation"]
    assert "2 missing tags" in fix["plain_english_explanation"]
    assert "3 empty values" in fix["plain_english_explanation"]
    assert "1 malformed elements" in fix["plain_english_explanation"]
    assert "activity/detail page pattern" in fix["grouping_explanation"]
    assert fix["grouped_recommendation_evidence_version"] == GROUPED_RECOMMENDATION_EVIDENCE_VERSION


def test_single_metadata_state_keeps_specific_rule_without_fake_combination():
    fixes = metadata_fixes([
        page("https://example.com/a", ""),
        page("https://example.com/b", ""),
    ])

    [fix] = fixes
    assert fix["rule"] == "missing_meta_description"
    assert fix["metadata_state_counts"] == {"missing": 2, "empty": 0, "malformed": 0}
    assert fix["combined_rules"] == []
    assert fix["page_count"] == 2
    assert fix["grouping_explanation"]


def test_three_200_routes_remain_three_affected_pages():
    pages = [page("https://example.com" + path, "") for path in ["/x", "/x/", "/X"]]
    [fix] = metadata_fixes(pages, scan_origin="https://example.com",
                           identity_version=PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION)
    assert fix["page_count"] == 3
    assert fix["affected_pages"] == ["https://example.com/x", "https://example.com/x/", "https://example.com/X"]
    assert fix["metadata_state_counts"]["missing"] == 3


def test_published_routes_survive_real_review_and_canonical_priority():
    from app.review import run_review
    from app.repair_contract_v2 import apply_canonical_repair_contract

    pages = [page("https://example.com" + path, "") for path in ["/x", "/x/", "/X"]]
    scan = {"website_url": "https://example.com", "pages": pages,
            "crawl_scope": {"requested_origin": "https://example.com"}}
    review = run_review(scan, identity_version=PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION)
    result = apply_canonical_repair_contract(review, scan, identity_version=PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION)
    [fix] = [item for item in result["canonical_repairs"] if item["category"] == "meta_description"]
    assert fix["affected_pages"] == ["https://example.com/x", "https://example.com/x/", "https://example.com/X"]
    assert fix["page_count"] == 3
    assert fix["family_breakdown"] == {"activity_detail": 3}
    assert fix["priority_context"]["affected_observed"] == 3
    assert fix["evidence_url_identity_version"] == PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION


def test_published_review_requires_scan_owned_origin():
    import pytest
    from app.review import run_review

    for scan in [{"normalized_domain": "example.com"},
                 {"website_url": "https://example.com", "crawl_scope": {"requested_origin": "not-an-origin"}}]:
        with pytest.raises(ValueError, match="trusted scan origin"):
            run_review(scan, identity_version=PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION)
