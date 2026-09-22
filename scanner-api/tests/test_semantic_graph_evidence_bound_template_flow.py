from app.semantic_graph_evidence_bound import (
    VECTOR_BOUND_GRAPH_ENVELOPE_VERSION,
    build_vector_bound_semantic_graph_evidence,
)
from app.semantic_graph_template_flow import TEMPLATE_LINK_FLOW_VERSION


def page(url, family):
    return {
        "url": url,
        "status_code": 200,
        "page_evidence_class": "usable_html",
        "indexable": True,
        "page_template_family": family,
    }


def contextual_link(source, target):
    return {
        "source_url": source,
        "target_url": target,
        "anchor_text": "related topic",
        "ancestor_tags": ["a", "main"],
    }


class StableVectorizer:
    version = "stable_template_flow_test_v1"

    def __init__(self):
        self.calls = 0

    def vectors(self, pages):
        self.calls += 1
        return {row["url"]: {"shared": 1.0} for row in pages}


def test_preferred_envelope_exposes_graph_bound_template_link_flow():
    article = "https://e.test/articles/a"
    product = "https://e.test/products/a"
    pages = [page(article, "article"), page(product, "product")]
    vectorizer = StableVectorizer()

    result = build_vector_bound_semantic_graph_evidence(
        pages,
        [contextual_link(article, product)],
        vectorizer=vectorizer,
        cluster_threshold=0.99,
        cannibalization_threshold=0.99,
        contextual_threshold=0.99,
    )

    assert result["version"] == VECTOR_BOUND_GRAPH_ENVELOPE_VERSION
    assert result["state"] == "verified"
    assert result["template_link_flow_version"] == TEMPLATE_LINK_FLOW_VERSION
    assert result["template_link_flow"]["state"] == "verified"
    assert result["template_link_flow"]["observed_template_group_count"] == 2
    assert result["template_link_flow"]["observed_template_flow_count"] == 1
    assert result["template_link_flow"]["observed_directed_edge_count"] == 1
    assert result["template_link_flow"]["flows"][0]["contextual_edge_count"] == 1
    assert result["sitewide_template_flow_claim"] is False
    assert result["customer_fix_created"] is False
    assert vectorizer.calls == 2


def test_preferred_envelope_keeps_zero_edge_template_flow_truthful_and_verified():
    pages = [
        page("https://e.test/articles/a", "article"),
        page("https://e.test/products/a", "product"),
    ]
    vectorizer = StableVectorizer()

    result = build_vector_bound_semantic_graph_evidence(
        pages,
        [],
        vectorizer=vectorizer,
        cluster_threshold=0.99,
        cannibalization_threshold=0.99,
        contextual_threshold=0.99,
    )

    assert result["state"] == "verified"
    assert result["template_link_flow"]["state"] == "verified"
    assert result["template_link_flow"]["observed_template_flow_count"] == 0
    assert result["template_link_flow"]["observed_directed_edge_count"] == 0
    assert result["template_link_flow"]["flows"] == []
    assert result["template_link_flow"]["sitewide_link_absence_claim"] is False
