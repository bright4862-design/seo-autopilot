from copy import deepcopy

from app.nextgen_browser_performance_provider import (
    normalize_crux_query_record_evidence,
    normalize_pagespeed_insights_evidence_strict,
)


def crux_url_payload():
    return {
        "record": {
            "key": {"url": "https://Example.COM/page#frag"},
            "metrics": {
                "largest_contentful_paint": {"percentiles": {"p75": 2450}, "category": "FAST"},
                "interaction_to_next_paint": {"percentiles": {"p75": 225}, "category": "AVERAGE"},
                "cumulative_layout_shift": {"percentiles": {"p75": 0.12}, "category": "AVERAGE"},
            },
            "collectionPeriod": {
                "firstDate": {"year": 2026, "month": 8, "day": 20},
                "lastDate": {"year": 2026, "month": 9, "day": 16},
            },
        }
    }


def test_crux_query_record_normalizes_real_record_shape_and_provenance():
    evidence = normalize_crux_query_record_evidence(crux_url_payload(), observed_at="2026-09-21")
    assert evidence["state"] == "connected"
    assert evidence["scope"] == "url"
    assert evidence["source_url"] == "https://example.com/page"
    assert evidence["metrics"]["lcp"]["value"] == 2450.0
    assert evidence["metrics"]["inp"]["rating"] == "needs_improvement"
    assert evidence["coverage_period"] == {"first_date": "2026-08-20", "last_date": "2026-09-16"}


def test_crux_query_record_supports_origin_scope():
    payload = crux_url_payload()
    payload["record"]["key"] = {"origin": "https://Example.COM"}
    evidence = normalize_crux_query_record_evidence(payload, scope="origin", source_url="https://example.com/")
    assert evidence["state"] == "connected"
    assert evidence["scope"] == "origin"
    assert evidence["source_url"] == "https://example.com/"


def test_crux_query_record_rejects_ambiguous_or_missing_record_identity():
    payload = crux_url_payload()
    payload["record"]["key"] = {"url": "https://e.test/a", "origin": "https://e.test"}
    ambiguous = normalize_crux_query_record_evidence(payload)
    assert ambiguous["state"] == "unavailable"
    assert ambiguous["reason"] == "crux_record_key_invalid"
    assert ambiguous["metrics"] is None


def test_crux_query_record_rejects_scope_and_identity_contradictions():
    scope_mismatch = normalize_crux_query_record_evidence(crux_url_payload(), scope="origin")
    assert scope_mismatch["state"] == "unavailable"
    assert scope_mismatch["reason"] == "crux_scope_mismatch"

    identity_mismatch = normalize_crux_query_record_evidence(
        crux_url_payload(), source_url="https://example.com/other"
    )
    assert identity_mismatch["state"] == "unavailable"
    assert identity_mismatch["reason"] == "crux_record_identity_mismatch"


def test_crux_query_record_non_connected_state_never_retains_metrics():
    evidence = normalize_crux_query_record_evidence(crux_url_payload(), state="rate_limited")
    assert evidence["state"] == "rate_limited"
    assert evidence["metrics"] is None
    assert evidence["coverage_period"] is None


def test_crux_query_record_does_not_mutate_input():
    payload = crux_url_payload()
    original = deepcopy(payload)
    normalize_crux_query_record_evidence(payload)
    assert payload == original


def test_psi_strict_falls_back_to_origin_when_url_experience_has_no_supported_metrics():
    payload = {
        "loadingExperience": {"metrics": {"UNKNOWN_METRIC": {"percentile": 1}}},
        "originLoadingExperience": {
            "metrics": {
                "LARGEST_CONTENTFUL_PAINT_MS": {"percentile": 2100, "category": "FAST"},
                "CUMULATIVE_LAYOUT_SHIFT_SCORE": {"percentile": 9, "category": "FAST"},
            }
        },
        "lighthouseResult": {"categories": {"performance": {"score": 0.91}}, "audits": {}},
    }
    evidence = normalize_pagespeed_insights_evidence_strict(payload)
    assert evidence["field"]["state"] == "connected"
    assert evidence["field"]["scope"] == "origin"
    assert evidence["field"]["metrics"]["lcp"]["value"] == 2100.0
    assert evidence["field"]["metrics"]["cls"]["value"] == 0.09
    assert evidence["lab"]["state"] == "connected"
    assert evidence["lab"]["performance_score"] == 91.0


def test_psi_strict_prefers_valid_url_field_data_over_origin_fallback():
    payload = {
        "loadingExperience": {
            "metrics": {"LARGEST_CONTENTFUL_PAINT_MS": {"percentile": 2500, "category": "AVERAGE"}}
        },
        "originLoadingExperience": {
            "metrics": {"LARGEST_CONTENTFUL_PAINT_MS": {"percentile": 1800, "category": "FAST"}}
        },
    }
    evidence = normalize_pagespeed_insights_evidence_strict(payload)
    assert evidence["field"]["scope"] == "url"
    assert evidence["field"]["metrics"]["lcp"]["value"] == 2500.0
    assert evidence["lab"]["state"] == "unavailable"
    assert evidence["lab"]["reason"] == "lighthouse_lab_data_unavailable"
