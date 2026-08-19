from __future__ import annotations

from copy import deepcopy
from typing import Any

from .repair_integration import REPAIR_CONTRACT_VERSION, build_shadow_repair_contract

_FIX_KEYS = (
    "cleaned_fixes",
    "recommendations",
    "fixes",
    "findings",
    "recommended_actions",
)
_PAGE_KEYS = (
    "crawled_pages",
    "pages",
    "scanned_pages",
)


def _first_dict_list(source: dict[str, Any], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    for key in keys:
        value = source.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def build_shadow_review_analysis(
    review_result: dict[str, Any],
    pages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Analyze a finished Python Review result without mutating live review state.

    This adapter is intentionally not wired into the production review endpoint,
    persistence, authority snapshot, worker, or scanner. It exists so integration
    tests and offline evaluation can compare the current customer order with the
    proposed repair-priority order before any runtime boundary is switched.
    """
    source = review_result if isinstance(review_result, dict) else {}
    live_fixes = _first_dict_list(source, _FIX_KEYS)
    evidence_pages = (
        [item for item in pages if isinstance(item, dict)]
        if isinstance(pages, list)
        else _first_dict_list(source, _PAGE_KEYS)
    )

    # Deep-copy the finished review payload before handing values to the shadow
    # layer so future changes inside the repair modules cannot accidentally
    # mutate the authoritative review object used by callers.
    fixes_snapshot = deepcopy(live_fixes)
    pages_snapshot = deepcopy(evidence_pages)
    shadow = build_shadow_repair_contract(fixes_snapshot, pages_snapshot)

    current_ids = [str(item.get("fix_id") or item.get("id") or "") for item in live_fixes]
    annotated_ids = [str(item.get("fix_id") or item.get("id") or "") for item in shadow["fixes"]]

    return {
        "version": REPAIR_CONTRACT_VERSION,
        "source_fix_count": len(live_fixes),
        "source_page_count": len(evidence_pages),
        "current_order_preserved": current_ids == annotated_ids,
        "current_order": current_ids,
        "fixes": shadow["fixes"],
        "proposed_fixes": shadow["proposed_fixes"],
        "priority_divergence": shadow["priority_divergence"],
    }
