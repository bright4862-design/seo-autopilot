from __future__ import annotations

from typing import Any

from .nextgen_fix_verification import COULD_NOT_VERIFY
from .nextgen_fix_verification_execution_binding import (
    strict_regression_reopen_from_execution_bound_observations,
    strict_verified_fixed_transition_from_execution_bound_observations,
    verification_plan_execution_binding_integrity,
)
from .nextgen_fix_verification_plan_identity import PLAN_IDENTITY_BINDING_VERSION

OBSERVATION_EXECUTION_BINDING_VERSION = (
    "fix_verification_observation_execution_binding_v1_exact_page_plan_identity"
)
STRICT_VERIFIED_FIXED_OBSERVATION_EXECUTION_BOUND_VERSION = (
    "fix_verified_fixed_observation_execution_bound_replay_v1_exact_page_plan_identity"
)
STRICT_REGRESSION_REOPEN_OBSERVATION_EXECUTION_BOUND_VERSION = (
    "fix_regression_reopen_observation_execution_bound_replay_v1_exact_page_plan_identity"
)

_EXECUTION_FINGERPRINT_FIELD = "verification_plan_fingerprint"
_EXECUTION_IDENTITY_VERSION_FIELD = "verification_plan_identity_version"


def _exact_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _request_evidence_keys(plan: dict[str, Any]) -> tuple[list[str], str]:
    requests = plan.get("requests") if isinstance(plan, dict) else None
    if not isinstance(requests, list):
        return [], "verification_plan_requests_not_a_list"
    if not requests:
        return [], "verification_plan_requests_empty"

    keys: list[str] = []
    seen: set[str] = set()
    for index, request in enumerate(requests):
        if not isinstance(request, dict):
            return [], f"verification_request_{index}_not_an_object"
        key = request.get("evidence_key")
        if not _exact_nonempty_string(key):
            return [], f"verification_request_{index}_evidence_key_must_be_exact_nonempty_string"
        if key in seen:
            return [], f"verification_request_{index}_duplicate_evidence_key"
        seen.add(key)
        keys.append(key)
    return keys, ""


