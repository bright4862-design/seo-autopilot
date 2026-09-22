"""Cluster-profile-bound Lane-B semantic-graph evidence envelope.

This preferred Lane-B envelope carries deterministic semantic-cluster profile
evidence together with template/link-zone evidence, the weighted internal-link
graph, semantic clusters, near-duplicate/cannibalization candidates, and
source-to-target internal-link opportunities. All semantic-dependent evidence is
derived from one validated semantic snapshot.

The helper is pure evidence generation and creates no customer Fix. It does not
modify scanner orchestration, repair priority, authority/persistence, projection,
admission, release, deployment, or production.
"""
from __future__ import annotations

from typing import Any

from .semantic_graph import (
    GRAPH_EVIDENCE_VERSION,
    TEMPLATE_EVIDENCE_VERSION,
    SemanticVectorizer,
    _bounded_links,
    _bounded_pages,
    build_weighted_internal_link_graph,
    infer_template_groups,
)
from .semantic_graph_analysis_profile_bound import (
    CLUSTER_PROFILE_BOUND_SEMANTIC_ANALYSIS_VERSION,
    cluster_profile_bound_semantic_analysis_evidence,
)
from .semantic_graph_cluster_profile import SEMANTIC_CLUSTER_PROFILE_VERSION
from .semantic_graph_contextual import _page_population
from .semantic_graph_evidence_bound import (
    EVIDENCE_SCOPE,
    _graph_edge_zone_summary,
)
from .semantic_graph_template_flow import (
    TEMPLATE_LINK_FLOW_VERSION,
    template_link_flow_evidence,
)
from .semantic_graph_template_opportunity import (
    TEMPLATE_CONTEXTUAL_OPPORTUNITY_VERSION,
    template_contextual_internal_link_opportunities,
)
from .semantic_graph_zone_profile import (
    LINK_ZONE_OBSERVATION_PROFILE_VERSION,
    graph_bound_link_zone_observation_profile,
)


CLUSTER_PROFILE_BOUND_GRAPH_ENVELOPE_VERSION = (
    "semantic_graph_evidence_v7_cluster_profile_bound"
)


