"""Production cutover wrapper for the calibrated FixList repair contract.

The crawler and normal Python review remain unchanged. This module runs only in
the durable worker after review has completed. It builds a separate canonical
repair snapshot from the finished review and publishes it only when the existing
complete-or-fail validator accepts every row and the full canonical order.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .observability import emit
from .repair_identity import annotate_repair_identity
from .repair_persistence_shadow import (
    REPAIR_CONTRACT_VERSION,
    REPAIR_PRIORITY_MODEL_VERSION,
    validate_v2_persistence_candidate,
)
from .repair_coverage import evidence_url_key, first_failed_repair_invariant, normalize_repair_scope
from .repair_shadow_calibration import build_calibrated_shadow_review_analysis


class CanonicalRepairContractError(RuntimeError):
    """Canonical-v2 synthesis was attempted but could not produce one complete snapshot."""


def _diagnostic_count(value: Any, fallback: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
        return fallback


def _safe_repair_diagnostic(fix: dict[str, Any], invariant: str, *, rank: int) -> dict[str, Any]:
    """Return bounded, non-secret fields sufficient to diagnose invariant drift.

    Never emit raw headers, authority material, tokens, or URL query strings.
    The diagnostic intentionally reports cardinalities and family names rather
    than representative URLs.
    """
    affected_pages = fix.get("affected_pages") if isinstance(fix.get("affected_pages"), list) else []
    affected_keys = {key for value in affected_pages if (key := evidence_url_key(value))}
    breakdown = fix.get("family_breakdown") if isinstance(fix.get("family_breakdown"), dict) else {}
    representatives = (
        fix.get("representative_pages_by_family")
        if isinstance(fix.get("representative_pages_by_family"), dict)
        else {}
    )
    page_count = _diagnostic_count(fix.get("page_count"))
    reported = _diagnostic_count(fix.get("affected_reported"), page_count)
    observed = _diagnostic_count(fix.get("affected_observed"), reported)
    eligible = _diagnostic_count(fix.get("affected_eligible"), observed)
    return {
        "invariant": str(invariant or "unknown")[:160],
        "fix_id": str(fix.get("fix_id") or "")[:160],
        "canonical_action_rank": rank,
        "page_scope": str(fix.get("page_scope") or "")[:80],
        "page_count": page_count,
        "affected_page_cardinality": len(affected_keys),
        "affected_pages_complete": fix.get("affected_pages_complete") is not False,
        "family_breakdown": {
            str(key)[:120]: _diagnostic_count(value)
            for key, value in list(breakdown.items())[:20]
        },
        "representative_families": [str(key)[:120] for key in list(representatives.keys())[:20]],
        "affected_reported": reported,
        "affected_observed": observed,
        "affected_eligible": eligible,
        "checked_eligible": fix.get("checked_eligible"),
        "indexable_affected": _diagnostic_count(fix.get("indexable_affected")),
        "indexable_checked_eligible": fix.get("indexable_checked_eligible"),
    }


def apply_canonical_repair_contract(
    review_result: dict[str, Any],
    scan_result: dict[str, Any],
) -> dict[str, Any]:
    """Attach one complete canonical v2 snapshot or leave review untouched.

    The legacy review recommendations are never reordered or rewritten here.
    Canonical repairs are carried in a separate signed completion field and are
    consumed by Base44 persistence only when the whole snapshot validates.
    """
    if not isinstance(review_result, dict):
        return review_result

    review = deepcopy(review_result)
    pages = _first_pages(scan_result)
    analysis = build_calibrated_shadow_review_analysis(review, pages)
    proposed = analysis.get("proposed_fixes") if isinstance(analysis, dict) else None
    if not isinstance(proposed, list):
        emit("canonical_repair_contract_absent", severity="WARNING", reason="proposed_fixes_missing")
        raise CanonicalRepairContractError("canonical repair synthesis did not produce a list")

    canonical_items: list[dict[str, Any]] = []
    for rank, raw_fix in enumerate(proposed, start=1):
        if not isinstance(raw_fix, dict):
            emit("canonical_repair_contract_absent", severity="WARNING", reason="proposed_fix_not_object", canonical_action_rank=rank)
            raise CanonicalRepairContractError("canonical repair synthesis produced a non-object repair")
        canonical_fix = _normalize_canonical_repair_evidence(raw_fix, pages)
        failed_invariant = first_failed_repair_invariant(canonical_fix)
        if failed_invariant:
            emit(
                "canonical_repair_invariant_rejected",
                severity="WARNING",
                **_safe_repair_diagnostic(canonical_fix, failed_invariant, rank=rank),
            )
            raise CanonicalRepairContractError(f"canonical repair invariant rejected: {failed_invariant}")
        identity = canonical_fix.get("repair_identity") if isinstance(canonical_fix.get("repair_identity"), dict) else {}
        item = {
            **deepcopy(canonical_fix),
            "repair_contract_version": REPAIR_CONTRACT_VERSION,
            "repair_priority_model_version": REPAIR_PRIORITY_MODEL_VERSION,
            "canonical_action_rank": rank,
            "repair_identity_version": str(identity.get("version") or "").strip(),
        }
        canonical_items.append(item)

    canonical_ids = [str(item.get("fix_id") or "").strip() for item in canonical_items]
    parent = {
        "repair_contract_version": REPAIR_CONTRACT_VERSION,
        "repair_snapshot_contract_version": REPAIR_CONTRACT_VERSION,
        "repair_snapshot_contract_complete": True,
        "repair_priority_model_version": REPAIR_PRIORITY_MODEL_VERSION,
        "total_fixes": len(canonical_items),
        "canonical_action_fix_ids": canonical_ids,
    }
    validation = validate_v2_persistence_candidate(parent, canonical_items)
    if validation.get("eligible") is not True:
        emit(
            "canonical_repair_contract_absent",
            severity="WARNING",
            reason="persistence_candidate_rejected",
            validation_code=str(validation.get("code") or validation.get("reason") or "")[:160],
            canonical_fix_count=len(canonical_items),
        )
        raise CanonicalRepairContractError("canonical repair persistence candidate was rejected")

    return {
        **review,
        **parent,
        "canonical_repairs": canonical_items,
        "repair_contract_validation_version": validation.get("version") or "",
    }


def _first_pages(scan_result: dict[str, Any]) -> list[dict[str, Any]]:
    source = scan_result if isinstance(scan_result, dict) else {}
    for key in ("crawled_pages", "pages", "scanned_pages", "crawl_pages"):
        value = source.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _normalize_canonical_repair_evidence(
    fix: dict[str, Any],
    pages: list[dict[str, Any]],
) -> dict[str, Any]:
    """Re-derive one canonical repair from one shared affected-page identity.

    Normal review/scoring remains untouched. The durable cutover is the single
    place that reconciles the finished repair's affected URLs, page count, family
    partition and representatives before identity is re-annotated and the
    completion envelope is signed.

    The family resolver is imported lazily to reuse review's existing vocabulary
    without creating a second classifier or changing crawler behavior.
    """
    from .review import normalize_template_family

    snapshot = deepcopy(fix)
    if snapshot.get("affected_pages_complete") is False:
        # A truncated affected list is only a sample of a larger proven total.
        # Re-normalizing from the sample would silently shrink page_count and
        # falsely claim completeness. Base44 deliberately skips URL-cardinality
        # and representative membership checks for this shape, so preserve it
        # and only refresh repair identity.
        return annotate_repair_identity(snapshot)

    normalized = normalize_repair_scope(
        snapshot,
        pages,
        family_resolver=normalize_template_family,
    )
    return annotate_repair_identity(normalized)
