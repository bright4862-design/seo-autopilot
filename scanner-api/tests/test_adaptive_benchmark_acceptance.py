from app.adaptive_benchmark_acceptance import (
    ADAPTIVE_BENCHMARK_ACCEPTANCE_VERSION,
    evaluate_smart_500_corpus,
)


def _corpus(**overrides):
    result = {
        "version": "adaptive_benchmark_bundle_corpus_v1",
        "state": "observed",
        "valid": True,
        "population_scope_complete": False,
        "site_count": 12,
        "site_ids": tuple(f"site-{i:02d}" for i in range(12)),
        "full_500_vs_1000_sites": 10,
        "inventory_limited_sites": 2,
        "smart_pages_assessed": 5600,
        "blind_pages_assessed": 10600,
        "pages_saved_by_smart": 5000,
        "smart_finding_coverage_vs_blind": 0.97,
        "median_site_finding_coverage_vs_blind": 0.95,
        "important_coverage_vs_blind": 0.98,
        "high_value_coverage_vs_blind": 0.99,
    }
    result.update(overrides)
    return result


def test_accepts_only_as_shadow_candidate_and_never_authorizes_budget():
    result = evaluate_smart_500_corpus(_corpus())
    assert result["version"] == ADAPTIVE_BENCHMARK_ACCEPTANCE_VERSION
    assert result["decision"] == "smart_500_candidate"
    assert result["production_budget_authorized"] is False
    assert result["site_fully_understood"] is False
    assert result["failed_thresholds"] == ()
    assert result["pages_saved_by_smart"] == 5000


def test_retains_blind_reference_when_aggregate_finding_coverage_is_too_low():
    result = evaluate_smart_500_corpus(_corpus(smart_finding_coverage_vs_blind=0.90))
    assert result["decision"] == "blind_1000_reference_retained"
    assert result["failed_thresholds"] == ("finding_coverage",)


def test_retains_blind_reference_when_median_site_coverage_hides_weak_sites():
    result = evaluate_smart_500_corpus(_corpus(median_site_finding_coverage_vs_blind=0.80))
    assert result["decision"] == "blind_1000_reference_retained"
    assert result["failed_thresholds"] == ("median_site_finding_coverage",)


def test_retains_blind_reference_when_important_page_coverage_is_too_low():
    result = evaluate_smart_500_corpus(_corpus(important_coverage_vs_blind=0.80))
    assert result["decision"] == "blind_1000_reference_retained"
    assert result["failed_thresholds"] == ("important_page_coverage",)


def test_retains_blind_reference_when_high_value_page_coverage_is_too_low():
    result = evaluate_smart_500_corpus(_corpus(high_value_coverage_vs_blind=0.80))
    assert result["decision"] == "blind_1000_reference_retained"
    assert result["failed_thresholds"] == ("high_value_page_coverage",)


def test_requires_enough_full_500_vs_1000_sites():
    result = evaluate_smart_500_corpus(
        _corpus(site_count=12, full_500_vs_1000_sites=9, inventory_limited_sites=3)
    )
    assert result["decision"] == "insufficient_evidence"
    assert result["reason"] == "too_few_full_500_vs_1000_sites"


def test_rejects_missing_coverage_instead_of_treating_unknown_as_zero():
    result = evaluate_smart_500_corpus(_corpus(high_value_coverage_vs_blind=None))
    assert result["decision"] == "insufficient_evidence"
    assert result["reason"] == "required_coverage_metric_missing:high_value_coverage_vs_blind"


def test_rejects_forged_page_savings():
    result = evaluate_smart_500_corpus(_corpus(pages_saved_by_smart=4999))
    assert result["decision"] == "insufficient_evidence"
    assert result["reason"] == "page_population_count_mismatch"


def test_rejects_site_partition_mismatch():
    result = evaluate_smart_500_corpus(_corpus(inventory_limited_sites=1))
    assert result["decision"] == "insufficient_evidence"
    assert result["reason"] == "site_population_count_mismatch"


def test_rejects_missing_duplicate_or_unsorted_site_identity_population():
    bad_values = (
        ("site-00",),
        tuple(["site-00"] * 12),
        tuple(reversed(tuple(f"site-{i:02d}" for i in range(12)))),
    )
    for site_ids in bad_values:
        result = evaluate_smart_500_corpus(_corpus(site_ids=site_ids))
        assert result["decision"] == "insufficient_evidence"
        assert result["reason"] == "site_identity_population_mismatch"


def test_rejects_nonfinite_or_out_of_range_metrics():
    for bad in (float("nan"), float("inf"), -0.1, 1.1, True):
        result = evaluate_smart_500_corpus(_corpus(smart_finding_coverage_vs_blind=bad))
        assert result["decision"] == "insufficient_evidence"
        assert result["reason"] == "required_coverage_metric_missing:smart_finding_coverage_vs_blind"


def test_rejects_invalid_thresholds_instead_of_silently_clamping():
    result = evaluate_smart_500_corpus(_corpus(), min_finding_coverage=1.5)
    assert result["decision"] == "insufficient_evidence"
    assert result["reason"] == "invalid_threshold:min_finding_coverage"

    result = evaluate_smart_500_corpus(_corpus(), min_full_comparison_sites=True)
    assert result["decision"] == "insufficient_evidence"
    assert result["reason"] == "invalid_threshold:min_full_comparison_sites"


def test_input_mapping_is_not_mutated_and_result_is_deterministic():
    corpus = _corpus()
    original = dict(corpus)
    first = evaluate_smart_500_corpus(corpus)
    second = evaluate_smart_500_corpus(corpus)
    assert corpus == original
    assert first == second
