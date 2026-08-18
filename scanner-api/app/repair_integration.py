from __future__ import annotations

from typing import Any

from .repair_identity import annotate_repair_identity
from .repair_priority import ACTION_RANK, SEVERITY_RANK, annotate_repair_priority

REPAIR_CONTRACT_VERSION = "repair_contract_v1_shadow"


def annotate_repair_contract(
    fixes: list[dict[str, Any]],
    pages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Add the repair-priority/identity contract without changing list order.

    This is intentionally safe for shadow-mode integration. It is additive and
    must not mutate crawl evidence, technical severity, authority, persistence,
    or the existing recommendation order until the migration gate is approved.
    """
    annotated: list[dict[str, Any]] = []
    for fix in fixes or []:
        if not isinstance(fix, dict):
            continue
        with_priority = annotate_repair_priority(dict(fix), pages or [])
        with_identity = annotate_repair_identity(with_priority)
        annotated.append({
            **with_identity,
            "repair_contract_version": REPAIR_CONTRACT_VERSION,
        })
    return annotated


def canonical_repair_sort_key(fix: dict[str, Any], original_index: int = 0) -> tuple[int, int, int, int]:
    """Proposed customer-order key; not used by live review while in shadow mode."""
    action = str(fix.get("action_priority") or "").strip().lower()
    severity = str(fix.get("base_severity") or fix.get("priority") or "").strip().lower()
    try:
        contextual_score = int(fix.get("action_priority_score") or 0)
    except (TypeError, ValueError):
        contextual_score = 0
    return (
        ACTION_RANK.get(action, 0),
        contextual_score,
        SEVERITY_RANK.get(severity, 0),
        -int(original_index),
    )


def proposed_customer_order(fixes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    indexed = [(index, fix) for index, fix in enumerate(fixes or []) if isinstance(fix, dict)]
    indexed.sort(
        key=lambda pair: canonical_repair_sort_key(pair[1], pair[0]),
        reverse=True,
    )
    return [fix for _, fix in indexed]


def _repair_key(fix: dict[str, Any], index: int) -> str:
    return str(
        fix.get("repair_fingerprint")
        or fix.get("fix_id")
        or fix.get("id")
        or f"index:{index}"
    )


def build_priority_divergence_report(
    current_order: list[dict[str, Any]],
    proposed_order: list[dict[str, Any]],
) -> dict[str, Any]:
    """Explain shadow ordering differences without changing customer output."""
    current_keys = [_repair_key(fix, index) for index, fix in enumerate(current_order or [])]
    proposed_keys = [_repair_key(fix, index) for index, fix in enumerate(proposed_order or [])]
    current_position = {key: index for index, key in enumerate(current_keys)}
    proposed_position = {key: index for index, key in enumerate(proposed_keys)}

    movements = []
    for key in current_keys:
        if key not in proposed_position:
            continue
        before = current_position[key]
        after = proposed_position[key]
        if before == after:
            continue
        movements.append({
            "repair_key": key,
            "from_position": before + 1,
            "to_position": after + 1,
            "delta": before - after,
        })

    return {
        "version": REPAIR_CONTRACT_VERSION,
        "order_changed": current_keys != proposed_keys,
        "current_order": current_keys,
        "proposed_order": proposed_keys,
        "movement_count": len(movements),
        "movements": movements,
    }


def build_shadow_repair_contract(
    fixes: list[dict[str, Any]],
    pages: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return additive repair annotations plus a proposed order for evaluation.

    The `fixes` member preserves the exact incoming order. `proposed_fixes` exists
    only for tests/analysis until the canonical-priority migration is approved.
    """
    annotated = annotate_repair_contract(fixes, pages)
    proposed = proposed_customer_order(annotated)
    return {
        "version": REPAIR_CONTRACT_VERSION,
        "fixes": annotated,
        "proposed_fixes": proposed,
        "priority_divergence": build_priority_divergence_report(annotated, proposed),
    }
