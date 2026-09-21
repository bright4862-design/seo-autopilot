import json
from pathlib import Path

from app.nextgen_browser_performance import (
    compare_critical_content_parity,
    normalize_crux_evidence,
    normalize_field_performance_evidence,
    normalize_lighthouse_evidence,
    normalize_pagespeed_insights_evidence,
    select_representative_performance_pages,
)

FIXTURE = Path(__file__).parent / "fixtures" / "nextgen_psi_sample.json"


def test_field_provider_states_fail_closed_without_metrics():
    evidence = normalize_field_performance_evidence(
        provider="CrUX",
        state="rate_limited",
        metrics={"lcp_ms": 1234},
        observed_at="2026-09-21",
    )
    assert evidence["state"] == "rate_limited"
    assert evidence["evidence_kind"] == "field"
    assert evidence["metrics"] is None

    invalid = normalize_field_performance_evidence(provider="CrUX", state="mystery", metrics={"lcp_ms": 1234})
    assert invalid["state"] == "unavailable"
    assert invalid["reason"] == "provider_state_invalid"
    assert invalid["metrics"] is None


def test_crux_wrapper_normalizes_percentile_shape_and_provider_categories():
    evidence = normalize_crux_evidence(
        {
            "metrics": {
                "largest_contentful_paint": {"percentiles": {"p75": 2450}, "category": "FAST"},
                "interaction_to_next_paint": {"percentiles": {"p75": 220}, "category": "AVERAGE"},
            }
        },
        scope="url",
        observed_at="2026-09-21",
    )
    assert evidence["state"] == "connected"
    assert evidence["evidence_kind"] == "field"
    assert evidence["metrics"]["lcp"] == {"value": 2450.0, "unit": "ms", "rating": "good"}
    assert evidence["metrics"]["inp"]["rating"] == "needs_improvement"


def test_missing_or_invalid_provider_payloads_fail_closed_with_truthful_reason():
    missing = normalize_crux_evidence(None, state="connected")
    assert missing["state"] == "unavailable"
    assert missing["reason"] == "provider_payload_missing"
    assert missing["metrics"] is None

    invalid = normalize_pagespeed_insights_evidence({}, state="mystery")
    assert invalid["field"]["state"] == "unavailable"
    assert invalid["field"]["reason"] == "provider_state_invalid"
    assert invalid["lab"]["state"] == "unavailable"
    assert invalid["lab"]["reason"] == "provider_state_invalid"

    absent = normalize_pagespeed_insights_evidence(None, state="connected")
    assert absent["field"]["reason"] == "provider_payload_missing"
    assert absent["lab"]["reason"] == "provider_payload_missing"


def test_pagespeed_keeps_field_and_lab_evidence_distinct():
    payload = json.loads(FIXTURE.read_text())
    evidence = normalize_pagespeed_insights_evidence(
        payload,
        observed_at="2026-09-21",
        source_url="https://example.com/",
    )
    assert evidence["field"]["evidence_kind"] == "field"
    assert evidence["lab"]["evidence_kind"] == "lab"
    assert evidence["field"]["metrics"]["lcp"]["value"] == 2400
    assert evidence["field"]["metrics"]["cls"]["value"] == 0.12
    assert evidence["lab"]["performance_score"] == 87.0
    assert evidence["lab"]["metrics"]["lcp"]["value"] == 2600
    assert "performance_score" not in evidence["field"]


def test_pagespeed_can_have_lab_without_field_data():
    payload = json.loads(FIXTURE.read_text())
    payload.pop("loadingExperience")
    evidence = normalize_pagespeed_insights_evidence(payload)
    assert evidence["field"]["state"] == "unavailable"
    assert evidence["field"]["reason"] == "crux_field_data_unavailable"
    assert evidence["lab"]["state"] == "connected"


