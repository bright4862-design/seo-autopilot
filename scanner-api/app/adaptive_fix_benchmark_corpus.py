"""Deterministic corpus aggregation for manifest-bound Smart-500 Fix benchmarks.

This module is pure/shadow-only. It validates transported per-site Fix benchmark
artifacts before aggregation and never performs crawling, repair prioritization,
persistence, customer projection, or budget authorization.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from statistics import median
from typing import Any

ADAPTIVE_FIX_BENCHMARK_VERSION = "adaptive_manifest_fix_benchmark_v1"
ADAPTIVE_FIX_BENCHMARK_CORPUS_VERSION = "adaptive_manifest_fix_benchmark_corpus_v1"

_STANDARD_150_MAX = 150
_SMART_500_MAX = 500
_BLIND_1000_MAX = 1000


def _canonical(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _canonical(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, set):
        return sorted(_canonical(item) for item in value)
    return value


def _fingerprint_json(value: Any, *, domain: str) -> str:
    digest = hashlib.sha256()
    digest.update(domain.encode("utf-8"))
    digest.update(b"\0")
    digest.update(
        json.dumps(
            _canonical(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    return digest.hexdigest()


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _finite_nonnegative(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number) or number < 0.0:
        return None
    return number


def _ratio(value: Any) -> float | None:
    number = _finite_nonnegative(value)
    if number is None or number > 1.0:
        return None
    return number


def _expected_ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 6)


def _expected_per_100(count: int, pages: int) -> float | None:
    if pages <= 0:
        return None
    return round(count * 100.0 / pages, 4)


def _is_sha256(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return value == value.lower()


def _same_optional_float(actual: Any, expected: float | None) -> bool:
    if expected is None:
        return actual is None
    normalized = _finite_nonnegative(actual)
    return normalized is not None and normalized == expected


def validate_fix_benchmark_member(result: Mapping[str, Any] | Any) -> dict[str, Any]:
    """Validate one transported Fix benchmark without granting production authority."""
    errors: list[str] = []
    if not isinstance(result, Mapping):
        return {"valid": False, "errors": ("result_not_mapping",)}
    if result.get("version") != ADAPTIVE_FIX_BENCHMARK_VERSION:
        errors.append("version_mismatch")

    transported_fingerprint = result.get("binding_fingerprint")
    unsigned = dict(result)
    unsigned.pop("binding_fingerprint", None)
    expected_fingerprint = _fingerprint_json(unsigned, domain=ADAPTIVE_FIX_BENCHMARK_VERSION)
    if transported_fingerprint != expected_fingerprint:
        errors.append("binding_fingerprint_mismatch")

    for field in (
        "manifest_input_population_fingerprint",
        "standard_reference_population_fingerprint",
        "smart_population_fingerprint",
        "blind_population_fingerprint",
    ):
        if not _is_sha256(result.get(field)):
            errors.append(f"{field}_invalid")

    count_fields = (
        "candidate_urls_supplied",
        "candidate_urls_unique",
        "duplicate_candidate_identities_removed",
        "standard_reference_target",
        "standard_reference_pages",
        "smart_manifest_target",
        "smart_pages_assessed",
        "blind_pages_assessed",
        "pages_saved_by_smart",
        "standard_fix_fingerprints",
        "smart_fix_fingerprints",
        "blind_fix_fingerprints",
        "shared_fix_fingerprints",
        "blind_only_fix_fingerprints",
        "smart_only_fix_fingerprints",
        "smart_incremental_pages_vs_standard",
        "smart_incremental_fix_fingerprints_vs_standard",
    )
    counts = {field: _nonnegative_int(result.get(field)) for field in count_fields}
    for field, value in counts.items():
        if value is None:
            errors.append(f"{field}_invalid")

    if all(value is not None for value in counts.values()):
        supplied = counts["candidate_urls_supplied"]
        unique = counts["candidate_urls_unique"]
        duplicates = counts["duplicate_candidate_identities_removed"]
        standard_target = counts["standard_reference_target"]
        standard_pages = counts["standard_reference_pages"]
        smart_target = counts["smart_manifest_target"]
        smart_pages = counts["smart_pages_assessed"]
        blind_pages = counts["blind_pages_assessed"]
        pages_saved = counts["pages_saved_by_smart"]
        standard_fixes = counts["standard_fix_fingerprints"]
        smart_fixes = counts["smart_fix_fingerprints"]
        blind_fixes = counts["blind_fix_fingerprints"]
        shared = counts["shared_fix_fingerprints"]
        blind_only = counts["blind_only_fix_fingerprints"]
        smart_only = counts["smart_only_fix_fingerprints"]
        incremental_pages = counts["smart_incremental_pages_vs_standard"]
        incremental_fixes = counts["smart_incremental_fix_fingerprints_vs_standard"]

        if supplied < unique or supplied - unique != duplicates:
            errors.append("candidate_population_count_mismatch")
        if standard_target > _STANDARD_150_MAX or standard_pages > standard_target:
            errors.append("standard_reference_cap_mismatch")
        if smart_target > _SMART_500_MAX or smart_pages > smart_target:
            errors.append("smart_population_cap_mismatch")
        if blind_pages > _BLIND_1000_MAX or blind_pages > unique:
            errors.append("blind_population_cap_mismatch")
        if smart_pages > blind_pages or pages_saved != blind_pages - smart_pages:
            errors.append("page_savings_mismatch")
        if smart_pages < standard_pages or incremental_pages != smart_pages - standard_pages:
            errors.append("incremental_page_count_mismatch")
        if standard_fixes > smart_fixes:
            errors.append("standard_fix_population_exceeds_smart")
        if shared > smart_fixes or shared > blind_fixes:
            errors.append("shared_fix_partition_invalid")
        if shared + blind_only != blind_fixes:
            errors.append("blind_fix_partition_mismatch")
        if shared + smart_only != smart_fixes:
            errors.append("smart_fix_partition_mismatch")
        if incremental_fixes > smart_fixes:
            errors.append("incremental_fix_count_invalid")

        expected_coverage = _expected_ratio(shared, blind_fixes)
        if not _same_optional_float(result.get("smart_fix_coverage_vs_blind"), expected_coverage):
            errors.append("smart_fix_coverage_vs_blind_mismatch")
        expected_yield = _expected_per_100(incremental_fixes, incremental_pages)
        if not _same_optional_float(result.get("smart_incremental_fix_yield_per_100"), expected_yield):
            errors.append("smart_incremental_fix_yield_per_100_mismatch")

    high_state = result.get("high_impact_evidence_state")
    high_fields = (
        "smart_high_impact_fix_fingerprints",
        "blind_high_impact_fix_fingerprints",
        "shared_high_impact_fix_fingerprints",
        "blind_only_high_impact_fix_fingerprints",
    )
    if high_state == "not_observed":
        if any(result.get(field) is not None for field in high_fields):
            errors.append("unobserved_high_impact_counts_must_be_null")
        if result.get("smart_high_impact_coverage_vs_blind") is not None:
            errors.append("unobserved_high_impact_coverage_must_be_null")
    elif high_state == "observed":
        highs = {field: _nonnegative_int(result.get(field)) for field in high_fields}
        if any(value is None for value in highs.values()):
            errors.append("observed_high_impact_count_invalid")
        else:
            smart_high = highs["smart_high_impact_fix_fingerprints"]
            blind_high = highs["blind_high_impact_fix_fingerprints"]
            shared_high = highs["shared_high_impact_fix_fingerprints"]
            blind_only_high = highs["blind_only_high_impact_fix_fingerprints"]
            assert smart_high is not None and blind_high is not None
            assert shared_high is not None and blind_only_high is not None
            if shared_high > smart_high or shared_high > blind_high:
                errors.append("high_impact_shared_partition_invalid")
            if shared_high + blind_only_high != blind_high:
                errors.append("high_impact_blind_partition_mismatch")
            expected = _expected_ratio(shared_high, blind_high)
            if not _same_optional_float(result.get("smart_high_impact_coverage_vs_blind"), expected):
                errors.append("smart_high_impact_coverage_vs_blind_mismatch")
    else:
        errors.append("high_impact_evidence_state_invalid")

    if result.get("standard_150_preserved") is not True:
        errors.append("standard_150_not_preserved")
    for field in (
        "population_scope_complete",
        "production_budget_authorized",
        "site_fully_understood",
    ):
        if result.get(field) is not False:
            errors.append(f"{field}_forbidden_claim")

    return {
        "valid": not errors,
        "errors": tuple(errors),
        "binding_fingerprint": transported_fingerprint,
    }


def summarize_fix_benchmark_corpus(
    members: Sequence[Mapping[str, Any]] | Any,
) -> dict[str, Any]:
    """Aggregate exact transported per-site Fix benchmarks deterministically.

    Each member is ``{"site_id": <stable id>, "benchmark": <artifact>}``. Site
    identity is intentionally opaque and does not authorize crawling or persistence.
    """
    if isinstance(members, (str, bytes, Mapping)) or not isinstance(members, Sequence):
        raise ValueError("members_invalid")
    rows = tuple(members)
    if not rows:
        raise ValueError("members_empty")

    normalized: list[tuple[str, Mapping[str, Any]]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("member_not_mapping")
        site_id = row.get("site_id")
        benchmark = row.get("benchmark")
        if not isinstance(site_id, str) or not site_id or site_id != site_id.strip():
            raise ValueError("site_id_invalid")
        if site_id in seen:
            raise ValueError("site_id_duplicate")
        checked = validate_fix_benchmark_member(benchmark)
        if checked["valid"] is not True:
            reason = checked["errors"][0] if checked["errors"] else "invalid"
            raise ValueError(f"benchmark_invalid:{site_id}:{reason}")
        assert isinstance(benchmark, Mapping)
        seen.add(site_id)
        normalized.append((site_id, benchmark))

    normalized.sort(key=lambda pair: pair[0])

    site_ids = tuple(site_id for site_id, _ in normalized)
    smart_pages = sum(int(benchmark["smart_pages_assessed"]) for _, benchmark in normalized)
    blind_pages = sum(int(benchmark["blind_pages_assessed"]) for _, benchmark in normalized)
    pages_saved = sum(int(benchmark["pages_saved_by_smart"]) for _, benchmark in normalized)
    smart_fixes = sum(int(benchmark["smart_fix_fingerprints"]) for _, benchmark in normalized)
    blind_fixes = sum(int(benchmark["blind_fix_fingerprints"]) for _, benchmark in normalized)
    shared_fixes = sum(int(benchmark["shared_fix_fingerprints"]) for _, benchmark in normalized)
    blind_only_fixes = sum(int(benchmark["blind_only_fix_fingerprints"]) for _, benchmark in normalized)
    smart_only_fixes = sum(int(benchmark["smart_only_fix_fingerprints"]) for _, benchmark in normalized)
    incremental_pages = sum(
        int(benchmark["smart_incremental_pages_vs_standard"]) for _, benchmark in normalized
    )
    incremental_fixes = sum(
        int(benchmark["smart_incremental_fix_fingerprints_vs_standard"])
        for _, benchmark in normalized
    )

    coverages = [
        float(benchmark["smart_fix_coverage_vs_blind"])
        for _, benchmark in normalized
        if benchmark["smart_fix_coverage_vs_blind"] is not None
    ]
    full_sites = sum(
        1
        for _, benchmark in normalized
        if benchmark["smart_pages_assessed"] == _SMART_500_MAX
        and benchmark["blind_pages_assessed"] == _BLIND_1000_MAX
    )

    high_observed = [
        benchmark
        for _, benchmark in normalized
        if benchmark["high_impact_evidence_state"] == "observed"
    ]
    if len(high_observed) == len(normalized):
        high_state = "observed"
        smart_high = sum(int(benchmark["smart_high_impact_fix_fingerprints"]) for benchmark in high_observed)
        blind_high = sum(int(benchmark["blind_high_impact_fix_fingerprints"]) for benchmark in high_observed)
        shared_high = sum(int(benchmark["shared_high_impact_fix_fingerprints"]) for benchmark in high_observed)
        blind_only_high = sum(int(benchmark["blind_only_high_impact_fix_fingerprints"]) for benchmark in high_observed)
        high_coverage = _expected_ratio(shared_high, blind_high)
    elif high_observed:
        high_state = "partial"
        smart_high = blind_high = shared_high = blind_only_high = high_coverage = None
    else:
        high_state = "not_observed"
        smart_high = blind_high = shared_high = blind_only_high = high_coverage = None

    result = {
        "version": ADAPTIVE_FIX_BENCHMARK_CORPUS_VERSION,
        "state": "observed",
        "valid": True,
        "site_count": len(normalized),
        "site_ids": site_ids,
        "full_500_vs_1000_sites": full_sites,
        "inventory_limited_sites": len(normalized) - full_sites,
        "smart_pages_assessed": smart_pages,
        "blind_pages_assessed": blind_pages,
        "pages_saved_by_smart": pages_saved,
        "smart_fix_fingerprints_site_scoped": smart_fixes,
        "blind_fix_fingerprints_site_scoped": blind_fixes,
        "shared_fix_fingerprints_site_scoped": shared_fixes,
        "blind_only_fix_fingerprints_site_scoped": blind_only_fixes,
        "smart_only_fix_fingerprints_site_scoped": smart_only_fixes,
        "smart_fix_coverage_vs_blind": _expected_ratio(shared_fixes, blind_fixes),
        "median_site_smart_fix_coverage_vs_blind": round(median(coverages), 6) if coverages else None,
        "smart_incremental_pages_vs_standard": incremental_pages,
        "smart_incremental_fix_fingerprints_vs_standard_site_scoped": incremental_fixes,
        "smart_incremental_fix_yield_per_100": _expected_per_100(incremental_fixes, incremental_pages),
        "high_impact_evidence_state": high_state,
        "smart_high_impact_fix_fingerprints_site_scoped": smart_high,
        "blind_high_impact_fix_fingerprints_site_scoped": blind_high,
        "shared_high_impact_fix_fingerprints_site_scoped": shared_high,
        "blind_only_high_impact_fix_fingerprints_site_scoped": blind_only_high,
        "smart_high_impact_coverage_vs_blind": high_coverage,
        "population_fingerprints": tuple(
            (
                site_id,
                benchmark["smart_population_fingerprint"],
                benchmark["blind_population_fingerprint"],
                benchmark["binding_fingerprint"],
            )
            for site_id, benchmark in normalized
        ),
        "standard_150_preserved": True,
        "population_scope_complete": False,
        "production_budget_authorized": False,
        "site_fully_understood": False,
    }
    result["corpus_fingerprint"] = _fingerprint_json(
        result, domain=ADAPTIVE_FIX_BENCHMARK_CORPUS_VERSION
    )
    return result
