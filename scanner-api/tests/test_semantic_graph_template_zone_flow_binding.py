from app.semantic_graph_evidence_template_zone_flow_bound import (
    TEMPLATE_ZONE_FLOW_BOUND_GRAPH_ENVELOPE_VERSION,
    build_template_zone_flow_bound_semantic_graph_evidence,
)
from app.semantic_graph_template_zone_flow import TEMPLATE_LINK_ZONE_FLOW_VERSION


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
    version = "template_zone_flow_binding_v1"

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


def contextual_link(source, target):
    return {
        "source_url": source,
        "target_url": target,
        "anchor_text": "Read the detailed guide",
        "ancestor_tags": ["a", "article", "main"],
        "ancestor_roles": ["article", "main"],
    }


def test_v9_carries_raw_zone_template_flow_without_extra_semantic_adapter_calls():
    source = "https://e.test/products/a"
    target = "https://e.test/guides/b"
    pages = [page(source, "product"), page(target, "guide")]
    links = [nav_link(source, target), contextual_link(source, target)]
    vectorizer = CountingVectorizer()

    result = build_template_zone_flow_bound_semantic_graph_evidence(
        pages,
        links,
        vectorizer=vectorizer,
        cluster_threshold=0.99,
        cannibalization_threshold=0.99,
        contextual_threshold=0.99,
    )

    assert result["version"] == TEMPLATE_ZONE_FLOW_BOUND_GRAPH_ENVELOPE_VERSION
    assert result["template_link_zone_flow_version"] == TEMPLATE_LINK_ZONE_FLOW_VERSION
    assert vectorizer.calls == 2
    template_zone_flow = result["template_link_zone_flow"]
    assert template_zone_flow["state"] == "verified"
    assert template_zone_flow["observed_link_occurrence_count"] == 2
    assert template_zone_flow["observed_directed_edge_count"] == 1
    assert template_zone_flow["flows"][0]["mixed_zone_directed_edge_count"] == 1
    assert result["sitewide_template_flow_claim"] is False
    assert result["sitewide_link_distribution_claim"] is False
    assert result["sitewide_link_absence_claim"] is False
    assert result["customer_fix_created"] is False


def test_v9_preserves_partial_semantic_coverage_instead_of_promoting_it():
    first = page("https://e.test/a", "article")
    second = page("https://e.test/b", "article")

    class PartialVectorizer(CountingVectorizer):
        def vectors(self, pages):
            self.calls += 1
            return {pages[0]["url"]: {"shared_intent": 1.0}}

    vectorizer = PartialVectorizer()
    result = build_template_zone_flow_bound_semantic_graph_evidence(
        [first, second],
        [],
        vectorizer=vectorizer,
    )

    assert vectorizer.calls == 2
    assert result["semantic_vector_coverage_state"] == "partial"
    assert result["state"] == "partial"
    assert result["template_link_zone_flow"]["state"] == "verified"
    assert result["template_link_zone_flow"]["observed_template_flow_count"] == 0


def test_v9_keeps_b10_cluster_and_template_zone_evidence_side_by_side():
    pages = [page("https://e.test/a", "article"), page("https://e.test/b", "article")]

    result = build_template_zone_flow_bound_semantic_graph_evidence(
        pages,
        [],
        vectorizer=CountingVectorizer(),
        cluster_threshold=0.99,
    )

    assert result["near_duplicate_cluster_binding_state"] == "verified"
    assert result["near_duplicate_cluster_evidence"]["cluster_count"] == 1
    assert result["template_link_zone_flow"]["state"] == "verified"
    assert result["template_link_zone_flow"]["observed_link_occurrence_count"] == 0
