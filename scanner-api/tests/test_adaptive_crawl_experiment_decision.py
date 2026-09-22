from copy import deepcopy

import pytest

import app.adaptive_crawl_experiment_decision as experiment_module
from app.adaptive_crawl_experiment_decision import (
    ADAPTIVE_CRAWL_EXPERIMENT_DECISION_VERSION,
    evaluate_adaptive_crawl_experiment,
)


def _fp(char):
    return char * 64


def _site_ids():
    return ("site-a", "site-b")


def _value(**overrides):
    site_ids = _site_ids()
    result = {
        "version": "adaptive_150_to_500_value_corpus_v1",
        "valid": True,
        "state": "observed",
        "site_ids": site_ids,
        "full_150_to_500_sites": 2,
        "inventory_limited_sites": 0,
        "sites": tuple(
            {
                "site_id": site_id,
                "smart_500_population_fingerprint": _fp(chr(97 + i)),
            }
            for i, site_id in enumerate(site_ids)
        ),
        "full_smart_150_to_500_new_finding_yield_per_100": 3.0,
        "median_full_site_smart_150_to_500_new_finding_yield_per_100": 2.5,
        "full_smart_150_reference_finding_coverage": 0.55,
        "full_smart_500_reference_finding_coverage": 0.90,
        "full_high_impact_observed_sites": 2,
        "high_impact_evidence_state": "observed",
        "population_scope_complete": False,
        "production_budget_authorized": False,
        "site_fully_understood": False,
    }
    result.update(overrides)
    return result


def _smart(**overrides):
    site_ids = _site_ids()
    result = {
        "version": "adaptive_smart_500_decision_v1",
        "decision": "smart_500_candidate",
        "reason": "population_bound_coverage_and_marginal_thresholds_met",
        "site_ids": site_ids,
        "population_fingerprints": tuple(
            (site_id, _fp(chr(97 + i)), _fp(chr(107 + i)))
            for i, site_id in enumerate(site_ids)
        ),
        "full_comparison_sites": 2,
        "production_budget_authorized": False,
        "site_fully_understood": False,
    }
    result.update(overrides)
    return result


@pytest.fixture(autouse=True)
def _isolate_existing_boundaries(monkeypatch):
    monkeypatch.setattr(
        experiment_module,
        "validate_150_to_500_value_corpus",
        lambda corpus: {
            "valid": corpus.get("valid") is True,
            "reason": "ok" if corpus.get("valid") is True else "corpus_not_valid",
        },
    )
    monkeypatch.setattr(
        experiment_module,
        "evaluate_population_bound_smart_500",
        lambda benchmark, marginal, **kwargs: _smart(),
    )


def test_candidate_requires_value_beyond_150_and_efficiency_against_1000():
    result = evaluate_adaptive_crawl_experiment(_value(), {}, {})
    assert result["version"] == ADAPTIVE_CRAWL_EXPERIMENT_DECISION_VERSION
    assert result["decision"] == "smart_500_experiment_candidate"
    assert result["production_budget_authorized"] is False
    assert result["population_scope_complete"] is False
    assert result["site_fully_understood"] is False
    assert result["smart_150_to_500_reference_finding_coverage_gain"] == 0.35


def test_low_aggregate_150_to_500_yield_retains_standard_150():
    result = evaluate_adaptive_crawl_experiment(
        _value(full_smart_150_to_500_new_finding_yield_per_100=0.5), {}, {}
    )
    assert result["decision"] == "standard_150_reference_retained"
    assert result["failed_thresholds"] == ("aggregate_150_to_500_finding_yield",)


def test_low_median_150_to_500_yield_retains_standard_150():
    result = evaluate_adaptive_crawl_experiment(
        _value(median_full_site_smart_150_to_500_new_finding_yield_per_100=0.5), {}, {}
    )
    assert result["decision"] == "standard_150_reference_retained"
    assert result["failed_thresholds"] == ("median_site_150_to_500_finding_yield",)


def test_small_150_to_500_coverage_gain_retains_standard_150():
    result = evaluate_adaptive_crawl_experiment(
        _value(
            full_smart_150_reference_finding_coverage=0.86,
            full_smart_500_reference_finding_coverage=0.90,
        ),
        {},
        {},
    )
    assert result["decision"] == "standard_150_reference_retained"
    assert result["failed_thresholds"] == ("150_to_500_reference_coverage_gain",)


