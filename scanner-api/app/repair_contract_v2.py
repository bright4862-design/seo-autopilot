"""Production cutover wrapper for the calibrated FixList repair contract.

The crawler and normal Python review remain unchanged. This module runs only in
the durable worker after review has completed. It builds a separate canonical
repair snapshot from the finished review and publishes it only when the existing
complete-or-fail validator accepts every row and the full canonical order.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .repair_identity import annotate_repair_identity
from .repair_persistence_shadow import (
    REPAIR_CONTRACT_VERSION,
    REPAIR_PRIORITY_MODEL_VERSION,
    validate_v2_persistence_candidate,
)
from .repair_coverage import first_failed_repair_invariant, normalize_repair_scope
from .repair_shadow_calibration import build_calibrated_shadow_review_analysis


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
        return review_result

    canonical_items: list[dict[str, Any]] = []
    for rank, raw_fix in enumerate(proposed, start=1):
        if not isinstance(raw_fix, dict):
            return review_result
        canonical_fix = _normalize_canonical_repair_evidence(raw_fix, pages)
        if first_failed_repair_invariant(canonical_fix):
            return review_result
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
        return review_result

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
