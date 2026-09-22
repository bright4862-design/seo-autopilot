from copy import deepcopy

from app.semantic_graph_opportunity_cluster_context import (
    CLUSTER_CONTEXTUAL_OPPORTUNITY_VERSION,
    cluster_context_internal_link_opportunities,
)
from app.semantic_graph_cluster_profile import SEMANTIC_CLUSTER_PROFILE_VERSION
from app.semantic_graph_opportunity_weighted_route import (
    WEIGHTED_ROUTE_CONTEXTUAL_OPPORTUNITY_VERSION,
    WEIGHTED_ROUTE_EVIDENCE_SCOPE,
)


SCOPE = "observed_assessed_pages_only"


def candidate(source="https://e.test/a", target="https://e.test/b"):
    return {
        "source_url": source,
        "target_url": target,
        "evidence_scope": SCOPE,
        "weighted_route_evidence_scope": WEIGHTED_ROUTE_EVIDENCE_SCOPE,
        "sitewide_reachability_claim": False,
        "sitewide_orphan_claim": False,
        "sitewide_link_absence_claim": False,
        "sitewide_template_flow_claim": False,
        "sitewide_link_distribution_claim": False,
    }


def weighted(rows=None, *, candidate_count=None, truncated=False):
    rows = [candidate()] if rows is None else rows
    count = len(rows) if candidate_count is None else candidate_count
    return {
        "version": WEIGHTED_ROUTE_CONTEXTUAL_OPPORTUNITY_VERSION,
        "scope": SCOPE,
        "state": "candidate" if rows else "no_candidate_observed",
        "reason": "validated",
        "graph_neighborhood_integrity_state": "verified",
        "graph_integrity_state": "verified",
        "candidate_count": count,
        "candidates": rows,
        "candidates_truncated": truncated,
        "weighted_route_evaluated_candidate_count": len(rows),
        "weighted_route_candidate_population_complete": not truncated,
        "weighted_route_evidence_scope": WEIGHTED_ROUTE_EVIDENCE_SCOPE,
        "sitewide_reachability_claim": False,
        "sitewide_orphan_claim": False,
        "sitewide_link_absence_claim": False,
        "sitewide_template_flow_claim": False,
        "sitewide_link_distribution_claim": False,
        "customer_fix_created": False,
    }


def profile(cluster_rows=None, *, state="verified"):
    if cluster_rows is None:
        cluster_rows = [
            {
                "cluster_id": "sem_same",
                "state": "verified",
                "reason": "validated_vector_bound_cluster_profile",
                "page_count": 2,
                "urls": ["https://e.test/a", "https://e.test/b"],
                "representative_url": "https://e.test/a",
                "top_terms": [],
            }
        ]
    return {
        "version": SEMANTIC_CLUSTER_PROFILE_VERSION,
        "scope": SCOPE,
        "state": state,
        "reason": "validated",
        "cluster_count": len(cluster_rows),
        "profile_count": len(cluster_rows),
        "profiles": cluster_rows,
        "semantic_vector_coverage_state": "complete",
        "semantic_pair_population_complete": True,
        "semantic_pair_scope": "all_pairs_within_vectorized_assessed_pages",
        "sitewide_semantic_coverage_claim": False,
        "customer_fix_created": False,
    }


def test_same_cluster_context_marks_representatives_without_creating_fix():
    result = cluster_context_internal_link_opportunities(weighted(), profile())

    assert result["version"] == CLUSTER_CONTEXTUAL_OPPORTUNITY_VERSION
    assert result["state"] == "candidate"
    row = result["candidates"][0]
    assert row["semantic_cluster_relation"] == "same_cluster"
    assert row["source_semantic_cluster_id"] == "sem_same"
    assert row["target_semantic_cluster_id"] == "sem_same"
    assert row["source_is_semantic_cluster_representative"] is True
    assert row["target_is_semantic_cluster_representative"] is False
    assert result["sitewide_semantic_coverage_claim"] is False
    assert result["customer_fix_created"] is False


