from __future__ import annotations

from typing import Any

from .targeted_fix_verification import (
    MAX_TARGETED_RECHECK_URLS,
    TARGETED_FIX_VERIFICATION_BUDGET_VERSION,
    TARGETED_FIX_VERIFICATION_PLAN_VERSION,
    _could_not_verify,
    _fingerprint,
    build_targeted_recheck_plan,
)
from .targeted_fix_verification_budget_integrity import (
    TARGETED_FIX_VERIFICATION_BUDGET_INTEGRITY_VERSION,
    strict_targeted_verification_budget_proposal,
)
from .targeted_fix_verification_evidence_integrity import (
    TARGETED_FIX_VERIFICATION_EVIDENCE_INTEGRITY_VERSION,
    strict_evaluate_targeted_fix_verification,
)

TARGETED_FIX_VERIFICATION_SERVICE_ADAPTER_VERSION = (
    "targeted_fix_verification_service_adapter_v1_pure_plan_budget_evidence"
)
TARGETED_FIX_VERIFICATION_PREPARED_VERSION = (
    "targeted_fix_verification_prepared_v1_exact_plan_budget_snapshot"
)

_EXECUTION_CONTRACT = {
    "performs_io": False,
    "calls_private_worker": False,
    "mutates_authority": False,
    "mutates_persistence": False,
    "mutates_historical_repairs": False,
    "requires_existing_shared_scheduler": True,
    "requires_protected_fetch_path": True,
    "requires_complete_rule_evaluation_receipt": True,
}


def _exact_nonempty_string(value: Any) -> str:
    return value if isinstance(value, str) and value and value == value.strip() else ""


def _prepared_fingerprint_material(prepared: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": prepared.get("version"),
        "service_adapter_version": prepared.get("service_adapter_version"),
        "state": prepared.get("state"),
        "plan": prepared.get("plan"),
        "budget": prepared.get("budget"),
        "scheduler_snapshot_fingerprint": prepared.get("scheduler_snapshot_fingerprint"),
        "execution_contract": prepared.get("execution_contract"),
    }


def _prepared_failure(
    *,
    plan: dict[str, Any] | None,
    reason: str,
    budget: dict[str, Any] | None = None,
    scheduler_snapshot_fingerprint: str = "",
) -> dict[str, Any]:
    return {
        "version": TARGETED_FIX_VERIFICATION_PREPARED_VERSION,
        "service_adapter_version": TARGETED_FIX_VERIFICATION_SERVICE_ADAPTER_VERSION,
        "state": "could_not_verify",
        "reason": reason,
        "plan": plan if isinstance(plan, dict) else {},
        "budget": budget if isinstance(budget, dict) else {},
        "scheduler_snapshot_fingerprint": scheduler_snapshot_fingerprint,
        "execution_contract": dict(_EXECUTION_CONTRACT),
        "prepared_fingerprint": "",
    }


def prepare_targeted_fix_verification_service(
    sealed_repair: dict[str, Any],
    *,
    source_scan_id: str,
    source_scan_origin: str,
    scheduler_summary: dict[str, Any] | None,
    requested_urls: list[str] | None = None,
    max_urls: int = MAX_TARGETED_RECHECK_URLS,
) -> dict[str, Any]:
    """Build a pure preflight envelope around the already-green Lane-E core.

    This function performs no network I/O and does not authenticate or persist
    anything. The serialized integrator must supply one already-authority-verified
    sealed repair and one snapshot from the existing shared scheduler. A ready
    result is only a deterministic preflight receipt for that exact plan/budget
    snapshot; it is not an authority seal and it does not reserve request budget.
    """
    plan = build_targeted_recheck_plan(
        sealed_repair,
        source_scan_id=source_scan_id,
        source_scan_origin=source_scan_origin,
        requested_urls=requested_urls,
        max_urls=max_urls,
    )
    scheduler_snapshot_fingerprint = _fingerprint(scheduler_summary)
    if plan.get("version") != TARGETED_FIX_VERIFICATION_PLAN_VERSION or plan.get("state") != "ready":
        blockers = plan.get("blockers") if isinstance(plan.get("blockers"), list) else []
        reason = str(blockers[0]) if blockers else "verification_plan_not_ready"
        return _prepared_failure(
            plan=plan,
            reason=reason,
            scheduler_snapshot_fingerprint=scheduler_snapshot_fingerprint,
        )

    budget = strict_targeted_verification_budget_proposal(
        plan,
        sealed_repair,
        scheduler_summary,
    )
    if budget.get("state") != "fits":
        return _prepared_failure(
            plan=plan,
            reason=str(budget.get("reason") or "targeted_verification_budget_could_not_verify"),
            budget=budget,
            scheduler_snapshot_fingerprint=scheduler_snapshot_fingerprint,
        )
    if not scheduler_snapshot_fingerprint:
        return _prepared_failure(
            plan=plan,
            reason="shared_scheduler_snapshot_transport_not_serializable",
            budget=budget,
        )

    prepared = {
        "version": TARGETED_FIX_VERIFICATION_PREPARED_VERSION,
        "service_adapter_version": TARGETED_FIX_VERIFICATION_SERVICE_ADAPTER_VERSION,
        "state": "ready",
        "reason": "exact_plan_and_shared_budget_snapshot_ready",
        "plan": plan,
        "budget": budget,
        "scheduler_snapshot_fingerprint": scheduler_snapshot_fingerprint,
        "execution_contract": dict(_EXECUTION_CONTRACT),
    }
    prepared["prepared_fingerprint"] = _fingerprint(_prepared_fingerprint_material(prepared))
    if not prepared["prepared_fingerprint"]:
        return _prepared_failure(
            plan=plan,
            reason="prepared_verification_transport_not_serializable",
            budget=budget,
            scheduler_snapshot_fingerprint=scheduler_snapshot_fingerprint,
        )
    return prepared


