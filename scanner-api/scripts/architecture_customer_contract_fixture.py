"""Offline synthetic scanner -> canonical repair handoff fixture for JS auth tests.

Emits production-generated canonical repairs, not hand-authored JS priority
values. No network, no Base44 writes, no real user data.
"""
import json

from app.repair_contract_v2 import apply_canonical_repair_contract
from app.repair_persistence_shadow import validate_v2_persistence_candidate


def page(path, family):
    url = "https://example.com" + path
    return {"url": url, "final_url": url, "status_code": 200,
            "content_type": "text/html", "page_evidence_class": "usable_html",
            "page_template_family": family, "indexable": True}


def main():
    hub = page("/categories/widgets", "collection_page")
    leaf = page("/products/sku-1", "product_page")
    fixes = [
        {"fix_id": "hub_canonical", "rule": "canonical_missing",
         "category": "canonical", "priority": "medium",
         "technical_severity": "medium", "evidence_class": "confirmed_problem",
         "page_scope": "page", "page_template_family": "collection_page",
         "affected_pages": [hub["url"]], "confidence_score": 95,
         "issue_title": "Review category canonical",
         "repair_surface": "canonical_tag",
         "remediation_family": "add_canonical"},
        {"fix_id": "leaf_canonical", "rule": "missing_canonical",
         "category": "canonical", "priority": "medium",
         "technical_severity": "medium", "evidence_class": "confirmed_problem",
         "page_scope": "page", "page_template_family": "product_page",
         "affected_pages": [leaf["url"]], "confidence_score": 95,
         "issue_title": "Review product canonical",
         "repair_surface": "canonical_tag",
         "remediation_family": "correct_canonical"},
    ]
    review = {"cleaned_fixes": fixes, "recommendations": fixes}
    result = apply_canonical_repair_contract(review, {"crawled_pages": [leaf, hub]})
    repairs = result["canonical_repairs"]
    assert len(repairs) == 2, "fixture must preserve two independent fixes"
    assert validate_v2_persistence_candidate(result, repairs)["eligible"] is True
    assert all(x["priority_context"]["architecture_score_policy_version"]
               == "architecture_score_policy_v2_role_first" for x in repairs)
    assert repairs[0]["fix_id"] == "hub_canonical", "same-severity role ordering failed"
    assert repairs[0]["action_priority_score"] > repairs[1]["action_priority_score"]
    print(json.dumps({
        "review": {k: v for k, v in result.items()
                   if k not in {"stage3_private_preview_source", "stage3_handoff_v2_source"}},
        "expected_ids": [x["fix_id"] for x in repairs],
        "expected_scores": [x["action_priority_score"] for x in repairs],
        "expected_architecture_versions": [
            x["priority_context"]["architecture_priority_version"] for x in repairs
        ],
    }, allow_nan=False))


if __name__ == "__main__":
    main()
