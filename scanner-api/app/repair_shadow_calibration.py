from __future__ import annotations

from copy import deepcopy
from typing import Any

from .repair_identity import annotate_repair_identity
from .repair_priority import ACTION_RANK, SEVERITY_RANK
from .repair_priority_calibration import (
    REPAIR_PRIORITY_CALIBRATION_VERSION,
    annotate_calibrated_repair_priority,
)

REPAIR_SHADOW_CALIBRATION_VERSION = "repair_contract_v2_shadow_calibrated"

_FIX_KEYS = ("cleaned_fixes", "recommendations", "fixes", "findings", "recommended_actions")
_PAGE_KEYS = ("crawled_pages", "pages", "scanned_pages")


def _first_dict_list(source: dict[str, Any], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    for key in keys:
        value = source.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _repair_key(fix: dict[str, Any], index: int) -> str:
    return str(fix.get("repair_fingerprint") or fix.get("fix_id") or fix.get("id") or f"index:{index}")


def _sort_key(fix: dict[str, Any], original_index: int) -> tuple[int, int, int, int]:
    action = str(fix.get("action_priority") or "").strip().lower()
    severity = str(fix.get("base_severity") or "").strip().lower()
    try:
        contextual = int(fix.get("action_priority_score") or 0)
    except (TypeError, ValueError):
        contextual = 0
    return (
        ACTION_RANK.get(action, 0),
        contextual,
        SEVERITY_RANK.get(severity, 0),
        -original_index,
    )


def build_calibrated_shadow_review_analysis(
    review_result: dict[str, Any],
    pages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the calibrated v2 ordering over an already-finished review.

    This function never changes crawler or review output. The durable worker may
    consume the returned proposal only through `repair_contract_v2`, where the
    complete-or-fail persistence validator decides whether a canonical snapshot
    is eligible.
    """
    source = review_result if isinstance(review_result, dict) else {}
    live_fixes = _first_dict_list(source, _FIX_KEYS)
    evidence_pages = (
        [item for item in pages if isinstance(item, dict)]
        if isinstance(pages, list)
        else _first_dict_list(source, _PAGE_KEYS)
    )

    fixes_snapshot = deepcopy(live_fixes)
    pages_snapshot = deepcopy(evidence_pages)
    annotated = []
    for fix in fixes_snapshot:
        calibrated = annotate_calibrated_repair_priority(fix, pages_snapshot)
        with_identity = annotate_repair_identity(calibrated)
        annotated.append({
            **with_identity,
            "repair_contract_version": REPAIR_SHADOW_CALIBRATION_VERSION,
        })

    indexed = list(enumerate(annotated))
    indexed.sort(key=lambda pair: _sort_key(pair[1], pair[0]), reverse=True)
    proposed = [fix for _, fix in indexed]

    current_keys = [_repair_key(fix, index) for index, fix in enumerate(annotated)]
    proposed_keys = [_repair_key(fix, index) for index, fix in enumerate(proposed)]
    proposed_position = {key: index for index, key in enumerate(proposed_keys)}
    movements = []
    for index, key in enumerate(current_keys):
        after = proposed_position.get(key)
        if after is None or after == index:
            continue
        movements.append({
            "repair_key": key,
            "from_position": index + 1,
            "to_position": after + 1,
            "delta": index - after,
        })

    return {
        "version": REPAIR_SHADOW_CALIBRATION_VERSION,
        "priority_version": REPAIR_PRIORITY_CALIBRATION_VERSION,
        "source_fix_count": len(live_fixes),
        "source_page_count": len(evidence_pages),
        "current_order_preserved": [
            str(item.get("fix_id") or item.get("id") or "") for item in live_fixes
        ] == [
            str(item.get("fix_id") or item.get("id") or "") for item in annotated
        ],
        "fixes": annotated,
        "proposed_fixes": proposed,
        "priority_divergence": {
            "version": REPAIR_SHADOW_CALIBRATION_VERSION,
            "order_changed": current_keys != proposed_keys,
            "current_order": current_keys,
            "proposed_order": proposed_keys,
            "movement_count": len(movements),
            "movements": movements,
        },
    }
