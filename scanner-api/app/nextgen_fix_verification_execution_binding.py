from __future__ import annotations

from typing import Any

from .nextgen_fix_verification import COULD_NOT_VERIFY
from .nextgen_fix_verification_plan_identity import (
    PLAN_IDENTITY_BINDING_VERSION,
    strict_regression_reopen_from_identity_bound_observations,
    strict_verified_fixed_transition_from_identity_bound_observations,
    verification_plan_identity_integrity,
)

PLAN_EXECUTION_BINDING_VERSION = (
    "fix_verification_plan_execution_binding_v1_exact_evaluation_plan_identity"
)
STRICT_VERIFIED_FIXED_PLAN_EXECUTION_BOUND_VERSION = (
    "fix_verified_fixed_plan_execution_bound_observation_replay_v1_exact_plan_execution"
)
STRICT_REGRESSION_REOPEN_PLAN_EXECUTION_BOUND_VERSION = (
    "fix_regression_reopen_plan_execution_bound_observation_replay_v1_exact_plan_execution"
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


def verification_plan_execution_binding_integrity(
    plan: dict[str, Any],
    rule_evaluations: list[dict[str, Any]],
    *,
    previous_scan_id: str,
) -> dict[str, Any]:
    """Bind predicate re-evaluations to the exact identity-bound plan transport.

    Plan identity proves which declarative recheck plan was approved. Scan lineage
    proves where the observations came from. Neither alone proves that the
    predicate re-evaluations were produced for that exact plan transport.

    This boundary therefore requires one and only one rule-evaluation row for
    every targeted request and requires each row to carry the exact plan
    fingerprint plus the exact plan-identity contract version. Missing, copied,
    stale, normalized, duplicate, or foreign execution provenance is non-proof.
    """
    base = {
        "version": PLAN_EXECUTION_BINDING_VERSION,
        "valid": False,
        "reason": "verification_plan_execution_binding_not_proven",
        "plan_fingerprint": "",
        "verification_plan_identity_integrity": {},
    }

    if not isinstance(plan, dict):
        return {**base, "reason": "verification_plan_not_an_object"}
    if not isinstance(rule_evaluations, list):
        return {**base, "reason": "rule_evaluations_not_a_list"}
    if any(not isinstance(item, dict) for item in rule_evaluations):
        return {**base, "reason": "rule_evaluations_contains_non_object"}

    identity = verification_plan_identity_integrity(
        plan,
        previous_scan_id=previous_scan_id,
    )
    with_identity = {
        **base,
        "verification_plan_identity_integrity": identity if isinstance(identity, dict) else {},
    }
    if not isinstance(identity, dict) or identity.get("valid") is not True:
        reason = identity.get("reason") if isinstance(identity, dict) else "not_an_object"
        return {
            **with_identity,
            "reason": f"verification_plan_identity_integrity_failed:{reason or 'not_proven'}",
        }

    fingerprint = plan.get("plan_fingerprint")
    if not _exact_nonempty_string(fingerprint):
        return {**with_identity, "reason": "verification_plan_fingerprint_not_exact_nonempty_string"}
    if identity.get("plan_fingerprint") != fingerprint:
        return {**with_identity, "reason": "verification_plan_identity_fingerprint_disagreement"}

    required_keys, request_reason = _request_evidence_keys(plan)
    if request_reason:
        return {**with_identity, "reason": request_reason, "plan_fingerprint": fingerprint}

    evaluation_by_key: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rule_evaluations):
        key = row.get("evidence_key")
        if not _exact_nonempty_string(key):
            return {
                **with_identity,
                "reason": f"rule_evaluation_{index}_evidence_key_must_be_exact_nonempty_string",
                "rule_evaluation_index": index,
                "plan_fingerprint": fingerprint,
            }
        if key in evaluation_by_key:
            return {
                **with_identity,
                "reason": f"rule_evaluation_{index}_duplicate_evidence_key",
                "rule_evaluation_index": index,
                "plan_fingerprint": fingerprint,
            }

        claimed_fingerprint = row.get(_EXECUTION_FINGERPRINT_FIELD)
        if not _exact_nonempty_string(claimed_fingerprint):
            return {
                **with_identity,
                "reason": (
                    f"rule_evaluation_{index}_{_EXECUTION_FINGERPRINT_FIELD}"
                    "_must_be_exact_nonempty_string"
                ),
                "rule_evaluation_index": index,
                "plan_fingerprint": fingerprint,
            }
        if claimed_fingerprint != fingerprint:
            return {
                **with_identity,
                "reason": f"rule_evaluation_{index}_{_EXECUTION_FINGERPRINT_FIELD}_mismatch",
                "rule_evaluation_index": index,
                "plan_fingerprint": fingerprint,
            }

        claimed_identity_version = row.get(_EXECUTION_IDENTITY_VERSION_FIELD)
        if not _exact_nonempty_string(claimed_identity_version):
            return {
                **with_identity,
                "reason": (
                    f"rule_evaluation_{index}_{_EXECUTION_IDENTITY_VERSION_FIELD}"
                    "_must_be_exact_nonempty_string"
                ),
                "rule_evaluation_index": index,
                "plan_fingerprint": fingerprint,
            }
        if claimed_identity_version != PLAN_IDENTITY_BINDING_VERSION:
            return {
                **with_identity,
                "reason": f"rule_evaluation_{index}_{_EXECUTION_IDENTITY_VERSION_FIELD}_mismatch",
                "rule_evaluation_index": index,
                "plan_fingerprint": fingerprint,
            }

        evaluation_by_key[key] = row

    required_set = set(required_keys)
    evaluation_set = set(evaluation_by_key)
    if evaluation_set != required_set:
        missing = [key for key in required_keys if key not in evaluation_set]
        extra = sorted(evaluation_set - required_set)
        return {
            **with_identity,
            "reason": "rule_evaluation_population_does_not_exactly_match_targeted_plan",
            "plan_fingerprint": fingerprint,
            "missing_evidence_keys": missing,
            "unexpected_evidence_keys": extra,
        }

    return {
        **with_identity,
        "valid": True,
        "reason": "all_rule_evaluations_bound_to_exact_targeted_plan_identity",
        "plan_fingerprint": fingerprint,
        "checked_requests": len(required_keys),
        "checked_rule_evaluations": len(rule_evaluations),
    }


