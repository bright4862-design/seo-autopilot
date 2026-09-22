from copy import deepcopy

import pytest

import app.adaptive_smart_500_decision as decision_module
from app.adaptive_smart_500_decision import (
    ADAPTIVE_SMART_500_DECISION_VERSION,
    evaluate_population_bound_smart_500,
)


@pytest.fixture(autouse=True)
def _isolate_cross_corpus_decision_from_existing_marginal_validator(monkeypatch):
    """Keep this suite focused on the new cross-corpus decision boundary.

    `adaptive_marginal_corpus` has its own integrity suite. Here we provide only the
    fields consumed by the new combiner and make validator acceptance explicit.
    """

    def _validate(corpus):
        valid = corpus.get("valid") is True
        return {"valid": valid, "reason": "ok" if valid else "corpus_not_valid"}

    monkeypatch.setattr(decision_module, "validate_marginal_gap_corpus", _validate)


def _fingerprint(char):
    return char * 64


def _site_ids():
    return tuple(f"site-{i:02d}" for i in range(10))


def _benchmark(**overrides):
    site_ids = _site_ids()
    result = {
        "version": "adaptive_benchmark_bundle_corpus_v1",
        "state": "observed",
        "valid": True,
        "population_scope_complete": False,
        "site_count": 10,
        "site_ids": site_ids,
        "population_fingerprints": tuple(
            (site_id, _fingerprint(chr(97 + i)), _fingerprint(chr(107 + i)))
            for i, site_id in enumerate(site_ids)
        ),
        "full_500_vs_1000_sites": 10,
        "inventory_limited_sites": 0,
        "smart_pages_assessed": 5000,
        "blind_pages_assessed": 10000,
        "pages_saved_by_smart": 5000,
        "smart_finding_coverage_vs_blind": 0.98,
        "median_site_finding_coverage_vs_blind": 0.97,
        "important_coverage_vs_blind": 0.99,
        "high_value_coverage_vs_blind": 0.99,
    }
    result.update(overrides)
    return result


def _marginal(**overrides):
    site_ids = _site_ids()
    result = {
        "version": "adaptive_marginal_gap_corpus_v1",
        "valid": True,
        "state": "observed",
        "reason": "ok",
        "site_count": 10,
        "full_500_vs_1000_sites": 10,
        "inventory_limited_sites": 0,
        "site_ids": site_ids,
        "sites": tuple(
            {
                "site_id": site_id,
                "smart_500_population_fingerprint": _fingerprint(chr(97 + i)),
                "blind_1000_population_fingerprint": _fingerprint(chr(107 + i)),
            }
            for i, site_id in enumerate(site_ids)
        ),
        "full_smart_500_reference_finding_coverage": 0.98,
        "full_blind_tail_pages": 5000,
        "full_blind_tail_new_findings": 20,
        "full_blind_tail_new_finding_yield_per_100": 0.4,
        "median_full_site_blind_tail_finding_yield_per_100": 0.4,
        "full_high_impact_observed_sites": 10,
        "high_impact_evidence_state": "observed",
        "full_smart_500_missed_reference_high_impact_findings": 0,
        "full_blind_tail_new_high_impact_findings": 0,
        "population_scope_complete": False,
        "production_budget_authorized": False,
        "site_fully_understood": False,
    }
    result.update(overrides)
    return result


def test_population_bound_evidence_can_name_smart_500_candidate_without_authorizing_budget():
    result = evaluate_population_bound_smart_500(_benchmark(), _marginal())
    assert result["version"] == ADAPTIVE_SMART_500_DECISION_VERSION
    assert result["decision"] == "smart_500_candidate"
    assert result["production_budget_authorized"] is False
    assert result["site_fully_understood"] is False
    assert result["failed_thresholds"] == ()


def test_fails_closed_when_site_population_differs_between_corpora():
    marginal = _marginal(site_ids=tuple(reversed(_site_ids())))
    result = evaluate_population_bound_smart_500(_benchmark(), marginal)
    assert result["decision"] == "insufficient_evidence"
    assert result["reason"] == "site_population_identity_mismatch"