def test_different_cluster_context_is_descriptive_only():
    clusters = [
        {
            "cluster_id": "sem_a",
            "state": "verified",
            "reason": "validated",
            "page_count": 2,
            "urls": ["https://e.test/a", "https://e.test/a2"],
            "representative_url": "https://e.test/a",
            "top_terms": [],
        },
        {
            "cluster_id": "sem_b",
            "state": "verified",
            "reason": "validated",
            "page_count": 2,
            "urls": ["https://e.test/b", "https://e.test/b2"],
            "representative_url": "https://e.test/b2",
            "top_terms": [],
        },
    ]
    result = cluster_context_internal_link_opportunities(weighted(), profile(clusters))
    row = result["candidates"][0]
    assert row["semantic_cluster_relation"] == "different_clusters"
    assert row["source_semantic_cluster_id"] == "sem_a"
    assert row["target_semantic_cluster_id"] == "sem_b"
    assert row["target_semantic_cluster_representative_url"] == "https://e.test/b2"


def test_unclustered_pair_remains_valid_sample_scoped_evidence():
    empty = profile([], state="no_cluster_observed")
    empty["reason"] = "no_semantic_cluster_observed"
    result = cluster_context_internal_link_opportunities(weighted(), empty)
    row = result["candidates"][0]
    assert row["semantic_cluster_relation"] == "unclustered_pair"
    assert row["source_semantic_cluster_id"] is None
    assert row["target_semantic_cluster_id"] is None
    assert row["sitewide_semantic_coverage_claim"] is False


def test_source_cluster_only_is_explicit():
    clusters = [
        {
            "cluster_id": "sem_a",
            "state": "verified",
            "reason": "validated",
            "page_count": 2,
            "urls": ["https://e.test/a", "https://e.test/a2"],
            "representative_url": "https://e.test/a2",
            "top_terms": [],
        }
    ]
    result = cluster_context_internal_link_opportunities(weighted(), profile(clusters))
    assert result["candidates"][0]["semantic_cluster_relation"] == "source_cluster_only"


def test_zero_candidate_transport_remains_verified_and_complete():
    result = cluster_context_internal_link_opportunities(weighted([]), profile())
    assert result["state"] == "no_candidate_observed"
    assert result["candidate_count"] == 0
    assert result["cluster_context_candidate_population_complete"] is True
    assert result["customer_fix_created"] is False


def test_truncated_candidate_population_stays_explicit():
    result = cluster_context_internal_link_opportunities(
        weighted([candidate()], candidate_count=3, truncated=True), profile()
    )
    assert result["state"] == "candidate"
    assert result["candidate_count"] == 3
    assert result["cluster_context_evaluated_candidate_count"] == 1
    assert result["cluster_context_candidate_population_complete"] is False


def test_overlapping_cluster_members_fail_closed():
    clusters = [
        {
            "cluster_id": "sem_a",
            "state": "verified",
            "page_count": 2,
            "urls": ["https://e.test/a", "https://e.test/x"],
            "representative_url": "https://e.test/a",
        },
        {
            "cluster_id": "sem_b",
            "state": "verified",
            "page_count": 2,
            "urls": ["https://e.test/x", "https://e.test/b"],
            "representative_url": "https://e.test/b",
        },
    ]
    result = cluster_context_internal_link_opportunities(weighted(), profile(clusters))
    assert result["state"] == "not_verified"
    assert result["reason"] == "semantic_cluster_profile_member_overlap"
    assert result["candidates"] == []


def test_duplicate_candidate_identity_fails_closed():
    row = candidate()
    result = cluster_context_internal_link_opportunities(weighted([row, deepcopy(row)]), profile())
    assert result["state"] == "not_verified"
    assert result["reason"] == "weighted_route_candidate_identity_invalid"


def test_forged_weighted_route_population_complete_flag_fails_closed():
    evidence = weighted()
    evidence["weighted_route_candidate_population_complete"] = False
    result = cluster_context_internal_link_opportunities(evidence, profile())
    assert result["state"] == "not_verified"
    assert result["reason"] == "weighted_route_population_complete_mismatch"


def test_not_verified_cluster_profile_fails_closed():
    evidence = profile()
    evidence["state"] = "not_verified"
    result = cluster_context_internal_link_opportunities(weighted(), evidence)
    assert result["state"] == "not_verified"
    assert result["reason"] == "semantic_cluster_profile_not_verified"


def test_sitewide_claim_in_cluster_profile_fails_closed():
    evidence = profile()
    evidence["sitewide_semantic_coverage_claim"] = True
    result = cluster_context_internal_link_opportunities(weighted(), evidence)
    assert result["state"] == "not_verified"
    assert result["reason"] == "semantic_cluster_profile_sitewide_semantic_coverage_claim_invalid"
