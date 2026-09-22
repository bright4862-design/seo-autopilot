import copy
import json
from pathlib import Path

from app.nextgen_browser_performance import (
    compare_critical_content_parity,
    normalize_field_performance_evidence,
    normalize_lighthouse_evidence,
    normalize_pagespeed_insights_evidence,
    select_representative_performance_pages,
)
from app.nextgen_browser_performance_contract import (
    INTEGRITY_VERSION,
    validate_critical_parity_contract,
    validate_field_performance_contract,
    validate_lighthouse_contract,
    validate_pagespeed_contract,
    validate_representative_sample_contract,
)

FIXTURE = Path(__file__).parent / "fixtures" / "nextgen_psi_sample.json"


def test_field_integrity_accepts_normalized_connected_and_unavailable_evidence():
    connected = normalize_field_performance_evidence(
        provider="CrUX",
        state="connected",
        metrics={"lcp_ms": 2400, "cls": 0.1},
    )
    unavailable = normalize_field_performance_evidence(
        provider="CrUX",
        state="rate_limited",
        metrics={"lcp_ms": 2400},
    )

    assert validate_field_performance_contract(connected) == {
        "version": INTEGRITY_VERSION,
        "contract": "field_performance",
        "valid": True,
        "reasons": [],
    }
    assert validate_field_performance_contract(unavailable)["valid"] is True


def test_field_integrity_rejects_forged_metrics_in_non_connected_state():
    evidence = normalize_field_performance_evidence(provider="CrUX", state="rate_limited")
    evidence["metrics"] = {"lcp": {"value": 1200.0, "unit": "ms", "rating": "good"}}

    result = validate_field_performance_contract(evidence)
    assert result["valid"] is False
    assert result["reasons"] == ["unavailable_state_retained_metrics"]


def test_field_integrity_rejects_non_finite_and_unsupported_metric_data():
    evidence = normalize_field_performance_evidence(
        provider="CrUX",
        state="connected",
        metrics={"lcp_ms": 2400},
    )
    evidence["metrics"]["lcp"]["value"] = float("nan")
    evidence["metrics"]["invented"] = {"value": 1.0, "unit": "ms", "rating": "good"}

    result = validate_field_performance_contract(evidence)
    assert result["valid"] is False
    assert result["reasons"] == ["metric_key_unsupported", "metric_value_invalid"]


def test_lighthouse_integrity_accepts_allowlisted_normalized_fixture():
    payload = json.loads(FIXTURE.read_text())["lighthouseResult"]
    evidence = normalize_lighthouse_evidence(payload)

    result = validate_lighthouse_contract(evidence)
    assert result["valid"] is True
    assert result["reasons"] == []


def test_lighthouse_integrity_rejects_retained_measurements_when_provider_failed():
    evidence = normalize_lighthouse_evidence(None, state="provider_error")
    evidence["performance_score"] = 88.0
    evidence["opportunities"] = [{
        "audit_id": "unused-javascript",
        "score": 0.4,
        "estimated_savings_ms": 100.0,
        "estimated_savings_bytes": None,
    }]

    result = validate_lighthouse_contract(evidence)
    assert result["valid"] is False
    assert result["reasons"] == [
        "unavailable_state_retained_opportunities",
        "unavailable_state_retained_score",
    ]


def test_pagespeed_integrity_preserves_field_and_lab_as_independent_contracts():
    payload = json.loads(FIXTURE.read_text())
    evidence = normalize_pagespeed_insights_evidence(payload)

    assert evidence["field"]["evidence_kind"] == "field"
    assert evidence["lab"]["evidence_kind"] == "lab"
    assert validate_pagespeed_contract(evidence)["valid"] is True


def test_pagespeed_integrity_rejects_cross_kind_forgery():
    payload = json.loads(FIXTURE.read_text())
    evidence = normalize_pagespeed_insights_evidence(payload)
    evidence["field"]["evidence_kind"] = "lab"

    result = validate_pagespeed_contract(evidence)
    assert result["valid"] is False
    assert result["reasons"] == ["field:evidence_kind_mismatch"]


