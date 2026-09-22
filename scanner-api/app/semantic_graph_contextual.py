"""Fail-closed contextual internal-link opportunity evidence for NextGen Lane B.

This module consumes only already-built Lane-B graph/page evidence. It performs no
network work, creates no customer Fix, and makes no sitewide link-absence claim.
It specifically distinguishes an existing navigation/footer/listing/etc. link
from an observed contextual link so a semantically relevant contextual upgrade
is not incorrectly suppressed merely because a global/non-contextual edge exists.
"""
from __future__ import annotations

from math import isfinite
from typing import Any, Iterable

from .semantic_graph import (
    GRAPH_EVIDENCE_VERSION,
    MAX_CANDIDATES,
    ZONE_WEIGHTS,
    DeterministicLocalVectorizer,
    SemanticVectorizer,
    _bounded_best_rows,
    _bounded_pages,
    _explicitly_indexable,
    _semantic_pair_rows,
    _usable_page,
    _url,
)


CONTEXTUAL_INTERNAL_LINK_OPPORTUNITY_VERSION = "contextual_internal_link_opportunity_v1"
EVIDENCE_SCOPE = "observed_assessed_pages_only"


def _empty_result(reason: str) -> dict[str, Any]:
    return {
        "version": CONTEXTUAL_INTERNAL_LINK_OPPORTUNITY_VERSION,
        "scope": EVIDENCE_SCOPE,
        "graph_integrity_state": "not_verified",
        "reason": reason,
        "sitewide_link_absence_claim": False,
        "semantic_pair_scan_complete": False,
        "candidate_count": 0,
        "state": "not_verified",
        "candidates": [],
        "candidates_truncated": False,
    }


def _page_population(pages: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], str | None]:
    by_url: dict[str, dict[str, Any]] = {}
    for page in pages:
        url = _url(page.get("url") or page.get("final_url") or page.get("page_url"))
        if not url:
            continue
        if url in by_url:
            return {}, "duplicate_page_identity"
        by_url[url] = page
    return by_url, None


def _strict_non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _strict_non_negative_weight(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(parsed) or parsed < 0.0:
        return None
    # Producer graph metrics are serialized at six-decimal precision.
    if parsed != round(parsed, 6):
        return None
    return parsed


def _validated_graph(
    page_urls: set[str],
    graph: dict[str, Any],
) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, dict[str, Any]], str | None]:
    if not isinstance(graph, dict) or graph.get("version") != GRAPH_EVIDENCE_VERSION:
        return {}, {}, "graph_version_mismatch"
    if graph.get("scope") != EVIDENCE_SCOPE:
        return {}, {}, "graph_scope_mismatch"

    raw_nodes = graph.get("nodes")
    raw_edges = graph.get("edges")
    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        return {}, {}, "graph_shape_invalid"

    nodes: dict[str, dict[str, Any]] = {}
    declared_metrics: dict[str, dict[str, int | float]] = {}
    for row in raw_nodes:
        if not isinstance(row, dict):
            return {}, {}, "graph_node_invalid"
        url = _url(row.get("url"))
        if not url or url in nodes:
            return {}, {}, "graph_node_identity_invalid"

        weighted_in = _strict_non_negative_weight(row.get("weighted_in"))
        weighted_out = _strict_non_negative_weight(row.get("weighted_out"))
        if weighted_in is None or weighted_out is None:
            return {}, {}, "graph_node_weight_invalid"

        observed_in = _strict_non_negative_int(row.get("observed_in_edge_count"))
        observed_out = _strict_non_negative_int(row.get("observed_out_edge_count"))
        if observed_in is None or observed_out is None:
            return {}, {}, "graph_node_edge_count_invalid"

        nodes[url] = row
        declared_metrics[url] = {
            "weighted_in": weighted_in,
            "weighted_out": weighted_out,
            "observed_in_edge_count": observed_in,
            "observed_out_edge_count": observed_out,
        }

    if set(nodes) != page_urls:
        return {}, {}, "graph_page_population_mismatch"

    expected_metrics: dict[str, dict[str, int | float]] = {
        url: {
            "weighted_in": 0.0,
            "weighted_out": 0.0,
            "observed_in_edge_count": 0,
            "observed_out_edge_count": 0,
        }
        for url in page_urls
    }
    edges: dict[tuple[str, str], dict[str, Any]] = {}
    for row in raw_edges:
        if not isinstance(row, dict):
            return {}, {}, "graph_edge_invalid"
        source = _url(row.get("source_url"))
        target = _url(row.get("target_url"))
        key = (source, target)
        if not source or not target or source == target or key in edges:
            return {}, {}, "graph_edge_identity_invalid"
        if source not in page_urls or target not in page_urls:
            return {}, {}, "graph_edge_population_mismatch"
        zone = str(row.get("strongest_zone") or "").strip().lower()
        if zone not in ZONE_WEIGHTS:
            return {}, {}, "graph_edge_zone_invalid"
        weight = _strict_non_negative_weight(row.get("weight"))
        if weight is None:
            return {}, {}, "graph_edge_weight_invalid"
        edges[key] = row
        expected_metrics[source]["observed_out_edge_count"] += 1
        expected_metrics[target]["observed_in_edge_count"] += 1
        expected_metrics[source]["weighted_out"] += weight
        expected_metrics[target]["weighted_in"] += weight

    for url in sorted(page_urls):
        declared = declared_metrics[url]
        expected = expected_metrics[url]
        if (
            declared["observed_in_edge_count"] != expected["observed_in_edge_count"]
            or declared["observed_out_edge_count"] != expected["observed_out_edge_count"]
        ):
            return {}, {}, "graph_node_edge_count_mismatch"
        if (
            declared["weighted_in"] != round(float(expected["weighted_in"]), 6)
            or declared["weighted_out"] != round(float(expected["weighted_out"]), 6)
        ):
            return {}, {}, "graph_node_weight_mismatch"

    return edges, nodes, None


