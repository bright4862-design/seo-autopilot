from copy import deepcopy
import json

from app.adaptive_joint_evidence_decision import (
    ADAPTIVE_JOINT_EVIDENCE_DECISION_VERSION,
    evaluate_joint_adaptive_evidence,
)


def _fp(char: str) -> str:
    return char * 64


def _sites():
    return ("site-a", "site-b")


def _experiment(**overrides):
    result = {
        "version": "adaptive_crawl_experiment_decision_v1",
        "decision": "smart_500_experiment_candidate",
        "reason": "150_to_500_value_and_500_to_1000_efficiency_met",
        "site_ids": _sites(),
        "smart_500_population_fingerprints": (
            ("site-a", _fp("a")),
            ("site-b", _fp("b")),
        ),
        "full_comparison_sites": 2,
        "population_scope_complete": False,
        "production_budget_authorized": False,
        "site_fully_understood": False,
    }
    result.update(overrides)
    return result


def _fix(**overrides):
    result = {
        "version": "adaptive_fix_benchmark_acceptance_v1",
        "decision": "smart_500_fix_evidence_candidate",
        "reason": "fix_coverage_and_incremental_yield_thresholds_met",
        "site_ids": _sites(),
        "population_fingerprints": (
            ("site-a", _fp("a"), _fp("c"), _fp("e")),
            ("site-b", _fp("b"), _fp("d"), _fp("f")),
        ),
        "full_comparison_sites": 2,
        "corpus_fingerprint": _fp("1"),
        "population_scope_complete": False,
        "production_budget_authorized": False,
        "site_fully_understood": False,
    }
    result.update(overrides)
    return result


def test_positive_candidate_requires_both_evidence_families_and_exact_population_identity():
    result = evaluate_joint_adaptive_evidence(_experiment(), _fix())
    assert result["version"] == ADAPTIVE_JOINT_EVIDENCE_DECISION_VERSION
    assert result["decision"] == "smart_500_joint_evidence_candidate"
    assert result["site_ids"] == _sites()
    assert result["full_comparison_sites"] == 2
    assert len(result["joint_evidence_fingerprint"]) == 64
    assert result["standard_150_contract"] == "unchanged_upstream_reference"
    assert result["population_scope_complete"] is False
    assert result["production_budget_authorized"] is False
    assert result["site_fully_understood"] is False


def test_positive_candidate_is_deterministic():
    first = evaluate_joint_adaptive_evidence(_experiment(), _fix())
    second = evaluate_joint_adaptive_evidence(_experiment(), _fix())
    assert first == second


def test_json_transport_preserves_joint_identity():
    experiment = json.loads(json.dumps(_experiment()))
    fix = json.loads(json.dumps(_fix()))
    result = evaluate_joint_adaptive_evidence(experiment, fix)
    assert result["decision"] == "smart_500_joint_evidence_candidate"


def test_same_count_different_site_population_fails_closed():
    fix = _fix(site_ids=("site-a", "site-c"))
    result = evaluate_joint_adaptive_evidence(_experiment(), fix)
    assert result["decision"] == "insufficient_evidence"
    assert result["reason"] == "joint_site_population_mismatch"


def test_same_sites_different_smart_500_population_fails_closed():
    fix = _fix(
        population_fingerprints=(
            ("site-a", _fp("9"), _fp("c"), _fp("e")),
            ("site-b", _fp("b"), _fp("d"), _fp("f")),
        )
    )
    result = evaluate_joint_adaptive_evidence(_experiment(), fix)
    assert result["decision"] == "insufficient_evidence"
    assert result["reason"] == "joint_smart_500_population_mismatch"


def test_malformed_population_fingerprint_fails_closed():
    experiment = _experiment(
        smart_500_population_fingerprints=(("site-a", "not-a-sha"), ("site-b", _fp("b")))
    )
    result = evaluate_joint_adaptive_evidence(experiment, _fix())
    assert result["decision"] == "insufficient_evidence"
    assert result["reason"] == "joint_population_fingerprint_set_invalid"


def test_full_comparison_count_must_match_across_evidence_families():
    result = evaluate_joint_adaptive_evidence(_experiment(), _fix(full_comparison_sites=1))
    assert result["decision"] == "insufficient_evidence"
    assert result["reason"] == "joint_full_comparison_count_mismatch"


def test_fix_corpus_fingerprint_must_be_canonical_sha256():
    result = evaluate_joint_adaptive_evidence(_experiment(), _fix(corpus_fingerprint="bad"))
    assert result["decision"] == "insufficient_evidence"
    assert result["reason"] == "fix_corpus_fingerprint_invalid"


def test_standard_150_retention_dominates_even_when_fix_evidence_is_positive():
    experiment = _experiment(
        decision="standard_150_reference_retained",
        reason="150_to_500_value_thresholds_not_met",
    )
    result = evaluate_joint_adaptive_evidence(experiment, _fix())
    assert result["decision"] == "standard_150_joint_reference_retained"


def test_blind_1000_discovery_reference_retention_propagates():
    experiment = _experiment(
        decision="blind_1000_reference_retained",
        reason="smart_500_acceptance_not_met",
    )
    result = evaluate_joint_adaptive_evidence(experiment, _fix())
    assert result["decision"] == "blind_1000_joint_reference_retained"


def test_blind_1000_fix_reference_retention_propagates():
    fix = _fix(
        decision="blind_1000_fix_reference_retained",
        reason="fix_evidence_thresholds_not_met",
    )
    result = evaluate_joint_adaptive_evidence(_experiment(), fix)
    assert result["decision"] == "blind_1000_joint_reference_retained"


def test_upstream_insufficient_evidence_fails_closed():
    experiment = _experiment(decision="insufficient_evidence", reason="tail_unknown")
    result = evaluate_joint_adaptive_evidence(experiment, _fix())
    assert result["decision"] == "insufficient_evidence"
    assert result["reason"] == "experiment_evidence_insufficient"


def test_fix_insufficient_evidence_fails_closed():
    fix = _fix(decision="insufficient_evidence", reason="high_impact_unknown")
    result = evaluate_joint_adaptive_evidence(_experiment(), fix)
    assert result["decision"] == "insufficient_evidence"
    assert result["reason"] == "fix_evidence_insufficient"


def test_forged_production_authority_is_rejected_from_either_envelope():
    experiment = _experiment(production_budget_authorized=True)
    first = evaluate_joint_adaptive_evidence(experiment, _fix())
    assert first["decision"] == "insufficient_evidence"
    assert first["reason"] == "experiment_decision_shadow_flags_invalid"

    fix = _fix(site_fully_understood=True)
    second = evaluate_joint_adaptive_evidence(_experiment(), fix)
    assert second["decision"] == "insufficient_evidence"
    assert second["reason"] == "fix_decision_shadow_flags_invalid"


def test_unknown_versions_and_decisions_fail_closed():
    wrong_version = evaluate_joint_adaptive_evidence(
        _experiment(version="adaptive_crawl_experiment_decision_v2"), _fix()
    )
    assert wrong_version["reason"] == "experiment_decision_version_mismatch"

    unknown_decision = evaluate_joint_adaptive_evidence(
        _experiment(decision="always_crawl_1000"), _fix()
    )
    assert unknown_decision["reason"] == "experiment_decision_unknown"


def test_inputs_are_not_mutated():
    experiment = _experiment()
    fix = _fix()
    before = deepcopy((experiment, fix))
    evaluate_joint_adaptive_evidence(experiment, fix)
    assert (experiment, fix) == before