def test_fails_closed_when_population_fingerprint_differs():
    marginal = _marginal()
    sites = list(marginal["sites"])
    sites[0] = {**sites[0], "smart_500_population_fingerprint": _fingerprint("z")}
    marginal["sites"] = tuple(sites)
    result = evaluate_population_bound_smart_500(_benchmark(), marginal)
    assert result["decision"] == "insufficient_evidence"
    assert result["reason"] == "population_fingerprint_mismatch"


def test_fails_closed_when_marginal_integrity_rejects_transport():
    result = evaluate_population_bound_smart_500(_benchmark(), _marginal(valid=False))
    assert result["decision"] == "insufficient_evidence"
    assert result["reason"].startswith("marginal_corpus_integrity_failed:")


def test_preserves_coverage_insufficient_state():
    benchmark = _benchmark(high_value_coverage_vs_blind=None)
    result = evaluate_population_bound_smart_500(benchmark, _marginal())
    assert result["decision"] == "insufficient_evidence"
    assert result["reason"] == "coverage_evidence_insufficient"


def test_retains_blind_reference_when_coverage_acceptance_fails():
    benchmark = _benchmark(smart_finding_coverage_vs_blind=0.90)
    result = evaluate_population_bound_smart_500(
        benchmark,
        _marginal(full_smart_500_reference_finding_coverage=0.90),
    )
    assert result["decision"] == "blind_1000_reference_retained"
    assert result["reason"] == "coverage_acceptance_not_met"


def test_retains_blind_reference_when_tail_finding_yield_is_too_high():
    result = evaluate_population_bound_smart_500(
        _benchmark(),
        _marginal(full_blind_tail_new_finding_yield_per_100=1.1),
    )
    assert result["decision"] == "blind_1000_reference_retained"
    assert result["failed_thresholds"] == ("blind_tail_finding_yield",)


def test_retains_blind_reference_when_median_tail_yield_hides_weak_sites():
    result = evaluate_population_bound_smart_500(
        _benchmark(),
        _marginal(median_full_site_blind_tail_finding_yield_per_100=1.2),
    )
    assert result["decision"] == "blind_1000_reference_retained"
    assert result["failed_thresholds"] == ("median_site_blind_tail_finding_yield",)


def test_unknown_high_impact_evidence_is_not_treated_as_zero():
    marginal = _marginal(
        high_impact_evidence_state="partially_observed",
        full_high_impact_observed_sites=8,
        full_smart_500_missed_reference_high_impact_findings=None,
        full_blind_tail_new_high_impact_findings=None,
    )
    result = evaluate_population_bound_smart_500(_benchmark(), marginal)
    assert result["decision"] == "insufficient_evidence"
    assert result["reason"] == "high_impact_evidence_not_fully_observed"


def test_retains_blind_reference_when_tail_contains_high_impact_finding():
    result = evaluate_population_bound_smart_500(
        _benchmark(),
        _marginal(full_blind_tail_new_high_impact_findings=1),
    )
    assert result["decision"] == "blind_1000_reference_retained"
    assert result["failed_thresholds"] == ("blind_tail_high_impact_findings",)


def test_cross_corpus_finding_coverage_must_reconcile():
    result = evaluate_population_bound_smart_500(
        _benchmark(),
        _marginal(full_smart_500_reference_finding_coverage=0.97),
    )
    assert result["decision"] == "insufficient_evidence"
    assert result["reason"] == "cross_corpus_finding_coverage_mismatch"


def test_invalid_thresholds_fail_closed_and_input_is_not_mutated():
    benchmark = _benchmark()
    marginal = _marginal()
    before_benchmark = deepcopy(benchmark)
    before_marginal = deepcopy(marginal)
    result = evaluate_population_bound_smart_500(
        benchmark,
        marginal,
        max_blind_tail_finding_yield_per_100=float("nan"),
    )
    assert result["decision"] == "insufficient_evidence"
    assert result["reason"] == "invalid_threshold:max_blind_tail_finding_yield_per_100"
    assert benchmark == before_benchmark
    assert marginal == before_marginal
