from __future__ import annotations

from typing import Any

from .nextgen_fix_regression_state_integrity import (
    verification_historical_resolution_state_integrity,
)
from .nextgen_fix_verification import COULD_NOT_VERIFY
from .nextgen_fix_verification_origin_binding import (
    evaluate_verification_observations_origin_bound,
)
from .nextgen_fix_verification_integrity import strict_regression_reopen_decision

STRICT_REGRESSION_REOPEN_OBSERVATION_REPLAY_VERSION = (
    "fix_regression_reopen_observation_replay_v6_exact_historical_evidence_alias_binding"
)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _denied(
    reason: str,
    *,
    recomputed_result: dict[str, Any] | None = None,
    replay: dict[str, Any] | None = None,
    state_integrity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = recomputed_result if isinstance(recomputed_result, dict) else {}
    state = _clean(result.get("state")).upper() or COULD_NOT_VERIFY
    return {
        "version": STRICT_REGRESSION_REOPEN_OBSERVATION_REPLAY_VERSION,
        "should_reopen": False,
        "reason": reason,
        "repair_fingerprint": "",
        "reopen_scope": [],
        "recomputed_verification_state": state,
        "recomputed_result": result,
        "replay": replay if isinstance(replay, dict) else {},
        "historical_resolution_state_integrity": (
            state_integrity if isinstance(state_integrity, dict) else {}
        ),
    }


def strict_regression_reopen_from_observations(
    previous_record: dict[str, Any],
    plan: dict[str, Any],
    current_pages: list[dict[str, Any]],
    rule_evaluations: list[dict[str, Any]],
    current_contract: dict[str, Any],
    *,
    previous_scan_origin: str = "",
    scan_origin: str = "",
) -> dict[str, Any]:
    """Recompute current verification from exact source-bound observations.

    ``strict_regression_reopen_decision`` accepts a transported verification
    result so it can validate historical binding and state-machine semantics in
    isolation. This final pure replay path recomputes that result, binds
    historical/plan/page/rule evidence to exact canonical scan origins, proves
    populated historical evidence aliases agree with the selected historical
    population, and proves historical resolution-state aliases are exact and
    non-conflicting before FAIL/PARTIAL may reopen a repair.

    The function is pure. It performs no network work and does not mutate
    workflow state, durable authority, persistence, customer projection,
    admission, release, deployment, or production configuration.
    """
    if not isinstance(previous_record, dict):
        return _denied("previous_record_not_an_object")
    if not isinstance(plan, dict):
        return _denied("verification_plan_not_an_object")
    if not isinstance(current_pages, list):
        return _denied("current_pages_not_a_list")
    if not isinstance(rule_evaluations, list):
        return _denied("rule_evaluations_not_a_list")
    if not isinstance(current_contract, dict):
        return _denied("current_contract_not_an_object")
    if any(not isinstance(item, dict) for item in current_pages):
        return _denied("current_pages_contains_non_object")
    if any(not isinstance(item, dict) for item in rule_evaluations):
        return _denied("rule_evaluations_contains_non_object")
    if not isinstance(previous_scan_origin, str) or previous_scan_origin != previous_scan_origin.strip():
        return _denied("previous_scan_origin_invalid")
    if not isinstance(scan_origin, str) or scan_origin != scan_origin.strip():
        return _denied("scan_origin_invalid")

    state_integrity = verification_historical_resolution_state_integrity(previous_record)
    if state_integrity.get("valid") is not True:
        return _denied(
            "historical_resolution_state_integrity_failed",
            state_integrity=state_integrity,
        )
    if state_integrity.get("historical_resolved") is not True:
        return _denied(
            "previous_repair_was_not_verified_resolved",
            state_integrity=state_integrity,
        )

    try:
        recomputed_result = evaluate_verification_observations_origin_bound(
            plan,
            previous_record,
            current_pages,
            rule_evaluations,
            current_contract,
            previous_scan_origin=previous_scan_origin,
            scan_origin=scan_origin,
        )
    except (KeyError, TypeError, ValueError) as exc:
        denied = _denied(
            "verification_replay_failed",
            state_integrity=state_integrity,
        )
        return {**denied, "verification_error_type": type(exc).__name__}

    if not isinstance(recomputed_result, dict):
        return _denied(
            "verification_replay_returned_non_object",
            state_integrity=state_integrity,
        )

    try:
        replay = strict_regression_reopen_decision(
            previous_record,
            recomputed_result,
            previous_scan_origin=previous_scan_origin,
        )
    except (KeyError, TypeError, ValueError) as exc:
        denied = _denied(
            "regression_reopen_replay_failed",
            recomputed_result=recomputed_result,
            state_integrity=state_integrity,
        )
        return {**denied, "reopen_error_type": type(exc).__name__}

    if not isinstance(replay, dict):
        return _denied(
            "regression_reopen_replay_returned_non_object",
            recomputed_result=recomputed_result,
            state_integrity=state_integrity,
        )

    should_reopen = replay.get("should_reopen") is True
    state = _clean(recomputed_result.get("state")).upper() or COULD_NOT_VERIFY
    reason = (
        "current_verification_recomputed_and_regression_reopen_proven"
        if should_reopen
        else f"recomputed_regression_not_proven:{_clean(replay.get('reason')) or 'not_proven'}"
    )
    reopen_scope = replay.get("reopen_scope") if should_reopen else []
    if not isinstance(reopen_scope, list):
        return _denied(
            "regression_reopen_scope_not_a_list",
            recomputed_result=recomputed_result,
            replay=replay,
            state_integrity=state_integrity,
        )

    return {
        "version": STRICT_REGRESSION_REOPEN_OBSERVATION_REPLAY_VERSION,
        "should_reopen": should_reopen,
        "reason": reason,
        "repair_fingerprint": _clean(replay.get("repair_fingerprint")),
        "reopen_scope": list(reopen_scope),
        "recomputed_verification_state": state,
        "recomputed_result": recomputed_result,
        "replay": replay,
        "historical_resolution_state_integrity": state_integrity,
    }