def test_unknown_150_to_500_high_impact_evidence_fails_closed_by_default():
    result = evaluate_adaptive_crawl_experiment(
        _value(high_impact_evidence_state="not_observed", full_high_impact_observed_sites=0),
        {},
        {},
    )
    assert result["decision"] == "insufficient_evidence"
    assert result["reason"] == "150_to_500_high_impact_evidence_not_fully_observed"


def test_invalid_value_transport_fails_closed():
    result = evaluate_adaptive_crawl_experiment(_value(valid=False), {}, {})
    assert result["decision"] == "insufficient_evidence"
    assert result["reason"] == "value_corpus_integrity_failed:corpus_not_valid"


def test_no_full_150_to_500_comparison_fails_closed():
    result = evaluate_adaptive_crawl_experiment(
        _value(state="insufficient_evidence", full_150_to_500_sites=0), {}, {}
    )
    assert result["decision"] == "insufficient_evidence"
    assert result["reason"] == "no_full_150_to_500_evidence"


def test_downstream_insufficient_evidence_propagates_conservatively(monkeypatch):
    monkeypatch.setattr(
        experiment_module,
        "evaluate_population_bound_smart_500",
        lambda *args, **kwargs: {"decision": "insufficient_evidence", "reason": "tail_unknown"},
    )
    result = evaluate_adaptive_crawl_experiment(_value(), {}, {})
    assert result["decision"] == "insufficient_evidence"
    assert result["reason"] == "smart_500_evidence_insufficient"


def test_productive_500_to_1000_tail_retains_blind_reference(monkeypatch):
    monkeypatch.setattr(
        experiment_module,
        "evaluate_population_bound_smart_500",
        lambda *args, **kwargs: {
            "decision": "blind_1000_reference_retained",
            "reason": "marginal_acceptance_thresholds_not_met",
        },
    )
    result = evaluate_adaptive_crawl_experiment(_value(), {}, {})
    assert result["decision"] == "blind_1000_reference_retained"
    assert result["reason"] == "smart_500_acceptance_not_met"


def test_candidate_fails_closed_when_cross_stage_site_population_differs(monkeypatch):
    monkeypatch.setattr(
        experiment_module,
        "evaluate_population_bound_smart_500",
        lambda *args, **kwargs: _smart(site_ids=("site-a", "site-c")),
    )
    result = evaluate_adaptive_crawl_experiment(_value(), {}, {})
    assert result["decision"] == "insufficient_evidence"
    assert result["reason"] == "cross_stage_site_population_mismatch"


def test_candidate_fails_closed_when_smart_500_population_fingerprint_differs(monkeypatch):
    smart = _smart()
    entries = list(smart["population_fingerprints"])
    entries[0] = (entries[0][0], _fp("z"), entries[0][2])
    smart["population_fingerprints"] = tuple(entries)
    monkeypatch.setattr(
        experiment_module,
        "evaluate_population_bound_smart_500",
        lambda *args, **kwargs: smart,
    )
    result = evaluate_adaptive_crawl_experiment(_value(), {}, {})
    assert result["decision"] == "insufficient_evidence"
    assert result["reason"] == "cross_stage_smart_500_population_mismatch"


def test_invalid_threshold_fails_closed():
    result = evaluate_adaptive_crawl_experiment(
        _value(), {}, {}, min_150_to_500_reference_coverage_gain=float("nan")
    )
    assert result["decision"] == "insufficient_evidence"
    assert result["reason"] == "invalid_threshold:min_150_to_500_reference_coverage_gain"


def test_high_impact_observation_requirement_can_be_explicitly_relaxed():
    result = evaluate_adaptive_crawl_experiment(
        _value(high_impact_evidence_state="not_observed", full_high_impact_observed_sites=0),
        {},
        {},
        require_150_to_500_high_impact_observed=False,
    )
    assert result["decision"] == "smart_500_experiment_candidate"


def test_inputs_are_not_mutated():
    value = _value()
    benchmark = {"marker": "benchmark"}
    marginal = {"marker": "marginal"}
    before = (deepcopy(value), deepcopy(benchmark), deepcopy(marginal))
    evaluate_adaptive_crawl_experiment(value, benchmark, marginal)
    assert (value, benchmark, marginal) == before
