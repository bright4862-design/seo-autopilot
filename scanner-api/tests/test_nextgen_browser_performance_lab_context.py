from copy import deepcopy

from app.nextgen_browser_performance_lab_context import (
    normalize_direct_lighthouse_lab_context,
    normalize_psi_lighthouse_lab_context,
    validate_lighthouse_lab_context_contract,
)


def raw_lighthouse():
    return {
        "requestedUrl": "https://example.com/page",
        "finalUrl": "https://example.com/page/",
        "fetchTime": "2026-09-22T18:00:00.000Z",
        "lighthouseVersion": "13.0.0",
        "configSettings": {
            "emulatedFormFactor": "mobile",
            "throttlingMethod": "simulate",
            "locale": "en-US",
        },
        "environment": {"benchmarkIndex": 1234.5},
    }


def bound_direct():
    return {
        "version": "nextgen_lighthouse_evidence_v1",
        "evidence_kind": "lab",
        "provider": "Lighthouse",
        "state": "connected",
        "source_url": "https://example.com/page/",
        "adapter_version": "nextgen_lighthouse_bound_provider_v1",
        "provenance": {
            "version": "nextgen_lighthouse_provenance_v1",
            "provider_requested_url": "https://example.com/page",
            "final_url": "https://example.com/page/",
            "fetch_time": "2026-09-22T18:00:00.000Z",
            "lighthouse_version": "13.0.0",
            "strategy": "mobile",
        },
    }


def bound_psi():
    return {
        "version": "nextgen_performance_evidence_v1",
        "provider": "PageSpeed Insights",
        "adapter_version": "nextgen_pagespeed_bound_provider_v1",
        "lab": {
            "version": "nextgen_lighthouse_evidence_v1",
            "evidence_kind": "lab",
            "provider": "PageSpeed Insights / Lighthouse",
            "state": "connected",
            "source_url": "https://example.com/page/",
        },
        "provenance": {
            "version": "nextgen_pagespeed_provenance_v1",
            "lighthouse_requested_url": "https://example.com/page",
            "lighthouse_final_url": "https://example.com/page/",
            "lighthouse_fetch_time": "2026-09-22T18:00:00.000Z",
            "lighthouse_version": "13.0.0",
            "strategy": "mobile",
        },
    }


def test_direct_context_normalizes_provider_neutral_fields():
    out = normalize_direct_lighthouse_lab_context(raw_lighthouse(), bound_direct())
    assert out["state"] == "normalized"
    assert out["context"] == {
        "device_class": "mobile",
        "throttling_mode": "simulated",
        "locale": "en-US",
        "observation_time": "2026-09-22T18:00:00.000Z",
        "engine_version": "13.0.0",
        "environment_benchmark_index": 1234.5,
    }
    assert out["missing_fields"] == []
    assert validate_lighthouse_lab_context_contract(out)["valid"] is True


def test_psi_context_uses_same_contract_and_not_field_component():
    raw = {
        "loadingExperience": {
            "metrics": {"LARGEST_CONTENTFUL_PAINT_MS": {"percentile": 1200}}
        },
        "lighthouseResult": raw_lighthouse(),
    }
    out = normalize_psi_lighthouse_lab_context(raw, bound_psi())
    assert out["state"] == "normalized"
    assert out["source_kind"] == "psi_lighthouse"
    assert out["context"]["device_class"] == "mobile"
    assert validate_lighthouse_lab_context_contract(out)["valid"] is True


def test_partial_context_is_truthful_not_guessed():
    raw = raw_lighthouse()
    raw["configSettings"].pop("throttlingMethod")
    raw["configSettings"].pop("locale")
    raw["environment"] = {}
    out = normalize_direct_lighthouse_lab_context(raw, bound_direct())
    assert out["state"] == "normalized"
    assert out["context"]["throttling_mode"] is None
    assert out["missing_fields"] == [
        "environment_benchmark_index",
        "locale",
        "throttling_mode",
    ]
    assert validate_lighthouse_lab_context_contract(out)["valid"] is True


