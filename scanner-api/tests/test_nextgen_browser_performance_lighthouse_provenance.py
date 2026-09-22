from copy import deepcopy

from app.nextgen_browser_performance_lighthouse_provenance import (
    LIGHTHOUSE_BOUND_ADAPTER_VERSION,
    LIGHTHOUSE_BOUND_INTEGRITY_VERSION,
    LIGHTHOUSE_PROVENANCE_VERSION,
    normalize_lighthouse_evidence_bound,
    validate_bound_lighthouse_contract,
)


def _payload():
    return {
        "requestedUrl": "https://example.com/start",
        "finalUrl": "https://example.com/final",
        "fetchTime": "2026-09-22T08:00:00.000Z",
        "lighthouseVersion": "13.0.1",
        "configSettings": {"emulatedFormFactor": "mobile"},
        "categories": {"performance": {"score": 0.91}},
        "audits": {
            "largest-contentful-paint": {
                "numericValue": 2100,
                "numericUnit": "millisecond",
                "score": 0.88,
            },
            "unused-javascript": {
                "numericValue": 200,
                "score": 0.4,
                "details": {
                    "overallSavingsMs": 180,
                    "overallSavingsBytes": 42000,
                },
            },
        },
    }


def test_bound_lighthouse_accepts_explicit_redirect_and_preserves_provenance():
    evidence = normalize_lighthouse_evidence_bound(
        _payload(),
        source_url="https://EXAMPLE.com/start#fragment",
    )
    assert evidence["state"] == "connected"
    assert evidence["source_url"] == "https://example.com/final"
    assert evidence["observed_at"] == "2026-09-22T08:00:00.000Z"
    assert evidence["adapter_version"] == LIGHTHOUSE_BOUND_ADAPTER_VERSION
    assert evidence["provenance"] == {
        "version": LIGHTHOUSE_PROVENANCE_VERSION,
        "requested_url": "https://example.com/start",
        "provider_requested_url": "https://example.com/start",
        "final_url": "https://example.com/final",
        "fetch_time": "2026-09-22T08:00:00.000Z",
        "lighthouse_version": "13.0.1",
        "strategy": "mobile",
        "runtime_error": None,
        "excluded_error_audits": [],
    }
    assert validate_bound_lighthouse_contract(evidence)["valid"] is True


def test_bound_lighthouse_runtime_error_is_provider_error_not_measurement():
    payload = _payload()
    payload["runtimeError"] = {"code": "ERRORED_DOCUMENT_REQUEST", "message": "Navigation failed"}
    evidence = normalize_lighthouse_evidence_bound(
        payload,
        source_url="https://example.com/start",
    )
    assert evidence["state"] == "provider_error"
    assert evidence["reason"] == "lighthouse_runtime_error"
    assert evidence["performance_score"] is None
    assert evidence["metrics"] is None
    assert evidence["opportunities"] == []
    assert evidence["provenance"]["runtime_error"]["code"] == "ERRORED_DOCUMENT_REQUEST"
    assert validate_bound_lighthouse_contract(evidence)["valid"] is True


def test_bound_lighthouse_requires_provider_requested_identity():
    payload = _payload()
    payload.pop("requestedUrl")
    evidence = normalize_lighthouse_evidence_bound(
        payload,
        source_url="https://example.com/start",
    )
    assert evidence["state"] == "unavailable"
    assert evidence["reason"] == "lighthouse_requested_identity_missing"
    assert evidence["metrics"] is None


def test_bound_lighthouse_rejects_requested_identity_mismatch():
    payload = _payload()
    payload["requestedUrl"] = "https://other.example/path"
    evidence = normalize_lighthouse_evidence_bound(
        payload,
        source_url="https://example.com/start",
    )
    assert evidence["state"] == "unavailable"
    assert evidence["reason"] == "lighthouse_requested_identity_mismatch"


def test_bound_lighthouse_rejects_invalid_final_identity():
    payload = _payload()
    payload["finalUrl"] = "javascript:alert(1)"
    evidence = normalize_lighthouse_evidence_bound(
        payload,
        source_url="https://example.com/start",
    )
    assert evidence["state"] == "unavailable"
    assert evidence["reason"] == "lighthouse_final_identity_invalid"


def test_bound_lighthouse_rejects_invalid_caller_source_identity():
    evidence = normalize_lighthouse_evidence_bound(
        _payload(),
        source_url="/relative",
    )
    assert evidence["state"] == "unavailable"
    assert evidence["reason"] == "lighthouse_source_identity_invalid"
    assert evidence["provenance"]["requested_url"] is None


def test_bound_lighthouse_excludes_error_audits_without_dropping_valid_lab_evidence():
    payload = _payload()
    payload["audits"]["unused-javascript"]["scoreDisplayMode"] = "error"
    payload["audits"]["unused-javascript"]["errorMessage"] = "Audit failed"
    evidence = normalize_lighthouse_evidence_bound(
        payload,
        source_url="https://example.com/start",
    )
    assert evidence["state"] == "connected"
    assert evidence["metrics"]["lcp"]["value"] == 2100.0
    assert evidence["opportunities"] == []
    assert evidence["provenance"]["excluded_error_audits"] == ["unused-javascript"]
    assert validate_bound_lighthouse_contract(evidence)["valid"] is True


def test_bound_lighthouse_non_connected_state_never_retains_measurements():
    evidence = normalize_lighthouse_evidence_bound(
        _payload(),
        state="rate_limited",
        source_url="https://example.com/start",
    )
    assert evidence["state"] == "rate_limited"
    assert evidence["performance_score"] is None
    assert evidence["metrics"] is None
    assert evidence["opportunities"] == []


def test_bound_lighthouse_does_not_mutate_provider_payload():
    payload = _payload()
    payload["audits"]["unused-javascript"]["errorMessage"] = "Audit failed"
    before = deepcopy(payload)
    normalize_lighthouse_evidence_bound(
        payload,
        source_url="https://example.com/start",
    )
    assert payload == before


def test_bound_lighthouse_integrity_fails_closed_on_forged_source_or_provenance():
    evidence = normalize_lighthouse_evidence_bound(
        _payload(),
        source_url="https://example.com/start",
    )
    forged_source = deepcopy(evidence)
    forged_source["source_url"] = "https://evil.example/"
    check = validate_bound_lighthouse_contract(forged_source)
    assert check["version"] == LIGHTHOUSE_BOUND_INTEGRITY_VERSION
    assert check["valid"] is False
    assert "connected_source_identity_mismatch" in check["reasons"]

    forged_version = deepcopy(evidence)
    forged_version["provenance"]["version"] = "forged"
    check = validate_bound_lighthouse_contract(forged_version)
    assert check["valid"] is False
    assert "provenance_version_mismatch" in check["reasons"]
