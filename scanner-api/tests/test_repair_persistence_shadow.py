from copy import deepcopy

from app.repair_persistence_shadow import (
    REPAIR_CONTRACT_VERSION,
    REPAIR_PRIORITY_MODEL_VERSION,
    validate_v2_persistence_candidate,
)


def _item(fix_id: str, rank: int, priority: str = "important"):
    return {
        "fix_id": fix_id,
        "repair_contract_version": REPAIR_CONTRACT_VERSION,
        "repair_priority_model_version": REPAIR_PRIORITY_MODEL_VERSION,
        "base_severity": "medium",
        "evidence_class": "confirmed_problem",
        "action_priority": priority,
        "canonical_action_rank": rank,
        "priority_reason": "Important searchable page is affected",
        "repair_identity_version": "repair_identity_v1_conservative",
        "repair_fingerprint": f"fp_{fix_id}",
    }


def _parent(ids):
    return {
        "repair_contract_version": REPAIR_CONTRACT_VERSION,
        "repair_snapshot_contract_version": REPAIR_CONTRACT_VERSION,
        "repair_snapshot_contract_complete": True,
        "repair_priority_model_version": REPAIR_PRIORITY_MODEL_VERSION,
        "total_fixes": len(ids),
        "canonical_action_fix_ids": list(ids),
    }


def test_complete_v2_candidate_is_eligible():
    items = [_item("f1", 1, "fix_first"), _item("f2", 2, "important")]
    result = validate_v2_persistence_candidate(_parent(["f1", "f2"]), items)

    assert result["eligible"] is True
    assert result["failures"] == []
    assert result["canonical_order"] == ["f1", "f2"]


def test_partial_or_mixed_snapshot_fails_closed():
    parent = _parent(["f1", "f2"])
    items = [_item("f1", 1), _item("f2", 2)]
    items[1]["repair_contract_version"] = "repair_contract_v1_shadow"

    result = validate_v2_persistence_candidate(parent, items)

    assert result["eligible"] is False
    assert "item_2:contract_version" in result["failures"]


def test_parent_order_must_match_item_ranks_exactly():
    parent = _parent(["f2", "f1"])
    items = [_item("f1", 1), _item("f2", 2)]

    result = validate_v2_persistence_candidate(parent, items)

    assert result["eligible"] is False
    assert "canonical_order_rank_mismatch" in result["failures"]


def test_missing_or_duplicate_order_identity_fails_closed():
    parent = _parent(["f1", "f1"])
    items = [_item("f1", 1), _item("f2", 1)]

    result = validate_v2_persistence_candidate(parent, items)

    assert result["eligible"] is False
    assert "canonical_order_duplicate_id" in result["failures"]
    assert "canonical_order_id_set_mismatch" in result["failures"]
    assert "item_2:duplicate_canonical_action_rank" in result["failures"]


def test_missing_stable_identity_or_customer_reason_fails_closed():
    parent = _parent(["f1"])
    item = _item("f1", 1)
    item["repair_fingerprint"] = ""
    item["priority_reason"] = ""

    result = validate_v2_persistence_candidate(parent, [item])

    assert result["eligible"] is False
    assert "item_1:repair_fingerprint" in result["failures"]
    assert "item_1:priority_reason" in result["failures"]


def test_legacy_parent_is_not_silently_promoted_to_v2():
    result = validate_v2_persistence_candidate(
        {"total_fixes": 1, "top_action_fix_ids": ["f1"]},
        [{"fix_id": "f1", "priority": "high"}],
    )

    assert result["eligible"] is False
    assert "parent_contract_version" in result["failures"]
    assert "snapshot_contract_version" in result["failures"]
    assert "snapshot_not_complete" in result["failures"]
    assert "canonical_order_missing" in result["failures"]


def test_validation_is_non_mutating():
    parent = _parent(["f1"])
    items = [_item("f1", 1)]
    before_parent = deepcopy(parent)
    before_items = deepcopy(items)

    validate_v2_persistence_candidate(parent, items)

    assert parent == before_parent
    assert items == before_items
