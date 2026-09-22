"""Graph-neighborhood-bound Lane-B semantic-graph evidence envelope.

This additive v11 wrapper extends the raw-zone-bound source→target opportunity
evidence with deterministic route measurements from the already-built weighted
assessed-page graph. It adds no semantic/provider invocation and makes no sitewide
reachability, orphan, link-absence, or customer-fix decision.
"""
from __future__ import annotations

from typing import Any

from .semantic_graph import SemanticVectorizer, _bounded_links, _bounded_pages
from .semantic_graph_evidence_template_zone_opportunity_bound import (
    TEMPLATE_ZONE_OPPORTUNITY_BOUND_GRAPH_ENVELOPE_VERSION,
    build_template_zone_opportunity_bound_semantic_graph_evidence,
)
from .semantic_graph_opportunity_neighborhood import (
    GRAPH_NEIGHBORHOOD_CONTEXTUAL_OPPORTUNITY_VERSION,
    graph_neighborhood_internal_link_opportunities,
)


GRAPH_NEIGHBORHOOD_BOUND_GRAPH_ENVELOPE_VERSION = (
    "semantic_graph_evidence_v11_graph_neighborhood_opportunity_bound"
)


def build_graph_neighborhood_bound_semantic_graph_evidence(
    pages: list[dict[str, Any]],
    links: list[dict[str, Any]],
    *,
    vectorizer: SemanticVectorizer | None = None,
    cluster_threshold: float = 0.62,
    cannibalization_threshold: float = 0.72,
    duplicate_threshold: float = 0.82,
    contextual_threshold: float = 0.58,
) -> dict[str, Any]:
    """Build v11 with assessed-graph route evidence on existing opportunities."""
    pages = _bounded_pages(pages)
    links = _bounded_links(links)
    base = build_template_zone_opportunity_bound_semantic_graph_evidence(
        pages,
        links,
        vectorizer=vectorizer,
        cluster_threshold=cluster_threshold,
        cannibalization_threshold=cannibalization_threshold,
        duplicate_threshold=duplicate_threshold,
        contextual_threshold=contextual_threshold,
    )
    graph_neighborhood = graph_neighborhood_internal_link_opportunities(
        base["raw_zone_template_contextual_internal_link_opportunities"],
        base["graph"],
    )

    result = dict(base)
    result["version"] = GRAPH_NEIGHBORHOOD_BOUND_GRAPH_ENVELOPE_VERSION
    result["previous_graph_envelope_version"] = (
        TEMPLATE_ZONE_OPPORTUNITY_BOUND_GRAPH_ENVELOPE_VERSION
    )
    result["graph_neighborhood_contextual_opportunity_version"] = (
        GRAPH_NEIGHBORHOOD_CONTEXTUAL_OPPORTUNITY_VERSION
    )
    result["graph_neighborhood_contextual_internal_link_opportunities"] = (
        graph_neighborhood
    )

    if graph_neighborhood.get("state") == "not_verified":
        if base.get("state") != "not_verified":
            result["reason"] = str(
                graph_neighborhood.get("reason")
                or "graph_neighborhood_contextual_opportunities_not_verified"
            )
        result["state"] = "not_verified"

    result["sitewide_reachability_claim"] = False
    result["sitewide_orphan_claim"] = False
    result["sitewide_template_flow_claim"] = False
    result["sitewide_link_distribution_claim"] = False
    result["sitewide_link_absence_claim"] = False
    result["customer_fix_created"] = False
    return result
