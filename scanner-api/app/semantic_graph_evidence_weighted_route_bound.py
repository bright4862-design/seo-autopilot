"""Weighted-route-bound Lane-B semantic-graph evidence envelope.

This additive v13 wrapper extends the v12 money-reachability envelope with
deterministic max-bottleneck route evidence for the already-produced contextual
source→target candidate sample. It adds no semantic/provider invocation and makes
no customer Fix, repair-priority, persistence, or sitewide reachability decision.
"""
from __future__ import annotations

from typing import Any

from .semantic_graph import SemanticVectorizer, _bounded_links, _bounded_pages
from .semantic_graph_evidence_money_reachability_bound import (
    MONEY_REACHABILITY_BOUND_GRAPH_ENVELOPE_VERSION,
    build_money_reachability_bound_semantic_graph_evidence,
)
from .semantic_graph_opportunity_weighted_route import (
    WEIGHTED_ROUTE_CONTEXTUAL_OPPORTUNITY_VERSION,
    weighted_route_internal_link_opportunities,
)


WEIGHTED_ROUTE_BOUND_GRAPH_ENVELOPE_VERSION = (
    "semantic_graph_evidence_v13_weighted_route_opportunity_bound"
)


def build_weighted_route_bound_semantic_graph_evidence(
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
    """Build v13 without invoking the semantic adapter beyond the v12 boundary."""
    pages = _bounded_pages(pages)
    links = _bounded_links(links)
    base = build_money_reachability_bound_semantic_graph_evidence(
        pages,
        links,
        vectorizer=vectorizer,
        cluster_threshold=cluster_threshold,
        cannibalization_threshold=cannibalization_threshold,
        duplicate_threshold=duplicate_threshold,
        contextual_threshold=contextual_threshold,
        seed_urls=seed_urls,
    )
    weighted_routes = weighted_route_internal_link_opportunities(
        base["graph_neighborhood_contextual_internal_link_opportunities"],
        base["graph"],
    )

    result = dict(base)
    result["version"] = WEIGHTED_ROUTE_BOUND_GRAPH_ENVELOPE_VERSION
    result["previous_graph_envelope_version"] = (
        MONEY_REACHABILITY_BOUND_GRAPH_ENVELOPE_VERSION
    )
    result["weighted_route_contextual_opportunity_version"] = (
        WEIGHTED_ROUTE_CONTEXTUAL_OPPORTUNITY_VERSION
    )
    result["weighted_route_contextual_internal_link_opportunities"] = (
        weighted_routes
    )

    if weighted_routes.get("state") == "not_verified":
        if base.get("state") != "not_verified":
            result["reason"] = str(
                weighted_routes.get("reason")
                or "weighted_route_contextual_opportunities_not_verified"
            )
        result["state"] = "not_verified"

    result["sitewide_reachability_claim"] = False
    result["sitewide_orphan_claim"] = False
    result["sitewide_template_flow_claim"] = False
    result["sitewide_link_distribution_claim"] = False
    result["sitewide_link_absence_claim"] = False
    result["customer_fix_created"] = False
    return result