def _sample_pages():
    return [
        {
            "url": "https://e.test/",
            "page_template_family": "homepage",
            "is_high_value": True,
        },
        {
            "url": "https://e.test/product/a",
            "page_template_family": "product_page",
            "page_value": 0.9,
        },
        {
            "url": "https://e.test/product/b",
            "page_template_family": "product_page",
            "page_value": 0.7,
        },
        {
            "url": "https://e.test/blog/a",
            "page_template_family": "blog",
        },
    ]


def test_sample_integrity_accepts_deterministic_sampler_output():
    sample = select_representative_performance_pages(_sample_pages(), max_pages=3)
    result = validate_representative_sample_contract(sample)

    assert result["valid"] is True
    assert sample["template_coverage_complete"] is True
    assert sample["selected_pages"] == 3


def test_sample_integrity_rejects_forged_duplicate_and_population_counts():
    sample = select_representative_performance_pages(_sample_pages(), max_pages=3)
    forged = copy.deepcopy(sample)
    forged["duplicate_page_observations_dropped"] = 9
    forged["pages"][1]["url"] = forged["pages"][0]["url"]

    result = validate_representative_sample_contract(forged)
    assert result["valid"] is False
    assert result["reasons"] == ["duplicate_count_inconsistent", "duplicate_selected_url"]


def test_sample_integrity_rejects_claimed_complete_template_coverage_with_omissions():
    sample = select_representative_performance_pages(_sample_pages(), max_pages=2)
    assert sample["template_coverage_complete"] is False
    sample["template_coverage_complete"] = True

    result = validate_representative_sample_contract(sample)
    assert result["valid"] is False
    assert result["reasons"] == ["template_coverage_flag_inconsistent"]


def test_parity_integrity_accepts_real_matched_and_material_delta_outputs():
    matched = compare_critical_content_parity(
        {"url": "https://e.test/p", "title": "Product"},
        {"url": "https://e.test/p", "title": "Product"},
    )
    changed = compare_critical_content_parity(
        {"url": "https://e.test/p", "title": "Product", "h1": ""},
        {"url": "https://e.test/p", "title": "Product", "h1": "Rendered"},
    )

    assert validate_critical_parity_contract(matched)["valid"] is True
    assert validate_critical_parity_contract(changed)["valid"] is True


def test_parity_integrity_rejects_forged_matched_result_with_changed_scope():
    parity = compare_critical_content_parity(
        {"url": "https://e.test/p", "title": "Product", "h1": ""},
        {"url": "https://e.test/p", "title": "Product", "h1": "Rendered"},
    )
    parity["state"] = "matched"
    parity["material_delta"] = False

    result = validate_critical_parity_contract(parity)
    assert result["valid"] is False
    assert result["reasons"] == ["matched_with_changed_fields"]


def test_parity_integrity_rejects_material_delta_without_same_identity():
    parity = compare_critical_content_parity(
        {"url": "https://e.test/p", "title": "A", "h1": ""},
        {"url": "https://e.test/p", "title": "A", "h1": "B"},
    )
    parity["rendered_url"] = "https://e.test/other"

    result = validate_critical_parity_contract(parity)
    assert result["valid"] is False
    assert result["reasons"] == ["paired_identity_mismatch"]


def test_parity_integrity_rejects_bilateral_claim_when_scalar_was_not_observed():
    parity = compare_critical_content_parity(
        {"url": "https://e.test/p", "title": "A"},
        {"url": "https://e.test/p", "title": "A"},
    )
    parity["fields"]["title"]["raw_observed"] = False

    result = validate_critical_parity_contract(parity)
    assert result["valid"] is False
    assert result["reasons"] == ["scalar_state_without_bilateral_observation"]
