from app.semantic_graph_evidence_opportunity_neighborhood_bound import (
    GRAPH_NEIGHBORHOOD_BOUND_GRAPH_ENVELOPE_VERSION,
    build_graph_neighborhood_bound_semantic_graph_evidence,
)
from app.semantic_graph_opportunity_neighborhood import (
    GRAPH_NEIGHBORHOOD_CONTEXTUAL_OPPORTUNITY_VERSION,
)


SHINGLES = ["aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb", "cccccccccccccccc"]


def page(url, family):
    return {
        "url": url,
        "status_code": 200,
        "page_evidence_class": "usable_html",
        "indexable": True,
        "page_template_family": family,
        "main_text_verified": True,
        "main_text_representation": "sha256_5_token_shingles_v1",
        "main_text": " ".join(SHINGLES),
    }


class CountingVectorizer:
    version = "graph_neighborhood_binding_v1"

    def __init__(self):
        self.calls = 0

    def vectors(self, pages):
        self.calls += 1
        return {row["url"]: {"shared_intent": 1.0} for row in pages}


def nav_link(source, target):
    return {
        "source_url": source,
        "target_url": target,
        "anchor_text": "Guides",
        "ancestor_tags": ["a", "nav"],
        "ancestor_roles": ["navigation"],
    }


def by_direction(result):
    evidence = result["graph_neighborhood_contextual_internal_link_opportunities"]
    return {
        (row["source_url"], row["target_url"]): row
        for row in evidence["candidates"]
    }


def test_v11_binds_existing_contextual_upgrade_to_assessed_graph_route_without_extra_vector_calls():
    source = "https://e.test/products/a"
    target = "https://e.test/guides/b"
    vectorizer = CountingVectorizer()

    result = build_graph_neighborhood_bound_semantic_graph_evidence(
        [page(source, "product"), page(target, "guide")],
        [nav_link(source, target)],
        vectorizer=vectorizer,
        cluster_threshold=0.99,
        cannibalization_threshold=0.99,
        contextual_threshold=0.58,
    )

    assert result["version"] == GRAPH_NEIGHBORHOOD_BOUND_GRAPH_ENVELOPE_VERSION
    assert result["graph_neighborhood_contextual_opportunity_version"] == (
        GRAPH_NEIGHBORHOOD_CONTEXTUAL_OPPORTUNITY_VERSION
    )
    assert vectorizer.calls == 2

    rows = by_direction(result)
    forward = rows[(source, target)]
    reverse = rows[(target, source)]
    assert forward["reason"] == "existing_non_contextual_edge_contextual_upgrade"
    assert forward["observed_directed_shortest_path_hops"] == 1
    assert forward["observed_graph_route_state"] == "reachable_in_assessed_graph"
    assert reverse["reason"] == "no_observed_edge_in_assessed_sample"
    assert reverse["observed_directed_shortest_path_hops"] is None
    assert reverse["observed_graph_route_state"] == "no_observed_route_in_assessed_graph"
    assert result["sitewide_reachability_claim"] is False
    assert result["sitewide_orphan_claim"] is False
    assert result["customer_fix_created"] is False


def test_v11_measures_two_hop_route_for_missing_direct_opportunity():
    source = "https://e.test/products/a"
    bridge = "https://e.test/hubs/middle"
    target = "https://e.test/guides/b"
    vectorizer = CountingVectorizer()

    result = build_graph_neighborhood_bound_semantic_graph_evidence(
        [
            page(source, "product"),
            page(bridge, "hub"),
            page(target, "guide"),
        ],
        [nav_link(source, bridge), nav_link(bridge, target)],
        vectorizer=vectorizer,
        cluster_threshold=0.99,
        cannibalization_threshold=0.99,
        contextual_threshold=0.58,
    )

    assert vectorizer.calls == 2
    candidate = by_direction(result)[(source, target)]
    assert candidate["observed_edge_present"] is False
    assert candidate["observed_directed_shortest_path_hops"] == 2
    assert candidate["observed_two_hop_bridge_count"] == 1
    assert candidate["observed_two_hop_bridges"][0]["url"] == bridge
    assert candidate["sitewide_reachability_claim"] is False


def test_v11_preserves_partial_semantic_coverage_without_inventing_route_candidates():
    first = page("https://e.test/a", "article")
    second = page("https://e.test/b", "article")

    class PartialVectorizer(CountingVectorizer):
        def vectors(self, pages):
            self.calls += 1
            return {pages[0]["url"]: {"shared_intent": 1.0}}

    vectorizer = PartialVectorizer()
    result = build_graph_neighborhood_bound_semantic_graph_evidence(
        [first, second],
        [],
        vectorizer=vectorizer,
    )

    assert vectorizer.calls == 2
    assert result["semantic_vector_coverage_state"] == "partial"
    assert result["state"] == "partial"
    opportunities = result["graph_neighborhood_contextual_internal_link_opportunities"]
    assert opportunities["state"] == "no_candidate_observed"
    assert opportunities["candidate_count"] == 0
    assert opportunities["observed_route_scan_complete"] is True
    assert opportunities["sitewide_reachability_claim"] is False
