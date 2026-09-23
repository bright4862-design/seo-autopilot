from __future__ import annotations

from typing import Any

from .targeted_fix_verification import TARGETED_FIX_VERIFICATION_PURPOSE
from .targeted_fix_verification_execution_accounting import (
    TARGETED_FIX_VERIFICATION_EXECUTION_ACCOUNTING_VERSION,
    _observations,
    evaluate_executed_targeted_fix_verification_service,
    validate_targeted_verification_execution_accounting,
)
from .targeted_fix_verification_service_adapter import _service_could_not_verify

TARGETED_FIX_VERIFICATION_EXECUTION_EVIDENCE_VERSION = (
    "targeted_fix_verification_execution_evidence_v1_exact_scheduler_outcome_binding"
)


def _exact_nonempty_string(value: Any) -> str:
    return value if isinstance(value, str) and value and value == value.strip() else ""


def _exact_status_code(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _page_status_code(page: Any) -> int | None:
    if not isinstance(page, dict):
        return None
    if "status_code" in page:
        return _exact_status_code(page.get("status_code"))
    if "status" in page:
        return _exact_status_code(page.get("status"))
    return None


def _failure(reason: str, **extra: Any) -> dict[str, Any]:
    return {
        "version": TARGETED_FIX_VERIFICATION_EXECUTION_EVIDENCE_VERSION,
        "state": "could_not_verify",
        "reason": reason,
        "execution_accounting_version": TARGETED_FIX_VERIFICATION_EXECUTION_ACCOUNTING_VERSION,
        "bound_observation_count": 0,
        **extra,
    }


def validate_targeted_verification_execution_evidence_binding(
    plan: dict[str, Any],
    sealed_repair: dict[str, Any],
    *,
    preflight_scheduler_summary: dict[str, Any] | None,
    postflight_scheduler_summary: dict[str, Any] | None,
    recheck_outcomes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Bind each Lane-E recheck outcome to the exact shared-scheduler receipt.

    The shared scheduler remains the only request-accounting authority. This helper
    performs no I/O and does not interpret repair truth. It only prevents an outcome
    produced from unrelated, stale, redirected, or fabricated fetch evidence from
    being paired with an otherwise valid scheduler execution window.
    """
    accounting = validate_targeted_verification_execution_accounting(
        plan,
        sealed_repair,
        preflight_scheduler_summary=preflight_scheduler_summary,
        postflight_scheduler_summary=postflight_scheduler_summary,
    )
    if accounting.get("state") != "valid":
        return _failure(
            str(accounting.get("reason") or "targeted_execution_accounting_could_not_verify"),
            execution_accounting=accounting,
        )

    if not isinstance(preflight_scheduler_summary, dict) or not isinstance(
        postflight_scheduler_summary, dict
    ):
        return _failure("shared_scheduler_snapshot_invalid")

    pre_observations, error = _observations(preflight_scheduler_summary)
    if error:
        return _failure(error)
    post_observations, error = _observations(postflight_scheduler_summary)
    if error:
        return _failure(error)
    new_observations = post_observations[len(pre_observations) :]

    requests = plan.get("requests") if isinstance(plan, dict) else None
    if not isinstance(requests, list) or not requests:
        return _failure("verification_plan_requests_invalid")
    planned_keys = [row.get("evidence_key") for row in requests if isinstance(row, dict)]
    if (
        len(planned_keys) != len(requests)
        or any(not _exact_nonempty_string(key) for key in planned_keys)
        or len(set(planned_keys)) != len(planned_keys)
    ):
        return _failure("verification_plan_request_identity_invalid")

    if not isinstance(recheck_outcomes, list):
        return _failure("recheck_outcomes_invalid")
    if len(recheck_outcomes) != len(planned_keys):
        return _failure("recheck_outcome_population_mismatch")

    outcome_by_key: dict[str, dict[str, Any]] = {}
    for outcome in recheck_outcomes:
        if not isinstance(outcome, dict):
            return _failure("recheck_outcome_transport_invalid")
        key = _exact_nonempty_string(outcome.get("evidence_key"))
        if key not in planned_keys:
            return _failure("recheck_outcome_outside_planned_scope", blocked_evidence_key=key)
        if key in outcome_by_key:
            return _failure("duplicate_recheck_outcome", blocked_evidence_key=key)
        outcome_by_key[key] = outcome

    observation_by_key: dict[str, dict[str, Any]] = {}
    for observation in new_observations:
        if not isinstance(observation, dict):
            return _failure("targeted_scheduler_observation_transport_invalid")
        if observation.get("purpose") != TARGETED_FIX_VERIFICATION_PURPOSE:
            return _failure("non_targeted_scheduler_observation_inside_execution_window")
        key = _exact_nonempty_string(observation.get("observed_url"))
        if key not in planned_keys:
            return _failure("targeted_scheduler_observation_outside_plan", blocked_evidence_key=key)
        if key in observation_by_key:
            return _failure("duplicate_targeted_scheduler_observation", blocked_evidence_key=key)
        observation_by_key[key] = observation

    if set(outcome_by_key) != set(planned_keys) or set(observation_by_key) != set(planned_keys):
        return _failure("scheduler_outcome_population_mismatch")

    bound_count = 0
    for key in planned_keys:
        observation = observation_by_key[key]
        outcome = outcome_by_key[key]

        scheduler_ref = _exact_nonempty_string(observation.get("evidence_ref"))
        if not scheduler_ref:
            return _failure(
                "targeted_scheduler_evidence_ref_missing",
                blocked_evidence_key=key,
                bound_observation_count=bound_count,
            )
        outcome_ref = _exact_nonempty_string(outcome.get("scheduler_evidence_ref"))
        if not outcome_ref or outcome_ref != scheduler_ref:
            return _failure(
                "recheck_outcome_scheduler_evidence_ref_mismatch",
                blocked_evidence_key=key,
                bound_observation_count=bound_count,
            )

        scheduler_state = observation.get("state")
        outcome_state = outcome.get("state")
        scheduler_reason = _exact_nonempty_string(observation.get("reason"))

        if scheduler_state == "not_verified":
            if outcome_state != "not_verified":
                return _failure(
                    "scheduler_not_verified_outcome_state_mismatch",
                    blocked_evidence_key=key,
                    bound_observation_count=bound_count,
                )
            outcome_reason = _exact_nonempty_string(outcome.get("reason"))
            if not scheduler_reason or outcome_reason != scheduler_reason:
                return _failure(
                    "scheduler_not_verified_reason_mismatch",
                    blocked_evidence_key=key,
                    bound_observation_count=bound_count,
                )
            if "page" in outcome:
                return _failure(
                    "scheduler_not_verified_outcome_carries_page_evidence",
                    blocked_evidence_key=key,
                    bound_observation_count=bound_count,
                )
            bound_count += 1
            continue

        if scheduler_state not in {"pass", "fail"}:
            return _failure(
                "targeted_scheduler_observation_state_invalid",
                blocked_evidence_key=key,
                bound_observation_count=bound_count,
            )
        if outcome_state != "observed":
            return _failure(
                "scheduler_observed_outcome_state_mismatch",
                blocked_evidence_key=key,
                bound_observation_count=bound_count,
            )

        scheduler_status = _exact_status_code(observation.get("status_code"))
        page = outcome.get("page")
        page_status = _page_status_code(page)
        if scheduler_status is None or page_status is None or scheduler_status != page_status:
            return _failure(
                "scheduler_page_status_mismatch",
                blocked_evidence_key=key,
                bound_observation_count=bound_count,
            )

        final_url = _exact_nonempty_string(observation.get("final_url"))
        if not final_url:
            return _failure(
                "targeted_scheduler_final_url_missing",
                blocked_evidence_key=key,
                bound_observation_count=bound_count,
            )
        # A changed redirect identity is not proof that the original affected URL
        # was repaired. Keep it incomparable rather than letting disappearance or
        # movement be interpreted as a successful fix.
        if final_url != key:
            return _failure(
                "targeted_scheduler_final_url_changed",
                blocked_evidence_key=key,
                bound_observation_count=bound_count,
            )
        if not isinstance(page, dict):
            return _failure(
                "observed_page_evidence_missing",
                blocked_evidence_key=key,
                bound_observation_count=bound_count,
            )
        page_final_url = _exact_nonempty_string(page.get("final_url"))
        if not page_final_url or page_final_url != final_url:
            return _failure(
                "scheduler_page_final_url_mismatch",
                blocked_evidence_key=key,
                bound_observation_count=bound_count,
            )
        bound_count += 1

    return {
        "version": TARGETED_FIX_VERIFICATION_EXECUTION_EVIDENCE_VERSION,
        "state": "valid",
        "reason": "exact_scheduler_receipts_bound_to_recheck_outcomes",
        "execution_accounting_version": TARGETED_FIX_VERIFICATION_EXECUTION_ACCOUNTING_VERSION,
        "bound_observation_count": bound_count,
    }


def evaluate_execution_bound_targeted_fix_verification_service(
    prepared: dict[str, Any],
    sealed_repair: dict[str, Any],
    *,
    preflight_scheduler_summary: dict[str, Any] | None,
    postflight_scheduler_summary: dict[str, Any] | None,
    current_scan_origin: str,
    current_contract: dict[str, Any] | None,
    recheck_outcomes: list[dict[str, Any]],
    current_fixes: list[dict[str, Any]],
    rule_evaluation_receipt: dict[str, Any] | None,
) -> dict[str, Any]:
    """Require exact scheduler/evidence binding, then delegate repair truth unchanged."""
    plan = prepared.get("plan") if isinstance(prepared, dict) else {}
    binding = validate_targeted_verification_execution_evidence_binding(
        plan if isinstance(plan, dict) else {},
        sealed_repair,
        preflight_scheduler_summary=preflight_scheduler_summary,
        postflight_scheduler_summary=postflight_scheduler_summary,
        recheck_outcomes=recheck_outcomes,
    )
    if binding.get("state") != "valid":
        return _service_could_not_verify(
            prepared,
            str(binding.get("reason") or "targeted_execution_evidence_could_not_verify"),
            execution_evidence_version=TARGETED_FIX_VERIFICATION_EXECUTION_EVIDENCE_VERSION,
            execution_evidence=binding,
        )

    result = evaluate_executed_targeted_fix_verification_service(
        prepared,
        sealed_repair,
        preflight_scheduler_summary=preflight_scheduler_summary,
        postflight_scheduler_summary=postflight_scheduler_summary,
        current_scan_origin=current_scan_origin,
        current_contract=current_contract,
        recheck_outcomes=recheck_outcomes,
        current_fixes=current_fixes,
        rule_evaluation_receipt=rule_evaluation_receipt,
    )
    return {
        **result,
        "execution_evidence_version": TARGETED_FIX_VERIFICATION_EXECUTION_EVIDENCE_VERSION,
        "execution_evidence": binding,
        "side_effects_performed": False,
    }