def _verified_fixed_denied(reason: str, binding: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": STRICT_VERIFIED_FIXED_PLAN_EXECUTION_BOUND_VERSION,
        "allowed": False,
        "reason": reason,
        "repair_fingerprint": "",
        "recomputed_verification_state": COULD_NOT_VERIFY,
        "recomputed_result": {},
        "replay": {},
        "verification_plan_execution_binding": binding,
        "inner_plan_identity_bound_replay_version": "",
    }


def strict_verified_fixed_transition_from_execution_bound_observations(
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
    """Require exact plan-execution provenance before verified-fixed proof."""
    binding = verification_plan_execution_binding_integrity(
        plan,
        rule_evaluations,
        previous_scan_id=previous_scan_id,
    )
    if binding.get("valid") is not True:
        return _verified_fixed_denied("verification_plan_execution_binding_failed", binding)

    decision = strict_verified_fixed_transition_from_identity_bound_observations(
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
            "plan_identity_bound_verified_fixed_replay_returned_non_object",
            binding,
        )
    return {
        **decision,
        "version": STRICT_VERIFIED_FIXED_PLAN_EXECUTION_BOUND_VERSION,
        "inner_plan_identity_bound_replay_version": decision.get("version", ""),
        "verification_plan_execution_binding": binding,
    }


def _regression_denied(reason: str, binding: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": STRICT_REGRESSION_REOPEN_PLAN_EXECUTION_BOUND_VERSION,
        "should_reopen": False,
        "reason": reason,
        "repair_fingerprint": "",
        "reopen_scope": [],
        "recomputed_verification_state": COULD_NOT_VERIFY,
        "recomputed_result": {},
        "replay": {},
        "verification_plan_execution_binding": binding,
        "inner_plan_identity_bound_replay_version": "",
    }


def strict_regression_reopen_from_execution_bound_observations(
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
    """Require exact plan-execution provenance before regression reopening proof."""
    binding = verification_plan_execution_binding_integrity(
        plan,
        rule_evaluations,
        previous_scan_id=previous_scan_id,
    )
    if binding.get("valid") is not True:
        return _regression_denied("verification_plan_execution_binding_failed", binding)

    decision = strict_regression_reopen_from_identity_bound_observations(
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
            "plan_identity_bound_regression_replay_returned_non_object",
            binding,
        )
    return {
        **decision,
        "version": STRICT_REGRESSION_REOPEN_PLAN_EXECUTION_BOUND_VERSION,
        "inner_plan_identity_bound_replay_version": decision.get("version", ""),
        "verification_plan_execution_binding": binding,
    }
