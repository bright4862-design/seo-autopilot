"""Weighted assessed-route evidence for contextual internal-link opportunities.

This Lane-B helper enriches already-verified graph-neighborhood contextual-link
candidates with deterministic widest-path evidence from the same validated
weighted assessed-page graph. It performs no crawl, model/provider work,
persistence, customer Fix creation, or sitewide reachability inference.
"""
from __future__ import annotations

from heapq import heappop, heappush
from typing import Any

from .semantic_graph import ZONE_WEIGHTS, _url
from .semantic_graph_contextual import EVIDENCE_SCOPE, _validated_graph
from .semantic_graph_opportunity_neighborhood import (
    GRAPH_NEIGHBORHOOD_CONTEXTUAL_OPPORTUNITY_VERSION,
    _graph_node_urls,
    _shortest_path_hops,
)


WEIGHTED_ROUTE_CONTEXTUAL_OPPORTUNITY_VERSION = (
    "template_contextual_internal_link_opportunity_v4_weighted_route_bound"
)
WEIGHTED_ROUTE_EVIDENCE_SCOPE = "assessed_internal_graph_only"
MAX_ROUTE_URL_SAMPLES = 12


def _empty_result(
    reason: str,
    *,
    neighborhood_verified: bool = False,
    graph_verified: bool = False,
) -> dict[str, Any]:
    """Return fail-closed evidence without upgrading sample gaps to sitewide claims."""
    return {
        "version": WEIGHTED_ROUTE_CONTEXTUAL_OPPORTUNITY_VERSION,
        "scope": EVIDENCE_SCOPE,
        "state": "not_verified",
        "reason": reason,
        "graph_neighborhood_integrity_state": (
            "verified" if neighborhood_verified else "not_verified"
        ),
        "graph_integrity_state": "verified" if graph_verified else "not_verified",
        "candidate_count": 0,
        "candidates": [],
        "candidates_truncated": False,
        "weighted_route_evaluated_candidate_count": 0,
        "weighted_route_candidate_population_complete": False,
        "weighted_route_evidence_scope": WEIGHTED_ROUTE_EVIDENCE_SCOPE,
        "sitewide_reachability_claim": False,
        "sitewide_orphan_claim": False,
        "sitewide_link_absence_claim": False,
        "sitewide_template_flow_claim": False,
        "sitewide_link_distribution_claim": False,
        "customer_fix_created": False,
    }


