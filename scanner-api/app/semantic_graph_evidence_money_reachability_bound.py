"""Money-page reachability-bound Lane-B semantic-graph evidence envelope.

This additive v12 wrapper extends the v11 graph-neighborhood opportunity envelope
with deterministic assessed-sample money-page reachability evidence derived only
from the already-built weighted graph and bounded raw link observations. It adds
no semantic/provider invocation, customer Fix, priority decision, persistence, or
sitewide orphan/reachability claim.
"""
from __future__ import annotations

from typing import Any

from .semantic_graph import SemanticVectorizer, _bounded_links, _bounded_pages
from .semantic_graph_evidence_opportunity_neighborhood_bound import (
    GRAPH_NEIGHBORHOOD_BOUND_GRAPH_ENVELOPE_VERSION,
    build_graph_neighborhood_bound_semantic_graph_evidence,
)
from .semantic_graph_money_reachability import (
    WEIGHTED_MONEY_PAGE_REACHABILITY_VERSION,
    weighted_money_page_reachability_evidence,
)


MONEY_REACHABILITY_BOUND_GRAPH_ENVELOPE_VERSION = (
    "semantic_graph_evidence_v12_money_reachability_bound"
)


def build_money_reachability_bound_semantic_graph_evidence(
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
    """Build v12 by binding classified money pages to assessed graph reachability."""
    pages = _bounded_pages(pages)
    links = _bounded_links(links)
    base = build_graph_neighborhood_bound_semantic_graph_evidence(
        pages,
        links,
        vectorizer=vectorizer,
        cluster_threshold=cluster_threshold,
        cannibalization_threshold=cannibalization_threshold,
        duplicate_threshold=duplicate_threshold,
        contextual_threshold=contextual_threshold,
    )
    reachability = weighted_money_page_reachability_evidence(
        pages,
        links,
        base["graph"],
        seed_urls=seed_urls,
    )

    result = dict(base)
    result["version"] = MONEY_REACHABILITY_BOUND_GRAPH_ENVELOPE_VERSION
    result["previous_graph_envelope_version"] = (
        GRAPH_NEIGHBORHOOD_BOUND_GRAPH_ENVELOPE_VERSION
    )
    result["money_page_reachability_version"] = (
        WEIGHTED_MONEY_PAGE_REACHABILITY_VERSION
    )
    result["money_page_reachability"] = reachability

    if reachability.get("state") == "not_verified":
        if base.get("state") != "not_verified":
            result["reason"] = str(
                reachability.get("reason")
                or "money_page_reachability_not_verified"
            )
        result["state"] = "not_verified"

    result["sitewide_reachability_claim"] = False
    result["sitewide_orphan_claim"] = False
    result["sitewide_navigation_absence_claim"] = False
    result["sitewide_link_absence_claim"] = False
    result["sitewide_link_distribution_claim"] = False
    result["customer_fix_created"] = False
    return result
