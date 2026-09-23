from __future__ import annotations

import hashlib
import json
from typing import Any

from .targeted_fix_verification import build_rule_evaluation_receipt
from .targeted_fix_verification_execution_evidence import (
    TARGETED_FIX_VERIFICATION_EXECUTION_EVIDENCE_VERSION,
    evaluate_execution_bound_targeted_fix_verification_service,
    validate_targeted_verification_execution_evidence_binding,
)
from .targeted_fix_verification_service_adapter import _service_could_not_verify

TARGETED_FIX_VERIFICATION_RULE_RECEIPT_BINDING_VERSION = (
    "targeted_fix_verification_rule_receipt_binding_v1_exact_execution_bound_population"
)


def _fingerprint(value: Any) -> str:
    try:
        payload = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError):
        return ""
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _exact_nonempty_string(value: Any) -> str:
    return value if isinstance(value, str) and value and value == value.strip() else ""


def _failure(reason: str, **extra: Any) -> dict[str, Any]:
    return {
        "version": TARGETED_FIX_VERIFICATION_RULE_RECEIPT_BINDING_VERSION,
        "state": "could_not_verify",
        "reason": reason,
        "execution_evidence_version": TARGETED_FIX_VERIFICATION_EXECUTION_EVIDENCE_VERSION,
        "receipt_fingerprint": "",
        **extra,
    }