def test_invalid_throttling_is_not_invented():
    raw = raw_lighthouse()
    raw["configSettings"]["throttlingMethod"] = "mystery"
    out = normalize_direct_lighthouse_lab_context(raw, bound_direct())
    assert out["context"]["throttling_mode"] is None
    assert "throttling_mode" in out["missing_fields"]


def test_requested_identity_mismatch_fails_closed():
    raw = raw_lighthouse()
    raw["requestedUrl"] = "https://foreign.example/page"
    out = normalize_direct_lighthouse_lab_context(raw, bound_direct())
    assert out["state"] == "not_verified"
    assert out["reason"] == "requested_identity_mismatch"
    assert out["context"] is None
    assert validate_lighthouse_lab_context_contract(out)["valid"] is True


def test_final_identity_mismatch_fails_closed():
    raw = raw_lighthouse()
    raw["finalUrl"] = "https://example.com/other"
    out = normalize_direct_lighthouse_lab_context(raw, bound_direct())
    assert out["reason"] == "final_identity_mismatch"


def test_fetch_time_mismatch_fails_closed():
    raw = raw_lighthouse()
    raw["fetchTime"] = "2026-09-22T18:05:00.000Z"
    out = normalize_direct_lighthouse_lab_context(raw, bound_direct())
    assert out["reason"] == "fetch_time_mismatch"


def test_engine_version_mismatch_fails_closed():
    raw = raw_lighthouse()
    raw["lighthouseVersion"] = "12.0.0"
    out = normalize_direct_lighthouse_lab_context(raw, bound_direct())
    assert out["reason"] == "engine_version_mismatch"


def test_device_class_mismatch_fails_closed():
    raw = raw_lighthouse()
    raw["configSettings"]["emulatedFormFactor"] = "desktop"
    out = normalize_direct_lighthouse_lab_context(raw, bound_direct())
    assert out["reason"] == "device_class_mismatch"


def test_credential_bearing_identity_fails_closed():
    raw = raw_lighthouse()
    raw["requestedUrl"] = "https://user:pass@example.com/page"
    out = normalize_direct_lighthouse_lab_context(raw, bound_direct())
    assert out["reason"] == "requested_identity_invalid"


def test_non_connected_lab_source_does_not_gain_context():
    bound = bound_direct()
    bound["state"] = "provider_error"
    out = normalize_direct_lighthouse_lab_context(raw_lighthouse(), bound)
    assert out["state"] == "not_verified"
    assert out["reason"] == "source_lab_provider_error"
    assert out["context"] is None


def test_field_evidence_cannot_be_laundered_into_lab_context():
    bound = bound_direct()
    bound["evidence_kind"] = "field"
    out = normalize_direct_lighthouse_lab_context(raw_lighthouse(), bound)
    assert out["reason"] == "source_not_lab_evidence"


def test_psi_requires_bound_lab_component():
    bound = bound_psi()
    bound["lab"] = {
        "version": "nextgen_field_performance_v1",
        "evidence_kind": "field",
        "state": "connected",
    }
    out = normalize_psi_lighthouse_lab_context(
        {"lighthouseResult": raw_lighthouse()}, bound
    )
    assert out["reason"] == "source_not_lab_evidence"


def test_integrity_rejects_tampered_missing_fields():
    out = normalize_direct_lighthouse_lab_context(raw_lighthouse(), bound_direct())
    out["missing_fields"] = ["locale"]
    check = validate_lighthouse_lab_context_contract(out)
    assert check["valid"] is False
    assert "missing_fields_mismatch" in check["reasons"]


def test_integrity_rejects_context_on_not_verified():
    out = normalize_direct_lighthouse_lab_context(raw_lighthouse(), bound_direct())
    out["state"] = "not_verified"
    out["reason"] = "forged"
    out["source_url"] = None
    check = validate_lighthouse_lab_context_contract(out)
    assert check["valid"] is False
    assert "not_verified_retained_context" in check["reasons"]


def test_inputs_are_not_mutated():
    raw = raw_lighthouse()
    bound = bound_direct()
    raw_before = deepcopy(raw)
    bound_before = deepcopy(bound)
    normalize_direct_lighthouse_lab_context(raw, bound)
    assert raw == raw_before
    assert bound == bound_before
