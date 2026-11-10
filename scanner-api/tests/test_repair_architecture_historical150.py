"""Historical Standard-150 family-census regressions (no raw page replay).

Four completed 150-page Standard scans in the owner's Base44 records supplied
these exact 149 sitemap-selected family counts; each recorded 150 checked
pages, including one additional non-sitemap seed. We reconstruct anonymous
pages with the observed family distribution, not original page identities.
These regressions test architecture priority against REAL OBSERVED MIXES but
DO NOT satisfy the separate fresh-live-scan acceptance gate.
"""
import pytest

from app.repair_priority_calibration import annotate_calibrated_repair_priority


# Observed family_sampled values: completed Standard-150 runs.
COHORTS = {
    "marketplace_2026_09_17": {
        "legal_info": 3, "activity_detail": 63, "collection_page": 29,
        "standard": 52, "guide_article": 1, "homepage": 1,
    },
    "finance_2026_09_13": {
        "legal_info": 2, "contact": 1, "standard": 10, "loan_program": 6,
        "conversion": 3, "location_landing": 60,
        "guide_article": 66, "homepage": 1,
    },
    "location_business_2026_10_12": {
        "standard": 37, "legal_info": 3, "contact": 1,
        "location_landing": 106, "guide_article": 1, "homepage": 1,
    },
    "mixed_index_2026_10_16": {
        "legal_info": 2, "standard": 71, "contact": 1, "guide_article": 48,
        "comparison_page": 1, "conversion": 2, "collection_page": 21,
        "homepage": 3,
    },
}


def cohort_pages(name):
    selected = {}
    for family, count in COHORTS[name].items():
        selected[family] = [
            {"url": f"https://example.com/observed/{family}/{i}",
             "page_template_family": family, "indexable": True,
             "status_code": 200, "content_type": "text/html"}
            for i in range(count)
        ]
    assert sum(len(group) for group in selected.values()) == 149
    selected["unknown_seed"] = [
        {"url": "https://example.com/observed/seed", "page_template_family": "other",
         "indexable": True, "status_code": 200, "content_type": "text/html"}
    ]
    pages = [p for group in selected.values() for p in group]
    assert len(pages) == 150
    return selected, pages


def issue(family, subset):
    return {
        "rule": "canonical_missing", "category": "canonical",
        "technical_severity": "medium", "evidence_class": "confirmed_problem",
        "affected_pages": [p["url"] for p in subset],
        "page_template_family": family,
    }


@pytest.mark.parametrize("cohort,winner,loser,winning_role,losing_role", [
    ("marketplace_2026_09_17", "collection_page", "activity_detail", "structural", "commercial_leaf"),
    ("finance_2026_09_13", "loan_program", "guide_article", "business_critical", "support"),
    ("location_business_2026_10_12", "location_landing", "standard", "structural", "support"),
    ("mixed_index_2026_10_16", "collection_page", "guide_article", "structural", "support"),
])
def test_historical_standard150_role_priorities(
    cohort, winner, loser, winning_role, losing_role
):
    sampled, pages = cohort_pages(cohort)
    high_value = annotate_calibrated_repair_priority(issue(winner, sampled[winner]), pages)
    repeated = annotate_calibrated_repair_priority(issue(loser, sampled[loser]), pages)

    assert high_value["base_severity"] == repeated["base_severity"] == "medium"
    assert high_value["action_priority"] == repeated["action_priority"]
    assert high_value["priority_context"]["architecture_role_counts"][winning_role] == len(sampled[winner])
    assert repeated["priority_context"]["architecture_role_counts"][losing_role] == len(sampled[loser])
    assert high_value["action_priority_score"] > repeated["action_priority_score"]
    assert "sitewide" not in high_value["priority_reason"].lower()
