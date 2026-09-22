from copy import deepcopy

from app.nextgen_browser_performance_crux_provenance import (
    normalize_crux_query_record_evidence_bound,
)
from app.nextgen_browser_performance_field_distributions import (
    FIELD_DISTRIBUTION_INTEGRITY_VERSION,
    normalize_crux_field_distribution_evidence,
    normalize_psi_field_distribution_evidence,
    validate_field_distribution_contract,
)
from app.nextgen_browser_performance_psi_provenance import (
    normalize_pagespeed_insights_evidence_bound,
)


def crux_payload():
    return {
        "record": {
            "key": {"url": "https://example.com/page"},
            "metrics": {
                "largest_contentful_paint": {
                    "percentiles": {"p75": 2400},
                    "category": "FAST",
                    "histogram": [
                        {"start": 0, "end": 2500, "density": 0.8},
                        {"start": 2500, "end": 4000, "density": 0.15},
                        {"start": 4000, "density": 0.05},
                    ],
                },
                "cumulative_layout_shift": {
                    "percentiles": {"p75": 0.12},
                    "category": "AVERAGE",
                    "histogram": [
                        {"start": 0, "end": 0.1, "density": 0.7},
                        {"start": 0.1, "end": 0.25, "density": 0.2},
                        {"start": 0.25, "density": 0.1},
                    ],
                },
            },
            "collectionPeriod": {
                "firstDate": {"year": 2026, "month": 8, "day": 20},
                "lastDate": {"year": 2026, "month": 9, "day": 16},
            },
        }
    }


def bound_crux(payload=None, *, state="connected"):
    return normalize_crux_query_record_evidence_bound(
        payload or crux_payload(),
        state=state,
        observed_at="2026-09-22T18:20:00Z",
        scope="url",
        source_url="https://example.com/page",
    )


def psi_payload():
    return {
        "id": "https://example.com/final",
        "analysisUTCTimestamp": "2026-09-22T18:20:00Z",
        "loadingExperience": {
            "id": "https://example.com/final",
            "initial_url": "https://example.com/start",
            "origin_fallback": False,
            "metrics": {
                "LARGEST_CONTENTFUL_PAINT_MS": {
                    "percentile": 2400,
                    "category": "FAST",
                    "distributions": [
                        {"min": 0, "max": 2500, "proportion": 0.8},
                        {"min": 2500, "max": 4000, "proportion": 0.15},
                        {"min": 4000, "proportion": 0.05},
                    ],
                },
                "CUMULATIVE_LAYOUT_SHIFT_SCORE": {
                    "percentile": 12,
                    "category": "AVERAGE",
                    "distributions": [
                        {"min": 0, "max": 10, "proportion": 0.7},
                        {"min": 10, "max": 25, "proportion": 0.2},
                        {"min": 25, "proportion": 0.1},
                    ],
                },
            },
        },
        "lighthouseResult": {
            "requestedUrl": "https://example.com/start",
            "finalUrl": "https://example.com/final",
            "fetchTime": "2026-09-22T18:19:58Z",
            "lighthouseVersion": "13.0.0",
            "configSettings": {"emulatedFormFactor": "mobile"},
            "audits": {
                "largest-contentful-paint": {
                    "numericValue": 9999,
                    "numericUnit": "millisecond",
                    "score": 0.2,
                }
            },
        },
    }


def bound_psi(payload=None, *, state="connected"):
    return normalize_pagespeed_insights_evidence_bound(
        payload or psi_payload(),
        state=state,
        observed_at="2026-09-22T18:20:00Z",
        source_url="https://example.com/start",
    )


def test_direct_crux_histograms_normalize_to_provider_neutral_field_shape():
    raw = crux_payload()
    result = normalize_crux_field_distribution_evidence(raw, bound_crux(raw))
    assert result["state"] == "connected"
    assert result["provider"] == "CrUX"
    assert result["metrics"]["lcp"]["bins"][0] == {
        "min": 0.0, "max": 2500.0, "proportion": 0.8,
    }
    assert result["metrics"]["cls"]["unit"] == "score"
    assert validate_field_distribution_contract(result) == {
        "version": FIELD_DISTRIBUTION_INTEGRITY_VERSION,
        "valid": True,
        "reasons": [],
    }


