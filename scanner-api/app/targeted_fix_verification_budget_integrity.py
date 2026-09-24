from __future__ import annotations

from typing import Any

from .coverage_probes import COVERAGE_PROBE_SCHEDULER_VERSION
from .targeted_fix_verification import (
    MAX_TARGETED_RECHECK_URLS,
    TARGETED_FIX_VERIFICATION_BUDGET_VERSION,
    TARGETED_FIX_VERIFICATION_PLAN_VERSION,
    TARGETED_FIX_VERIFICATION_PURPOSE,
    _key_origin,
    _origin_root,
    _validate_plan_against_repair,
    targeted_verification_budget_proposal,
)

TARGETED_FIX_VERIFICATION_BUDGET_INTEGRITY_VERSION = (
    "targeted_fix_verification_budget_integrity_v1_exact_shared_scheduler_snapshot"
)


def _exact_nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _exact_positive_int(value: Any) -> int | None:
    parsed = _exact_nonnegative_int(value)
    return parsed if parsed is not None and parsed > 0 else None


def _exact_nonempty_string(value: Any) -> str:
    return value if isinstance(value, str) and value and value == value.strip() else ""


def _plan_transport_error(plan: Any, sealed_repair: Any) -> str:
    if not isinstance(plan, dict) or not isinstance(sealed_repair, dict):
        return "verification_plan_inputs_invalid"

    canonical_error = _validate_plan_against_repair(plan, sealed_repair)
    if canonical_error:
        return canonical_error

    if plan.get("version") != TARGETED_FIX_VERIFICATION_PLAN_VERSION:
        return "verification_plan_version_mismatch"
    if plan.get("state") != "ready" or plan.get("population_complete") is not True:
        return "verification_plan_not_ready"
    if plan.get("blockers") != []:
        return "verification_plan_ready_with_blockers"

    requests = plan.get("requests")
    if not isinstance(requests, list) or not requests:
        return "verification_plan_requests_invalid"

    sealed_count = _exact_positive_int(plan.get("sealed_population_count"))
    selected_count = _exact_positive_int(plan.get("selected_population_count"))
    max_targeted = _exact_positive_int(plan.get("max_targeted_urls"))
    if sealed_count is None or selected_count is None:
        return "verification_plan_population_count_invalid"
    if max_targeted is None or max_targeted > MAX_TARGETED_RECHECK_URLS:
        return "verification_plan_max_targeted_urls_invalid"
    if sealed_count != selected_count or selected_count != len(requests):
        return "verification_plan_population_count_mismatch"
    if len(requests) > max_targeted:
        return "verification_plan_population_exceeds_declared_bound"

    source_origin = _exact_nonempty_string(plan.get("source_scan_origin"))
    canonical_origin = _origin_root(source_origin) if source_origin else ""
    if not canonical_origin or canonical_origin != source_origin:
        return "verification_plan_source_origin_invalid"

    repair_fingerprint = _exact_nonempty_string(plan.get("repair_fingerprint"))
    rule_version = _exact_nonempty_string(plan.get("rule_definition_version"))
    comparison_version = _exact_nonempty_string(plan.get("comparison_profile_version"))
    evidence_version = _exact_nonempty_string(plan.get("evidence_url_identity_version"))
    if not all((repair_fingerprint, rule_version, comparison_version, evidence_version)):
        return "verification_plan_contract_identity_invalid"

    seen: set[str] = set()
    for request in requests:
        if not isinstance(request, dict):
            return "verification_plan_request_transport_invalid"
        if request.get("purpose") != TARGETED_FIX_VERIFICATION_PURPOSE:
            return "verification_plan_request_purpose_mismatch"
        evidence_key = _exact_nonempty_string(request.get("evidence_key"))
        request_url = _exact_nonempty_string(request.get("url"))
        if not evidence_key or request_url != evidence_key:
            return "verification_plan_request_url_identity_mismatch"
        if _key_origin(evidence_key) != source_origin:
            return "verification_plan_request_origin_mismatch"
        if evidence_key in seen:
            return "verification_plan_duplicate_request_identity"
        seen.add(evidence_key)
        if request.get("repair_fingerprint") != repair_fingerprint:
            return "verification_plan_request_repair_identity_mismatch"
        if request.get("rule_definition_version") != rule_version:
            return "verification_plan_request_rule_version_mismatch"
        if request.get("comparison_profile_version") != comparison_version:
            return "verification_plan_request_comparison_version_mismatch"
        if request.get("evidence_url_identity_version") != evidence_version:
            return "verification_plan_request_evidence_identity_version_mismatch"

    shared = plan.get("shared_scheduler")
    if not isinstance(shared, dict):
        return "verification_plan_shared_scheduler_contract_missing"
    if shared.get("version") != COVERAGE_PROBE_SCHEDULER_VERSION:
        return "verification_plan_shared_scheduler_version_mismatch"
    if shared.get("purpose") != TARGETED_FIX_VERIFICATION_PURPOSE:
        return "verification_plan_shared_scheduler_purpose_mismatch"
    worst_case = _exact_nonnegative_int(shared.get("worst_case_new_requests"))
    if worst_case != len(requests):
        return "verification_plan_shared_scheduler_request_count_mismatch"
    if shared.get("must_share_existing_request_limit") is not True:
        return "verification_plan_shared_scheduler_limit_contract_mismatch"
    if shared.get("cache_reuse_may_reduce_actual_requests") is not True:
        return "verification_plan_shared_scheduler_cache_contract_mismatch"
    return ""


