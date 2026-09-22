from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any

from .nextgen_fix_verification import COULD_NOT_VERIFY, MAX_RECHECK_URLS
from .nextgen_fix_verification_plan_envelope import verification_plan_envelope_integrity
from .nextgen_fix_verification_plan_lineage import (
    build_scan_bound_targeted_recheck_plan,
    strict_regression_reopen_from_plan_scan_bound_observations,
    strict_verified_fixed_transition_from_plan_scan_bound_observations,
    verification_plan_lineage_integrity,
)

PLAN_IDENTITY_BINDING_VERSION = (
    "fix_verification_plan_identity_binding_v1_exact_proof_contract_hash"
)
STRICT_VERIFIED_FIXED_PLAN_IDENTITY_BOUND_VERSION = (
    "fix_verified_fixed_plan_identity_bound_observation_replay_v1_exact_plan_contract"
)
STRICT_REGRESSION_REOPEN_PLAN_IDENTITY_BOUND_VERSION = (
    "fix_regression_reopen_plan_identity_bound_observation_replay_v1_exact_plan_contract"
)

_IDENTITY_FIELDS = frozenset(
    {
        "plan_identity_version",
        "plan_identity_state",
        "plan_identity_reason",
        "plan_fingerprint",
    }
)


def _exact_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _strict_json_transport_reason(value: Any, *, path: str) -> str:
    """Reject values whose serialized form could hide coercion or ambiguity."""
    if value is None or isinstance(value, (str, bool)):
        return ""
    if isinstance(value, int) and not isinstance(value, bool):
        return ""
    if isinstance(value, list):
        for index, item in enumerate(value):
            reason = _strict_json_transport_reason(item, path=f"{path}_{index}")
            if reason:
                return reason
        return ""
    if isinstance(value, dict):
        for key, item in value.items():
            if not _exact_nonempty_string(key):
                return f"{path}_contains_nonexact_object_key"
            reason = _strict_json_transport_reason(item, path=f"{path}_{key}")
            if reason:
                return reason
        return ""
    return f"{path}_contains_unsupported_transport_type"


def _identity_material(
    plan: dict[str, Any],
    *,
    previous_scan_id: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str]:
    if not isinstance(plan, dict):
        return {}, {}, {}, "verification_plan_not_an_object"

    envelope = verification_plan_envelope_integrity(plan)
    if not isinstance(envelope, dict) or envelope.get("valid") is not True:
        reason = envelope.get("reason") if isinstance(envelope, dict) else "not_an_object"
        return {}, envelope if isinstance(envelope, dict) else {}, {}, (
            f"verification_plan_envelope_integrity_failed:{reason or 'not_proven'}"
        )

    lineage = verification_plan_lineage_integrity(
        plan,
        previous_scan_id=previous_scan_id,
    )
    if not isinstance(lineage, dict) or lineage.get("valid") is not True:
        reason = lineage.get("reason") if isinstance(lineage, dict) else "not_an_object"
        return {}, envelope, lineage if isinstance(lineage, dict) else {}, (
            f"verification_plan_lineage_integrity_failed:{reason or 'not_proven'}"
        )

    material = {
        key: deepcopy(value)
        for key, value in plan.items()
        if key not in _IDENTITY_FIELDS
    }
    reason = _strict_json_transport_reason(material, path="verification_plan")
    if reason:
        return {}, envelope, lineage, reason
    return material, envelope, lineage, ""


