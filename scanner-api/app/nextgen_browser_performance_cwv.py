"""Pure Core Web Vitals assessment over trusted Lane-C field evidence.

This module performs no network I/O and never uses Lighthouse lab evidence to
infer field Core Web Vitals. It consumes only the existing normalized field
contract and keeps unknown/incomplete coverage explicit.
"""
from __future__ import annotations

from typing import Any

from app.nextgen_browser_performance_contract import validate_field_performance_contract

CWV_FIELD_ASSESSMENT_VERSION = "nextgen_cwv_field_assessment_v1"
CWV_REQUIRED_METRICS = ("lcp", "inp", "cls")
CWV_THRESHOLDS = {
    "lcp": {"unit": "ms", "good_max": 2500.0, "needs_improvement_max": 4000.0},
    "inp": {"unit": "ms", "good_max": 200.0, "needs_improvement_max": 500.0},
    "cls": {"unit": "score", "good_max": 0.1, "needs_improvement_max": 0.25},
}


def _rating(metric: str, value: float) -> str:
    thresholds = CWV_THRESHOLDS[metric]
    if value <= thresholds["good_max"]:
        return "good"
    if value <= thresholds["needs_improvement_max"]:
        return "needs_improvement"
    return "poor"


def _base(field_evidence: Any) -> dict[str, Any]:
    provider = field_evidence.get("provider") if isinstance(field_evidence, dict) else None
    source_state = field_evidence.get("state") if isinstance(field_evidence, dict) else None
    return {
        "version": CWV_FIELD_ASSESSMENT_VERSION,
        "evidence_kind": "field_assessment",
        "assessment": "core_web_vitals",
        "provider": provider,
        "source_state": source_state,
        "state": "not_verified",
        "reason": None,
        "required_metrics": list(CWV_REQUIRED_METRICS),
        "observed_required_metrics": 0,
        "missing_required_metrics": list(CWV_REQUIRED_METRICS),
        "coverage_complete": False,
        "metrics": {},
        "non_good_metrics": [],
        "provider_rating_mismatches": [],
    }


def assess_core_web_vitals_field_evidence(field_evidence: Any) -> dict[str, Any]:
    """Assess field Core Web Vitals without laundering lab evidence into field truth.

    A known non-good required metric is enough to prove that the all-good CWV
    assessment does not pass. If every observed required metric is good but one
    or more required metrics are absent, the result remains ``not_verified``.
    """
    result = _base(field_evidence)
    contract = validate_field_performance_contract(field_evidence)
    if not contract["valid"]:
        result["reason"] = "field_contract_invalid"
        result["contract_reasons"] = list(contract["reasons"])
        return result

    if field_evidence["state"] != "connected":
        result["reason"] = f"field_evidence_{field_evidence['state']}"
        return result

    source_metrics = field_evidence.get("metrics") or {}
    observed: dict[str, dict[str, Any]] = {}
    mismatches: list[str] = []
    non_good: list[str] = []
    for name in CWV_REQUIRED_METRICS:
        metric = source_metrics.get(name)
        if not isinstance(metric, dict):
            continue
        value = float(metric["value"])
        derived_rating = _rating(name, value)
        provider_rating = metric.get("rating")
        if provider_rating is not None and provider_rating != derived_rating:
            mismatches.append(name)
        if derived_rating != "good":
            non_good.append(name)
        observed[name] = {
            "value": value,
            "unit": CWV_THRESHOLDS[name]["unit"],
            "derived_rating": derived_rating,
            "provider_rating": provider_rating,
            "good_max": CWV_THRESHOLDS[name]["good_max"],
            "needs_improvement_max": CWV_THRESHOLDS[name]["needs_improvement_max"],
        }

    missing = [name for name in CWV_REQUIRED_METRICS if name not in observed]
    result.update({
        "observed_required_metrics": len(observed),
        "missing_required_metrics": missing,
        "coverage_complete": not missing,
        "metrics": observed,
        "non_good_metrics": non_good,
        "provider_rating_mismatches": mismatches,
    })

    if non_good:
        result["state"] = "failed"
        result["reason"] = "required_metric_not_good"
        return result
    if missing:
        result["reason"] = "core_web_vitals_metrics_incomplete"
        return result

    result["state"] = "passed"
    result["reason"] = "all_required_field_metrics_good"
    return result
