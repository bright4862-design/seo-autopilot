"""Metadata-state and contextual duplicate-title regressions."""

from app.extract import extract_page
from app.metadata_title_evidence import (
    classify_duplicate_title_context,
    is_generic_fallback_title,
)
from app.review import build_page_pattern_findings, compute_health_score
from app.scanner import (
    build_findings,
    calculate_health_score,
    duplicate_title_findings,
    group_findings,
)

DESCRIPTION_RULES = {
    "missing_meta_description",
    "empty_meta_description",
    "malformed_meta_description",
}


def extracted(
    html: str,
    url: str = "https://example.com/page",
    *,
    status_code: int = 200,
    content_type: str = "text/html; charset=utf-8",
    fetch_error: str = "",
):
    return extract_page(
        html,
        url,
        url,
        status_code,
        content_type,
        {"discovered_from": ["sitemap"], "source_pages": ["/sitemap.xml"], "link_text_samples": []},
        fetch_error=fetch_error,
    )


def page(url: str, title: str, **extra):
    return {
        "url": url,
        "final_url": url,
        "path": "/" + url.split("/", 3)[-1] if url.count("/") >= 3 else "/",
        "status_code": 200,
        "content_type": "text/html",
        "indexable": True,
        "title": title,
        "meta_description": "Valid description",
        "meta_description_state": "present_valid",
        "h1_count": 1,
        "canonical": url,
        "page_template_family": extra.pop("page_template_family", "standard"),
        "estimated_page_intent": "public",
        **extra,
    }


def description_rules(pages):
    return {item["rule"] for item in build_findings(pages)} & DESCRIPTION_RULES


def test_absent_empty_valid_malformed_and_whitespace_descriptions_are_distinct():
    missing = extracted("<html><head><title>Missing</title></head><body><h1>Page</h1></body></html>")
    empty = extracted('<html><head><title>Empty</title><meta name="description" content=""></head><body><h1>Page</h1></body></html>')
    whitespace = extracted('<html><head><title>Whitespace</title><meta name="description" content="   "></head><body><h1>Page</h1></body></html>')
    malformed = extracted('<html><head><title>Malformed</title><meta name="description"></head><body><h1>Page</h1></body></html>')
    valid = extracted('<html><head><title>Valid</title><meta name="description" content="Useful summary"></head><body><h1>Page</h1></body></html>')

    assert missing["meta_description_state"] == "missing"
    assert empty["meta_description_state"] == "present_empty"
    assert whitespace["meta_description_state"] == "present_empty"
    assert malformed["meta_description_state"] == "malformed"
    assert valid["meta_description_state"] == "present_valid"
    assert empty["meta_description_element_count"] == 1
    assert valid["meta_description"] == "Useful summary"


def test_mixed_description_elements_follow_deterministic_precedence():
    empty_and_valid = extracted(
        '<html><head><title>Mixed</title><meta name="description" content=""><meta name="description" content="Useful"></head><body><h1>Page</h1></body></html>'
    )
    empty_and_malformed = extracted(
        '<html><head><title>Mixed malformed</title><meta name="description" content=""><meta name="description"></head><body><h1>Page</h1></body></html>'
    )

    assert empty_and_valid["meta_description_state"] == "present_valid"
    assert empty_and_valid["meta_description"] == "Useful"
    assert empty_and_valid["meta_description_duplicate"] is True
    assert empty_and_malformed["meta_description_state"] == "malformed"
    assert empty_and_malformed["meta_description_duplicate"] is True


def test_non_200_non_html_and_fetch_failures_are_access_inconclusive():
    redirect = extracted(
        "<html><head><title>Redirect</title></head><body>Moved</body></html>",
        status_code=301,
    )
    no_content = extracted("", status_code=204)
    non_html = extracted('{"description":"not metadata"}', content_type="application/json")
    failed = extracted(
        "<html><head><title>Blocked</title></head></html>",
        fetch_error="connection_verification",
    )

    for record in [redirect, no_content, non_html, failed]:
        assert record["meta_description_state"] == "access_inconclusive"
        assert description_rules([record]) == set()


