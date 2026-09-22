from __future__ import annotations

from copy import deepcopy

from app.nextgen_browser_performance_parity_hardening import (
    RESOLVED_CRITICAL_PARITY_VERSION,
    compare_critical_content_parity_resolved,
)
from app.nextgen_browser_performance_parity_sufficiency import (
    BASELINE_REQUIRED_FIELDS,
    PARITY_SUFFICIENCY_INTEGRITY_VERSION,
    PARITY_SUFFICIENCY_VERSION,
    assess_critical_parity_sufficiency,
    validate_critical_parity_sufficiency,
)


def _page(**overrides):
    page = {
        "url": "https://example.com/products/a",
        "status_code": 200,
        "page_evidence_class": "usable_html",
        "title": "Product A",
        "h1": "Product A",
        "canonical": "/products/a",
        "indexable": True,
        "main_text": "Product A is available.",
        "important_links": ["/cart", "/products/b"],
    }
    page.update(overrides)
    return page


def _full_match():
    return compare_critical_content_parity_resolved(_page(), _page())


def test_full_baseline_match_is_verified():
    parity = _full_match()

    result = assess_critical_parity_sufficiency(parity)

    assert parity["version"] == RESOLVED_CRITICAL_PARITY_VERSION
    assert result["version"] == PARITY_SUFFICIENCY_VERSION
    assert result["state"] == "verified_match"
    assert result["reason"] == "matched_required_fields_complete"
    assert result["missing_required_fields"] == []
    assert result["material_delta"] is False
    assert set(BASELINE_REQUIRED_FIELDS).issubset(result["verified_fields"])


def test_partial_match_is_not_enough_to_claim_critical_content_match():
    raw = _page()
    rendered = _page()
    for key in (
        "h1",
        "canonical",
        "indexable",
        "main_text",
        "important_links",
    ):
        raw.pop(key)
        rendered.pop(key)

    parity = compare_critical_content_parity_resolved(raw, rendered)
    result = assess_critical_parity_sufficiency(parity)

    assert parity["state"] == "matched"
    assert parity["verified_fields"] == ["title"]
    assert result["state"] == "not_verified"
    assert result["reason"] == "matched_required_fields_incomplete"
    assert result["material_delta"] is None
    assert result["missing_required_fields"] == [
        "h1",
        "canonical",
        "indexability",
        "main_content_present",
        "important_links",
    ]


def test_partial_material_delta_remains_positive_evidence():
    raw = _page()
    rendered = _page(title="Rendered Product A")
    for key in (
        "h1",
        "canonical",
        "indexable",
        "main_text",
        "important_links",
    ):
        raw.pop(key)
        rendered.pop(key)

    parity = compare_critical_content_parity_resolved(raw, rendered)
    result = assess_critical_parity_sufficiency(parity)

    assert parity["state"] == "material_delta"
    assert result["state"] == "verified_delta"
    assert result["reason"] == "material_delta_observed"
    assert result["material_delta"] is True
    assert result["changed_fields"] == ["title"]
    assert "h1" in result["missing_required_fields"]


def test_render_failure_stays_not_verified():
    parity = compare_critical_content_parity_resolved(
        _page(),
        None,
        render_state="failed",
        render_reason="browser_timeout",
    )

    result = assess_critical_parity_sufficiency(parity)

    assert parity["state"] == "not_verified"
    assert result["state"] == "not_verified"
    assert result["reason"] == "source_not_verified"
    assert result["material_delta"] is None


def test_invalid_source_contract_fails_closed():
    parity = _full_match()
    parity["verified_fields"] = ["title"]

    result = assess_critical_parity_sufficiency(parity)

    assert result["state"] == "not_verified"
    assert result["reason"] == "source_contract_invalid"
    assert result["verified_fields"] == []
    assert result["changed_fields"] == []
    assert result["source_contract_reasons"]


def test_integrity_accepts_truthful_fail_closed_invalid_source():
    parity = _full_match()
    parity["version"] = "forged_parity_v0"
    result = assess_critical_parity_sufficiency(parity)

    integrity = validate_critical_parity_sufficiency(parity, result)

    assert result["reason"] == "source_contract_invalid"
    assert integrity == {
        "version": PARITY_SUFFICIENCY_INTEGRITY_VERSION,
        "valid": True,
        "reasons": [],
    }


def test_relative_canonical_match_counts_as_required_field_coverage():
    raw = _page(canonical="/products/a")
    rendered = _page(canonical="https://example.com/products/a")

    parity = compare_critical_content_parity_resolved(raw, rendered)
    result = assess_critical_parity_sufficiency(parity)

    assert parity["fields"]["canonical"]["state"] == "same"
    assert result["state"] == "verified_match"
    assert "canonical" in result["verified_fields"]


def test_integrity_accepts_exact_bound_assessment():
    parity = _full_match()
    result = assess_critical_parity_sufficiency(parity)

    integrity = validate_critical_parity_sufficiency(parity, result)

    assert integrity == {
        "version": PARITY_SUFFICIENCY_INTEGRITY_VERSION,
        "valid": True,
        "reasons": [],
    }


def test_integrity_rejects_missing_field_tampering():
    parity = _full_match()
    result = assess_critical_parity_sufficiency(parity)
    result["missing_required_fields"] = ["title"]

    integrity = validate_critical_parity_sufficiency(parity, result)

    assert integrity["valid"] is False
    assert "assessment_source_mismatch" in integrity["reasons"]


def test_integrity_rejects_delta_laundered_into_match():
    parity = compare_critical_content_parity_resolved(
        _page(),
        _page(title="Rendered Product A"),
    )
    result = assess_critical_parity_sufficiency(parity)
    result["state"] = "verified_match"
    result["material_delta"] = False

    integrity = validate_critical_parity_sufficiency(parity, result)

    assert integrity["valid"] is False
    assert "assessment_source_mismatch" in integrity["reasons"]


def test_assessment_and_validation_do_not_mutate_source():
    parity = _full_match()
    before = deepcopy(parity)

    result = assess_critical_parity_sufficiency(parity)
    validate_critical_parity_sufficiency(parity, result)

    assert parity == before