def verification_observation_execution_binding_integrity(
    plan: dict[str, Any],
    current_pages: list[dict[str, Any]],
    rule_evaluations: list[dict[str, Any]],
    *,
    previous_scan_id: str,
) -> dict[str, Any]:
    """Bind observed page rows and rule evaluations to one exact targeted plan.

    The prior execution boundary proves that predicate evaluations belong to the
    exact identity-bound targeted plan. Page observations are also proof-bearing:
    without an execution claim, a page row from another recheck batch in the same
    scan could be paired with an otherwise valid evaluation receipt.

    Every present page must therefore carry the exact plan fingerprint,
    plan-identity version, and targeted evidence key. Missing required pages are
    intentionally left for the downstream evaluator, which must retain
    ``required_page_not_observed`` and ``COULD_NOT_VERIFY``. A disappeared URL is
    never proof of a fix.
    """
    base = {
        "version": OBSERVATION_EXECUTION_BINDING_VERSION,
        "valid": False,
        "reason": "observation_execution_binding_not_proven",
        "plan_fingerprint": "",
        "verification_plan_execution_binding": {},
    }

    if not isinstance(plan, dict):
        return {**base, "reason": "verification_plan_not_an_object"}
    if not isinstance(current_pages, list):
        return {**base, "reason": "current_pages_not_a_list"}
    if any(not isinstance(item, dict) for item in current_pages):
        return {**base, "reason": "current_pages_contains_non_object"}
    if not isinstance(rule_evaluations, list):
        return {**base, "reason": "rule_evaluations_not_a_list"}

    execution = verification_plan_execution_binding_integrity(
        plan,
        rule_evaluations,
        previous_scan_id=previous_scan_id,
    )
    with_execution = {
        **base,
        "verification_plan_execution_binding": execution if isinstance(execution, dict) else {},
    }
    if not isinstance(execution, dict) or execution.get("valid") is not True:
        reason = execution.get("reason") if isinstance(execution, dict) else "not_an_object"
        return {
            **with_execution,
            "reason": f"verification_plan_execution_binding_failed:{reason or 'not_proven'}",
        }

    fingerprint = plan.get("plan_fingerprint")
    if not _exact_nonempty_string(fingerprint):
        return {**with_execution, "reason": "verification_plan_fingerprint_not_exact_nonempty_string"}
    if execution.get("plan_fingerprint") != fingerprint:
        return {**with_execution, "reason": "verification_plan_execution_fingerprint_disagreement"}

    required_keys, request_reason = _request_evidence_keys(plan)
    if request_reason:
        return {**with_execution, "reason": request_reason, "plan_fingerprint": fingerprint}
    required_set = set(required_keys)

    observed_keys: list[str] = []
    seen: set[str] = set()
    for index, page in enumerate(current_pages):
        key = page.get("evidence_key")
        if not _exact_nonempty_string(key):
            return {
                **with_execution,
                "reason": f"current_page_{index}_evidence_key_must_be_exact_nonempty_string",
                "current_page_index": index,
                "plan_fingerprint": fingerprint,
            }
        if key in seen:
            return {
                **with_execution,
                "reason": f"current_page_{index}_duplicate_evidence_key",
                "current_page_index": index,
                "plan_fingerprint": fingerprint,
            }
        if key not in required_set:
            return {
                **with_execution,
                "reason": f"current_page_{index}_evidence_key_not_targeted_by_plan",
                "current_page_index": index,
                "plan_fingerprint": fingerprint,
                "unexpected_evidence_key": key,
            }

        claimed_fingerprint = page.get(_EXECUTION_FINGERPRINT_FIELD)
        if not _exact_nonempty_string(claimed_fingerprint):
            return {
                **with_execution,
                "reason": (
                    f"current_page_{index}_{_EXECUTION_FINGERPRINT_FIELD}"
                    "_must_be_exact_nonempty_string"
                ),
                "current_page_index": index,
                "plan_fingerprint": fingerprint,
            }
        if claimed_fingerprint != fingerprint:
            return {
                **with_execution,
                "reason": f"current_page_{index}_{_EXECUTION_FINGERPRINT_FIELD}_mismatch",
                "current_page_index": index,
                "plan_fingerprint": fingerprint,
            }

        claimed_identity_version = page.get(_EXECUTION_IDENTITY_VERSION_FIELD)
        if not _exact_nonempty_string(claimed_identity_version):
            return {
                **with_execution,
                "reason": (
                    f"current_page_{index}_{_EXECUTION_IDENTITY_VERSION_FIELD}"
                    "_must_be_exact_nonempty_string"
                ),
                "current_page_index": index,
                "plan_fingerprint": fingerprint,
            }
        if claimed_identity_version != PLAN_IDENTITY_BINDING_VERSION:
            return {
                **with_execution,
                "reason": f"current_page_{index}_{_EXECUTION_IDENTITY_VERSION_FIELD}_mismatch",
                "current_page_index": index,
                "plan_fingerprint": fingerprint,
            }

        seen.add(key)
        observed_keys.append(key)

    missing_keys = [key for key in required_keys if key not in seen]
    return {
        **with_execution,
        "valid": True,
        "reason": "all_present_page_observations_and_rule_evaluations_bound_to_exact_targeted_plan",
        "plan_fingerprint": fingerprint,
        "checked_current_pages": len(current_pages),
        "checked_rule_evaluations": len(rule_evaluations),
        "observed_evidence_keys": observed_keys,
        "missing_required_evidence_keys": missing_keys,
    }


