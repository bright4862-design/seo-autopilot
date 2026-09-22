from copy import deepcopy

from app.nextgen_browser_performance_lighthouse_opportunities import (
    LIGHTHOUSE_OPPORTUNITY_INTEGRITY_VERSION,
    LIGHTHOUSE_OPPORTUNITY_VERSION,
    normalize_lighthouse_opportunity_evidence,
    validate_lighthouse_opportunity_contract,
)


def _source(*, state="connected", source_url="https://example.com/final"):
    return {
        "version": "nextgen_lighthouse_evidence_v1",
        "evidence_kind": "lab",
        "provider": "Lighthouse",
        "state": state,
        "reason": None,
        "observed_at": "2026-09-22T14:00:00Z",
        "source_url": source_url,
        "performance_score": 91.0 if state == "connected" else None,
        "metrics": None,
        "opportunities": [],
        "adapter_version": "nextgen_lighthouse_bound_provider_v1",
        "provenance": {
            "version": "nextgen_lighthouse_provenance_v1",
            "requested_url": "https://example.com/start",
            "provider_requested_url": "https://example.com/start",
            "final_url": "https://example.com/final",
            "fetch_time": "2026-09-22T14:00:00Z",
            "lighthouse_version": "13.0.1",
            "strategy": "mobile",
            "runtime_error": None,
            "excluded_error_audits": [],
        },
    }


def _payload():
    return {
        "requestedUrl": "https://example.com/start",
        "finalUrl": "https://example.com/final",
        "audits": {},
    }


def test_explicit_typed_savings_are_normalized_without_guessing():
    payload = _payload()
    payload["audits"]["unused-javascript"] = {
        "score": 0.42,
        "numericValue": 999999,
        "numericUnit": "byte",
        "details": {"overallSavingsMs": 180, "overallSavingsBytes": 42000},
    }
    result = normalize_lighthouse_opportunity_evidence(payload, _source())
    assert result["version"] == LIGHTHOUSE_OPPORTUNITY_VERSION
    assert result["state"] == "normalized"
    assert result["opportunities"] == [{
        "audit_id": "unused-javascript",
        "score": 0.42,
        "estimated_savings_ms": 180.0,
        "estimated_savings_bytes": 42000.0,
    }]
    assert result["excluded_opportunities"] == []
    assert validate_lighthouse_opportunity_contract(payload, _source(), result)["valid"] is True


def test_numeric_millisecond_fallback_requires_explicit_time_unit():
    payload = _payload()
    payload["audits"]["render-blocking-resources"] = {
        "numericValue": 240,
        "numericUnit": "millisecond",
    }
    result = normalize_lighthouse_opportunity_evidence(payload, _source())
    assert result["opportunities"][0]["estimated_savings_ms"] == 240.0
    assert result["opportunities"][0]["estimated_savings_bytes"] is None


def test_numeric_byte_fallback_maps_to_bytes_not_milliseconds():
    payload = _payload()
    payload["audits"]["unused-css-rules"] = {
        "numericValue": 12000,
        "numericUnit": "bytes",
    }
    result = normalize_lighthouse_opportunity_evidence(payload, _source())
    row = result["opportunities"][0]
    assert row["estimated_savings_ms"] is None
    assert row["estimated_savings_bytes"] == 12000.0


def test_missing_numeric_unit_is_not_guessed_but_valid_score_is_preserved():
    payload = _payload()
    payload["audits"]["unused-javascript"] = {"numericValue": 300, "score": 0.5}
    result = normalize_lighthouse_opportunity_evidence(payload, _source())
    assert result["state"] == "normalized"
    assert result["opportunities"][0]["score"] == 0.5
    assert result["opportunities"][0]["estimated_savings_ms"] is None
    assert result["excluded_opportunities"] == [{
        "audit_id": "unused-javascript",
        "reason": "numeric_unit_unverified",
        "raw_unit": None,
    }]


