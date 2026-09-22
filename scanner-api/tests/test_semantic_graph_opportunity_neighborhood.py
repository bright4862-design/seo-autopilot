from copy import deepcopy

from app.semantic_graph import build_weighted_internal_link_graph
from app.semantic_graph_opportunity_neighborhood import (
    GRAPH_NEIGHBORHOOD_CONTEXTUAL_OPPORTUNITY_VERSION,
    graph_neighborhood_internal_link_opportunities,
)


def page(url):
    return {
        "url": url,
        "status_code": 200,
        "page_evidence_class": "usable_html",
        "indexable": True,
    }


def nav_link(source, target, anchor="Guide"):
    return {
        "source_url": source,
        "target_url": target,
        "anchor_text": anchor,
        "ancestor_tags": ["a", "nav"],
        "ancestor_roles": ["navigation"],
    }


def contextual_link(source, target, anchor="Related guide"):
    return {
        "source_url": source,
        "target_url": target,
        "anchor_text": anchor,
        "ancestor_tags": ["a", "article", "main"],
        "ancestor_roles": ["article", "main"],
    }


def raw_zone_candidate(
    source,
    target,
    *,
    observed_edge_present=False,
    existing_strongest_zone=None,
):
    return {
        "version": "template_contextual_internal_link_opportunity_v2_raw_zone_bound",
        "scope": "observed_assessed_pages_only",
        "state": "candidate",
        "reason": "validated",
        "template_contextual_opportunity_integrity_state": "verified",
        "template_zone_flow_integrity_state": "verified",
        "candidate_count": 1,
        "candidates_truncated": False,
        "sitewide_link_absence_claim": False,
        "sitewide_template_flow_claim": False,
        "sitewide_link_distribution_claim": False,
        "customer_fix_created": False,
        "candidates": [
            {
                "source_url": source,
                "target_url": target,
                "observed_edge_present": observed_edge_present,
                "observed_contextual_edge_present": False,
                "existing_strongest_zone": existing_strongest_zone,
                "reason": (
                    "existing_non_contextual_edge_contextual_upgrade"
                    if observed_edge_present
                    else "no_observed_edge_in_assessed_sample"
                ),
                "evidence_scope": "observed_assessed_pages_only",
                "sitewide_link_absence_claim": False,
                "sitewide_template_flow_claim": False,
                "sitewide_link_distribution_claim": False,
            }
        ],
    }


def row(result):
    return result["candidates"][0]


def test_graph_neighborhood_measures_two_hop_bridge_without_sitewide_claim():
    source = "https://e.test/source"
    bridge = "https://e.test/bridge"
    target = "https://e.test/target"
    pages = [page(source), page(bridge), page(target)]
    graph = build_weighted_internal_link_graph(
        pages,
        [nav_link(source, bridge), nav_link(bridge, target)],
    )

    result = graph_neighborhood_internal_link_opportunities(
        raw_zone_candidate(source, target),
        graph,
    )

    assert result["version"] == GRAPH_NEIGHBORHOOD_CONTEXTUAL_OPPORTUNITY_VERSION
    assert result["state"] == "candidate"
    candidate = row(result)
    assert candidate["observed_directed_shortest_path_hops"] == 2
    assert candidate["observed_graph_route_state"] == "reachable_in_assessed_graph"
    assert candidate["observed_two_hop_bridge_count"] == 1
    assert candidate["observed_two_hop_bridges"][0]["url"] == bridge
    assert candidate["observed_two_hop_bridge_max_bottleneck_weight"] > 0.0
    assert candidate["sitewide_reachability_claim"] is False
    assert candidate["sitewide_orphan_claim"] is False
    assert result["sitewide_link_absence_claim"] is False
    assert result["customer_fix_created"] is False


def test_graph_neighborhood_measures_longer_directed_route_without_inventing_bridge():
    urls = [f"https://e.test/{name}" for name in ("source", "a", "b", "target")]
    source, a, b, target = urls
    graph = build_weighted_internal_link_graph(
        [page(url) for url in urls],
        [nav_link(source, a), nav_link(a, b), nav_link(b, target)],
    )

    result = graph_neighborhood_internal_link_opportunities(
        raw_zone_candidate(source, target),
        graph,
    )

    candidate = row(result)
    assert candidate["observed_directed_shortest_path_hops"] == 3
    assert candidate["observed_two_hop_bridge_count"] == 0
    assert candidate["observed_two_hop_bridges"] == []
    assert candidate["observed_two_hop_bridge_max_bottleneck_weight"] is None


def test_graph_neighborhood_keeps_missing_route_sample_scoped():
    source = "https://e.test/source"
    target = "https://e.test/target"
    graph = build_weighted_internal_link_graph([page(source), page(target)], [])

    result = graph_neighborhood_internal_link_opportunities(
        raw_zone_candidate(source, target),
        graph,
    )

    candidate = row(result)
    assert candidate["observed_directed_shortest_path_hops"] is None
    assert candidate["observed_graph_route_state"] == "no_observed_route_in_assessed_graph"
    assert candidate["route_evidence_scope"] == "assessed_internal_graph_only"
    assert result["sitewide_reachability_claim"] is False
    assert result["sitewide_orphan_claim"] is False


