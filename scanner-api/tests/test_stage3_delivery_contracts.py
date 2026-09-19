from copy import deepcopy

import pytest

from app.stage3_delivery import (
    HANDOFF_V2,
    apply_root_cause_score_caps,
    build_handoff_v2,
    prepare_ranked_candidates,
    read_handoff_compatible,
    select_private_preview,
    summarize_candidate_counts,
)


def candidate(rule_id, *, rank=0, impact=1, pages=None, groups=None, observations=None, **extra):
    payload = {
        "rule_id": rule_id,
        "title": rule_id,
        "priority_rank": rank,
        "impact": impact,
        "affected_pages": list(pages or []),
        "groups": list(groups or []),
        "observations": list(observations or []),
    }
    payload.update(extra)
    return payload


def test_b21_exact_union_is_computed_before_display_sample_truncation():
    pages = [f"https://example.com/product/{i}" for i in range(15)]
    item = candidate(
        "duplicate_title",
        pages=pages[:8],
        groups=[{"affected_pages": pages[5:12]}, {"affected_pages": pages[11:]}],
        observations=[{"observed_url": pages[0]}, {"observed_url": pages[14]}],
        observation_count=23,
        known_population_count=120,
    )

    summary = summarize_candidate_counts(item, sample_limit=10)

    assert summary["unique_affected_page_count"] == 15
    assert summary["observation_count"] == 23
    assert summary["known_population_count"] == 120
    assert summary["displayed_sample_count"] == 10
    assert summary["displayed_samples"] == pages[:10]
    assert summary["examples_partial"] is True
    assert summary["truncated_sample_count"] == 5


def test_b21_overlapping_groups_do_not_double_count_pages():
    item = candidate(
        "shared_template",
        pages=["https://e.test/a", "https://e.test/b"],
        groups=[
            {"affected_pages": ["https://e.test/b", "https://e.test/c"]},
            {"affected_pages": ["https://e.test/c", "https://e.test/d"]},
        ],
        observations=[
            {"observed_url": "https://e.test/d"},
            {"observed_url": "https://e.test/a"},
        ],
    )

    summary = summarize_candidate_counts(item, sample_limit=10)
    assert summary["unique_affected_page_count"] == 4
    assert summary["displayed_samples"] == [
        "https://e.test/a",
        "https://e.test/b",
        "https://e.test/c",
        "https://e.test/d",
    ]


def test_b21_ranks_every_candidate_before_applying_legacy_presentation_cap():
    low = [candidate(f"low-{i}", rank=10, impact=1) for i in range(40)]
    low[-1] = candidate("critical-last", rank=999, impact=5)

    output = prepare_ranked_candidates(low, presentation_limit=36)

    assert len(output["displayed_candidates"]) == 36
    assert output["displayed_candidates"][0]["rule_id"] == "critical-last"
    assert output["eligible_candidate_count"] == 40
    assert output["presentation_truncated"] is True
    assert output["presentation_omitted_count"] == 4


def test_b22_private_preview_exposes_only_whitelisted_authenticated_fields():
    hidden = candidate(
        "canonical_conflict",
        rank=90,
        impact=5,
        pages=["https://example.com/private"],
        authority_verified=True,
        preview_allowed=True,
        evidence_state="verified",
        scan_id="scan-a",
        owner_id="owner-a",
        evidence_summary="Canonical points to a conflicting live URL.",
        secret_internal_trace="must-not-leak",
        suppressed_findings=[{"title": "hidden"}],
    )

    preview = select_private_preview(
        [hidden],
        authority_verified=True,
        requested_scan_id="scan-a",
        requested_owner_id="owner-a",
        max_items=2,
    )

    assert preview["state"] == "findings"
    assert len(preview["findings"]) == 1
    exposed = preview["findings"][0]
    assert exposed == {
        "rule_id": "canonical_conflict",
        "title": "canonical_conflict",
        "impact": 5,
        "evidence_summary": "Canonical points to a conflicting live URL.",
    }
    assert "affected_pages" not in exposed
    assert "secret_internal_trace" not in exposed
    assert "suppressed_findings" not in exposed


def test_b22_unverified_tampered_or_cross_scan_candidates_never_enter_preview():
    items = [
        candidate(
            "wrong-scan",
            impact=5,
            authority_verified=True,
            preview_allowed=True,
            evidence_state="verified",
            scan_id="scan-b",
            owner_id="owner-a",
        ),
        candidate(
            "wrong-owner",
            impact=5,
            authority_verified=True,
            preview_allowed=True,
            evidence_state="verified",
            scan_id="scan-a",
            owner_id="owner-b",
        ),
        candidate(
            "unverified",
            impact=5,
            authority_verified=False,
            preview_allowed=True,
            evidence_state="verified",
            scan_id="scan-a",
            owner_id="owner-a",
        ),
        candidate(
            "not-verified-evidence",
            impact=5,
            authority_verified=True,
            preview_allowed=True,
            evidence_state="not_verified",
            scan_id="scan-a",
            owner_id="owner-a",
        ),
    ]

    preview = select_private_preview(
        items,
        authority_verified=True,
        requested_scan_id="scan-a",
        requested_owner_id="owner-a",
        coverage_qualification={"state": "limited_coverage", "text": "Only a bounded sample was checked."},
    )

    assert preview["state"] == "not_available"
    assert preview["findings"] == []
    assert preview["coverage_qualification"] == "Only a bounded sample was checked."