def _strict_non_negative_int(value: Any) -> int | None:
    """Accept only real non-negative integers, excluding bool coercion."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _validated_neighborhood_opportunities(
    evidence: dict[str, Any],
) -> tuple[list[dict[str, Any]], int, bool, str | None]:
    """Validate the transported v3 candidate sample before using route fields."""
    if (
        not isinstance(evidence, dict)
        or evidence.get("version") != GRAPH_NEIGHBORHOOD_CONTEXTUAL_OPPORTUNITY_VERSION
    ):
        return [], 0, False, "graph_neighborhood_opportunity_version_mismatch"
    if evidence.get("scope") != EVIDENCE_SCOPE:
        return [], 0, False, "graph_neighborhood_opportunity_scope_mismatch"
    if evidence.get("state") == "not_verified":
        return [], 0, False, "graph_neighborhood_opportunity_not_verified"
    if evidence.get("raw_zone_opportunity_integrity_state") != "verified":
        return [], 0, False, "graph_neighborhood_raw_zone_integrity_not_verified"
    if evidence.get("graph_integrity_state") != "verified":
        return [], 0, False, "graph_neighborhood_graph_integrity_not_verified"
    if evidence.get("observed_route_scan_complete") is not True:
        return [], 0, False, "graph_neighborhood_route_scan_incomplete"
    if evidence.get("route_evidence_scope") != WEIGHTED_ROUTE_EVIDENCE_SCOPE:
        return [], 0, False, "graph_neighborhood_route_scope_mismatch"
    for field in (
        "sitewide_reachability_claim",
        "sitewide_orphan_claim",
        "sitewide_link_absence_claim",
        "sitewide_template_flow_claim",
        "sitewide_link_distribution_claim",
        "customer_fix_created",
    ):
        if evidence.get(field) is not False:
            return [], 0, False, f"graph_neighborhood_{field}_invalid"

    candidates = evidence.get("candidates")
    candidate_count = _strict_non_negative_int(evidence.get("candidate_count"))
    truncated = evidence.get("candidates_truncated")
    if (
        not isinstance(candidates, list)
        or candidate_count is None
        or not isinstance(truncated, bool)
    ):
        return [], 0, False, "graph_neighborhood_opportunity_shape_invalid"
    if candidate_count < len(candidates):
        return [], 0, False, "graph_neighborhood_opportunity_count_invalid"
    if truncated != (candidate_count > len(candidates)):
        return [], 0, False, "graph_neighborhood_opportunity_truncation_mismatch"
    expected_state = "candidate" if candidates else "no_candidate_observed"
    if evidence.get("state") != expected_state:
        return [], 0, False, "graph_neighborhood_opportunity_state_mismatch"

    seen: set[tuple[str, str]] = set()
    validated: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            return [], 0, False, "graph_neighborhood_candidate_invalid"
        source = _url(candidate.get("source_url"))
        target = _url(candidate.get("target_url"))
        key = (source, target)
        if not source or not target or source == target or key in seen:
            return [], 0, False, "graph_neighborhood_candidate_identity_invalid"
        seen.add(key)

        if candidate.get("evidence_scope") != EVIDENCE_SCOPE:
            return [], 0, False, "graph_neighborhood_candidate_scope_mismatch"
        if candidate.get("observed_route_scan_complete") is not True:
            return [], 0, False, "graph_neighborhood_candidate_route_scan_incomplete"
        if candidate.get("route_evidence_scope") != WEIGHTED_ROUTE_EVIDENCE_SCOPE:
            return [], 0, False, "graph_neighborhood_candidate_route_scope_mismatch"
        for field in (
            "sitewide_reachability_claim",
            "sitewide_orphan_claim",
            "sitewide_link_absence_claim",
            "sitewide_template_flow_claim",
            "sitewide_link_distribution_claim",
        ):
            if candidate.get(field) is not False:
                return [], 0, False, f"graph_neighborhood_candidate_{field}_invalid"

        forward = candidate.get("observed_directed_shortest_path_hops")
        reverse = candidate.get("observed_reverse_shortest_path_hops")
        if forward is not None and (
            isinstance(forward, bool) or not isinstance(forward, int) or forward < 1
        ):
            return [], 0, False, "graph_neighborhood_forward_hops_invalid"
        if reverse is not None and (
            isinstance(reverse, bool) or not isinstance(reverse, int) or reverse < 1
        ):
            return [], 0, False, "graph_neighborhood_reverse_hops_invalid"
        expected_forward_state = (
            "reachable_in_assessed_graph"
            if forward is not None
            else "no_observed_route_in_assessed_graph"
        )
        expected_reverse_state = (
            "reachable_in_assessed_graph"
            if reverse is not None
            else "no_observed_route_in_assessed_graph"
        )
        if candidate.get("observed_graph_route_state") != expected_forward_state:
            return [], 0, False, "graph_neighborhood_forward_route_state_mismatch"
        if (
            candidate.get("observed_reverse_graph_route_state")
            != expected_reverse_state
        ):
            return [], 0, False, "graph_neighborhood_reverse_route_state_mismatch"
        validated.append(candidate)

    return validated, candidate_count, truncated, None


def _widest_path(
    source: str,
    target: str,
    out_edges: dict[str, list[tuple[str, dict[str, Any]]]],
) -> tuple[tuple[str, ...] | None, float | None]:
    """Return the deterministic max-bottleneck simple path between two nodes.

    Ties prefer fewer hops and then the lexicographically smaller full URL path.
    """
    if source == target:
        return (source,), None

    start_path = (source,)
    best: dict[str, tuple[float, int, tuple[str, ...]]] = {
        source: (float("inf"), 0, start_path)
    }
    heap: list[tuple[float, int, tuple[str, ...], str]] = [
        (float("-inf"), 0, start_path, source)
    ]

    while heap:
        negative_bottleneck, hops, path, current = heappop(heap)
        bottleneck = -negative_bottleneck
        current_best = best.get(current)
        if current_best is None or current_best != (bottleneck, hops, path):
            continue
        if current == target:
            return path, bottleneck

        for neighbour, edge in out_edges.get(current, []):
            if neighbour in path:
                continue
            weight = float(edge["weight"])
            next_bottleneck = min(bottleneck, weight)
            next_hops = hops + 1
            next_path = path + (neighbour,)
            previous = best.get(neighbour)
            better = (
                previous is None
                or next_bottleneck > previous[0]
                or (
                    next_bottleneck == previous[0]
                    and (
                        next_hops < previous[1]
                        or (
                            next_hops == previous[1]
                            and next_path < previous[2]
                        )
                    )
                )
            )
            if not better:
                continue
            best[neighbour] = (next_bottleneck, next_hops, next_path)
            heappush(
                heap,
                (-next_bottleneck, next_hops, next_path, neighbour),
            )

    return None, None


def _route_url_samples(path: tuple[str, ...]) -> tuple[list[str], bool]:
    """Return a bounded sample that preserves both route endpoints."""
    if len(path) <= MAX_ROUTE_URL_SAMPLES:
        return list(path), False
    half = MAX_ROUTE_URL_SAMPLES // 2
    return list(path[:half] + path[-half:]), True


def weighted_route_internal_link_opportunities(
    neighborhood_opportunities: dict[str, Any],
    graph: dict[str, Any],
) -> dict[str, Any]:
    """Bind contextual candidates to deterministic weighted-route evidence."""
    candidates, candidate_count, truncated, neighborhood_error = (
        _validated_neighborhood_opportunities(neighborhood_opportunities)
    )
    if neighborhood_error:
        return _empty_result(neighborhood_error)

    page_urls = _graph_node_urls(graph)
    edges, nodes, graph_error = _validated_graph(page_urls, graph)
    if graph_error:
        return _empty_result(graph_error, neighborhood_verified=True)
    if graph.get("sitewide_orphan_claim") is not False:
        return _empty_result(
            "graph_sitewide_orphan_claim_invalid",
            neighborhood_verified=True,
        )
    if any(row.get("sitewide_orphan_claim") is not False for row in nodes.values()):
        return _empty_result(
            "graph_node_sitewide_orphan_claim_invalid",
            neighborhood_verified=True,
        )

    out_edges: dict[str, list[tuple[str, dict[str, Any]]]] = {
        url: [] for url in nodes
    }
    out_neighbours: dict[str, set[str]] = {url: set() for url in nodes}
    for (source, target), edge in edges.items():
        out_edges[source].append((target, edge))
        out_neighbours[source].add(target)
    for source in out_edges:
        out_edges[source].sort(key=lambda item: item[0])

    enriched: list[dict[str, Any]] = []
    for candidate in candidates:
        source = _url(candidate.get("source_url"))
        target = _url(candidate.get("target_url"))
        if source not in nodes or target not in nodes:
            return _empty_result(
                "weighted_route_graph_population_mismatch",
                neighborhood_verified=True,
                graph_verified=True,
            )

        expected_forward = _shortest_path_hops(source, target, out_neighbours)
        expected_reverse = _shortest_path_hops(target, source, out_neighbours)
        if candidate.get("observed_directed_shortest_path_hops") != expected_forward:
            return _empty_result(
                "weighted_route_forward_shortest_path_mismatch",
                neighborhood_verified=True,
                graph_verified=True,
            )
        if candidate.get("observed_reverse_shortest_path_hops") != expected_reverse:
            return _empty_result(
                "weighted_route_reverse_shortest_path_mismatch",
                neighborhood_verified=True,
                graph_verified=True,
            )

        path, bottleneck = _widest_path(source, target, out_edges)
        if path is None:
            if expected_forward is not None:
                return _empty_result(
                    "weighted_route_reachability_mismatch",
                    neighborhood_verified=True,
                    graph_verified=True,
                )
            weighted_state = "no_observed_route_in_assessed_graph"
            route_hops = None
            mean_weight = None
            bottleneck_edge = None
            zone_counts = {zone: 0 for zone in ZONE_WEIGHTS}
            path_samples: list[str] = []
            path_truncated = False
            extra_hops = None
        else:
            route_hops = len(path) - 1
            if route_hops < 1 or bottleneck is None:
                return _empty_result(
                    "weighted_route_shape_invalid",
                    neighborhood_verified=True,
                    graph_verified=True,
                )
            route_edges = [
                edges[(path[index], path[index + 1])]
                for index in range(route_hops)
            ]
            edge_weights = [float(edge["weight"]) for edge in route_edges]
            mean_weight = round(sum(edge_weights) / len(edge_weights), 6)
            min_weight = min(edge_weights)
            if round(float(bottleneck), 6) != round(min_weight, 6):
                return _empty_result(
                    "weighted_route_bottleneck_mismatch",
                    neighborhood_verified=True,
                    graph_verified=True,
                )
            bottleneck_rows = []
            zone_counts = {zone: 0 for zone in ZONE_WEIGHTS}
            for index, edge in enumerate(route_edges):
                zone = str(edge.get("strongest_zone") or "").strip().lower()
                zone_counts[zone] += 1
                if float(edge["weight"]) == min_weight:
                    bottleneck_rows.append(
                        {
                            "source_url": path[index],
                            "target_url": path[index + 1],
                            "strongest_zone": zone,
                            "weight": round(float(edge["weight"]), 6),
                        }
                    )
            bottleneck_rows.sort(
                key=lambda row: (
                    row["source_url"],
                    row["target_url"],
                    row["strongest_zone"],
                )
            )
            bottleneck_edge = bottleneck_rows[0]
            weighted_state = "widest_route_observed_in_assessed_graph"
            path_samples, path_truncated = _route_url_samples(path)
            extra_hops = route_hops - int(expected_forward or 0)
            if extra_hops < 0:
                return _empty_result(
                    "weighted_route_shorter_than_shortest_path",
                    neighborhood_verified=True,
                    graph_verified=True,
                )

        row = dict(candidate)
        row.update(
            {
                "observed_weighted_route_state": weighted_state,
                "observed_widest_path_hops": route_hops,
                "observed_widest_path_bottleneck_weight": (
                    round(float(bottleneck), 6)
                    if bottleneck is not None
                    else None
                ),
                "observed_widest_path_mean_edge_weight": mean_weight,
                "observed_widest_path_extra_hops_vs_shortest": extra_hops,
                "observed_widest_path_bottleneck_edge": bottleneck_edge,
                "observed_widest_path_zone_edge_counts": zone_counts,
                "observed_widest_path_url_samples": path_samples,
                "observed_widest_path_url_samples_truncated": path_truncated,
                "weighted_route_evidence_scope": WEIGHTED_ROUTE_EVIDENCE_SCOPE,
                "sitewide_reachability_claim": False,
                "sitewide_orphan_claim": False,
            }
        )
        enriched.append(row)

    return {
        "version": WEIGHTED_ROUTE_CONTEXTUAL_OPPORTUNITY_VERSION,
        "scope": EVIDENCE_SCOPE,
        "state": "candidate" if enriched else "no_candidate_observed",
        "reason": "validated",
        "graph_neighborhood_integrity_state": "verified",
        "graph_integrity_state": "verified",
        "graph_neighborhood_contextual_opportunity_version": (
            GRAPH_NEIGHBORHOOD_CONTEXTUAL_OPPORTUNITY_VERSION
        ),
        "candidate_count": candidate_count,
        "candidates": enriched,
        "candidates_truncated": truncated,
        "weighted_route_evaluated_candidate_count": len(enriched),
        "weighted_route_candidate_population_complete": not truncated,
        "weighted_route_evidence_scope": WEIGHTED_ROUTE_EVIDENCE_SCOPE,
        "sitewide_reachability_claim": False,
        "sitewide_orphan_claim": False,
        "sitewide_link_absence_claim": False,
        "sitewide_template_flow_claim": False,
        "sitewide_link_distribution_claim": False,
        "customer_fix_created": False,
    }
