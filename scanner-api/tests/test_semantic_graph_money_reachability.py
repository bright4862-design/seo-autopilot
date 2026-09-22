from copy import deepcopy

from app.semantic_graph import build_weighted_internal_link_graph
from app.semantic_graph_money_reachability import (
    WEIGHTED_MONEY_PAGE_REACHABILITY_VERSION,
    weighted_money_page_reachability_evidence,
)


def page(url, **extra):
    return {
        "url": url,
        "status_code": 200,
        "page_evidence_class": "usable_html",
        "indexable": True,
        **extra,
    }


def nav_link(source, target, anchor="Pricing"):
    return {
        "source_url": source,
        "target_url": target,
        "anchor_text": anchor,
        "ancestor_tags": ["a", "nav"],
        "ancestor_roles": ["navigation"],
    }


def contextual_link(source, target, anchor="Pricing"):
    return {
        "source_url": source,
        "target_url": target,
        "anchor_text": anchor,
        "ancestor_tags": ["a", "article", "main"],
        "ancestor_roles": ["article", "main"],
    }


def money_row(result):
    assert len(result["pages"]) == 1
    return result["pages"][0]


def test_weighted_money_reachability_binds_direct_navigation_route():
    seed = "https://e.test/"
    pricing = "https://e.test/pricing"
    pages = [page(seed, is_seed=True), page(pricing, page_template_family="pricing_page")]
    links = [nav_link(seed, pricing)]
    graph = build_weighted_internal_link_graph(pages, links)

    result = weighted_money_page_reachability_evidence(pages, links, graph)

    assert result["version"] == WEIGHTED_MONEY_PAGE_REACHABILITY_VERSION
    assert result["state"] == "verified"
    assert result["seed_integrity_state"] == "verified"
    row = money_row(result)
    assert row["classification_reason"] == "existing_money_template_family"
    assert row["observed_in_edge_count"] == 1
    assert row["observed_navigation_in_edge_count"] == 1
    assert row["observed_contextual_in_edge_count"] == 0
    assert row["observed_depth_from_seed"] == 1
    assert row["observed_route_state"] == "reachable_from_seed_in_assessed_graph"
    assert row["reachability_assessment_state"] == "observed_reachable"
    assert row["weak_route_reasons"] == []
    assert result["sitewide_orphan_claim"] is False
    assert result["customer_fix_created"] is False


def test_contextual_only_money_route_is_sample_scoped_weak_navigation_signal():
    seed = "https://e.test/"
    product = "https://e.test/product/widget"
    pages = [page(seed, is_seed=True), page(product, money_page=True)]
    links = [contextual_link(seed, product)]
    graph = build_weighted_internal_link_graph(pages, links)

    result = weighted_money_page_reachability_evidence(pages, links, graph)
    row = money_row(result)

    assert row["observed_contextual_in_edge_count"] == 1
    assert row["observed_navigation_in_edge_count"] == 0
    assert row["observed_depth_from_seed"] == 1
    assert row["reachability_assessment_state"] == "observed_weak_route"
    assert row["weak_route_reasons"] == ["no_navigation_edge_observed"]
    assert row["sitewide_navigation_absence_claim"] is False


def test_depth_four_money_route_is_observed_weak_without_sitewide_orphan_claim():
    seed = "https://e.test/"
    a = "https://e.test/a"
    b = "https://e.test/b"
    c = "https://e.test/c"
    pricing = "https://e.test/pricing"
    pages = [
        page(seed, is_seed=True),
        page(a),
        page(b),
        page(c),
        page(pricing, page_template_family="pricing_page"),
    ]
    links = [nav_link(seed, a), nav_link(a, b), nav_link(b, c), nav_link(c, pricing)]
    graph = build_weighted_internal_link_graph(pages, links)

    row = money_row(weighted_money_page_reachability_evidence(pages, links, graph))

    assert row["observed_depth_from_seed"] == 4
    assert "observed_depth_at_least_4" in row["weak_route_reasons"]
    assert row["sitewide_orphan_claim"] is False


def test_mixed_zone_repeated_edge_preserves_occurrences_and_zone_membership():
    seed = "https://e.test/"
    pricing = "https://e.test/pricing"
    pages = [page(seed, is_seed=True), page(pricing, money_page=True)]
    links = [
        nav_link(seed, pricing, "Pricing"),
        contextual_link(seed, pricing, "Compare plans"),
        contextual_link(seed, pricing, "See pricing"),
    ]
    graph = build_weighted_internal_link_graph(pages, links)

    row = money_row(weighted_money_page_reachability_evidence(pages, links, graph))

    assert row["observed_in_edge_count"] == 1
    assert row["observed_inlink_occurrence_count"] == 3
    assert row["observed_navigation_in_edge_count"] == 1
    assert row["observed_contextual_in_edge_count"] == 1
    assert row["observed_mixed_zone_in_edge_count"] == 1
    assert row["zone_in_occurrence_counts"]["navigation"] == 1
    assert row["zone_in_occurrence_counts"]["contextual"] == 2
    assert row["strongest_inbound_zone"] == "contextual"


