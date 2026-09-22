from __future__ import annotations

from typing import Any

SCAN_LINEAGE_BINDING_VERSION = (
    "fix_verification_scan_lineage_binding_v1_exact_source_scan_ids"
)
STRICT_VERIFIED_FIXED_SCAN_BOUND_VERSION = (
    "fix_verified_fixed_scan_bound_observation_replay_v1_exact_source_scan_ids"
)
STRICT_REGRESSION_REOPEN_SCAN_BOUND_VERSION = (
    "fix_regression_reopen_scan_bound_observation_replay_v1_exact_source_scan_ids"
)

_SOURCE_ID_FIELDS = ("scan_run_id", "scan_id", "source_scan_id")


def _exact_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _source_claim_reason(
    container: dict[str, Any],
    expected_scan_id: str,
    *,
    label: str,
    require_claim: bool = True,
) -> str:
    if not isinstance(container, dict):
        return f"{label}_not_an_object"

    # Presence itself is a claim. A present null alias must not be ignored just
    # because another alias happens to carry the expected scan id; that would let
    # ambiguous transport metadata participate in proof.
    present: list[tuple[str, Any]] = [
        (field, container.get(field))
        for field in _SOURCE_ID_FIELDS
        if field in container
    ]
    if not present:
        return f"{label}_source_scan_id_missing" if require_claim else ""

    for field, value in present:
        if not _exact_nonempty_string(value):
            return f"{label}_{field}_must_be_exact_nonempty_string"
        if value != expected_scan_id:
            return f"{label}_{field}_mismatch"

    return ""


def verification_scan_lineage_integrity(
    previous_record: dict[str, Any],
    current_contract: dict[str, Any],
    current_pages: list[dict[str, Any]],
    rule_evaluations: list[dict[str, Any]],
    current_fixes: list[dict[str, Any]] | None = None,
    *,
    previous_scan_id: str,
    scan_id: str,
) -> dict[str, Any]:
    """Bind all proof-bearing inputs to exact historical/current scan identities.

    URL-origin binding proves that evidence belongs to the same website origin.
    It does not prove that page observations, rule evaluations, comparison
    metadata, and the current fix population were produced by the same scan run.
    This pure boundary closes that gap by requiring exact caller-owned scan IDs
    plus matching source claims on every proving input.

    Nothing is persisted or mutated. A missing, null, whitespace-normalized,
    conflicting, or cross-scan source claim is non-proof.
    """
    base = {
        "version": SCAN_LINEAGE_BINDING_VERSION,
        "valid": False,
        "reason": "scan_lineage_not_proven",
        "previous_scan_id": previous_scan_id if _exact_nonempty_string(previous_scan_id) else "",
        "scan_id": scan_id if _exact_nonempty_string(scan_id) else "",
    }

    if not _exact_nonempty_string(previous_scan_id):
        return {**base, "reason": "previous_scan_id_must_be_exact_nonempty_string"}
    if not _exact_nonempty_string(scan_id):
        return {**base, "reason": "scan_id_must_be_exact_nonempty_string"}
    if previous_scan_id == scan_id:
        return {**base, "reason": "historical_and_current_scan_ids_must_differ"}

    if not isinstance(previous_record, dict):
        return {**base, "reason": "previous_record_not_an_object"}
    if not isinstance(current_contract, dict):
        return {**base, "reason": "current_contract_not_an_object"}
    if not isinstance(current_pages, list):
        return {**base, "reason": "current_pages_not_a_list"}
    if not isinstance(rule_evaluations, list):
        return {**base, "reason": "rule_evaluations_not_a_list"}
    if current_fixes is not None and not isinstance(current_fixes, list):
        return {**base, "reason": "current_fixes_not_a_list"}

    reason = _source_claim_reason(
        previous_record,
        previous_scan_id,
        label="previous_record",
    )
    if reason:
        return {**base, "reason": reason}

    reason = _source_claim_reason(
        current_contract,
        scan_id,
        label="current_contract",
    )
    if reason:
        return {**base, "reason": reason}

    for index, page in enumerate(current_pages):
        reason = _source_claim_reason(
            page,
            scan_id,
            label=f"current_page_{index}",
        )
        if reason:
            return {**base, "reason": reason, "current_page_index": index}

    for index, row in enumerate(rule_evaluations):
        reason = _source_claim_reason(
            row,
            scan_id,
            label=f"rule_evaluation_{index}",
        )
        if reason:
            return {**base, "reason": reason, "rule_evaluation_index": index}

    fixes = current_fixes if isinstance(current_fixes, list) else []
    for index, fix in enumerate(fixes):
        reason = _source_claim_reason(
            fix,
            scan_id,
            label=f"current_fix_{index}",
        )
        if reason:
            return {**base, "reason": reason, "current_fix_index": index}

    return {
        **base,
        "valid": True,
        "reason": "all_proving_inputs_bound_to_exact_scan_lineage",
        "checked_current_pages": len(current_pages),
        "checked_rule_evaluations": len(rule_evaluations),
        "checked_current_fixes": len(fixes),
    }