def test_empty_successful_html_and_head_boundary_remain_excluded_states():
    incomplete = extracted("")
    implied_head = extracted(
        '<html><title>Implied head</title><meta name="description" content="Useful"><body><h1>Page</h1></body></html>'
    )

    assert incomplete["meta_description_state"] == "raw_html_incomplete"
    assert implied_head["meta_description_state"] == "head_parse_boundary"
    assert implied_head["meta_description"] == "Useful"
    assert description_rules([incomplete, implied_head]) == set()


def test_scanner_preserves_description_states_and_review_combines_the_family_task():
    missing = extracted("<html><head><title>Missing</title></head><body><h1>Page</h1></body></html>", "https://example.com/missing")
    empty = extracted('<html><head><title>Empty</title><meta name="description" content=""></head><body><h1>Page</h1></body></html>', "https://example.com/empty")
    malformed = extracted('<html><head><title>Malformed</title><meta name="description"></head><body><h1>Page</h1></body></html>', "https://example.com/malformed")

    scanner_rules = {item["rule"] for item in build_findings([missing, empty, malformed])}
    review_fixes = [
        item for item in build_page_pattern_findings([missing, empty, malformed])
        if item.get("category") == "meta_description"
    ]

    assert DESCRIPTION_RULES <= scanner_rules
    assert len(review_fixes) == 1
    [review_fix] = review_fixes
    assert review_fix["rule"] == "meta_description_unusable"
    assert review_fix["combined_rules"] == [
        "missing_meta_description",
        "empty_meta_description",
        "malformed_meta_description",
    ]
    assert review_fix["metadata_state_counts"] == {"missing": 1, "empty": 1, "malformed": 1}


def test_description_state_split_keeps_existing_health_score_calibration():
    missing = {"rule": "missing_meta_description", "priority": "medium", "page_template_family": "activity_detail"}
    empty = {"rule": "empty_meta_description", "priority": "medium", "page_template_family": "activity_detail"}
    malformed = {"rule": "malformed_meta_description", "priority": "medium", "page_template_family": "activity_detail"}

    baseline = calculate_health_score([], [missing])
    assert calculate_health_score([], [missing, empty, malformed]) == baseline

    fingerprint = {"pages_crawled": 150, "pages_received": 150, "pages_found": 1200, "blocked_or_429_pages": 0}
    assert compute_health_score([missing, empty, malformed], fingerprint) == compute_health_score([missing], fingerprint)


def test_localized_duplicate_titles_are_verification_context_and_non_scoring():
    findings = duplicate_title_findings([
        page("https://stripe.example/fr/connect", "Stripe Connect | Stripe"),
        page("https://stripe.example/de/connect", "Stripe Connect | Stripe"),
        page("https://stripe.example/es/connect", "Stripe Connect | Stripe"),
    ])
    assert len(findings) == 1
    assert findings[0]["duplicate_title_context"] == "localized_pages"
    assert findings[0]["rule"] == "duplicate_title_localized"
    assert findings[0]["verification_state"] == "needs_verification"
    assert findings[0]["non_scoring"] is True
    assert findings[0]["score_impact"] == 0


def test_sephora_query_variants_are_consolidated_separately_and_non_scoring():
    findings = duplicate_title_findings([
        page("https://shop.example/shop/cheveux-c307/", "Hair products | Sephora"),
        page("https://shop.example/shop/cheveux-c307/?listview=true", "Hair products | Sephora"),
    ])
    assert len(findings) == 1
    assert findings[0]["duplicate_title_context"] == "query_parameter_variants"
    assert findings[0]["rule"] == "duplicate_title_query_variants"
    assert findings[0]["non_scoring"] is True
    assert set(findings[0]["duplicate_title_urls"]) == {
        "/shop/cheveux-c307/",
        "/shop/cheveux-c307/?listview=true",
    }


