from __future__ import annotations

from typing import Any

from .nextgen_fix_verification import COULD_NOT_VERIFY
from .nextgen_fix_verification_observation_execution import (
    strict_regression_reopen_from_observation_execution_bound_inputs,
    strict_verified_fixed_transition_from_observation_execution_bound_inputs,
    verification_observation_execution_binding_integrity,
)
from .nextgen_fix_verification_observation_identity import (
    verification_observation_identity_binding,
)
from .repair_coverage import (
    PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION,
    repair_evidence_key_function,
)

PAGE_RECEIPT_IDENTITY_BINDING_VERSION = (
    "fix_verification_page_receipt_identity_binding_v1_exact_evidence_key_url_identity"
)
STRICT_VERIFIED_FIXED_PAGE_RECEIPT_IDENTITY_BOUND_VERSION = (
    "fix_verified_fixed_page_receipt_identity_bound_replay_v1_exact_page_evidence_key"
)
STRICT_REGRESSION_REOPEN_PAGE_RECEIPT_IDENTITY_BOUND_VERSION = (
    "fix_regression_reopen_page_receipt_identity_bound_replay_v1_exact_page_evidence_key"
)

_PAGE_IDENTITY_FIELDS = ("url", "final_url", "page_url", "path")


def _exact_nonempty_string(value: Any) -> bool:
    """Return true only for already-canonical non-empty string transport."""
    return isinstance(value, str) and bool(value) and value == value.strip()


def _resolved_page_identity(
    page: dict[str, Any],
    *,
    key_for: Any,
    index: int,
) -> tuple[str, dict[str, str], str]:
    """Resolve all populated page identity aliases and require exact agreement."""
    resolved: dict[str, str] = {}
    for field in _PAGE_IDENTITY_FIELDS:
        if field not in page:
            continue
        value = page.get(field)
        if value is None or value == "":
            continue
        if not _exact_nonempty_string(value):
            return "", {}, f"current_page_{index}_{field}_must_be_exact_nonempty_string"
        key = key_for(value)
        if not key:
            return "", {}, f"current_page_{index}_{field}_identity_unresolvable"
        resolved[field] = key

    if not resolved:
        return "", {}, f"current_page_{index}_evidence_identity_missing"
    if len(set(resolved.values())) != 1:
        return "", resolved, f"current_page_{index}_identity_fields_conflict"
    return next(iter(resolved.values())), resolved, ""


def verification_page_receipt_identity_binding_integrity(
    plan: dict[str, Any],
    current_pages: list[dict[str, Any]],
    rule_evaluations: list[dict[str, Any]],
    current_contract: dict[str, Any],
    *,
    previous_scan_id: str,
    scan_origin: str,
) -> dict[str, Any]:
    """Bind each present page receipt's declared evidence key to its actual URL identity.

    The preceding execution boundary proves that page receipts name targeted evidence
    keys and belong to the exact plan execution. The observation-identity boundary
    proves that URL aliases on a page row are internally consistent. Neither alone
    proves that the declared ``evidence_key`` on a receipt identifies that page.

    This boundary requires an exact one-to-one match between each present receipt's
    targeted evidence key and the canonical page identity derived under the published
    URL-identity contract. A copied/swapped label is therefore non-proof. Missing
    targeted pages remain valid input to this binding and are left to the downstream
    evaluator, which must return ``required_page_not_observed`` / ``COULD_NOT_VERIFY``.
    """
    base = {
        "version": PAGE_RECEIPT_IDENTITY_BINDING_VERSION,
        "valid": False,
        "reason": "page_receipt_identity_binding_not_proven",
        "plan_fingerprint": "",
        "observation_execution_binding": {},
        "observation_identity_binding": {},
    }

    if not _exact_nonempty_string(scan_origin):
        return {**base, "reason": "scan_origin_must_be_exact_nonempty_string"}
    if not isinstance(current_contract, dict):
        return {**base, "reason": "current_contract_not_an_object"}

    execution = verification_observation_execution_binding_integrity(
        plan,
        current_pages,
        rule_evaluations,
        previous_scan_id=previous_scan_id,
    )
    with_execution = {
        **base,
        "observation_execution_binding": execution if isinstance(execution, dict) else {},
    }
    if not isinstance(execution, dict) or execution.get("valid") is not True:
        reason = execution.get("reason") if isinstance(execution, dict) else "not_an_object"
        return {
            **with_execution,
            "reason": f"observation_execution_binding_failed:{reason or 'not_proven'}",
        }

    identity = verification_observation_identity_binding(
        current_pages,
        rule_evaluations,
        current_contract,
        scan_origin=scan_origin,
    )
    with_identity = {
        **with_execution,
        "plan_fingerprint": execution.get("plan_fingerprint", ""),
        "observation_identity_binding": identity if isinstance(identity, dict) else {},
    }
    if not isinstance(identity, dict) or identity.get("valid") is not True:
        reason = identity.get("reason") if isinstance(identity, dict) else "not_an_object"
        return {
            **with_identity,
            "reason": f"observation_identity_binding_failed:{reason or 'not_proven'}",
        }

    identity_version = current_contract.get("evidence_url_identity_version")
    if not _exact_nonempty_string(identity_version):
        return {
            **with_identity,
            "reason": "current_contract_evidence_url_identity_version_must_be_exact_nonempty_string",
        }
    if identity_version != PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION:
        return {**with_identity, "reason": "unsupported_evidence_url_identity_version"}

    try:
        key_for = repair_evidence_key_function(
            scan_origin=scan_origin,
            identity_version=identity_version,
        )
    except (TypeError, ValueError):
        return {**with_identity, "reason": "page_receipt_identity_context_invalid"}

    checked_keys: list[str] = []
    for index, page in enumerate(current_pages):
        declared_key = page.get("evidence_key")
        if not _exact_nonempty_string(declared_key):
            return {
                **with_identity,
                "reason": f"current_page_{index}_evidence_key_must_be_exact_nonempty_string",
                "current_page_index": index,
            }

        resolved_key, resolved_fields, reason = _resolved_page_identity(
            page,
            key_for=key_for,
            index=index,
        )
        if reason:
            return {
                **with_identity,
                "reason": reason,
                "current_page_index": index,
                "resolved_identity_fields": resolved_fields,
            }
        if declared_key != resolved_key:
            return {
                **with_identity,
                "reason": f"current_page_{index}_evidence_key_does_not_match_page_identity",
                "current_page_index": index,
                "declared_evidence_key": declared_key,
                "resolved_evidence_key": resolved_key,
                "resolved_identity_fields": resolved_fields,
            }
        checked_keys.append(declared_key)

    return {
        **with_identity,
        "valid": True,
        "reason": "all_present_page_receipt_evidence_keys_match_exact_page_identity",
        "checked_current_pages": len(current_pages),
        "checked_evidence_keys": checked_keys,
        "missing_required_evidence_keys": list(
            execution.get("missing_required_evidence_keys") or []
        ),
    }


