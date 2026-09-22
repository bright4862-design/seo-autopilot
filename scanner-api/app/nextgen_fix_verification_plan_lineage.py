from __future__ import annotations

from copy import deepcopy
from typing import Any

from .nextgen_fix_verification import (
    COULD_NOT_VERIFY,
    MAX_RECHECK_URLS,
    VERIFICATION_PLAN_VERSION,
    build_targeted_recheck_plan,
)
from .nextgen_fix_verification_scan_lineage import (
    strict_regression_reopen_from_scan_bound_observations,
    strict_verified_fixed_transition_from_scan_bound_observations,
)

PLAN_LINEAGE_BINDING_VERSION = (
    "fix_verification_plan_lineage_binding_v1_exact_historical_scan_id"
)
STRICT_VERIFIED_FIXED_PLAN_SCAN_BOUND_VERSION = (
    "fix_verified_fixed_plan_scan_bound_observation_replay_v1_exact_historical_plan_lineage"
)
STRICT_REGRESSION_REOPEN_PLAN_SCAN_BOUND_VERSION = (
    "fix_regression_reopen_plan_scan_bound_observation_replay_v1_exact_historical_plan_lineage"
)

_SOURCE_ID_FIELDS = ("scan_run_id", "scan_id", "source_scan_id")
_INVALID_PREVIOUS_SCAN_ID_BLOCKER = "previous_scan_id_exact_nonempty_string_required"


def _exact_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _source_claim_reason(
    container: dict[str, Any],
    expected_scan_id: str,
    *,
    label: str,
) -> str:
    if not isinstance(container, dict):
        return f"{label}_not_an_object"

    present = [
        (field, container.get(field))
        for field in _SOURCE_ID_FIELDS
        if field in container
    ]
    if not present:
        return f"{label}_source_scan_id_missing"

    for field, value in present:
        if not _exact_nonempty_string(value):
            return f"{label}_{field}_must_be_exact_nonempty_string"
        if value != expected_scan_id:
            return f"{label}_{field}_mismatch"
    return ""


def build_scan_bound_targeted_recheck_plan(
    previous_fix: dict[str, Any],
    *,
    previous_scan_origin: str = "",
    previous_scan_id: str,
    max_urls: int = MAX_RECHECK_URLS,
) -> dict[str, Any]:
    """Build a targeted recheck plan explicitly bound to its historical scan.

    The existing v1 plan remains unchanged for compatibility. This additive
    envelope stamps provenance on the plan and every request so a later strict
    consumer can distinguish an exact plan produced for the authoritative
    historical scan from an otherwise identical transported plan.
    """
    plan = deepcopy(
        build_targeted_recheck_plan(
            previous_fix,
            previous_scan_origin=previous_scan_origin,
            max_urls=max_urls,
        )
    )
    exact_scan_id = previous_scan_id if _exact_nonempty_string(previous_scan_id) else ""
    plan["plan_lineage_version"] = PLAN_LINEAGE_BINDING_VERSION
    plan["source_scan_id"] = exact_scan_id

    requests = plan.get("requests")
    if isinstance(requests, list):
        for request in requests:
            if isinstance(request, dict):
                request["source_scan_id"] = exact_scan_id

    if not exact_scan_id:
        blockers = list(plan.get("blockers")) if isinstance(plan.get("blockers"), list) else []
        if _INVALID_PREVIOUS_SCAN_ID_BLOCKER not in blockers:
            blockers.append(_INVALID_PREVIOUS_SCAN_ID_BLOCKER)
        plan["blockers"] = blockers
        plan["state"] = "blocked"
        plan["population_complete"] = False

    return plan


