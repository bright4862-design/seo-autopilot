"""Production cutover wrapper for the calibrated FixList repair contract.

The crawler and normal Python review remain unchanged. This module runs only in
the durable worker after review has completed. It builds a separate canonical
repair snapshot from the finished review and publishes it only when the existing
complete-or-fail validator accepts every row and the full canonical order.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .repair_persistence_shadow import (
    REPAIR_CONTRACT_VERSION,
    REPAIR_PRIORITY_MODEL_VERSION,
    validate_v2_persistence_candidate,
)
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
        identity = raw_fix.get("repair_identity") if isinstance(raw_fix.get("repair_identity"), dict) else {}
        item = {
            **deepcopy(raw_fix),
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
