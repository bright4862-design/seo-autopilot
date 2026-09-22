from copy import deepcopy

from app.semantic_graph import build_weighted_internal_link_graph
from app.semantic_graph_contextual import contextual_internal_link_opportunities


def page(url, *, indexable=True):
    return {
        "url": url,
        "status_code": 200,
        "page_evidence_class": "usable_html",
        "indexable": indexable,
    }


class MappingVectorizer:
    version = "test_mapping_v1"

    def vectors(self, pages):
        return {row["url"]: {"shared_intent": 1.0} for row in pages}


def candidate(result, source, target):
    return next(
        row
        for row in result["candidates"]
        if row["source_url"] == source and row["target_url"] == target
    )


def test_navigation_edge_does_not_suppress_contextual_upgrade():
    left = "https://e.test/a"
    right = "https://e.test/b"
    pages = [page(left), page(right)]
    graph = build_weighted_internal_link_graph(
        pages,
        [
            {
                "source_url": left,
                "target_url": right,
                "anchor_text": "Products",
                "ancestor_tags": ["a", "nav"],
                "ancestor_roles": ["navigation"],
            }
        ],
    )

    result = contextual_internal_link_opportunities(
        pages,
        graph,
        semantic_threshold=0.99,
        vectorizer=MappingVectorizer(),
    )

    row = candidate(result, left, right)
    assert row["observed_edge_present"] is True
    assert row["observed_contextual_edge_present"] is False
    assert row["existing_strongest_zone"] == "navigation"
    assert row["reason"] == "existing_non_contextual_edge_contextual_upgrade"
    assert row["sitewide_link_absence_claim"] is False


def test_contextual_edge_suppresses_duplicate_contextual_proposal():
    left = "https://e.test/a"
    right = "https://e.test/b"
    pages = [page(left), page(right)]
    graph = build_weighted_internal_link_graph(
        pages,
        [
            {
                "source_url": left,
                "target_url": right,
                "anchor_text": "Read more about shared intent",
                "ancestor_tags": ["a", "article", "main"],
                "ancestor_roles": ["article", "main"],
            }
        ],
    )

    result = contextual_internal_link_opportunities(
        pages,
        graph,
        semantic_threshold=0.99,
        vectorizer=MappingVectorizer(),
    )

    assert not any(
        row["source_url"] == left and row["target_url"] == right
        for row in result["candidates"]
    )
    assert any(
        row["source_url"] == right and row["target_url"] == left
        for row in result["candidates"]
    )


def test_contextual_zone_normalization_matches_graph_validation_before_suppression():
    left = "https://e.test/a"
    right = "https://e.test/b"
    pages = [page(left), page(right)]
    graph = build_weighted_internal_link_graph(
        pages,
        [
            {
                "source_url": left,
                "target_url": right,
                "anchor_text": "Read more about shared intent",
                "ancestor_tags": ["a", "article", "main"],
                "ancestor_roles": ["article", "main"],
            }
        ],
    )
    graph["edges"][0]["strongest_zone"] = "  Contextual  "

    result = contextual_internal_link_opportunities(
        pages,
        graph,
        semantic_threshold=0.99,
        vectorizer=MappingVectorizer(),
    )

    assert result["graph_integrity_state"] == "verified"
    assert not any(
        row["source_url"] == left and row["target_url"] == right
        for row in result["candidates"]
    )
    assert any(
        row["source_url"] == right and row["target_url"] == left
        for row in result["candidates"]
    )


def test_graph_page_population_mismatch_fails_closed():
    left = "https://e.test/a"
    right = "https://e.test/b"
    graph = build_weighted_internal_link_graph([page(left)], [])

    result = contextual_internal_link_opportunities(
        [page(left), page(right)],
        graph,
        semantic_threshold=0.99,
        vectorizer=MappingVectorizer(),
    )

    assert result["state"] == "not_verified"
    assert result["graph_integrity_state"] == "not_verified"
    assert result["reason"] == "graph_page_population_mismatch"
    assert result["candidate_count"] == 0
    assert result["candidates"] == []
    assert result["semantic_pair_scan_complete"] is False