def test_true_template_duplicates_remain_distinct_and_non_scoring():
    findings = duplicate_title_findings([
        page("https://shop.example/shop/makeup", "Shop beauty | Sephora"),
        page("https://shop.example/shop/skincare", "Shop beauty | Sephora"),
    ])
    assert len(findings) == 1
    assert findings[0]["duplicate_title_context"] == "true_template_duplicates"
    assert findings[0]["rule"] == "duplicate_title_template"
    assert findings[0]["non_scoring"] is True


def test_all_contextual_duplicate_titles_preserve_score_parity():
    pages = [
        page("https://shop.example/shop/makeup", "Shop beauty | Sephora"),
        page("https://shop.example/shop/skincare", "Shop beauty | Sephora"),
        page("https://shop.example/shop/cheveux/", "Hair | Sephora"),
        page("https://shop.example/shop/cheveux/?listview=true", "Hair | Sephora"),
    ]
    findings = duplicate_title_findings(pages)
    assert {item["rule"] for item in findings} == {
        "duplicate_title_query_variants",
        "duplicate_title_template",
    }
    assert all(item["non_scoring"] is True and item["score_impact"] == 0 for item in findings)
    assert calculate_health_score([], findings) == calculate_health_score([], [])

    fingerprint = {"pages_crawled": 4, "pages_received": 4, "pages_found": 4, "blocked_or_429_pages": 0}
    assert compute_health_score(findings, fingerprint) == compute_health_score([], fingerprint)


def test_generic_fallback_title_has_one_page_level_owner():
    pages = [
        page("https://shop.example/accessibility", "Sites-Sephora_FR-Site"),
        page("https://shop.example/promotion", "Sites-Sephora_FR-Site"),
        page("https://shop.example/terms", "Sites-Sephora_FR-Site"),
    ]
    assert duplicate_title_findings(pages) == []

    grouped = group_findings(build_findings(pages) + duplicate_title_findings(pages))
    fallback = [item for item in grouped if item["rule"] == "generic_fallback_title"]
    affected = [url for item in fallback for url in item["affected_pages"]]
    assert sorted(affected) == ["/accessibility", "/promotion", "/terms"]
    assert len(affected) == len(set(affected))
    assert all(item["non_scoring"] is True for item in fallback)
    assert all(item["score_impact"] == 0 for item in fallback)


def test_normal_home_brand_title_is_not_a_generic_fallback():
    assert is_generic_fallback_title("Home | Dupont Plomberie Lyon") is False
    assert is_generic_fallback_title("Sites-Sephora_FR-Site") is True


def test_demandware_on_path_is_not_treated_as_a_locale():
    context = classify_duplicate_title_context(
        "Shared title",
        ["/on/demandware.store/page", "/fr/demandware.store/page"],
    )
    assert context == "true_template_duplicates"


def test_duplicate_title_output_is_shuffle_deterministic():
    pages = [
        page("https://stripe.example/fr/connect", "Stripe Connect | Stripe"),
        page("https://stripe.example/de/connect", "Stripe Connect | Stripe"),
        page("https://shop.example/a", "Repeated template title"),
        page("https://shop.example/b", "Repeated template title"),
    ]
    assert duplicate_title_findings(pages) == duplicate_title_findings(list(reversed(pages)))


def test_grouped_title_evidence_remains_non_scoring():
    long_titles = [
        "A very long commercial category title designed to exceed the estimated search result width for product family one",
        "A very long commercial category title designed to exceed the estimated search result width for product family two",
        "A very long commercial category title designed to exceed the estimated search result width for product family three",
    ]
    pages = [
        page(
            f"https://shop.example/category/{index}",
            title,
            title_width_state="over_pixel_limit",
            title_pixel_width_estimate=700,
        )
        for index, title in enumerate(long_titles)
    ]
    grouped = group_findings(build_findings(pages))
    width_groups = [item for item in grouped if item["rule"] == "title_over_pixel_limit"]
    assert len(width_groups) == 1
    assert width_groups[0]["non_scoring"] is True
    assert width_groups[0]["score_impact"] == 0
    assert calculate_health_score([], width_groups) == calculate_health_score([], [])
