from __future__ import annotations

import hashlib
import json
from typing import Any

from .nextgen_fix_verification import COULD_NOT_VERIFY
from .nextgen_fix_verification_page_receipt_identity import (
    strict_regression_reopen_from_page_receipt_identity_bound_inputs,
    strict_verified_fixed_transition_from_page_receipt_identity_bound_inputs,
    verification_page_receipt_identity_binding_integrity,
)

PAGE_OBSERVATION_RECEIPT_VERSION = (
    "fix_verification_page_observation_receipt_v1_exact_proof_transport_sha256"
)
EVALUATION_RECEIPT_BINDING_VERSION = (
    "fix_verification_evaluation_receipt_binding_v1_exact_page_observation_receipt"
)
STRICT_VERIFIED_FIXED_EVALUATION_RECEIPT_BOUND_VERSION = (
    "fix_verified_fixed_evaluation_receipt_bound_replay_v1_exact_page_observation_receipt"
)
STRICT_REGRESSION_REOPEN_EVALUATION_RECEIPT_BOUND_VERSION = (
    "fix_regression_reopen_evaluation_receipt_bound_replay_v1_exact_page_observation_receipt"
)

_RECEIPT_VERSION_FIELD = "page_observation_receipt_version"
_RECEIPT_FINGERPRINT_FIELD = "page_observation_receipt_fingerprint"
_PAGE_PROOF_FIELDS = (
    "scan_run_id",
    "scan_id",
    "source_scan_id",
    "evidence_key",
    "verification_plan_fingerprint",
    "verification_plan_identity_version",
    "url",
    "final_url",
    "page_url",
    "path",
    "status_code",
    "status",
    "content_type",
    "mime_type",
    "indexable",
    "page_evidence_class",
    "evidence_class",
    "robots",
    "robots_meta",
    "meta_robots",
)


def _exact_nonempty_string(value: Any) -> bool:
    """Return true only for already-canonical non-empty string transport."""
    return isinstance(value, str) and bool(value) and value == value.strip()


def _exact_sha256(value: Any) -> bool:
    """Require a lowercase 64-character SHA-256 transport value."""
    if not _exact_nonempty_string(value) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return value.lower() == value


