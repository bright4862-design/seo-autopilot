from copy import deepcopy

from app.adaptive_benchmark_integrity import (
    ADAPTIVE_BENCHMARK_CORPUS_VERSION,
    ADAPTIVE_BENCHMARK_INTEGRITY_VERSION,
    summarize_benchmark_corpus,
    validate_adaptive_benchmark,
)


def _benchmark(*, smart_pages=500, blind_pages=1000, shared=8, smart_only=2, blind_only=2):
    smart_findings = shared + smart_only
    blind_findings = shared + blind_only
    smart_yield = round(smart_findings * 100.0 / smart_pages, 4) if smart_pages else 0.0
    blind_yield = round(blind_findings * 100.0 / blind_pages, 4) if blind_pages else 0.0
    return {
        "version": "adaptive_benchmark_v1",
        "smart_500": {
            "pages_assessed": smart_pages,
            "finding_fingerprints": smart_findings,
            "finding_yield_per_100": smart_yield,
            "template_keys": min(5, smart_pages),
            "families": min(4, smart_pages),
            "route_signatures": min(20, smart_pages),
        },
        "blind_1000": {
            "pages_assessed": blind_pages,
            "finding_fingerprints": blind_findings,
            "finding_yield_per_100": blind_yield,
            "template_keys": min(5, blind_pages),
            "families": min(4, blind_pages),
            "route_signatures": min(20, blind_pages),
        },
        "smart_finding_coverage_vs_blind": round(shared / blind_findings, 4) if blind_findings else None,
        "smart_efficiency_vs_blind": round(smart_yield / blind_yield, 4) if blind_yield else None,
        "finding_comparison_state": "observed" if blind_findings else "no_blind_findings",
        "shared_finding_fingerprints": shared,
        "smart_only_finding_fingerprints": smart_only,
        "blind_only_finding_fingerprints": blind_only,
        "pages_saved_by_smart": blind_pages - smart_pages,
    }


def test_valid_benchmark_passes_integrity():
    assert validate_adaptive_benchmark(_benchmark()) == {
        "version": ADAPTIVE_BENCHMARK_INTEGRITY_VERSION,
        "valid": True,
        "reason": "benchmark_integrity_verified",
    }


def test_benchmark_integrity_rejects_forged_pages_saved():
    result = _benchmark()
    result["pages_saved_by_smart"] = 999
    integrity = validate_adaptive_benchmark(result)
    assert integrity["valid"] is False
    assert integrity["reason"] == "pages_saved_mismatch"


def test_benchmark_integrity_rejects_forged_finding_partition():
    result = _benchmark()
    result["smart_only_finding_fingerprints"] += 1
    integrity = validate_adaptive_benchmark(result)
    assert integrity["valid"] is False
    assert integrity["reason"] == "smart_finding_partition_mismatch"


def test_benchmark_integrity_rejects_forged_coverage_ratio():
    result = _benchmark()
    result["smart_finding_coverage_vs_blind"] = 1.0
    integrity = validate_adaptive_benchmark(result)
    assert integrity["valid"] is False
    assert integrity["reason"] == "finding_coverage_ratio_mismatch"


def test_benchmark_integrity_rejects_non_finite_or_boolean_metrics():
    result = _benchmark()
    result["smart_500"]["finding_yield_per_100"] = float("nan")
    assert validate_adaptive_benchmark(result)["reason"] == "smart_500_invalid_finding_yield"

    result = _benchmark()
    result["blind_1000"]["pages_assessed"] = True
    assert validate_adaptive_benchmark(result)["reason"] == "blind_1000_invalid_count"


def test_benchmark_integrity_preserves_no_blind_findings_unknown_ratios():
    result = _benchmark(shared=0, smart_only=3, blind_only=0)
    result["smart_finding_coverage_vs_blind"] = None
    result["smart_efficiency_vs_blind"] = None
    result["finding_comparison_state"] = "no_blind_findings"
    integrity = validate_adaptive_benchmark(result)
    assert integrity["valid"] is True


def test_benchmark_integrity_does_not_mutate_input():
    result = _benchmark()
    original = deepcopy(result)
    validate_adaptive_benchmark(result)
    assert result == original


def test_corpus_summary_is_deterministic_and_uses_site_scoped_totals():
    first = _benchmark(shared=8, smart_only=2, blind_only=2)
    second = _benchmark(smart_pages=400, blind_pages=700, shared=3, smart_only=1, blind_only=2)
    summary = summarize_benchmark_corpus({"z-site": second, "a-site": first})
    assert summary["version"] == ADAPTIVE_BENCHMARK_CORPUS_VERSION
    assert summary["valid"] is True
    assert summary["site_ids"] == ("a-site", "z-site")
    assert summary["site_count"] == 2
    assert summary["full_500_vs_1000_sites"] == 1
    assert summary["inventory_limited_sites"] == 1
    assert summary["smart_pages_assessed"] == 900
    assert summary["blind_pages_assessed"] == 1700
    assert summary["pages_saved_by_smart"] == 800
    assert summary["shared_site_scoped_finding_fingerprints"] == 11
    assert summary["blind_site_scoped_finding_fingerprints"] == 15
    assert summary["smart_finding_coverage_vs_blind"] == round(11 / 15, 4)


def test_corpus_summary_fails_closed_when_any_member_is_invalid():
    valid = _benchmark()
    invalid = _benchmark()
    invalid["smart_finding_coverage_vs_blind"] = 99.0
    summary = summarize_benchmark_corpus({"valid": valid, "broken": invalid})
    assert summary["valid"] is False
    assert summary["state"] == "invalid_benchmark"
    assert summary["invalid_sites"] == (("broken", "finding_coverage_ratio_mismatch"),)


def test_corpus_summary_requires_evidence_and_keeps_zero_blind_yield_unknown():
    assert summarize_benchmark_corpus({}) == {
        "version": ADAPTIVE_BENCHMARK_CORPUS_VERSION,
        "state": "insufficient_evidence",
        "valid": False,
        "reason": "no_benchmarks",
        "site_count": 0,
    }

    no_blind = _benchmark(smart_pages=200, blind_pages=400, shared=0, smart_only=1, blind_only=0)
    no_blind["smart_finding_coverage_vs_blind"] = None
    no_blind["smart_efficiency_vs_blind"] = None
    no_blind["finding_comparison_state"] = "no_blind_findings"
    summary = summarize_benchmark_corpus({"site": no_blind})
    assert summary["valid"] is True
    assert summary["smart_finding_coverage_vs_blind"] is None
    assert summary["smart_efficiency_vs_blind"] is None
    assert summary["median_site_finding_coverage_vs_blind"] is None


def test_corpus_summary_rejects_ambiguous_site_identity():
    result = _benchmark()
    summary = summarize_benchmark_corpus({"": result})
    assert summary["valid"] is False
    assert summary["state"] == "invalid_benchmark"
    assert summary["reason"] == "invalid_site_identity"

    summary = summarize_benchmark_corpus({1: result})
    assert summary["valid"] is False
    assert summary["reason"] == "invalid_site_identity"
