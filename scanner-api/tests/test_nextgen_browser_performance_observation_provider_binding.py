from copy import deepcopy

from app.nextgen_browser_performance_observation_provider_binding import (
    OBSERVATION_PROVIDER_BINDING_VERSION,
    validate_performance_observation_provider_binding,
)


def sample(url="https://example.com/start"):
    return {
        "version": "nextgen_performance_sample_v1",
        "requested_max_pages": 1,
        "max_pages": 1,
        "hard_cap": 12,
        "eligible_page_observations": 1,
        "duplicate_page_observations_dropped": 0,
        "eligible_pages": 1,
        "template_families": 1,
        "selected_pages": 1,
        "template_coverage_complete": True,
        "omitted_template_families": [],
        "pages": [{
            "url": url,
            "template_family": "product_page",
            "high_value_weight": 1.0,
            "selection_reason": "template_representative",
        }],
    }


def crux(url="https://example.com/start", *, origin=False, state="connected"):
    source = "https://example.com/" if origin else url
    scope = "origin" if origin else "url"
    coverage = {"first_date": "2026-08-20", "last_date": "2026-09-16"}
    evidence = {
        "version": "nextgen_field_performance_v1",
        "evidence_kind": "field",
        "provider": "CrUX",
        "state": state,
        "reason": None if state == "connected" else state,
        "scope": scope,
        "observed_at": "2026-09-22T01:23:45Z",
        "source_url": source,
        "metrics": {
            "lcp": {"value": 2400.0, "unit": "ms", "rating": "good"}
        } if state == "connected" else None,
        "adapter_version": "nextgen_crux_bound_provider_v1",
        "base_adapter_version": "nextgen_performance_provider_adapter_v1",
        "coverage_period": coverage if state == "connected" else None,
        "provenance": {
            "version": "nextgen_crux_provenance_v1",
            "record_scope": scope if state == "connected" else None,
            "record_source_url": source if state == "connected" else None,
            "requested_scope": scope,
            "requested_source_url": source,
            "coverage_period": coverage if state == "connected" else None,
            "observed_at": "2026-09-22T01:23:45Z",
        },
    }
    return evidence


def lighthouse(requested="https://example.com/start", final="https://example.com/final", *, state="connected"):
    return {
        "version": "nextgen_lighthouse_evidence_v1",
        "evidence_kind": "lab",
        "provider": "Lighthouse",
        "state": state,
        "reason": None if state == "connected" else state,
        "observed_at": "2026-09-22T01:23:45Z",
        "source_url": final if state == "connected" else requested,
        "performance_score": 92.0 if state == "connected" else None,
        "metrics": None,
        "opportunities": [],
        "adapter_version": "nextgen_lighthouse_bound_provider_v1",
        "provenance": {
            "version": "nextgen_lighthouse_provenance_v1",
            "requested_url": requested,
            "provider_requested_url": requested,
            "final_url": final if state == "connected" else None,
            "fetch_time": "2026-09-22T01:23:44Z",
            "lighthouse_version": "13.0.0",
            "strategy": "mobile",
            "runtime_error": None,
            "excluded_error_audits": [],
        },
    }


def psi(requested="https://example.com/start", final="https://example.com/final", *, state="connected"):
    field = {
        "version": "nextgen_field_performance_v1",
        "evidence_kind": "field",
        "provider": "PageSpeed Insights / CrUX",
        "state": state,
        "reason": None if state == "connected" else state,
        "scope": "url" if state == "connected" else None,
        "observed_at": "2026-09-22T01:23:45Z",
        "source_url": final if state == "connected" else requested,
        "metrics": {
            "lcp": {"value": 2400.0, "unit": "ms", "rating": "good"}
        } if state == "connected" else None,
    }
    lab = {
        "version": "nextgen_lighthouse_evidence_v1",
        "evidence_kind": "lab",
        "provider": "PageSpeed Insights / Lighthouse",
        "state": state,
        "reason": None if state == "connected" else state,
        "observed_at": "2026-09-22T01:23:45Z",
        "source_url": final if state == "connected" else requested,
        "performance_score": 92.0 if state == "connected" else None,
        "metrics": None,
        "opportunities": [],
    }
    return {
        "version": "nextgen_performance_evidence_v1",
        "provider": "PageSpeed Insights",
        "adapter_version": "nextgen_pagespeed_bound_provider_v1",
        "base_adapter_version": "nextgen_performance_provider_adapter_v1",
        "field": field,
        "lab": lab,
        "provenance": {
            "version": "nextgen_pagespeed_provenance_v1",
            "requested_url": requested,
            "response_final_url": final if state == "connected" else None,
            "field_source_url": final if state == "connected" else None,
            "field_initial_url": requested if state == "connected" else None,
            "field_origin_fallback": False if state == "connected" else None,
            "lighthouse_requested_url": requested if state == "connected" else None,
            "lighthouse_final_url": final if state == "connected" else None,
            "analysis_timestamp": "2026-09-22T01:23:45Z",
            "lighthouse_fetch_time": "2026-09-22T01:23:44Z",
            "lighthouse_version": "13.0.0",
            "strategy": "mobile",
        },
    }


