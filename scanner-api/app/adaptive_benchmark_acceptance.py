"""Shadow-only acceptance policy for Smart-500 vs blind-1000 corpus evidence.

This module evaluates engineering benchmark summaries only. It never authorizes a
production crawl budget, never claims whole-site completeness, and performs no
network or persistence work.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

ADAPTIVE_BENCHMARK_ACCEPTANCE_VERSION = "adaptive_benchmark_acceptance_v1"
ADAPTIVE_BENCHMARK_BUNDLE_CORPUS_VERSION = "adaptive_benchmark_bundle_corpus_v1"

DEFAULT_MIN_FULL_COMPARISON_SITES = 10
DEFAULT_MIN_FINDING_COVERAGE = 0.95
DEFAULT_MIN_MEDIAN_SITE_FINDING_COVERAGE = 0.90
DEFAULT_MIN_IMPORTANT_COVERAGE = 0.95
DEFAULT_MIN_HIGH_VALUE_COVERAGE = 0.95


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _bounded_ratio(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number) or number < 0.0 or number > 1.0:
        return None
    return number


def _threshold_ratio(value: Any, *, field: str) -> tuple[float | None, str | None]:
    ratio = _bounded_ratio(value)
    if ratio is None:
        return None, f"invalid_threshold:{field}"
    return ratio, None


def _valid_site_ids(value: Any, expected_count: int) -> bool:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
        return False
    materialized = tuple(value)
    if len(materialized) != expected_count:
        return False
    if any(not isinstance(site_id, str) or not site_id.strip() for site_id in materialized):
        return False
    return len(set(materialized)) == len(materialized) and materialized == tuple(sorted(materialized))


def _result(decision: str, reason: str, **extra: Any) -> dict[str, Any]:
    return {
        "version": ADAPTIVE_BENCHMARK_ACCEPTANCE_VERSION,
        "decision": decision,
        "reason": reason,
        "production_budget_authorized": False,
        "site_fully_understood": False,
        **extra,
    }


def evaluate_smart_500_corpus(
    corpus: Mapping[str, Any] | Any,
    *,
    min_full_comparison_sites: int = DEFAULT_MIN_FULL_COMPARISON_SITES,
    min_finding_coverage: float = DEFAULT_MIN_FINDING_COVERAGE,
    min_median_site_finding_coverage: float = DEFAULT_MIN_MEDIAN_SITE_FINDING_COVERAGE,
    min_important_coverage: float = DEFAULT_MIN_IMPORTANT_COVERAGE,
    min_high_value_coverage: float = DEFAULT_MIN_HIGH_VALUE_COVERAGE,
) -> dict[str, Any]:
    """Evaluate whether Smart 500 is a *shadow* rollout candidate.

    The input must be the population-bound corpus summary from Lane A. A positive
    result is deliberately named ``smart_500_candidate`` rather than "approved".
    The serialized integrator still owns real crawl budgets and full regression /
    corpus acceptance before any customer-visible change.
    """
    if not isinstance(corpus, Mapping):
        return _result("insufficient_evidence", "corpus_not_mapping")
    if corpus.get("version") != ADAPTIVE_BENCHMARK_BUNDLE_CORPUS_VERSION:
        return _result("insufficient_evidence", "corpus_version_mismatch")
    if corpus.get("valid") is not True or corpus.get("state") != "observed":
        return _result("insufficient_evidence", "corpus_not_integrity_verified")
    if corpus.get("population_scope_complete") is not False:
        return _result("insufficient_evidence", "population_scope_claim_invalid")

    site_count = _nonnegative_int(corpus.get("site_count"))
    full_sites = _nonnegative_int(corpus.get("full_500_vs_1000_sites"))
    limited_sites = _nonnegative_int(corpus.get("inventory_limited_sites"))
    smart_pages = _nonnegative_int(corpus.get("smart_pages_assessed"))
    blind_pages = _nonnegative_int(corpus.get("blind_pages_assessed"))
    pages_saved = _nonnegative_int(corpus.get("pages_saved_by_smart"))
    if None in (site_count, full_sites, limited_sites, smart_pages, blind_pages, pages_saved):
        return _result("insufficient_evidence", "invalid_corpus_count")
    assert site_count is not None
    assert full_sites is not None
    assert limited_sites is not None
    assert smart_pages is not None
    assert blind_pages is not None
    assert pages_saved is not None

    if full_sites + limited_sites != site_count:
        return _result("insufficient_evidence", "site_population_count_mismatch")
    if not _valid_site_ids(corpus.get("site_ids"), site_count):
        return _result("insufficient_evidence", "site_identity_population_mismatch")
    if smart_pages > blind_pages or pages_saved != blind_pages - smart_pages:
        return _result("insufficient_evidence", "page_population_count_mismatch")

    if isinstance(min_full_comparison_sites, bool) or not isinstance(min_full_comparison_sites, int) or min_full_comparison_sites <= 0:
        return _result("insufficient_evidence", "invalid_threshold:min_full_comparison_sites")
    threshold_values: dict[str, float] = {}
    for field, raw in (
        ("min_finding_coverage", min_finding_coverage),
        ("min_median_site_finding_coverage", min_median_site_finding_coverage),
        ("min_important_coverage", min_important_coverage),
        ("min_high_value_coverage", min_high_value_coverage),
    ):
        normalized, error = _threshold_ratio(raw, field=field)
        if error:
            return _result("insufficient_evidence", error)
        assert normalized is not None
        threshold_values[field] = normalized

    metrics: dict[str, float] = {}
    for field in (
        "smart_finding_coverage_vs_blind",
        "median_site_finding_coverage_vs_blind",
        "important_coverage_vs_blind",
        "high_value_coverage_vs_blind",
    ):
        normalized = _bounded_ratio(corpus.get(field))
        if normalized is None:
            return _result("insufficient_evidence", f"required_coverage_metric_missing:{field}")
        metrics[field] = normalized

    if full_sites < min_full_comparison_sites:
        return _result(
            "insufficient_evidence",
            "too_few_full_500_vs_1000_sites",
            full_comparison_sites=full_sites,
            minimum_full_comparison_sites=min_full_comparison_sites,
        )
    if pages_saved <= 0:
        return _result("insufficient_evidence", "no_incremental_reference_pages")

    failed: list[str] = []
    if metrics["smart_finding_coverage_vs_blind"] < threshold_values["min_finding_coverage"]:
        failed.append("finding_coverage")
    if metrics["median_site_finding_coverage_vs_blind"] < threshold_values["min_median_site_finding_coverage"]:
        failed.append("median_site_finding_coverage")
    if metrics["important_coverage_vs_blind"] < threshold_values["min_important_coverage"]:
        failed.append("important_page_coverage")
    if metrics["high_value_coverage_vs_blind"] < threshold_values["min_high_value_coverage"]:
        failed.append("high_value_page_coverage")

    evidence = {
        "full_comparison_sites": full_sites,
        "inventory_limited_sites": limited_sites,
        "smart_pages_assessed": smart_pages,
        "blind_pages_assessed": blind_pages,
        "pages_saved_by_smart": pages_saved,
        **metrics,
        "thresholds": {
            "min_full_comparison_sites": min_full_comparison_sites,
            **threshold_values,
        },
    }
    if failed:
        return _result(
            "blind_1000_reference_retained",
            "shadow_acceptance_thresholds_not_met",
            failed_thresholds=tuple(failed),
            **evidence,
        )
    return _result(
        "smart_500_candidate",
        "shadow_acceptance_thresholds_met",
        failed_thresholds=(),
        **evidence,
    )
