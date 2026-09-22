from app.semantic_graph_evidence_bound import (
    VECTOR_BOUND_GRAPH_ENVELOPE_VERSION,
    build_vector_bound_semantic_graph_evidence,
)
from app.semantic_graph_template_opportunity import TEMPLATE_CONTEXTUAL_OPPORTUNITY_VERSION


def page(url, family):
    return {
        "url": url,
        "status_code": 200,
        "page_evidence_class": "usable_html",
        "indexable": True,
        "page_template_family": family,
    }


def navigation_link(source, target):
    return {
        "source_url": source,
        "target_url": target,
        "anchor_text": "shared topic",
        "ancestor_tags": ["a", "nav"],
    }


class StableVectorizer:
    version = "stable_template_opportunity_envelope_test_v1"

    def __init__(self):
        self.calls = 0

    def vectors(self, pages):
        self.calls += 1
        return {row["url"]: {"shared": 1.0} for row in pages}


def test_preferred_envelope_exposes_template_bound_contextual_opportunities():
    article = "https://e.test/articles/a"
    product = "https://e.test/products/a"
    pages = [page(article, "article"), page(product, "product")]
    vectorizer = StableVectorizer()

    result = build_vector_bound_semantic_graph_evidence(
        pages,
        [navigation_link(article, product)],
        vectorizer=vectorizer,
        cluster_threshold=0.99,
        cannibalization_threshold=0.99,
        contextual_threshold=0.5,
    )

    assert result["version"] == VECTOR_BOUND_GRAPH_ENVELOPE_VERSION
    assert result["state"] == "verified"
    assert result["template_contextual_opportunity_version"] == TEMPLATE_CONTEXTUAL_OPPORTUNITY_VERSION
    bound = result["template_contextual_internal_link_opportunities"]
    assert bound["state"] == "candidate"
    assert bound["template_integrity_state"] == "verified"
    assert bound["graph_integrity_state"] == "verified"
    candidate = next(
        row
        for row in bound["candidates"]
        if row["source_url"] == article and row["target_url"] == product
    )
    assert candidate["observed_edge_present"] is True
    assert candidate["existing_strongest_zone"] == "navigation"
    assert candidate["observed_template_flow_present"] is True
    assert candidate["observed_template_flow_directed_edge_count"] == 1
    assert candidate["sitewide_template_flow_claim"] is False
    assert result["customer_fix_created"] is False
    assert vectorizer.calls == 2


def test_preferred_envelope_keeps_unobserved_template_flow_sample_scoped():
    pages = [
        page("https://e.test/articles/a", "article"),
        page("https://e.test/products/a", "product"),
    ]

    result = build_vector_bound_semantic_graph_evidence(
        pages,
        [],
        vectorizer=StableVectorizer(),
        cluster_threshold=0.99,
        cannibalization_threshold=0.99,
        contextual_threshold=0.5,
    )

    assert result["state"] == "verified"
    bound = result["template_contextual_internal_link_opportunities"]
    assert bound["state"] == "candidate"
    assert bound["candidate_count"] == 2
    assert all(row["observed_template_flow_present"] is False for row in bound["candidates"])
    assert all(
        row["template_flow_evidence_state"] == "no_observed_flow_in_assessed_sample"
        for row in bound["candidates"]
    )
    assert bound["sitewide_link_absence_claim"] is False
    assert bound["sitewide_template_flow_claim"] is False


def test_preferred_envelope_reports_no_candidate_without_inventing_absence():
    pages = [
        page("https://e.test/articles/a", "article"),
        page("https://e.test/products/a", "product"),
    ]

    result = build_vector_bound_semantic_graph_evidence(
        pages,
        [],
        vectorizer=StableVectorizer(),
        cluster_threshold=1.0,
        cannibalization_threshold=1.0,
        contextual_threshold=1.0,
    )

    # Identical stable vectors still produce 1.0 similarity, so suppress both
    # contextual candidates with already-contextual observed edges instead.
    result = build_vector_bound_semantic_graph_evidence(
        pages,
        [
            {
                "source_url": pages[0]["url"],
                "target_url": pages[1]["url"],
                "anchor_text": "shared topic",
                "ancestor_tags": ["a", "main"],
            },
            {
                "source_url": pages[1]["url"],
                "target_url": pages[0]["url"],
                "anchor_text": "shared topic",
                "ancestor_tags": ["a", "main"],
            },
        ],
        vectorizer=StableVectorizer(),
        cluster_threshold=1.0,
        cannibalization_threshold=1.0,
        contextual_threshold=1.0,
    )

    bound = result["template_contextual_internal_link_opportunities"]
    assert result["state"] == "verified"
    assert bound["state"] == "no_candidate_observed"
    assert bound["candidate_count"] == 0
    assert bound["candidates"] == []
    assert bound["sitewide_link_absence_claim"] is False
    assert bound["sitewide_template_flow_claim"] is False