def test_accepts_direct_crux_field_and_direct_lighthouse_lab():
    field = crux()
    lab = lighthouse()
    result = validate_performance_observation_provider_binding(sample(), [{
        "requested_url": "https://example.com/start",
        "field": field,
        "lab": lab,
        "provider_bindings": [
            {"kind": "crux", "evidence": field},
            {"kind": "lighthouse", "evidence": lab},
        ],
    }])
    assert result == {
        "version": OBSERVATION_PROVIDER_BINDING_VERSION,
        "valid": True,
        "selected_pages": 1,
        "checked_observations": 1,
        "bound_observations": 1,
        "bound_field_components": 1,
        "bound_lab_components": 1,
        "reasons": [],
        "observation_errors": [],
    }


def test_accepts_one_bound_psi_envelope_for_both_components():
    bound = psi()
    result = validate_performance_observation_provider_binding(sample(), [{
        "requested_url": "https://example.com/start",
        "field": bound["field"],
        "lab": bound["lab"],
        "provider_bindings": [{"kind": "psi", "evidence": bound}],
    }])
    assert result["valid"] is True
    assert result["bound_field_components"] == 1
    assert result["bound_lab_components"] == 1


def test_accepts_origin_scoped_direct_crux_for_same_site_page():
    field = crux(origin=True)
    result = validate_performance_observation_provider_binding(sample(), [{
        "requested_url": "https://example.com/start",
        "field": field,
        "provider_bindings": [{"kind": "crux", "evidence": field}],
    }])
    assert result["valid"] is True


def test_empty_observation_set_is_valid_and_does_not_claim_coverage():
    result = validate_performance_observation_provider_binding(sample(), [])
    assert result["valid"] is True
    assert result["checked_observations"] == 0
    assert result["bound_observations"] == 0


def test_rejects_credential_bearing_selected_identity_even_if_sample_shape_is_valid():
    result = validate_performance_observation_provider_binding(
        sample("https://user:secret@example.com/start"), []
    )
    assert result["valid"] is False
    assert result["reasons"] == ["sample_page_identity_invalid"]


def test_rejects_unknown_provider_kind():
    field = crux()
    result = validate_performance_observation_provider_binding(sample(), [{
        "requested_url": "https://example.com/start",
        "field": field,
        "provider_bindings": [{"kind": "unknown", "evidence": field}],
    }])
    reasons = result["observation_errors"][0]["reasons"]
    assert "provider_binding_0:kind_unsupported" in reasons
    assert "field_provider_binding_missing" in reasons


def test_rejects_duplicate_provider_kind_to_avoid_ambiguous_transport():
    field = crux()
    result = validate_performance_observation_provider_binding(sample(), [{
        "requested_url": "https://example.com/start",
        "field": field,
        "provider_bindings": [
            {"kind": "crux", "evidence": field},
            {"kind": "crux", "evidence": deepcopy(field)},
        ],
    }])
    assert "provider_binding_1:kind_duplicate" in result["observation_errors"][0]["reasons"]


def test_rejects_invalid_bound_provider_contract():
    field = crux()
    forged = deepcopy(field)
    forged["adapter_version"] = "forged"
    result = validate_performance_observation_provider_binding(sample(), [{
        "requested_url": "https://example.com/start",
        "field": field,
        "provider_bindings": [{"kind": "crux", "evidence": forged}],
    }])
    reasons = result["observation_errors"][0]["reasons"]
    assert any("adapter_version_mismatch" in reason for reason in reasons)


def test_rejects_bound_lighthouse_requested_identity_mismatch():
    lab = lighthouse(requested="https://example.com/other")
    result = validate_performance_observation_provider_binding(sample(), [{
        "requested_url": "https://example.com/start",
        "lab": lab,
        "provider_bindings": [{"kind": "lighthouse", "evidence": lab}],
    }])
    assert any(
        reason.endswith("requested_identity_mismatch")
        for reason in result["observation_errors"][0]["reasons"]
    )