def _page_receipt_material(page: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Extract only fields that can affect page comparability or evidence identity."""
    if not isinstance(page, dict):
        return {}, "current_page_not_an_object"

    material: dict[str, Any] = {}
    for field in _PAGE_PROOF_FIELDS:
        if field not in page:
            continue
        value = page.get(field)
        if value is None or isinstance(value, (str, bool)):
            material[field] = value
            continue
        if isinstance(value, int) and not isinstance(value, bool):
            material[field] = value
            continue
        return {}, f"current_page_{field}_contains_unsupported_receipt_transport_type"

    evidence_key = material.get("evidence_key")
    if not _exact_nonempty_string(evidence_key):
        return {}, "current_page_evidence_key_must_be_exact_nonempty_string"
    plan_fingerprint = material.get("verification_plan_fingerprint")
    if not _exact_sha256(plan_fingerprint):
        return {}, "current_page_verification_plan_fingerprint_must_be_exact_sha256"
    plan_identity_version = material.get("verification_plan_identity_version")
    if not _exact_nonempty_string(plan_identity_version):
        return {}, "current_page_verification_plan_identity_version_must_be_exact_nonempty_string"
    return material, ""


def page_observation_receipt_fingerprint(page: dict[str, Any]) -> tuple[str, str]:
    """Hash the exact proof-bearing page transport without coercion or normalization."""
    material, reason = _page_receipt_material(page)
    if reason:
        return "", reason
    payload = json.dumps(
        {
            "version": PAGE_OBSERVATION_RECEIPT_VERSION,
            "page": material,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest(), ""


def verification_evaluation_receipt_binding_integrity(
    plan: dict[str, Any],
    current_pages: list[dict[str, Any]],
    rule_evaluations: list[dict[str, Any]],
    current_contract: dict[str, Any],
    *,
    previous_scan_id: str,
    scan_origin: str,
) -> dict[str, Any]:
    """Bind each predicate evaluation to the exact page receipt it evaluated.

    Earlier Lane-E boundaries prove scan lineage, exact targeted-plan execution,
    page URL/evidence identity, and rule-evaluation identity. They still permit a
    same-plan evaluation for URL X to be paired with a different observation of
    URL X from another fetch attempt. This boundary hashes the proof-bearing page
    receipt and requires the evaluation row for that evidence key to carry the
    exact receipt version and fingerprint.

    Missing targeted pages intentionally remain missing. An evaluation for a
    missing page must not claim a page receipt; the downstream evaluator then
    keeps the existing ``required_page_not_observed`` => ``COULD_NOT_VERIFY``
    semantics. Disappearance therefore never becomes proof of a fix.
    """
    base = {
        "version": EVALUATION_RECEIPT_BINDING_VERSION,
        "valid": False,
        "reason": "evaluation_receipt_binding_not_proven",
        "plan_fingerprint": "",
        "page_receipt_identity_binding": {},
    }
    if not isinstance(current_pages, list):
        return {**base, "reason": "current_pages_not_a_list"}
    if not isinstance(rule_evaluations, list):
        return {**base, "reason": "rule_evaluations_not_a_list"}
    if any(not isinstance(item, dict) for item in current_pages):
        return {**base, "reason": "current_pages_contains_non_object"}
    if any(not isinstance(item, dict) for item in rule_evaluations):
        return {**base, "reason": "rule_evaluations_contains_non_object"}

    page_identity = verification_page_receipt_identity_binding_integrity(
        plan,
        current_pages,
        rule_evaluations,
        current_contract,
        previous_scan_id=previous_scan_id,
        scan_origin=scan_origin,
    )
    with_page_identity = {
        **base,
        "page_receipt_identity_binding": (
            page_identity if isinstance(page_identity, dict) else {}
        ),
    }
    if not isinstance(page_identity, dict) or page_identity.get("valid") is not True:
        reason = page_identity.get("reason") if isinstance(page_identity, dict) else "not_an_object"
        return {
            **with_page_identity,
            "reason": f"page_receipt_identity_binding_failed:{reason or 'not_proven'}",
        }

    plan_fingerprint = page_identity.get("plan_fingerprint")
    if not _exact_sha256(plan_fingerprint):
        return {
            **with_page_identity,
            "reason": "page_receipt_binding_plan_fingerprint_not_exact_sha256",
        }

    page_receipts: dict[str, str] = {}
    receipt_rows: list[dict[str, str]] = []
    for index, page in enumerate(current_pages):
        evidence_key = page.get("evidence_key")
        if not _exact_nonempty_string(evidence_key):
            return {
                **with_page_identity,
                "reason": f"current_page_{index}_evidence_key_must_be_exact_nonempty_string",
                "current_page_index": index,
                "plan_fingerprint": plan_fingerprint,
            }
        fingerprint, reason = page_observation_receipt_fingerprint(page)
        if reason:
            return {
                **with_page_identity,
                "reason": f"current_page_{index}_receipt_invalid:{reason}",
                "current_page_index": index,
                "plan_fingerprint": plan_fingerprint,
            }
        page_receipts[evidence_key] = fingerprint
        receipt_rows.append(
            {
                "evidence_key": evidence_key,
                "receipt_version": PAGE_OBSERVATION_RECEIPT_VERSION,
                "receipt_fingerprint": fingerprint,
            }
        )

    for index, row in enumerate(rule_evaluations):
        evidence_key = row.get("evidence_key")
        if not _exact_nonempty_string(evidence_key):
            return {
                **with_page_identity,
                "reason": f"rule_evaluation_{index}_evidence_key_must_be_exact_nonempty_string",
                "rule_evaluation_index": index,
                "plan_fingerprint": plan_fingerprint,
            }
        expected_fingerprint = page_receipts.get(evidence_key)
        claimed_version_present = _RECEIPT_VERSION_FIELD in row
        claimed_fingerprint_present = _RECEIPT_FINGERPRINT_FIELD in row

        if expected_fingerprint is None:
            if claimed_version_present or claimed_fingerprint_present:
                return {
                    **with_page_identity,
                    "reason": f"rule_evaluation_{index}_claims_missing_page_receipt",
                    "rule_evaluation_index": index,
                    "evidence_key": evidence_key,
                    "plan_fingerprint": plan_fingerprint,
                }
            continue

        claimed_version = row.get(_RECEIPT_VERSION_FIELD)
        if claimed_version != PAGE_OBSERVATION_RECEIPT_VERSION:
            return {
                **with_page_identity,
                "reason": f"rule_evaluation_{index}_{_RECEIPT_VERSION_FIELD}_mismatch",
                "rule_evaluation_index": index,
                "evidence_key": evidence_key,
                "plan_fingerprint": plan_fingerprint,
            }
        claimed_fingerprint = row.get(_RECEIPT_FINGERPRINT_FIELD)
        if not _exact_sha256(claimed_fingerprint):
            return {
                **with_page_identity,
                "reason": f"rule_evaluation_{index}_{_RECEIPT_FINGERPRINT_FIELD}_must_be_exact_sha256",
                "rule_evaluation_index": index,
                "evidence_key": evidence_key,
                "plan_fingerprint": plan_fingerprint,
            }
        if claimed_fingerprint != expected_fingerprint:
            return {
                **with_page_identity,
                "reason": f"rule_evaluation_{index}_{_RECEIPT_FINGERPRINT_FIELD}_mismatch",
                "rule_evaluation_index": index,
                "evidence_key": evidence_key,
                "expected_page_observation_receipt_fingerprint": expected_fingerprint,
                "claimed_page_observation_receipt_fingerprint": claimed_fingerprint,
                "plan_fingerprint": plan_fingerprint,
            }

    missing_required = list(page_identity.get("missing_required_evidence_keys") or [])
    return {
        **with_page_identity,
        "valid": True,
        "reason": "all_present_rule_evaluations_bound_to_exact_page_observation_receipts",
        "plan_fingerprint": plan_fingerprint,
        "checked_current_pages": len(current_pages),
        "checked_rule_evaluations": len(rule_evaluations),
        "bound_evidence_keys": [row["evidence_key"] for row in receipt_rows],
        "missing_required_evidence_keys": missing_required,
        "page_observation_receipts": receipt_rows,
    }


def _verified_fixed_denied(reason: str, binding: dict[str, Any]) -> dict[str, Any]:
    """Return the fail-closed verified-fixed transport for receipt-binding failure."""
    return {
        "version": STRICT_VERIFIED_FIXED_EVALUATION_RECEIPT_BOUND_VERSION,
        "allowed": False,
        "reason": reason,
        "repair_fingerprint": "",
        "recomputed_verification_state": COULD_NOT_VERIFY,
        "recomputed_result": {},
        "replay": {},
        "evaluation_receipt_binding": binding,
        "inner_page_receipt_identity_bound_replay_version": "",
    }


def strict_verified_fixed_transition_from_evaluation_receipt_bound_inputs(
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
    """Require exact page-receipt provenance before any verified-fixed proof."""
    binding = verification_evaluation_receipt_binding_integrity(
        plan,
        current_pages,
        rule_evaluations,
        current_contract,
        previous_scan_id=previous_scan_id,
        scan_origin=scan_origin,
    )
    if binding.get("valid") is not True:
        return _verified_fixed_denied("evaluation_receipt_binding_failed", binding)

    decision = strict_verified_fixed_transition_from_page_receipt_identity_bound_inputs(
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
            "page_receipt_identity_bound_verified_fixed_replay_returned_non_object",
            binding,
        )
    return {
        **decision,
        "version": STRICT_VERIFIED_FIXED_EVALUATION_RECEIPT_BOUND_VERSION,
        "inner_page_receipt_identity_bound_replay_version": decision.get("version", ""),
        "evaluation_receipt_binding": binding,
    }


def _regression_denied(reason: str, binding: dict[str, Any]) -> dict[str, Any]:
    """Return the fail-closed regression transport for receipt-binding failure."""
    return {
        "version": STRICT_REGRESSION_REOPEN_EVALUATION_RECEIPT_BOUND_VERSION,
        "should_reopen": False,
        "reason": reason,
        "repair_fingerprint": "",
        "reopen_scope": [],
        "recomputed_verification_state": COULD_NOT_VERIFY,
        "recomputed_result": {},
        "replay": {},
        "evaluation_receipt_binding": binding,
        "inner_page_receipt_identity_bound_replay_version": "",
    }


def strict_regression_reopen_from_evaluation_receipt_bound_inputs(
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
    """Require exact page-receipt provenance before regression reopening proof."""
    binding = verification_evaluation_receipt_binding_integrity(
        plan,
        current_pages,
        rule_evaluations,
        current_contract,
        previous_scan_id=previous_scan_id,
        scan_origin=scan_origin,
    )
    if binding.get("valid") is not True:
        return _regression_denied("evaluation_receipt_binding_failed", binding)

    decision = strict_regression_reopen_from_page_receipt_identity_bound_inputs(
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
            "page_receipt_identity_bound_regression_replay_returned_non_object",
            binding,
        )
    return {
        **decision,
        "version": STRICT_REGRESSION_REOPEN_EVALUATION_RECEIPT_BOUND_VERSION,
        "inner_page_receipt_identity_bound_replay_version": decision.get("version", ""),
        "evaluation_receipt_binding": binding,
    }
