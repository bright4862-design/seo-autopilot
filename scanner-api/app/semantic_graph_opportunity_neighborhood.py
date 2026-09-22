"""Assessed-graph route evidence for source→target internal-link opportunities.

This Lane-B helper binds already-verified raw-zone contextual-link candidates to the
weighted directed graph that produced their link-presence evidence. It measures
only routes observed inside the assessed graph. It performs no crawl, model, or
provider work, creates no customer Fix, and never upgrades assessed-sample route
absence into a sitewide reachability/orphan claim.
"""
from __future__ import annotations

from collections import deque
from typing import Any

from .semantic_graph import _url
from .semantic_graph_contextual import EVIDENCE_SCOPE, _validated_graph
from .semantic_graph_template_zone_opportunity import (
    RAW_ZONE_TEMPLATE_CONTEXTUAL_OPPORTUNITY_VERSION,
)


GRAPH_NEIGHBORHOOD_CONTEXTUAL_OPPORTUNITY_VERSION = (
    "template_contextual_internal_link_opportunity_v3_graph_neighborhood_bound"
)
MAX_BRIDGE_SAMPLES = 8


def _empty_result(
    reason: str,
    *,
    raw_zone_verified: bool = False,
    graph_verified: bool = False,
) -> dict[str, Any]:
    return {
        "version": GRAPH_NEIGHBORHOOD_CONTEXTUAL_OPPORTUNITY_VERSION,
        "scope": EVIDENCE_SCOPE,
        "state": "not_verified",
        "reason": reason,
        "raw_zone_opportunity_integrity_state": (
            "verified" if raw_zone_verified else "not_verified"
        ),
        "graph_integrity_state": "verified" if graph_verified else "not_verified",
        "candidate_count": 0,
        "candidates": [],
        "candidates_truncated": False,
        "observed_route_scan_complete": False,
        "route_evidence_scope": "assessed_internal_graph_only",
        "sitewide_reachability_claim": False,
        "sitewide_orphan_claim": False,
        "sitewide_link_absence_claim": False,
        "sitewide_template_flow_claim": False,
        "sitewide_link_distribution_claim": False,
        "customer_fix_created": False,
    }


def _strict_non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _validated_raw_zone_opportunities(
    evidence: dict[str, Any],
) -> tuple[list[dict[str, Any]], int, bool, str | None]:
    if (
        not isinstance(evidence, dict)
        or evidence.get("version") != RAW_ZONE_TEMPLATE_CONTEXTUAL_OPPORTUNITY_VERSION
    ):
        return [], 0, False, "raw_zone_opportunity_version_mismatch"
    if evidence.get("scope") != EVIDENCE_SCOPE:
        return [], 0, False, "raw_zone_opportunity_scope_mismatch"
    if evidence.get("state") == "not_verified":
        return [], 0, False, "raw_zone_opportunity_not_verified"
    if evidence.get("template_contextual_opportunity_integrity_state") != "verified":
        return [], 0, False, "raw_zone_contextual_integrity_not_verified"
    if evidence.get("template_zone_flow_integrity_state") != "verified":
        return [], 0, False, "raw_zone_flow_integrity_not_verified"
    for field in (
        "sitewide_link_absence_claim",
        "sitewide_template_flow_claim",
        "sitewide_link_distribution_claim",
        "customer_fix_created",
    ):
        if evidence.get(field) is not False:
            return [], 0, False, f"raw_zone_{field}_invalid"

    candidates = evidence.get("candidates")
    candidate_count = _strict_non_negative_int(evidence.get("candidate_count"))
    truncated = evidence.get("candidates_truncated")
    if (
        not isinstance(candidates, list)
        or candidate_count is None
        or not isinstance(truncated, bool)
    ):
        return [], 0, False, "raw_zone_opportunity_shape_invalid"
    if candidate_count < len(candidates):
        return [], 0, False, "raw_zone_opportunity_count_invalid"
    if truncated != (candidate_count > len(candidates)):
        return [], 0, False, "raw_zone_opportunity_truncation_mismatch"
    expected_state = "candidate" if candidates else "no_candidate_observed"
    if evidence.get("state") != expected_state:
        return [], 0, False, "raw_zone_opportunity_state_mismatch"

    seen: set[tuple[str, str]] = set()
    validated: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            return [], 0, False, "raw_zone_candidate_invalid"
        source = _url(candidate.get("source_url"))
        target = _url(candidate.get("target_url"))
        key = (source, target)
        if not source or not target or source == target or key in seen:
            return [], 0, False, "raw_zone_candidate_identity_invalid"
        seen.add(key)
        if candidate.get("evidence_scope") != EVIDENCE_SCOPE:
            return [], 0, False, "raw_zone_candidate_scope_mismatch"
        if candidate.get("sitewide_link_absence_claim") is not False:
            return [], 0, False, "raw_zone_candidate_sitewide_link_claim_invalid"
        if candidate.get("sitewide_template_flow_claim") is not False:
            return [], 0, False, "raw_zone_candidate_sitewide_flow_claim_invalid"
        if candidate.get("sitewide_link_distribution_claim") is not False:
            return [], 0, False, "raw_zone_candidate_sitewide_distribution_claim_invalid"
        if not isinstance(candidate.get("observed_edge_present"), bool):
            return [], 0, False, "raw_zone_candidate_edge_presence_invalid"
        if candidate.get("observed_contextual_edge_present") is not False:
            return [], 0, False, "raw_zone_candidate_contextual_presence_invalid"

        existing_zone = candidate.get("existing_strongest_zone")
        if candidate["observed_edge_present"]:
            zone = str(existing_zone or "").strip().lower()
            if not zone or zone == "contextual":
                return [], 0, False, "raw_zone_candidate_existing_zone_invalid"
            if candidate.get("reason") != "existing_non_contextual_edge_contextual_upgrade":
                return [], 0, False, "raw_zone_candidate_reason_mismatch"
        else:
            if existing_zone not in (None, ""):
                return [], 0, False, "raw_zone_candidate_existing_zone_mismatch"
            if candidate.get("reason") != "no_observed_edge_in_assessed_sample":
                return [], 0, False, "raw_zone_candidate_reason_mismatch"
        validated.append(candidate)
    return validated, candidate_count, truncated, None


