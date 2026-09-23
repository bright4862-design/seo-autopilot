from __future__ import annotations

import hashlib
import json
from typing import Any

from .repair_identity import build_repair_identity, compare_repair_runs

SCAN_COMPARISON_VERSION = "scan_comparison_v1"
SCAN_COMPARISON_PRESENTATION_VERSION = "scan_comparison_presentation_v1"
SCAN_COMPARISON_TRANSPORT_VERSION = "scan_comparison_transport_v1"

_COMPARATOR_STATES = frozenset({"verified_fixed", "still_detected", "came_back", "could_not_verify"})
_SUMMARY_STATES = frozenset({"fixed", "still_detected", "came_back", "could_not_verify"})


def _require_scan_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    value = value.strip()
    if len(value) > 256:
        raise ValueError(f"{field} is too long")
    return value


def _nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _score(value: Any, field: str) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric or null")
    if value != value or value in {float("inf"), float("-inf")}:
        raise ValueError(f"{field} must be finite")
    return value


def _optional_finding_id(fix: dict[str, Any]) -> str:
    for key in ("fix_id", "finding_id", "id"):
        value = fix.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:512]
    return ""


def _reference_identity(fix: dict[str, Any]) -> dict[str, Any]:
    """Return persisted row identity without upgrading it to verification authority.

    V8 persistence may carry a durable repair_fingerprint even when the repair
    identity is explicitly provisional. That fingerprint is safe for exact row
    referencing and continuity evidence, but it must not be treated as sufficient
    proof for ``verified_fixed``. The canonical comparator keeps that stricter gate.
    """
    identity = build_repair_identity(fix)
    persisted = fix.get("repair_fingerprint")
    persisted_fingerprint = ""
    if persisted not in (None, ""):
        if not isinstance(persisted, str):
            raise ValueError("persisted repair_fingerprint must be a string")
        persisted_fingerprint = persisted.strip().lower()
        if len(persisted_fingerprint) != 24 or any(ch not in "0123456789abcdef" for ch in persisted_fingerprint):
            raise ValueError("persisted repair_fingerprint must be a 24-character hex fingerprint")
        if identity["stable"] and persisted_fingerprint != identity["fingerprint"]:
            raise ValueError("persisted repair_fingerprint conflicts with stable repair identity")
    reference = persisted_fingerprint or (str(identity.get("fingerprint") or "") if identity.get("stable") else "")
    return {
        "reference_fingerprint": reference,
        "reference_source": "persisted_repair_fingerprint" if persisted_fingerprint else "computed_repair_identity",
        "verification_identity_stable": bool(identity.get("stable")),
        "computed_fingerprint": str(identity.get("fingerprint") or ""),
    }


def _by_reference_fingerprint(fixes: list[dict[str, Any]], *, population: str) -> tuple[dict[str, list[dict[str, Any]]], int]:
    by_fingerprint: dict[str, list[dict[str, Any]]] = {}
    unclassified = 0
    for fix in fixes:
        if not isinstance(fix, dict):
            raise ValueError(f"{population} must contain objects")
        reference = _reference_identity(fix)
        fingerprint = reference["reference_fingerprint"]
        if not fingerprint:
            unclassified += 1
            continue
        by_fingerprint.setdefault(fingerprint, []).append(fix)
    return by_fingerprint, unclassified


