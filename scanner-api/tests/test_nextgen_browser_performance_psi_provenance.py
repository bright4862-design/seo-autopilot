from copy import deepcopy

from app.nextgen_browser_performance_psi_provenance import (
    PSI_BOUND_ADAPTER_VERSION,
    PSI_PROVENANCE_VERSION,
    normalize_pagespeed_insights_evidence_bound,
)


def psi_payload():
    return {
        "id": "https://example.com/final",
        "analysisUTCTimestamp": "2026-09-22T01:23:45Z",
        "loadingExperience": {
            "id": "https://example.com/final",
            "initial_url": "https://example.com/start",
            "origin_fallback": False,
            "metrics": {
                "LARGEST_CONTENTFUL_PAINT_MS": {"percentile": 2400, "category": "FAST"},
            },
        },
        "originLoadingExperience": {
            "id": "https://example.com",
            "initial_url": "https://example.com/start",
            "metrics": {
                "LARGEST_CONTENTFUL_PAINT_MS": {"percentile": 1900, "category": "FAST"},
            },
        },
        "lighthouseResult": {
            "requestedUrl": "https://example.com/start",
            "finalUrl": "https://example.com/final",
            "fetchTime": "2026-09-22T01:23:44Z",
            "lighthouseVersion": "13.0.0",
            "configSettings": {"emulatedFormFactor": "mobile"},
            "categories": {"performance": {"score": 0.92}},
            "audits": {},
        },
    }


def test_bound_psi_preserves_redirected_requested_and_final_identities():
    evidence = normalize_pagespeed_insights_evidence_bound(
        psi_payload(), source_url="https://EXAMPLE.com/start#frag"
    )
    assert evidence["adapter_version"] == PSI_BOUND_ADAPTER_VERSION
    assert evidence["provenance"]["version"] == PSI_PROVENANCE_VERSION
    assert evidence["provenance"]["requested_url"] == "https://example.com/start"
    assert evidence["provenance"]["response_final_url"] == "https://example.com/final"
    assert evidence["provenance"]["lighthouse_requested_url"] == "https://example.com/start"
    assert evidence["provenance"]["lighthouse_final_url"] == "https://example.com/final"
    assert evidence["lab"]["state"] == "connected"
    assert evidence["lab"]["source_url"] == "https://example.com/final"
    assert evidence["field"]["source_url"] == "https://example.com/final"


def test_bound_psi_rejects_foreign_lighthouse_requested_identity_without_poisoning_field():
    payload = psi_payload()
    payload["lighthouseResult"]["requestedUrl"] = "https://foreign.example/start"
    evidence = normalize_pagespeed_insights_evidence_bound(
        payload, source_url="https://example.com/start"
    )
    assert evidence["field"]["state"] == "connected"
    assert evidence["lab"]["state"] == "unavailable"
    assert evidence["lab"]["reason"] == "lighthouse_requested_identity_mismatch"
    assert evidence["lab"]["metrics"] is None


def test_bound_psi_runtime_error_fails_lab_closed_but_keeps_valid_field_evidence():
    payload = psi_payload()
    payload["lighthouseResult"]["runtimeError"] = {
        "code": "ERRORED_DOCUMENT_REQUEST",
        "message": "The page could not be loaded reliably.",
    }
    evidence = normalize_pagespeed_insights_evidence_bound(
        payload, source_url="https://example.com/start"
    )
    assert evidence["field"]["state"] == "connected"
    assert evidence["lab"]["state"] == "provider_error"
    assert evidence["lab"]["reason"] == "lighthouse_runtime_error"
    assert evidence["lab"]["performance_score"] is None
    assert evidence["lab"]["metrics"] is None
    assert evidence["lab"]["opportunities"] == []


def test_bound_psi_preserves_origin_fallback_truth_in_field_scope():
    payload = psi_payload()
    payload["loadingExperience"]["origin_fallback"] = True
    payload["loadingExperience"]["id"] = "https://example.com"
    evidence = normalize_pagespeed_insights_evidence_bound(
        payload, source_url="https://example.com/start"
    )
    assert evidence["field"]["state"] == "connected"
    assert evidence["field"]["scope"] == "origin"
    assert evidence["field"]["source_url"] == "https://example.com/"
    assert evidence["provenance"]["field_origin_fallback"] is True


def test_bound_psi_rejects_foreign_field_initial_identity_without_poisoning_lab():
    payload = psi_payload()
    payload["loadingExperience"]["initial_url"] = "https://foreign.example/start"
    evidence = normalize_pagespeed_insights_evidence_bound(
        payload, source_url="https://example.com/start"
    )
    assert evidence["field"]["state"] == "unavailable"
    assert evidence["field"]["reason"] == "psi_field_initial_identity_mismatch"
    assert evidence["field"]["metrics"] is None
    assert evidence["lab"]["state"] == "connected"


def test_bound_psi_invalid_caller_identity_fails_both_components_closed():
    evidence = normalize_pagespeed_insights_evidence_bound(
        psi_payload(), source_url="javascript:alert(1)"
    )
    assert evidence["field"]["state"] == "unavailable"
    assert evidence["field"]["reason"] == "psi_source_identity_invalid"
    assert evidence["lab"]["state"] == "unavailable"
    assert evidence["lab"]["reason"] == "psi_source_identity_invalid"
    assert evidence["provenance"]["requested_url"] is None


def test_bound_psi_uses_provider_analysis_timestamp_when_observed_at_is_absent():
    evidence = normalize_pagespeed_insights_evidence_bound(psi_payload())
    assert evidence["field"]["observed_at"] == "2026-09-22T01:23:45Z"
    assert evidence["lab"]["observed_at"] == "2026-09-22T01:23:45Z"
    assert evidence["provenance"]["analysis_timestamp"] == "2026-09-22T01:23:45Z"
    assert evidence["provenance"]["lighthouse_fetch_time"] == "2026-09-22T01:23:44Z"
    assert evidence["provenance"]["lighthouse_version"] == "13.0.0"
    assert evidence["provenance"]["strategy"] == "mobile"


def test_bound_psi_does_not_mutate_provider_payload():
    payload = psi_payload()
    original = deepcopy(payload)
    normalize_pagespeed_insights_evidence_bound(
        payload, source_url="https://example.com/start"
    )
    assert payload == original