def test_lighthouse_normalizer_is_bounded_and_deterministic():
    payload = json.loads(FIXTURE.read_text())["lighthouseResult"]
    payload["audits"]["totally-unrelated-audit"] = {"numericValue": 999999}
    normalized = normalize_lighthouse_evidence(payload)
    assert normalized["state"] == "connected"
    assert normalized["performance_score"] == 87.0
    assert "totally-unrelated-audit" not in normalized["metrics"]
    assert normalized["opportunities"] == [{
        "audit_id": "unused-javascript",
        "score": 0.45,
        "estimated_savings_ms": 220.0,
        "estimated_savings_bytes": 120000.0,
    }]


def test_lighthouse_normalizer_rejects_invalid_scores_and_prefers_explicit_savings():
    payload = json.loads(FIXTURE.read_text())["lighthouseResult"]
    payload["categories"]["performance"]["score"] = 7
    payload["audits"]["largest-contentful-paint"]["score"] = 2
    payload["audits"]["unused-javascript"]["details"]["overallSavingsMs"] = 175
    normalized = normalize_lighthouse_evidence(payload)
    assert normalized["performance_score"] is None
    assert normalized["metrics"]["lcp"]["score"] is None
    assert normalized["opportunities"][0]["estimated_savings_ms"] == 175.0


def test_representative_sampler_covers_templates_before_extra_pages():
    pages = [
        {"url": "https://e.test/", "status_code": 200, "page_evidence_class": "usable_html", "page_template_family": "homepage"},
        {"url": "https://e.test/product/a", "status_code": 200, "page_evidence_class": "usable_html", "page_template_family": "product_page", "page_value": 0.5},
        {"url": "https://e.test/product/b", "status_code": 200, "page_evidence_class": "usable_html", "page_template_family": "product_page", "page_value": 0.9},
        {"url": "https://e.test/blog/a", "status_code": 200, "page_evidence_class": "usable_html", "page_template_family": "blog"},
    ]
    sample = select_representative_performance_pages(pages, max_pages=3)
    assert sample["template_coverage_complete"] is True
    assert [row["template_family"] for row in sample["pages"]] == ["product_page", "homepage", "blog"]
    assert sample["pages"][0]["url"].endswith("/product/b")
    assert all(row["selection_reason"] == "template_representative" for row in sample["pages"])


def test_representative_sampler_hard_caps_large_requests():
    pages = [
        {"url": f"https://e.test/{i}", "page_template_family": f"family_{i}"}
        for i in range(30)
    ]
    sample = select_representative_performance_pages(pages, max_pages=500)
    assert sample["requested_max_pages"] == 500
    assert sample["hard_cap"] == 12
    assert sample["selected_pages"] == 12
    assert sample["template_coverage_complete"] is False


def test_representative_sampler_reports_omitted_templates_when_budget_is_too_small():
    pages = [
        {"url": "https://e.test/", "page_template_family": "homepage", "is_high_value": True},
        {"url": "https://e.test/p", "page_template_family": "product_page", "page_value": 0.8},
        {"url": "https://e.test/b", "page_template_family": "blog"},
    ]
    sample = select_representative_performance_pages(pages, max_pages=2)
    assert sample["selected_pages"] == 2
    assert sample["template_coverage_complete"] is False
    assert sample["omitted_template_families"] == ["blog"]


def test_representative_sampler_uses_high_value_fill_after_template_coverage():
    pages = [
        {"url": "https://e.test/", "page_template_family": "homepage"},
        {"url": "https://e.test/product/a", "page_template_family": "product_page", "page_value": 0.4},
        {"url": "https://e.test/product/b", "page_template_family": "product_page", "page_value": 0.95},
        {"url": "https://e.test/product/c", "page_template_family": "product_page", "page_value": 0.8},
    ]
    sample = select_representative_performance_pages(pages, max_pages=3)
    assert sample["template_families"] == 2
    assert sample["pages"][0]["url"].endswith("/product/b")
    assert sample["pages"][2]["url"].endswith("/product/c")
    assert sample["pages"][2]["selection_reason"] == "high_value_fill"


