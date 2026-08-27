"""Fail-closed Standard 150 release-acceptance evidence projection.

Each required release dimension stays independent.  ``available=False`` means
that the acceptance path did not measure or project that dimension; a measured
absence is represented as an available neutral state instead.
"""

from __future__ import annotations

from typing import Any


REQUIRED_MATRIX_DIMENSIONS = (
    "infrastructure_outcome",
    "authority_outcome",
    "coverage_sufficiency",
    "classification_verdict",
    "evidence_quality_verdict",
    "ui_result_route_verdict",
    "duration",
    "memory_resource_result",
    "exact_release_markers",
    "limited_access_failure_class",
)

# Compatibility name retained from the earlier isolated helper candidate.
MATRIX_DIMENSIONS = REQUIRED_MATRIX_DIMENSIONS
TERMINAL_STATUSES = {"complete", "limited", "failed", "cancelled"}


def _clean(value: Any, limit: int = 200) -> str:
    return str(value or "").strip()[:limit]


def _nonnegative_number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return None
    return value


def _limited_access_failure_class(observation: dict[str, Any]) -> dict[str, Any]:
    run = observation.get("run") if isinstance(observation.get("run"), dict) else {}
    status = _clean(run.get("status") or observation.get("status"), 80).lower()
    error_code = _clean(run.get("error_code") or observation.get("error_code"), 160)
    failure_kind = _clean(run.get("customer_failure_kind"), 120)
    access_state = _clean(run.get("access_evidence_state"), 120)
    limitation = run.get("limitation")
    if isinstance(limitation, dict):
        limitation_code = _clean(limitation.get("code") or limitation.get("reason"), 160)
    else:
        limitation_code = _clean(limitation, 160)

    measured = status in TERMINAL_STATUSES or bool(
        error_code or failure_kind or access_state or limitation_code
    )
    if not measured:
        return {
            "available": False,
            "state": "unavailable",
            "limited": None,
            "failure_class": "",
        }

    access_signal = " ".join(
        (error_code, failure_kind, access_state, limitation_code)
    ).lower()
    limited = status == "limited" or any(
        token in access_signal
        for token in (
            "access_limited",
            "access limited",
            "rate_limit",
            "rate limit",
            "429",
            "challenge",
            "blocked_access",
            "robots",
        )
    ) or access_state.lower() in {"blocked", "limited", "access_limited"}

    return {
        "available": True,
        "state": "limited" if limited else "none",
        "limited": limited,
        "failure_class": (
            error_code
            or limitation_code
            or failure_kind
            or access_state
            or "limited_result"
        ) if limited else "",
    }


