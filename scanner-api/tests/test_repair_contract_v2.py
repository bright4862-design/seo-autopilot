import pytest

from app.repair_contract_v2 import CanonicalRepairContractError, apply_canonical_repair_contract
from app.repair_persistence_shadow import REPAIR_CONTRACT_VERSION, REPAIR_PRIORITY_MODEL_VERSION


def _page(url: str) -> dict:
    return {
        "url": url,
        "final_url": url,
        "status_code": 200,
        "content_type": "text/html",
        "page_evidence_class": "usable_html",
        "indexable": True,
        "page_template_family": "collection_page",
    }


def _fix(fix_id: str, rule: str, priority: str, pages: list[str]) -> dict:
    return {
        "fix_id": fix_id,
        "rule": rule,
        "category": "meta_description" if "meta" in rule else "internal_link",
        "priority": priority,
        "page_scope": "family" if len(pages) > 1 else "page",
        "page_template_family": "collection_page",
        "affected_pages": pages,
        "confidence_score": 95,
        "repair_surface": "cms_field" if "meta" in rule else "shared_navigation",
        "remediation_family": "update_meta_description" if "meta" in rule else "replace_redirecting_internal_link",
        "issue_title": fix_id,
    }


def test_complete_contract_is_attached_without_reordering_legacy_recommendations():
    legacy = [
        _fix("low-first-in-legacy", "missing_meta_description", "low", ["https://example.com/a"]),
        _fix("high-second-in-legacy", "internal_link_redirect", "high", ["https://example.com/a", "https://example.com/b"]),
    ]
    review = {"recommendations": legacy, "cleaned_fixes": legacy}
    scan = {"crawled_pages": [_page("https://example.com/a"), _page("https://example.com/b")]}

    result = apply_canonical_repair_contract(review, scan)

    assert result["recommendations"] == legacy
    assert result["repair_contract_version"] == REPAIR_CONTRACT_VERSION
    assert result["repair_snapshot_contract_version"] == REPAIR_CONTRACT_VERSION
    assert result["repair_snapshot_contract_complete"] is True
    assert result["repair_priority_model_version"] == REPAIR_PRIORITY_MODEL_VERSION
    assert len(result["canonical_repairs"]) == 2
    assert [item["canonical_action_rank"] for item in result["canonical_repairs"]] == [1, 2]
    assert result["canonical_action_fix_ids"] == [item["fix_id"] for item in result["canonical_repairs"]]
    assert all(item["priority_reason"] for item in result["canonical_repairs"])
    assert all(item["evidence_class"] in {"confirmed_problem", "improvement", "opportunity"} for item in result["canonical_repairs"])


def test_invalid_duplicate_fix_ids_fail_closed_instead_of_publishing_legacy():
    duplicate = _fix("same-id", "internal_link_redirect", "high", ["https://example.com/a"])
    review = {"recommendations": [duplicate, {**duplicate}], "cleaned_fixes": [duplicate, {**duplicate}]}
    scan = {"crawled_pages": [_page("https://example.com/a")]}

    with pytest.raises(CanonicalRepairContractError):
        apply_canonical_repair_contract(review, scan)
