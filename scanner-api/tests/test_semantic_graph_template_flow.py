from copy import deepcopy

from app.semantic_graph import build_weighted_internal_link_graph, infer_template_groups
from app.semantic_graph_template_flow import (
    MAX_FLOW_EDGE_SAMPLES,
    TEMPLATE_LINK_FLOW_VERSION,
    template_link_flow_evidence,
)


def page(url, family):
    return {
        "url": url,
        "status_code": 200,
        "page_evidence_class": "usable_html",
        "indexable": True,
        "page_template_family": family,
    }


def link(source, target, *, zone="contextual"):
    row = {
        "source_url": source,
        "target_url": target,
        "anchor_text": "shared topic",
    }
    if zone == "contextual":
        row["ancestor_tags"] = ["a", "main"]
    elif zone == "navigation":
        row["ancestor_tags"] = ["a", "nav"]
    elif zone == "footer":
        row["ancestor_tags"] = ["a", "footer"]
    return row


def test_template_link_flow_aggregates_observed_edges_by_template_pair_and_zone():
    article_a = "https://e.test/articles/a"
    article_b = "https://e.test/articles/b"
    product_a = "https://e.test/products/a"
    product_b = "https://e.test/products/b"
    pages = [
        page(article_a, "article"),
        page(article_b, "article"),
        page(product_a, "product"),
        page(product_b, "product"),
    ]
    links = [
        link(article_a, product_a, zone="contextual"),
        link(article_b, product_a, zone="navigation"),
        link(article_b, product_b, zone="footer"),
    ]

    templates = infer_template_groups(pages)
    graph = build_weighted_internal_link_graph(pages, links)
    result = template_link_flow_evidence(templates, graph)

    assert result["version"] == TEMPLATE_LINK_FLOW_VERSION
    assert result["state"] == "verified"
    assert result["template_integrity_state"] == "verified"
    assert result["graph_integrity_state"] == "verified"
    assert result["observed_template_group_count"] == 2
    assert result["observed_template_flow_count"] == 1
    assert result["observed_directed_edge_count"] == 3
    flow = result["flows"][0]
    assert flow["cross_template"] is True
    assert flow["observed_directed_edge_count"] == 3
    assert flow["observed_source_page_count"] == 2
    assert flow["observed_target_page_count"] == 2
    assert flow["strongest_zone_counts"]["contextual"] == 1
    assert flow["strongest_zone_counts"]["navigation"] == 1
    assert flow["strongest_zone_counts"]["footer"] == 1
    assert flow["contextual_edge_count"] == 1
    assert flow["sitewide_link_absence_claim"] is False
    assert result["sitewide_template_flow_claim"] is False
    assert result["customer_fix_created"] is False


def test_template_link_flow_revalidates_graph_metrics_before_using_weights():
    pages = [page("https://e.test/a", "article"), page("https://e.test/b", "product")]
    templates = infer_template_groups(pages)
    graph = build_weighted_internal_link_graph(pages, [link(pages[0]["url"], pages[1]["url"])])
    forged = deepcopy(graph)
    forged["nodes"][0]["weighted_out"] = round(forged["nodes"][0]["weighted_out"] + 1.0, 6)

    result = template_link_flow_evidence(templates, forged)

    assert result["state"] == "not_verified"
    assert result["reason"] == "graph_node_weight_mismatch"
    assert result["template_integrity_state"] == "verified"
    assert result["graph_integrity_state"] == "not_verified"
    assert result["flows"] == []


def test_template_link_flow_requires_exact_graph_and_template_page_population():
    pages = [page("https://e.test/a", "article"), page("https://e.test/b", "product")]
    templates = infer_template_groups(pages[:1])
    graph = build_weighted_internal_link_graph(pages, [])

    result = template_link_flow_evidence(templates, graph)

    assert result["state"] == "not_verified"
    assert result["reason"] == "graph_page_population_mismatch"
    assert result["template_integrity_state"] == "verified"


def test_template_link_flow_rejects_forged_group_counts():
    pages = [page("https://e.test/a", "article"), page("https://e.test/b", "article")]
    templates = infer_template_groups(pages)
    graph = build_weighted_internal_link_graph(pages, [])
    forged = deepcopy(templates)
    forged["groups"][0]["page_count"] = 99

    result = template_link_flow_evidence(forged, graph)

    assert result["state"] == "not_verified"
    assert result["reason"] == "template_group_count_mismatch"
    assert result["graph_integrity_state"] == "not_verified"


def test_template_link_flow_fails_closed_when_template_page_identity_is_missing():
    pages = [page("https://e.test/a", "article"), {"status_code": 200}]
    templates = infer_template_groups(pages)
    graph = build_weighted_internal_link_graph(pages, [])

    result = template_link_flow_evidence(templates, graph)

    assert result["state"] == "not_verified"
    assert result["reason"] == "template_page_identity_incomplete"
    assert result["flows"] == []


def test_template_link_flow_is_deterministic_across_input_order():
    pages = [
        page("https://e.test/articles/a", "article"),
        page("https://e.test/articles/b", "article"),
        page("https://e.test/products/a", "product"),
    ]
    links = [
        link(pages[0]["url"], pages[2]["url"], zone="navigation"),
        link(pages[1]["url"], pages[2]["url"], zone="contextual"),
    ]

    forward = template_link_flow_evidence(
        infer_template_groups(pages),
        build_weighted_internal_link_graph(pages, links),
    )
    reverse_pages = list(reversed(pages))
    reverse_links = list(reversed(links))
    reverse = template_link_flow_evidence(
        infer_template_groups(reverse_pages),
        build_weighted_internal_link_graph(reverse_pages, reverse_links),
    )

    assert forward == reverse


def test_template_link_flow_samples_are_bounded_without_hiding_total_observed_edges():
    sources = [page(f"https://e.test/articles/{index}", "article") for index in range(3)]
    targets = [page(f"https://e.test/products/{index}", "product") for index in range(2)]
    pages = sources + targets
    links = [link(source["url"], target["url"]) for source in sources for target in targets]

    result = template_link_flow_evidence(
        infer_template_groups(pages),
        build_weighted_internal_link_graph(pages, links),
    )

    flow = result["flows"][0]
    assert flow["observed_directed_edge_count"] == 6
    assert len(flow["sample_edges"]) == MAX_FLOW_EDGE_SAMPLES
    assert flow["sample_edges_truncated"] is True
