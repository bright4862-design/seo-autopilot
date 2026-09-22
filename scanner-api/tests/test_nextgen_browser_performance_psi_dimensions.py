from copy import deepcopy

from app.nextgen_browser_performance_psi_dimensions import (
    PSI_FIELD_DIMENSION_INTEGRITY_VERSION,
    PSI_FIELD_DIMENSION_VERSION,
    normalize_psi_field_dimension_context,
    validate_psi_field_dimension_contract,
)


def _payload(form_factor="PHONE"):
    metric = lambda value: {"percentile": value, "category": "FAST", "formFactor": form_factor}
    return {
        "loadingExperience": {
            "id": "https://example.com/final",
            "initial_url": "https://example.com/start",
            "origin_fallback": False,
            "metrics": {
                "LARGEST_CONTENTFUL_PAINT_MS": metric(2100),
                "INTERACTION_TO_NEXT_PAINT": metric(180),
                "CUMULATIVE_LAYOUT_SHIFT_SCORE": metric(8),
            },
        },
        "originLoadingExperience": {
            "id": "https://example.com",
            "initial_url": "https://example.com/start",
            "metrics": {
                "LARGEST_CONTENTFUL_PAINT_MS": metric(1900),
                "INTERACTION_TO_NEXT_PAINT": metric(160),
                "CUMULATIVE_LAYOUT_SHIFT_SCORE": metric(6),
            },
        },
        "lighthouseResult": {
            "configSettings": {"formFactor": "mobile"},
        },
    }


def _bound(scope="url", state="connected", origin_fallback=False):
    source = "https://example.com/final" if scope == "url" else "https://example.com/"
    field = {
        "version": "nextgen_field_performance_v1",
        "evidence_kind": "field",
        "provider": "PageSpeed Insights / CrUX",
        "state": state,
        "reason": None if state == "connected" else state,
        "scope": scope if state == "connected" else None,
        "observed_at": "2026-09-22T12:00:00Z",
        "source_url": source if state == "connected" else None,
        "metrics": {
            "lcp": {"value": 2100.0, "unit": "ms", "rating": "good"},
            "inp": {"value": 180.0, "unit": "ms", "rating": "good"},
            "cls": {"value": 0.08, "unit": "score", "rating": "good"},
        } if state == "connected" else None,
    }
    return {
        "version": "nextgen_performance_evidence_v1",
        "provider": "PageSpeed Insights",
        "adapter_version": "nextgen_pagespeed_bound_provider_v1",
        "base_adapter_version": "nextgen_performance_provider_adapter_v1",
        "field": field,
        "lab": {
            "evidence_kind": "lab",
            "state": "connected",
        },
        "provenance": {
            "version": "nextgen_pagespeed_provenance_v1",
            "field_source_url": source if state == "connected" else None,
            "field_initial_url": "https://example.com/start" if state == "connected" else None,
            "field_origin_fallback": origin_fallback,
            "strategy": "mobile",
        },
    }


def test_psi_field_dimension_binds_phone_from_field_metric_metadata():
    evidence = normalize_psi_field_dimension_context(_payload("PHONE"), _bound())
    assert evidence["version"] == PSI_FIELD_DIMENSION_VERSION
    assert evidence["state"] == "connected"
    assert evidence["form_factor"] == "phone"
    assert evidence["aggregation"] == "single_form_factor"
    assert evidence["dimension_source"] == "field_metric_form_factor"
    assert evidence["metric_form_factors"] == {"cls": "phone", "inp": "phone", "lcp": "phone"}
    assert validate_psi_field_dimension_contract(_payload("PHONE"), _bound(), evidence)["valid"] is True


def test_psi_field_dimension_normalizes_desktop_case_insensitively():
    payload = _payload("desktop")
    evidence = normalize_psi_field_dimension_context(payload, _bound())
    assert evidence["state"] == "connected"
    assert evidence["form_factor"] == "desktop"


def test_psi_field_dimension_supports_tablet_when_provider_reports_it():
    evidence = normalize_psi_field_dimension_context(_payload("TABLET"), _bound())
    assert evidence["state"] == "connected"
    assert evidence["form_factor"] == "tablet"