def test_representative_sampler_deduplicates_final_urls_deterministically():
    low = {
        "url": "https://e.test/go#tracking",
        "final_url": "https://E.TEST/product/a#hero",
        "page_template_family": "product_page",
        "page_value": 0.2,
    }
    high = {
        "url": "https://e.test/product/a",
        "final_url": "https://e.test/product/a",
        "page_template_family": "product_page",
        "page_value": 0.9,
    }
    first = select_representative_performance_pages([low, high], max_pages=1)
    second = select_representative_performance_pages([high, low], max_pages=1)
    assert first == second
    assert first["eligible_page_observations"] == 2
    assert first["duplicate_page_observations_dropped"] == 1
    assert first["eligible_pages"] == 1
    assert first["pages"][0]["url"] == "https://e.test/product/a"
    assert first["pages"][0]["high_value_weight"] == 0.9


def test_render_failure_is_not_verified_not_a_site_defect():
    raw = {"url": "https://e.test/p", "title": "Raw", "h1": "Raw H1"}
    parity = compare_critical_content_parity(raw, None, render_state="provider_error", render_reason="renderer_failed")
    assert parity["state"] == "not_verified"
    assert parity["material_delta"] is None
    assert parity["reason"] == "renderer_failed"
    assert parity["fields"] == {}


def test_render_identity_mismatch_is_not_treated_as_a_content_delta():
    raw = {"url": "https://e.test/a", "title": "A"}
    rendered = {"url": "https://e.test/b", "title": "B"}
    parity = compare_critical_content_parity(raw, rendered)
    assert parity["state"] == "not_verified"
    assert parity["reason"] == "render_identity_mismatch"
    assert parity["material_delta"] is None
    assert parity["fields"] == {}


def test_explicitly_unusable_render_is_not_verified_even_if_render_state_completed():
    raw = {"url": "https://e.test/a", "title": "A"}
    rendered = {"url": "https://e.test/a", "title": "A", "status_code": 503}
    parity = compare_critical_content_parity(raw, rendered)
    assert parity["state"] == "not_verified"
    assert parity["reason"] == "render_http_status_unusable"
    assert parity["material_delta"] is None


def test_parity_normalizes_relative_links_against_page_identity():
    raw = {
        "url": "https://e.test/p",
        "title": "Product",
        "important_links": ["/shipping#top"],
    }
    rendered = {
        "url": "https://e.test/p",
        "title": "Product",
        "important_links": ["https://E.TEST/shipping"],
    }
    parity = compare_critical_content_parity(raw, rendered)
    assert parity["state"] == "matched"
    assert parity["fields"]["important_links"]["state"] == "same"
    assert parity["changed_fields"] == []


def test_parity_reports_critical_render_deltas_as_evidence_only():
    raw = {
        "url": "https://e.test/p",
        "title": "Product",
        "h1": "",
        "canonical": "https://e.test/p#frag",
        "indexable": True,
        "word_count": 0,
        "important_links": ["/cart"],
        "schema_types": ["Organization"],
        "product_facts": {"price": "49"},
    }
    rendered = {
        "url": "https://e.test/p",
        "title": "Product",
        "h1": "Product A",
        "canonical": "https://e.test/p",
        "indexable": True,
        "word_count": 220,
        "important_links": ["/cart", "/shipping"],
        "schema_types": ["Organization", "Product"],
        "product_facts": {"price": "49", "availability": "InStock"},
    }
    parity = compare_critical_content_parity(raw, rendered)
    assert parity["state"] == "material_delta"
    assert parity["material_delta"] is True
    assert parity["fields"]["title"]["state"] == "same"
    assert parity["fields"]["h1"]["state"] == "raw_missing_rendered_present"
    assert parity["fields"]["canonical"]["state"] == "same"
    assert parity["fields"]["main_content_present"]["state"] == "changed"
    assert parity["fields"]["important_links"]["rendered_only"] == ["https://e.test/shipping"]
    assert parity["fields"]["structured_data"]["rendered_only"] == ["Product"]
    assert parity["fields"]["business_facts"]["state"] == "changed"
    assert parity["changed_fields"] == [
        "business_facts", "h1", "important_links", "main_content_present", "structured_data"
    ]
