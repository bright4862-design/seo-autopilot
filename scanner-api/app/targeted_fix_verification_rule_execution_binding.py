from __future__ import annotations

import hashlib
import json
from typing import Any

from .targeted_fix_verification import _matching_current_fix_keys, _origin_root
from .targeted_fix_verification_rule_receipt_binding import (
    TARGETED_FIX_VERIFICATION_RULE_RECEIPT_BINDING_VERSION,
    build_execution_bound_rule_evaluation_receipt,
    evaluate_rule_receipt_bound_targeted_fix_verification_service,
)
from .targeted_fix_verification_service_adapter import _service_could_not_verify

TARGETED_FIX_VERIFICATION_RULE_EXECUTION_RESULT_VERSION = (
    "targeted_fix_verification_rule_execution_result_v1_exact_page_evidence"
)
TARGETED_FIX_VERIFICATION_RULE_EXECUTION_BINDING_VERSION = (
    "targeted_fix_verification_rule_execution_binding_v1_exact_execution_population"
)
ORIGINATING_RULE_PRODUCER_CONTRACT = "originating_deterministic_rule"

_RULE_EXECUTION_RESULT_FIELDS = frozenset(
    {
        "version",
        "state",
        "producer_contract",
        "model_calls_performed",
        "plan_fingerprint",
        "repair_fingerprint",
        "rule_definition_version",
        "comparison_profile_version",
        "evidence_url_identity_version",
        "evidence_key",
        "scheduler_evidence_ref",
        "page_evidence_fingerprint",
        "finding_state",
    }
)
_FINDING_STATES = frozenset({"finding_present", "finding_absent"})


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


def rule_execution_page_evidence_fingerprint(page: Any) -> str:
    """Fingerprint the exact page object consumed by the deterministic rule."""
    if not isinstance(page, dict):
        return ""
    return _fingerprint(page)


def _result_failure(reason: str) -> dict[str, Any]:
    return {
        "version": TARGETED_FIX_VERIFICATION_RULE_EXECUTION_RESULT_VERSION,
        "state": "could_not_verify",
        "reason": reason,
        "producer_contract": ORIGINATING_RULE_PRODUCER_CONTRACT,
        "model_calls_performed": False,
    }


def build_originating_rule_execution_result(
    plan: dict[str, Any],
    recheck_outcome: dict[str, Any],
    *,
    finding_state: str,
) -> dict[str, Any]:
    """Serialize one deterministic rule execution over one exact observed page.

    This helper is not execution authority by itself. The serialized integrator must
    call it only from the trusted originating deterministic-rule producer after that
    rule has actually evaluated the exact page object carried by ``recheck_outcome``.
    """
    if not isinstance(plan, dict) or plan.get("state") != "ready":
        return _result_failure("verification_plan_not_ready")
    if not isinstance(recheck_outcome, dict):
        return _result_failure("recheck_outcome_invalid")
    if recheck_outcome.get("plan_fingerprint") != plan.get("plan_fingerprint"):
        return _result_failure("recheck_outcome_plan_mismatch")
    evidence_key = _exact_nonempty_string(recheck_outcome.get("evidence_key"))
    if not evidence_key:
        return _result_failure("recheck_outcome_evidence_key_invalid")
    if recheck_outcome.get("state") != "observed":
        return _result_failure("rule_execution_requires_observed_evidence")
    scheduler_ref = _exact_nonempty_string(recheck_outcome.get("scheduler_evidence_ref"))
    if not scheduler_ref:
        return _result_failure("rule_execution_scheduler_evidence_ref_missing")
    page_fingerprint = rule_execution_page_evidence_fingerprint(recheck_outcome.get("page"))
    if not page_fingerprint:
        return _result_failure("rule_execution_page_evidence_not_serializable")
    exact_finding_state = _exact_nonempty_string(finding_state)
    if exact_finding_state not in _FINDING_STATES:
        return _result_failure("rule_execution_finding_state_invalid")

    required_plan_values = {
        "plan_fingerprint": _exact_nonempty_string(plan.get("plan_fingerprint")),
        "repair_fingerprint": _exact_nonempty_string(plan.get("repair_fingerprint")),
        "rule_definition_version": _exact_nonempty_string(plan.get("rule_definition_version")),
        "comparison_profile_version": _exact_nonempty_string(plan.get("comparison_profile_version")),
        "evidence_url_identity_version": _exact_nonempty_string(
            plan.get("evidence_url_identity_version")
        ),
    }
    if any(not value for value in required_plan_values.values()):
        return _result_failure("rule_execution_plan_identity_invalid")

    return {
        "version": TARGETED_FIX_VERIFICATION_RULE_EXECUTION_RESULT_VERSION,
        "state": "evaluated",
        "producer_contract": ORIGINATING_RULE_PRODUCER_CONTRACT,
        "model_calls_performed": False,
        **required_plan_values,
        "evidence_key": evidence_key,
        "scheduler_evidence_ref": scheduler_ref,
        "page_evidence_fingerprint": page_fingerprint,
        "finding_state": exact_finding_state,
    }