def test_psi_distributions_use_same_shape_and_scale_cls_to_score():
    raw = psi_payload()
    result = normalize_psi_field_distribution_evidence(raw, bound_psi(raw))
    assert result["state"] == "connected"
    assert result["provider"] == "PageSpeed Insights / CrUX"
    assert result["metrics"]["cls"]["p75"] == 0.12
    assert result["metrics"]["cls"]["bins"][0]["max"] == 0.1
    assert result["metrics"]["cls"]["bins"][1]["max"] == 0.25
    assert validate_field_distribution_contract(result)["valid"] is True


def test_psi_lighthouse_lab_values_never_enter_field_distribution():
    raw = psi_payload()
    result = normalize_psi_field_distribution_evidence(raw, bound_psi(raw))
    assert result["metrics"]["lcp"]["p75"] == 2400.0
    assert result["metrics"]["lcp"]["p75"] != 9999
    assert set(result["metrics"]) == {"cls", "lcp"}


def test_invalid_bound_crux_contract_fails_closed_without_measurements():
    raw = crux_payload()
    trusted = bound_crux(raw)
    trusted["adapter_version"] = "forged"
    result = normalize_crux_field_distribution_evidence(raw, trusted)
    assert result["state"] == "unavailable"
    assert result["reason"] == "bound_crux_contract_invalid"
    assert result["metrics"] is None
    assert validate_field_distribution_contract(result)["valid"] is True


def test_invalid_bound_psi_contract_fails_closed_without_measurements():
    raw = psi_payload()
    trusted = bound_psi(raw)
    trusted["adapter_version"] = "forged"
    result = normalize_psi_field_distribution_evidence(raw, trusted)
    assert result["state"] == "unavailable"
    assert result["reason"] == "bound_pagespeed_contract_invalid"
    assert result["metrics"] is None
    assert validate_field_distribution_contract(result)["valid"] is True


def test_non_connected_field_state_retains_no_distribution_measurements():
    raw = psi_payload()
    result = normalize_psi_field_distribution_evidence(raw, bound_psi(raw, state="rate_limited"))
    assert result["state"] == "rate_limited"
    assert result["metrics"] is None
    assert validate_field_distribution_contract(result)["valid"] is True


def test_raw_percentile_mismatch_is_not_laundered_into_distribution():
    raw = crux_payload()
    trusted = bound_crux(raw)
    raw["record"]["metrics"]["largest_contentful_paint"]["percentiles"]["p75"] = 9999
    result = normalize_crux_field_distribution_evidence(raw, trusted)
    assert "lcp" not in result["metrics"]
    assert {"metric": "lcp", "reason": "percentile_mismatch"} in result["omitted_metrics"]
    assert validate_field_distribution_contract(result)["valid"] is True


def test_overlapping_bins_are_omitted_not_promoted():
    raw = crux_payload()
    trusted = bound_crux(raw)
    raw["record"]["metrics"]["largest_contentful_paint"]["histogram"][1]["start"] = 2000
    result = normalize_crux_field_distribution_evidence(raw, trusted)
    assert "lcp" not in result["metrics"]
    assert {"metric": "lcp", "reason": "distribution_invalid"} in result["omitted_metrics"]


def test_distribution_mass_must_be_approximately_one():
    raw = psi_payload()
    trusted = bound_psi(raw)
    raw["loadingExperience"]["metrics"]["LARGEST_CONTENTFUL_PAINT_MS"]["distributions"][0]["proportion"] = 0.5
    result = normalize_psi_field_distribution_evidence(raw, trusted)
    assert "lcp" not in result["metrics"]
    assert {"metric": "lcp", "reason": "distribution_invalid"} in result["omitted_metrics"]