def _service_could_not_verify(
    prepared: Any,
    reason: str,
    **extra: Any,
) -> dict[str, Any]:
    plan = prepared.get("plan") if isinstance(prepared, dict) else {}
    result = _could_not_verify(plan, reason, **extra)
    return {
        **result,
        "service_adapter_version": TARGETED_FIX_VERIFICATION_SERVICE_ADAPTER_VERSION,
        "prepared_fingerprint": (
            prepared.get("prepared_fingerprint", "") if isinstance(prepared, dict) else ""
        ),
        "side_effects_performed": False,
    }


def evaluate_prepared_targeted_fix_verification_service(
    prepared: dict[str, Any],
    sealed_repair: dict[str, Any],
    *,
    scheduler_summary: dict[str, Any] | None,
    current_scan_origin: str,
    current_contract: dict[str, Any] | None,
    recheck_outcomes: list[dict[str, Any]],
    current_fixes: list[dict[str, Any]],
    rule_evaluation_receipt: dict[str, Any] | None,
) -> dict[str, Any]:
    """Validate a prepared envelope again, then delegate repair truth unchanged.

    The adapter never fetches URLs, reserves budget, calls a worker, writes repair
    state, or mutates historical evidence. Budget and scheduler identity are
    rechecked against the same supplied scheduler snapshot before deterministic
    evidence can reach the strict Lane-E evaluator.
    """
    if not isinstance(prepared, dict):
        return _service_could_not_verify(prepared, "prepared_verification_invalid")
    if (
        prepared.get("version") != TARGETED_FIX_VERIFICATION_PREPARED_VERSION
        or prepared.get("service_adapter_version") != TARGETED_FIX_VERIFICATION_SERVICE_ADAPTER_VERSION
        or prepared.get("state") != "ready"
    ):
        return _service_could_not_verify(prepared, "prepared_verification_not_ready")

    prepared_fingerprint = _exact_nonempty_string(prepared.get("prepared_fingerprint"))
    if not prepared_fingerprint:
        return _service_could_not_verify(prepared, "prepared_verification_fingerprint_missing")
    if prepared_fingerprint != _fingerprint(_prepared_fingerprint_material(prepared)):
        return _service_could_not_verify(prepared, "prepared_verification_fingerprint_mismatch")

    if prepared.get("execution_contract") != _EXECUTION_CONTRACT:
        return _service_could_not_verify(prepared, "prepared_execution_contract_mismatch")

    plan = prepared.get("plan")
    if not isinstance(plan, dict):
        return _service_could_not_verify(prepared, "prepared_verification_plan_missing")

    scheduler_snapshot_fingerprint = _fingerprint(scheduler_summary)
    if (
        not scheduler_snapshot_fingerprint
        or scheduler_snapshot_fingerprint != prepared.get("scheduler_snapshot_fingerprint")
    ):
        return _service_could_not_verify(prepared, "shared_scheduler_snapshot_fingerprint_mismatch")

    budget = strict_targeted_verification_budget_proposal(
        plan,
        sealed_repair,
        scheduler_summary,
    )
    if budget.get("state") != "fits":
        return _service_could_not_verify(
            prepared,
            str(budget.get("reason") or "targeted_verification_budget_could_not_verify"),
            budget_integrity_version=TARGETED_FIX_VERIFICATION_BUDGET_INTEGRITY_VERSION,
        )
    if budget != prepared.get("budget"):
        return _service_could_not_verify(prepared, "prepared_budget_snapshot_mismatch")

    result = strict_evaluate_targeted_fix_verification(
        plan,
        sealed_repair,
        current_scan_origin=current_scan_origin,
        current_contract=current_contract,
        recheck_outcomes=recheck_outcomes,
        current_fixes=current_fixes,
        rule_evaluation_receipt=rule_evaluation_receipt,
    )
    return {
        **result,
        "service_adapter_version": TARGETED_FIX_VERIFICATION_SERVICE_ADAPTER_VERSION,
        "prepared_fingerprint": prepared_fingerprint,
        "budget_integrity_version": TARGETED_FIX_VERIFICATION_BUDGET_INTEGRITY_VERSION,
        "evidence_integrity_version": TARGETED_FIX_VERIFICATION_EVIDENCE_INTEGRITY_VERSION,
        "side_effects_performed": False,
    }
