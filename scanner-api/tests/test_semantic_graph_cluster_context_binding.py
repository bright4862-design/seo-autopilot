from app.semantic_graph_evidence_cluster_context_bound import (
    CLUSTER_CONTEXT_BOUND_GRAPH_ENVELOPE_VERSION,
    build_cluster_context_bound_semantic_graph_evidence,
)
from app.semantic_graph_opportunity_cluster_context import (
    CLUSTER_CONTEXTUAL_OPPORTUNITY_VERSION,
)


SHINGLES = ["aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb", "cccccccccccccccc"]


def page(url, family, **extra):
    return {
        "url": url,
        "status_code": 200,
        "page_evidence_class": "usable_html",
        "indexable": True,
        "page_template_family": family,
        "main_text_verified": True,
        "main_text_representation": "sha256_5_token_shingles_v1",
        "main_text": " ".join(SHINGLES),
        **extra,
    }


def nav_link(source, target):
    return {
        "source_url": source,
        "target_url": target,
        "anchor_text": "Pricing",
        "ancestor_tags": ["a", "nav"],
        "ancestor_roles": ["navigation"],
    }


class CountingVectorizer:
    version = "cluster_context_binding_v1"

    def __init__(self):
        self.calls = 0

    def vectors(self, pages):
        self.calls += 1
        return {row["url"]: {"shared_intent": 1.0} for row in pages}


class DistinctVectorizer:
    version = "cluster_context_distinct_binding_v1"

    def __init__(self):
        self.calls = 0

    def vectors(self, pages):
        self.calls += 1
        return {
            row["url"]: {f"term_{index}": 1.0}
            for index, row in enumerate(pages)
        }


def test_v14_adds_same_cluster_context_without_extra_vector_calls():
    source = "https://e.test/"
    pricing = "https://e.test/pricing"
    vectorizer = CountingVectorizer()

    result = build_cluster_context_bound_semantic_graph_evidence(
        [page(source, "home"), page(pricing, "pricing_page")],
        [nav_link(source, pricing)],
        vectorizer=vectorizer,
        seed_urls=[source],
        cluster_threshold=0.99,
        cannibalization_threshold=0.99,
        contextual_threshold=0.58,
    )

    assert result["version"] == CLUSTER_CONTEXT_BOUND_GRAPH_ENVELOPE_VERSION
    assert (
        result["cluster_contextual_opportunity_version"]
        == CLUSTER_CONTEXTUAL_OPPORTUNITY_VERSION
    )
    assert vectorizer.calls == 2
    evidence = result["cluster_contextual_internal_link_opportunities"]
    assert evidence["state"] == "candidate"
    row = next(
        candidate
        for candidate in evidence["candidates"]
        if candidate["source_url"] == source and candidate["target_url"] == pricing
    )
    assert row["semantic_cluster_relation"] == "same_cluster"
    assert row["source_semantic_cluster_id"] == row["target_semantic_cluster_id"]
    assert result["sitewide_semantic_coverage_claim"] is False
    assert result["customer_fix_created"] is False


def test_v14_no_semantic_candidate_remains_verified_without_extra_vector_calls():
    source = "https://e.test/a"
    target = "https://e.test/b"
    vectorizer = DistinctVectorizer()

    result = build_cluster_context_bound_semantic_graph_evidence(
        [page(source, "article"), page(target, "article")],
        [],
        vectorizer=vectorizer,
        seed_urls=[source],
        cluster_threshold=0.99,
        cannibalization_threshold=0.99,
        contextual_threshold=0.99,
    )

    assert vectorizer.calls == 2
    evidence = result["cluster_contextual_internal_link_opportunities"]
    assert evidence["state"] == "no_candidate_observed"
    assert evidence["candidate_count"] == 0
    assert evidence["cluster_context_candidate_population_complete"] is True
    assert evidence["sitewide_semantic_coverage_claim"] is False
    assert result["customer_fix_created"] is False


def test_v14_preserves_v13_seed_failure_while_cluster_context_stays_descriptive():
    source = "https://e.test/"
    pricing = "https://e.test/pricing"
    vectorizer = CountingVectorizer()

    result = build_cluster_context_bound_semantic_graph_evidence(
        [page(source, "home"), page(pricing, "pricing_page")],
        [nav_link(source, pricing)],
        vectorizer=vectorizer,
        seed_urls=["https://e.test/not-assessed"],
        cluster_threshold=0.99,
        cannibalization_threshold=0.99,
        contextual_threshold=0.58,
    )

    assert vectorizer.calls == 2
    assert result["state"] == "not_verified"
    assert result["reason"] == "seed_population_mismatch"
    evidence = result["cluster_contextual_internal_link_opportunities"]
    assert evidence["state"] == "candidate"
    assert evidence["customer_fix_created"] is False
    assert result["customer_fix_created"] is False