def build_execution_bound_rule_evaluation_receipt(
    prepared: dict[str, Any],
    sealed_repair: dict[str, Any],
    *,
    preflight_scheduler_summary: dict[str, Any] | None,
    postflight_scheduler_summary: dict[str, Any] | None,
    current_scan_origin: str,
    current_contract: dict[str, Any] | None,
    recheck_outcomes: list[dict[str, Any]],
    current_fixes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Fingerprint one deterministic rule result against its exact verification execution.

    This is an integrity/provenance contract only. It does not establish caller trust,
    run a rule, spend scheduler budget, or decide repair truth. The serialized
    integrator must construct it inside the originating deterministic-rule producer
    after protected execution has completed.
    """
    plan = prepared.get("plan") if isinstance(prepared, dict) else {}
    if not isinstance(plan, dict):
        return _failure("verification_plan_missing")

    execution_binding = validate_targeted_verification_execution_evidence_binding(
        plan,
        sealed_repair,
        preflight_scheduler_summary=preflight_scheduler_summary,
        postflight_scheduler_summary=postflight_scheduler_summary,
        recheck_outcomes=recheck_outcomes,
    )
    if execution_binding.get("state") != "valid":
        return _failure(
            str(execution_binding.get("reason") or "targeted_execution_evidence_could_not_verify"),
            execution_evidence=execution_binding,
        )

    if not isinstance(current_fixes, list):
        return _failure("current_fix_population_invalid")
    core_receipt = build_rule_evaluation_receipt(plan, current_fixes)
    if core_receipt.get("state") != "ready":
        return _failure("rule_evaluation_receipt_not_ready")
    if not _exact_nonempty_string(current_scan_origin):
        return _failure("current_scan_origin_invalid")
    if not isinstance(current_contract, dict):
        return _failure("current_comparison_contract_missing")

    material = {
        "version": TARGETED_FIX_VERIFICATION_RULE_RECEIPT_BINDING_VERSION,
        "plan_fingerprint": plan.get("plan_fingerprint"),
        "repair_fingerprint": plan.get("repair_fingerprint"),
        "rule_definition_version": plan.get("rule_definition_version"),
        "comparison_profile_version": plan.get("comparison_profile_version"),
        "evidence_url_identity_version": plan.get("evidence_url_identity_version"),
        "execution_evidence_version": TARGETED_FIX_VERIFICATION_EXECUTION_EVIDENCE_VERSION,
        "execution_binding_fingerprint": _fingerprint(execution_binding),
        "preflight_scheduler_fingerprint": _fingerprint(preflight_scheduler_summary),
        "postflight_scheduler_fingerprint": _fingerprint(postflight_scheduler_summary),
        "recheck_outcomes_fingerprint": _fingerprint(recheck_outcomes),
        "current_scan_origin_fingerprint": _fingerprint(current_scan_origin),
        "current_contract_fingerprint": _fingerprint(current_contract),
        "core_rule_evaluation_receipt_fingerprint": _fingerprint(core_receipt),
        "current_fixes_fingerprint": core_receipt.get("current_fixes_fingerprint"),
        "evaluated_population_count": len(core_receipt.get("evaluated_evidence_keys") or []),
    }
    if any(
        not isinstance(material[field], str) or not material[field]
        for field in (
            "plan_fingerprint",
            "repair_fingerprint",
            "rule_definition_version",
            "comparison_profile_version",
            "evidence_url_identity_version",
            "execution_binding_fingerprint",
            "preflight_scheduler_fingerprint",
            "postflight_scheduler_fingerprint",
            "recheck_outcomes_fingerprint",
            "current_scan_origin_fingerprint",
            "current_contract_fingerprint",
            "core_rule_evaluation_receipt_fingerprint",
            "current_fixes_fingerprint",
        )
    ):
        return _failure("execution_bound_rule_receipt_material_invalid")

    receipt_fingerprint = _fingerprint(material)
    if not receipt_fingerprint:
        return _failure("execution_bound_rule_receipt_not_serializable")
    return {
        **material,
        "state": "ready",
        "reason": "exact_rule_result_bound_to_targeted_execution",
        "receipt_fingerprint": receipt_fingerprint,
    }


def evaluate_rule_receipt_bound_targeted_fix_verification_service(
    prepared: dict[str, Any],
    sealed_repair: dict[str, Any],
    *,
    preflight_scheduler_summary: dict[str, Any] | None,
    postflight_scheduler_summary: dict[str, Any] | None,
    current_scan_origin: str,
    current_contract: dict[str, Any] | None,
    recheck_outcomes: list[dict[str, Any]],
    current_fixes: list[dict[str, Any]],
    execution_bound_rule_receipt: dict[str, Any] | None,
) -> dict[str, Any]:
    """Fail closed unless the rule receipt exactly matches this execution population."""
    expected = build_execution_bound_rule_evaluation_receipt(
        prepared,
        sealed_repair,
        preflight_scheduler_summary=preflight_scheduler_summary,
        postflight_scheduler_summary=postflight_scheduler_summary,
        current_scan_origin=current_scan_origin,
        current_contract=current_contract,
        recheck_outcomes=recheck_outcomes,
        current_fixes=current_fixes,
    )
    if expected.get("state") != "ready":
        return _service_could_not_verify(
            prepared,
            str(expected.get("reason") or "execution_bound_rule_receipt_could_not_verify"),
            rule_receipt_binding_version=TARGETED_FIX_VERIFICATION_RULE_RECEIPT_BINDING_VERSION,
            rule_receipt_binding=expected,
        )
    if (
        not isinstance(execution_bound_rule_receipt, dict)
        or execution_bound_rule_receipt.get("version")
        != TARGETED_FIX_VERIFICATION_RULE_RECEIPT_BINDING_VERSION
        or execution_bound_rule_receipt.get("state") != "ready"
    ):
        return _service_could_not_verify(
            prepared,
            "execution_bound_rule_receipt_missing_or_invalid",
            rule_receipt_binding_version=TARGETED_FIX_VERIFICATION_RULE_RECEIPT_BINDING_VERSION,
        )
    if execution_bound_rule_receipt != expected:
        return _service_could_not_verify(
            prepared,
            "execution_bound_rule_receipt_mismatch",
            rule_receipt_binding_version=TARGETED_FIX_VERIFICATION_RULE_RECEIPT_BINDING_VERSION,
            expected_receipt_fingerprint=expected.get("receipt_fingerprint", ""),
        )

    plan = prepared.get("plan") if isinstance(prepared, dict) else {}
    core_receipt = build_rule_evaluation_receipt(
        plan if isinstance(plan, dict) else {},
        current_fixes,
    )
    result = evaluate_execution_bound_targeted_fix_verification_service(
        prepared,
        sealed_repair,
        preflight_scheduler_summary=preflight_scheduler_summary,
        postflight_scheduler_summary=postflight_scheduler_summary,
        current_scan_origin=current_scan_origin,
        current_contract=current_contract,
        recheck_outcomes=recheck_outcomes,
        current_fixes=current_fixes,
        rule_evaluation_receipt=core_receipt,
    )
    return {
        **result,
        "rule_receipt_binding_version": TARGETED_FIX_VERIFICATION_RULE_RECEIPT_BINDING_VERSION,
        "rule_receipt_binding": {
            "version": TARGETED_FIX_VERIFICATION_RULE_RECEIPT_BINDING_VERSION,
            "state": "valid",
            "reason": "exact_rule_result_bound_to_targeted_execution",
            "receipt_fingerprint": expected["receipt_fingerprint"],
        },
        "side_effects_performed": False,
    }