def _verified_fixed_denied(reason: str, binding: dict[str, Any]) -> dict[str, Any]:
    """Return the fail-closed verified-fixed transport for this boundary."""
    return {
        "version": STRICT_VERIFIED_FIXED_PAGE_RECEIPT_IDENTITY_BOUND_VERSION,
        "allowed": False,
        "reason": reason,
        "repair_fingerprint": "",
        "recomputed_verification_state": COULD_NOT_VERIFY,
        "recomputed_result": {},
        "replay": {},
        "page_receipt_identity_binding": binding,
        "inner_observation_execution_bound_replay_version": "",
    }


def strict_verified_fixed_transition_from_page_receipt_identity_bound_inputs(
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
    """Require exact page receipt identity before any verified-fixed proof."""
    binding = verification_page_receipt_identity_binding_integrity(
        plan,
        current_pages,
        rule_evaluations,
        current_contract,
        previous_scan_id=previous_scan_id,
        scan_origin=scan_origin,
    )
    if binding.get("valid") is not True:
        return _verified_fixed_denied("page_receipt_identity_binding_failed", binding)

    decision = strict_verified_fixed_transition_from_observation_execution_bound_inputs(
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
            "observation_execution_bound_verified_fixed_replay_returned_non_object",
            binding,
        )
    return {
        **decision,
        "version": STRICT_VERIFIED_FIXED_PAGE_RECEIPT_IDENTITY_BOUND_VERSION,
        "inner_observation_execution_bound_replay_version": decision.get("version", ""),
        "page_receipt_identity_binding": binding,
    }


def _regression_denied(reason: str, binding: dict[str, Any]) -> dict[str, Any]:
    """Return the fail-closed regression-reopen transport for this boundary."""
    return {
        "version": STRICT_REGRESSION_REOPEN_PAGE_RECEIPT_IDENTITY_BOUND_VERSION,
        "should_reopen": False,
        "reason": reason,
        "repair_fingerprint": "",
        "reopen_scope": [],
        "recomputed_verification_state": COULD_NOT_VERIFY,
        "recomputed_result": {},
        "replay": {},
        "page_receipt_identity_binding": binding,
        "inner_observation_execution_bound_replay_version": "",
    }


def strict_regression_reopen_from_page_receipt_identity_bound_inputs(
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
    """Require exact page receipt identity before regression reopening proof."""
    binding = verification_page_receipt_identity_binding_integrity(
        plan,
        current_pages,
        rule_evaluations,
        current_contract,
        previous_scan_id=previous_scan_id,
        scan_origin=scan_origin,
    )
    if binding.get("valid") is not True:
        return _regression_denied("page_receipt_identity_binding_failed", binding)

    decision = strict_regression_reopen_from_observation_execution_bound_inputs(
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
            "observation_execution_bound_regression_replay_returned_non_object",
            binding,
        )
    return {
        **decision,
        "version": STRICT_REGRESSION_REOPEN_PAGE_RECEIPT_IDENTITY_BOUND_VERSION,
        "inner_observation_execution_bound_replay_version": decision.get("version", ""),
        "page_receipt_identity_binding": binding,
    }