def build_cluster_profile_bound_semantic_graph_evidence(
    pages: list[dict[str, Any]],
    links: list[dict[str, Any]],
    *,
    vectorizer: SemanticVectorizer | None = None,
    cluster_threshold: float = 0.62,
    cannibalization_threshold: float = 0.72,
    duplicate_threshold: float = 0.82,
    contextual_threshold: float = 0.58,
) -> dict[str, Any]:
    """Build the Lane-B graph envelope with same-snapshot cluster profiles.

    Duplicate assessed-page identities are rejected before caller vectorizer code
    executes. Missing page identities remain explicit. Raw link-zone observations,
    template flow, and template-context opportunity evidence remain graph-bound and
    sample-scoped.

    Semantic cluster profiles are computed only from the vector snapshot accepted
    by ``semantic_vector_contract_v1`` inside the v3 analysis boundary. No third
    adapter/provider invocation is permitted. Partial semantic-vector coverage is
    transported as partial evidence and never promoted to a sitewide claim.
    """
    pages = _bounded_pages(pages)
    links = _bounded_links(links)

    population, population_error = _page_population(pages)
    if population_error:
        raise ValueError(population_error)

    input_page_count = len(pages)
    if len(population) == input_page_count:
        page_identity_coverage_state = "complete"
    elif population:
        page_identity_coverage_state = "partial"
    else:
        page_identity_coverage_state = "not_verified"

    template_evidence = infer_template_groups(pages)
    graph = build_weighted_internal_link_graph(pages, links)
    link_zone_observation_profile = graph_bound_link_zone_observation_profile(
        pages,
        links,
        graph,
    )
    template_link_flow = template_link_flow_evidence(template_evidence, graph)
    semantic_analysis = cluster_profile_bound_semantic_analysis_evidence(
        pages,
        graph,
        vectorizer=vectorizer,
        cluster_threshold=cluster_threshold,
        cannibalization_threshold=cannibalization_threshold,
        duplicate_threshold=duplicate_threshold,
        contextual_threshold=contextual_threshold,
    )
    template_contextual_opportunities = template_contextual_internal_link_opportunities(
        template_evidence,
        graph,
        semantic_analysis["contextual_internal_link_opportunities"],
    )

    zone_profile_state = str(link_zone_observation_profile.get("state") or "not_verified")
    template_flow_state = str(template_link_flow.get("state") or "not_verified")
    semantic_state = str(
        semantic_analysis.get("semantic_vector_integrity_state") or "not_verified"
    )
    semantic_coverage_state = str(
        semantic_analysis.get("semantic_vector_coverage_state") or "not_verified"
    )
    graph_state = str(semantic_analysis.get("graph_integrity_state") or "not_verified")
    template_context_state = str(
        template_contextual_opportunities.get("state") or "not_verified"
    )
    cluster_profile_state = str(
        semantic_analysis["semantic_cluster_profile"].get("state") or "not_verified"
    )

    if page_identity_coverage_state != "complete":
        state = "not_verified"
        reason = "page_identity_coverage_incomplete"
    elif zone_profile_state != "verified":
        state = "not_verified"
        reason = str(
            link_zone_observation_profile.get("reason")
            or "link_zone_observation_profile_not_verified"
        )
    elif template_flow_state != "verified":
        state = "not_verified"
        reason = str(template_link_flow.get("reason") or "template_link_flow_not_verified")
    elif semantic_state != "verified":
        state = "not_verified"
        reason = str(
            semantic_analysis.get("semantic_vector_integrity_reason")
            or "semantic_vector_not_verified"
        )
    elif semantic_coverage_state == "none":
        state = "not_verified"
        reason = "semantic_vector_coverage_unavailable"
    elif semantic_coverage_state not in {"complete", "partial"}:
        state = "not_verified"
        reason = "semantic_vector_coverage_not_verified"
    elif graph_state != "verified":
        state = "not_verified"
        reason = str(
            semantic_analysis.get("graph_integrity_reason") or "graph_not_verified"
        )
    elif template_context_state == "not_verified":
        state = "not_verified"
        reason = str(
            template_contextual_opportunities.get("reason")
            or "template_contextual_opportunities_not_verified"
        )
    elif cluster_profile_state == "not_verified":
        state = "not_verified"
        reason = str(
            semantic_analysis["semantic_cluster_profile"].get("reason")
            or "semantic_cluster_profile_not_verified"
        )
    elif semantic_coverage_state == "partial":
        state = "partial"
        reason = "semantic_vector_coverage_partial"
    elif cluster_profile_state == "partial":
        state = "partial"
        reason = "semantic_cluster_profile_partial"
    else:
        state = "verified"
        reason = "validated"

    return {
        "version": CLUSTER_PROFILE_BOUND_GRAPH_ENVELOPE_VERSION,
        "scope": EVIDENCE_SCOPE,
        "state": state,
        "reason": reason,
        "input_page_count": input_page_count,
        "assessed_page_identity_count": len(population),
        "page_identity_coverage_state": page_identity_coverage_state,
        "semantic_vector_coverage_version": semantic_analysis.get(
            "semantic_vector_coverage_version"
        ),
        "semantic_vector_coverage_state": semantic_coverage_state,
        "semantic_assessed_page_identity_count": semantic_analysis.get(
            "semantic_assessed_page_identity_count",
            0,
        ),
        "semantic_vectorized_pages": semantic_analysis.get("semantic_vectorized_pages", 0),
        "unidentified_page_count": semantic_analysis.get("unidentified_page_count"),
        "unvectorized_page_identity_count": semantic_analysis.get(
            "unvectorized_page_identity_count"
        ),
        "semantic_pair_population_complete": bool(
            semantic_analysis.get("semantic_pair_population_complete")
        ),
        "semantic_pair_scope": semantic_analysis.get(
            "semantic_pair_scope",
            "not_verified",
        ),
        "template_evidence_version": TEMPLATE_EVIDENCE_VERSION,
        "graph_evidence_version": GRAPH_EVIDENCE_VERSION,
        "link_zone_observation_profile_version": LINK_ZONE_OBSERVATION_PROFILE_VERSION,
        "template_link_flow_version": TEMPLATE_LINK_FLOW_VERSION,
        "template_contextual_opportunity_version": TEMPLATE_CONTEXTUAL_OPPORTUNITY_VERSION,
        "semantic_analysis_version": CLUSTER_PROFILE_BOUND_SEMANTIC_ANALYSIS_VERSION,
        "semantic_cluster_profile_version": SEMANTIC_CLUSTER_PROFILE_VERSION,
        "template_evidence": template_evidence,
        "graph": graph,
        "link_zone_summary": _graph_edge_zone_summary(graph),
        "link_zone_observation_profile": link_zone_observation_profile,
        "template_link_flow": template_link_flow,
        "semantic_analysis": semantic_analysis,
        "semantic_clusters": semantic_analysis["semantic_clusters"],
        "semantic_cluster_profile": semantic_analysis["semantic_cluster_profile"],
        "near_duplicate_candidates": semantic_analysis["near_duplicate_candidates"],
        "cannibalization_candidates": semantic_analysis["cannibalization_candidates"],
        "contextual_internal_link_opportunities": semantic_analysis[
            "contextual_internal_link_opportunities"
        ],
        "template_contextual_internal_link_opportunities": template_contextual_opportunities,
        "sitewide_orphan_claim": False,
        "sitewide_link_absence_claim": False,
        "sitewide_template_flow_claim": False,
        "sitewide_link_distribution_claim": False,
        "sitewide_semantic_coverage_claim": False,
        "customer_fix_created": False,
    }