def _failure(reason: str, **extra: Any) -> dict[str, Any]:
    return {
        "version": TARGETED_FIX_VERIFICATION_RULE_EXECUTION_BINDING_VERSION,
        "state": "could_not_verify",
        "reason": reason,
        "rule_execution_result_version": TARGETED_FIX_VERIFICATION_RULE_EXECUTION_RESULT_VERSION,
        "rule_receipt_binding_version": TARGETED_FIX_VERIFICATION_RULE_RECEIPT_BINDING_VERSION,
        "receipt_fingerprint": "",
        "model_calls_performed": False,
        **extra,
    }


def _planned_keys(plan: Any) -> tuple[list[str], str]:
    requests = plan.get("requests") if isinstance(plan, dict) else None
    if not isinstance(requests, list) or not requests:
        return [], "verification_plan_requests_invalid"
    keys: list[str] = []
    for request in requests:
        if not isinstance(request, dict):
            return [], "verification_plan_request_transport_invalid"
        key = _exact_nonempty_string(request.get("evidence_key"))
        if not key:
            return [], "verification_plan_request_identity_invalid"
        if key in keys:
            return [], "verification_plan_request_identity_invalid"
        keys.append(key)
    return keys, ""


def _outcomes_by_key(
    recheck_outcomes: Any,
    planned_keys: list[str],
) -> tuple[dict[str, dict[str, Any]], str]:
    if not isinstance(recheck_outcomes, list):
        return {}, "recheck_outcomes_invalid"
    if len(recheck_outcomes) != len(planned_keys):
        return {}, "recheck_outcome_population_mismatch"
    output: dict[str, dict[str, Any]] = {}
    for outcome in recheck_outcomes:
        if not isinstance(outcome, dict):
            return {}, "recheck_outcome_transport_invalid"
        key = _exact_nonempty_string(outcome.get("evidence_key"))
        if key not in planned_keys:
            return {}, "recheck_outcome_outside_planned_scope"
        if key in output:
            return {}, "duplicate_recheck_outcome"
        output[key] = outcome
    if set(output) != set(planned_keys):
        return {}, "recheck_outcome_population_mismatch"
    return output, ""