def test_psi_field_dimension_does_not_borrow_mobile_lighthouse_strategy_when_field_metadata_missing():
    payload = _payload("PHONE")
    for metric in payload["loadingExperience"]["metrics"].values():
        metric.pop("formFactor")
    evidence = normalize_psi_field_dimension_context(payload, _bound())
    assert evidence["state"] == "unavailable"
    assert evidence["reason"] == "psi_metric_form_factor_unavailable"
    assert evidence["form_factor"] is None
    assert evidence["metric_form_factors"] is None


def test_psi_field_dimension_rejects_incomplete_metric_form_factor_coverage():
    payload = _payload("PHONE")
    payload["loadingExperience"]["metrics"]["INTERACTION_TO_NEXT_PAINT"].pop("formFactor")
    evidence = normalize_psi_field_dimension_context(payload, _bound())
    assert evidence["state"] == "unavailable"
    assert evidence["reason"] == "psi_metric_form_factor_incomplete"
    assert evidence["form_factor"] is None


def test_psi_field_dimension_rejects_mixed_metric_form_factors():
    payload = _payload("PHONE")
    payload["loadingExperience"]["metrics"]["INTERACTION_TO_NEXT_PAINT"]["formFactor"] = "DESKTOP"
    evidence = normalize_psi_field_dimension_context(payload, _bound())
    assert evidence["state"] == "unavailable"
    assert evidence["reason"] == "psi_metric_form_factor_mixed"


def test_psi_field_dimension_rejects_unknown_metric_form_factor():
    payload = _payload("PHONE")
    payload["loadingExperience"]["metrics"]["LARGEST_CONTENTFUL_PAINT_MS"]["formFactor"] = "WATCH"
    evidence = normalize_psi_field_dimension_context(payload, _bound())
    assert evidence["state"] == "unavailable"
    assert evidence["reason"] == "psi_metric_form_factor_invalid"


def test_psi_field_dimension_preserves_non_connected_provider_state_without_device_claim():
    bound = _bound(state="rate_limited")
    evidence = normalize_psi_field_dimension_context(_payload("PHONE"), bound)
    assert evidence["state"] == "rate_limited"
    assert evidence["reason"] == "rate_limited"
    assert evidence["form_factor"] is None
    assert evidence["metric_form_factors"] is None


def test_psi_field_dimension_rejects_untrusted_bound_adapter():
    bound = _bound()
    bound["adapter_version"] = "forged"
    evidence = normalize_psi_field_dimension_context(_payload("PHONE"), bound)
    assert evidence["state"] == "unavailable"
    assert evidence["reason"] == "bound_psi_adapter_version_invalid"


def test_psi_field_dimension_handles_origin_fallback_from_loading_experience():
    payload = _payload("PHONE")
    payload["loadingExperience"]["origin_fallback"] = True
    payload["loadingExperience"]["id"] = "https://example.com"
    bound = _bound(scope="origin", origin_fallback=True)
    evidence = normalize_psi_field_dimension_context(payload, bound)
    assert evidence["state"] == "connected"
    assert evidence["scope"] == "origin"
    assert evidence["source_url"] == "https://example.com/"
    assert evidence["form_factor"] == "phone"


def test_psi_field_dimension_rejects_raw_field_identity_mismatch():
    payload = _payload("PHONE")
    payload["loadingExperience"]["id"] = "https://foreign.example/final"
    evidence = normalize_psi_field_dimension_context(payload, _bound())
    assert evidence["state"] == "unavailable"
    assert evidence["reason"] == "psi_field_experience_identity_mismatch"


def test_psi_field_dimension_integrity_rejects_forged_form_factor():
    payload = _payload("PHONE")
    bound = _bound()
    evidence = normalize_psi_field_dimension_context(payload, bound)
    evidence["form_factor"] = "desktop"
    check = validate_psi_field_dimension_contract(payload, bound, evidence)
    assert check["version"] == PSI_FIELD_DIMENSION_INTEGRITY_VERSION
    assert check["valid"] is False
    assert "form_factor_mismatch" in check["reasons"]


def test_psi_field_dimension_does_not_mutate_payload_or_bound_evidence():
    payload = _payload("PHONE")
    bound = _bound()
    before_payload = deepcopy(payload)
    before_bound = deepcopy(bound)
    normalize_psi_field_dimension_context(payload, bound)
    assert payload == before_payload
    assert bound == before_bound
