from __future__ import annotations

from typing import Any

from .nextgen_fix_verification import COULD_NOT_VERIFY, evaluate_verification_plan
from .nextgen_fix_verified_fixed_replay import strict_verified_fixed_transition_from_evidence

STRICT_VERIFIED_FIXED_OBSERVATION_REPLAY_VERSION = (
    "fix_verified_fixed_observation_replay_v1_recomputed_nextgen_and_legacy"
)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _denied(reason: str, *, recomputed_result: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "version": STRICT_VERIFIED_FIXED_OBSERVATION_REPLAY_VERSION,
        "allowed": False,
        "reason": reason,
        "recomputed_result": recomputed_result if isinstance(recomputed_result, dict) else {},
        "replay": {},
    }


def strict_verified_fixed_transition_from_observations(
    previous_record: dict[str, Any],
    plan: dict[str, Any],
    current_pages: list[dict[str, Any]],
    rule_evaluations: list[dict[str, Any]],
    current_fixes: list[dict[str, Any]],
    current_contract: dict[str, Any],
    *,
    previous_scan_origin: str = "",
    scan_origin: str = "",
) -> dict[str, Any]:
    """Recompute both verification proofs from current observations.

    The lower-level replay helper already prevents a transported legacy comparator
    from authorizing ``verified_fixed``. This boundary removes the analogous trust
    in a transported NextGen PASS: it recomputes the verification result from the
    exact plan, current page observations, rule evaluations, and comparison
    contract before recomputing the historical comparator over the same current
    page/fix evidence.

    The function is pure. It performs no network work and does not mutate durable
    workflow, authority, persistence, customer projection, admission, or release
    state.
    """
    if not isinstance(previous_record, dict):
        return _denied("previous_record_not_an_object")
    if not isinstance(plan, dict):
        return _denied("verification_plan_not_an_object")
    if not isinstance(current_pages, list):
        return _denied("current_pages_not_a_list")
    if not isinstance(rule_evaluations, list):
        return _denied("rule_evaluations_not_a_list")
    if not isinstance(current_fixes, list):
        return _denied("current_fixes_not_a_list")
    if not isinstance(current_contract, dict):
        return _denied("current_contract_not_an_object")
    if any(not isinstance(item, dict) for item in current_pages):
        return _denied("current_pages_contains_non_object")
    if any(not isinstance(item, dict) for item in rule_evaluations):
        return _denied("rule_evaluations_contains_non_object")
    if any(not isinstance(item, dict) for item in current_fixes):
        return _denied("current_fixes_contains_non_object")
    if not isinstance(previous_scan_origin, str) or previous_scan_origin != previous_scan_origin.strip():
        return _denied("previous_scan_origin_invalid")
    if not isinstance(scan_origin, str) or scan_origin != scan_origin.strip():
        return _denied("scan_origin_invalid")

    try:
        recomputed_result = evaluate_verification_plan(
            plan,
            previous_record,
            current_pages,
            rule_evaluations,
            current_contract,
            scan_origin=scan_origin,
        )
    except (KeyError, TypeError, ValueError) as exc:
        return {
            **_denied("nextgen_verification_replay_failed"),
            "verification_error_type": type(exc).__name__,
        }

    if not isinstance(recomputed_result, dict):
        return _denied("nextgen_verification_returned_non_object")

    replay = strict_verified_fixed_transition_from_evidence(
        previous_record,
        recomputed_result,
        current_fixes,
        current_pages,
        current_contract,
        previous_scan_origin=previous_scan_origin,
        scan_origin=scan_origin,
    )
    if not isinstance(replay, dict):
        return _denied(
            "legacy_replay_returned_non_object",
            recomputed_result=recomputed_result,
        )

    allowed = replay.get("allowed") is True
    result_state = _clean(recomputed_result.get("state")).upper() or COULD_NOT_VERIFY
    reason = (
        "nextgen_and_legacy_proofs_recomputed_and_transition_proven"
        if allowed
        else f"recomputed_transition_denied:{_clean(replay.get('reason')) or 'not_proven'}"
    )
    return {
        "version": STRICT_VERIFIED_FIXED_OBSERVATION_REPLAY_VERSION,
        "allowed": allowed,
        "reason": reason,
        "repair_fingerprint": _clean(replay.get("repair_fingerprint")),
        "recomputed_verification_state": result_state,
        "recomputed_result": recomputed_result,
        "replay": replay,
    }