def validate_shared_scheduler_snapshot(scheduler_summary: Any) -> dict[str, Any]:
    """Validate one exact summary emitted by the existing shared probe scheduler.

    This helper does not create, reserve, or spend budget. It only proves that the
    supplied accounting snapshot is self-consistent under the existing scheduler
    contract before Lane E uses it for a worst-case fit decision.
    """
    base = {
        "version": TARGETED_FIX_VERIFICATION_BUDGET_INTEGRITY_VERSION,
        "state": "could_not_verify",
        "reason": "shared_scheduler_summary_unavailable",
        "requests_remaining": 0,
    }
    if not isinstance(scheduler_summary, dict):
        return base
    if scheduler_summary.get("version") != COVERAGE_PROBE_SCHEDULER_VERSION:
        return {**base, "reason": "shared_scheduler_version_mismatch"}

    budget = scheduler_summary.get("request_budget")
    if not isinstance(budget, dict):
        return {**base, "reason": "shared_scheduler_budget_missing"}

    names = (
        "configured_probe_requests",
        "shared_request_limit",
        "crawl_requests_consumed",
        "requests_consumed",
        "requests_reused",
        "requests_remaining",
    )
    parsed: dict[str, int] = {}
    for name in names:
        value = _exact_nonnegative_int(budget.get(name))
        if value is None:
            return {**base, "reason": f"shared_scheduler_{name}_invalid"}
        parsed[name] = value

    if budget.get("budget_exhausted") not in {True, False} or not isinstance(budget.get("budget_exhausted"), bool):
        return {**base, "reason": "shared_scheduler_budget_exhausted_flag_invalid"}
    if budget.get("deadline_exhausted") not in {True, False} or not isinstance(budget.get("deadline_exhausted"), bool):
        return {**base, "reason": "shared_scheduler_deadline_exhausted_flag_invalid"}

    if parsed["requests_consumed"] > parsed["configured_probe_requests"]:
        return {**base, "reason": "shared_scheduler_probe_consumption_inconsistent"}

    remaining_probe = max(0, parsed["configured_probe_requests"] - parsed["requests_consumed"])
    remaining_shared = max(
        0,
        parsed["shared_request_limit"]
        - parsed["crawl_requests_consumed"]
        - parsed["requests_consumed"],
    )
    expected_remaining = min(remaining_probe, remaining_shared)
    if parsed["requests_remaining"] != expected_remaining:
        return {
            **base,
            "reason": "shared_scheduler_remaining_budget_inconsistent",
            "requests_remaining": parsed["requests_remaining"],
        }
    if budget.get("budget_exhausted") is True and expected_remaining != 0:
        return {
            **base,
            "reason": "shared_scheduler_exhaustion_flag_inconsistent",
            "requests_remaining": expected_remaining,
        }

    return {
        **base,
        "state": "valid",
        "reason": "exact_shared_scheduler_snapshot",
        "requests_remaining": expected_remaining,
        "budget_exhausted": budget["budget_exhausted"],
        "deadline_exhausted": budget["deadline_exhausted"],
    }


def strict_targeted_verification_budget_proposal(
    plan: dict[str, Any],
    sealed_repair: dict[str, Any],
    scheduler_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    """Fail closed unless both the sealed plan and shared-budget snapshot are exact.

    The underlying Lane-E proposal and the shared scheduler retain their existing
    semantics. This function adds transport/invariant checking only; it does not
    create a second request pool or change any Standard-150/global budget.
    """
    plan_error = _plan_transport_error(plan, sealed_repair)
    if plan_error:
        return {
            "version": TARGETED_FIX_VERIFICATION_BUDGET_VERSION,
            "integrity_version": TARGETED_FIX_VERIFICATION_BUDGET_INTEGRITY_VERSION,
            "state": "could_not_verify",
            "reason": plan_error,
            "shared_scheduler_version": COVERAGE_PROBE_SCHEDULER_VERSION,
            "required_new_request_upper_bound": len(plan.get("requests") or []) if isinstance(plan, dict) else 0,
            "requests_remaining": 0,
        }

    snapshot = validate_shared_scheduler_snapshot(scheduler_summary)
    if snapshot.get("state") != "valid":
        return {
            "version": TARGETED_FIX_VERIFICATION_BUDGET_VERSION,
            "integrity_version": TARGETED_FIX_VERIFICATION_BUDGET_INTEGRITY_VERSION,
            "state": "could_not_verify",
            "reason": snapshot.get("reason", "shared_scheduler_snapshot_invalid"),
            "shared_scheduler_version": COVERAGE_PROBE_SCHEDULER_VERSION,
            "required_new_request_upper_bound": len(plan.get("requests") or []),
            "requests_remaining": snapshot.get("requests_remaining", 0),
        }

    result = targeted_verification_budget_proposal(plan, scheduler_summary)
    return {
        **result,
        "integrity_version": TARGETED_FIX_VERIFICATION_BUDGET_INTEGRITY_VERSION,
    }
