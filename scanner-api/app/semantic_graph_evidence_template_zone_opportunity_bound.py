"""Raw-zone-template-opportunity-bound Lane-B semantic-graph evidence envelope.

This preferred envelope extends v9 raw template-zone flow evidence by binding the
existing template-aware contextual source→target candidates to that exact verified
raw-zone template flow. It remains pure evidence generation and performs no
additional semantic/provider call.
"""
from __future__ import annotations

from typing import Any

from .semantic_graph import SemanticVectorizer, _bounded_links, _bounded_pages
from .semantic_graph_evidence_template_zone_flow_bound import (
    TEMPLATE_ZONE_FLOW_BOUND_GRAPH_ENVELOPE_VERSION,
    build_template_zone_flow_bound_semantic_graph_evidence,
)
from .semantic_graph_template_zone_opportunity import (
    RAW_ZONE_TEMPLATE_CONTEXTUAL_OPPORTUNITY_VERSION,
    raw_zone_template_contextual_internal_link_opportunities,
)


TEMPLATE_ZONE_OPPORTUNITY_BOUND_GRAPH_ENVELOPE_VERSION = (
    "semantic_graph_evidence_v10_template_zone_opportunity_bound"
)


def build_template_zone_opportunity_bound_semantic_graph_evidence(
    pages: list[dict[str, Any]],
    links: list[dict[str, Any]],
    *,
    vectorizer: SemanticVectorizer | None = None,
    cluster_threshold: float = 0.62,
    cannibalization_threshold: float = 0.72,
    duplicate_threshold: float = 0.82,
    contextual_threshold: float = 0.58,
) -> dict[str, Any]:
    """Build the preferred Lane-B envelope with raw-zone-bound opportunities.

    v9 remains the sole semantic-analysis owner. This wrapper consumes only the
    already-built template-contextual candidate evidence and raw-zone template
    flow, so the caller vectorizer/provider invocation count cannot increase here.
    """
    pages = _bounded_pages(pages)
    links = _bounded_links(links)
    base = build_template_zone_flow_bound_semantic_graph_evidence(
        pages,
        links,
        vectorizer=vectorizer,
        cluster_threshold=cluster_threshold,
        cannibalization_threshold=cannibalization_threshold,
        duplicate_threshold=duplicate_threshold,
        contextual_threshold=contextual_threshold,
    )
    raw_zone_opportunities = raw_zone_template_contextual_internal_link_opportunities(
        base["template_contextual_internal_link_opportunities"],
        base["template_link_zone_flow"],
    )

    result = dict(base)
    result["version"] = TEMPLATE_ZONE_OPPORTUNITY_BOUND_GRAPH_ENVELOPE_VERSION
    result["previous_graph_envelope_version"] = (
        TEMPLATE_ZONE_FLOW_BOUND_GRAPH_ENVELOPE_VERSION
    )
    result["raw_zone_template_contextual_opportunity_version"] = (
        RAW_ZONE_TEMPLATE_CONTEXTUAL_OPPORTUNITY_VERSION
    )
    result["raw_zone_template_contextual_internal_link_opportunities"] = (
        raw_zone_opportunities
    )

    if raw_zone_opportunities.get("state") == "not_verified":
        result["state"] = "not_verified"
        result["reason"] = str(
            raw_zone_opportunities.get("reason")
            or "raw_zone_template_contextual_opportunities_not_verified"
        )

    result["sitewide_template_flow_claim"] = False
    result["sitewide_link_distribution_claim"] = False
    result["sitewide_link_absence_claim"] = False
    result["customer_fix_created"] = False
    return result