def test_b22_good_shape_requires_explicit_sufficient_coverage_qualification():
    qualified = select_private_preview(
        [],
        authority_verified=True,
        requested_scan_id="scan-a",
        requested_owner_id="owner-a",
        coverage_qualification={"state": "sufficient", "text": "150 representative pages checked."},
    )
    unqualified = select_private_preview(
        [],
        authority_verified=True,
        requested_scan_id="scan-a",
        requested_owner_id="owner-a",
    )

    assert qualified == {
        "state": "good_shape",
        "findings": [],
        "coverage_qualification": "150 representative pages checked.",
    }
    assert unqualified["state"] == "not_available"


def test_b23_only_verified_explicit_root_cause_caps_can_lower_score_ceiling():
    root_causes = [
        {"root_cause_id": "verified-indexability", "verification_state": "verified", "score_cap": 72},
        {"root_cause_id": "duplicate-copy", "verification_state": "verified", "score_cap": 72},
        {"root_cause_id": "heuristic", "verification_state": "heuristic", "score_cap": 50},
        {"root_cause_id": "unknown", "verification_state": "not_verified", "score_cap": 20},
        {"root_cause_id": "missing-cap", "verification_state": "verified"},
    ]

    result = apply_root_cause_score_caps(91, root_causes, existing_score_ceiling=80)

    assert result["existing_score_ceiling"] == 80
    assert result["root_cause_score_ceiling"] == 72
    assert result["effective_score_ceiling"] == 72
    assert result["adjusted_health_score"] == 72
    assert [row["root_cause_id"] for row in result["applied_root_cause_caps"]] == [
        "verified-indexability",
        "duplicate-copy",
    ]
    assert {row["root_cause_id"] for row in result["ignored_root_cause_caps"]} == {
        "heuristic",
        "unknown",
        "missing-cap",
    }


def test_b23_unknown_coverage_does_not_invent_a_score_penalty():
    result = apply_root_cause_score_caps(
        88,
        [{"root_cause_id": "unproven", "verification_state": "not_verified", "score_cap": 40}],
        existing_score_ceiling=85,
        coverage_state="inventory_unproven",
    )

    assert result["root_cause_score_ceiling"] is None
    assert result["effective_score_ceiling"] == 85
    assert result["adjusted_health_score"] == 85
    assert result["coverage_state"] == "inventory_unproven"


def test_b24_v2_contains_explicit_counts_provenance_priority_and_dependencies():
    fixes = [
        candidate(
            "canonical_conflict",
            rank=80,
            impact=5,
            pages=["https://example.com/a", "https://example.com/b"],
            observation_count=3,
            known_population_count=10,
            root_cause_id="root:canonical-template",
            family_ids=["family:product"],
            published_url="https://example.com/a",
            request_url="https://example.com/a?utm_source=x",
            final_url="https://example.com/a",
            priority_factors={"impact": 5, "reach": 0.2, "page_value": 1.0, "confidence": 1.0},
            evidence_refs=["evidence:1"],
            verification_steps=["Confirm the canonical target is intentional."],
            dependency="Template canonical component",
            vendor_owner="Engineering",
        )
    ]

    handoff = build_handoff_v2(
        scan_identity={"scan_id": "scan-a", "domain": "example.com"},
        fixes=fixes,
        user_agent="FixListBot/1.0",
    )

    assert handoff["handoff_version"] == HANDOFF_V2
    assert handoff["scan"] == {"scan_id": "scan-a", "domain": "example.com"}
    assert handoff["user_agent"] == "FixListBot/1.0"
    fix = handoff["fixes"][0]
    assert fix["counts"] == {
        "unique_affected_pages": 2,
        "observations": 3,
        "known_population": 10,
        "displayed_examples": 2,
    }
    assert fix["examples_partial"] is False
    assert fix["root_cause_id"] == "root:canonical-template"
    assert fix["family_ids"] == ["family:product"]
    assert fix["url_provenance"] == {
        "published_url": "https://example.com/a",
        "request_url": "https://example.com/a?utm_source=x",
        "final_url": "https://example.com/a",
    }
    assert fix["priority_factors"]["impact"] == 5
    assert fix["evidence_refs"] == ["evidence:1"]
    assert fix["dependency"] == "Template canonical component"
    assert fix["vendor_owner"] == "Engineering"
    assert "suppressed_findings" not in handoff


def test_b24_suppressed_findings_are_operator_only():
    hidden = [{"rule_id": "suppressed", "reason": "covered_by_root_cause"}]

    customer = build_handoff_v2(
        scan_identity={"scan_id": "scan-a"},
        fixes=[],
        user_agent="FixListBot/1.0",
        suppressed_findings=hidden,
        operator_authorized=False,
    )
    operator = build_handoff_v2(
        scan_identity={"scan_id": "scan-a"},
        fixes=[],
        user_agent="FixListBot/1.0",
        suppressed_findings=hidden,
        operator_authorized=True,
    )

    assert "suppressed_findings" not in customer
    assert operator["suppressed_findings"] == hidden


def test_b24_v1_reader_is_byte_shape_compatible_and_unknown_versions_fail_closed():
    legacy = {
        "domain": "example.com",
        "fix_count": 1,
        "fixes": [{"title": "Old handoff", "affected_pages": ["/a"]}],
    }
    original = deepcopy(legacy)

    assert read_handoff_compatible(legacy) == original
    assert legacy == original

    v2 = build_handoff_v2(
        scan_identity={"scan_id": "scan-a"},
        fixes=[],
        user_agent="FixListBot/1.0",
    )
    assert read_handoff_compatible(v2) == v2

    with pytest.raises(ValueError, match="unsupported handoff version"):
        read_handoff_compatible({"handoff_version": "fixlist_handoff_v999", "fixes": []})