def test_rejects_bound_psi_requested_identity_mismatch():
    bound = psi(requested="https://example.com/other")
    result = validate_performance_observation_provider_binding(sample(), [{
        "requested_url": "https://example.com/start",
        "field": bound["field"],
        "provider_bindings": [{"kind": "psi", "evidence": bound}],
    }])
    assert any(
        reason.endswith("requested_identity_mismatch")
        for reason in result["observation_errors"][0]["reasons"]
    )


def test_rejects_direct_crux_from_foreign_source():
    field = crux(url="https://other.example/start")
    result = validate_performance_observation_provider_binding(sample(), [{
        "requested_url": "https://example.com/start",
        "field": field,
        "provider_bindings": [{"kind": "crux", "evidence": field}],
    }])
    assert any(
        reason.endswith("requested_identity_mismatch")
        for reason in result["observation_errors"][0]["reasons"]
    )


def test_rejects_base_valid_field_component_tampering():
    bound = psi()
    transported = deepcopy(bound["field"])
    transported["metrics"]["lcp"]["value"] = 2450.0
    result = validate_performance_observation_provider_binding(sample(), [{
        "requested_url": "https://example.com/start",
        "field": transported,
        "provider_bindings": [{"kind": "psi", "evidence": bound}],
    }])
    assert "field_component_provider_mismatch" in result["observation_errors"][0]["reasons"]


def test_rejects_base_valid_lab_component_tampering():
    bound = psi()
    transported = deepcopy(bound["lab"])
    transported["performance_score"] = 91.0
    result = validate_performance_observation_provider_binding(sample(), [{
        "requested_url": "https://example.com/start",
        "lab": transported,
        "provider_bindings": [{"kind": "psi", "evidence": bound}],
    }])
    assert "lab_component_provider_mismatch" in result["observation_errors"][0]["reasons"]


def test_lighthouse_binding_cannot_satisfy_field_component():
    lab = lighthouse()
    field = crux()
    result = validate_performance_observation_provider_binding(sample(), [{
        "requested_url": "https://example.com/start",
        "field": field,
        "provider_bindings": [{"kind": "lighthouse", "evidence": lab}],
    }])
    reasons = result["observation_errors"][0]["reasons"]
    assert "field_provider_binding_missing" in reasons
    assert "provider_binding_0:unused" in reasons


def test_crux_binding_cannot_satisfy_lab_component():
    field = crux()
    lab = lighthouse()
    result = validate_performance_observation_provider_binding(sample(), [{
        "requested_url": "https://example.com/start",
        "lab": lab,
        "provider_bindings": [{"kind": "crux", "evidence": field}],
    }])
    reasons = result["observation_errors"][0]["reasons"]
    assert "lab_provider_binding_missing" in reasons
    assert "provider_binding_0:unused" in reasons


def test_rejects_unused_extra_provider_binding():
    field = crux()
    lab = lighthouse()
    result = validate_performance_observation_provider_binding(sample(), [{
        "requested_url": "https://example.com/start",
        "field": field,
        "provider_bindings": [
            {"kind": "crux", "evidence": field},
            {"kind": "lighthouse", "evidence": lab},
        ],
    }])
    assert "provider_binding_1:unused" in result["observation_errors"][0]["reasons"]


def test_rejects_duplicate_observations_for_same_sampled_request():
    field = crux()
    observation = {
        "requested_url": "https://example.com/start",
        "field": field,
        "provider_bindings": [{"kind": "crux", "evidence": field}],
    }
    result = validate_performance_observation_provider_binding(
        sample(), [observation, deepcopy(observation)]
    )
    assert "requested_identity_duplicate" in result["observation_errors"][0]["reasons"]


def test_accepts_truthful_non_connected_psi_components_when_still_bound_to_request():
    bound = psi(state="rate_limited")
    result = validate_performance_observation_provider_binding(sample(), [{
        "requested_url": "https://example.com/start",
        "field": bound["field"],
        "lab": bound["lab"],
        "provider_bindings": [{"kind": "psi", "evidence": bound}],
    }])
    assert result["valid"] is True
    assert result["bound_field_components"] == 1
    assert result["bound_lab_components"] == 1


def test_validation_does_not_mutate_inputs():
    s = sample()
    bound = psi()
    observations = [{
        "requested_url": "https://example.com/start",
        "field": bound["field"],
        "lab": bound["lab"],
        "provider_bindings": [{"kind": "psi", "evidence": bound}],
    }]
    before_sample = deepcopy(s)
    before_observations = deepcopy(observations)
    validate_performance_observation_provider_binding(s, observations)
    assert s == before_sample
    assert observations == before_observations
