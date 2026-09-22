"""Weighted semantic-cluster link-flow evidence for the assessed page graph.

This Lane-B helper collapses an already-validated weighted page graph onto the
already-validated semantic-cluster profile. It performs no crawl, model/provider
work, persistence, ranking, customer Fix creation, or sitewide reachability/
coverage inference. Strongest-zone fields reflect the reduced graph edge's
strongest observed zone; they are not a raw occurrence distribution.
"""
from __future__ import annotations

from collections import defaultdict
from math import isfinite
from typing import Any

from .semantic_graph import GRAPH_EVIDENCE_VERSION
from .semantic_graph_cluster_profile import SEMANTIC_CLUSTER_PROFILE_VERSION


SEMANTIC_CLUSTER_LINK_FLOW_VERSION = "semantic_cluster_link_flow_v1_weighted_graph_bound"
EVIDENCE_SCOPE = "observed_assessed_pages_only"
MAX_FLOW_EDGE_SAMPLES = 8
_ALLOWED_ZONES = {
    "contextual",
    "listing",
    "aside",
    "navigation",
    "header",
    "footer",
    "facet",
    "unknown",
}


def _empty_result(reason: str, *, graph_verified: bool = False) -> dict[str, Any]:
    return {
        "version": SEMANTIC_CLUSTER_LINK_FLOW_VERSION,
        "scope": EVIDENCE_SCOPE,
        "state": "not_verified",
        "reason": reason,
        "graph_integrity_state": "verified" if graph_verified else "not_verified",
        "semantic_cluster_profile_integrity_state": "not_verified",
        "cluster_count": 0,
        "clustered_page_count": 0,
        "graph_edge_count": 0,
        "clustered_endpoint_edge_count": 0,
        "intra_cluster_edge_count": 0,
        "inter_cluster_edge_count": 0,
        "unclustered_endpoint_edge_count": 0,
        "cluster_flows": [],
        "cluster_summaries": [],
        "semantic_vector_coverage_state": "not_verified",
        "semantic_pair_population_complete": False,
        "sitewide_semantic_coverage_claim": False,
        "sitewide_reachability_claim": False,
        "sitewide_orphan_claim": False,
        "sitewide_link_absence_claim": False,
        "sitewide_link_distribution_claim": False,
        "customer_fix_created": False,
    }


def _strict_non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _strict_positive_int(value: Any) -> int | None:
    parsed = _strict_non_negative_int(value)
    if parsed is None or parsed < 1:
        return None
    return parsed


def _finite_non_negative_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    parsed = float(value)
    if not isfinite(parsed) or parsed < 0.0:
        return None
    return parsed


