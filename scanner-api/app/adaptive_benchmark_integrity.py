"""Fail-closed validation and corpus summaries for Lane-A benchmark evidence.

The benchmark helper is intentionally an engineering instrument, not a customer
claim. These helpers validate transported benchmark envelopes and aggregate a
corpus without silently accepting forged ratios or mixing invalid site results.
They are pure, deterministic, and perform no network work.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from statistics import median
from typing import Any

from .adaptive_crawl import ADAPTIVE_BENCHMARK_VERSION

ADAPTIVE_BENCHMARK_INTEGRITY_VERSION = "adaptive_benchmark_integrity_v1"
ADAPTIVE_BENCHMARK_CORPUS_VERSION = "adaptive_benchmark_corpus_v1"


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _finite_nonnegative_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return number


def _ratio_matches(actual: Any, expected: float | None) -> bool:
    if expected is None:
        return actual is None
    normalized = _finite_nonnegative_number(actual)
    return normalized is not None and abs(normalized - expected) <= 1e-9


def _validate_summary(name: str, summary: Any, *, page_cap: int) -> str | None:
    if not isinstance(summary, Mapping):
        return f"{name}_not_mapping"

    pages = _nonnegative_int(summary.get("pages_assessed"))
    findings = _nonnegative_int(summary.get("finding_fingerprints"))
    templates = _nonnegative_int(summary.get("template_keys"))
    families = _nonnegative_int(summary.get("families"))
    signatures = _nonnegative_int(summary.get("route_signatures"))
    if None in (pages, findings, templates, families, signatures):
        return f"{name}_invalid_count"
    assert pages is not None
    assert findings is not None
    assert templates is not None
    assert families is not None
    assert signatures is not None

    if pages > page_cap:
        return f"{name}_page_cap_exceeded"
    if any(value > pages for value in (templates, families, signatures)):
        return f"{name}_coverage_count_exceeds_pages"
    if pages == 0 and findings > 0:
        return f"{name}_findings_without_pages"

    observed_yield = _finite_nonnegative_number(summary.get("finding_yield_per_100"))
    if observed_yield is None:
        return f"{name}_invalid_finding_yield"
    expected_yield = round(findings * 100.0 / pages, 4) if pages else 0.0
    if abs(observed_yield - expected_yield) > 1e-9:
        return f"{name}_finding_yield_mismatch"
    return None


def validate_adaptive_benchmark(result: Mapping[str, Any] | Any) -> dict[str, Any]:
    """Validate one smart-500-vs-blind-1000 result before it is compared or stored."""
    if not isinstance(result, Mapping):
        return {
            "version": ADAPTIVE_BENCHMARK_INTEGRITY_VERSION,
            "valid": False,
            "reason": "benchmark_not_mapping",
        }
    if result.get("version") != ADAPTIVE_BENCHMARK_VERSION:
        return {
            "version": ADAPTIVE_BENCHMARK_INTEGRITY_VERSION,
            "valid": False,
            "reason": "benchmark_version_mismatch",
        }

    for name, cap in (("smart_500", 500), ("blind_1000", 1000)):
        reason = _validate_summary(name, result.get(name), page_cap=cap)
        if reason:
            return {
                "version": ADAPTIVE_BENCHMARK_INTEGRITY_VERSION,
                "valid": False,
                "reason": reason,
            }

    smart = result["smart_500"]
    blind = result["blind_1000"]
    smart_pages = int(smart["pages_assessed"])
    blind_pages = int(blind["pages_assessed"])
    smart_findings = int(smart["finding_fingerprints"])
    blind_findings = int(blind["finding_fingerprints"])
    if smart_pages > blind_pages:
        return {
            "version": ADAPTIVE_BENCHMARK_INTEGRITY_VERSION,
            "valid": False,
            "reason": "smart_pages_exceed_blind_pages",
        }

    shared = _nonnegative_int(result.get("shared_finding_fingerprints"))
    smart_only = _nonnegative_int(result.get("smart_only_finding_fingerprints"))
    blind_only = _nonnegative_int(result.get("blind_only_finding_fingerprints"))
    pages_saved = _nonnegative_int(result.get("pages_saved_by_smart"))
    if None in (shared, smart_only, blind_only, pages_saved):
        return {
            "version": ADAPTIVE_BENCHMARK_INTEGRITY_VERSION,
            "valid": False,
            "reason": "invalid_comparison_count",
        }
    assert shared is not None
    assert smart_only is not None
    assert blind_only is not None
    assert pages_saved is not None

    if shared + smart_only != smart_findings:
        return {
            "version": ADAPTIVE_BENCHMARK_INTEGRITY_VERSION,
            "valid": False,
            "reason": "smart_finding_partition_mismatch",
        }
    if shared + blind_only != blind_findings:
        return {
            "version": ADAPTIVE_BENCHMARK_INTEGRITY_VERSION,
            "valid": False,
            "reason": "blind_finding_partition_mismatch",
        }
    if pages_saved != blind_pages - smart_pages:
        return {
            "version": ADAPTIVE_BENCHMARK_INTEGRITY_VERSION,
            "valid": False,
            "reason": "pages_saved_mismatch",
        }

    state = result.get("finding_comparison_state")
    if blind_findings == 0:
        if state != "no_blind_findings":
            return {
                "version": ADAPTIVE_BENCHMARK_INTEGRITY_VERSION,
                "valid": False,
                "reason": "comparison_state_mismatch",
            }
        if result.get("smart_finding_coverage_vs_blind") is not None:
            return {
                "version": ADAPTIVE_BENCHMARK_INTEGRITY_VERSION,
                "valid": False,
                "reason": "coverage_without_blind_findings",
            }
        if result.get("smart_efficiency_vs_blind") is not None:
            return {
                "version": ADAPTIVE_BENCHMARK_INTEGRITY_VERSION,
                "valid": False,
                "reason": "efficiency_without_blind_findings",
            }
    else:
        if state != "observed":
            return {
                "version": ADAPTIVE_BENCHMARK_INTEGRITY_VERSION,
                "valid": False,
                "reason": "comparison_state_mismatch",
            }
        expected_coverage = round(shared / blind_findings, 4)
        if not _ratio_matches(result.get("smart_finding_coverage_vs_blind"), expected_coverage):
            return {
                "version": ADAPTIVE_BENCHMARK_INTEGRITY_VERSION,
                "valid": False,
                "reason": "finding_coverage_ratio_mismatch",
            }

        blind_yield = float(blind["finding_yield_per_100"])
        smart_yield = float(smart["finding_yield_per_100"])
        expected_efficiency = round(smart_yield / blind_yield, 4) if blind_yield > 0 else None
        if not _ratio_matches(result.get("smart_efficiency_vs_blind"), expected_efficiency):
            return {
                "version": ADAPTIVE_BENCHMARK_INTEGRITY_VERSION,
                "valid": False,
                "reason": "finding_efficiency_ratio_mismatch",
            }

    return {
        "version": ADAPTIVE_BENCHMARK_INTEGRITY_VERSION,
        "valid": True,
        "reason": "benchmark_integrity_verified",
    }


def summarize_benchmark_corpus(results_by_site: Mapping[str, Any] | Any) -> dict[str, Any]:
    """Aggregate only integrity-valid site benchmarks into a deterministic corpus summary.

    Counts are site-scoped sums. Fingerprints are not de-duplicated across sites because
    their global identity semantics are not owned by this lane.
    """
    if not isinstance(results_by_site, Mapping) or not results_by_site:
        return {
            "version": ADAPTIVE_BENCHMARK_CORPUS_VERSION,
            "state": "insufficient_evidence",
            "valid": False,
            "reason": "no_benchmarks",
            "site_count": 0,
        }

    ordered_site_ids = tuple(sorted(str(site_id) for site_id in results_by_site))
    normalized_by_id = {str(site_id): value for site_id, value in results_by_site.items()}
    invalid: list[tuple[str, str]] = []
    for site_id in ordered_site_ids:
        integrity = validate_adaptive_benchmark(normalized_by_id[site_id])
        if integrity["valid"] is not True:
            invalid.append((site_id, str(integrity["reason"])))
    if invalid:
        return {
            "version": ADAPTIVE_BENCHMARK_CORPUS_VERSION,
            "state": "invalid_benchmark",
            "valid": False,
            "reason": "member_integrity_failed",
            "site_count": len(ordered_site_ids),
            "invalid_sites": tuple(invalid),
        }

    smart_pages = 0
    blind_pages = 0
    smart_findings = 0
    blind_findings = 0
    shared_findings = 0
    smart_only_findings = 0
    blind_only_findings = 0
    full_comparison_sites = 0
    observed_coverages: list[float] = []

    for site_id in ordered_site_ids:
        result = normalized_by_id[site_id]
        smart = result["smart_500"]
        blind = result["blind_1000"]
        smart_pages += int(smart["pages_assessed"])
        blind_pages += int(blind["pages_assessed"])
        smart_findings += int(smart["finding_fingerprints"])
        blind_findings += int(blind["finding_fingerprints"])
        shared_findings += int(result["shared_finding_fingerprints"])
        smart_only_findings += int(result["smart_only_finding_fingerprints"])
        blind_only_findings += int(result["blind_only_finding_fingerprints"])
        if int(smart["pages_assessed"]) == 500 and int(blind["pages_assessed"]) == 1000:
            full_comparison_sites += 1
        coverage = result.get("smart_finding_coverage_vs_blind")
        if coverage is not None:
            observed_coverages.append(float(coverage))

    smart_yield = round(smart_findings * 100.0 / smart_pages, 4) if smart_pages else 0.0
    blind_yield = round(blind_findings * 100.0 / blind_pages, 4) if blind_pages else 0.0
    corpus_coverage = round(shared_findings / blind_findings, 4) if blind_findings else None
    corpus_efficiency = round(smart_yield / blind_yield, 4) if blind_yield > 0 else None

    return {
        "version": ADAPTIVE_BENCHMARK_CORPUS_VERSION,
        "state": "observed",
        "valid": True,
        "reason": "corpus_integrity_verified",
        "site_count": len(ordered_site_ids),
        "site_ids": ordered_site_ids,
        "full_500_vs_1000_sites": full_comparison_sites,
        "inventory_limited_sites": len(ordered_site_ids) - full_comparison_sites,
        "smart_pages_assessed": smart_pages,
        "blind_pages_assessed": blind_pages,
        "pages_saved_by_smart": blind_pages - smart_pages,
        "smart_site_scoped_finding_fingerprints": smart_findings,
        "blind_site_scoped_finding_fingerprints": blind_findings,
        "shared_site_scoped_finding_fingerprints": shared_findings,
        "smart_only_site_scoped_finding_fingerprints": smart_only_findings,
        "blind_only_site_scoped_finding_fingerprints": blind_only_findings,
        "smart_finding_yield_per_100": smart_yield,
        "blind_finding_yield_per_100": blind_yield,
        "smart_finding_coverage_vs_blind": corpus_coverage,
        "smart_efficiency_vs_blind": corpus_efficiency,
        "median_site_finding_coverage_vs_blind": (
            round(float(median(observed_coverages)), 4) if observed_coverages else None
        ),
    }
