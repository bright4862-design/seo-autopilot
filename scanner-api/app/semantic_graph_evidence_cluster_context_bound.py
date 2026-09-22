"""Semantic-cluster-context-bound Lane-B graph evidence envelope.

This additive v14 wrapper extends v13 weighted-route opportunity evidence with
semantic-cluster membership/profile context for the same contextual source→target
candidate sample. It adds no semantic/provider invocation and creates no customer
Fix, repair-priority, persistence, projection, admission, release, deployment, or
production behavior.
"""
from __future__ import annotations

from typing import Any

from .semantic_graph import SemanticVectorizer, _bounded_links, _bounded_pages
from .semantic_graph_evidence_weighted_route_bound import (
    WEIGHTED_ROUTE_BOUND_GRAPH_ENVELOPE_VERSION,
    build_weighted_route_bound_semantic_graph_evidence,
)
from .semantic_graph_opportunity_cluster_context import (
    CLUSTER_CONTEXTUAL_OPPORTUNITY_VERSION,
    cluster_context_internal_link_opportunities,
)


CLUSTER_CONTEXT_BOUND_GRAPH_ENVELOPE_VERSION = (
    "semantic_graph_evidence_v14_cluster_context_opportunity_bound"
)


def build_cluster_context_bound_semantic_graph_evidence(
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
    """Build v14 without invoking the semantic adapter beyond the v13 boundary."""
    pages = _bounded_pages(pages)
    links = _bounded_links(links)
    base = build_weighted_route_bound_semantic_graph_evidence(
        pages,
        links,
        vectorizer=vectorizer,
        cluster_threshold=cluster_threshold,
        cannibalization_threshold=cannibalization_threshold,
        duplicate_threshold=duplicate_threshold,
        contextual_threshold=contextual_threshold,
        seed_urls=seed_urls,
    )
    cluster_context = cluster_context_internal_link_opportunities(
        base["weighted_route_contextual_internal_link_opportunities"],
        base["semantic_cluster_profile"],
    )

    result = dict(base)
    result["version"] = CLUSTER_CONTEXT_BOUND_GRAPH_ENVELOPE_VERSION
    result["previous_graph_envelope_version"] = (
        WEIGHTED_ROUTE_BOUND_GRAPH_ENVELOPE_VERSION
    )
    result["cluster_contextual_opportunity_version"] = (
        CLUSTER_CONTEXTUAL_OPPORTUNITY_VERSION
    )
    result["cluster_contextual_internal_link_opportunities"] = cluster_context

    if cluster_context.get("state") == "not_verified":
        if base.get("state") != "not_verified":
            result["reason"] = str(
                cluster_context.get("reason")
                or "cluster_contextual_opportunities_not_verified"
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
