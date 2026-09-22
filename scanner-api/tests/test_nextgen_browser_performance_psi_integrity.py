from copy import deepcopy

from app.nextgen_browser_performance_psi_integrity import (
    PSI_BOUND_INTEGRITY_VERSION,
    validate_bound_pagespeed_contract,
)


def bound_psi_evidence():
    return {
        "version": "nextgen_performance_evidence_v1",
        "provider": "PageSpeed Insights",
        "adapter_version": "nextgen_pagespeed_bound_provider_v1",
        "base_adapter_version": "nextgen_performance_provider_adapter_v1",
        "field": {
            "version": "nextgen_field_performance_v1",
            "evidence_kind": "field",
            "provider": "PageSpeed Insights / CrUX",
            "state": "connected",
            "reason": None,
            "scope": "url",
            "observed_at": "2026-09-22T01:23:45Z",
            "source_url": "https://example.com/final",
            "metrics": {
                "lcp": {"value": 2400.0, "unit": "ms", "rating": "good"},
            },
        },
        "lab": {
            "version": "nextgen_lighthouse_evidence_v1",
            "evidence_kind": "lab",
            "provider": "PageSpeed Insights / Lighthouse",
            "state": "connected",
            "reason": None,
            "observed_at": "2026-09-22T01:23:45Z",
            "source_url": "https://example.com/final",
            "performance_score": 92.0,
            "metrics": None,
            "opportunities": [],
        },
        "provenance": {
            "version": "nextgen_pagespeed_provenance_v1",
            "requested_url": "https://example.com/start",
            "response_final_url": "https://example.com/final",
            "field_source_url": "https://example.com/final",
            "field_initial_url": "https://example.com/start",
            "field_origin_fallback": False,
            "lighthouse_requested_url": "https://example.com/start",
            "lighthouse_final_url": "https://example.com/final",
            "analysis_timestamp": "2026-09-22T01:23:45Z",
            "lighthouse_fetch_time": "2026-09-22T01:23:44Z",
            "lighthouse_version": "13.0.0",
            "strategy": "mobile",
        },
    }


def test_bound_psi_integrity_accepts_consistent_field_and_lab_provenance():
    result = validate_bound_pagespeed_contract(bound_psi_evidence())
    assert result == {"version": PSI_BOUND_INTEGRITY_VERSION, "valid": True, "reasons": []}


def test_bound_psi_integrity_rechecks_base_component_contracts():
    evidence = bound_psi_evidence()
    evidence["field"]["metrics"]["lcp"]["unit"] = "bytes"
    result = validate_bound_pagespeed_contract(evidence)
    assert not result["valid"]
    assert "base:field:metric_unit_mismatch" in result["reasons"]


def test_bound_psi_integrity_rejects_adapter_version_tampering():
    evidence = bound_psi_evidence()
    evidence["adapter_version"] = "nextgen_pagespeed_bound_provider_v999"
    result = validate_bound_pagespeed_contract(evidence)
    assert "adapter_version_mismatch" in result["reasons"]


def test_bound_psi_integrity_rejects_provenance_version_tampering():
    evidence = bound_psi_evidence()
    evidence["provenance"]["version"] = "nextgen_pagespeed_provenance_v999"
    result = validate_bound_pagespeed_contract(evidence)
    assert "provenance_version_mismatch" in result["reasons"]


def test_bound_psi_integrity_rejects_foreign_field_source_transport():
    evidence = bound_psi_evidence()
    evidence["provenance"]["field_source_url"] = "https://foreign.example/final"
    result = validate_bound_pagespeed_contract(evidence)
    assert "connected_field_source_mismatch" in result["reasons"]


def test_bound_psi_integrity_rejects_foreign_lab_final_transport():
    evidence = bound_psi_evidence()
    evidence["provenance"]["lighthouse_final_url"] = "https://foreign.example/final"
    result = validate_bound_pagespeed_contract(evidence)
    assert "connected_lab_source_identity_mismatch" in result["reasons"]


def test_bound_psi_integrity_rejects_cross_component_requested_identity_disagreement():
    evidence = bound_psi_evidence()
    evidence["provenance"]["lighthouse_requested_url"] = "https://example.com/other"
    result = validate_bound_pagespeed_contract(evidence)
    assert "lighthouse_requested_identity_mismatch" in result["reasons"]
    assert "component_requested_identity_mismatch" in result["reasons"]


def test_bound_psi_integrity_rejects_credential_bearing_identity():
    evidence = bound_psi_evidence()
    evidence["provenance"]["requested_url"] = "https://user:secret@example.com/start"
    result = validate_bound_pagespeed_contract(evidence)
    assert "requested_url_invalid" in result["reasons"]


def test_bound_psi_integrity_rejects_page_shaped_origin_scope():
    evidence = bound_psi_evidence()
    evidence["field"]["scope"] = "origin"
    evidence["field"]["source_url"] = "https://example.com/location/paris"
    evidence["provenance"]["field_source_url"] = "https://example.com/location/paris"
    evidence["provenance"]["field_origin_fallback"] = True
    result = validate_bound_pagespeed_contract(evidence)
    assert "connected_field_origin_source_not_origin" in result["reasons"]
    assert "connected_field_origin_identity_mismatch" in result["reasons"]


def test_bound_psi_integrity_requires_provider_requested_identity_for_connected_lab():
    evidence = bound_psi_evidence()
    evidence["provenance"]["lighthouse_requested_url"] = None
    result = validate_bound_pagespeed_contract(evidence)
    assert "connected_lab_provider_requested_identity_missing" in result["reasons"]


def test_bound_psi_integrity_allows_truthful_unavailable_components():
    evidence = bound_psi_evidence()
    for component in (evidence["field"], evidence["lab"]):
        component["state"] = "unavailable"
        component["reason"] = "provider_unavailable"
        component["source_url"] = "https://example.com/start"
    evidence["field"]["metrics"] = None
    evidence["lab"]["performance_score"] = None
    evidence["lab"]["metrics"] = None
    evidence["lab"]["opportunities"] = []
    evidence["provenance"]["field_source_url"] = None
    evidence["provenance"]["field_initial_url"] = None
    evidence["provenance"]["lighthouse_requested_url"] = None
    evidence["provenance"]["lighthouse_final_url"] = None
    result = validate_bound_pagespeed_contract(evidence)
    assert result["valid"]


def test_bound_psi_integrity_does_not_mutate_evidence():
    evidence = bound_psi_evidence()
    original = deepcopy(evidence)
    validate_bound_pagespeed_contract(evidence)
    assert evidence == original