def _verified_fixed_denied(reason: str, binding: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": STRICT_VERIFIED_FIXED_OBSERVATION_EXECUTION_BOUND_VERSION,
        "allowed": False,
        "reason": reason,
        "repair_fingerprint": "",
        "recomputed_verification_state": COULD_NOT_VERIFY,
        "recomputed_result": {},
        "replay": {},
        "observation_execution_binding": binding,
        "inner_plan_execution_bound_replay_version": "",
    }


def strict_verified_fixed_transition_from_observation_execution_bound_inputs(
    previous_record: dict[str, Any],
    plan: dict[str, Any],
    current_pages: list[dict[str, Any]],
    rule_evaluations: list[dict[str, Any]],
    current_fixes: list[dict[str, Any]],
    current_contract: dict[str, Any],
    *,
    previous_scan_id: str,
    scan_id: str,
    previous_scan_origin: str = "",
    scan_origin: str = "",
) -> dict[str, Any]:
    """Require exact page+evaluation plan execution provenance before PASS proof."""
    binding = verification_observation_execution_binding_integrity(
        plan,
        current_pages,
        rule_evaluations,
        previous_scan_id=previous_scan_id,
    )
    if binding.get("valid") is not True:
        return _verified_fixed_denied("observation_execution_binding_failed", binding)

    decision = strict_verified_fixed_transition_from_execution_bound_observations(
        previous_record,
        plan,
        current_pages,
        rule_evaluations,
        current_fixes,
        current_contract,
        previous_scan_id=previous_scan_id,
        scan_id=scan_id,
        previous_scan_origin=previous_scan_origin,
        scan_origin=scan_origin,
    )
    if not isinstance(decision, dict):
        return _verified_fixed_denied(
            "plan_execution_bound_verified_fixed_replay_returned_non_object",
            binding,
        )
    return {
        **decision,
        "version": STRICT_VERIFIED_FIXED_OBSERVATION_EXECUTION_BOUND_VERSION,
        "inner_plan_execution_bound_replay_version": decision.get("version", ""),
        "observation_execution_binding": binding,
    }


def _regression_denied(reason: str, binding: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": STRICT_REGRESSION_REOPEN_OBSERVATION_EXECUTION_BOUND_VERSION,
        "should_reopen": False,
        "reason": reason,
        "repair_fingerprint": "",
        "reopen_scope": [],
        "recomputed_verification_state": COULD_NOT_VERIFY,
        "recomputed_result": {},
        "replay": {},
        "observation_execution_binding": binding,
        "inner_plan_execution_bound_replay_version": "",
    }


def strict_regression_reopen_from_observation_execution_bound_inputs(
    previous_record: dict[str, Any],
    plan: dict[str, Any],
    current_pages: list[dict[str, Any]],
    rule_evaluations: list[dict[str, Any]],
    current_contract: dict[str, Any],
    *,
    previous_scan_id: str,
    scan_id: str,
    previous_scan_origin: str = "",
    scan_origin: str = "",
) -> dict[str, Any]:
    """Require exact page+evaluation plan execution provenance before reopening."""
    binding = verification_observation_execution_binding_integrity(
        plan,
        current_pages,
        rule_evaluations,
        previous_scan_id=previous_scan_id,
    )
    if binding.get("valid") is not True:
        return _regression_denied("observation_execution_binding_failed", binding)

    decision = strict_regression_reopen_from_execution_bound_observations(
        previous_record,
        plan,
        current_pages,
        rule_evaluations,
        current_contract,
        previous_scan_id=previous_scan_id,
        scan_id=scan_id,
        previous_scan_origin=previous_scan_origin,
        scan_origin=scan_origin,
    )
    if not isinstance(decision, dict):
        return _regression_denied(
            "plan_execution_bound_regression_replay_returned_non_object",
            binding,
        )
    return {
        **decision,
        "version": STRICT_REGRESSION_REOPEN_OBSERVATION_EXECUTION_BOUND_VERSION,
        "inner_plan_execution_bound_replay_version": decision.get("version", ""),
        "observation_execution_binding": binding,
    }
