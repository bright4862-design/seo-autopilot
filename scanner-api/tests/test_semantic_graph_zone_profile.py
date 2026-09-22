from copy import deepcopy

from app.semantic_graph import build_weighted_internal_link_graph
from app.semantic_graph_zone_profile import (
    LINK_ZONE_OBSERVATION_PROFILE_VERSION,
    graph_bound_link_zone_observation_profile,
)


def page(url):
    return {
        "url": url,
        "status_code": 200,
        "page_evidence_class": "usable_html",
        "indexable": True,
    }


def link(source, target, *, zone="contextual", anchor="shared topic"):
    row = {
        "source_url": source,
        "target_url": target,
        "anchor_text": anchor,
    }
    if zone == "contextual":
        row["ancestor_tags"] = ["a", "main"]
    elif zone == "navigation":
        row["ancestor_tags"] = ["a", "nav"]
    elif zone == "footer":
        row["ancestor_tags"] = ["a", "footer"]
    elif zone == "aside":
        row["ancestor_tags"] = ["a", "aside"]
    elif zone == "header":
        row["ancestor_tags"] = ["a", "header"]
    return row


def test_zone_profile_preserves_all_observed_zones_for_one_graph_edge():
    source = "https://e.test/a"
    target = "https://e.test/b"
    pages = [page(source), page(target)]
    links = [
        link(source, target, zone="footer", anchor="footer topic"),
        link(source, target, zone="navigation", anchor="nav topic"),
        link(source, target, zone="contextual", anchor="body topic"),
    ]
    graph = build_weighted_internal_link_graph(pages, links)

    result = graph_bound_link_zone_observation_profile(pages, links, graph)

    assert result["version"] == LINK_ZONE_OBSERVATION_PROFILE_VERSION
    assert result["state"] == "verified"
    assert result["graph_integrity_state"] == "verified"
    assert result["observed_assessed_link_occurrence_count"] == 3
    assert result["observed_directed_edge_count"] == 1
    assert result["zone_occurrence_counts"]["footer"] == 1
    assert result["zone_occurrence_counts"]["navigation"] == 1
    assert result["zone_occurrence_counts"]["contextual"] == 1
    profile = result["edge_profiles"][0]
    assert profile["observed_occurrences"] == 3
    assert profile["zone_occurrence_counts"]["footer"] == 1
    assert profile["zone_occurrence_counts"]["navigation"] == 1
    assert profile["zone_occurrence_counts"]["contextual"] == 1
    assert profile["strongest_observed_zone"] == "contextual"
    assert profile["graph_strongest_zone"] == "contextual"
    assert profile["sitewide_link_distribution_claim"] is False
    assert result["customer_fix_created"] is False


def test_zone_profile_rejects_forged_graph_occurrence_count():
    pages = [page("https://e.test/a"), page("https://e.test/b")]
    links = [link(pages[0]["url"], pages[1]["url"])]
    graph = build_weighted_internal_link_graph(pages, links)
    forged = deepcopy(graph)
    forged["edges"][0]["observed_occurrences"] = 99

    result = graph_bound_link_zone_observation_profile(pages, links, forged)

    assert result["state"] == "not_verified"
    assert result["reason"] == "graph_edge_occurrence_mismatch"


def test_zone_profile_rejects_forged_strongest_zone_even_when_graph_metrics_balance():
    pages = [page("https://e.test/a"), page("https://e.test/b")]
    links = [link(pages[0]["url"], pages[1]["url"], zone="contextual")]
    graph = build_weighted_internal_link_graph(pages, links)
    forged = deepcopy(graph)
    forged["edges"][0]["strongest_zone"] = "footer"

    result = graph_bound_link_zone_observation_profile(pages, links, forged)

    assert result["state"] == "not_verified"
    assert result["reason"] == "graph_edge_strongest_zone_mismatch"


def test_zone_profile_rejects_forged_weight_even_if_node_totals_are_forged_consistently():
    pages = [page("https://e.test/a"), page("https://e.test/b")]
    links = [link(pages[0]["url"], pages[1]["url"], zone="navigation")]
    graph = build_weighted_internal_link_graph(pages, links)
    forged = deepcopy(graph)
    old_weight = forged["edges"][0]["weight"]
    new_weight = round(old_weight + 0.125, 6)
    forged["edges"][0]["weight"] = new_weight
    by_url = {row["url"]: row for row in forged["nodes"]}
    by_url[pages[0]["url"]]["weighted_out"] = new_weight
    by_url[pages[1]["url"]]["weighted_in"] = new_weight

    result = graph_bound_link_zone_observation_profile(pages, links, forged)

    assert result["state"] == "not_verified"
    assert result["reason"] == "graph_edge_weight_mismatch"


def test_zone_profile_rejects_forged_anchor_terms():
    pages = [page("https://e.test/a"), page("https://e.test/b")]
    links = [link(pages[0]["url"], pages[1]["url"], anchor="alpha beta")]
    graph = build_weighted_internal_link_graph(pages, links)
    forged = deepcopy(graph)
    forged["edges"][0]["anchor_terms"] = ["fabricated"]

    result = graph_bound_link_zone_observation_profile(pages, links, forged)

    assert result["state"] == "not_verified"
    assert result["reason"] == "graph_edge_anchor_terms_mismatch"


def test_zone_profile_binds_skipped_link_counters_to_raw_observations():
    pages = [page("https://e.test/a"), page("https://e.test/b")]
    links = [
        link(pages[0]["url"], "https://outside.test/x"),
        link(pages[0]["url"], "https://e.test/unassessed"),
    ]
    graph = build_weighted_internal_link_graph(pages, links)
    forged = deepcopy(graph)
    forged["skipped_external_links"] = 0

    result = graph_bound_link_zone_observation_profile(pages, links, forged)

    assert result["state"] == "not_verified"
    assert result["reason"] == "graph_skipped_external_count_mismatch"


def test_zone_profile_is_deterministic_across_raw_link_input_order():
    source = "https://e.test/a"
    target = "https://e.test/b"
    pages = [page(source), page(target)]
    links = [
        link(source, target, zone="footer", anchor="zeta"),
        link(source, target, zone="contextual", anchor="alpha"),
        link(source, target, zone="navigation", anchor="beta"),
    ]

    forward = graph_bound_link_zone_observation_profile(
        pages,
        links,
        build_weighted_internal_link_graph(pages, links),
    )
    reverse_links = list(reversed(links))
    reverse = graph_bound_link_zone_observation_profile(
        pages,
        reverse_links,
        build_weighted_internal_link_graph(pages, reverse_links),
    )

    assert forward == reverse


def test_zone_profile_does_not_mutate_inputs():
    pages = [page("https://e.test/a"), page("https://e.test/b")]
    links = [link(pages[0]["url"], pages[1]["url"], zone="aside")]
    graph = build_weighted_internal_link_graph(pages, links)
    before_pages = deepcopy(pages)
    before_links = deepcopy(links)
    before_graph = deepcopy(graph)

    graph_bound_link_zone_observation_profile(pages, links, graph)

    assert pages == before_pages
    assert links == before_links
    assert graph == before_graph