def test_explicit_seed_list_supports_depth_when_page_seed_marker_is_absent():
    seed = "https://e.test/start"
    pricing = "https://e.test/pricing"
    pages = [page(seed), page(pricing, page_value_class="money")]
    links = [nav_link(seed, pricing)]
    graph = build_weighted_internal_link_graph(pages, links)

    result = weighted_money_page_reachability_evidence(
        pages,
        links,
        graph,
        seed_urls=[seed],
    )

    row = money_row(result)
    assert result["seed_urls"] == [seed]
    assert row["classification_reason"] == "explicit_money_page_value_class"
    assert row["observed_depth_from_seed"] == 1


def test_missing_seed_preserves_verified_graph_metrics_but_partial_depth():
    source = "https://e.test/source"
    pricing = "https://e.test/pricing"
    pages = [page(source), page(pricing, page_intent="transactional")]
    links = [nav_link(source, pricing)]
    graph = build_weighted_internal_link_graph(pages, links)

    result = weighted_money_page_reachability_evidence(pages, links, graph)
    row = money_row(result)

    assert result["state"] == "verified"
    assert result["seed_integrity_state"] == "not_verified"
    assert row["classification_reason"] == "existing_money_page_intent"
    assert row["observed_in_edge_count"] == 1
    assert row["observed_depth_from_seed"] is None
    assert row["observed_route_state"] == "seed_not_verified"
    assert row["reachability_assessment_state"] == "partial_seed_unknown"


def test_disconnected_money_page_records_no_observed_seed_route_without_sitewide_claim():
    seed = "https://e.test/"
    source = "https://e.test/source"
    pricing = "https://e.test/pricing"
    pages = [page(seed, is_seed=True), page(source), page(pricing, money_page=True)]
    links = [nav_link(source, pricing)]
    graph = build_weighted_internal_link_graph(pages, links)

    result = weighted_money_page_reachability_evidence(pages, links, graph)
    row = money_row(result)

    assert row["observed_in_edge_count"] == 1
    assert row["observed_navigation_in_edge_count"] == 1
    assert row["observed_depth_from_seed"] is None
    assert row["observed_route_state"] == "no_observed_route_from_seed_in_assessed_graph"
    assert "no_observed_route_from_seed" in row["weak_route_reasons"]
    assert result["unreached_from_seed_count"] == 1
    assert row["sitewide_reachability_claim"] is False


def test_seed_outside_assessed_population_fails_closed():
    pricing = "https://e.test/pricing"
    pages = [page(pricing, money_page=True)]
    graph = build_weighted_internal_link_graph(pages, [])

    result = weighted_money_page_reachability_evidence(
        pages,
        [],
        graph,
        seed_urls=["https://e.test/not-assessed"],
    )

    assert result["state"] == "not_verified"
    assert result["reason"] == "seed_population_mismatch"
    assert result["graph_integrity_state"] == "verified"
    assert result["raw_link_observation_integrity_state"] == "verified"


def test_forged_graph_node_metric_fails_closed_before_reachability_evidence():
    seed = "https://e.test/"
    pricing = "https://e.test/pricing"
    pages = [page(seed, is_seed=True), page(pricing, money_page=True)]
    links = [nav_link(seed, pricing)]
    graph = build_weighted_internal_link_graph(pages, links)
    forged = deepcopy(graph)
    pricing_node = next(row for row in forged["nodes"] if row["url"] == pricing)
    pricing_node["weighted_in"] += 1.0

    result = weighted_money_page_reachability_evidence(pages, links, forged)

    assert result["state"] == "not_verified"
    assert result["reason"] == "graph_node_weight_mismatch"


def test_raw_link_graph_divergence_fails_closed():
    seed = "https://e.test/"
    pricing = "https://e.test/pricing"
    pages = [page(seed, is_seed=True), page(pricing, money_page=True)]
    links = [nav_link(seed, pricing)]
    graph = build_weighted_internal_link_graph(pages, links)

    result = weighted_money_page_reachability_evidence(pages, [], graph)

    assert result["state"] == "not_verified"
    assert result["reason"] == "graph_edge_observation_population_mismatch"
    assert result["graph_integrity_state"] == "verified"


def test_no_classified_money_pages_is_verified_zero_observed_sample_not_sitewide_claim():
    seed = "https://e.test/"
    pages = [page(seed, is_seed=True)]
    graph = build_weighted_internal_link_graph(pages, [])

    result = weighted_money_page_reachability_evidence(pages, [], graph)

    assert result["state"] == "verified"
    assert result["classified_money_page_count"] == 0
    assert result["weak_route_count"] == 0
    assert result["pages"] == []
    assert result["sitewide_reachability_claim"] is False
    assert result["sitewide_orphan_claim"] is False
    assert result["sitewide_navigation_absence_claim"] is False
    assert result["sitewide_link_absence_claim"] is False