def test_unsupported_numeric_unit_without_other_measurement_fails_closed():
    payload = _payload()
    payload["audits"]["unused-javascript"] = {
        "numericValue": 300,
        "numericUnit": "widgets",
    }
    result = normalize_lighthouse_opportunity_evidence(payload, _source())
    assert result["state"] == "not_verified"
    assert result["reason"] == "all_opportunity_measurements_unverified"
    assert result["opportunities"] == []
    assert result["excluded_opportunities"][0]["reason"] == "numeric_unit_unverified"


def test_error_audit_is_excluded_while_other_valid_opportunity_survives():
    payload = _payload()
    payload["audits"]["unused-javascript"] = {
        "scoreDisplayMode": "error",
        "errorMessage": "Audit failed",
        "numericValue": 999,
        "numericUnit": "millisecond",
    }
    payload["audits"]["unused-css-rules"] = {
        "details": {"overallSavingsBytes": 9000},
    }
    result = normalize_lighthouse_opportunity_evidence(payload, _source())
    assert [row["audit_id"] for row in result["opportunities"]] == ["unused-css-rules"]
    assert result["excluded_opportunities"] == [{"audit_id": "unused-javascript", "reason": "audit_error"}]


def test_no_allowlisted_audits_is_not_applicable_not_provider_failure():
    payload = _payload()
    payload["audits"]["largest-contentful-paint"] = {"numericValue": 2100, "numericUnit": "millisecond"}
    result = normalize_lighthouse_opportunity_evidence(payload, _source())
    assert result["state"] == "not_applicable"
    assert result["reason"] == "allowlisted_opportunities_absent"
    assert result["opportunities"] == []


def test_non_connected_source_cannot_emit_opportunity_measurements():
    payload = _payload()
    payload["audits"]["unused-javascript"] = {"numericValue": 200, "numericUnit": "millisecond"}
    result = normalize_lighthouse_opportunity_evidence(payload, _source(state="rate_limited"))
    assert result["state"] == "not_verified"
    assert result["reason"] == "source_rate_limited"
    assert result["opportunities"] == []


def test_field_evidence_cannot_be_laundered_into_lab_opportunities():
    source = _source()
    source["evidence_kind"] = "field"
    result = normalize_lighthouse_opportunity_evidence(_payload(), source)
    assert result["state"] == "not_verified"
    assert result["reason"] == "source_not_lab_evidence"


def test_credential_bearing_provider_identity_fails_closed():
    payload = _payload()
    payload["requestedUrl"] = "https://user:secret@example.com/start"
    result = normalize_lighthouse_opportunity_evidence(payload, _source())
    assert result["state"] == "not_verified"
    assert result["reason"] == "provider_requested_identity_invalid"
    assert result["opportunities"] == []


def test_raw_redirect_identity_must_match_bound_lighthouse_provenance():
    payload = _payload()
    payload["finalUrl"] = "https://example.com/other"
    result = normalize_lighthouse_opportunity_evidence(payload, _source())
    assert result["state"] == "not_verified"
    assert result["reason"] == "provider_final_identity_mismatch"


def test_integrity_recomputes_from_exact_raw_and_source_evidence():
    payload = _payload()
    payload["audits"]["unused-javascript"] = {"numericValue": 200, "numericUnit": "millisecond"}
    source = _source()
    result = normalize_lighthouse_opportunity_evidence(payload, source)
    forged = deepcopy(result)
    forged["opportunities"][0]["estimated_savings_ms"] = 20.0
    check = validate_lighthouse_opportunity_contract(payload, source, forged)
    assert check["version"] == LIGHTHOUSE_OPPORTUNITY_INTEGRITY_VERSION
    assert check["valid"] is False
    assert "evidence_source_mismatch" in check["reasons"]


def test_normalizer_does_not_mutate_raw_or_source_inputs():
    payload = _payload()
    payload["audits"]["unused-javascript"] = {"numericValue": 200, "numericUnit": "millisecond"}
    source = _source()
    before_payload = deepcopy(payload)
    before_source = deepcopy(source)
    normalize_lighthouse_opportunity_evidence(payload, source)
    assert payload == before_payload
    assert source == before_source
