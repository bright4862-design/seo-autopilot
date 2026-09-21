import math

import pytest

from app.stage3_delivery import (
    apply_root_cause_score_caps,
    select_private_preview,
    summarize_candidate_counts,
)


def _preview_candidate(rule_id, *, impact, priority_score):
    return {
        "rule_id": rule_id,
        "title": rule_id,
        "impact": impact,
        "priority_score": priority_score,
        "authority_verified": True,
        "preview_allowed": True,
        "evidence_state": "verified",
        "scan_id": "scan-a",
        "owner_id": "owner-a",
        "evidence_summary": f"Verified evidence for {rule_id}.",
    }


@pytest.mark.parametrize("invalid_priority", ["999", math.nan, math.inf, -math.inf])
def test_b22_invalid_or_nonfinite_priority_cannot_outrank_known_numeric_priority(invalid_priority):
    preview = select_private_preview(
        [
            _preview_candidate("invalid-priority", impact=5, priority_score=invalid_priority),
            _preview_candidate("known-priority", impact=5, priority_score=1.0),
        ],
        authority_verified=True,
        requested_scan_id="scan-a",
        requested_owner_id="owner-a",
        max_items=1,
    )

    assert preview["state"] == "findings"
    assert [item["rule_id"] for item in preview["findings"]] == ["known-priority"]


@pytest.mark.parametrize("invalid_impact", ["5", 4.5, math.nan, math.inf, -math.inf])
def test_b22_invalid_or_nonintegral_impact_cannot_create_high_impact_preview_eligibility(invalid_impact):
    preview = select_private_preview(
        [
            _preview_candidate("invalid-impact", impact=invalid_impact, priority_score=999.0),
            _preview_candidate("known-impact", impact=3, priority_score=1.0),
        ],
        authority_verified=True,
        requested_scan_id="scan-a",
        requested_owner_id="owner-a",
        max_items=1,
    )

    assert preview["state"] == "findings"
    assert [item["rule_id"] for item in preview["findings"]] == ["known-impact"]
    assert preview["findings"][0]["impact"] == 3


@pytest.mark.parametrize("invalid_population", ["10", 10.5, math.nan, math.inf, -math.inf, True])
def test_b21_malformed_count_evidence_stays_unknown_without_coercion_or_crash(invalid_population):
    summary = summarize_candidate_counts(
        {
            "affected_pages": ["https://example.com/a", "https://example.com/b"],
            "observations": [
                {"observed_url": "https://example.com/a"},
                {"observed_url": "https://example.com/b"},
            ],
            "observation_count": "999",
            "known_population_count": invalid_population,
        }
    )

    # The malformed explicit observation count is ignored; the retained observation
    # collection is still truthful evidence and therefore supplies the event count.
    assert summary["observation_count"] == 2
    assert summary["known_population_count"] is None


@pytest.mark.parametrize("invalid_cap", ["72", 72.5, math.nan, math.inf, -math.inf, True])
def test_b23_malformed_score_cap_never_becomes_a_confirmed_root_cause_ceiling(invalid_cap):
    result = apply_root_cause_score_caps(
        90,
        [
            {
                "root_cause_id": "root:verified-but-malformed-cap",
                "verification_state": "verified",
                "score_cap": invalid_cap,
            }
        ],
    )

    assert result["root_cause_score_ceiling"] is None
    assert result["effective_score_ceiling"] is None
    assert result["adjusted_health_score"] == 90
    assert result["applied_root_cause_caps"] == []
    assert result["ignored_root_cause_caps"] == [
        {
            "root_cause_id": "root:verified-but-malformed-cap",
            "score_cap": None,
            "reason": "missing_or_invalid_explicit_cap",
        }
    ]
