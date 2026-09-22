from copy import deepcopy

from app.nextgen_browser_performance_cwv import assess_core_web_vitals_field_evidence


def field(metrics=None, *, state="connected"):
    return {
        "version": "nextgen_field_performance_v1",
        "evidence_kind": "field",
        "provider": "CrUX",
        "state": state,
        "reason": None,
        "scope": "url",
        "observed_at": "2026-09-22T10:00:00Z",
        "source_url": "https://example.test/",
        "metrics": metrics if state == "connected" else None,
    }


def metric(value, unit, rating=None):
    return {"value": value, "unit": unit, "rating": rating}


def test_passes_only_when_all_three_required_field_metrics_are_good():
    evidence = field({
        "lcp": metric(2500, "ms", "good"),
        "inp": metric(200, "ms", "good"),
        "cls": metric(0.1, "score", "good"),
    })
    result = assess_core_web_vitals_field_evidence(evidence)
    assert result["state"] == "passed"
    assert result["coverage_complete"] is True
    assert result["missing_required_metrics"] == []
    assert result["non_good_metrics"] == []


def test_good_boundaries_are_inclusive_and_next_values_need_improvement():
    evidence = field({
        "lcp": metric(2500.1, "ms"),
        "inp": metric(200.1, "ms"),
        "cls": metric(0.1001, "score"),
    })
    result = assess_core_web_vitals_field_evidence(evidence)
    assert result["state"] == "failed"
    assert result["metrics"]["lcp"]["derived_rating"] == "needs_improvement"
    assert result["metrics"]["inp"]["derived_rating"] == "needs_improvement"
    assert result["metrics"]["cls"]["derived_rating"] == "needs_improvement"


def test_poor_thresholds_are_bounded_and_classified_from_numeric_field_values():
    evidence = field({
        "lcp": metric(4000.1, "ms"),
        "inp": metric(500.1, "ms"),
        "cls": metric(0.2501, "score"),
    })
    result = assess_core_web_vitals_field_evidence(evidence)
    assert result["state"] == "failed"
    assert {row["derived_rating"] for row in result["metrics"].values()} == {"poor"}


def test_known_non_good_metric_proves_failure_even_when_other_required_metrics_are_missing():
    result = assess_core_web_vitals_field_evidence(field({"lcp": metric(3100, "ms")}))
    assert result["state"] == "failed"
    assert result["coverage_complete"] is False
    assert result["missing_required_metrics"] == ["inp", "cls"]
    assert result["non_good_metrics"] == ["lcp"]


def test_incomplete_all_good_field_data_remains_not_verified():
    result = assess_core_web_vitals_field_evidence(field({
        "lcp": metric(1800, "ms"),
        "inp": metric(150, "ms"),
    }))
    assert result["state"] == "not_verified"
    assert result["reason"] == "core_web_vitals_metrics_incomplete"
    assert result["missing_required_metrics"] == ["cls"]


def test_non_connected_field_state_never_becomes_a_cwv_measurement():
    result = assess_core_web_vitals_field_evidence(field(state="rate_limited"))
    assert result["state"] == "not_verified"
    assert result["reason"] == "field_evidence_rate_limited"
    assert result["metrics"] == {}


def test_lab_evidence_is_rejected_instead_of_being_reinterpreted_as_field_cwv():
    lab = {
        "version": "nextgen_lighthouse_evidence_v1",
        "evidence_kind": "lab",
        "provider": "Lighthouse",
        "state": "connected",
        "reason": None,
        "observed_at": None,
        "source_url": "https://example.test/",
        "performance_score": 100,
        "metrics": {"lcp": {"value": 1000, "unit": "ms", "score": 1.0}},
        "opportunities": [],
    }
    result = assess_core_web_vitals_field_evidence(lab)
    assert result["state"] == "not_verified"
    assert result["reason"] == "field_contract_invalid"
    assert "evidence_kind_mismatch" in result["contract_reasons"]


def test_invalid_field_contract_fails_closed_before_threshold_assessment():
    evidence = field({
        "lcp": metric(1800, "seconds", "good"),
        "inp": metric(150, "ms", "good"),
        "cls": metric(0.05, "score", "good"),
    })
    result = assess_core_web_vitals_field_evidence(evidence)
    assert result["state"] == "not_verified"
    assert result["reason"] == "field_contract_invalid"
    assert "metric_unit_mismatch" in result["contract_reasons"]


def test_provider_rating_disagreement_fails_closed_instead_of_claiming_cwv_pass():
    evidence = field({
        "lcp": metric(1800, "ms", "poor"),
        "inp": metric(150, "ms", "good"),
        "cls": metric(0.05, "score", "good"),
    })
    result = assess_core_web_vitals_field_evidence(evidence)
    assert result["state"] == "not_verified"
    assert result["reason"] == "field_metric_rating_mismatch"
    assert result["provider_rating_mismatches"] == ["lcp"]
    assert result["metrics"]["lcp"]["derived_rating"] == "good"


def test_assessment_does_not_mutate_input_evidence():
    evidence = field({
        "lcp": metric(1800, "ms", "good"),
        "inp": metric(150, "ms", "good"),
        "cls": metric(0.05, "score", "good"),
        "fcp": metric(900, "ms", "good"),
    })
    before = deepcopy(evidence)
    assess_core_web_vitals_field_evidence(evidence)
    assert evidence == before
