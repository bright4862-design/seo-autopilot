from copy import deepcopy

from app.repair_shadow import build_shadow_review_analysis
from app.review import run_review


def _page(path: str, *, family: str = "product_detail", **extra):
    return {
        "url": f"https://example.com{path}",
        "final_url": f"https://example.com{path}",
        "status_code": 200,
        "content_type": "text/html",
        "title": f"Page {path}",
        "h1_count": 1,
        "h1": "Useful heading",
        "meta_description": "Useful description",
        "canonical": f"https://example.com{path}",
        "page_template_family": family,
        "indexable": True,
        **extra,
    }


def _review(pages):
    return run_review({
        "website_url": "https://example.com",
        "pages_found": len(pages),
        "pages_crawled": len(pages),
        "pages": pages,
        "scan_coverage": {
            "pages_found": len(pages),
            "pages_crawled": len(pages),
            "sampled_pages_sent_to_ai": len(pages),
        },
    })


def test_shadow_analysis_consumes_finished_review_without_mutating_it():
    pages = [
        _page("/products/a", meta_description=""),
        _page("/products/b"),
        _page("/products/c"),
        _page("/products/d"),
    ]
    review = _review(pages)
    before = deepcopy(review)

    analysis = build_shadow_review_analysis(review, pages)

    assert review == before
    assert analysis["current_order_preserved"] is True
    assert analysis["source_fix_count"] == len(review["cleaned_fixes"])
    assert analysis["current_order"] == [
        str(fix.get("fix_id") or fix.get("id") or "")
        for fix in review["cleaned_fixes"]
    ]
    assert all(
        fix.get("repair_contract_version") == analysis["version"]
        for fix in analysis["fixes"]
    )


def test_shadow_analysis_cannot_change_review_release_or_authority_fields():
    pages = [
        _page("/products/a", canonical=""),
        _page("/products/b"),
        _page("/products/c"),
        _page("/products/d"),
    ]
    review = _review(pages)
    protected = {
        "scan_status": review.get("scan_status"),
        "release_gate_eligible": review.get("release_gate_eligible"),
        "score_is_provisional": review.get("score_is_provisional"),
        "health_score": review.get("health_score"),
        "review_confidence_state": review.get("review_confidence_state"),
    }

    build_shadow_review_analysis(review, pages)

    assert {
        "scan_status": review.get("scan_status"),
        "release_gate_eligible": review.get("release_gate_eligible"),
        "score_is_provisional": review.get("score_is_provisional"),
        "health_score": review.get("health_score"),
        "review_confidence_state": review.get("review_confidence_state"),
    } == protected


def test_shadow_analysis_reports_divergence_without_reordering_source_repairs():
    review_result = {
        "cleaned_fixes": [
            {
                "id": "wide",
                "fix_id": "wide",
                "rule": "missing_meta_description",
                "category": "meta_description",
                "priority": "medium",
                "affected_pages": [
                    "https://example.com/products/a",
                    "https://example.com/products/b",
                ],
                "page_template_family": "product_detail",
                "confidence_score": 95,
            },
            {
                "id": "urgent",
                "fix_id": "urgent",
                "rule": "canonical_missing",
                "category": "canonical",
                "priority": "critical",
                "affected_pages": ["https://example.com/products/a"],
                "page_template_family": "product_detail",
                "confidence_score": 95,
            },
        ],
    }
    pages = [_page("/products/a"), _page("/products/b")]
    source_order = [fix["id"] for fix in review_result["cleaned_fixes"]]

    analysis = build_shadow_review_analysis(review_result, pages)

    assert [fix["id"] for fix in review_result["cleaned_fixes"]] == source_order
    assert [fix["id"] for fix in analysis["fixes"]] == source_order
    assert analysis["priority_divergence"]["order_changed"] is True
    assert [fix["id"] for fix in analysis["proposed_fixes"]][0] == "urgent"


def test_shadow_analysis_fails_closed_to_empty_when_review_has_no_repairs():
    review_result = {
        "scan_status": "complete_no_high_confidence_findings",
        "cleaned_fixes": [],
    }

    analysis = build_shadow_review_analysis(review_result, [])

    assert analysis["source_fix_count"] == 0
    assert analysis["fixes"] == []
    assert analysis["proposed_fixes"] == []
    assert analysis["priority_divergence"]["order_changed"] is False
