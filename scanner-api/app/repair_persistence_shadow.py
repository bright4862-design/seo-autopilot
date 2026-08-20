"""Complete-or-fail validation for the calibrated FixList repair contract.

This module never mutates scans, persists entities, or signs authority. It was
originally exercised only in shadow analysis and is now consumed exclusively by
`repair_contract_v2`, the post-review durable-worker cutover boundary.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


REPAIR_CONTRACT_VERSION = "repair_contract_v2_shadow_calibrated"
REPAIR_PRIORITY_MODEL_VERSION = "repair_priority_v2_technical_severity"

VALID_BASE_SEVERITIES = frozenset({"critical", "high", "medium", "low"})
VALID_EVIDENCE_CLASSES = frozenset({"confirmed_problem", "improvement", "opportunity"})
VALID_ACTION_PRIORITIES = frozenset({"fix_first", "important", "improve", "review"})


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _integer_rank(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    try:
        if float(value) != float(parsed):
            return None
    except (TypeError, ValueError):
        return None
    return parsed


def validate_v2_persistence_candidate(
    fix_list: dict[str, Any] | None,
    fix_items: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Validate complete-or-fail v2 snapshot invariants without mutating input.

    The caller supplies the proposed parent FixList projection and all proposed
    FixItems for one exact durable snapshot. This helper intentionally does not
    infer missing values or repair partial state.
    """

    parent = deepcopy(fix_list or {})
    items = deepcopy(fix_items or [])
    failures: list[str] = []

    parent_contract = _clean(parent.get("repair_contract_version"))
    snapshot_contract = _clean(parent.get("repair_snapshot_contract_version"))
    priority_model = _clean(parent.get("repair_priority_model_version"))

    if parent_contract != REPAIR_CONTRACT_VERSION:
        failures.append("parent_contract_version")
    if snapshot_contract != REPAIR_CONTRACT_VERSION:
        failures.append("snapshot_contract_version")
    if parent.get("repair_snapshot_contract_complete") is not True:
        failures.append("snapshot_not_complete")
    if priority_model != REPAIR_PRIORITY_MODEL_VERSION:
        failures.append("priority_model_version")

    total_fixes = parent.get("total_fixes")
    if isinstance(total_fixes, bool) or not isinstance(total_fixes, int) or total_fixes < 0:
        failures.append("invalid_total_fixes")
        total_fixes = len(items)
    if total_fixes != len(items):
        failures.append("item_count_mismatch")

    canonical_ids = parent.get("canonical_action_fix_ids")
    if not isinstance(canonical_ids, list):
        failures.append("canonical_order_missing")
        canonical_ids = []
    canonical_ids = [_clean(value) for value in canonical_ids]
    if any(not value for value in canonical_ids):
        failures.append("canonical_order_blank_id")
    if len(canonical_ids) != len(set(canonical_ids)):
        failures.append("canonical_order_duplicate_id")
    if len(canonical_ids) != len(items):
        failures.append("canonical_order_count_mismatch")

    item_ids: list[str] = []
    ranks: dict[int, str] = {}

    for index, item in enumerate(items):
        prefix = f"item_{index + 1}"
        fix_id = _clean(item.get("fix_id"))
        if not fix_id:
            failures.append(f"{prefix}:missing_fix_id")
        item_ids.append(fix_id)

        if _clean(item.get("repair_contract_version")) != REPAIR_CONTRACT_VERSION:
            failures.append(f"{prefix}:contract_version")
        if _clean(item.get("repair_priority_model_version") or priority_model) != REPAIR_PRIORITY_MODEL_VERSION:
            failures.append(f"{prefix}:priority_model_version")
        if _clean(item.get("base_severity")) not in VALID_BASE_SEVERITIES:
            failures.append(f"{prefix}:base_severity")
        if _clean(item.get("evidence_class")) not in VALID_EVIDENCE_CLASSES:
            failures.append(f"{prefix}:evidence_class")
        if _clean(item.get("action_priority")) not in VALID_ACTION_PRIORITIES:
            failures.append(f"{prefix}:action_priority")
        if not _clean(item.get("priority_reason")):
            failures.append(f"{prefix}:priority_reason")
        if not _clean(item.get("repair_identity_version")):
            failures.append(f"{prefix}:repair_identity_version")
        if not _clean(item.get("repair_fingerprint")):
            failures.append(f"{prefix}:repair_fingerprint")

        rank = _integer_rank(item.get("canonical_action_rank"))
        if rank is None or rank < 1 or rank > max(1, len(items)):
            failures.append(f"{prefix}:canonical_action_rank")
        elif rank in ranks:
            failures.append(f"{prefix}:duplicate_canonical_action_rank")
        else:
            ranks[rank] = fix_id

    nonblank_item_ids = [value for value in item_ids if value]
    if len(nonblank_item_ids) != len(set(nonblank_item_ids)):
        failures.append("duplicate_fix_id")
    if set(canonical_ids) != set(nonblank_item_ids):
        failures.append("canonical_order_id_set_mismatch")

    if len(ranks) == len(items):
        ranked_ids = [ranks[position] for position in range(1, len(items) + 1)]
        if ranked_ids != canonical_ids:
            failures.append("canonical_order_rank_mismatch")

    # Keep the public result deterministic and easy to assert in migration CI.
    unique_failures = list(dict.fromkeys(failures))
    return {
        "version": "repair_persistence_shadow_v1_complete_or_fail",
        "eligible": not unique_failures,
        "failures": unique_failures,
        "expected_item_count": len(items),
        "canonical_order": canonical_ids,
    }
