"""Data-shaped shadow regression from a completed Standard-150 scan census.

A 2026-10-16 completed scan recorded 150 checked pages. Its sampling_evidence
family_sampled contains 149 sitemap-selected pages; the remaining checked page
is modeled as an unknown seed. These are aggregate historical observations,
NOT a replay of original raw pages or proof of a fresh live scan.
"""
from app.repair_priority_calibration import annotate_calibrated_repair_priority

# Recorded family_sampled counts from a completed Standard-150 run.
RECORDED_SAMPLED_FAMILIES = {
    "legal_info": 2,
    "standard": 71,
    "contact": 1,
    "guide_article": 48,
    "comparison_page": 1,
    "conversion": 2,
    "collection_page": 21,
    "homepage": 3,
}


def fixture_page(family, index):
    path = f"/observed/{family}/{index}"
    return {
        "url": f"https://example.com{path}",
        "page_template_family": family,
        "indexable": True,
        "status_code": 200,
        "content_type": "text/html",
    }


def issue(family, pages):
    return {
        "rule": "canonical_missing",
        "category": "canonical",
        "technical_severity": "medium",
        "evidence_class": "confirmed_problem",
        "affected_pages": [p["url"] for p in pages],
        "page_template_family": family,
    }


def test_historical_standard_150_family_distribution_keeps_hubs_ahead_of_guides():
    sampled = {
        family: [fixture_page(family, i) for i in range(count)]
        for family, count in RECORDED_SAMPLED_FAMILIES.items()
    }
    assert sum(map(len, sampled.values())) == 149
    # The historical scan checked 150 pages but selected 149 from sitemap.
    sampled["unknown_seed"] = [fixture_page("unknown_seed", 0)]
    pages = [p for group in sampled.values() for p in group]
    assert len(pages) == 150

    collection = annotate_calibrated_repair_priority(
        issue("collection_page", sampled["collection_page"]), pages
    )
    guides = annotate_calibrated_repair_priority(
        issue("guide_article", sampled["guide_article"]), pages
    )

    assert collection["base_severity"] == guides["base_severity"] == "medium"
    assert collection["action_priority"] == guides["action_priority"]
    assert collection["priority_context"]["architecture_role_counts"]["structural"] == 21
    assert guides["priority_context"]["architecture_role_counts"]["support"] == 48
    assert collection["action_priority_score"] > guides["action_priority_score"]
    assert "sitewide" not in collection["priority_reason"].lower()
