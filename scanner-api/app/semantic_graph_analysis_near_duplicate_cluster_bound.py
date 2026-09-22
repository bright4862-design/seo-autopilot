"""B10-cluster-bound semantic-analysis evidence for NextGen Lane B.

This contract extends the cluster-profile-bound single-snapshot analysis bundle
with deterministic near-duplicate *cluster* evidence derived only from retained,
verified B10 main-content shingles. The semantic adapter is still owned by the
underlying v3 analysis boundary and is never called by this module.

The helper emits descriptive evidence only. It creates no customer Fix and does
not touch orchestration, repair priority, authority/persistence, projection,
admission, release, deployment, or production.
"""
from __future__ import annotations

from typing import Any

from .semantic_graph import SemanticVectorizer, _bounded_pages
from .semantic_graph_analysis_profile_bound import (
    cluster_profile_bound_semantic_analysis_evidence,
)
from .semantic_graph_near_duplicate_clusters import (
    NEAR_DUPLICATE_CLUSTER_VERSION,
    near_duplicate_cluster_evidence,
)


NEAR_DUPLICATE_CLUSTER_BOUND_SEMANTIC_ANALYSIS_VERSION = (
    "semantic_analysis_bundle_v4_b10_cluster_bound"
)


def _bind_near_duplicate_cluster_evidence(
    pages: list[dict[str, Any]],
    analysis: dict[str, Any],
    *,
    duplicate_threshold: float,
) -> dict[str, Any]:
    """Bind B10 pair and cluster evidence produced from one page snapshot.

    The legacy pair candidate producer and the B10 cluster producer intentionally
    remain separate contracts. This binder cross-checks their full eligible-page
    and qualifying-pair counts whenever both producers are verified, so future
    producer drift cannot silently create contradictory evidence.
    """
    pages = _bounded_pages(pages)
    cluster_evidence = near_duplicate_cluster_evidence(
        pages,
        threshold=duplicate_threshold,
    )
    pair_evidence = analysis.get("near_duplicate_candidates")
    if not isinstance(pair_evidence, dict):
        pair_evidence = {}

    pair_state = str(pair_evidence.get("state") or "not_verified")
    cluster_state = str(cluster_evidence.get("state") or "not_verified")
    binding_state = "verified"
    binding_reason = "pair_and_cluster_b10_population_counts_match"

    if pair_state == "not_verified" and cluster_state == "not_verified":
        binding_state = "not_verified"
        binding_reason = str(
            cluster_evidence.get("reason") or "b10_main_content_evidence_not_verified"
        )
    elif pair_state == "not_verified" or cluster_state == "not_verified":
        binding_state = "not_verified"
        binding_reason = "pair_cluster_verification_state_mismatch"
    else:
        pair_eligible = pair_evidence.get("eligible_pages")
        cluster_eligible = cluster_evidence.get("eligible_page_count")
        pair_count = pair_evidence.get("candidate_count")
        cluster_pair_count = cluster_evidence.get("qualifying_pair_count")
        if pair_eligible != cluster_eligible:
            binding_state = "not_verified"
            binding_reason = "pair_cluster_eligible_page_count_mismatch"
        elif pair_count != cluster_pair_count:
            binding_state = "not_verified"
            binding_reason = "pair_cluster_qualifying_pair_count_mismatch"

    result = dict(analysis)
    result["version"] = NEAR_DUPLICATE_CLUSTER_BOUND_SEMANTIC_ANALYSIS_VERSION
    result["near_duplicate_cluster_version"] = NEAR_DUPLICATE_CLUSTER_VERSION
    result["near_duplicate_cluster_evidence"] = cluster_evidence
    result["near_duplicate_cluster_binding_state"] = binding_state
    result["near_duplicate_cluster_binding_reason"] = binding_reason
    result["near_duplicate_cluster_coverage_state"] = cluster_evidence.get(
        "coverage_state",
        "not_verified",
    )
    result["sitewide_near_duplicate_claim"] = False
    result["customer_fix_created"] = False
    return result


def near_duplicate_cluster_bound_semantic_analysis_evidence(
    pages: list[dict[str, Any]],
    graph: dict[str, Any],
    *,
    vectorizer: SemanticVectorizer | None = None,
    cluster_threshold: float = 0.62,
    cannibalization_threshold: float = 0.72,
    duplicate_threshold: float = 0.82,
    contextual_threshold: float = 0.58,
) -> dict[str, Any]:
    """Evaluate the preferred Lane-B semantic bundle with B10 clusters.

    Semantic clustering, cannibalization, contextual link opportunities, and
    semantic-cluster profiles continue to consume the single validated semantic
    snapshot provided by the v3 boundary. B10 near-duplicate clusters are local
    shingle evidence and do not invoke or depend on the semantic vectorizer.
    """
    pages = _bounded_pages(pages)
    analysis = cluster_profile_bound_semantic_analysis_evidence(
        pages,
        graph,
        vectorizer=vectorizer,
        cluster_threshold=cluster_threshold,
        cannibalization_threshold=cannibalization_threshold,
        duplicate_threshold=duplicate_threshold,
        contextual_threshold=contextual_threshold,
    )
    return _bind_near_duplicate_cluster_evidence(
        pages,
        analysis,
        duplicate_threshold=duplicate_threshold,
    )