def _fingerprint(material: dict[str, Any]) -> str:
    payload = json.dumps(
        material,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def bind_verification_plan_identity(
    plan: dict[str, Any],
    *,
    previous_scan_id: str,
) -> dict[str, Any]:
    """Return a copy whose exact ready-plan transport is committed by hash.

    The fingerprint covers the complete plan transport, including exact raw
    request URLs, evidence keys, acceptance-criterion material, bounded-population
    metadata, required observations, and scan-lineage claims. Only the identity
    metadata itself is excluded from the hash.
    """
    bound = deepcopy(plan) if isinstance(plan, dict) else {}
    material, _, _, reason = _identity_material(
        bound,
        previous_scan_id=previous_scan_id,
    )
    bound["plan_identity_version"] = PLAN_IDENTITY_BINDING_VERSION
    if reason:
        bound["plan_identity_state"] = "blocked"
        bound["plan_identity_reason"] = reason
        bound["plan_fingerprint"] = ""
        return bound

    bound["plan_identity_state"] = "bound"
    bound["plan_identity_reason"] = "exact_ready_plan_transport_bound"
    bound["plan_fingerprint"] = _fingerprint(material)
    return bound


def build_identity_bound_targeted_recheck_plan(
    previous_fix: dict[str, Any],
    *,
    previous_scan_origin: str = "",
    previous_scan_id: str,
    max_urls: int = MAX_RECHECK_URLS,
) -> dict[str, Any]:
    """Build the existing scan-bound plan and commit its exact transport identity."""
    plan = build_scan_bound_targeted_recheck_plan(
        previous_fix,
        previous_scan_origin=previous_scan_origin,
        previous_scan_id=previous_scan_id,
        max_urls=max_urls,
    )
    return bind_verification_plan_identity(
        plan,
        previous_scan_id=previous_scan_id,
    )


def verification_plan_identity_integrity(
    plan: dict[str, Any],
    *,
    previous_scan_id: str,
) -> dict[str, Any]:
    """Fail closed unless a plan is the exact transport that was identity-bound."""
    base = {
        "version": PLAN_IDENTITY_BINDING_VERSION,
        "valid": False,
        "reason": "verification_plan_identity_not_proven",
        "plan_fingerprint": "",
        "verification_plan_envelope_integrity": {},
        "verification_plan_lineage_integrity": {},
    }
    if not isinstance(plan, dict):
        return {**base, "reason": "verification_plan_not_an_object"}
    if plan.get("plan_identity_version") != PLAN_IDENTITY_BINDING_VERSION:
        return {**base, "reason": "verification_plan_identity_version_missing_or_unsupported"}
    if plan.get("plan_identity_state") != "bound":
        return {**base, "reason": "verification_plan_identity_not_bound"}
    if plan.get("plan_identity_reason") != "exact_ready_plan_transport_bound":
        return {**base, "reason": "verification_plan_identity_reason_mismatch"}

    declared = plan.get("plan_fingerprint")
    if not _exact_nonempty_string(declared) or len(declared) != 64:
        return {**base, "reason": "verification_plan_fingerprint_not_exact_sha256"}
    try:
        int(declared, 16)
    except ValueError:
        return {**base, "reason": "verification_plan_fingerprint_not_exact_sha256"}
    if declared.lower() != declared:
        return {**base, "reason": "verification_plan_fingerprint_not_exact_sha256"}

    material, envelope, lineage, reason = _identity_material(
        plan,
        previous_scan_id=previous_scan_id,
    )
    with_integrity = {
        **base,
        "plan_fingerprint": declared,
        "verification_plan_envelope_integrity": envelope,
        "verification_plan_lineage_integrity": lineage,
    }
    if reason:
        return {**with_integrity, "reason": reason}

    expected = _fingerprint(material)
    if declared != expected:
        return {
            **with_integrity,
            "reason": "verification_plan_fingerprint_mismatch",
            "expected_plan_fingerprint": expected,
        }

    return {
        **with_integrity,
        "valid": True,
        "reason": "exact_ready_plan_transport_identity_proven",
        "expected_plan_fingerprint": expected,
    }


def _verified_fixed_denied(reason: str, identity: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": STRICT_VERIFIED_FIXED_PLAN_IDENTITY_BOUND_VERSION,
        "allowed": False,
        "reason": reason,
        "repair_fingerprint": "",
        "recomputed_verification_state": COULD_NOT_VERIFY,
        "recomputed_result": {},
        "replay": {},
        "verification_plan_identity_integrity": identity,
        "inner_plan_scan_bound_replay_version": "",
    }


def strict_verified_fixed_transition_from_identity_bound_observations(
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
    """Require exact plan identity before the existing plan+scan-bound replay."""
    identity = verification_plan_identity_integrity(
        plan,
        previous_scan_id=previous_scan_id,
    )
    if identity.get("valid") is not True:
        return _verified_fixed_denied("verification_plan_identity_binding_failed", identity)

    decision = strict_verified_fixed_transition_from_plan_scan_bound_observations(
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
            "plan_scan_bound_verified_fixed_replay_returned_non_object",
            identity,
        )
    return {
        **decision,
        "version": STRICT_VERIFIED_FIXED_PLAN_IDENTITY_BOUND_VERSION,
        "inner_plan_scan_bound_replay_version": decision.get("version", ""),
        "verification_plan_identity_integrity": identity,
    }


def _regression_denied(reason: str, identity: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": STRICT_REGRESSION_REOPEN_PLAN_IDENTITY_BOUND_VERSION,
        "should_reopen": False,
        "reason": reason,
        "repair_fingerprint": "",
        "reopen_scope": [],
        "recomputed_verification_state": COULD_NOT_VERIFY,
        "recomputed_result": {},
        "replay": {},
        "verification_plan_identity_integrity": identity,
        "inner_plan_scan_bound_replay_version": "",
    }


def strict_regression_reopen_from_identity_bound_observations(
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
    """Require exact plan identity before the existing regression-reopen replay."""
    identity = verification_plan_identity_integrity(
        plan,
        previous_scan_id=previous_scan_id,
    )
    if identity.get("valid") is not True:
        return _regression_denied("verification_plan_identity_binding_failed", identity)

    decision = strict_regression_reopen_from_plan_scan_bound_observations(
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
            "plan_scan_bound_regression_replay_returned_non_object",
            identity,
        )
    return {
        **decision,
        "version": STRICT_REGRESSION_REOPEN_PLAN_IDENTITY_BOUND_VERSION,
        "inner_plan_scan_bound_replay_version": decision.get("version", ""),
        "verification_plan_identity_integrity": identity,
    }
