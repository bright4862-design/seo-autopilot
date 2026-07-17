"""Metadata-state and contextual duplicate-title regressions."""

from app.extract import extract_page
from app.review import build_page_pattern_findings, compute_health_score
from app.scanner import build_findings, calculate_health_score, duplicate_title_findings


def extracted(html: str, url: str = "https://example.com/page"):
    return extract_page(
        html,
        url,
        url,
        200,
        "text/html; charset=utf-8",
        {"discovered_from": ["sitemap"], "source_pages": ["/sitemap.xml"], "link_text_samples": []},
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


def test_absent_empty_and_valid_descriptions_are_distinct():
    missing = extracted("<html><head><title>Missing</title></head><body><h1>Page</h1></body></html>")
    empty = extracted('<html><head><title>Empty</title><meta name="description" content=""></head><body><h1>Page</h1></body></html>')
    valid = extracted('<html><head><title>Valid</title><meta name="description" content="Useful summary"></head><body><h1>Page</h1></body></html>')

    assert missing["meta_description_state"] == "missing"
    assert empty["meta_description_state"] == "present_empty"
    assert valid["meta_description_state"] == "present_valid"
    assert empty["meta_description_element_count"] == 1
    assert valid["meta_description"] == "Useful summary"


def test_scanner_and_review_emit_separate_absent_and_empty_rules():
    missing = extracted("<html><head><title>Missing</title></head><body><h1>Page</h1></body></html>", "https://example.com/missing")
    empty = extracted('<html><head><title>Empty</title><meta name="description" content=""></head><body><h1>Page</h1></body></html>', "https://example.com/empty")

    scanner_rules = {item["rule"] for item in build_findings([missing, empty])}
    review_rules = {item["rule"] for item in build_page_pattern_findings([missing, empty])}

    assert "missing_meta_description" in scanner_rules
    assert "empty_meta_description" in scanner_rules
    assert "missing_meta_description" in review_rules
    assert "empty_meta_description" in review_rules


def test_empty_description_keeps_existing_health_score_calibration():
    missing = {
        "rule": "missing_meta_description",
        "priority": "medium",
        "page_template_family": "activity_detail",
    }
    empty = {
        "rule": "empty_meta_description",
        "priority": "medium",
        "page_template_family": "activity_detail",
    }
    baseline = calculate_health_score([], [missing])
    split = calculate_health_score([], [missing, empty])
    assert split == baseline

    fingerprint = {"pages_crawled": 150, "pages_received": 150, "pages_found": 1200, "blocked_or_429_pages": 0}
    assert compute_health_score([missing, empty], fingerprint) == compute_health_score([missing], fingerprint)


def test_localized_duplicate_titles_are_verification_context():
    findings = duplicate_title_findings([
        page("https://stripe.example/fr/connect", "Stripe Connect | Stripe"),
        page("https://stripe.example/de/connect", "Stripe Connect | Stripe"),
        page("https://stripe.example/es/connect", "Stripe Connect | Stripe"),
    ])
    assert len(findings) == 1
    assert findings[0]["duplicate_title_context"] == "localized_pages"
    assert findings[0]["rule"] == "duplicate_title_localized"
    assert findings[0]["non_scoring"] is True


def test_sephora_query_variants_are_consolidated_separately():
    findings = duplicate_title_findings([
        page("https://shop.example/shop/cheveux-c307/", "Hair products | Sephora"),
        page("https://shop.example/shop/cheveux-c307/?listview=true", "Hair products | Sephora"),
    ])
    assert len(findings) == 1
    assert findings[0]["duplicate_title_context"] == "query_parameter_variants"
    assert findings[0]["rule"] == "duplicate_title_query_variants"
    assert set(findings[0]["duplicate_title_urls"]) == {
        "/shop/cheveux-c307/",
        "/shop/cheveux-c307/?listview=true",
    }


def test_true_template_duplicates_remain_distinct_from_locale_and_query_groups():
    findings = duplicate_title_findings([
        page("https://shop.example/shop/makeup", "Shop beauty | Sephora"),
        page("https://shop.example/shop/skincare", "Shop beauty | Sephora"),
    ])
    assert len(findings) == 1
    assert findings[0]["duplicate_title_context"] == "true_template_duplicates"
    assert findings[0]["rule"] == "duplicate_title_template"


def test_generic_fallback_title_is_detected_and_non_scoring():
    fallback = extracted("<html><head><title>Sites-Sephora_FR-Site</title><meta name='description' content='Valid'></head><body><h1>Accessibility</h1></body></html>")
    rules = {item["rule"]: item for item in build_findings([fallback])}
    assert rules["generic_fallback_title"]["non_scoring"] is True


def test_overwide_title_is_evidence_only():
    long_title = "A very long commercial category title designed to exceed the estimated search result width by a substantial margin"
    wide = extracted(f"<html><head><title>{long_title}</title><meta name='description' content='Valid'></head><body><h1>Category</h1></body></html>")
    wide_rules = {item["rule"]: item for item in build_findings([wide])}
    assert wide["title_width_state"] == "over_pixel_limit"
    assert wide_rules["title_over_pixel_limit"]["score_impact"] == 0
    assert calculate_health_score([], [wide_rules["title_over_pixel_limit"]]) == 92
