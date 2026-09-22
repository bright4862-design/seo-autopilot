"""Shadow-only acceptance policy for manifest-bound Fix benchmark corpus evidence.

This module evaluates opaque Fix-fingerprint coverage/yield telemetry only. It does
not rank repairs, authorize crawl budgets, persist authority, project customer output,
or perform network work. A positive result is an engineering experiment candidate.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from typing import Any

ADAPTIVE_FIX_BENCHMARK_CORPUS_VERSION = "adaptive_manifest_fix_benchmark_corpus_v1"
ADAPTIVE_FIX_BENCHMARK_ACCEPTANCE_VERSION = "adaptive_fix_benchmark_acceptance_v1"

DEFAULT_MIN_FULL_COMPARISON_SITES = 10
DEFAULT_MIN_FIX_COVERAGE = 0.95
DEFAULT_MIN_MEDIAN_SITE_FIX_COVERAGE = 0.90
DEFAULT_MIN_INCREMENTAL_FIX_YIELD_PER_100 = 0.50
DEFAULT_MIN_HIGH_IMPACT_FIX_COVERAGE = 0.95


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


def _result(decision: str, reason: str, **extra: Any) -> dict[str, Any]:
    return {
        "version": ADAPTIVE_FIX_BENCHMARK_ACCEPTANCE_VERSION,
        "decision": decision,
        "reason": reason,
        "population_scope_complete": False,
        "production_budget_authorized": False,
        "site_fully_understood": False,
        **extra,
    }


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


def _threshold(value: Any, *, field: str, ratio: bool = False) -> tuple[float | None, str | None]:
    number = _ratio(value) if ratio else _finite_nonnegative(value)
    if number is None:
        return None, f"invalid_threshold:{field}"
    return number, None


def _site_ids(value: Any, expected_count: int) -> tuple[str, ...] | None:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
        return None
    ids = tuple(value)
    if len(ids) != expected_count:
        return None
    if (
        any(not isinstance(site_id, str) or not site_id or site_id.strip() != site_id for site_id in ids)
        or len(set(ids)) != len(ids)
        or ids != tuple(sorted(ids))
    ):
        return None
    return ids


def _population_fingerprints(
    value: Any, expected_site_ids: tuple[str, ...]
) -> tuple[tuple[str, str, str, str], ...] | None:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
        return None
    rows = tuple(value)
    if len(rows) != len(expected_site_ids):
        return None
    normalized: list[tuple[str, str, str, str]] = []
    seen: set[str] = set()
    for raw in rows:
        if isinstance(raw, (str, bytes, Mapping)) or not isinstance(raw, Sequence):
            return None
        parts = tuple(raw)
        if len(parts) != 4 or not all(isinstance(part, str) and part for part in parts):
            return None
        site_id, smart_fp, blind_fp, binding_fp = parts
        if site_id in seen:
            return None
        for fingerprint in (smart_fp, blind_fp, binding_fp):
            if len(fingerprint) != 64:
                return None
            try:
                int(fingerprint, 16)
            except ValueError:
                return None
            if fingerprint != fingerprint.lower():
                return None
        seen.add(site_id)
        normalized.append((site_id, smart_fp, blind_fp, binding_fp))
    normalized.sort(key=lambda row: row[0])
    result = tuple(normalized)
    if tuple(row[0] for row in result) != expected_site_ids:
        return None
    return result


def _same_optional_float(value: Any, expected: float | None) -> bool:
    if expected is None:
        return value is None
    number = _finite_nonnegative(value)
    return number is not None and number == expected


def _expected_ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 6)


def _expected_per_100(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator * 100.0 / denominator, 4)


def validate_fix_benchmark_corpus(corpus: Mapping[str, Any] | Any) -> dict[str, Any]:
    """Validate transported corpus identity/arithmetic before threshold evaluation."""
    if not isinstance(corpus, Mapping):
        return {"valid": False, "reason": "corpus_not_mapping"}
    if corpus.get("version") != ADAPTIVE_FIX_BENCHMARK_CORPUS_VERSION:
        return {"valid": False, "reason": "corpus_version_mismatch"}
    if corpus.get("valid") is not True or corpus.get("state") != "observed":
        return {"valid": False, "reason": "corpus_not_integrity_verified"}
    if corpus.get("standard_150_preserved") is not True:
        return {"valid": False, "reason": "standard_150_not_preserved"}
    for field in (
        "population_scope_complete",
        "production_budget_authorized",
        "site_fully_understood",
    ):
        if corpus.get(field) is not False:
            return {"valid": False, "reason": f"{field}_forbidden_claim"}

    transported_fingerprint = corpus.get("corpus_fingerprint")
    if not isinstance(transported_fingerprint, str):
        return {"valid": False, "reason": "corpus_fingerprint_missing"}
    unsigned = dict(corpus)
    unsigned.pop("corpus_fingerprint", None)
    expected_fingerprint = _fingerprint_json(
        unsigned, domain=ADAPTIVE_FIX_BENCHMARK_CORPUS_VERSION
    )
    if transported_fingerprint != expected_fingerprint:
        return {"valid": False, "reason": "corpus_fingerprint_mismatch"}

    count_fields = (
        "site_count",
        "full_500_vs_1000_sites",
        "inventory_limited_sites",
        "smart_pages_assessed",
        "blind_pages_assessed",
        "pages_saved_by_smart",
        "smart_fix_fingerprints_site_scoped",
        "blind_fix_fingerprints_site_scoped",
        "shared_fix_fingerprints_site_scoped",
        "blind_only_fix_fingerprints_site_scoped",
        "smart_only_fix_fingerprints_site_scoped",
        "smart_incremental_pages_vs_standard",
        "smart_incremental_fix_fingerprints_vs_standard_site_scoped",
    )
    counts = {field: _nonnegative_int(corpus.get(field)) for field in count_fields}
    if any(value is None for value in counts.values()):
        return {"valid": False, "reason": "corpus_count_invalid"}

    site_count = counts["site_count"]
    full_sites = counts["full_500_vs_1000_sites"]
    limited_sites = counts["inventory_limited_sites"]
    smart_pages = counts["smart_pages_assessed"]
    blind_pages = counts["blind_pages_assessed"]
    pages_saved = counts["pages_saved_by_smart"]
    smart_fixes = counts["smart_fix_fingerprints_site_scoped"]
    blind_fixes = counts["blind_fix_fingerprints_site_scoped"]
    shared = counts["shared_fix_fingerprints_site_scoped"]
    blind_only = counts["blind_only_fix_fingerprints_site_scoped"]
    smart_only = counts["smart_only_fix_fingerprints_site_scoped"]
    incremental_pages = counts["smart_incremental_pages_vs_standard"]
    incremental_fixes = counts["smart_incremental_fix_fingerprints_vs_standard_site_scoped"]
    assert None not in (
        site_count,
        full_sites,
        limited_sites,
        smart_pages,
        blind_pages,
        pages_saved,
        smart_fixes,
        blind_fixes,
        shared,
        blind_only,
        smart_only,
        incremental_pages,
        incremental_fixes,
    )

    if site_count <= 0 or full_sites + limited_sites != site_count:
        return {"valid": False, "reason": "site_population_count_mismatch"}
    site_ids = _site_ids(corpus.get("site_ids"), site_count)
    if site_ids is None:
        return {"valid": False, "reason": "site_identity_population_mismatch"}
    populations = _population_fingerprints(corpus.get("population_fingerprints"), site_ids)
    if populations is None:
        return {"valid": False, "reason": "population_fingerprint_set_invalid"}

    if smart_pages > blind_pages or pages_saved != blind_pages - smart_pages:
        return {"valid": False, "reason": "page_population_count_mismatch"}
    if shared > smart_fixes or shared > blind_fixes:
        return {"valid": False, "reason": "shared_fix_partition_invalid"}
    if shared + blind_only != blind_fixes or shared + smart_only != smart_fixes:
        return {"valid": False, "reason": "fix_partition_mismatch"}
    if incremental_fixes > smart_fixes:
        return {"valid": False, "reason": "incremental_fix_count_invalid"}

    coverage = _expected_ratio(shared, blind_fixes)
    if not _same_optional_float(corpus.get("smart_fix_coverage_vs_blind"), coverage):
        return {"valid": False, "reason": "smart_fix_coverage_mismatch"}
    median_coverage = _ratio(corpus.get("median_site_smart_fix_coverage_vs_blind"))
    if corpus.get("median_site_smart_fix_coverage_vs_blind") is not None and median_coverage is None:
        return {"valid": False, "reason": "median_site_fix_coverage_invalid"}
    incremental_yield = _expected_per_100(incremental_fixes, incremental_pages)
    if not _same_optional_float(corpus.get("smart_incremental_fix_yield_per_100"), incremental_yield):
        return {"valid": False, "reason": "incremental_fix_yield_mismatch"}

    high_state = corpus.get("high_impact_evidence_state")
    high_fields = (
        "smart_high_impact_fix_fingerprints_site_scoped",
        "blind_high_impact_fix_fingerprints_site_scoped",
        "shared_high_impact_fix_fingerprints_site_scoped",
        "blind_only_high_impact_fix_fingerprints_site_scoped",
    )
    if high_state == "observed":
        highs = {field: _nonnegative_int(corpus.get(field)) for field in high_fields}
        if any(value is None for value in highs.values()):
            return {"valid": False, "reason": "high_impact_count_invalid"}
        smart_high = highs["smart_high_impact_fix_fingerprints_site_scoped"]
        blind_high = highs["blind_high_impact_fix_fingerprints_site_scoped"]
        shared_high = highs["shared_high_impact_fix_fingerprints_site_scoped"]
        blind_only_high = highs["blind_only_high_impact_fix_fingerprints_site_scoped"]
        assert None not in (smart_high, blind_high, shared_high, blind_only_high)
        if shared_high > smart_high or shared_high > blind_high:
            return {"valid": False, "reason": "high_impact_shared_partition_invalid"}
        if shared_high + blind_only_high != blind_high:
            return {"valid": False, "reason": "high_impact_blind_partition_mismatch"}
        expected_high_coverage = _expected_ratio(shared_high, blind_high)
        if not _same_optional_float(
            corpus.get("smart_high_impact_coverage_vs_blind"), expected_high_coverage
        ):
            return {"valid": False, "reason": "high_impact_coverage_mismatch"}
    elif high_state in ("partial", "not_observed"):
        if any(corpus.get(field) is not None for field in high_fields):
            return {"valid": False, "reason": "unresolved_high_impact_counts_must_be_null"}
        if corpus.get("smart_high_impact_coverage_vs_blind") is not None:
            return {"valid": False, "reason": "unresolved_high_impact_coverage_must_be_null"}
    else:
        return {"valid": False, "reason": "high_impact_evidence_state_invalid"}

    return {
        "valid": True,
        "reason": "ok",
        "site_ids": site_ids,
        "population_fingerprints": populations,
        "corpus_fingerprint": transported_fingerprint,
    }


def evaluate_fix_benchmark_corpus(
    corpus: Mapping[str, Any] | Any,
    *,
    min_full_comparison_sites: int = DEFAULT_MIN_FULL_COMPARISON_SITES,
    min_fix_coverage: float = DEFAULT_MIN_FIX_COVERAGE,
    min_median_site_fix_coverage: float = DEFAULT_MIN_MEDIAN_SITE_FIX_COVERAGE,
    min_incremental_fix_yield_per_100: float = DEFAULT_MIN_INCREMENTAL_FIX_YIELD_PER_100,
    min_high_impact_fix_coverage: float = DEFAULT_MIN_HIGH_IMPACT_FIX_COVERAGE,
    require_high_impact_observed: bool = True,
) -> dict[str, Any]:
    """Evaluate Fix evidence for a shadow Smart-500 experiment candidate.

    This is intentionally not a repair-priority policy. Fix identities are opaque and
    only coverage/yield evidence is compared. No decision here authorizes production.
    """
    integrity = validate_fix_benchmark_corpus(corpus)
    if integrity.get("valid") is not True:
        return _result(
            "insufficient_evidence",
            f"fix_corpus_integrity_failed:{integrity.get('reason') or 'invalid'}",
        )
    assert isinstance(corpus, Mapping)

    if (
        isinstance(min_full_comparison_sites, bool)
        or not isinstance(min_full_comparison_sites, int)
        or min_full_comparison_sites <= 0
    ):
        return _result("insufficient_evidence", "invalid_threshold:min_full_comparison_sites")

    thresholds: dict[str, float] = {}
    for field, raw, ratio in (
        ("min_fix_coverage", min_fix_coverage, True),
        ("min_median_site_fix_coverage", min_median_site_fix_coverage, True),
        ("min_incremental_fix_yield_per_100", min_incremental_fix_yield_per_100, False),
        ("min_high_impact_fix_coverage", min_high_impact_fix_coverage, True),
    ):
        normalized, error = _threshold(raw, field=field, ratio=ratio)
        if error:
            return _result("insufficient_evidence", error)
        assert normalized is not None
        thresholds[field] = normalized
    if not isinstance(require_high_impact_observed, bool):
        return _result("insufficient_evidence", "invalid_threshold:require_high_impact_observed")

    full_sites = int(corpus["full_500_vs_1000_sites"])
    limited_sites = int(corpus["inventory_limited_sites"])
    if full_sites < min_full_comparison_sites:
        return _result(
            "insufficient_evidence",
            "too_few_full_500_vs_1000_sites",
            full_comparison_sites=full_sites,
            minimum_full_comparison_sites=min_full_comparison_sites,
        )
    if int(corpus["pages_saved_by_smart"]) <= 0:
        return _result("insufficient_evidence", "no_pages_saved_by_smart")

    fix_coverage = _ratio(corpus.get("smart_fix_coverage_vs_blind"))
    median_fix_coverage = _ratio(corpus.get("median_site_smart_fix_coverage_vs_blind"))
    incremental_fix_yield = _finite_nonnegative(corpus.get("smart_incremental_fix_yield_per_100"))
    if fix_coverage is None:
        return _result("insufficient_evidence", "fix_coverage_unavailable")
    if median_fix_coverage is None:
        return _result("insufficient_evidence", "median_site_fix_coverage_unavailable")
    if incremental_fix_yield is None:
        return _result("insufficient_evidence", "incremental_fix_yield_unavailable")

    high_state = corpus.get("high_impact_evidence_state")
    high_coverage = _ratio(corpus.get("smart_high_impact_coverage_vs_blind"))
    if require_high_impact_observed and (high_state != "observed" or high_coverage is None):
        return _result("insufficient_evidence", "high_impact_fix_evidence_not_fully_observed")

    failed: list[str] = []
    if fix_coverage < thresholds["min_fix_coverage"]:
        failed.append("fix_coverage")
    if median_fix_coverage < thresholds["min_median_site_fix_coverage"]:
        failed.append("median_site_fix_coverage")
    if incremental_fix_yield < thresholds["min_incremental_fix_yield_per_100"]:
        failed.append("incremental_fix_yield")
    if require_high_impact_observed and high_coverage is not None:
        if high_coverage < thresholds["min_high_impact_fix_coverage"]:
            failed.append("high_impact_fix_coverage")

    evidence = {
        "site_ids": integrity["site_ids"],
        "population_fingerprints": integrity["population_fingerprints"],
        "corpus_fingerprint": integrity["corpus_fingerprint"],
        "full_comparison_sites": full_sites,
        "inventory_limited_sites": limited_sites,
        "smart_pages_assessed": int(corpus["smart_pages_assessed"]),
        "blind_pages_assessed": int(corpus["blind_pages_assessed"]),
        "pages_saved_by_smart": int(corpus["pages_saved_by_smart"]),
        "smart_fix_coverage_vs_blind": fix_coverage,
        "median_site_smart_fix_coverage_vs_blind": median_fix_coverage,
        "smart_incremental_fix_yield_per_100": incremental_fix_yield,
        "high_impact_evidence_state": high_state,
        "smart_high_impact_coverage_vs_blind": high_coverage,
        "thresholds": {
            "min_full_comparison_sites": min_full_comparison_sites,
            **thresholds,
            "require_high_impact_observed": require_high_impact_observed,
        },
    }
    if failed:
        return _result(
            "blind_1000_fix_reference_retained",
            "fix_evidence_thresholds_not_met",
            failed_thresholds=tuple(failed),
            **evidence,
        )
    return _result(
        "smart_500_fix_evidence_candidate",
        "fix_coverage_and_incremental_yield_thresholds_met",
        failed_thresholds=(),
        **evidence,
    )
