"""Pure smart-500 vs blind-1000 priority-page benchmark helpers.

This module is engineering-only evidence. It measures whether a smaller smart
selection preserves coverage of caller-declared important/high-value URL
identities relative to a blind reference selection. It performs no network I/O,
does not infer sitewide completeness, and does not authorize crawl expansion.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from statistics import median
from typing import Any

ADAPTIVE_PRIORITY_BENCHMARK_VERSION = "adaptive_priority_benchmark_v1"
ADAPTIVE_PRIORITY_CORPUS_VERSION = "adaptive_priority_benchmark_corpus_v1"
SMART_PAGE_CAP = 500
BLIND_PAGE_CAP = 1000


def _identity_sequence(values: Iterable[str] | Any, *, field: str) -> tuple[tuple[str, ...] | None, str | None]:
    if isinstance(values, (str, bytes, Mapping)):
        return None, f"{field}_not_sequence"
    try:
        materialized = tuple(values)
    except TypeError:
        return None, f"{field}_not_sequence"
    for value in materialized:
        if not isinstance(value, str) or not value or value != value.strip():
            return None, f"{field}_invalid_identity"
    if len(set(materialized)) != len(materialized):
        return None, f"{field}_duplicate_identity"
    return materialized, None


def _coverage(covered: int, reference: int) -> float | None:
    if reference <= 0:
        return None
    return round(covered / reference, 4)


def build_priority_page_benchmark(
    smart_selected: Iterable[str],
    blind_selected: Iterable[str],
    *,
    important_urls: Iterable[str],
    high_value_urls: Iterable[str] = (),
) -> dict[str, Any]:
    """Measure priority-page coverage without normalizing URL identity.

    Coverage denominators are limited to priority identities present in the
    blind reference selection. Smart-only priority pages are reported
    separately and therefore cannot inflate coverage above 1.0.
    """
    normalized: dict[str, tuple[str, ...]] = {}
    for field, values in (
        ("smart_selected", smart_selected),
        ("blind_selected", blind_selected),
        ("important_urls", important_urls),
        ("high_value_urls", high_value_urls),
    ):
        sequence, reason = _identity_sequence(values, field=field)
        if reason:
            return {
                "version": ADAPTIVE_PRIORITY_BENCHMARK_VERSION,
                "state": "invalid_evidence",
                "valid": False,
                "reason": reason,
                "population_scope_complete": False,
            }
        assert sequence is not None
        normalized[field] = sequence

    smart = normalized["smart_selected"]
    blind = normalized["blind_selected"]
    if len(smart) > SMART_PAGE_CAP:
        return {
            "version": ADAPTIVE_PRIORITY_BENCHMARK_VERSION,
            "state": "invalid_evidence",
            "valid": False,
            "reason": "smart_page_cap_exceeded",
            "population_scope_complete": False,
        }
    if len(blind) > BLIND_PAGE_CAP:
        return {
            "version": ADAPTIVE_PRIORITY_BENCHMARK_VERSION,
            "state": "invalid_evidence",
            "valid": False,
            "reason": "blind_page_cap_exceeded",
            "population_scope_complete": False,
        }

    smart_set = set(smart)
    blind_set = set(blind)
    important = set(normalized["important_urls"])
    high_value = set(normalized["high_value_urls"])

    important_reference = important & blind_set
    high_value_reference = high_value & blind_set
    important_covered = important_reference & smart_set
    high_value_covered = high_value_reference & smart_set
    smart_only_important = (important & smart_set) - blind_set
    smart_only_high_value = (high_value & smart_set) - blind_set

    important_reference_count = len(important_reference)
    high_value_reference_count = len(high_value_reference)
    important_covered_count = len(important_covered)
    high_value_covered_count = len(high_value_covered)

    reference_state = (
        "observed"
        if important_reference_count or high_value_reference_count
        else "no_reference_priority_pages"
    )
    return {
        "version": ADAPTIVE_PRIORITY_BENCHMARK_VERSION,
        "state": reference_state,
        "valid": True,
        "reason": "priority_population_measured",
        "population_scope_complete": False,
        "smart_pages_assessed": len(smart),
        "blind_pages_assessed": len(blind),
        "smart_pages_inside_blind": len(smart_set & blind_set),
        "smart_pages_outside_blind": len(smart_set - blind_set),
        "important_reference_pages": important_reference_count,
        "important_reference_covered_by_smart": important_covered_count,
        "important_coverage_vs_blind": _coverage(important_covered_count, important_reference_count),
        "smart_only_important_pages": len(smart_only_important),
        "high_value_reference_pages": high_value_reference_count,
        "high_value_reference_covered_by_smart": high_value_covered_count,
        "high_value_coverage_vs_blind": _coverage(high_value_covered_count, high_value_reference_count),
        "smart_only_high_value_pages": len(smart_only_high_value),
    }


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _ratio_matches(actual: Any, expected: float | None) -> bool:
    if expected is None:
        return actual is None
    if isinstance(actual, bool):
        return False
    try:
        number = float(actual)
    except (TypeError, ValueError, OverflowError):
        return False
    return math.isfinite(number) and abs(number - expected) <= 1e-9


def validate_priority_page_benchmark(result: Mapping[str, Any] | Any) -> dict[str, Any]:
    """Fail closed on malformed or internally inconsistent benchmark evidence."""
    if not isinstance(result, Mapping):
        return {"version": ADAPTIVE_PRIORITY_BENCHMARK_VERSION, "valid": False, "reason": "benchmark_not_mapping"}
    if result.get("version") != ADAPTIVE_PRIORITY_BENCHMARK_VERSION:
        return {"version": ADAPTIVE_PRIORITY_BENCHMARK_VERSION, "valid": False, "reason": "benchmark_version_mismatch"}
    if result.get("valid") is not True:
        return {"version": ADAPTIVE_PRIORITY_BENCHMARK_VERSION, "valid": False, "reason": "benchmark_not_valid"}
    if result.get("population_scope_complete") is not False:
        return {"version": ADAPTIVE_PRIORITY_BENCHMARK_VERSION, "valid": False, "reason": "population_scope_claim_invalid"}

    fields = (
        "smart_pages_assessed",
        "blind_pages_assessed",
        "smart_pages_inside_blind",
        "smart_pages_outside_blind",
        "important_reference_pages",
        "important_reference_covered_by_smart",
        "smart_only_important_pages",
        "high_value_reference_pages",
        "high_value_reference_covered_by_smart",
        "smart_only_high_value_pages",
    )
    counts = {field: _nonnegative_int(result.get(field)) for field in fields}
    if any(value is None for value in counts.values()):
        return {"version": ADAPTIVE_PRIORITY_BENCHMARK_VERSION, "valid": False, "reason": "invalid_count"}

    smart = int(counts["smart_pages_assessed"] or 0)
    blind = int(counts["blind_pages_assessed"] or 0)
    if smart > SMART_PAGE_CAP:
        return {"version": ADAPTIVE_PRIORITY_BENCHMARK_VERSION, "valid": False, "reason": "smart_page_cap_exceeded"}
    if blind > BLIND_PAGE_CAP:
        return {"version": ADAPTIVE_PRIORITY_BENCHMARK_VERSION, "valid": False, "reason": "blind_page_cap_exceeded"}
    if counts["smart_pages_inside_blind"] + counts["smart_pages_outside_blind"] != smart:
        return {"version": ADAPTIVE_PRIORITY_BENCHMARK_VERSION, "valid": False, "reason": "smart_partition_mismatch"}

    important_reference = int(counts["important_reference_pages"] or 0)
    important_covered = int(counts["important_reference_covered_by_smart"] or 0)
    high_reference = int(counts["high_value_reference_pages"] or 0)
    high_covered = int(counts["high_value_reference_covered_by_smart"] or 0)
    if important_reference > blind or important_covered > important_reference or important_covered > smart:
        return {"version": ADAPTIVE_PRIORITY_BENCHMARK_VERSION, "valid": False, "reason": "important_coverage_count_mismatch"}
    if high_reference > blind or high_covered > high_reference or high_covered > smart:
        return {"version": ADAPTIVE_PRIORITY_BENCHMARK_VERSION, "valid": False, "reason": "high_value_coverage_count_mismatch"}

    expected_important = _coverage(important_covered, important_reference)
    expected_high = _coverage(high_covered, high_reference)
    if not _ratio_matches(result.get("important_coverage_vs_blind"), expected_important):
        return {"version": ADAPTIVE_PRIORITY_BENCHMARK_VERSION, "valid": False, "reason": "important_coverage_ratio_mismatch"}
    if not _ratio_matches(result.get("high_value_coverage_vs_blind"), expected_high):
        return {"version": ADAPTIVE_PRIORITY_BENCHMARK_VERSION, "valid": False, "reason": "high_value_coverage_ratio_mismatch"}

    expected_state = "observed" if important_reference or high_reference else "no_reference_priority_pages"
    if result.get("state") != expected_state:
        return {"version": ADAPTIVE_PRIORITY_BENCHMARK_VERSION, "valid": False, "reason": "reference_state_mismatch"}
    return {"version": ADAPTIVE_PRIORITY_BENCHMARK_VERSION, "valid": True, "reason": "priority_benchmark_integrity_verified"}


def summarize_priority_benchmark_corpus(results_by_site: Mapping[str, Any] | Any) -> dict[str, Any]:
    """Aggregate only integrity-valid site results for the smart-500 experiment."""
    if not isinstance(results_by_site, Mapping) or not results_by_site:
        return {
            "version": ADAPTIVE_PRIORITY_CORPUS_VERSION,
            "state": "insufficient_evidence",
            "valid": False,
            "reason": "no_benchmarks",
            "site_count": 0,
        }
    site_ids = tuple(results_by_site.keys())
    if any(not isinstance(site_id, str) or not site_id.strip() for site_id in site_ids):
        return {
            "version": ADAPTIVE_PRIORITY_CORPUS_VERSION,
            "state": "invalid_benchmark",
            "valid": False,
            "reason": "invalid_site_identity",
            "site_count": len(site_ids),
        }

    ordered = tuple(sorted(site_ids))
    invalid: list[tuple[str, str]] = []
    for site_id in ordered:
        integrity = validate_priority_page_benchmark(results_by_site[site_id])
        if integrity["valid"] is not True:
            invalid.append((site_id, str(integrity["reason"])))
    if invalid:
        return {
            "version": ADAPTIVE_PRIORITY_CORPUS_VERSION,
            "state": "invalid_benchmark",
            "valid": False,
            "reason": "member_integrity_failed",
            "site_count": len(ordered),
            "invalid_sites": tuple(invalid),
        }

    smart_pages = blind_pages = 0
    important_reference = important_covered = 0
    high_reference = high_covered = 0
    full_sites = 0
    important_site_ratios: list[float] = []
    high_site_ratios: list[float] = []
    for site_id in ordered:
        result = results_by_site[site_id]
        smart_pages += int(result["smart_pages_assessed"])
        blind_pages += int(result["blind_pages_assessed"])
        important_reference += int(result["important_reference_pages"])
        important_covered += int(result["important_reference_covered_by_smart"])
        high_reference += int(result["high_value_reference_pages"])
        high_covered += int(result["high_value_reference_covered_by_smart"])
        if int(result["smart_pages_assessed"]) == SMART_PAGE_CAP and int(result["blind_pages_assessed"]) == BLIND_PAGE_CAP:
            full_sites += 1
        if result["important_coverage_vs_blind"] is not None:
            important_site_ratios.append(float(result["important_coverage_vs_blind"]))
        if result["high_value_coverage_vs_blind"] is not None:
            high_site_ratios.append(float(result["high_value_coverage_vs_blind"]))

    return {
        "version": ADAPTIVE_PRIORITY_CORPUS_VERSION,
        "state": "observed",
        "valid": True,
        "reason": "priority_corpus_integrity_verified",
        "site_count": len(ordered),
        "site_ids": ordered,
        "full_500_vs_1000_sites": full_sites,
        "inventory_limited_sites": len(ordered) - full_sites,
        "smart_pages_assessed": smart_pages,
        "blind_pages_assessed": blind_pages,
        "pages_saved_by_smart": blind_pages - smart_pages,
        "important_reference_pages": important_reference,
        "important_reference_covered_by_smart": important_covered,
        "important_coverage_vs_blind": _coverage(important_covered, important_reference),
        "median_site_important_coverage_vs_blind": round(float(median(important_site_ratios)), 4) if important_site_ratios else None,
        "high_value_reference_pages": high_reference,
        "high_value_reference_covered_by_smart": high_covered,
        "high_value_coverage_vs_blind": _coverage(high_covered, high_reference),
        "median_site_high_value_coverage_vs_blind": round(float(median(high_site_ratios)), 4) if high_site_ratios else None,
    }
