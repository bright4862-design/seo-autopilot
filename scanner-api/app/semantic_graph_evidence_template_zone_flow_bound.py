"""Raw-zone-template-flow-bound Lane-B semantic-graph evidence envelope.

This preferred envelope extends the B10-cluster-bound v8 evidence package with
raw-observation template-to-template link-zone flow. It preserves repeated and
mixed-zone observations that the reduced weighted graph intentionally collapses
into one strongest-zone edge.

The helper is pure evidence generation. It creates no customer Fix and does not
modify scanner orchestration, final repair priority, authority/persistence,
customer projection, admission, release, deployment, or production.
"""
from __future__ import annotations

from typing import Any

from .semantic_graph import SemanticVectorizer, _bounded_links, _bounded_pages
from .semantic_graph_evidence_near_duplicate_cluster_bound import (
    NEAR_DUPLICATE_CLUSTER_BOUND_GRAPH_ENVELOPE_VERSION,
    build_near_duplicate_cluster_bound_semantic_graph_evidence,
)
from .semantic_graph_template_zone_flow import (
    TEMPLATE_LINK_ZONE_FLOW_VERSION,
    template_link_zone_flow_evidence,
)


TEMPLATE_ZONE_FLOW_BOUND_GRAPH_ENVELOPE_VERSION = (
    "semantic_graph_evidence_v9_template_zone_flow_bound"
)


def build_template_zone_flow_bound_semantic_graph_evidence(
    pages: list[dict[str, Any]],
    links: list[dict[str, Any]],
    *,
    vectorizer: SemanticVectorizer | None = None,
    cluster_threshold: float = 0.62,
    cannibalization_threshold: float = 0.72,
    duplicate_threshold: float = 0.82,
    contextual_threshold: float = 0.58,
) -> dict[str, Any]:
    """Build the preferred Lane-B envelope with raw-zone template-flow evidence.

    The semantic adapter remains owned by the underlying v8 boundary. This wrapper
    performs no semantic/provider call and only derives template-zone flow from
    already supplied bounded pages/links plus the graph/template evidence built by
    v8. A template-zone integrity failure fails the envelope closed; otherwise the
    existing v8 verified/partial/not-verified state is preserved.
    """
    pages = _bounded_pages(pages)
    links = _bounded_links(links)
    base = build_near_duplicate_cluster_bound_semantic_graph_evidence(
        pages,
        links,
        vectorizer=vectorizer,
        cluster_threshold=cluster_threshold,
        cannibalization_threshold=cannibalization_threshold,
        duplicate_threshold=duplicate_threshold,
        contextual_threshold=contextual_threshold,
    )
    template_zone_flow = template_link_zone_flow_evidence(
        pages,
        links,
        base["template_evidence"],
        base["graph"],
    )

    result = dict(base)
    result["version"] = TEMPLATE_ZONE_FLOW_BOUND_GRAPH_ENVELOPE_VERSION
    result["previous_graph_envelope_version"] = (
        NEAR_DUPLICATE_CLUSTER_BOUND_GRAPH_ENVELOPE_VERSION
    )
    result["template_link_zone_flow_version"] = TEMPLATE_LINK_ZONE_FLOW_VERSION
    result["template_link_zone_flow"] = template_zone_flow

    if template_zone_flow.get("state") != "verified":
        result["state"] = "not_verified"
        result["reason"] = str(
            template_zone_flow.get("reason") or "template_link_zone_flow_not_verified"
        )

    result["sitewide_template_flow_claim"] = False
    result["sitewide_link_distribution_claim"] = False
    result["sitewide_link_absence_claim"] = False
    result["customer_fix_created"] = False
    return result