def test_graph_neighborhood_measures_reverse_route_independently():
    source = "https://e.test/source"
    bridge = "https://e.test/bridge"
    target = "https://e.test/target"
    graph = build_weighted_internal_link_graph(
        [page(source), page(bridge), page(target)],
        [nav_link(target, bridge), nav_link(bridge, source)],
    )

    result = graph_neighborhood_internal_link_opportunities(
        raw_zone_candidate(source, target),
        graph,
    )

    candidate = row(result)
    assert candidate["observed_directed_shortest_path_hops"] is None
    assert candidate["observed_reverse_shortest_path_hops"] == 2
    assert candidate["observed_reverse_graph_route_state"] == "reachable_in_assessed_graph"


def test_graph_neighborhood_bridge_sample_is_weight_ranked_and_deterministic():
    source = "https://e.test/source"
    weaker = "https://e.test/a-weaker"
    stronger = "https://e.test/z-stronger"
    target = "https://e.test/target"
    graph = build_weighted_internal_link_graph(
        [page(source), page(weaker), page(stronger), page(target)],
        [
            nav_link(source, weaker),
            nav_link(weaker, target),
            contextual_link(source, stronger),
            contextual_link(stronger, target),
        ],
    )

    result = graph_neighborhood_internal_link_opportunities(
        raw_zone_candidate(source, target),
        graph,
    )

    bridges = row(result)["observed_two_hop_bridges"]
    assert [item["url"] for item in bridges] == [stronger, weaker]
    assert bridges[0]["bottleneck_weight"] > bridges[1]["bottleneck_weight"]


def test_graph_neighborhood_preserves_existing_noncontextual_direct_route():
    source = "https://e.test/source"
    target = "https://e.test/target"
    graph = build_weighted_internal_link_graph(
        [page(source), page(target)],
        [nav_link(source, target)],
    )

    result = graph_neighborhood_internal_link_opportunities(
        raw_zone_candidate(
            source,
            target,
            observed_edge_present=True,
            existing_strongest_zone="navigation",
        ),
        graph,
    )

    candidate = row(result)
    assert candidate["observed_directed_shortest_path_hops"] == 1
    assert candidate["observed_graph_route_state"] == "reachable_in_assessed_graph"
    assert candidate["observed_edge_present"] is True
    assert candidate["reason"] == "existing_non_contextual_edge_contextual_upgrade"


def test_graph_neighborhood_rejects_candidate_graph_edge_presence_divergence():
    source = "https://e.test/source"
    target = "https://e.test/target"
    graph = build_weighted_internal_link_graph(
        [page(source), page(target)],
        [nav_link(source, target)],
    )

    result = graph_neighborhood_internal_link_opportunities(
        raw_zone_candidate(source, target),
        graph,
    )

    assert result["state"] == "not_verified"
    assert result["reason"] == "opportunity_graph_edge_presence_mismatch"
    assert result["raw_zone_opportunity_integrity_state"] == "verified"
    assert result["graph_integrity_state"] == "verified"


def test_graph_neighborhood_rejects_candidate_graph_zone_divergence():
    source = "https://e.test/source"
    target = "https://e.test/target"
    graph = build_weighted_internal_link_graph(
        [page(source), page(target)],
        [nav_link(source, target)],
    )

    result = graph_neighborhood_internal_link_opportunities(
        raw_zone_candidate(
            source,
            target,
            observed_edge_present=True,
            existing_strongest_zone="footer",
        ),
        graph,
    )

    assert result["state"] == "not_verified"
    assert result["reason"] == "opportunity_graph_edge_zone_mismatch"


def test_graph_neighborhood_rejects_forged_graph_metrics():
    source = "https://e.test/source"
    bridge = "https://e.test/bridge"
    target = "https://e.test/target"
    graph = build_weighted_internal_link_graph(
        [page(source), page(bridge), page(target)],
        [nav_link(source, bridge), nav_link(bridge, target)],
    )
    forged = deepcopy(graph)
    source_node = next(item for item in forged["nodes"] if item["url"] == source)
    source_node["weighted_out"] += 1.0

    result = graph_neighborhood_internal_link_opportunities(
        raw_zone_candidate(source, target),
        forged,
    )

    assert result["state"] == "not_verified"
    assert result["reason"] == "graph_node_weight_mismatch"
    assert result["raw_zone_opportunity_integrity_state"] == "verified"
    assert result["graph_integrity_state"] == "not_verified"


def test_graph_neighborhood_rejects_unverified_raw_zone_evidence():
    source = "https://e.test/source"
    target = "https://e.test/target"
    graph = build_weighted_internal_link_graph([page(source), page(target)], [])
    raw = raw_zone_candidate(source, target)
    raw["state"] = "not_verified"

    result = graph_neighborhood_internal_link_opportunities(raw, graph)

    assert result["state"] == "not_verified"
    assert result["reason"] == "raw_zone_opportunity_not_verified"
    assert result["candidate_count"] == 0
    assert result["observed_route_scan_complete"] is False


def test_graph_neighborhood_no_candidate_state_remains_verified_and_non_sitewide():
    source = "https://e.test/source"
    target = "https://e.test/target"
    graph = build_weighted_internal_link_graph([page(source), page(target)], [])
    raw = raw_zone_candidate(source, target)
    raw["state"] = "no_candidate_observed"
    raw["candidate_count"] = 0
    raw["candidates"] = []

    result = graph_neighborhood_internal_link_opportunities(raw, graph)

    assert result["state"] == "no_candidate_observed"
    assert result["candidate_count"] == 0
    assert result["candidates"] == []
    assert result["observed_route_scan_complete"] is True
    assert result["sitewide_reachability_claim"] is False