def _validated_graph(
    evidence: Any,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], str | None]:
    if not isinstance(evidence, dict):
        return {}, [], "graph_evidence_invalid"
    if evidence.get("version") != GRAPH_EVIDENCE_VERSION:
        return {}, [], "graph_version_mismatch"
    if evidence.get("scope") != EVIDENCE_SCOPE:
        return {}, [], "graph_scope_mismatch"
    if evidence.get("sitewide_orphan_claim") is not False:
        return {}, [], "graph_sitewide_orphan_claim_invalid"

    skipped_external = _strict_non_negative_int(evidence.get("skipped_external_links"))
    skipped_unassessed = _strict_non_negative_int(evidence.get("skipped_unassessed_targets"))
    nodes = evidence.get("nodes")
    edges = evidence.get("edges")
    if (
        skipped_external is None
        or skipped_unassessed is None
        or not isinstance(nodes, list)
        or not isinstance(edges, list)
    ):
        return {}, [], "graph_shape_invalid"

    node_map: dict[str, dict[str, Any]] = {}
    for node in nodes:
        if not isinstance(node, dict):
            return {}, [], "graph_node_invalid"
        url = node.get("url")
        in_count = _strict_non_negative_int(node.get("observed_in_edge_count"))
        out_count = _strict_non_negative_int(node.get("observed_out_edge_count"))
        weighted_in = _finite_non_negative_float(node.get("weighted_in"))
        weighted_out = _finite_non_negative_float(node.get("weighted_out"))
        if (
            not isinstance(url, str)
            or not url
            or url in node_map
            or in_count is None
            or out_count is None
            or weighted_in is None
            or weighted_out is None
            or node.get("sitewide_orphan_claim") is not False
        ):
            return {}, [], "graph_node_invalid"
        node_map[url] = node

    seen_edges: set[tuple[str, str]] = set()
    in_count_actual: dict[str, int] = defaultdict(int)
    out_count_actual: dict[str, int] = defaultdict(int)
    weighted_in_actual: dict[str, float] = defaultdict(float)
    weighted_out_actual: dict[str, float] = defaultdict(float)
    validated_edges: list[dict[str, Any]] = []
    for edge in edges:
        if not isinstance(edge, dict):
            return {}, [], "graph_edge_invalid"
        source = edge.get("source_url")
        target = edge.get("target_url")
        occurrences = _strict_positive_int(edge.get("observed_occurrences"))
        weight = _finite_non_negative_float(edge.get("weight"))
        confidence = _finite_non_negative_float(edge.get("zone_confidence"))
        zone = edge.get("strongest_zone")
        anchor_terms = edge.get("anchor_terms")
        key = (source, target)
        if (
            not isinstance(source, str)
            or not source
            or not isinstance(target, str)
            or not target
            or source == target
            or source not in node_map
            or target not in node_map
            or key in seen_edges
            or occurrences is None
            or weight is None
            or confidence is None
            or confidence > 1.0
            or zone not in _ALLOWED_ZONES
            or not isinstance(anchor_terms, list)
        ):
            return {}, [], "graph_edge_invalid"
        if any(not isinstance(term, str) or not term for term in anchor_terms):
            return {}, [], "graph_edge_anchor_terms_invalid"
        seen_edges.add(key)
        in_count_actual[target] += 1
        out_count_actual[source] += 1
        weighted_in_actual[target] += weight
        weighted_out_actual[source] += weight
        validated_edges.append(edge)

    for url, node in node_map.items():
        if node["observed_in_edge_count"] != in_count_actual[url]:
            return {}, [], "graph_node_in_edge_count_mismatch"
        if node["observed_out_edge_count"] != out_count_actual[url]:
            return {}, [], "graph_node_out_edge_count_mismatch"
        if abs(float(node["weighted_in"]) - round(weighted_in_actual[url], 6)) > 1e-6:
            return {}, [], "graph_node_weighted_in_mismatch"
        if abs(float(node["weighted_out"]) - round(weighted_out_actual[url], 6)) > 1e-6:
            return {}, [], "graph_node_weighted_out_mismatch"

    return node_map, validated_edges, None


def _validated_cluster_profiles(
    evidence: Any,
    graph_nodes: dict[str, dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, str], str | None]:
    if not isinstance(evidence, dict):
        return {}, {}, "semantic_cluster_profile_evidence_invalid"
    if evidence.get("version") != SEMANTIC_CLUSTER_PROFILE_VERSION:
        return {}, {}, "semantic_cluster_profile_version_mismatch"
    if evidence.get("scope") != EVIDENCE_SCOPE:
        return {}, {}, "semantic_cluster_profile_scope_mismatch"
    if evidence.get("state") == "not_verified":
        return {}, {}, "semantic_cluster_profile_not_verified"
    if evidence.get("state") not in {"verified", "partial", "no_cluster_observed"}:
        return {}, {}, "semantic_cluster_profile_state_invalid"
    if evidence.get("sitewide_semantic_coverage_claim") is not False:
        return {}, {}, "semantic_cluster_profile_sitewide_semantic_coverage_claim_invalid"
    if evidence.get("customer_fix_created") is not False:
        return {}, {}, "semantic_cluster_profile_customer_fix_created_invalid"

    cluster_count = _strict_non_negative_int(evidence.get("cluster_count"))
    profile_count = _strict_non_negative_int(evidence.get("profile_count"))
    profiles = evidence.get("profiles")
    if cluster_count is None or profile_count is None or not isinstance(profiles, list):
        return {}, {}, "semantic_cluster_profile_shape_invalid"
    if cluster_count != profile_count or profile_count != len(profiles):
        return {}, {}, "semantic_cluster_profile_count_mismatch"
    if evidence.get("state") == "no_cluster_observed":
        if profiles:
            return {}, {}, "semantic_cluster_profile_state_mismatch"
        return {}, {}, None
    if not profiles:
        return {}, {}, "semantic_cluster_profile_state_mismatch"

    by_cluster: dict[str, dict[str, Any]] = {}
    membership: dict[str, str] = {}
    verified_profiles = 0
    for profile in profiles:
        if not isinstance(profile, dict):
            return {}, {}, "semantic_cluster_profile_row_invalid"
        cluster_id = profile.get("cluster_id")
        urls = profile.get("urls")
        page_count = _strict_non_negative_int(profile.get("page_count"))
        state = profile.get("state")
        if (
            not isinstance(cluster_id, str)
            or not cluster_id
            or cluster_id in by_cluster
            or not isinstance(urls, list)
            or page_count is None
            or state not in {"verified", "not_verified"}
        ):
            return {}, {}, "semantic_cluster_profile_row_invalid"
        if page_count < 2 or page_count != len(urls):
            return {}, {}, "semantic_cluster_profile_page_count_mismatch"
        if any(not isinstance(url, str) or not url or url not in graph_nodes for url in urls):
            return {}, {}, "semantic_cluster_profile_member_outside_graph"
        if len(set(urls)) != len(urls) or any(url in membership for url in urls):
            return {}, {}, "semantic_cluster_profile_member_overlap"

        representative = profile.get("representative_url")
        if state == "verified":
            verified_profiles += 1
            if not isinstance(representative, str) or representative not in urls:
                return {}, {}, "semantic_cluster_profile_representative_invalid"
        elif representative is not None:
            return {}, {}, "semantic_cluster_profile_representative_invalid"

        canonical = dict(profile)
        canonical["urls"] = sorted(urls)
        by_cluster[cluster_id] = canonical
        for url in urls:
            membership[url] = cluster_id

    expected_state = (
        "verified"
        if verified_profiles == len(profiles)
        else "partial"
        if verified_profiles
        else "not_verified"
    )
    if evidence.get("state") != expected_state:
        return {}, {}, "semantic_cluster_profile_state_mismatch"
    return by_cluster, membership, None


