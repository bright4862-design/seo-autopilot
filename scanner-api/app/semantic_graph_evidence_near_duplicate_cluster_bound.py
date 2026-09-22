"""B10-near-duplicate-cluster-bound Lane-B semantic-graph evidence envelope.

This preferred envelope extends the v7 cluster-profile-bound graph envelope with
near-duplicate connected-component evidence from verified B10 main-content
shingles. It reuses the v7 semantic-analysis result rather than re-running the
semantic adapter, preserving the two-call determinism/input-isolation contract.

The helper is pure evidence generation. It creates no customer Fix and does not
modify scanner orchestration, final repair priority, authority/persistence,
customer projection, admission, release, deployment, or production.
"""
from __future__ import annotations

from typing import Any

from .semantic_graph import SemanticVectorizer, _bounded_links, _bounded_pages
from .semantic_graph_analysis_near_duplicate_cluster_bound import (
    NEAR_DUPLICATE_CLUSTER_BOUND_SEMANTIC_ANALYSIS_VERSION,
    _bind_near_duplicate_cluster_evidence,
)
from .semantic_graph_evidence_cluster_profile_bound import (
    build_cluster_profile_bound_semantic_graph_evidence,
)
from .semantic_graph_near_duplicate_clusters import NEAR_DUPLICATE_CLUSTER_VERSION


NEAR_DUPLICATE_CLUSTER_BOUND_GRAPH_ENVELOPE_VERSION = (
    "semantic_graph_evidence_v8_b10_cluster_bound"
)


def build_near_duplicate_cluster_bound_semantic_graph_evidence(
    pages: list[dict[str, Any]],
    links: list[dict[str, Any]],
    *,
    vectorizer: SemanticVectorizer | None = None,
    cluster_threshold: float = 0.62,
    cannibalization_threshold: float = 0.72,
    duplicate_threshold: float = 0.82,
    contextual_threshold: float = 0.58,
) -> dict[str, Any]:
    """Build the preferred Lane-B envelope with B10 cluster evidence.

    B10 evidence is intentionally scoped to verified accepted-main-content
    shingles. Missing B10 coverage is exposed as unknown/partial evidence and does
    not invalidate independently verified semantic/vector or graph evidence.
    Contradictory pair-vs-cluster producer counts fail the B10 binding closed.
    """
    pages = _bounded_pages(pages)
    links = _bounded_links(links)
    base = build_cluster_profile_bound_semantic_graph_evidence(
        pages,
        links,
        vectorizer=vectorizer,
        cluster_threshold=cluster_threshold,
        cannibalization_threshold=cannibalization_threshold,
        duplicate_threshold=duplicate_threshold,
        contextual_threshold=contextual_threshold,
    )
    analysis = _bind_near_duplicate_cluster_evidence(
        pages,
        base["semantic_analysis"],
        duplicate_threshold=duplicate_threshold,
    )

    result = dict(base)
    result["version"] = NEAR_DUPLICATE_CLUSTER_BOUND_GRAPH_ENVELOPE_VERSION
    result["semantic_analysis_version"] = (
        NEAR_DUPLICATE_CLUSTER_BOUND_SEMANTIC_ANALYSIS_VERSION
    )
    result["near_duplicate_cluster_version"] = NEAR_DUPLICATE_CLUSTER_VERSION
    result["semantic_analysis"] = analysis
    result["near_duplicate_cluster_evidence"] = analysis[
        "near_duplicate_cluster_evidence"
    ]
    result["near_duplicate_cluster_binding_state"] = analysis[
        "near_duplicate_cluster_binding_state"
    ]
    result["near_duplicate_cluster_binding_reason"] = analysis[
        "near_duplicate_cluster_binding_reason"
    ]
    result["near_duplicate_cluster_coverage_state"] = analysis[
        "near_duplicate_cluster_coverage_state"
    ]
    result["sitewide_near_duplicate_claim"] = False
    result["customer_fix_created"] = False
    return result