def build_rule_execution_bound_rule_evaluation_receipt(
    prepared: dict[str, Any],
    sealed_repair: dict[str, Any],
    *,
    preflight_scheduler_summary: dict[str, Any] | None,
    postflight_scheduler_summary: dict[str, Any] | None,
    current_scan_origin: str,
    current_contract: dict[str, Any] | None,
    recheck_outcomes: list[dict[str, Any]],
    current_fixes: list[dict[str, Any]],
    rule_execution_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Bind explicit originating-rule executions to the exact protected execution.

    Repair truth is still decided only downstream by the canonical comparison path.
    This contract merely proves that every planned observed page has one exact,
    deterministic, no-model rule-execution result tied to the same page evidence.
    """
    plan = prepared.get("plan") if isinstance(prepared, dict) else {}
    if not isinstance(plan, dict):
        return _failure("verification_plan_missing")

    underlying = build_execution_bound_rule_evaluation_receipt(
        prepared,
        sealed_repair,
        preflight_scheduler_summary=preflight_scheduler_summary,
        postflight_scheduler_summary=postflight_scheduler_summary,
        current_scan_origin=current_scan_origin,
        current_contract=current_contract,
        recheck_outcomes=recheck_outcomes,
        current_fixes=current_fixes,
    )
    if underlying.get("state") != "ready":
        return _failure(
            str(underlying.get("reason") or "execution_bound_rule_receipt_could_not_verify"),
            underlying_rule_receipt=underlying,
        )

    planned_keys, error = _planned_keys(plan)
    if error:
        return _failure(error)
    outcomes, error = _outcomes_by_key(recheck_outcomes, planned_keys)
    if error:
        return _failure(error)
    for key in planned_keys:
        outcome = outcomes[key]
        if outcome.get("state") != "observed":
            return _failure(
                "rule_execution_requires_observed_evidence",
                blocked_evidence_key=key,
                blocked_reason=_exact_nonempty_string(outcome.get("reason"))
                or "recheck_not_verified",
            )

    current_origin = _origin_root(current_scan_origin)
    if not current_origin or current_origin != plan.get("source_scan_origin"):
        return _failure("current_scan_origin_mismatch")
    if not isinstance(current_fixes, list):
        return _failure("current_fix_population_invalid")

    matching_by_key, fix_error = _matching_current_fix_keys(
        str(plan.get("repair_fingerprint") or ""),
        current_fixes,
        current_origin=current_origin,
    )
    if fix_error:
        return _failure(fix_error)
    if set(matching_by_key) - set(planned_keys):
        return _failure("matching_current_fix_expands_sealed_repair_scope")

    if not isinstance(rule_execution_results, list):
        return _failure("rule_execution_results_invalid")
    if len(rule_execution_results) != len(planned_keys):
        return _failure("rule_execution_result_population_mismatch")

    result_by_key: dict[str, dict[str, Any]] = {}
    for result in rule_execution_results:
        if not isinstance(result, dict):
            return _failure("rule_execution_result_transport_invalid")
        if result.get("version") != TARGETED_FIX_VERIFICATION_RULE_EXECUTION_RESULT_VERSION:
            return _failure("rule_execution_result_version_mismatch")
        if result.get("state") != "evaluated":
            return _failure("rule_execution_result_not_evaluated")
        if set(result) != _RULE_EXECUTION_RESULT_FIELDS:
            return _failure("rule_execution_result_fields_invalid")
        if result.get("producer_contract") != ORIGINATING_RULE_PRODUCER_CONTRACT:
            return _failure("rule_execution_producer_contract_mismatch")
        if result.get("model_calls_performed") is not False:
            return _failure("rule_execution_model_calls_not_allowed")

        key = _exact_nonempty_string(result.get("evidence_key"))
        if key not in planned_keys:
            return _failure("rule_execution_result_outside_planned_scope")
        if key in result_by_key:
            return _failure("duplicate_rule_execution_result", blocked_evidence_key=key)

        expected_identity = {
            "plan_fingerprint": plan.get("plan_fingerprint"),
            "repair_fingerprint": plan.get("repair_fingerprint"),
            "rule_definition_version": plan.get("rule_definition_version"),
            "comparison_profile_version": plan.get("comparison_profile_version"),
            "evidence_url_identity_version": plan.get("evidence_url_identity_version"),
        }
        for field, expected in expected_identity.items():
            if result.get(field) != expected:
                return _failure(
                    f"rule_execution_result_{field}_mismatch",
                    blocked_evidence_key=key,
                )

        outcome = outcomes[key]
        if outcome.get("state") != "observed":
            return _failure(
                "rule_execution_requires_observed_evidence",
                blocked_evidence_key=key,
            )
        scheduler_ref = _exact_nonempty_string(outcome.get("scheduler_evidence_ref"))
        if not scheduler_ref or result.get("scheduler_evidence_ref") != scheduler_ref:
            return _failure(
                "rule_execution_scheduler_evidence_ref_mismatch",
                blocked_evidence_key=key,
            )
        page_fingerprint = rule_execution_page_evidence_fingerprint(outcome.get("page"))
        if not page_fingerprint:
            return _failure(
                "rule_execution_page_evidence_not_serializable",
                blocked_evidence_key=key,
            )
        if result.get("page_evidence_fingerprint") != page_fingerprint:
            return _failure(
                "rule_execution_page_evidence_fingerprint_mismatch",
                blocked_evidence_key=key,
            )

        finding_state = result.get("finding_state")
        if finding_state not in _FINDING_STATES:
            return _failure(
                "rule_execution_finding_state_invalid",
                blocked_evidence_key=key,
            )
        expected_finding_state = (
            "finding_present" if key in matching_by_key else "finding_absent"
        )
        if finding_state != expected_finding_state:
            return _failure(
                "rule_execution_fix_population_mismatch",
                blocked_evidence_key=key,
                expected_finding_state=expected_finding_state,
            )
        result_by_key[key] = result

    if set(result_by_key) != set(planned_keys):
        return _failure("rule_execution_result_population_mismatch")

    ordered_results = [result_by_key[key] for key in planned_keys]
    results_fingerprint = _fingerprint(ordered_results)
    if not results_fingerprint:
        return _failure("rule_execution_results_not_serializable")

    material = {
        "version": TARGETED_FIX_VERIFICATION_RULE_EXECUTION_BINDING_VERSION,
        "rule_execution_result_version": TARGETED_FIX_VERIFICATION_RULE_EXECUTION_RESULT_VERSION,
        "rule_receipt_binding_version": TARGETED_FIX_VERIFICATION_RULE_RECEIPT_BINDING_VERSION,
        "underlying_rule_receipt_fingerprint": underlying.get("receipt_fingerprint"),
        "plan_fingerprint": plan.get("plan_fingerprint"),
        "repair_fingerprint": plan.get("repair_fingerprint"),
        "rule_definition_version": plan.get("rule_definition_version"),
        "comparison_profile_version": plan.get("comparison_profile_version"),
        "evidence_url_identity_version": plan.get("evidence_url_identity_version"),
        "current_fixes_fingerprint": underlying.get("current_fixes_fingerprint"),
        "executed_evidence_keys": planned_keys,
        "executed_population_count": len(planned_keys),
        "population_complete": True,
        "rule_execution_results_fingerprint": results_fingerprint,
        "model_calls_performed": False,
    }
    if any(
        not isinstance(material[field], str) or not material[field]
        for field in (
            "underlying_rule_receipt_fingerprint",
            "plan_fingerprint",
            "repair_fingerprint",
            "rule_definition_version",
            "comparison_profile_version",
            "evidence_url_identity_version",
            "current_fixes_fingerprint",
            "rule_execution_results_fingerprint",
        )
    ):
        return _failure("rule_execution_binding_material_invalid")

    receipt_fingerprint = _fingerprint(material)
    if not receipt_fingerprint:
        return _failure("rule_execution_binding_not_serializable")
    return {
        **material,
        "state": "ready",
        "reason": "exact_originating_rule_execution_bound_to_targeted_population",
        "receipt_fingerprint": receipt_fingerprint,
    }


def evaluate_rule_execution_bound_targeted_fix_verification_service(
    prepared: dict[str, Any],
    sealed_repair: dict[str, Any],
    *,
    preflight_scheduler_summary: dict[str, Any] | None,
    postflight_scheduler_summary: dict[str, Any] | None,
    current_scan_origin: str,
    current_contract: dict[str, Any] | None,
    recheck_outcomes: list[dict[str, Any]],
    current_fixes: list[dict[str, Any]],
    rule_execution_results: list[dict[str, Any]],
    rule_execution_bound_receipt: dict[str, Any] | None,
) -> dict[str, Any]:
    """Require exact deterministic-rule execution binding, then delegate truth."""
    expected = build_rule_execution_bound_rule_evaluation_receipt(
        prepared,
        sealed_repair,
        preflight_scheduler_summary=preflight_scheduler_summary,
        postflight_scheduler_summary=postflight_scheduler_summary,
        current_scan_origin=current_scan_origin,
        current_contract=current_contract,
        recheck_outcomes=recheck_outcomes,
        current_fixes=current_fixes,
        rule_execution_results=rule_execution_results,
    )
    if expected.get("state") != "ready":
        return _service_could_not_verify(
            prepared,
            str(expected.get("reason") or "rule_execution_binding_could_not_verify"),
            rule_execution_binding_version=TARGETED_FIX_VERIFICATION_RULE_EXECUTION_BINDING_VERSION,
            rule_execution_binding=expected,
            model_calls_performed=False,
        )
    if (
        not isinstance(rule_execution_bound_receipt, dict)
        or rule_execution_bound_receipt.get("version")
        != TARGETED_FIX_VERIFICATION_RULE_EXECUTION_BINDING_VERSION
        or rule_execution_bound_receipt.get("state") != "ready"
    ):
        return _service_could_not_verify(
            prepared,
            "rule_execution_bound_receipt_missing_or_invalid",
            rule_execution_binding_version=TARGETED_FIX_VERIFICATION_RULE_EXECUTION_BINDING_VERSION,
            model_calls_performed=False,
        )
    if rule_execution_bound_receipt != expected:
        return _service_could_not_verify(
            prepared,
            "rule_execution_bound_receipt_mismatch",
            rule_execution_binding_version=TARGETED_FIX_VERIFICATION_RULE_EXECUTION_BINDING_VERSION,
            expected_receipt_fingerprint=expected.get("receipt_fingerprint", ""),
            model_calls_performed=False,
        )

    underlying = build_execution_bound_rule_evaluation_receipt(
        prepared,
        sealed_repair,
        preflight_scheduler_summary=preflight_scheduler_summary,
        postflight_scheduler_summary=postflight_scheduler_summary,
        current_scan_origin=current_scan_origin,
        current_contract=current_contract,
        recheck_outcomes=recheck_outcomes,
        current_fixes=current_fixes,
    )
    if underlying.get("state") != "ready":
        return _service_could_not_verify(
            prepared,
            "execution_bound_rule_receipt_not_ready",
            rule_execution_binding_version=TARGETED_FIX_VERIFICATION_RULE_EXECUTION_BINDING_VERSION,
            model_calls_performed=False,
        )

    result = evaluate_rule_receipt_bound_targeted_fix_verification_service(
        prepared,
        sealed_repair,
        preflight_scheduler_summary=preflight_scheduler_summary,
        postflight_scheduler_summary=postflight_scheduler_summary,
        current_scan_origin=current_scan_origin,
        current_contract=current_contract,
        recheck_outcomes=recheck_outcomes,
        current_fixes=current_fixes,
        execution_bound_rule_receipt=underlying,
    )
    return {
        **result,
        "rule_execution_binding_version": TARGETED_FIX_VERIFICATION_RULE_EXECUTION_BINDING_VERSION,
        "rule_execution_binding": {
            "version": TARGETED_FIX_VERIFICATION_RULE_EXECUTION_BINDING_VERSION,
            "state": "valid",
            "reason": "exact_originating_rule_execution_bound_to_targeted_population",
            "receipt_fingerprint": expected["receipt_fingerprint"],
            "executed_population_count": expected["executed_population_count"],
        },
        "model_calls_performed": False,
        "side_effects_performed": False,
    }
