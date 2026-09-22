"""Pure canonical-unit hardening for normalized Lighthouse lab metrics.

This module never runs Lighthouse or calls a provider. It consumes an already-
normalized Lighthouse lab evidence dictionary and emits a separate derived unit
normalization artifact so field and lab evidence cannot be conflated.
"""
from __future__ import annotations

from copy import deepcopy
from math import isfinite
from typing import Any

LIGHTHOUSE_UNIT_NORMALIZATION_VERSION = "nextgen_lighthouse_metric_units_v1"
LIGHTHOUSE_UNIT_INTEGRITY_VERSION = "nextgen_lighthouse_metric_units_integrity_v1"
SOURCE_LIGHTHOUSE_VERSION = "nextgen_lighthouse_evidence_v1"

CANONICAL_METRIC_UNITS = {
    "lcp": "ms",
    "inp": "ms",
    "cls": "score",
    "fcp": "ms",
    "server_response_time": "ms",
    "speed_index": "ms",
    "total_blocking_time": "ms",
}
NORMALIZATION_STATES = {"normalized", "not_applicable", "not_verified"}
SOURCE_STATES = {"connected", "disconnected", "unavailable", "rate_limited", "provider_error"}
EXCLUSION_REASONS = {
    "metric_unsupported",
    "metric_not_object",
    "metric_value_invalid",
    "metric_unit_missing",
    "metric_unit_mismatch",
}
_UNIT_ALIASES = {
    "ms": {"ms", "millisecond", "milliseconds"},
    "score": {"score", "unitless", "unitless_number", "unitlessnumber"},
}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if isfinite(number) and number >= 0 else None


def _canonical_unit(value: Any, expected: str) -> str | None:
    raw = _text(value).lower().replace("-", "_").replace(" ", "_")
    return expected if raw in _UNIT_ALIASES[expected] else None


def _base(evidence: Any) -> dict[str, Any]:
    source = evidence if isinstance(evidence, dict) else {}
    return {
        "version": LIGHTHOUSE_UNIT_NORMALIZATION_VERSION,
        "evidence_kind": "lab_metric_units",
        "state": "not_verified",
        "reason": None,
        "source_version": source.get("version"),
        "source_state": source.get("state"),
        "source_url": source.get("source_url"),
        "metrics": None,
        "excluded_metrics": [],
    }


def normalize_lighthouse_metric_units(evidence: Any) -> dict[str, Any]:
    """Canonicalize trusted Lighthouse metric units without rewriting source evidence.

    Timing audits normalize to ``ms`` and CLS normalizes to ``score``. Metrics with
    missing, malformed or contradictory units are excluded rather than guessed.
    The source dictionary is never mutated and field evidence is rejected.
    """
    result = _base(evidence)
    if not isinstance(evidence, dict):
        return {**result, "reason": "source_not_object"}
    if evidence.get("version") != SOURCE_LIGHTHOUSE_VERSION:
        return {**result, "reason": "source_version_mismatch"}
    if evidence.get("evidence_kind") != "lab":
        return {**result, "reason": "source_not_lab_evidence"}

    source_state = evidence.get("state")
    if source_state not in SOURCE_STATES:
        return {**result, "reason": "source_state_invalid"}
    if source_state != "connected":
        return {**result, "reason": f"source_{source_state}"}

    source_metrics = evidence.get("metrics")
    if source_metrics is None or source_metrics == {}:
        return {**result, "state": "not_applicable", "reason": "source_metrics_absent"}
    if not isinstance(source_metrics, dict):
        return {**result, "reason": "source_metrics_invalid"}

    normalized: dict[str, dict[str, Any]] = {}
    excluded: list[dict[str, Any]] = []
    for name in sorted(source_metrics):
        row = source_metrics[name]
        expected = CANONICAL_METRIC_UNITS.get(name)
        if expected is None:
            excluded.append({
                "metric": name,
                "reason": "metric_unsupported",
                "raw_unit": _text(row.get("unit")) or None if isinstance(row, dict) else None,
                "expected_unit": None,
            })
            continue
        if not isinstance(row, dict):
            excluded.append({
                "metric": name,
                "reason": "metric_not_object",
                "raw_unit": None,
                "expected_unit": expected,
            })
            continue
        if _number(row.get("value")) is None:
            excluded.append({
                "metric": name,
                "reason": "metric_value_invalid",
                "raw_unit": _text(row.get("unit")) or None,
                "expected_unit": expected,
            })
            continue
        raw_unit = _text(row.get("unit")) or None
        canonical = _canonical_unit(raw_unit, expected) if raw_unit is not None else None
        if canonical is None:
            excluded.append({
                "metric": name,
                "reason": "metric_unit_missing" if raw_unit is None else "metric_unit_mismatch",
                "raw_unit": raw_unit,
                "expected_unit": expected,
            })
            continue
        normalized[name] = {**deepcopy(row), "unit": canonical}

    if not normalized:
        return {
            **result,
            "reason": "all_metric_units_unverified",
            "excluded_metrics": excluded,
        }
    return {
        **result,
        "state": "normalized",
        "metrics": normalized,
        "excluded_metrics": excluded,
    }