def _positive_denied(reason: str, lineage: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": STRICT_VERIFIED_FIXED_SCAN_BOUND_VERSION,
        "allowed": False,
        "reason": reason,
        "repair_fingerprint": "",
        "recomputed_verification_state": "COULD_NOT_VERIFY",
        "recomputed_result": {},
        "replay": {},
        "scan_lineage_binding": lineage,
    }


def strict_verified_fixed_transition_from_scan_bound_observations(
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
    """Require exact scan lineage before the existing final verified-fixed replay."""
    lineage = verification_scan_lineage_integrity(
        previous_record,
        current_contract,
        current_pages,
        rule_evaluations,
        current_fixes,
        previous_scan_id=previous_scan_id,
        scan_id=scan_id,
    )
    if lineage.get("valid") is not True:
        return _positive_denied("scan_lineage_binding_failed", lineage)

    from .nextgen_fix_verified_fixed_observation_replay import (
        strict_verified_fixed_transition_from_observations,
    )

    decision = strict_verified_fixed_transition_from_observations(
        previous_record,
        plan,
        current_pages,
        rule_evaluations,
        current_fixes,
        current_contract,
        previous_scan_origin=previous_scan_origin,
        scan_origin=scan_origin,
    )
    if not isinstance(decision, dict):
        return _positive_denied("verified_fixed_observation_replay_returned_non_object", lineage)

    return {
        **decision,
        "version": STRICT_VERIFIED_FIXED_SCAN_BOUND_VERSION,
        "inner_observation_replay_version": decision.get("version", ""),
        "scan_lineage_binding": lineage,
    }


def _reopen_denied(reason: str, lineage: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": STRICT_REGRESSION_REOPEN_SCAN_BOUND_VERSION,
        "should_reopen": False,
        "reason": reason,
        "repair_fingerprint": "",
        "reopen_scope": [],
        "recomputed_verification_state": "COULD_NOT_VERIFY",
        "recomputed_result": {},
        "replay": {},
        "scan_lineage_binding": lineage,
    }


def strict_regression_reopen_from_scan_bound_observations(
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
    """Require exact scan lineage before the existing final regression replay."""
    lineage = verification_scan_lineage_integrity(
        previous_record,
        current_contract,
        current_pages,
        rule_evaluations,
        None,
        previous_scan_id=previous_scan_id,
        scan_id=scan_id,
    )
    if lineage.get("valid") is not True:
        return _reopen_denied("scan_lineage_binding_failed", lineage)

    from .nextgen_fix_regression_reopen_replay import (
        strict_regression_reopen_from_observations,
    )

    decision = strict_regression_reopen_from_observations(
        previous_record,
        plan,
        current_pages,
        rule_evaluations,
        current_contract,
        previous_scan_origin=previous_scan_origin,
        scan_origin=scan_origin,
    )
    if not isinstance(decision, dict):
        return _reopen_denied("regression_observation_replay_returned_non_object", lineage)

    return {
        **decision,
        "version": STRICT_REGRESSION_REOPEN_SCAN_BOUND_VERSION,
        "inner_observation_replay_version": decision.get("version", ""),
        "scan_lineage_binding": lineage,
    }
