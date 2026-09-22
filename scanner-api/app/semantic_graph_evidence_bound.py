"""Vector-bound Lane-B semantic-graph evidence envelope.

This module composes Lane-B-owned template, weighted-link-graph, semantic,
near-duplicate, cannibalization, and contextual-link evidence without touching
scanner orchestration, repair priority, authority/persistence, projection, or
production. It is deliberately pure and performs no provider/network work.

The legacy ``build_semantic_graph_evidence`` helper predates the semantic-vector
integrity contract and may invoke a pluggable vectorizer multiple times. New
integration should prefer ``build_vector_bound_semantic_graph_evidence`` so all
semantic-dependent outputs are derived from one validated, isolated, deterministic
snapshot under ``semantic_vector_contract_v1``.
"""
from __future__ import annotations

from typing import Any

from .semantic_graph import (
    GRAPH_EVIDENCE_VERSION,
    TEMPLATE_EVIDENCE_VERSION,
    ZONE_WEIGHTS,
    SemanticVectorizer,
    _bounded_links,
    _bounded_pages,
    build_weighted_internal_link_graph,
    infer_template_groups,
)
from .semantic_graph_analysis_bound import (
    VECTOR_BOUND_SEMANTIC_ANALYSIS_VERSION,
    vector_bound_semantic_analysis_evidence,
)
from .semantic_graph_contextual import _page_population


VECTOR_BOUND_GRAPH_ENVELOPE_VERSION = "semantic_graph_evidence_v2_vector_bound"
LINK_ZONE_SUMMARY_VERSION = "link_zone_summary_v1_graph_edge_bound"
EVIDENCE_SCOPE = "observed_assessed_pages_only"


def _graph_edge_zone_summary(graph: dict[str, Any]) -> dict[str, Any]:
    """Summarize only the strongest zone retained on assessed graph edges.

    This is intentionally not a claim about all links on the site. The weighted
    graph already reduces repeated observations for one directed source/target
    pair to its strongest observed zone; this summary reports that bounded graph
    evidence exactly and nothing more.
    """
    counts = {zone: 0 for zone in ZONE_WEIGHTS}
    edges = graph.get("edges") if isinstance(graph, dict) else None
    if not isinstance(edges, list):
        edges = []
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        zone = str(edge.get("strongest_zone") or "").strip().lower()
        if zone in counts:
            counts[zone] += 1
    return {
        "version": LINK_ZONE_SUMMARY_VERSION,
        "scope": EVIDENCE_SCOPE,
        "summary_basis": "strongest_zone_per_observed_assessed_directed_edge",
        "observed_directed_edge_count": len(edges),
        "strongest_zone_counts": counts,
        "sitewide_link_distribution_claim": False,
    }


def build_vector_bound_semantic_graph_evidence(
    pages: list[dict[str, Any]],
    links: list[dict[str, Any]],
    *,
    vectorizer: SemanticVectorizer | None = None,
    cluster_threshold: float = 0.62,
    cannibalization_threshold: float = 0.72,
    duplicate_threshold: float = 0.82,
    contextual_threshold: float = 0.58,
) -> dict[str, Any]:
    """Build the preferred Lane-B evidence envelope from one semantic snapshot.

    Duplicate assessed-page identities are rejected before any caller-provided
    vectorizer executes. Template inference and graph construction remain purely
    local. Semantic-dependent clustering, cannibalization, and contextual-link
    opportunity evidence are delegated to the vector-bound analysis contract,
    which validates adapter shape/population/determinism/input isolation and then
    replays one sealed vector snapshot to every downstream semantic analyzer.

    The result is evidence only. It creates no customer Fix and makes no sitewide
    orphan/link-absence claim.
    """
    pages = _bounded_pages(pages)
    links = _bounded_links(links)

    population, population_error = _page_population(pages)
    if population_error:
        raise ValueError(population_error)

    template_evidence = infer_template_groups(pages)
    graph = build_weighted_internal_link_graph(pages, links)
    semantic_analysis = vector_bound_semantic_analysis_evidence(
        pages,
        graph,
        vectorizer=vectorizer,
        cluster_threshold=cluster_threshold,
        cannibalization_threshold=cannibalization_threshold,
        duplicate_threshold=duplicate_threshold,
        contextual_threshold=contextual_threshold,
    )

    semantic_state = str(
        semantic_analysis.get("semantic_vector_integrity_state") or "not_verified"
    )
    graph_state = str(semantic_analysis.get("graph_integrity_state") or "not_verified")
    if semantic_state != "verified":
        state = "not_verified"
        reason = str(
            semantic_analysis.get("semantic_vector_integrity_reason")
            or "semantic_vector_not_verified"
        )
    elif graph_state != "verified":
        state = "not_verified"
        reason = str(
            semantic_analysis.get("graph_integrity_reason") or "graph_not_verified"
        )
    else:
        state = "verified"
        reason = "validated"

    return {
        "version": VECTOR_BOUND_GRAPH_ENVELOPE_VERSION,
        "scope": EVIDENCE_SCOPE,
        "state": state,
        "reason": reason,
        "assessed_page_identity_count": len(population),
        "template_evidence_version": TEMPLATE_EVIDENCE_VERSION,
        "graph_evidence_version": GRAPH_EVIDENCE_VERSION,
        "semantic_analysis_version": VECTOR_BOUND_SEMANTIC_ANALYSIS_VERSION,
        "template_evidence": template_evidence,
        "graph": graph,
        "link_zone_summary": _graph_edge_zone_summary(graph),
        "semantic_analysis": semantic_analysis,
        "semantic_clusters": semantic_analysis["semantic_clusters"],
        "near_duplicate_candidates": semantic_analysis["near_duplicate_candidates"],
        "cannibalization_candidates": semantic_analysis["cannibalization_candidates"],
        "contextual_internal_link_opportunities": semantic_analysis[
            "contextual_internal_link_opportunities"
        ],
        "sitewide_orphan_claim": False,
        "sitewide_link_absence_claim": False,
        "customer_fix_created": False,
    }
