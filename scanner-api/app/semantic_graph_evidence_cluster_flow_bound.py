"""Semantic-cluster-link-flow-bound Lane-B graph evidence envelope.

This additive v15 wrapper extends v14 cluster-context opportunity evidence with
weighted page-graph flow collapsed onto the validated semantic-cluster profile.
It adds no semantic/provider invocation and creates no customer Fix, priority,
persistence, projection, admission, release, deployment, or production behavior.
"""
from __future__ import annotations

from typing import Any

from .semantic_graph import SemanticVectorizer, _bounded_links, _bounded_pages
from .semantic_graph_cluster_link_flow import (
    SEMANTIC_CLUSTER_LINK_FLOW_VERSION,
    semantic_cluster_link_flow,
)
from .semantic_graph_evidence_cluster_context_bound import (
    CLUSTER_CONTEXT_BOUND_GRAPH_ENVELOPE_VERSION,
    build_cluster_context_bound_semantic_graph_evidence,
)


CLUSTER_FLOW_BOUND_GRAPH_ENVELOPE_VERSION = (
    "semantic_graph_evidence_v15_semantic_cluster_link_flow_bound"
)


def build_cluster_flow_bound_semantic_graph_evidence(
    pages: list[dict[str, Any]],
    links: list[dict[str, Any]],
    *,
    vectorizer: SemanticVectorizer | None = None,
    cluster_threshold: float = 0.62,
    cannibalization_threshold: float = 0.72,
    duplicate_threshold: float = 0.82,
    contextual_threshold: float = 0.58,
    seed_urls: list[str] | None = None,
) -> dict[str, Any]:
    """Build v15 without invoking the semantic adapter beyond the v14 boundary."""
    pages = _bounded_pages(pages)
    links = _bounded_links(links)
    base = build_cluster_context_bound_semantic_graph_evidence(
        pages,
        links,
        vectorizer=vectorizer,
        cluster_threshold=cluster_threshold,
        cannibalization_threshold=cannibalization_threshold,
        duplicate_threshold=duplicate_threshold,
        contextual_threshold=contextual_threshold,
        seed_urls=seed_urls,
    )
    cluster_flow = semantic_cluster_link_flow(
        base.get("graph"),
        base.get("semantic_cluster_profile"),
    )

    result = dict(base)
    result["version"] = CLUSTER_FLOW_BOUND_GRAPH_ENVELOPE_VERSION
    result["previous_graph_envelope_version"] = (
        CLUSTER_CONTEXT_BOUND_GRAPH_ENVELOPE_VERSION
    )
    result["semantic_cluster_link_flow_version"] = SEMANTIC_CLUSTER_LINK_FLOW_VERSION
    result["semantic_cluster_link_flow"] = cluster_flow

    if cluster_flow.get("state") == "not_verified":
        if base.get("state") != "not_verified":
            result["reason"] = str(
                cluster_flow.get("reason") or "semantic_cluster_link_flow_not_verified"
            )
        result["state"] = "not_verified"

    result["sitewide_semantic_coverage_claim"] = False
    result["sitewide_reachability_claim"] = False
    result["sitewide_orphan_claim"] = False
    result["sitewide_link_absence_claim"] = False
    result["sitewide_template_flow_claim"] = False
    result["sitewide_link_distribution_claim"] = False
    result["customer_fix_created"] = False
    return result
