from copy import deepcopy

from app.nextgen_browser_performance_lighthouse_units import (
    LIGHTHOUSE_UNIT_INTEGRITY_VERSION,
    LIGHTHOUSE_UNIT_NORMALIZATION_VERSION,
    normalize_lighthouse_metric_units,
    validate_lighthouse_metric_unit_contract,
)


def _lab(metrics=None, *, state="connected"):
    return {
        "version": "nextgen_lighthouse_evidence_v1",
        "evidence_kind": "lab",
        "provider": "Lighthouse",
        "state": state,
        "reason": None,
        "observed_at": "2026-09-22T10:00:00Z",
        "source_url": "https://example.com/",
        "performance_score": 92.0 if state == "connected" else None,
        "metrics": metrics,
        "opportunities": [],
    }


def test_normalizes_timing_and_cls_units_to_provider_neutral_values():
    evidence = _lab({
        "lcp": {"value": 2100.0, "unit": "millisecond", "score": 0.9},
        "cls": {"value": 0.08, "unit": "unitless", "score": 0.95},
    })
    result = normalize_lighthouse_metric_units(evidence)
    assert result["version"] == LIGHTHOUSE_UNIT_NORMALIZATION_VERSION
    assert result["state"] == "normalized"
    assert result["metrics"]["lcp"]["unit"] == "ms"
    assert result["metrics"]["cls"]["unit"] == "score"
    assert result["excluded_metrics"] == []
    assert validate_lighthouse_metric_unit_contract(result)["valid"] is True


def test_accepts_existing_canonical_aliases_deterministically():
    result = normalize_lighthouse_metric_units(_lab({
        "speed_index": {"value": 3100.0, "unit": "ms", "score": 0.7},
        "cls": {"value": 0.12, "unit": "score", "score": 0.8},
    }))
    assert list(result["metrics"]) == ["cls", "speed_index"]
    assert result["metrics"]["speed_index"]["unit"] == "ms"
    assert result["metrics"]["cls"]["unit"] == "score"


def test_wrong_timing_unit_is_excluded_without_discarding_valid_lab_metric():
    result = normalize_lighthouse_metric_units(_lab({
        "lcp": {"value": 2100.0, "unit": "byte", "score": 0.9},
        "fcp": {"value": 900.0, "unit": "milliseconds", "score": 0.95},
    }))
    assert result["state"] == "normalized"
    assert set(result["metrics"]) == {"fcp"}
    assert result["excluded_metrics"] == [{
        "metric": "lcp",
        "reason": "metric_unit_mismatch",
        "raw_unit": "byte",
        "expected_unit": "ms",
    }]
    assert validate_lighthouse_metric_unit_contract(result)["valid"] is True


def test_missing_unit_is_not_guessed():
    result = normalize_lighthouse_metric_units(_lab({
        "total_blocking_time": {"value": 120.0, "score": 0.9},
    }))
    assert result["state"] == "not_verified"
    assert result["metrics"] is None
    assert result["reason"] == "all_metric_units_unverified"
    assert result["excluded_metrics"][0]["reason"] == "metric_unit_missing"
    assert validate_lighthouse_metric_unit_contract(result)["valid"] is True


def test_malformed_and_unsupported_metrics_are_excluded_fail_closed():
    result = normalize_lighthouse_metric_units(_lab({
        "lcp": "2100 ms",
        "mystery_metric": {"value": 4, "unit": "widgets"},
        "inp": {"value": -1, "unit": "millisecond"},
    }))
    assert result["state"] == "not_verified"
    assert [row["metric"] for row in result["excluded_metrics"]] == ["inp", "lcp", "mystery_metric"]
    assert {row["reason"] for row in result["excluded_metrics"]} == {
        "metric_value_invalid", "metric_not_object", "metric_unsupported"
    }


def test_connected_score_only_lighthouse_is_not_applicable_not_failed():
    result = normalize_lighthouse_metric_units(_lab(None))
    assert result["state"] == "not_applicable"
    assert result["reason"] == "source_metrics_absent"
    assert result["metrics"] is None
    assert result["excluded_metrics"] == []
    assert validate_lighthouse_metric_unit_contract(result)["valid"] is True


def test_non_connected_lab_state_never_becomes_normalized_measurement():
    result = normalize_lighthouse_metric_units(_lab(None, state="rate_limited"))
    assert result["state"] == "not_verified"
    assert result["reason"] == "source_rate_limited"
    assert result["metrics"] is None
    assert validate_lighthouse_metric_unit_contract(result)["valid"] is True


def test_field_evidence_cannot_be_laundered_into_lab_units():
    field = {
        "version": "nextgen_lighthouse_evidence_v1",
        "evidence_kind": "field",
        "state": "connected",
        "source_url": "https://example.com/",
        "metrics": {"lcp": {"value": 2000.0, "unit": "ms"}},
    }
    result = normalize_lighthouse_metric_units(field)
    assert result["state"] == "not_verified"
    assert result["reason"] == "source_not_lab_evidence"
    assert result["metrics"] is None


def test_normalizer_does_not_mutate_source_evidence():
    evidence = _lab({"lcp": {"value": 2100.0, "unit": "millisecond", "score": 0.9}})
    before = deepcopy(evidence)
    normalize_lighthouse_metric_units(evidence)
    assert evidence == before


def test_integrity_rejects_forged_noncanonical_unit_and_source_version():
    result = normalize_lighthouse_metric_units(_lab({
        "lcp": {"value": 2100.0, "unit": "millisecond", "score": 0.9},
    }))
    forged = deepcopy(result)
    forged["metrics"]["lcp"]["unit"] = "millisecond"
    forged["source_version"] = "forged"
    check = validate_lighthouse_metric_unit_contract(forged)
    assert check["version"] == LIGHTHOUSE_UNIT_INTEGRITY_VERSION
    assert check["valid"] is False
    assert "metric_unit_not_canonical" in check["reasons"]
    assert "source_version_mismatch" in check["reasons"]