def _current_repair_references(fixes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Serialize deterministic current-row reference evidence without adding authority.

    This list lets downstream integrity validation prove current population counts,
    continuity observations, and candidate fingerprints against the exact envelope
    that was produced from authenticated rows. It never classifies repair state.
    """
    references: list[dict[str, Any]] = []
    for fix in fixes:
        if not isinstance(fix, dict):
            raise ValueError("current_fixes must contain objects")
        reference = _reference_identity(fix)
        references.append(
            {
                "repair_fingerprint": reference["reference_fingerprint"],
                "repair_fingerprint_source": reference["reference_source"],
                "repair_identity_stable": reference["verification_identity_stable"],
                "finding_id": _optional_finding_id(fix),
            }
        )
    references.sort(
        key=lambda item: (
            item["repair_fingerprint"] or "~",
            item["finding_id"],
            item["repair_fingerprint_source"],
            item["repair_identity_stable"],
        )
    )
    return references


def _score_sample_context(
    *,
    previous_score: Any,
    current_score: Any,
    previous_pages_checked: Any,
    current_pages_checked: Any,
) -> dict[str, Any]:
    previous_score = _score(previous_score, "previous_score")
    current_score = _score(current_score, "current_score")
    previous_pages_checked = _nonnegative_int(previous_pages_checked, "previous_pages_checked")
    current_pages_checked = _nonnegative_int(current_pages_checked, "current_pages_checked")
    sample_size_changed = previous_pages_checked != current_pages_checked
    score_delta = None
    if previous_score is not None and current_score is not None:
        score_delta = current_score - previous_score
    return {
        "previous_score": previous_score,
        "current_score": current_score,
        "score_delta": score_delta,
        "previous_pages_checked": previous_pages_checked,
        "current_pages_checked": current_pages_checked,
        "sample_size_changed": sample_size_changed,
        # V1 deliberately never promotes a score delta into a directional claim.
        # Equal page counts do not prove the same page population was assessed.
        "score_direction_claim_allowed": False,
        "score_context_state": (
            "sample_size_changed_do_not_infer_direction"
            if sample_size_changed
            else "score_delta_descriptive_only"
        ),
    }


def build_scan_comparison_v1(
    *,
    previous_scan_id: str,
    current_scan_id: str,
    current_previous_scan_id: str,
    previous_fixes: list[dict[str, Any]],
    current_fixes: list[dict[str, Any]],
    current_pages: list[dict[str, Any]],
    previous_score: int | float | None,
    current_score: int | float | None,
    previous_pages_checked: int,
    current_pages_checked: int,
    current_contract: dict[str, Any] | None = None,
    previous_scan_origin: str = "",
    current_scan_origin: str = "",
) -> dict[str, Any]:
    """Build a deterministic cross-scan comparison using the canonical repair comparator.

    This helper does not decide whether a repair is fixed independently. Every
    historical repair delegates that decision to ``compare_repair_runs``. New
    current repairs are identified only as current reference fingerprints that
    were absent from the immediately previous reference population, and remain
    explicitly candidate-only unless the canonical comparator proves came-back.
    """
    previous_scan_id = _require_scan_id(previous_scan_id, "previous_scan_id")
    current_scan_id = _require_scan_id(current_scan_id, "current_scan_id")
    current_previous_scan_id = _require_scan_id(current_previous_scan_id, "current_previous_scan_id")
    if current_scan_id == previous_scan_id:
        raise ValueError("current_scan_id must differ from previous_scan_id")
    if current_previous_scan_id != previous_scan_id:
        raise ValueError("current scan lineage does not point to the supplied previous scan")
    if not isinstance(previous_fixes, list) or not isinstance(current_fixes, list) or not isinstance(current_pages, list):
        raise ValueError("repair and page populations must be lists")
    if current_contract is not None and not isinstance(current_contract, dict):
        raise ValueError("current_contract must be an object or null")

    previous_by_fingerprint, previous_unclassified = _by_reference_fingerprint(previous_fixes, population="previous_fixes")
    current_by_fingerprint, current_unclassified = _by_reference_fingerprint(current_fixes, population="current_fixes")
    current_repair_references = _current_repair_references(current_fixes)
    previous_fingerprints = set(previous_by_fingerprint)

    repair_comparisons: list[dict[str, Any]] = []
    for previous_fix in previous_fixes:
        reference = _reference_identity(previous_fix)
        comparison = compare_repair_runs(
            previous_fix,
            current_fixes,
            current_pages,
            current_contract=current_contract,
            previous_scan_origin=previous_scan_origin,
            scan_origin=current_scan_origin,
        )
        state = comparison.get("state")
        if state not in _COMPARATOR_STATES:
            state = "could_not_verify"
            reason = "Canonical repair comparator returned an unsupported state."
        else:
            reason = str(comparison.get("reason") or "")
        summary_state = "fixed" if state == "verified_fixed" else state
        current_matches = current_by_fingerprint.get(reference["reference_fingerprint"], []) if reference["reference_fingerprint"] else []
        current_matches = sorted(current_matches, key=_optional_finding_id)
        record = {
            "repair_fingerprint": reference["reference_fingerprint"],
            "repair_fingerprint_source": reference["reference_source"],
            "repair_identity_stable": reference["verification_identity_stable"],
            "same_reference_fingerprint_observed": bool(current_matches),
            "previous_finding_id": _optional_finding_id(previous_fix),
            "current_finding_id": _optional_finding_id(current_matches[0]) if current_matches else "",
            "state": state,
            "summary_state": summary_state,
            "reason": reason,
            "verification_version": str(comparison.get("version") or ""),
            "comparison_contract_state": str(comparison.get("comparison_contract_state") or ""),
            "previous_affected_pages": int(comparison.get("previous_affected_pages") or 0),
            "rechecked_pages": int(comparison.get("rechecked_pages") or 0),
            "eligible_rechecked_pages": int(comparison.get("eligible_rechecked_pages") or 0),
        }
        repair_comparisons.append(record)

    repair_comparisons.sort(
        key=lambda item: (
            item["repair_fingerprint"] or "~",
            item["previous_finding_id"],
            item["summary_state"],
        )
    )

    counts = {
        "fixed": 0,
        "still_detected": 0,
        "came_back": 0,
        "could_not_verify": 0,
    }
    for record in repair_comparisons:
        counts[record["summary_state"]] += 1

    # A fingerprint absent from the immediately previous repair population is
    # not enough evidence to distinguish a genuinely new defect from one that
    # existed in an older scan and returned. Keep that bucket deliberately
    # conservative unless the canonical comparator has explicit came-back proof.
    new_or_came_back_fingerprints = sorted(set(current_by_fingerprint) - previous_fingerprints)
    counts["new_or_came_back"] = len(new_or_came_back_fingerprints) + counts["came_back"]

    context = _score_sample_context(
        previous_score=previous_score,
        current_score=current_score,
        previous_pages_checked=previous_pages_checked,
        current_pages_checked=current_pages_checked,
    )

    return {
        "version": SCAN_COMPARISON_VERSION,
        "previous_scan_id": previous_scan_id,
        "current_scan_id": current_scan_id,
        "current_previous_scan_id": current_previous_scan_id,
        "repair_comparisons": repair_comparisons,
        "current_repair_references": current_repair_references,
        "new_or_came_back_repair_fingerprints": new_or_came_back_fingerprints,
        "new_or_came_back_candidate_only": True,
        "summary": {
            **counts,
            "previous_repairs_total": len(previous_fixes),
            "current_repairs_total": len(current_repair_references),
            "previous_repairs_without_reference_fingerprint": previous_unclassified,
            "current_repairs_without_reference_fingerprint": sum(
                1 for reference in current_repair_references if not reference["repair_fingerprint"]
            ),
            "previous_repairs_with_stable_verification_identity": sum(
                1 for fix in previous_fixes if _reference_identity(fix)["verification_identity_stable"]
            ),
            "current_repairs_with_stable_verification_identity": sum(
                1 for reference in current_repair_references if reference["repair_identity_stable"]
            ),
        },
        "score_sample_context": context,
        "comparison_engine": "repair_identity.compare_repair_runs",
        "creates_customer_fixes": False,
        "recomputes_score": False,
        "mutates_historical_rows": False,
    }


def build_customer_scan_comparison_presentation(comparison: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(comparison, dict) or comparison.get("version") != SCAN_COMPARISON_VERSION:
        raise ValueError("unsupported scan comparison contract")
    context = comparison.get("score_sample_context")
    summary = comparison.get("summary")
    if not isinstance(context, dict) or not isinstance(summary, dict):
        raise ValueError("scan comparison is missing summary context")

    previous_score = context.get("previous_score")
    current_score = context.get("current_score")
    previous_pages = context.get("previous_pages_checked")
    current_pages = context.get("current_pages_checked")
    sample_changed = context.get("sample_size_changed") is True

    score_line = "Health score comparison is unavailable."
    if previous_score is not None and current_score is not None:
        score_line = f"Health score changed from {previous_score:g} to {current_score:g}."

    sample_line = f"The assessed sample was {previous_pages} pages before and {current_pages} pages now."
    if sample_changed:
        caution = (
            "Because the assessed sample size changed, the score difference alone does not prove "
            "the site improved or regressed. Repair-level states below use comparable repair evidence."
        )
    else:
        caution = (
            "The score difference is descriptive only; equal page counts do not prove the exact same "
            "page population was assessed. Repair-level states below use comparable repair evidence."
        )

    return {
        "version": SCAN_COMPARISON_PRESENTATION_VERSION,
        "previous_scan_id": comparison["previous_scan_id"],
        "current_scan_id": comparison["current_scan_id"],
        "headline": "What changed since the previous scan",
        "score_line": score_line,
        "sample_line": sample_line,
        "score_caution": caution,
        "counts": {
            "fixed": int(summary.get("fixed") or 0),
            "still_detected": int(summary.get("still_detected") or 0),
            "new_or_came_back": int(summary.get("new_or_came_back") or 0),
            "came_back": int(summary.get("came_back") or 0),
            "could_not_verify": int(summary.get("could_not_verify") or 0),
        },
        "new_or_came_back_label": "New or returned candidate",
        "new_or_came_back_is_verified_claim": False,
        "score_direction_claim_allowed": False,
        "overall_improvement_or_regression_claim": None,
    }


def _authority_receipt(receipt: Any, expected_scan_id: str, field: str) -> dict[str, str]:
    if not isinstance(receipt, dict):
        raise ValueError(f"{field} must be an authority verification receipt")
    if receipt.get("state") != "verified":
        raise ValueError(f"{field} must be verified before comparison transport")
    scan_id = _require_scan_id(receipt.get("scan_id"), f"{field}.scan_id")
    if scan_id != expected_scan_id:
        raise ValueError(f"{field} scan_id does not match comparison")
    seal_version = receipt.get("authority_seal_version")
    fingerprint = receipt.get("authority_proof_fingerprint")
    if not isinstance(seal_version, str) or not seal_version.strip():
        raise ValueError(f"{field} is missing authority_seal_version")
    if not isinstance(fingerprint, str):
        raise ValueError(f"{field} is missing authority_proof_fingerprint")
    fingerprint = fingerprint.strip().lower()
    if len(fingerprint) != 64 or any(ch not in "0123456789abcdef" for ch in fingerprint):
        raise ValueError(f"{field} has invalid authority_proof_fingerprint")
    return {
        "scan_id": scan_id,
        "state": "verified",
        "authority_seal_version": seal_version.strip(),
        "authority_proof_fingerprint": fingerprint,
    }


def build_scan_comparison_transport_v1(
    comparison: dict[str, Any],
    *,
    previous_authority_receipt: dict[str, Any],
    current_authority_receipt: dict[str, Any],
) -> dict[str, Any]:
    """Bind a comparison to upstream V8 authority-verification receipts.

    This function never verifies or creates an authority seal. The serialized V8
    reader/integrator must produce the receipts after its existing authority
    verification succeeds. Missing, non-verified, or cross-scan receipts fail
    closed here.
    """
    if not isinstance(comparison, dict) or comparison.get("version") != SCAN_COMPARISON_VERSION:
        raise ValueError("unsupported scan comparison contract")
    previous_scan_id = _require_scan_id(comparison.get("previous_scan_id"), "previous_scan_id")
    current_scan_id = _require_scan_id(comparison.get("current_scan_id"), "current_scan_id")
    previous_receipt = _authority_receipt(previous_authority_receipt, previous_scan_id, "previous_authority_receipt")
    current_receipt = _authority_receipt(current_authority_receipt, current_scan_id, "current_authority_receipt")

    comparison_fingerprint = hashlib.sha256(
        json.dumps(comparison, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    ).hexdigest()
    return {
        "version": SCAN_COMPARISON_TRANSPORT_VERSION,
        "comparison_version": SCAN_COMPARISON_VERSION,
        "comparison_fingerprint": comparison_fingerprint,
        "previous_scan_id": previous_scan_id,
        "current_scan_id": current_scan_id,
        "previous_authority_receipt": previous_receipt,
        "current_authority_receipt": current_receipt,
        "requires_serialized_v8_integrator": True,
        "customer_projection_authorized": False,
        "authority_created_or_modified": False,
    }
