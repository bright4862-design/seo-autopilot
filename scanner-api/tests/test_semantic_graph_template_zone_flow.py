from copy import deepcopy

from app.semantic_graph import build_weighted_internal_link_graph, infer_template_groups
from app.semantic_graph_template_zone_flow import (
    TEMPLATE_LINK_ZONE_FLOW_VERSION,
    template_link_zone_flow_evidence,
)


def page(url, family):
    return {
        "url": url,
        "status_code": 200,
        "page_evidence_class": "usable_html",
        "page_template_family": family,
        "indexable": True,
    }


def nav_link(source, target, text="Products"):
    return {
        "source_url": source,
        "target_url": target,
        "anchor_text": text,
        "ancestor_tags": ["a", "nav"],
        "ancestor_roles": ["navigation"],
    }


def contextual_link(source, target, text="Read more"):
    return {
        "source_url": source,
        "target_url": target,
        "anchor_text": text,
        "ancestor_tags": ["a", "article", "main"],
        "ancestor_roles": ["article", "main"],
    }


def build(pages, links):
    templates = infer_template_groups(pages)
    graph = build_weighted_internal_link_graph(pages, links)
    return template_link_zone_flow_evidence(pages, links, templates, graph)


def flow(result, source_key, target_key):
    return next(
        row
        for row in result["flows"]
        if row["source_template_key"] == source_key
        and row["target_template_key"] == target_key
    )


def test_mixed_zone_occurrences_are_preserved_beyond_strongest_graph_zone():
    source = "https://e.test/products/a"
    target = "https://e.test/guides/b"
    pages = [page(source, "product"), page(target, "guide")]
    links = [
        nav_link(source, target, "Guides"),
        contextual_link(source, target, "Guide to product b"),
    ]

    result = build(pages, links)

    assert result["version"] == TEMPLATE_LINK_ZONE_FLOW_VERSION
    assert result["state"] == "verified"
    row = flow(result, "family:product", "family:guide")
    assert row["observed_link_occurrence_count"] == 2
    assert row["observed_directed_edge_count"] == 1
    assert row["zone_occurrence_counts"]["navigation"] == 1
    assert row["zone_occurrence_counts"]["contextual"] == 1
    assert row["contextual_occurrence_count"] == 1
    assert row["contextual_directed_edge_count"] == 1
    assert row["mixed_zone_directed_edge_count"] == 1
    assert row["strongest_zone_directed_edge_counts"]["contextual"] == 1
    assert result["sitewide_link_absence_claim"] is False
    assert result["customer_fix_created"] is False


def test_repeated_same_zone_occurrences_do_not_inflate_directed_edge_count():
    source = "https://e.test/products/a"
    target = "https://e.test/guides/b"
    pages = [page(source, "product"), page(target, "guide")]
    links = [
        nav_link(source, target, "Guides"),
        nav_link(source, target, "Help"),
        nav_link(source, target, "Learn"),
    ]

    result = build(pages, links)
    row = flow(result, "family:product", "family:guide")

    assert row["observed_link_occurrence_count"] == 3
    assert row["observed_directed_edge_count"] == 1
    assert row["zone_occurrence_counts"]["navigation"] == 3
    assert row["mixed_zone_directed_edge_count"] == 0
    assert result["observed_link_occurrence_count"] == 3
    assert result["observed_directed_edge_count"] == 1


def test_template_pairs_remain_directional_and_separate():
    product = "https://e.test/products/a"
    guide = "https://e.test/guides/b"
    category = "https://e.test/categories/c"
    pages = [
        page(product, "product"),
        page(guide, "guide"),
        page(category, "category"),
    ]
    links = [
        contextual_link(product, guide),
        nav_link(guide, product),
        contextual_link(category, product),
    ]

    result = build(pages, links)

    assert result["observed_template_flow_count"] == 3
    assert flow(result, "family:product", "family:guide")["cross_template"] is True
    assert flow(result, "family:guide", "family:product")["observed_directed_edge_count"] == 1
    assert flow(result, "family:category", "family:product")["contextual_occurrence_count"] == 1


def test_same_template_flow_is_explicitly_not_cross_template():
    left = "https://e.test/products/a"
    right = "https://e.test/products/b"
    pages = [page(left, "product"), page(right, "product")]

    result = build(pages, [contextual_link(left, right)])
    row = flow(result, "family:product", "family:product")

    assert row["cross_template"] is False
    assert row["observed_source_page_count"] == 1
    assert row["observed_target_page_count"] == 1


def test_output_is_deterministic_across_link_order():
    left = "https://e.test/products/a"
    right = "https://e.test/guides/b"
    pages = [page(left, "product"), page(right, "guide")]
    links = [
        nav_link(left, right, "Guides"),
        contextual_link(left, right, "Detailed guide"),
        nav_link(right, left, "Products"),
    ]

    forward = build(pages, links)
    reverse = build(list(reversed(pages)), list(reversed(links)))

    assert forward == reverse


def test_external_and_unassessed_observations_are_scoped_not_promoted_to_flow():
    left = "https://e.test/a"
    right = "https://e.test/b"
    pages = [page(left, "a"), page(right, "b")]
    links = [
        contextual_link(left, right),
        contextual_link(left, "https://external.test/x"),
        contextual_link(left, "https://e.test/unassessed"),
    ]

    result = build(pages, links)

    assert result["state"] == "verified"
    assert result["observed_link_occurrence_count"] == 1
    assert result["skipped_external_links"] == 1
    assert result["skipped_unassessed_targets"] == 1
    assert result["observed_directed_edge_count"] == 1


def test_duplicate_page_identity_fails_closed_before_flow_evidence():
    url = "https://e.test/a"
    pages = [page(url, "a"), page(url, "a")]
    templates = infer_template_groups(pages)
    graph = build_weighted_internal_link_graph(pages, [])

    result = template_link_zone_flow_evidence(pages, [], templates, graph)

    assert result["state"] == "not_verified"
    assert result["reason"] == "duplicate_page_identity"
    assert result["flows"] == []


def test_forged_graph_raw_link_count_relationship_fails_closed():
    left = "https://e.test/a"
    right = "https://e.test/b"
    pages = [page(left, "a"), page(right, "b")]
    links = [contextual_link(left, right)]
    templates = infer_template_groups(pages)
    graph = build_weighted_internal_link_graph(pages, links)
    forged = deepcopy(graph)
    forged["edges"][0]["observed_occurrences"] = 2

    result = template_link_zone_flow_evidence(pages, links, templates, forged)

    assert result["state"] == "not_verified"
    assert result["reason"] == "graph_edge_occurrence_mismatch"
    assert result["template_integrity_state"] == "verified"
    assert result["graph_integrity_state"] == "verified"


def test_zero_links_is_verified_empty_observed_sample_not_sitewide_absence():
    pages = [page("https://e.test/a", "a"), page("https://e.test/b", "b")]

    result = build(pages, [])

    assert result["state"] == "verified"
    assert result["observed_template_flow_count"] == 0
    assert result["observed_directed_edge_count"] == 0
    assert result["observed_link_occurrence_count"] == 0
    assert result["flows"] == []
    assert result["sitewide_template_flow_claim"] is False
    assert result["sitewide_link_distribution_claim"] is False
    assert result["sitewide_link_absence_claim"] is False