def test_foreign_graph_edge_fails_closed():
    left = "https://e.test/a"
    right = "https://e.test/b"
    pages = [page(left), page(right)]
    graph = build_weighted_internal_link_graph(pages, [])
    forged = deepcopy(graph)
    forged["edges"].append(
        {
            "source_url": "https://e.test/foreign",
            "target_url": right,
            "strongest_zone": "contextual",
            "weight": 1.0,
        }
    )

    result = contextual_internal_link_opportunities(
        pages,
        forged,
        semantic_threshold=0.99,
        vectorizer=MappingVectorizer(),
    )

    assert result["state"] == "not_verified"
    assert result["reason"] == "graph_edge_population_mismatch"
    assert result["candidate_count"] == 0


def test_nonindexable_target_is_not_proposed():
    left = "https://e.test/a"
    right = "https://e.test/b"
    pages = [page(left), page(right, indexable=False)]
    graph = build_weighted_internal_link_graph(pages, [])

    result = contextual_internal_link_opportunities(
        pages,
        graph,
        semantic_threshold=0.99,
        vectorizer=MappingVectorizer(),
    )

    assert not any(row["target_url"] == right for row in result["candidates"])
    assert any(row["target_url"] == left for row in result["candidates"])


def test_contextual_opportunities_are_deterministic_across_page_order():
    urls = ["https://e.test/a", "https://e.test/b", "https://e.test/c"]
    pages = [page(url) for url in urls]
    graph = build_weighted_internal_link_graph(pages, [])
    reverse_pages = list(reversed(pages))
    reverse_graph = build_weighted_internal_link_graph(reverse_pages, [])

    forward = contextual_internal_link_opportunities(
        pages,
        graph,
        semantic_threshold=0.99,
        vectorizer=MappingVectorizer(),
    )
    reverse = contextual_internal_link_opportunities(
        reverse_pages,
        reverse_graph,
        semantic_threshold=0.99,
        vectorizer=MappingVectorizer(),
    )

    assert forward == reverse


def _linked_graph():
    left = "https://e.test/a"
    right = "https://e.test/b"
    pages = [page(left), page(right)]
    graph = build_weighted_internal_link_graph(
        pages,
        [
            {
                "source_url": left,
                "target_url": right,
                "anchor_text": "Products",
                "ancestor_tags": ["a", "nav"],
                "ancestor_roles": ["navigation"],
            }
        ],
    )
    return left, right, pages, graph


def _node(graph, url):
    return next(row for row in graph["nodes"] if row["url"] == url)


def test_forged_weighted_in_fails_closed():
    left, right, pages, graph = _linked_graph()
    forged = deepcopy(graph)
    _node(forged, right)["weighted_in"] += 10.0

    result = contextual_internal_link_opportunities(
        pages,
        forged,
        semantic_threshold=0.99,
        vectorizer=MappingVectorizer(),
    )

    assert result["state"] == "not_verified"
    assert result["graph_integrity_state"] == "not_verified"
    assert result["reason"] == "graph_node_weight_mismatch"
    assert result["candidate_count"] == 0


def test_forged_weighted_out_fails_closed():
    left, right, pages, graph = _linked_graph()
    forged = deepcopy(graph)
    _node(forged, left)["weighted_out"] += 10.0

    result = contextual_internal_link_opportunities(
        pages,
        forged,
        semantic_threshold=0.99,
        vectorizer=MappingVectorizer(),
    )

    assert result["state"] == "not_verified"
    assert result["reason"] == "graph_node_weight_mismatch"
    assert result["candidate_count"] == 0


def test_forged_observed_in_edge_count_fails_closed():
    left, right, pages, graph = _linked_graph()
    forged = deepcopy(graph)
    _node(forged, right)["observed_in_edge_count"] += 1

    result = contextual_internal_link_opportunities(
        pages,
        forged,
        semantic_threshold=0.99,
        vectorizer=MappingVectorizer(),
    )

    assert result["state"] == "not_verified"
    assert result["reason"] == "graph_node_edge_count_mismatch"
    assert result["candidate_count"] == 0


def test_forged_observed_out_edge_count_fails_closed():
    left, right, pages, graph = _linked_graph()
    forged = deepcopy(graph)
    _node(forged, left)["observed_out_edge_count"] += 1

    result = contextual_internal_link_opportunities(
        pages,
        forged,
        semantic_threshold=0.99,
        vectorizer=MappingVectorizer(),
    )

    assert result["state"] == "not_verified"
    assert result["reason"] == "graph_node_edge_count_mismatch"
    assert result["candidate_count"] == 0