def verification_plan_lineage_integrity(
    plan: dict[str, Any],
    *,
    previous_scan_id: str,
) -> dict[str, Any]:
    """Prove that a transported targeted plan belongs to one historical scan.

    Presence is a claim. Null, empty, whitespace-normalized, conflicting, or
    foreign scan-id aliases on either the plan or any request are ambiguous and
    therefore non-proof.
    """
    base = {
        "version": PLAN_LINEAGE_BINDING_VERSION,
        "valid": False,
        "reason": "verification_plan_lineage_not_proven",
        "previous_scan_id": previous_scan_id if _exact_nonempty_string(previous_scan_id) else "",
    }

    if not _exact_nonempty_string(previous_scan_id):
        return {**base, "reason": "previous_scan_id_must_be_exact_nonempty_string"}
    if not isinstance(plan, dict):
        return {**base, "reason": "verification_plan_not_an_object"}
    if plan.get("version") != VERIFICATION_PLAN_VERSION:
        return {**base, "reason": "unsupported_verification_plan_version"}
    if plan.get("plan_lineage_version") != PLAN_LINEAGE_BINDING_VERSION:
        return {**base, "reason": "verification_plan_lineage_version_missing_or_unsupported"}

    reason = _source_claim_reason(plan, previous_scan_id, label="verification_plan")
    if reason:
        return {**base, "reason": reason}

    requests = plan.get("requests")
    if not isinstance(requests, list):
        return {**base, "reason": "verification_plan_requests_not_a_list"}
    for index, request in enumerate(requests):
        reason = _source_claim_reason(
            request,
            previous_scan_id,
            label=f"verification_request_{index}",
        )
        if reason:
            return {**base, "reason": reason, "verification_request_index": index}

    return {
        **base,
        "valid": True,
        "reason": "verification_plan_and_requests_bound_to_exact_historical_scan",
        "checked_requests": len(requests),
    }


def _verified_fixed_denied(reason: str, binding: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": STRICT_VERIFIED_FIXED_PLAN_SCAN_BOUND_VERSION,
        "allowed": False,
        "reason": reason,
        "repair_fingerprint": "",
        "recomputed_verification_state": COULD_NOT_VERIFY,
        "recomputed_result": {},
        "replay": {},
        "verification_plan_lineage_integrity": binding,
    }


def strict_verified_fixed_transition_from_plan_scan_bound_observations(
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
    """Require exact plan provenance before the existing scan-bound fixed replay."""
    binding = verification_plan_lineage_integrity(
        plan,
        previous_scan_id=previous_scan_id,
    )
    if binding.get("valid") is not True:
        return _verified_fixed_denied("verification_plan_lineage_binding_failed", binding)

    decision = strict_verified_fixed_transition_from_scan_bound_observations(
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
        return _verified_fixed_denied("scan_bound_verified_fixed_replay_returned_non_object", binding)

    return {
        **decision,
        "version": STRICT_VERIFIED_FIXED_PLAN_SCAN_BOUND_VERSION,
        "inner_scan_bound_replay_version": decision.get("version", ""),
        "verification_plan_lineage_integrity": binding,
    }


def _regression_denied(reason: str, binding: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": STRICT_REGRESSION_REOPEN_PLAN_SCAN_BOUND_VERSION,
        "should_reopen": False,
        "reason": reason,
        "repair_fingerprint": "",
        "reopen_scope": [],
        "recomputed_verification_state": COULD_NOT_VERIFY,
        "recomputed_result": {},
        "replay": {},
        "verification_plan_lineage_integrity": binding,
    }


def strict_regression_reopen_from_plan_scan_bound_observations(
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
    """Require exact plan provenance before the existing scan-bound reopen replay."""
    binding = verification_plan_lineage_integrity(
        plan,
        previous_scan_id=previous_scan_id,
    )
    if binding.get("valid") is not True:
        return _regression_denied("verification_plan_lineage_binding_failed", binding)

    decision = strict_regression_reopen_from_scan_bound_observations(
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
        return _regression_denied("scan_bound_regression_replay_returned_non_object", binding)

    return {
        **decision,
        "version": STRICT_REGRESSION_REOPEN_PLAN_SCAN_BOUND_VERSION,
        "inner_scan_bound_replay_version": decision.get("version", ""),
        "verification_plan_lineage_integrity": binding,
    }
