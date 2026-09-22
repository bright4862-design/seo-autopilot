"""Population-bound shadow decision for Smart-500 vs blind-1000 evidence.

This module combines Lane-A's population-bound benchmark corpus with its strict
marginal-gap corpus. It is pure, deterministic, and engineering-only: a positive
result names Smart 500 a *candidate* but never authorizes production budgets or
claims that a site is fully understood.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from .adaptive_benchmark_acceptance import evaluate_smart_500_corpus
from .adaptive_marginal_corpus import validate_marginal_gap_corpus

ADAPTIVE_SMART_500_DECISION_VERSION = "adaptive_smart_500_decision_v1"
ADAPTIVE_BENCHMARK_BUNDLE_CORPUS_VERSION = "adaptive_benchmark_bundle_corpus_v1"
ADAPTIVE_MARGINAL_CORPUS_VERSION = "adaptive_marginal_gap_corpus_v1"

DEFAULT_MAX_BLIND_TAIL_FINDING_YIELD_PER_100 = 1.0
DEFAULT_MAX_MEDIAN_SITE_BLIND_TAIL_FINDING_YIELD_PER_100 = 1.0


def _result(decision: str, reason: str, **extra: Any) -> dict[str, Any]:
    return {
        "version": ADAPTIVE_SMART_500_DECISION_VERSION,
        "decision": decision,
        "reason": reason,
        "production_budget_authorized": False,
        "site_fully_understood": False,
        **extra,
    }


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _nonnegative_finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number) or number < 0.0:
        return None
    return number


def _bounded_ratio(value: Any) -> float | None:
    number = _nonnegative_finite(value)
    if number is None or number > 1.0:
        return None
    return number


def _threshold(value: Any, *, field: str) -> tuple[float | None, str | None]:
    number = _nonnegative_finite(value)
    if number is None:
        return None, f"invalid_threshold:{field}"
    return number, None


def _site_ids(value: Any) -> tuple[str, ...] | None:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
        return None
    materialized = tuple(value)
    if any(not isinstance(site_id, str) or not site_id or site_id.strip() != site_id for site_id in materialized):
        return None
    if len(set(materialized)) != len(materialized) or materialized != tuple(sorted(materialized)):
        return None
    return materialized


def _bundle_fingerprints(value: Any, expected_site_ids: tuple[str, ...]) -> dict[str, tuple[str, str]] | None:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
        return None
    entries = tuple(value)
    if len(entries) != len(expected_site_ids):
        return None
    result: dict[str, tuple[str, str]] = {}
    for entry in entries:
        if isinstance(entry, (str, bytes, Mapping)) or not isinstance(entry, Sequence):
            return None
        parts = tuple(entry)
        if len(parts) != 3:
            return None
        site_id, smart_fp, blind_fp = parts
        if not all(isinstance(part, str) and part for part in parts):
            return None
        if site_id in result:
            return None
        result[site_id] = (smart_fp, blind_fp)
    if tuple(sorted(result)) != expected_site_ids:
        return None
    return result


def _marginal_fingerprints(value: Any, expected_site_ids: tuple[str, ...]) -> dict[str, tuple[str, str]] | None:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
        return None
    entries = tuple(value)
    if len(entries) != len(expected_site_ids):
        return None
    result: dict[str, tuple[str, str]] = {}
    for member in entries:
        if not isinstance(member, Mapping):
            return None
        site_id = member.get("site_id")
        smart_fp = member.get("smart_500_population_fingerprint")
        blind_fp = member.get("blind_1000_population_fingerprint")
        if not isinstance(site_id, str) or not site_id or site_id.strip() != site_id:
            return None
        if not isinstance(smart_fp, str) or not smart_fp or not isinstance(blind_fp, str) or not blind_fp:
            return None
        if site_id in result:
            return None
        result[site_id] = (smart_fp, blind_fp)
    if tuple(sorted(result)) != expected_site_ids:
        return None
    return result


def evaluate_population_bound_smart_500(
    benchmark_corpus: Mapping[str, Any] | Any,
    marginal_corpus: Mapping[str, Any] | Any,
    *,
    max_blind_tail_finding_yield_per_100: float = DEFAULT_MAX_BLIND_TAIL_FINDING_YIELD_PER_100,
    max_median_site_blind_tail_finding_yield_per_100: float = DEFAULT_MAX_MEDIAN_SITE_BLIND_TAIL_FINDING_YIELD_PER_100,
    require_high_impact_observed: bool = True,
    **coverage_thresholds: Any,
) -> dict[str, Any]:
    """Combine coverage and marginal-yield evidence for a shadow Smart-500 decision.

    The two corpus artifacts must describe the same ordered site population and the
    same exact Smart-500 / blind-1000 URL populations per site. Coverage acceptance
    alone is insufficient: the blind 500->1000 tail must also have acceptably low
    incremental finding yield, and high-impact evidence must be fully observed by
    default. Unknown or ambiguous population/evidence identity fails closed.
    """
    if not isinstance(benchmark_corpus, Mapping):
        return _result("insufficient_evidence", "benchmark_corpus_not_mapping")
    if not isinstance(marginal_corpus, Mapping):
        return _result("insufficient_evidence", "marginal_corpus_not_mapping")
    if benchmark_corpus.get("version") != ADAPTIVE_BENCHMARK_BUNDLE_CORPUS_VERSION:
        return _result("insufficient_evidence", "benchmark_corpus_version_mismatch")
    if marginal_corpus.get("version") != ADAPTIVE_MARGINAL_CORPUS_VERSION:
        return _result("insufficient_evidence", "marginal_corpus_version_mismatch")

    marginal_integrity = validate_marginal_gap_corpus(marginal_corpus)
    if marginal_integrity.get("valid") is not True:
        return _result(
            "insufficient_evidence",
            f"marginal_corpus_integrity_failed:{marginal_integrity.get('reason') or 'invalid'}",
        )

    coverage = evaluate_smart_500_corpus(benchmark_corpus, **coverage_thresholds)
    coverage_decision = coverage.get("decision")
    if coverage_decision == "insufficient_evidence":
        return _result("insufficient_evidence", "coverage_evidence_insufficient", coverage_acceptance=coverage)
    if coverage_decision != "smart_500_candidate":
        return _result(
            "blind_1000_reference_retained",
            "coverage_acceptance_not_met",
            coverage_acceptance=coverage,
        )

    max_tail_yield, error = _threshold(
        max_blind_tail_finding_yield_per_100,
        field="max_blind_tail_finding_yield_per_100",
    )
    if error:
        return _result("insufficient_evidence", error)
    max_median_tail_yield, error = _threshold(
        max_median_site_blind_tail_finding_yield_per_100,
        field="max_median_site_blind_tail_finding_yield_per_100",
    )
    if error:
        return _result("insufficient_evidence", error)
    if not isinstance(require_high_impact_observed, bool):
        return _result("insufficient_evidence", "invalid_threshold:require_high_impact_observed")
    assert max_tail_yield is not None and max_median_tail_yield is not None

    benchmark_site_ids = _site_ids(benchmark_corpus.get("site_ids"))
    marginal_site_ids = _site_ids(marginal_corpus.get("site_ids"))
    if benchmark_site_ids is None or marginal_site_ids is None or benchmark_site_ids != marginal_site_ids:
        return _result("insufficient_evidence", "site_population_identity_mismatch")

    benchmark_fingerprints = _bundle_fingerprints(
        benchmark_corpus.get("population_fingerprints"), benchmark_site_ids
    )
    marginal_fingerprints = _marginal_fingerprints(
        marginal_corpus.get("sites"), marginal_site_ids
    )
    if benchmark_fingerprints is None or marginal_fingerprints is None:
        return _result("insufficient_evidence", "population_fingerprint_set_invalid")
    if benchmark_fingerprints != marginal_fingerprints:
        return _result("insufficient_evidence", "population_fingerprint_mismatch")

    benchmark_full_sites = _nonnegative_int(benchmark_corpus.get("full_500_vs_1000_sites"))
    marginal_full_sites = _nonnegative_int(marginal_corpus.get("full_500_vs_1000_sites"))
    if benchmark_full_sites is None or marginal_full_sites is None or benchmark_full_sites != marginal_full_sites:
        return _result("insufficient_evidence", "full_comparison_site_count_mismatch")

    benchmark_coverage = _bounded_ratio(benchmark_corpus.get("smart_finding_coverage_vs_blind"))
    marginal_coverage = _bounded_ratio(marginal_corpus.get("full_smart_500_reference_finding_coverage"))
    if benchmark_coverage is None or marginal_coverage is None:
        return _result("insufficient_evidence", "cross_corpus_finding_coverage_missing")
    if benchmark_coverage != marginal_coverage:
        return _result("insufficient_evidence", "cross_corpus_finding_coverage_mismatch")

    tail_pages = _nonnegative_int(marginal_corpus.get("full_blind_tail_pages"))
    tail_findings = _nonnegative_int(marginal_corpus.get("full_blind_tail_new_findings"))
    tail_yield = _nonnegative_finite(marginal_corpus.get("full_blind_tail_new_finding_yield_per_100"))
    median_tail_yield = _nonnegative_finite(
        marginal_corpus.get("median_full_site_blind_tail_finding_yield_per_100")
    )
    if None in (tail_pages, tail_findings, tail_yield, median_tail_yield):
        return _result("insufficient_evidence", "marginal_tail_metric_missing")
    assert tail_pages is not None and tail_findings is not None
    assert tail_yield is not None and median_tail_yield is not None
    if tail_pages <= 0:
        return _result("insufficient_evidence", "no_blind_500_to_1000_tail")

    high_state = marginal_corpus.get("high_impact_evidence_state")
    high_observed_sites = _nonnegative_int(marginal_corpus.get("full_high_impact_observed_sites"))
    high_missed = _nonnegative_int(marginal_corpus.get("full_smart_500_missed_reference_high_impact_findings"))
    high_tail = _nonnegative_int(marginal_corpus.get("full_blind_tail_new_high_impact_findings"))
    if require_high_impact_observed:
        if high_state != "observed" or high_observed_sites != marginal_full_sites:
            return _result("insufficient_evidence", "high_impact_evidence_not_fully_observed")
        if high_missed is None or high_tail is None:
            return _result("insufficient_evidence", "high_impact_metric_missing")

    failed: list[str] = []
    if tail_yield > max_tail_yield:
        failed.append("blind_tail_finding_yield")
    if median_tail_yield > max_median_tail_yield:
        failed.append("median_site_blind_tail_finding_yield")
    if require_high_impact_observed and high_missed is not None and high_missed > 0:
        failed.append("missed_high_impact_findings")
    if require_high_impact_observed and high_tail is not None and high_tail > 0:
        failed.append("blind_tail_high_impact_findings")

    evidence = {
        "coverage_acceptance": coverage,
        "site_ids": benchmark_site_ids,
        "full_comparison_sites": benchmark_full_sites,
        "population_fingerprints": tuple(
            (site_id, *benchmark_fingerprints[site_id]) for site_id in benchmark_site_ids
        ),
        "blind_tail_pages": tail_pages,
        "blind_tail_new_findings": tail_findings,
        "blind_tail_new_finding_yield_per_100": tail_yield,
        "median_site_blind_tail_finding_yield_per_100": median_tail_yield,
        "high_impact_evidence_state": high_state,
        "missed_high_impact_findings": high_missed,
        "blind_tail_new_high_impact_findings": high_tail,
        "thresholds": {
            "max_blind_tail_finding_yield_per_100": max_tail_yield,
            "max_median_site_blind_tail_finding_yield_per_100": max_median_tail_yield,
            "require_high_impact_observed": require_high_impact_observed,
        },
    }
    if failed:
        return _result(
            "blind_1000_reference_retained",
            "marginal_acceptance_thresholds_not_met",
            failed_thresholds=tuple(failed),
            **evidence,
        )
    return _result(
        "smart_500_candidate",
        "population_bound_coverage_and_marginal_thresholds_met",
        failed_thresholds=(),
        **evidence,
    )
