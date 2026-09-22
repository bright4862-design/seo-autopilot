import copy
import hashlib
import json

import pytest

from app.adaptive_fix_benchmark_corpus import (
    ADAPTIVE_FIX_BENCHMARK_CORPUS_VERSION,
    ADAPTIVE_FIX_BENCHMARK_VERSION,
    summarize_fix_benchmark_corpus,
    validate_fix_benchmark_member,
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


def _bind(result):
    digest = hashlib.sha256()
    digest.update(ADAPTIVE_FIX_BENCHMARK_VERSION.encode())
    digest.update(b"\0")
    digest.update(json.dumps(_canon(result), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())
    return digest.hexdigest()


def _benchmark(
    site,
    *,
    smart_pages=500,
    blind_pages=1000,
    standard_pages=150,
    standard_fixes=3,
    smart_fixes=10,
    blind_fixes=10,
    shared=10,
    incremental_fixes=7,
    high="observed",
):
    blind_only = blind_fixes - shared
    smart_only = smart_fixes - shared
    incremental_pages = smart_pages - standard_pages
    result = {
        "version": ADAPTIVE_FIX_BENCHMARK_VERSION,
        "manifest_input_population_fingerprint": _sha(site + ":input"),
        "candidate_urls_supplied": blind_pages,
        "candidate_urls_unique": blind_pages,
        "duplicate_candidate_identities_removed": 0,
        "standard_reference_target": standard_pages,
        "standard_reference_pages": standard_pages,
        "standard_reference_population_fingerprint": _sha(site + ":standard"),
        "smart_manifest_target": smart_pages,
        "smart_pages_assessed": smart_pages,
        "smart_population_fingerprint": _sha(site + ":smart"),
        "blind_pages_assessed": blind_pages,
        "blind_population_fingerprint": _sha(site + ":blind"),
        "pages_saved_by_smart": blind_pages - smart_pages,
        "standard_fix_fingerprints": standard_fixes,
        "smart_fix_fingerprints": smart_fixes,
        "blind_fix_fingerprints": blind_fixes,
        "shared_fix_fingerprints": shared,
        "blind_only_fix_fingerprints": blind_only,
        "smart_only_fix_fingerprints": smart_only,
        "smart_fix_coverage_vs_blind": None if blind_fixes == 0 else round(shared / blind_fixes, 6),
        "smart_incremental_pages_vs_standard": incremental_pages,
        "smart_incremental_fix_fingerprints_vs_standard": incremental_fixes,
        "smart_incremental_fix_yield_per_100": None if incremental_pages == 0 else round(incremental_fixes * 100 / incremental_pages, 4),
        "high_impact_evidence_state": high,
        "smart_high_impact_fix_fingerprints": 2 if high == "observed" else None,
        "blind_high_impact_fix_fingerprints": 2 if high == "observed" else None,
        "shared_high_impact_fix_fingerprints": 2 if high == "observed" else None,
        "blind_only_high_impact_fix_fingerprints": 0 if high == "observed" else None,
        "smart_high_impact_coverage_vs_blind": 1.0 if high == "observed" else None,
        "standard_150_preserved": True,
        "population_scope_complete": False,
        "production_budget_authorized": False,
        "site_fully_understood": False,
    }
    result["binding_fingerprint"] = _bind(result)
    return result


def _rebind(result):
    result = copy.deepcopy(result)
    result.pop("binding_fingerprint", None)
    result["binding_fingerprint"] = _bind(result)
    return result


def test_member_validator_accepts_exact_transport_and_authority_stays_false():
    result = _benchmark("a")
    checked = validate_fix_benchmark_member(result)
    assert checked["valid"] is True
    assert checked["errors"] == ()
    assert result["standard_150_preserved"] is True
    assert result["production_budget_authorized"] is False


def test_member_validator_rejects_binding_tamper():
    result = _benchmark("a")
    result["pages_saved_by_smart"] = 499
    checked = validate_fix_benchmark_member(result)
    assert checked["valid"] is False
    assert "binding_fingerprint_mismatch" in checked["errors"]


def test_member_validator_rejects_rebound_arithmetic_tamper():
    result = _benchmark("a")
    result["pages_saved_by_smart"] = 499
    result = _rebind(result)
    checked = validate_fix_benchmark_member(result)
    assert "page_savings_mismatch" in checked["errors"]


def test_member_validator_rejects_fix_partition_drift_even_when_rebound():
    result = _benchmark("a")
    result["blind_only_fix_fingerprints"] = 2
    result = _rebind(result)
    checked = validate_fix_benchmark_member(result)
    assert "blind_fix_partition_mismatch" in checked["errors"]


def test_member_validator_rejects_forged_production_authority():
    result = _benchmark("a")
    result["production_budget_authorized"] = True
    result = _rebind(result)
    checked = validate_fix_benchmark_member(result)
    assert "production_budget_authorized_forbidden_claim" in checked["errors"]


def test_corpus_aggregates_weighted_fix_coverage_and_incremental_yield():
    a = _benchmark("a", smart_fixes=9, blind_fixes=10, shared=9, incremental_fixes=6)
    b = _benchmark("b", smart_fixes=8, blind_fixes=10, shared=8, incremental_fixes=5)
    corpus = summarize_fix_benchmark_corpus([
        {"site_id": "b", "benchmark": b},
        {"site_id": "a", "benchmark": a},
    ])
    assert corpus["version"] == ADAPTIVE_FIX_BENCHMARK_CORPUS_VERSION
    assert corpus["site_ids"] == ("a", "b")
    assert corpus["smart_fix_fingerprints_site_scoped"] == 17
    assert corpus["blind_fix_fingerprints_site_scoped"] == 20
    assert corpus["shared_fix_fingerprints_site_scoped"] == 17
    assert corpus["smart_fix_coverage_vs_blind"] == 0.85
    assert corpus["median_site_smart_fix_coverage_vs_blind"] == 0.85
    assert corpus["smart_incremental_fix_fingerprints_vs_standard_site_scoped"] == 11
    assert corpus["smart_incremental_pages_vs_standard"] == 700
    assert corpus["smart_incremental_fix_yield_per_100"] == pytest.approx(1.5714)


def test_corpus_distinguishes_full_and_inventory_limited_sites():
    full = _benchmark("full")
    limited = _benchmark("limited", smart_pages=500, blind_pages=620)
    corpus = summarize_fix_benchmark_corpus([
        {"site_id": "full", "benchmark": full},
        {"site_id": "limited", "benchmark": limited},
    ])
    assert corpus["full_500_vs_1000_sites"] == 1
    assert corpus["inventory_limited_sites"] == 1
    assert corpus["pages_saved_by_smart"] == 620


def test_corpus_partial_high_impact_observation_stays_partial_not_zero():
    observed = _benchmark("observed", high="observed")
    unknown = _benchmark("unknown", high="not_observed")
    corpus = summarize_fix_benchmark_corpus([
        {"site_id": "observed", "benchmark": observed},
        {"site_id": "unknown", "benchmark": unknown},
    ])
    assert corpus["high_impact_evidence_state"] == "partial"
    assert corpus["smart_high_impact_fix_fingerprints_site_scoped"] is None
    assert corpus["smart_high_impact_coverage_vs_blind"] is None


def test_corpus_all_unknown_high_impact_stays_not_observed():
    corpus = summarize_fix_benchmark_corpus([
        {"site_id": "a", "benchmark": _benchmark("a", high="not_observed")},
        {"site_id": "b", "benchmark": _benchmark("b", high="not_observed")},
    ])
    assert corpus["high_impact_evidence_state"] == "not_observed"
    assert corpus["blind_high_impact_fix_fingerprints_site_scoped"] is None


def test_corpus_requires_unique_strict_site_ids():
    benchmark = _benchmark("a")
    with pytest.raises(ValueError, match="site_id_duplicate"):
        summarize_fix_benchmark_corpus([
            {"site_id": "a", "benchmark": benchmark},
            {"site_id": "a", "benchmark": benchmark},
        ])
    with pytest.raises(ValueError, match="site_id_invalid"):
        summarize_fix_benchmark_corpus([{"site_id": " a ", "benchmark": benchmark}])


def test_corpus_rejects_invalid_member_before_aggregation():
    bad = _benchmark("bad")
    bad["standard_150_preserved"] = False
    bad = _rebind(bad)
    with pytest.raises(ValueError, match="benchmark_invalid:bad:standard_150_not_preserved"):
        summarize_fix_benchmark_corpus([{"site_id": "bad", "benchmark": bad}])


def test_zero_blind_fix_denominator_remains_unknown():
    zero = _benchmark(
        "zero",
        standard_fixes=0,
        smart_fixes=0,
        blind_fixes=0,
        shared=0,
        incremental_fixes=0,
        high="not_observed",
    )
    corpus = summarize_fix_benchmark_corpus([{"site_id": "zero", "benchmark": zero}])
    assert corpus["smart_fix_coverage_vs_blind"] is None
    assert corpus["median_site_smart_fix_coverage_vs_blind"] is None


def test_population_fingerprints_are_preserved_per_site():
    a = _benchmark("a")
    corpus = summarize_fix_benchmark_corpus([{"site_id": "a", "benchmark": a}])
    assert corpus["population_fingerprints"] == ((
        "a",
        a["smart_population_fingerprint"],
        a["blind_population_fingerprint"],
        a["binding_fingerprint"],
    ),)


def test_corpus_is_deterministic_and_does_not_mutate_inputs():
    members = [
        {"site_id": "b", "benchmark": _benchmark("b")},
        {"site_id": "a", "benchmark": _benchmark("a")},
    ]
    before = copy.deepcopy(members)
    first = summarize_fix_benchmark_corpus(members)
    second = summarize_fix_benchmark_corpus(list(reversed(members)))
    assert first == second
    assert members == before
    assert first["population_scope_complete"] is False
    assert first["production_budget_authorized"] is False
    assert first["site_fully_understood"] is False