def contextual_internal_link_opportunities(
    pages: list[dict[str, Any]],
    graph: dict[str, Any],
    *,
    semantic_threshold: float = 0.58,
    vectorizer: SemanticVectorizer | None = None,
) -> dict[str, Any]:
    """Return bounded source→target contextual-link candidate evidence.

    A pre-existing non-contextual edge does not suppress a contextual upgrade.
    Only an observed edge whose strongest observed zone is contextual suppresses
    that directed candidate. All absence language stays scoped to the assessed
    sample, and transported graph identity is validated before it can influence
    opportunity evidence.
    """
    pages = _bounded_pages(pages)
    try:
        threshold = float(semantic_threshold)
    except (TypeError, ValueError):
        raise ValueError("semantic_threshold out of bounds")
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("semantic_threshold out of bounds")

    by_url, population_error = _page_population(pages)
    if population_error:
        return _empty_result(population_error)

    edges, nodes, graph_error = _validated_graph(set(by_url), graph)
    if graph_error:
        return _empty_result(graph_error)

    vectorizer = vectorizer or DeterministicLocalVectorizer()
    vectors = vectorizer.vectors(pages)
    if not isinstance(vectors, dict):
        return _empty_result("semantic_vectors_invalid")
    if any(url not in by_url for url in vectors):
        return _empty_result("semantic_vector_population_mismatch")

    def candidate_rows() -> Iterable[dict[str, Any]]:
        for pair in _semantic_pair_rows(vectors, threshold):
            left, right = pair["left_url"], pair["right_url"]
            for source, target in ((left, right), (right, left)):
                source_page, target_page = by_url.get(source), by_url.get(target)
                if not source_page or not target_page:
                    continue
                if not (_usable_page(source_page) and _usable_page(target_page)):
                    continue
                if not _explicitly_indexable(target_page):
                    continue

                existing = edges.get((source, target))
                existing_zone = str(existing.get("strongest_zone") or "").lower() if existing else None
                if existing_zone == "contextual":
                    continue

                source_node = nodes[source]
                target_node = nodes[target]
                target_in = float(target_node.get("weighted_in") or 0.0)
                source_out = float(source_node.get("weighted_out") or 0.0)
                target_need = 1.0 / (1.0 + target_in)
                source_capacity = 1.0 / (1.0 + max(0.0, source_out - 3.0) / 8.0)
                edge_novelty = 1.0 if existing is None else 0.5
                score = (
                    0.72 * pair["similarity"]
                    + 0.16 * target_need
                    + 0.08 * source_capacity
                    + 0.04 * edge_novelty
                )

                yield {
                    "source_url": source,
                    "target_url": target,
                    "semantic_similarity": pair["similarity"],
                    "shared_terms": pair["shared_terms"],
                    "observed_edge_present": existing is not None,
                    "observed_contextual_edge_present": False,
                    "existing_strongest_zone": existing_zone,
                    "target_observed_weighted_in": round(target_in, 6),
                    "source_observed_weighted_out": round(source_out, 6),
                    "opportunity_score": round(score, 6),
                    "proposed_zone": "contextual",
                    "evidence_scope": EVIDENCE_SCOPE,
                    "sitewide_link_absence_claim": False,
                    "reason": (
                        "existing_non_contextual_edge_contextual_upgrade"
                        if existing is not None
                        else "no_observed_edge_in_assessed_sample"
                    ),
                    "state": "candidate",
                }

    candidates, candidate_count = _bounded_best_rows(
        candidate_rows(),
        key=lambda row: (-row["opportunity_score"], row["source_url"], row["target_url"]),
    )
    return {
        "version": CONTEXTUAL_INTERNAL_LINK_OPPORTUNITY_VERSION,
        "scope": EVIDENCE_SCOPE,
        "graph_integrity_state": "verified",
        "sitewide_link_absence_claim": False,
        "semantic_pair_scan_complete": True,
        "candidate_count": candidate_count,
        "state": "candidate" if candidates else ("not_verified" if not vectors else "no_candidate_observed"),
        "candidates": candidates,
        "candidates_truncated": candidate_count > MAX_CANDIDATES,
    }
