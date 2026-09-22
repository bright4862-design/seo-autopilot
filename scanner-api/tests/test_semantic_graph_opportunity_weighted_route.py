from copy import deepcopy

from app.semantic_graph import build_weighted_internal_link_graph
from app.semantic_graph_opportunity_neighborhood import (
    graph_neighborhood_internal_link_opportunities,
)
from app.semantic_graph_opportunity_weighted_route import (
    WEIGHTED_ROUTE_CONTEXTUAL_OPPORTUNITY_VERSION,
    weighted_route_internal_link_opportunities,
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


def raw_zone_empty():
    return {
        "version": "template_contextual_internal_link_opportunity_v2_raw_zone_bound",
        "scope": "observed_assessed_pages_only",
        "state": "no_candidate_observed",
        "reason": "validated",
        "template_contextual_opportunity_integrity_state": "verified",
        "template_zone_flow_integrity_state": "verified",
        "candidate_count": 0,
        "candidates_truncated": False,
        "sitewide_link_absence_claim": False,
        "sitewide_template_flow_claim": False,
        "sitewide_link_distribution_claim": False,
        "customer_fix_created": False,
        "candidates": [],
    }


def neighborhood(raw, graph):
    return graph_neighborhood_internal_link_opportunities(raw, graph)


def first(result):
    return result["candidates"][0]


def test_weighted_route_prefers_stronger_longer_route_over_shortest_weak_route():
    source = "https://e.test/source"
    weak = "https://e.test/weak"
    strong_a = "https://e.test/strong-a"
    strong_b = "https://e.test/strong-b"
    target = "https://e.test/target"
    pages = [page(url) for url in (source, weak, strong_a, strong_b, target)]
    graph = build_weighted_internal_link_graph(
        pages,
        [
            nav_link(source, weak),
            nav_link(weak, target),
            contextual_link(source, strong_a),
            contextual_link(strong_a, strong_b),
            contextual_link(strong_b, target),
        ],
    )
    observed = neighborhood(raw_zone_candidate(source, target), graph)

    result = weighted_route_internal_link_opportunities(observed, graph)

    assert result["version"] == WEIGHTED_ROUTE_CONTEXTUAL_OPPORTUNITY_VERSION
    assert result["state"] == "candidate"
    candidate = first(result)
    assert candidate["observed_directed_shortest_path_hops"] == 2
    assert candidate["observed_widest_path_hops"] == 3
    assert candidate["observed_widest_path_extra_hops_vs_shortest"] == 1
    assert candidate["observed_widest_path_url_samples"] == [
        source,
        strong_a,
        strong_b,
        target,
    ]
    assert candidate["observed_widest_path_zone_edge_counts"]["contextual"] == 3
    assert candidate["observed_widest_path_bottleneck_edge"]["strongest_zone"] == "contextual"
    assert candidate["sitewide_reachability_claim"] is False
    assert result["customer_fix_created"] is False


def test_weighted_route_ties_prefer_fewer_hops_then_lexicographic_path():
    source = "https://e.test/source"
    a = "https://e.test/a"
    b = "https://e.test/b"
    long_a = "https://e.test/long-a"
    long_b = "https://e.test/long-b"
    target = "https://e.test/target"
    pages = [page(url) for url in (source, a, b, long_a, long_b, target)]
    graph = build_weighted_internal_link_graph(
        pages,
        [
            nav_link(source, a),
            nav_link(a, target),
            nav_link(source, b),
            nav_link(b, target),
            nav_link(source, long_a),
            nav_link(long_a, long_b),
            nav_link(long_b, target),
        ],
    )
    observed = neighborhood(raw_zone_candidate(source, target), graph)

    candidate = first(weighted_route_internal_link_opportunities(observed, graph))

    assert candidate["observed_widest_path_hops"] == 2
    assert candidate["observed_widest_path_url_samples"] == [source, a, target]
    assert candidate["observed_widest_path_extra_hops_vs_shortest"] == 0


def test_weighted_route_preserves_existing_noncontextual_direct_edge():
    source = "https://e.test/source"
    target = "https://e.test/target"
    graph = build_weighted_internal_link_graph(
        [page(source), page(target)],
        [nav_link(source, target)],
    )
    observed = neighborhood(
        raw_zone_candidate(
            source,
            target,
            observed_edge_present=True,
            existing_strongest_zone="navigation",
        ),
        graph,
    )

    candidate = first(weighted_route_internal_link_opportunities(observed, graph))

    assert candidate["observed_widest_path_hops"] == 1
    assert candidate["observed_widest_path_extra_hops_vs_shortest"] == 0
    assert candidate["observed_widest_path_bottleneck_edge"]["source_url"] == source
    assert candidate["observed_widest_path_bottleneck_edge"]["target_url"] == target
    assert candidate["observed_widest_path_bottleneck_edge"]["strongest_zone"] == "navigation"


def test_weighted_route_keeps_missing_route_sample_scoped():
    source = "https://e.test/source"
    target = "https://e.test/target"
    graph = build_weighted_internal_link_graph([page(source), page(target)], [])
    observed = neighborhood(raw_zone_candidate(source, target), graph)

    result = weighted_route_internal_link_opportunities(observed, graph)

    candidate = first(result)
    assert candidate["observed_weighted_route_state"] == "no_observed_route_in_assessed_graph"
    assert candidate["observed_widest_path_hops"] is None
    assert candidate["observed_widest_path_bottleneck_weight"] is None
    assert candidate["observed_widest_path_url_samples"] == []
    assert result["sitewide_reachability_claim"] is False
    assert result["sitewide_orphan_claim"] is False
    assert result["sitewide_link_absence_claim"] is False


def test_weighted_route_rejects_forged_shortest_path_measurement():
    source = "https://e.test/source"
    bridge = "https://e.test/bridge"
    target = "https://e.test/target"
    graph = build_weighted_internal_link_graph(
        [page(source), page(bridge), page(target)],
        [nav_link(source, bridge), nav_link(bridge, target)],
    )
    observed = neighborhood(raw_zone_candidate(source, target), graph)
    forged = deepcopy(observed)
    forged["candidates"][0]["observed_directed_shortest_path_hops"] = 3

    result = weighted_route_internal_link_opportunities(forged, graph)

    assert result["state"] == "not_verified"
    assert result["reason"] == "weighted_route_forward_shortest_path_mismatch"
    assert result["graph_neighborhood_integrity_state"] == "verified"
    assert result["graph_integrity_state"] == "verified"


def test_weighted_route_rejects_forged_neighborhood_route_state_before_graph_use():
    source = "https://e.test/source"
    target = "https://e.test/target"
    graph = build_weighted_internal_link_graph([page(source), page(target)], [])
    observed = neighborhood(raw_zone_candidate(source, target), graph)
    forged = deepcopy(observed)
    forged["candidates"][0]["observed_graph_route_state"] = "reachable_in_assessed_graph"

    result = weighted_route_internal_link_opportunities(forged, graph)

    assert result["state"] == "not_verified"
    assert result["reason"] == "graph_neighborhood_forward_route_state_mismatch"
    assert result["graph_neighborhood_integrity_state"] == "not_verified"


def test_weighted_route_rejects_forged_graph_metrics():
    source = "https://e.test/source"
    bridge = "https://e.test/bridge"
    target = "https://e.test/target"
    graph = build_weighted_internal_link_graph(
        [page(source), page(bridge), page(target)],
        [nav_link(source, bridge), nav_link(bridge, target)],
    )
    observed = neighborhood(raw_zone_candidate(source, target), graph)
    forged_graph = deepcopy(graph)
    source_node = next(row for row in forged_graph["nodes"] if row["url"] == source)
    source_node["weighted_out"] += 1.0

    result = weighted_route_internal_link_opportunities(observed, forged_graph)

    assert result["state"] == "not_verified"
    assert result["reason"] == "graph_node_weight_mismatch"
    assert result["graph_neighborhood_integrity_state"] == "verified"
    assert result["graph_integrity_state"] == "not_verified"


def test_weighted_route_discloses_truncated_candidate_population():
    source = "https://e.test/source"
    target = "https://e.test/target"
    graph = build_weighted_internal_link_graph([page(source), page(target)], [])
    observed = neighborhood(raw_zone_candidate(source, target), graph)
    truncated = deepcopy(observed)
    truncated["candidate_count"] = 2
    truncated["candidates_truncated"] = True

    result = weighted_route_internal_link_opportunities(truncated, graph)

    assert result["state"] == "candidate"
    assert result["candidate_count"] == 2
    assert len(result["candidates"]) == 1
    assert result["candidates_truncated"] is True
    assert result["weighted_route_evaluated_candidate_count"] == 1
    assert result["weighted_route_candidate_population_complete"] is False


def test_weighted_route_does_not_mutate_inputs():
    source = "https://e.test/source"
    bridge = "https://e.test/bridge"
    target = "https://e.test/target"
    graph = build_weighted_internal_link_graph(
        [page(source), page(bridge), page(target)],
        [nav_link(source, bridge), nav_link(bridge, target)],
    )
    observed = neighborhood(raw_zone_candidate(source, target), graph)
    graph_before = deepcopy(graph)
    observed_before = deepcopy(observed)

    weighted_route_internal_link_opportunities(observed, graph)

    assert graph == graph_before
    assert observed == observed_before


def test_weighted_route_long_path_sample_preserves_both_endpoints():
    urls = ["https://e.test/source"] + [
        f"https://e.test/n{index:02d}" for index in range(1, 13)
    ] + ["https://e.test/target"]
    graph = build_weighted_internal_link_graph(
        [page(url) for url in urls],
        [nav_link(left, right) for left, right in zip(urls, urls[1:])],
    )
    observed = neighborhood(raw_zone_candidate(urls[0], urls[-1]), graph)

    candidate = first(weighted_route_internal_link_opportunities(observed, graph))

    assert candidate["observed_widest_path_hops"] == len(urls) - 1
    assert candidate["observed_widest_path_url_samples_truncated"] is True
    assert len(candidate["observed_widest_path_url_samples"]) == 12
    assert candidate["observed_widest_path_url_samples"][0] == urls[0]
    assert candidate["observed_widest_path_url_samples"][-1] == urls[-1]


def test_weighted_route_no_candidate_state_remains_verified_and_non_sitewide():
    source = "https://e.test/source"
    target = "https://e.test/target"
    graph = build_weighted_internal_link_graph([page(source), page(target)], [])
    observed = neighborhood(raw_zone_empty(), graph)

    result = weighted_route_internal_link_opportunities(observed, graph)

    assert result["state"] == "no_candidate_observed"
    assert result["candidate_count"] == 0
    assert result["candidates"] == []
    assert result["weighted_route_evaluated_candidate_count"] == 0
    assert result["weighted_route_candidate_population_complete"] is True
    assert result["sitewide_reachability_claim"] is False
    assert result["customer_fix_created"] is False