def build_acceptance_matrix(observation: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Project one harness observation without inventing missing evidence."""
    if not isinstance(observation, dict):
        observation = {}
    run = observation.get("run") if isinstance(observation.get("run"), dict) else {}
    result = (
        observation.get("customer_result")
        if isinstance(observation.get("customer_result"), dict)
        else {}
    )
    status = _clean(run.get("status") or observation.get("status"), 80).lower()
    error_code = _clean(run.get("error_code") or observation.get("error_code"), 160)

    coverage = run.get("coverage_authority_evidence")
    coverage = coverage if isinstance(coverage, dict) else {}
    coverage_state = _clean(coverage.get("state") or coverage.get("assessment"), 120)

    classification = run.get("classification_integrity")
    classification = classification if isinstance(classification, dict) else {}
    classification_state = _clean(
        classification.get("state")
        or classification.get("verdict")
        or run.get("classification_verdict"),
        160,
    )

    evidence_state = _clean(run.get("evidence_quality_state"), 120)
    requested_scan_id = _clean(observation.get("scan_id"), 160)
    projected_scan_id = _clean(result.get("scan_id"), 160)
    projected_run_id = _clean(run.get("id") or run.get("scan_id"), 160)
    route_available = bool(requested_scan_id and projected_scan_id and projected_run_id)
    route_exact = bool(
        route_available
        and requested_scan_id == projected_scan_id
        and requested_scan_id == projected_run_id
    )

    submitted_at = observation.get("submitted_at")
    terminal_at = observation.get("terminal_at")
    duration_ms = None
    if (
        isinstance(submitted_at, (int, float))
        and not isinstance(submitted_at, bool)
        and isinstance(terminal_at, (int, float))
        and not isinstance(terminal_at, bool)
        and submitted_at > 0
        and terminal_at >= submitted_at
    ):
        duration_ms = int((terminal_at - submitted_at) * 1000)

    peak_memory = _nonnegative_number(
        run.get("peak_memory_bytes")
        if run.get("peak_memory_bytes") is not None
        else run.get("worker_peak_memory_bytes")
    )
    resource_code = error_code if any(
        token in error_code.lower() for token in ("resource", "memory", "oom")
    ) else ""

    terminal_observed = status in TERMINAL_STATUSES
    if not terminal_observed or not result:
        authority_state = "unavailable"
    elif status == "complete":
        authority_state = "authoritative" if result.get("authority_verified") is True else "unverified"
    elif status == "limited":
        authority_state = "integrity_only" if result.get("result_integrity_verified") is True else "unverified"
    else:
        authority_state = "none"

    fingerprint = _clean(run.get("beta_revision_fingerprint"), 160)
    return {
        "infrastructure_outcome": {
            "available": bool(
                observation.get("http_status")
                or observation.get("accepted") is True
                or status
            ),
            "admission_http_status": int(observation.get("http_status") or 0),
            "accepted": observation.get("accepted") is True,
            "terminal_status": status,
            "failure_code": error_code,
        },
        "authority_outcome": {
            "available": terminal_observed and bool(result),
            "state": authority_state,
            "authority_verified": result.get("authority_verified") is True,
            "result_integrity_verified": result.get("result_integrity_verified") is True,
            "release_contract_current": result.get("release_contract_current") is True,
        },
        "coverage_sufficiency": {
            "available": bool(coverage_state),
            "state": coverage_state or "unavailable",
            "reason": "" if coverage_state else "coverage_authority_not_projected",
        },
        "classification_verdict": {
            "available": bool(classification_state),
            "state": classification_state or "unavailable",
            "classifier_version": _clean(run.get("archetype_classifier_version"), 160),
            "reason": "" if classification_state else "classification_verdict_not_projected",
        },
        "evidence_quality_verdict": {
            "available": bool(evidence_state),
            "state": evidence_state or "unavailable",
            "score": run.get("evidence_quality_score"),
            "blocking": run.get("evidence_quality_blocking") is True,
        },
        "ui_result_route_verdict": {
            "available": route_available,
            "state": "exact" if route_exact else ("mismatch" if route_available else "unavailable"),
            "requested_scan_id": requested_scan_id,
            "projected_scan_id": projected_scan_id,
            "projected_run_id": projected_run_id,
        },
        "duration": {
            "available": duration_ms is not None,
            "milliseconds": duration_ms,
        },
        "memory_resource_result": {
            "available": peak_memory is not None or bool(resource_code),
            "state": (
                "resource_failure"
                if resource_code
                else ("measured" if peak_memory is not None else "unavailable")
            ),
            "peak_memory_bytes": peak_memory,
            "failure_code": resource_code,
            "reason": "" if peak_memory is not None or resource_code else "peak_memory_or_resource_verdict_not_recorded",
        },
        "exact_release_markers": {
            "available": bool(fingerprint),
            "beta_revision_fingerprint": fingerprint,
            "scanner_version": _clean(run.get("scanner_version"), 160),
            "scanner_build_revision": _clean(run.get("scanner_build_revision"), 160),
            "review_version": _clean(run.get("review_version"), 160),
            "review_evidence_calibration_version": _clean(
                run.get("review_evidence_calibration_version"), 160
            ),
            "archetype_classifier_version": _clean(
                run.get("archetype_classifier_version"), 160
            ),
        },
        "limited_access_failure_class": _limited_access_failure_class(observation),
    }


def _matrix_contract_gaps(matrix: dict[str, Any]) -> list[str]:
    gaps: list[str] = []
    for name in REQUIRED_MATRIX_DIMENSIONS:
        dimension = matrix.get(name) if isinstance(matrix, dict) else None
        if not isinstance(dimension, dict) or dimension.get("available") is not True:
            gaps.append(name)
    route = matrix.get("ui_result_route_verdict") if isinstance(matrix, dict) else None
    if isinstance(route, dict) and route.get("available") is True and route.get("state") != "exact":
        gaps.append("ui_result_route_mismatch")
    return gaps