def test_when_all_distributions_are_invalid_state_becomes_unavailable():
    raw = crux_payload()
    trusted = bound_crux(raw)
    for metric in raw["record"]["metrics"].values():
        metric.pop("histogram")
    result = normalize_crux_field_distribution_evidence(raw, trusted)
    assert result["state"] == "unavailable"
    assert result["reason"] == "field_distributions_unavailable"
    assert result["metrics"] is None
    assert validate_field_distribution_contract(result)["valid"] is True


def test_psi_origin_fallback_reads_loading_experience_not_origin_or_lab_data():
    raw = psi_payload()
    raw["loadingExperience"]["origin_fallback"] = True
    raw["loadingExperience"]["id"] = "https://example.com/"
    raw["originLoadingExperience"] = {"metrics": {}}
    trusted = bound_psi(raw)
    assert trusted["field"]["scope"] == "origin"
    result = normalize_psi_field_distribution_evidence(raw, trusted)
    assert result["state"] == "connected"
    assert result["scope"] == "origin"
    assert result["metrics"]["lcp"]["p75"] == 2400.0


def test_crux_distribution_rejects_raw_source_mismatch_even_with_same_metrics():
    raw = crux_payload()
    trusted = bound_crux(raw)
    raw["record"]["key"]["url"] = "https://foreign.example/page"
    result = normalize_crux_field_distribution_evidence(raw, trusted)
    assert result["state"] == "unavailable"
    assert result["reason"] == "crux_distribution_source_mismatch"
    assert result["metrics"] is None


def test_psi_distribution_rejects_raw_source_mismatch_even_with_same_metrics():
    raw = psi_payload()
    trusted = bound_psi(raw)
    raw["loadingExperience"]["initial_url"] = "https://foreign.example/start"
    result = normalize_psi_field_distribution_evidence(raw, trusted)
    assert result["state"] == "unavailable"
    assert result["reason"] == "psi_distribution_source_mismatch"
    assert result["metrics"] is None


def test_integrity_rejects_tampered_overlap_and_mass():
    raw = crux_payload()
    result = normalize_crux_field_distribution_evidence(raw, bound_crux(raw))
    result["metrics"]["lcp"]["bins"][1]["min"] = 2000.0
    result["metrics"]["lcp"]["bins"][0]["proportion"] = 0.2
    check = validate_field_distribution_contract(result)
    assert check["valid"] is False
    assert "metric_bin_overlap" in check["reasons"]
    assert "metric_distribution_mass_invalid" in check["reasons"]


def test_integrity_rejects_credential_bearing_source_identity():
    raw = crux_payload()
    result = normalize_crux_field_distribution_evidence(raw, bound_crux(raw))
    result["source_url"] = "https://user:secret@example.com/page"
    check = validate_field_distribution_contract(result)
    assert check["valid"] is False
    assert "source_url_invalid" in check["reasons"]


def test_integrity_rejects_cross_provider_source_contract_laundering():
    raw = crux_payload()
    result = normalize_crux_field_distribution_evidence(raw, bound_crux(raw))
    result["source_contract"] = "nextgen_pagespeed_bound_integrity_v1"
    check = validate_field_distribution_contract(result)
    assert check["valid"] is False
    assert "provider_source_contract_mismatch" in check["reasons"]


def test_integrity_rejects_metric_present_and_omitted():
    raw = crux_payload()
    result = normalize_crux_field_distribution_evidence(raw, bound_crux(raw))
    result["omitted_metrics"].append({"metric": "lcp", "reason": "forged"})
    check = validate_field_distribution_contract(result)
    assert check["valid"] is False
    assert "metric_present_and_omitted" in check["reasons"]


def test_normalizers_do_not_mutate_provider_or_bound_inputs():
    crux_raw = crux_payload()
    crux_source = bound_crux(crux_raw)
    psi_raw = psi_payload()
    psi_source = bound_psi(psi_raw)
    snapshots = tuple(deepcopy(value) for value in (crux_raw, crux_source, psi_raw, psi_source))
    normalize_crux_field_distribution_evidence(crux_raw, crux_source)
    normalize_psi_field_distribution_evidence(psi_raw, psi_source)
    assert (crux_raw, crux_source, psi_raw, psi_source) == snapshots