def _graph_node_urls(graph: dict[str, Any]) -> set[str]:
    rows = graph.get("nodes") if isinstance(graph, dict) else None
    if not isinstance(rows, list):
        return set()
    return {
        url
        for row in rows
        if isinstance(row, dict)
        for url in [_url(row.get("url"))]
        if url
    }


def _shortest_path_hops(
    source: str,
    target: str,
    out_neighbours: dict[str, set[str]],
) -> int | None:
    if source == target:
        return 0
    queue: deque[tuple[str, int]] = deque([(source, 0)])
    seen = {source}
    while queue:
        current, hops = queue.popleft()
        for neighbour in sorted(out_neighbours.get(current, set())):
            if neighbour == target:
                return hops + 1
            if neighbour in seen:
                continue
            seen.add(neighbour)
            queue.append((neighbour, hops + 1))
    return None


def graph_neighborhood_internal_link_opportunities(
    raw_zone_opportunities: dict[str, Any],
    graph: dict[str, Any],
) -> dict[str, Any]:
    """Bind contextual candidates to deterministic assessed-graph route evidence."""
    candidates, candidate_count, truncated, raw_error = (
        _validated_raw_zone_opportunities(raw_zone_opportunities)
    )
    if raw_error:
        return _empty_result(raw_error)

    page_urls = _graph_node_urls(graph)
    edges, nodes, graph_error = _validated_graph(page_urls, graph)
    if graph_error:
        return _empty_result(graph_error, raw_zone_verified=True)
    if graph.get("sitewide_orphan_claim") is not False:
        return _empty_result(
            "graph_sitewide_orphan_claim_invalid",
            raw_zone_verified=True,
        )
    if any(row.get("sitewide_orphan_claim") is not False for row in nodes.values()):
        return _empty_result(
            "graph_node_sitewide_orphan_claim_invalid",
            raw_zone_verified=True,
        )

    out_neighbours: dict[str, set[str]] = {url: set() for url in nodes}
    in_neighbours: dict[str, set[str]] = {url: set() for url in nodes}
    for source, target in edges:
        out_neighbours[source].add(target)
        in_neighbours[target].add(source)

    enriched: list[dict[str, Any]] = []
    for candidate in candidates:
        source = _url(candidate.get("source_url"))
        target = _url(candidate.get("target_url"))
        if source not in nodes or target not in nodes:
            return _empty_result(
                "opportunity_graph_population_mismatch",
                raw_zone_verified=True,
                graph_verified=True,
            )

        direct_edge = edges.get((source, target))
        direct_present = direct_edge is not None
        if candidate.get("observed_edge_present") is not direct_present:
            return _empty_result(
                "opportunity_graph_edge_presence_mismatch",
                raw_zone_verified=True,
                graph_verified=True,
            )
        if direct_edge is not None:
            graph_zone = str(direct_edge.get("strongest_zone") or "").strip().lower()
            candidate_zone = str(candidate.get("existing_strongest_zone") or "").strip().lower()
            if candidate_zone != graph_zone:
                return _empty_result(
                    "opportunity_graph_edge_zone_mismatch",
                    raw_zone_verified=True,
                    graph_verified=True,
                )

        forward_hops = _shortest_path_hops(source, target, out_neighbours)
        reverse_hops = _shortest_path_hops(target, source, out_neighbours)
        bridge_urls = sorted(out_neighbours[source] & in_neighbours[target])
        bridges: list[dict[str, Any]] = []
        for bridge in bridge_urls:
            left = edges[(source, bridge)]
            right = edges[(bridge, target)]
            bottleneck = round(min(float(left["weight"]), float(right["weight"])), 6)
            bridges.append(
                {
                    "url": bridge,
                    "bottleneck_weight": bottleneck,
                    "source_to_bridge_weight": round(float(left["weight"]), 6),
                    "bridge_to_target_weight": round(float(right["weight"]), 6),
                }
            )
        bridges.sort(key=lambda row: (-row["bottleneck_weight"], row["url"]))
        sampled_bridges = bridges[:MAX_BRIDGE_SAMPLES]

        row = dict(candidate)
        row.update(
            {
                "observed_directed_shortest_path_hops": forward_hops,
                "observed_reverse_shortest_path_hops": reverse_hops,
                "observed_graph_route_state": (
                    "reachable_in_assessed_graph"
                    if forward_hops is not None
                    else "no_observed_route_in_assessed_graph"
                ),
                "observed_reverse_graph_route_state": (
                    "reachable_in_assessed_graph"
                    if reverse_hops is not None
                    else "no_observed_route_in_assessed_graph"
                ),
                "observed_two_hop_bridge_count": len(bridges),
                "observed_two_hop_bridges": sampled_bridges,
                "observed_two_hop_bridges_truncated": len(bridges) > len(sampled_bridges),
                "observed_two_hop_bridge_max_bottleneck_weight": (
                    bridges[0]["bottleneck_weight"] if bridges else None
                ),
                "observed_shared_out_neighbour_count": len(
                    out_neighbours[source] & out_neighbours[target]
                ),
                "observed_shared_in_neighbour_count": len(
                    in_neighbours[source] & in_neighbours[target]
                ),
                "observed_route_scan_complete": True,
                "route_evidence_scope": "assessed_internal_graph_only",
                "sitewide_reachability_claim": False,
                "sitewide_orphan_claim": False,
            }
        )
        enriched.append(row)

    return {
        "version": GRAPH_NEIGHBORHOOD_CONTEXTUAL_OPPORTUNITY_VERSION,
        "scope": EVIDENCE_SCOPE,
        "state": "candidate" if enriched else "no_candidate_observed",
        "reason": "validated",
        "raw_zone_opportunity_integrity_state": "verified",
        "graph_integrity_state": "verified",
        "raw_zone_opportunity_version": RAW_ZONE_TEMPLATE_CONTEXTUAL_OPPORTUNITY_VERSION,
        "candidate_count": candidate_count,
        "candidates": enriched,
        "candidates_truncated": truncated,
        "observed_route_scan_complete": True,
        "route_evidence_scope": "assessed_internal_graph_only",
        "sitewide_reachability_claim": False,
        "sitewide_orphan_claim": False,
        "sitewide_link_absence_claim": False,
        "sitewide_template_flow_claim": False,
        "sitewide_link_distribution_claim": False,
        "customer_fix_created": False,
    }
