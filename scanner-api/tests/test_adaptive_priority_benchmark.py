from copy import deepcopy

from app.adaptive_priority_benchmark import (
    ADAPTIVE_PRIORITY_BENCHMARK_VERSION,
    ADAPTIVE_PRIORITY_CORPUS_VERSION,
    build_priority_page_benchmark,
    summarize_priority_benchmark_corpus,
    validate_priority_page_benchmark,
)


def _result():
    return build_priority_page_benchmark(
        ["https://x.test/a", "https://x.test/b", "https://x.test/outside"],
        ["https://x.test/a", "https://x.test/b", "https://x.test/c", "https://x.test/d"],
        important_urls=["https://x.test/a", "https://x.test/c", "https://x.test/outside"],
        high_value_urls=["https://x.test/a", "https://x.test/c"],
    )


def test_priority_benchmark_measures_reference_coverage_without_smart_only_inflation():
    result = _result()
    assert result["version"] == ADAPTIVE_PRIORITY_BENCHMARK_VERSION
    assert result["valid"] is True
    assert result["important_reference_pages"] == 2
    assert result["important_reference_covered_by_smart"] == 1
    assert result["important_coverage_vs_blind"] == 0.5
    assert result["smart_only_important_pages"] == 1
    assert result["high_value_reference_pages"] == 2
    assert result["high_value_reference_covered_by_smart"] == 1
    assert result["high_value_coverage_vs_blind"] == 0.5
    assert result["population_scope_complete"] is False


def test_priority_benchmark_keeps_zero_reference_denominators_unknown():
    result = build_priority_page_benchmark(
        ["https://x.test/a"],
        ["https://x.test/b"],
        important_urls=["https://x.test/outside"],
    )
    assert result["state"] == "no_reference_priority_pages"
    assert result["important_coverage_vs_blind"] is None
    assert result["high_value_coverage_vs_blind"] is None


def test_priority_benchmark_preserves_exact_url_identity_semantics():
    result = build_priority_page_benchmark(
        ["https://x.test/X", "https://x.test/x/"],
        ["https://x.test/x", "https://x.test/x/", "https://x.test/X"],
        important_urls=["https://x.test/x", "https://x.test/x/", "https://x.test/X"],
    )
    assert result["important_reference_pages"] == 3
    assert result["important_reference_covered_by_smart"] == 2
    assert result["important_coverage_vs_blind"] == round(2 / 3, 4)


def test_priority_benchmark_rejects_ambiguous_or_duplicate_identities():
    bad = build_priority_page_benchmark(["https://x.test/a", "https://x.test/a"], [], important_urls=[])
    assert bad["valid"] is False
    assert bad["reason"] == "smart_selected_duplicate_identity"

    bad = build_priority_page_benchmark([" https://x.test/a"], [], important_urls=[])
    assert bad["valid"] is False
    assert bad["reason"] == "smart_selected_invalid_identity"

    bad = build_priority_page_benchmark("https://x.test/a", [], important_urls=[])
    assert bad["valid"] is False
    assert bad["reason"] == "smart_selected_not_sequence"


def test_priority_benchmark_enforces_smart_and_blind_caps():
    smart = [f"https://x.test/s/{i}" for i in range(501)]
    result = build_priority_page_benchmark(smart, [], important_urls=[])
    assert result["valid"] is False
    assert result["reason"] == "smart_page_cap_exceeded"

    blind = [f"https://x.test/b/{i}" for i in range(1001)]
    result = build_priority_page_benchmark([], blind, important_urls=[])
    assert result["valid"] is False
    assert result["reason"] == "blind_page_cap_exceeded"


def test_priority_benchmark_validator_accepts_builder_output_and_does_not_mutate():
    result = _result()
    original = deepcopy(result)
    assert validate_priority_page_benchmark(result) == {
        "version": ADAPTIVE_PRIORITY_BENCHMARK_VERSION,
        "valid": True,
        "reason": "priority_benchmark_integrity_verified",
    }
    assert result == original


def test_priority_benchmark_validator_rejects_forged_ratio_and_partition():
    result = _result()
    result["important_coverage_vs_blind"] = 1.0
    assert validate_priority_page_benchmark(result)["reason"] == "important_coverage_ratio_mismatch"

    result = _result()
    result["smart_pages_outside_blind"] += 1
    assert validate_priority_page_benchmark(result)["reason"] == "smart_partition_mismatch"


def test_priority_benchmark_validator_rejects_sitewide_completeness_claim():
    result = _result()
    result["population_scope_complete"] = True
    integrity = validate_priority_page_benchmark(result)
    assert integrity["valid"] is False
    assert integrity["reason"] == "population_scope_claim_invalid"


def test_priority_corpus_is_deterministic_and_uses_weighted_reference_coverage():
    first = build_priority_page_benchmark(
        [f"https://a.test/{i}" for i in range(500)],
        [f"https://a.test/{i}" for i in range(1000)],
        important_urls=["https://a.test/0", "https://a.test/700"],
        high_value_urls=["https://a.test/0"],
    )
    second = build_priority_page_benchmark(
        ["https://b.test/0"],
        ["https://b.test/0", "https://b.test/1"],
        important_urls=["https://b.test/0", "https://b.test/1"],
        high_value_urls=["https://b.test/1"],
    )
    summary = summarize_priority_benchmark_corpus({"z-site": second, "a-site": first})
    assert summary["version"] == ADAPTIVE_PRIORITY_CORPUS_VERSION
    assert summary["valid"] is True
    assert summary["site_ids"] == ("a-site", "z-site")
    assert summary["full_500_vs_1000_sites"] == 1
    assert summary["inventory_limited_sites"] == 1
    assert summary["important_reference_pages"] == 4
    assert summary["important_reference_covered_by_smart"] == 2
    assert summary["important_coverage_vs_blind"] == 0.5
    assert summary["high_value_reference_pages"] == 2
    assert summary["high_value_reference_covered_by_smart"] == 1
    assert summary["high_value_coverage_vs_blind"] == 0.5


def test_priority_corpus_fails_closed_on_invalid_member_or_site_identity():
    invalid = _result()
    invalid["high_value_coverage_vs_blind"] = 99.0
    summary = summarize_priority_benchmark_corpus({"site": invalid})
    assert summary["valid"] is False
    assert summary["state"] == "invalid_benchmark"
    assert summary["invalid_sites"] == (("site", "high_value_coverage_ratio_mismatch"),)

    summary = summarize_priority_benchmark_corpus({"": _result()})
    assert summary["valid"] is False
    assert summary["reason"] == "invalid_site_identity"


def test_priority_corpus_requires_evidence():
    assert summarize_priority_benchmark_corpus({}) == {
        "version": ADAPTIVE_PRIORITY_CORPUS_VERSION,
        "state": "insufficient_evidence",
        "valid": False,
        "reason": "no_benchmarks",
        "site_count": 0,
    }
