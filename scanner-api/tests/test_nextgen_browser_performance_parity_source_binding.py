from copy import deepcopy

from app.nextgen_browser_performance_parity_hardening import (
    compare_critical_content_parity_resolved,
)
from app.nextgen_browser_performance_parity_source_binding import (
    PARITY_SOURCE_BINDING_VERSION,
    validate_resolved_critical_parity_source_binding,
)


def _pair(url="https://e.test/p", raw_title="Same", rendered_title="Same"):
    return (
        {"url": url, "title": raw_title, "canonical": "/p"},
        {"url": url, "title": rendered_title, "canonical": "https://e.test/p"},
    )


def _evidence(raw, rendered, **kwargs):
    return compare_critical_content_parity_resolved(raw, rendered, **kwargs)


def test_exact_matched_sources_bind():
    raw, rendered = _pair()
    result = validate_resolved_critical_parity_source_binding(
        raw, rendered, _evidence(raw, rendered)
    )
    assert result == {
        "version": PARITY_SOURCE_BINDING_VERSION,
        "contract": "nextgen_critical_content_parity_v2_resolved",
        "valid": True,
        "reasons": [],
        "expected_url": "https://e.test/p",
        "expected_state": "matched",
    }


def test_material_delta_sources_bind():
    raw, rendered = _pair(rendered_title="Changed")
    result = validate_resolved_critical_parity_source_binding(
        raw, rendered, _evidence(raw, rendered)
    )
    assert result["valid"] is True
    assert result["expected_state"] == "material_delta"


def test_relative_canonical_resolution_is_source_bound():
    raw = {"url": "https://e.test/catalog/p", "canonical": "../p"}
    rendered = {"url": "https://e.test/catalog/p", "canonical": "https://e.test/p"}
    evidence = _evidence(raw, rendered)
    result = validate_resolved_critical_parity_source_binding(raw, rendered, evidence)
    assert result["valid"] is True


def test_structurally_valid_field_value_forgery_is_rejected():
    raw, rendered = _pair()
    evidence = _evidence(raw, rendered)
    evidence["fields"]["title"]["raw"] = "Forged but structurally plausible"
    result = validate_resolved_critical_parity_source_binding(raw, rendered, evidence)
    assert result["valid"] is False
    assert "fields_mismatch" in result["reasons"]


def test_wrong_source_raw_identity_is_rejected():
    raw, rendered = _pair()
    evidence = _evidence(raw, rendered)
    other_raw = {**raw, "url": "https://e.test/other"}
    result = validate_resolved_critical_parity_source_binding(
        other_raw, rendered, evidence
    )
    assert result["valid"] is False
    assert "url_mismatch" in result["reasons"]
    assert result["expected_state"] == "not_verified"


def test_wrong_source_rendered_identity_cannot_rebind_a_match():
    raw, rendered = _pair()
    evidence = _evidence(raw, rendered)
    other_rendered = {**rendered, "url": "https://e.test/other"}
    result = validate_resolved_critical_parity_source_binding(
        raw, other_rendered, evidence
    )
    assert result["valid"] is False
    assert "state_mismatch" in result["reasons"]
    assert result["expected_state"] == "not_verified"


def test_failed_render_binds_only_to_not_verified_evidence():
    raw, _ = _pair()
    evidence = _evidence(
        raw, None, render_state="provider_error", render_reason="renderer_failed"
    )
    result = validate_resolved_critical_parity_source_binding(
        raw,
        None,
        evidence,
        render_state="provider_error",
        render_reason="renderer_failed",
    )
    assert result["valid"] is True
    assert result["expected_state"] == "not_verified"


def test_matched_evidence_cannot_be_used_for_failed_render_source():
    raw, rendered = _pair()
    matched = _evidence(raw, rendered)
    result = validate_resolved_critical_parity_source_binding(
        raw,
        None,
        matched,
        render_state="provider_error",
        render_reason="renderer_failed",
    )
    assert result["valid"] is False
    assert "state_mismatch" in result["reasons"]
    assert "fields_mismatch" in result["reasons"]


def test_render_reason_is_bound_for_not_verified_evidence():
    raw, _ = _pair()
    evidence = _evidence(
        raw, None, render_state="provider_error", render_reason="renderer_failed"
    )
    result = validate_resolved_critical_parity_source_binding(
        raw,
        None,
        evidence,
        render_state="provider_error",
        render_reason="different_failure",
    )
    assert result["valid"] is False
    assert result["reasons"] == ["reason_mismatch"]


def test_invalid_transport_contract_fails_before_source_binding():
    raw, rendered = _pair()
    evidence = _evidence(raw, rendered)
    evidence["canonical_resolution_version"] = "forged"
    result = validate_resolved_critical_parity_source_binding(raw, rendered, evidence)
    assert result["valid"] is False
    assert "evidence:canonical_resolution_version_mismatch" in result["reasons"]
    assert result["expected_state"] is None


def test_extra_transport_metadata_does_not_change_binding():
    raw, rendered = _pair()
    evidence = _evidence(raw, rendered)
    evidence["transport_trace_id"] = "non-authoritative-context"
    result = validate_resolved_critical_parity_source_binding(raw, rendered, evidence)
    assert result["valid"] is True


def test_non_object_evidence_fails_closed():
    raw, rendered = _pair()
    result = validate_resolved_critical_parity_source_binding(raw, rendered, None)
    assert result["valid"] is False
    assert result["reasons"] == ["evidence_not_object"]


def test_source_change_after_evidence_creation_is_detected():
    raw, rendered = _pair()
    evidence = _evidence(raw, rendered)
    changed_raw = deepcopy(raw)
    changed_raw["title"] = "Changed after evidence creation"
    result = validate_resolved_critical_parity_source_binding(
        changed_raw, rendered, evidence
    )
    assert result["valid"] is False
    assert "fields_mismatch" in result["reasons"]
    assert result["expected_state"] == "material_delta"


def test_binding_does_not_mutate_inputs():
    raw, rendered = _pair()
    evidence = _evidence(raw, rendered)
    before_raw = deepcopy(raw)
    before_rendered = deepcopy(rendered)
    before_evidence = deepcopy(evidence)
    validate_resolved_critical_parity_source_binding(raw, rendered, evidence)
    assert raw == before_raw
    assert rendered == before_rendered
    assert evidence == before_evidence
