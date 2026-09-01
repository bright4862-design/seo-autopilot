import pytest

from app.repair_contract_v2 import (
    CanonicalRepairContractError,
    _group_canonical_repairs,
    apply_canonical_repair_contract,
)
from app.repair_persistence_shadow import REPAIR_CONTRACT_VERSION, REPAIR_PRIORITY_MODEL_VERSION
from app.repair_identity import annotate_repair_identity, compare_repair_runs


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



def test_stable_fingerprint_rows_persist_as_one_action_with_child_evidence():
    first = annotate_repair_identity({
        **_fix("first", "missing_meta_description", "medium", ["https://example.com/fr/a"]),
        "action_priority": "improve",
        "base_severity": "medium",
        "evidence_class": "improvement",
        "page_template_family": "collection_page",
        "requires_developer": False,
        "difficulty": "easy",
    })
    second = annotate_repair_identity({
        **_fix("second", "missing_meta_description", "high", ["https://example.com/de/b"]),
        "action_priority": "important",
        "base_severity": "high",
        "evidence_class": "confirmed_problem",
        "page_template_family": "product_detail",
        "requires_developer": True,
        "who_can_do_this": "your_web_person",
        "difficulty": "hard",
    })
    assert first["repair_fingerprint"] == second["repair_fingerprint"]
    expected_fingerprint = first["repair_fingerprint"]
    pages = [
        {**_page("https://example.com/fr/a"), "page_template_family": "collection_page"},
        {**_page("https://example.com/de/b"), "page_template_family": "product_detail"},
    ]

    grouped = _group_canonical_repairs([first, second], pages)

    assert len(grouped) == 1
    action = grouped[0]
    assert action["repair_fingerprint"] == expected_fingerprint
    assert action["affected_pages"] == ["https://example.com/fr/a", "https://example.com/de/b"]
    assert action["page_count"] == 2
    assert action["action_priority"] == "important"
    assert action["priority"] == "high"
    assert action["requires_developer"] is True
    assert action["difficulty"] == "hard"
    assert [group["fix_id"] for group in action["repair_evidence_groups"]] == ["first", "second"]
    assert [group["locale"] for group in action["repair_evidence_groups"]] == ["fr", "de"]
    assert {group["family"] for group in action["repair_evidence_groups"]} == {"collection_page", "product_detail"}


def test_production_shaped_nonempty_fingerprint_persists_as_one_action_without_enabling_fixed_state():
    # Production review rows carry the scanner's repair_fingerprint but do not
    # generally carry repair_surface or repair_identity_stable=True. The old
    # persistence gate therefore wrote one FixItem per row even though the
    # customer read path correctly rendered this fingerprint as one action.
    first = {
        "fix_id": "audit_first",
        "rule": "missing_meta_description",
        "category": "meta_description",
        "priority": "medium",
        "base_severity": "medium",
        "action_priority": "improve",
        "evidence_class": "improvement",
        "page_scope": "page",
        "page_template_family": "collection_page",
        "affected_pages": ["https://example.com/fr/category/a"],
        "page_count": 1,
        "difficulty": "easy",
        "repair_fingerprint": "production-fingerprint",
    }
    second = {
        **first,
        "fix_id": "audit_second",
        "priority": "high",
        "base_severity": "high",
        "action_priority": "important",
        "evidence_class": "confirmed_problem",
        "page_template_family": "product_detail",
        "affected_pages": ["https://example.com/de/product/b"],
        "difficulty": "hard",
        "requires_developer": True,
        "who_can_do_this": "your_web_person",
    }
    pages = [
        {**_page("https://example.com/fr/category/a"), "page_template_family": "collection_page"},
        {**_page("https://example.com/de/product/b"), "page_template_family": "product_detail"},
    ]

    grouped = _group_canonical_repairs([first, second], pages)

    assert len(grouped) == 1
    action = grouped[0]
    assert action["repair_fingerprint"] == "production-fingerprint"
    assert action["affected_pages"] == [
        "https://example.com/fr/category/a",
        "https://example.com/de/product/b",
    ]
    assert action["page_count"] == 2
    assert action["action_priority"] == "important"
    assert action["priority"] == "high"
    assert action["requires_developer"] is True
    assert action["difficulty"] == "hard"
    assert [group["fix_id"] for group in action["repair_evidence_groups"]] == [
        "audit_first",
        "audit_second",
    ]

    # Grouping is presentation/persistence identity only. With no explicit
    # technical repair surface the cross-scan fixed-state contract stays closed.
    assert action["repair_identity_stable"] is False
    comparison = compare_repair_runs(action, [], pages)
    assert comparison["state"] == "could_not_verify"


def test_missing_fingerprints_remain_separate_persistence_rows():
    rows = [
        {
            "fix_id": fix_id,
            "rule": "missing_meta_description",
            "category": "meta_description",
            "priority": "medium",
            "base_severity": "medium",
            "action_priority": "improve",
            "evidence_class": "improvement",
            "page_scope": "page",
            "page_template_family": "standard",
            "affected_pages": [f"https://example.com/{fix_id}"],
            "page_count": 1,
            "difficulty": "easy",
            "repair_fingerprint": "",
        }
        for fix_id in ("missing_a", "missing_b")
    ]

    grouped = _group_canonical_repairs(rows, [_page("https://example.com/missing_a"), _page("https://example.com/missing_b")])

    assert [item["fix_id"] for item in grouped] == ["missing_a", "missing_b"]
    assert all(len(item["repair_evidence_groups"]) == 1 for item in grouped)


def test_grouping_deduplicates_urls_without_losing_child_counts():
    first = {
        **_fix("first", "internal_link_redirect", "high", ["https://example.com/a", "https://example.com/shared"]),
        "repair_fingerprint": "redirect-fp",
        "repair_identity_stable": True,
        "action_priority": "important",
        "base_severity": "high",
        "evidence_class": "confirmed_problem",
    }
    second = {
        **_fix("second", "internal_link_redirect", "high", ["https://example.com/shared", "https://example.com/b"]),
        "repair_fingerprint": "redirect-fp",
        "repair_identity_stable": True,
        "action_priority": "important",
        "base_severity": "high",
        "evidence_class": "confirmed_problem",
    }

    grouped = _group_canonical_repairs(
        [first, second],
        [_page("https://example.com/a"), _page("https://example.com/shared"), _page("https://example.com/b")],
    )

    assert len(grouped) == 1
    assert grouped[0]["affected_pages"] == [
        "https://example.com/a",
        "https://example.com/shared",
        "https://example.com/b",
    ]
    assert grouped[0]["page_count"] == 3
    assert [child["count"] for child in grouped[0]["repair_evidence_groups"]] == [2, 2]
