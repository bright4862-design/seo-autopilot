from __future__ import annotations

from typing import Any

from .coverage_probes import COVERAGE_PROBE_SCHEDULER_VERSION
from .targeted_fix_verification import (
    TARGETED_FIX_VERIFICATION_PLAN_VERSION,
    TARGETED_FIX_VERIFICATION_PURPOSE,
)
from .targeted_fix_verification_budget_integrity import (
    _plan_transport_error,
    validate_shared_scheduler_snapshot,
)
from .targeted_fix_verification_service_adapter import (
    TARGETED_FIX_VERIFICATION_SERVICE_ADAPTER_VERSION,
    _service_could_not_verify,
    evaluate_prepared_targeted_fix_verification_service,
)

TARGETED_FIX_VERIFICATION_EXECUTION_ACCOUNTING_VERSION = (
    "targeted_fix_verification_execution_accounting_v1_exact_shared_scheduler_delta"
)

_PURPOSE_STAT_KEYS = (
    "eligible",
    "selected",
    "attempted",
    "completed",
    "passed",
    "failed",
    "not_verified",
    "skipped",
    "exhausted",
)


def _exact_nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _exact_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _budget(summary: dict[str, Any]) -> dict[str, Any]:
    value = summary.get("request_budget")
    return value if isinstance(value, dict) else {}


def _purpose_stats(summary: dict[str, Any], purpose: str) -> tuple[dict[str, int], str]:
    purposes = summary.get("purposes")
    if purposes is None:
        purposes = {}
    if not isinstance(purposes, dict):
        return {}, "shared_scheduler_purposes_invalid"
    raw = purposes.get(purpose)
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        return {}, "targeted_scheduler_purpose_stats_invalid"

    out: dict[str, int] = {}
    for key in _PURPOSE_STAT_KEYS:
        if key not in raw:
            out[key] = 0
            continue
        parsed = _exact_nonnegative_int(raw.get(key))
        if parsed is None:
            return {}, f"targeted_scheduler_{key}_invalid"
        out[key] = parsed
    return out, ""


