import copy
import hashlib
import json

import pytest

from app.adaptive_fix_benchmark_acceptance import (
    ADAPTIVE_FIX_BENCHMARK_ACCEPTANCE_VERSION,
    ADAPTIVE_FIX_BENCHMARK_CORPUS_VERSION,
    evaluate_fix_benchmark_corpus,
    validate_fix_benchmark_corpus,
)


def _sha(seed):
    return hashlib.sha256(seed.encode()).hexdigest()


def _canon(value):
    if isinstance(value, dict):
        return {str(k): _canon(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_canon(v) for v in value]
    if isinstance(value, set):
        return sorted(_canon(v) for v in value)
    return value


def _bind(corpus):
    unsigned = copy.deepcopy(corpus)
    unsigned.pop("corpus_fingerprint", None)
    digest = hashlib.sha256()
    digest.update(ADAPTIVE_FIX_BENCHMARK_CORPUS_VERSION.encode())
    digest.update(b"\0")
    digest.update(json.dumps(_canon(unsigned), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())
    return digest.hexdigest()


def _corpus(
    *,
    sites=10,
    coverage=0.98,
    median_coverage=0.96,
    incremental_yield=1.25,
    high_state="observed",
    high_coverage=1.0,
):
    blind_fixes = sites * 100
    shared = round(blind_fixes * coverage)
    smart_only = sites * 2
    smart_fixes = shared + smart_only
    blind_only = blind_fixes - shared
    smart_pages = sites * 500
    blind_pages = sites * 1000
    incremental_pages = sites * 350
    incremental_fixes = round(incremental_yield * incremental_pages / 100.0)
    if high_state == "observed":
        blind_high = sites * 10
        shared_high = round(blind_high * high_coverage)
        smart_high = shared_high + sites
        blind_only_high = blind_high - shared_high
        normalized_high_coverage = None if blind_high == 0 else round(shared_high / blind_high, 6)
    else:
        smart_high = blind_high = shared_high = blind_only_high = normalized_high_coverage = None
    site_ids = tuple(f"site-{index:02d}" for index in range(sites))
    corpus = {
        "version": ADAPTIVE_FIX_BENCHMARK_CORPUS_VERSION,
        "state": "observed",
        "valid": True,
        "site_count": sites,
        "site_ids": site_ids,
        "full_500_vs_1000_sites": sites,
        "inventory_limited_sites": 0,
        "smart_pages_assessed": smart_pages,
        "blind_pages_assessed": blind_pages,
        "pages_saved_by_smart": blind_pages - smart_pages,
        "smart_fix_fingerprints_site_scoped": smart_fixes,
        "blind_fix_fingerprints_site_scoped": blind_fixes,
        "shared_fix_fingerprints_site_scoped": shared,
        "blind_only_fix_fingerprints_site_scoped": blind_only,
        "smart_only_fix_fingerprints_site_scoped": smart_only,
        "smart_fix_coverage_vs_blind": round(shared / blind_fixes, 6),
        "median_site_smart_fix_coverage_vs_blind": median_coverage,
        "smart_incremental_pages_vs_standard": incremental_pages,
        "smart_incremental_fix_fingerprints_vs_standard_site_scoped": incremental_fixes,
        "smart_incremental_fix_yield_per_100": round(incremental_fixes * 100.0 / incremental_pages, 4),
        "high_impact_evidence_state": high_state,
        "smart_high_impact_fix_fingerprints_site_scoped": smart_high,
        "blind_high_impact_fix_fingerprints_site_scoped": blind_high,
        "shared_high_impact_fix_fingerprints_site_scoped": shared_high,
        "blind_only_high_impact_fix_fingerprints_site_scoped": blind_only_high,
        "smart_high_impact_coverage_vs_blind": normalized_high_coverage,
        "population_fingerprints": tuple(
            (site_id, _sha(site_id + ":smart"), _sha(site_id + ":blind"), _sha(site_id + ":binding"))
            for site_id in site_ids
        ),
        "standard_150_preserved": True,
        "population_scope_complete": False,
        "production_budget_authorized": False,
        "site_fully_understood": False,
    }
    corpus["corpus_fingerprint"] = _bind(corpus)
    return corpus


def _rebind(corpus):
    result = copy.deepcopy(corpus)
    result["corpus_fingerprint"] = _bind(result)
    return result


def test_validator_accepts_exact_corpus_and_preserves_standard_150_boundary():
    corpus = _corpus()
    checked = validate_fix_benchmark_corpus(corpus)
    assert checked["valid"] is True
    assert checked["site_ids"] == corpus["site_ids"]
    assert corpus["standard_150_preserved"] is True
    assert corpus["production_budget_authorized"] is False


def test_validator_rejects_transport_tamper_before_thresholding():
    corpus = _corpus()
    corpus["pages_saved_by_smart"] -= 1
    checked = validate_fix_benchmark_corpus(corpus)
    assert checked == {"valid": False, "reason": "corpus_fingerprint_mismatch"}


def test_validator_rejects_rebound_fix_partition_drift():
    corpus = _corpus()
    corpus["blind_only_fix_fingerprints_site_scoped"] += 1
    corpus = _rebind(corpus)
    checked = validate_fix_benchmark_corpus(corpus)
    assert checked == {"valid": False, "reason": "fix_partition_mismatch"}


def test_validator_rejects_rebound_population_identity_drift():
    corpus = _corpus()
    entries = list(corpus["population_fingerprints"])
    entries[0] = (entries[0][0], "NOT-SHA", entries[0][2], entries[0][3])
    corpus["population_fingerprints"] = tuple(entries)
    corpus = _rebind(corpus)
    checked = validate_fix_benchmark_corpus(corpus)
    assert checked == {"valid": False, "reason": "population_fingerprint_set_invalid"}


def test_validator_rejects_forged_authority_even_if_rebound():
    corpus = _corpus()
    corpus["production_budget_authorized"] = True
    corpus = _rebind(corpus)
    checked = validate_fix_benchmark_corpus(corpus)
    assert checked == {"valid": False, "reason": "production_budget_authorized_forbidden_claim"}


def test_candidate_requires_fix_coverage_and_incremental_fix_yield():
    result = evaluate_fix_benchmark_corpus(_corpus())
    assert result["version"] == ADAPTIVE_FIX_BENCHMARK_ACCEPTANCE_VERSION
    assert result["decision"] == "smart_500_fix_evidence_candidate"
    assert result["failed_thresholds"] == ()
    assert result["smart_fix_coverage_vs_blind"] >= 0.95
    assert result["smart_incremental_fix_yield_per_100"] >= 0.5
    assert result["production_budget_authorized"] is False
    assert result["site_fully_understood"] is False


def test_low_fix_coverage_retains_blind_reference():
    result = evaluate_fix_benchmark_corpus(_corpus(coverage=0.80, median_coverage=0.80))
    assert result["decision"] == "blind_1000_fix_reference_retained"
    assert "fix_coverage" in result["failed_thresholds"]
    assert "median_site_fix_coverage" in result["failed_thresholds"]


def test_low_incremental_fix_yield_fails_separately_from_coverage():
    result = evaluate_fix_benchmark_corpus(_corpus(incremental_yield=0.10))
    assert result["decision"] == "blind_1000_fix_reference_retained"
    assert result["failed_thresholds"] == ("incremental_fix_yield",)


def test_missing_high_impact_evidence_fails_closed_by_default():
    result = evaluate_fix_benchmark_corpus(_corpus(high_state="not_observed"))
    assert result["decision"] == "insufficient_evidence"
    assert result["reason"] == "high_impact_fix_evidence_not_fully_observed"


def test_high_impact_requirement_can_be_disabled_without_forging_observation():
    result = evaluate_fix_benchmark_corpus(
        _corpus(high_state="not_observed"),
        require_high_impact_observed=False,
    )
    assert result["decision"] == "smart_500_fix_evidence_candidate"
    assert result["high_impact_evidence_state"] == "not_observed"
    assert result["smart_high_impact_coverage_vs_blind"] is None


def test_low_observed_high_impact_coverage_retains_blind_reference():
    result = evaluate_fix_benchmark_corpus(_corpus(high_coverage=0.80))
    assert result["decision"] == "blind_1000_fix_reference_retained"
    assert "high_impact_fix_coverage" in result["failed_thresholds"]


def test_too_few_full_comparison_sites_is_insufficient_not_failure():
    result = evaluate_fix_benchmark_corpus(_corpus(sites=4), min_full_comparison_sites=5)
    assert result["decision"] == "insufficient_evidence"
    assert result["reason"] == "too_few_full_500_vs_1000_sites"


def test_invalid_thresholds_fail_closed():
    corpus = _corpus()
    assert evaluate_fix_benchmark_corpus(corpus, min_full_comparison_sites=0)["reason"] == "invalid_threshold:min_full_comparison_sites"
    assert evaluate_fix_benchmark_corpus(corpus, min_fix_coverage=1.1)["reason"] == "invalid_threshold:min_fix_coverage"
    assert evaluate_fix_benchmark_corpus(corpus, min_incremental_fix_yield_per_100=float("nan"))["reason"] == "invalid_threshold:min_incremental_fix_yield_per_100"
    assert evaluate_fix_benchmark_corpus(corpus, require_high_impact_observed="yes")["reason"] == "invalid_threshold:require_high_impact_observed"


def test_zero_fix_denominator_remains_insufficient_not_zero_coverage():
    corpus = _corpus()
    corpus["smart_fix_fingerprints_site_scoped"] = 0
    corpus["blind_fix_fingerprints_site_scoped"] = 0
    corpus["shared_fix_fingerprints_site_scoped"] = 0
    corpus["blind_only_fix_fingerprints_site_scoped"] = 0
    corpus["smart_only_fix_fingerprints_site_scoped"] = 0
    corpus["smart_fix_coverage_vs_blind"] = None
    corpus["smart_incremental_fix_fingerprints_vs_standard_site_scoped"] = 0
    corpus["smart_incremental_fix_yield_per_100"] = 0.0
    corpus = _rebind(corpus)
    result = evaluate_fix_benchmark_corpus(corpus)
    assert result["decision"] == "insufficient_evidence"
    assert result["reason"] == "fix_coverage_unavailable"


def test_evaluation_is_deterministic_and_does_not_mutate_input():
    corpus = _corpus()
    before = copy.deepcopy(corpus)
    first = evaluate_fix_benchmark_corpus(corpus)
    second = evaluate_fix_benchmark_corpus(corpus)
    assert first == second
    assert corpus == before
