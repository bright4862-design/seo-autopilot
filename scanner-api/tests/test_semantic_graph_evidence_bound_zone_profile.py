from app.semantic_graph_evidence_bound import (
    VECTOR_BOUND_GRAPH_ENVELOPE_VERSION,
    build_vector_bound_semantic_graph_evidence,
)
from app.semantic_graph_zone_profile import LINK_ZONE_OBSERVATION_PROFILE_VERSION


def page(url, family):
    return {
        "url": url,
        "status_code": 200,
        "page_evidence_class": "usable_html",
        "indexable": True,
        "page_template_family": family,
    }


def link(source, target, zone):
    row = {
        "source_url": source,
        "target_url": target,
        "anchor_text": f"{zone} shared topic",
    }
    row["ancestor_tags"] = {
        "contextual": ["a", "main"],
        "navigation": ["a", "nav"],
        "footer": ["a", "footer"],
    }[zone]
    return row


class StableVectorizer:
    version = "stable_zone_profile_envelope_test_v1"

    def vectors(self, pages):
        return {row["url"]: {"shared": 1.0} for row in pages}


def test_preferred_envelope_exposes_raw_observation_bound_link_zone_profile():
    article = "https://e.test/articles/a"
    product = "https://e.test/products/a"
    pages = [page(article, "article"), page(product, "product")]
    links = [
        link(article, product, "footer"),
        link(article, product, "navigation"),
        link(article, product, "contextual"),
    ]

    result = build_vector_bound_semantic_graph_evidence(
        pages,
        links,
        vectorizer=StableVectorizer(),
        cluster_threshold=0.99,
        cannibalization_threshold=0.99,
        contextual_threshold=0.5,
    )

    assert result["version"] == VECTOR_BOUND_GRAPH_ENVELOPE_VERSION
    assert result["state"] == "verified"
    assert (
        result["link_zone_observation_profile_version"]
        == LINK_ZONE_OBSERVATION_PROFILE_VERSION
    )
    profile = result["link_zone_observation_profile"]
    assert profile["state"] == "verified"
    assert profile["observed_assessed_link_occurrence_count"] == 3
    assert profile["observed_directed_edge_count"] == 1
    assert profile["zone_occurrence_counts"]["footer"] == 1
    assert profile["zone_occurrence_counts"]["navigation"] == 1
    assert profile["zone_occurrence_counts"]["contextual"] == 1
    assert profile["edge_profiles"][0]["observed_occurrences"] == 3
    assert profile["edge_profiles"][0]["strongest_observed_zone"] == "contextual"
    assert result["sitewide_link_distribution_claim"] is False
    assert result["customer_fix_created"] is False


def test_preferred_envelope_keeps_zero_observed_links_truthfully_sample_scoped():
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

    profile = result["link_zone_observation_profile"]
    assert result["state"] == "verified"
    assert profile["state"] == "verified"
    assert profile["observed_assessed_link_occurrence_count"] == 0
    assert profile["observed_directed_edge_count"] == 0
    assert profile["edge_profile_count"] == 0
    assert profile["edge_profiles"] == []
    assert profile["sitewide_link_absence_claim"] is False
    assert profile["sitewide_link_distribution_claim"] is False