def _observations(summary: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    truncated = _exact_bool(summary.get("observation_samples_truncated"))
    if truncated is None:
        return [], "shared_scheduler_observation_truncation_flag_invalid"
    if truncated:
        return [], "shared_scheduler_observations_truncated"

    raw = summary.get("observations")
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        return [], "shared_scheduler_observations_invalid"
    if any(not isinstance(item, dict) for item in raw):
        return [], "shared_scheduler_observation_transport_invalid"
    return list(raw), ""


def _failure(reason: str, **extra: Any) -> dict[str, Any]:
    return {
        "version": TARGETED_FIX_VERIFICATION_EXECUTION_ACCOUNTING_VERSION,
        "state": "could_not_verify",
        "reason": reason,
        "requests_consumed_delta": 0,
        "requests_reused_delta": 0,
        "targeted_attempted_delta": 0,
        "targeted_completed_delta": 0,
        **extra,
    }


def validate_targeted_verification_execution_accounting(
    plan: dict[str, Any],
    sealed_repair: dict[str, Any],
    *,
    preflight_scheduler_summary: dict[str, Any] | None,
    postflight_scheduler_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    """Prove a bounded targeted run is a monotonic continuation of one shared scheduler.

    This helper performs no I/O and never decides repair truth. It only validates
    that an exact ready Lane-E plan was executed inside one unchanged shared-budget
    envelope and that one bounded scheduler observation exists for each planned URL.
    PASS/PARTIAL/FAIL remain owned by the existing comparator-backed evaluator.
    """
    plan_error = _plan_transport_error(plan, sealed_repair)
    if plan_error:
        return _failure(plan_error)
    if plan.get("version") != TARGETED_FIX_VERIFICATION_PLAN_VERSION:
        return _failure("verification_plan_version_mismatch")
    if plan.get("state") != "ready" or plan.get("population_complete") is not True:
        return _failure("verification_plan_not_ready")

    preflight = validate_shared_scheduler_snapshot(preflight_scheduler_summary)
    if preflight.get("state") != "valid":
        return _failure(
            str(preflight.get("reason") or "preflight_scheduler_snapshot_invalid")
        )
    postflight = validate_shared_scheduler_snapshot(postflight_scheduler_summary)
    if postflight.get("state") != "valid":
        return _failure(
            str(postflight.get("reason") or "postflight_scheduler_snapshot_invalid")
        )

    if not isinstance(preflight_scheduler_summary, dict) or not isinstance(
        postflight_scheduler_summary, dict
    ):
        return _failure("shared_scheduler_snapshot_invalid")
    if (
        preflight_scheduler_summary.get("version") != COVERAGE_PROBE_SCHEDULER_VERSION
        or postflight_scheduler_summary.get("version") != COVERAGE_PROBE_SCHEDULER_VERSION
    ):
        return _failure("shared_scheduler_version_mismatch")

    pre_budget = _budget(preflight_scheduler_summary)
    post_budget = _budget(postflight_scheduler_summary)
    for key in (
        "configured_probe_requests",
        "shared_request_limit",
        "crawl_requests_consumed",
    ):
        if pre_budget.get(key) != post_budget.get(key):
            return _failure(f"shared_scheduler_{key}_changed_during_execution")

    pre_consumed = _exact_nonnegative_int(pre_budget.get("requests_consumed"))
    post_consumed = _exact_nonnegative_int(post_budget.get("requests_consumed"))
    pre_reused = _exact_nonnegative_int(pre_budget.get("requests_reused"))
    post_reused = _exact_nonnegative_int(post_budget.get("requests_reused"))
    if None in {pre_consumed, post_consumed, pre_reused, post_reused}:
        return _failure("shared_scheduler_request_accounting_invalid")
    assert pre_consumed is not None
    assert post_consumed is not None
    assert pre_reused is not None
    assert post_reused is not None
    if post_consumed < pre_consumed:
        return _failure("shared_scheduler_requests_consumed_went_backwards")
    if post_reused < pre_reused:
        return _failure("shared_scheduler_requests_reused_went_backwards")

    consumed_delta = post_consumed - pre_consumed
    reused_delta = post_reused - pre_reused
    planned_requests = plan.get("requests")
    if not isinstance(planned_requests, list) or not planned_requests:
        return _failure("verification_plan_requests_invalid")

    request_upper_bound = plan.get("shared_scheduler", {}).get("worst_case_new_requests")
    if (
        isinstance(request_upper_bound, bool)
        or not isinstance(request_upper_bound, int)
        or request_upper_bound != len(planned_requests)
    ):
        return _failure("verification_plan_shared_scheduler_request_count_mismatch")
    if consumed_delta > request_upper_bound:
        return _failure(
            "targeted_execution_exceeded_declared_new_request_bound",
            requests_consumed_delta=consumed_delta,
            requests_reused_delta=reused_delta,
        )

    pre_stats, stats_error = _purpose_stats(
        preflight_scheduler_summary, TARGETED_FIX_VERIFICATION_PURPOSE
    )
    if stats_error:
        return _failure(stats_error)
    post_stats, stats_error = _purpose_stats(
        postflight_scheduler_summary, TARGETED_FIX_VERIFICATION_PURPOSE
    )
    if stats_error:
        return _failure(stats_error)
    for key in _PURPOSE_STAT_KEYS:
        if post_stats[key] < pre_stats[key]:
            return _failure(f"targeted_scheduler_{key}_went_backwards")

    attempted_delta = post_stats["attempted"] - pre_stats["attempted"]
    completed_delta = post_stats["completed"] - pre_stats["completed"]
    selected_delta = post_stats["selected"] - pre_stats["selected"]
    expected_count = len(planned_requests)
    if selected_delta != expected_count:
        return _failure(
            "targeted_scheduler_selected_population_mismatch",
            requests_consumed_delta=consumed_delta,
            requests_reused_delta=reused_delta,
            targeted_attempted_delta=attempted_delta,
            targeted_completed_delta=completed_delta,
        )
    if attempted_delta != expected_count:
        return _failure(
            "targeted_scheduler_attempted_population_mismatch",
            requests_consumed_delta=consumed_delta,
            requests_reused_delta=reused_delta,
            targeted_attempted_delta=attempted_delta,
            targeted_completed_delta=completed_delta,
        )

    terminal_delta = sum(
        post_stats[key] - pre_stats[key]
        for key in ("passed", "failed", "not_verified", "skipped", "exhausted")
    )
    if (
        completed_delta
        + (post_stats["skipped"] - pre_stats["skipped"])
        + (post_stats["exhausted"] - pre_stats["exhausted"])
        != expected_count
    ):
        return _failure(
            "targeted_scheduler_terminal_population_mismatch",
            requests_consumed_delta=consumed_delta,
            requests_reused_delta=reused_delta,
            targeted_attempted_delta=attempted_delta,
            targeted_completed_delta=completed_delta,
        )
    if terminal_delta != expected_count:
        return _failure(
            "targeted_scheduler_terminal_state_count_mismatch",
            requests_consumed_delta=consumed_delta,
            requests_reused_delta=reused_delta,
            targeted_attempted_delta=attempted_delta,
            targeted_completed_delta=completed_delta,
        )

    pre_observations, observation_error = _observations(preflight_scheduler_summary)
    if observation_error:
        return _failure(observation_error)
    post_observations, observation_error = _observations(postflight_scheduler_summary)
    if observation_error:
        return _failure(observation_error)
    if len(post_observations) < len(pre_observations):
        return _failure("shared_scheduler_observation_history_shrank")
    if post_observations[: len(pre_observations)] != pre_observations:
        return _failure("shared_scheduler_observation_history_rewritten")

    new_observations = post_observations[len(pre_observations) :]
    if len(new_observations) != expected_count:
        return _failure(
            "targeted_scheduler_observation_population_mismatch",
            requests_consumed_delta=consumed_delta,
            requests_reused_delta=reused_delta,
            targeted_attempted_delta=attempted_delta,
            targeted_completed_delta=completed_delta,
        )

    planned_urls = [row.get("url") for row in planned_requests]
    if any(not isinstance(url, str) or not url for url in planned_urls):
        return _failure("verification_plan_request_url_identity_mismatch")

    seen: set[str] = set()
    for observation in new_observations:
        if observation.get("purpose") != TARGETED_FIX_VERIFICATION_PURPOSE:
            return _failure("non_targeted_scheduler_observation_inside_execution_window")
        if observation.get("version") != COVERAGE_PROBE_SCHEDULER_VERSION:
            return _failure("targeted_scheduler_observation_version_mismatch")
        observed_url = observation.get("observed_url")
        if not isinstance(observed_url, str) or observed_url not in planned_urls:
            return _failure("targeted_scheduler_observation_outside_plan")
        if observed_url in seen:
            return _failure("duplicate_targeted_scheduler_observation")
        seen.add(observed_url)
        state = observation.get("state")
        if state not in {"pass", "fail", "not_verified"}:
            return _failure("targeted_scheduler_observation_state_invalid")

    if seen != set(planned_urls):
        return _failure("targeted_scheduler_observation_population_mismatch")

    return {
        "version": TARGETED_FIX_VERIFICATION_EXECUTION_ACCOUNTING_VERSION,
        "state": "valid",
        "reason": "exact_shared_scheduler_execution_delta",
        "scheduler_version": COVERAGE_PROBE_SCHEDULER_VERSION,
        "purpose": TARGETED_FIX_VERIFICATION_PURPOSE,
        "planned_url_count": expected_count,
        "requests_consumed_delta": consumed_delta,
        "requests_reused_delta": reused_delta,
        "targeted_selected_delta": selected_delta,
        "targeted_attempted_delta": attempted_delta,
        "targeted_completed_delta": completed_delta,
        "targeted_terminal_delta": terminal_delta,
    }


def evaluate_executed_targeted_fix_verification_service(
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
    """Bind real shared-scheduler execution before delegating repair truth unchanged."""
    if not isinstance(prepared, dict):
        return _service_could_not_verify(
            prepared,
            "prepared_verification_invalid",
            execution_accounting_version=TARGETED_FIX_VERIFICATION_EXECUTION_ACCOUNTING_VERSION,
        )
    if prepared.get("service_adapter_version") != TARGETED_FIX_VERIFICATION_SERVICE_ADAPTER_VERSION:
        return _service_could_not_verify(
            prepared,
            "prepared_verification_service_adapter_version_mismatch",
            execution_accounting_version=TARGETED_FIX_VERIFICATION_EXECUTION_ACCOUNTING_VERSION,
        )

    plan = prepared.get("plan")
    if not isinstance(plan, dict):
        return _service_could_not_verify(
            prepared,
            "prepared_verification_plan_missing",
            execution_accounting_version=TARGETED_FIX_VERIFICATION_EXECUTION_ACCOUNTING_VERSION,
        )

    accounting = validate_targeted_verification_execution_accounting(
        plan,
        sealed_repair,
        preflight_scheduler_summary=preflight_scheduler_summary,
        postflight_scheduler_summary=postflight_scheduler_summary,
    )
    if accounting.get("state") != "valid":
        return _service_could_not_verify(
            prepared,
            str(accounting.get("reason") or "targeted_execution_accounting_could_not_verify"),
            execution_accounting_version=TARGETED_FIX_VERIFICATION_EXECUTION_ACCOUNTING_VERSION,
            execution_accounting=accounting,
        )

    result = evaluate_prepared_targeted_fix_verification_service(
        prepared,
        sealed_repair,
        scheduler_summary=preflight_scheduler_summary,
        current_scan_origin=current_scan_origin,
        current_contract=current_contract,
        recheck_outcomes=recheck_outcomes,
        current_fixes=current_fixes,
        rule_evaluation_receipt=rule_evaluation_receipt,
    )
    return {
        **result,
        "execution_accounting_version": TARGETED_FIX_VERIFICATION_EXECUTION_ACCOUNTING_VERSION,
        "execution_accounting": accounting,
        "side_effects_performed": False,
    }