def semantic_cluster_link_flow(
    graph: dict[str, Any],
    semantic_cluster_profile: dict[str, Any],
) -> dict[str, Any]:
    """Collapse weighted assessed-page edges into deterministic semantic-cluster flow."""
    graph_nodes, edges, graph_error = _validated_graph(graph)
    if graph_error:
        return _empty_result(graph_error)

    profiles, membership, profile_error = _validated_cluster_profiles(
        semantic_cluster_profile,
        graph_nodes,
    )
    if profile_error:
        return _empty_result(profile_error, graph_verified=True)

    flow_acc: dict[tuple[str, str], dict[str, Any]] = {}
    summary_acc: dict[str, dict[str, Any]] = {
        cluster_id: {
            "internal_edges": 0,
            "internal_weight": 0.0,
            "outbound_edges": 0,
            "outbound_weight": 0.0,
            "inbound_edges": 0,
            "inbound_weight": 0.0,
            "outbound_clusters": set(),
            "inbound_clusters": set(),
        }
        for cluster_id in profiles
    }
    clustered_endpoint_edge_count = 0
    intra_cluster_edge_count = 0
    inter_cluster_edge_count = 0
    unclustered_endpoint_edge_count = 0

    for edge in edges:
        source_cluster = membership.get(edge["source_url"])
        target_cluster = membership.get(edge["target_url"])
        if not source_cluster or not target_cluster:
            unclustered_endpoint_edge_count += 1
            continue

        clustered_endpoint_edge_count += 1
        relation = "intra_cluster" if source_cluster == target_cluster else "inter_cluster"
        if relation == "intra_cluster":
            intra_cluster_edge_count += 1
        else:
            inter_cluster_edge_count += 1

        key = (source_cluster, target_cluster)
        acc = flow_acc.get(key)
        if acc is None:
            acc = {
                "relation": relation,
                "edges": [],
                "edge_count": 0,
                "occurrence_count": 0,
                "weighted_strength": 0.0,
                "occurrence_weighted_strength": 0.0,
                "zone_edge_counts": defaultdict(int),
            }
            flow_acc[key] = acc
        acc["edges"].append(edge)
        acc["edge_count"] += 1
        acc["occurrence_count"] += edge["observed_occurrences"]
        acc["weighted_strength"] += float(edge["weight"])
        acc["occurrence_weighted_strength"] += float(edge["weight"]) * edge["observed_occurrences"]
        acc["zone_edge_counts"][edge["strongest_zone"]] += 1

        if relation == "intra_cluster":
            summary_acc[source_cluster]["internal_edges"] += 1
            summary_acc[source_cluster]["internal_weight"] += float(edge["weight"])
        else:
            summary_acc[source_cluster]["outbound_edges"] += 1
            summary_acc[source_cluster]["outbound_weight"] += float(edge["weight"])
            summary_acc[source_cluster]["outbound_clusters"].add(target_cluster)
            summary_acc[target_cluster]["inbound_edges"] += 1
            summary_acc[target_cluster]["inbound_weight"] += float(edge["weight"])
            summary_acc[target_cluster]["inbound_clusters"].add(source_cluster)

    cluster_flows: list[dict[str, Any]] = []
    for source_cluster, target_cluster in sorted(flow_acc):
        acc = flow_acc[(source_cluster, target_cluster)]
        ordered_edges = sorted(
            acc["edges"],
            key=lambda edge: (-float(edge["weight"]), edge["source_url"], edge["target_url"]),
        )
        weights = [float(edge["weight"]) for edge in acc["edges"]]
        strongest = ordered_edges[0]
        cluster_flows.append(
            {
                "source_cluster_id": source_cluster,
                "target_cluster_id": target_cluster,
                "relation": acc["relation"],
                "edge_count": acc["edge_count"],
                "occurrence_count": acc["occurrence_count"],
                "weighted_strength": round(acc["weighted_strength"], 6),
                "occurrence_weighted_strength": round(acc["occurrence_weighted_strength"], 6),
                "min_edge_weight": round(min(weights), 6),
                "mean_edge_weight": round(sum(weights) / len(weights), 6),
                "max_edge_weight": round(max(weights), 6),
                "strongest_zone_edge_counts": {
                    zone: acc["zone_edge_counts"][zone]
                    for zone in sorted(acc["zone_edge_counts"])
                },
                "strongest_edge": {
                    "source_url": strongest["source_url"],
                    "target_url": strongest["target_url"],
                    "weight": round(float(strongest["weight"]), 6),
                    "strongest_zone": strongest["strongest_zone"],
                    "observed_occurrences": strongest["observed_occurrences"],
                },
                "edge_samples": [
                    {
                        "source_url": edge["source_url"],
                        "target_url": edge["target_url"],
                        "weight": round(float(edge["weight"]), 6),
                        "strongest_zone": edge["strongest_zone"],
                        "observed_occurrences": edge["observed_occurrences"],
                    }
                    for edge in ordered_edges[:MAX_FLOW_EDGE_SAMPLES]
                ],
                "edge_samples_truncated": len(ordered_edges) > MAX_FLOW_EDGE_SAMPLES,
                "evidence_scope": EVIDENCE_SCOPE,
                "sitewide_link_distribution_claim": False,
            }
        )

    cluster_summaries: list[dict[str, Any]] = []
    for cluster_id in sorted(profiles):
        profile = profiles[cluster_id]
        acc = summary_acc[cluster_id]
        cluster_summaries.append(
            {
                "cluster_id": cluster_id,
                "profile_state": profile["state"],
                "page_count": profile["page_count"],
                "representative_url": profile.get("representative_url"),
                "observed_internal_edge_count": acc["internal_edges"],
                "observed_internal_weighted_strength": round(acc["internal_weight"], 6),
                "observed_outbound_cross_cluster_edge_count": acc["outbound_edges"],
                "observed_outbound_cross_cluster_weighted_strength": round(acc["outbound_weight"], 6),
                "observed_outbound_target_cluster_count": len(acc["outbound_clusters"]),
                "observed_inbound_cross_cluster_edge_count": acc["inbound_edges"],
                "observed_inbound_cross_cluster_weighted_strength": round(acc["inbound_weight"], 6),
                "observed_inbound_source_cluster_count": len(acc["inbound_clusters"]),
                "evidence_scope": EVIDENCE_SCOPE,
                "sitewide_reachability_claim": False,
                "sitewide_orphan_claim": False,
                "sitewide_link_absence_claim": False,
            }
        )

    profile_state = semantic_cluster_profile.get("state")
    if not profiles:
        state = "no_cluster_observed"
    elif cluster_flows:
        state = "flow_observed"
    else:
        state = "no_cluster_flow_observed"

    return {
        "version": SEMANTIC_CLUSTER_LINK_FLOW_VERSION,
        "scope": EVIDENCE_SCOPE,
        "state": state,
        "reason": "validated",
        "graph_integrity_state": "verified",
        "semantic_cluster_profile_integrity_state": "verified",
        "semantic_cluster_profile_state": profile_state,
        "cluster_count": len(profiles),
        "clustered_page_count": len(membership),
        "graph_edge_count": len(edges),
        "clustered_endpoint_edge_count": clustered_endpoint_edge_count,
        "intra_cluster_edge_count": intra_cluster_edge_count,
        "inter_cluster_edge_count": inter_cluster_edge_count,
        "unclustered_endpoint_edge_count": unclustered_endpoint_edge_count,
        "cluster_flows": cluster_flows,
        "cluster_summaries": cluster_summaries,
        "semantic_vector_coverage_state": semantic_cluster_profile.get(
            "semantic_vector_coverage_state", "not_verified"
        ),
        "semantic_pair_population_complete": bool(
            semantic_cluster_profile.get("semantic_pair_population_complete")
        ),
        "sitewide_semantic_coverage_claim": False,
        "sitewide_reachability_claim": False,
        "sitewide_orphan_claim": False,
        "sitewide_link_absence_claim": False,
        "sitewide_link_distribution_claim": False,
        "customer_fix_created": False,
    }
