from __future__ import annotations

from typing import Any

from .nextgen_fix_verification import COULD_NOT_VERIFY, VERIFICATION_RESULT_VERSION
from .nextgen_fix_verification_historical_identity import (
    verification_historical_identity_integrity,
)
from .nextgen_fix_verification_observation_identity import (
    evaluate_verification_observations_identity_bound,
)

HISTORICAL_BOUND_OBSERVATION_VERSION = (
    "fix_verification_historical_bound_observation_v1_exact_repair_identity"
)


def _exact_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _strict_population_count(plan: dict[str, Any]) -> int:
    value = plan.get("population_count") if isinstance(plan, dict) else None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value


def _safe_exact_identity(plan: dict[str, Any], field: str) -> str:
    value = plan.get(field) if isinstance(plan, dict) else None
    return value if _exact_nonempty_string(value) else ""


def _could_not_verify(
    plan: dict[str, Any],
    reason: str,
    *,
    identity_integrity: dict[str, Any],
) -> dict[str, Any]:
    return {
        "version": VERIFICATION_RESULT_VERSION,
        "state": COULD_NOT_VERIFY,
        "reason": reason,
        "repair_fingerprint": _safe_exact_identity(plan, "repair_fingerprint"),
        "criterion_id": _safe_exact_identity(plan, "criterion_id"),
        "required_population_count": _strict_population_count(plan),
        "observed_population_count": 0,
        "evaluated_population_count": 0,
        "resolved_scope": [],
        "unresolved_scope": [],
        "unverifiable_scope": [],
        "historical_identity_integrity": identity_integrity,
        "historical_bound_observation_version": HISTORICAL_BOUND_OBSERVATION_VERSION,
    }


def evaluate_verification_observations_historical_bound(
    plan: dict[str, Any],
    previous_record: dict[str, Any],
    current_pages: list[dict[str, Any]],
    rule_evaluations: list[dict[str, Any]],
    current_contract: dict[str, Any],
    *,
    scan_origin: str = "",
) -> dict[str, Any]:
    """Require exact historical repair identity before current evidence can prove a state.

    Historical repair identity reconstruction remains intentionally tolerant for
    report compatibility. This final pure observation boundary prevents that
    tolerance from becoming proof: stable-identity source fields must already be
    exact strings and any persisted identity metadata that is present must agree
    with a freshly derived identity. Only then may the existing current-observation
    identity and metadata boundaries evaluate PASS/PARTIAL/FAIL.
    """
    identity_integrity = verification_historical_identity_integrity(previous_record)
    if identity_integrity.get("valid") is not True:
        return _could_not_verify(
            plan if isinstance(plan, dict) else {},
            "Historical repair identity integrity failed: "
            f"{identity_integrity.get('reason') or 'not_proven'}",
            identity_integrity=identity_integrity,
        )

    result = evaluate_verification_observations_identity_bound(
        plan,
        previous_record,
        current_pages,
        rule_evaluations,
        current_contract,
        scan_origin=scan_origin,
    )
    if not isinstance(result, dict):
        return _could_not_verify(
            plan if isinstance(plan, dict) else {},
            "Identity-bound verification evaluator returned non-object evidence.",
            identity_integrity=identity_integrity,
        )
    return {
        **result,
        "historical_identity_integrity": identity_integrity,
        "historical_bound_observation_version": HISTORICAL_BOUND_OBSERVATION_VERSION,
    }