def validate_lighthouse_metric_unit_contract(evidence: Any) -> dict[str, Any]:
    """Validate the derived canonical-unit artifact fail-closed."""
    reasons: list[str] = []
    if not isinstance(evidence, dict):
        return {
            "version": LIGHTHOUSE_UNIT_INTEGRITY_VERSION,
            "valid": False,
            "reasons": ["evidence_not_object"],
        }
    if evidence.get("version") != LIGHTHOUSE_UNIT_NORMALIZATION_VERSION:
        reasons.append("version_mismatch")
    if evidence.get("evidence_kind") != "lab_metric_units":
        reasons.append("evidence_kind_mismatch")
    state = evidence.get("state")
    if state not in NORMALIZATION_STATES:
        reasons.append("state_invalid")
    if evidence.get("source_version") != SOURCE_LIGHTHOUSE_VERSION:
        reasons.append("source_version_mismatch")
    source_state = evidence.get("source_state")
    if source_state not in SOURCE_STATES:
        reasons.append("source_state_invalid")

    metrics = evidence.get("metrics")
    excluded = evidence.get("excluded_metrics")
    if not isinstance(excluded, list):
        reasons.append("excluded_metrics_not_list")
        excluded = []

    normalized_names: set[str] = set()
    if state == "normalized":
        if source_state != "connected":
            reasons.append("normalized_source_not_connected")
        if not isinstance(metrics, dict) or not metrics:
            reasons.append("normalized_metrics_missing")
            metrics = {}
        for name, row in metrics.items():
            expected = CANONICAL_METRIC_UNITS.get(name)
            if expected is None:
                reasons.append("metric_unsupported")
                continue
            normalized_names.add(name)
            if not isinstance(row, dict):
                reasons.append("metric_not_object")
                continue
            if _number(row.get("value")) is None:
                reasons.append("metric_value_invalid")
            if row.get("unit") != expected:
                reasons.append("metric_unit_not_canonical")
    elif metrics is not None:
        reasons.append("non_normalized_retained_metrics")

    excluded_names: set[str] = set()
    for row in excluded:
        if not isinstance(row, dict):
            reasons.append("excluded_metric_not_object")
            continue
        name = row.get("metric")
        if not isinstance(name, str) or not name:
            reasons.append("excluded_metric_name_invalid")
            continue
        if name in excluded_names:
            reasons.append("excluded_metric_duplicate")
        excluded_names.add(name)
        if row.get("reason") not in EXCLUSION_REASONS:
            reasons.append("excluded_metric_reason_invalid")
        expected = CANONICAL_METRIC_UNITS.get(name)
        if row.get("expected_unit") != expected:
            reasons.append("excluded_metric_expected_unit_mismatch")
        raw_unit = row.get("raw_unit")
        if raw_unit is not None and not isinstance(raw_unit, str):
            reasons.append("excluded_metric_raw_unit_invalid")
    if normalized_names & excluded_names:
        reasons.append("metric_both_normalized_and_excluded")

    reason = evidence.get("reason")
    if state == "normalized":
        if reason is not None:
            reasons.append("normalized_reason_present")
    elif state == "not_applicable":
        if source_state != "connected":
            reasons.append("not_applicable_source_not_connected")
        if reason != "source_metrics_absent":
            reasons.append("not_applicable_reason_invalid")
        if excluded:
            reasons.append("not_applicable_with_exclusions")
    elif state == "not_verified":
        if not isinstance(reason, str) or not reason:
            reasons.append("not_verified_reason_missing")

    return {
        "version": LIGHTHOUSE_UNIT_INTEGRITY_VERSION,
        "valid": not reasons,
        "reasons": sorted(set(reasons)),
    }
