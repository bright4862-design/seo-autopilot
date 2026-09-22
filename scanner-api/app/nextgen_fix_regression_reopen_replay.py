from __future__ import annotations

from typing import Any

from .nextgen_fix_verification import COULD_NOT_VERIFY
from .nextgen_fix_verification_origin_binding import (
    evaluate_verification_observations_origin_bound,
)
from .nextgen_fix_verification_integrity import strict_regression_reopen_decision

STRICT_REGRESSION_REOPEN_OBSERVATION_REPLAY_VERSION = (
    "fix_regression_reopen_observation_replay_v4_exact_scan_origin_binding"
)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _denied(
    reason: str,
    *,
    recomputed_result: dict[str, Any] | None = None,
    replay: dict[str, Any] | None = None,
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
    isolation. This final pure replay path recomputes that result and now binds
    historical, plan, page, and rule-evaluation URL evidence to exact canonical
    caller-owned scan origins before FAIL/PARTIAL may prove a regression reopen.

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
        denied = _denied("verification_replay_failed")
        return {**denied, "verification_error_type": type(exc).__name__}

    if not isinstance(recomputed_result, dict):
        return _denied("verification_replay_returned_non_object")

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
        )
        return {**denied, "reopen_error_type": type(exc).__name__}

    if not isinstance(replay, dict):
        return _denied(
            "regression_reopen_replay_returned_non_object",
            recomputed_result=recomputed_result,
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
    }
