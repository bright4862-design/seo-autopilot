from app.semantic_graph_evidence_template_zone_opportunity_bound import (
    TEMPLATE_ZONE_OPPORTUNITY_BOUND_GRAPH_ENVELOPE_VERSION,
    build_template_zone_opportunity_bound_semantic_graph_evidence,
)
from app.semantic_graph_template_zone_opportunity import (
    RAW_ZONE_TEMPLATE_CONTEXTUAL_OPPORTUNITY_VERSION,
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
    version = "template_zone_opportunity_binding_v1"

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


def listing_link(source, target):
    return {
        "source_url": source,
        "target_url": target,
        "anchor_text": "Related guide",
        "ancestor_tags": ["a", "div"],
        "ancestor_classes": "related listing cards",
        "repeated_sibling_links": 4,
    }


def by_direction(result):
    return {
        (row["source_url"], row["target_url"]): row
        for row in result["raw_zone_template_contextual_internal_link_opportunities"]["candidates"]
    }


def test_v10_binds_directed_opportunities_to_raw_zone_template_flow_without_extra_vector_calls():
    source = "https://e.test/products/a"
    target = "https://e.test/guides/b"
    vectorizer = CountingVectorizer()

    result = build_template_zone_opportunity_bound_semantic_graph_evidence(
        [page(source, "product"), page(target, "guide")],
        [nav_link(source, target)],
        vectorizer=vectorizer,
        cluster_threshold=0.99,
        cannibalization_threshold=0.99,
        contextual_threshold=0.58,
    )

    assert result["version"] == TEMPLATE_ZONE_OPPORTUNITY_BOUND_GRAPH_ENVELOPE_VERSION
    assert result["raw_zone_template_contextual_opportunity_version"] == (
        RAW_ZONE_TEMPLATE_CONTEXTUAL_OPPORTUNITY_VERSION
    )
    assert vectorizer.calls == 2

    rows = by_direction(result)
    forward = rows[(source, target)]
    reverse = rows[(target, source)]
    assert forward["reason"] == "existing_non_contextual_edge_contextual_upgrade"
    assert forward["raw_zone_template_flow_present"] is True
    assert forward["raw_zone_template_flow_link_occurrence_count"] == 1
    assert forward["raw_zone_template_flow_zone_occurrence_counts"]["navigation"] == 1
    assert reverse["reason"] == "no_observed_edge_in_assessed_sample"
    assert reverse["raw_zone_template_flow_present"] is False
    assert reverse["raw_zone_template_flow_link_occurrence_count"] == 0
    assert result["sitewide_link_absence_claim"] is False
    assert result["customer_fix_created"] is False


def test_v10_preserves_mixed_non_contextual_zone_evidence_for_upgrade_candidate():
    source = "https://e.test/products/a"
    target = "https://e.test/guides/b"

    result = build_template_zone_opportunity_bound_semantic_graph_evidence(
        [page(source, "product"), page(target, "guide")],
        [nav_link(source, target), listing_link(source, target)],
        vectorizer=CountingVectorizer(),
        cluster_threshold=0.99,
        cannibalization_threshold=0.99,
        contextual_threshold=0.58,
    )

    forward = by_direction(result)[(source, target)]
    assert forward["observed_edge_present"] is True
    assert forward["observed_contextual_edge_present"] is False
    assert forward["raw_zone_template_flow_link_occurrence_count"] == 2
    assert forward["raw_zone_template_flow_directed_edge_count"] == 1
    assert forward["raw_zone_template_flow_mixed_zone_directed_edge_count"] == 1
    assert forward["raw_zone_template_flow_zone_occurrence_counts"]["navigation"] == 1
    assert forward["raw_zone_template_flow_zone_occurrence_counts"]["listing"] == 1


def test_v10_preserves_partial_semantic_coverage_and_does_not_invent_candidates():
    first = page("https://e.test/a", "article")
    second = page("https://e.test/b", "article")

    class PartialVectorizer(CountingVectorizer):
        def vectors(self, pages):
            self.calls += 1
            return {pages[0]["url"]: {"shared_intent": 1.0}}

    vectorizer = PartialVectorizer()
    result = build_template_zone_opportunity_bound_semantic_graph_evidence(
        [first, second],
        [],
        vectorizer=vectorizer,
    )

    assert vectorizer.calls == 2
    assert result["semantic_vector_coverage_state"] == "partial"
    assert result["state"] == "partial"
    opportunities = result["raw_zone_template_contextual_internal_link_opportunities"]
    assert opportunities["state"] == "no_candidate_observed"
    assert opportunities["candidate_count"] == 0
    assert opportunities["sitewide_link_absence_claim"] is False
    assert opportunities["sitewide_link_distribution_claim"] is False
