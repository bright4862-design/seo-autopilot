from app.semantic_graph_evidence_weighted_route_bound import (
    WEIGHTED_ROUTE_BOUND_GRAPH_ENVELOPE_VERSION,
    build_weighted_route_bound_semantic_graph_evidence,
)
from app.semantic_graph_opportunity_weighted_route import (
    WEIGHTED_ROUTE_CONTEXTUAL_OPPORTUNITY_VERSION,
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
    version = "weighted_route_binding_v1"

    def __init__(self):
        self.calls = 0

    def vectors(self, pages):
        self.calls += 1
        return {row["url"]: {"shared_intent": 1.0} for row in pages}


class DistinctVectorizer:
    version = "weighted_route_distinct_binding_v1"

    def __init__(self):
        self.calls = 0

    def vectors(self, pages):
        self.calls += 1
        return {
            row["url"]: {f"term_{index}": 1.0}
            for index, row in enumerate(pages)
        }


def test_v13_adds_weighted_route_evidence_without_extra_vector_calls():
    source = "https://e.test/"
    pricing = "https://e.test/pricing"
    vectorizer = CountingVectorizer()

    result = build_weighted_route_bound_semantic_graph_evidence(
        [page(source, "home"), page(pricing, "pricing_page")],
        [nav_link(source, pricing)],
        vectorizer=vectorizer,
        seed_urls=[source],
        cluster_threshold=0.99,
        cannibalization_threshold=0.99,
        contextual_threshold=0.58,
    )

    assert result["version"] == WEIGHTED_ROUTE_BOUND_GRAPH_ENVELOPE_VERSION
    assert (
        result["weighted_route_contextual_opportunity_version"]
        == WEIGHTED_ROUTE_CONTEXTUAL_OPPORTUNITY_VERSION
    )
    assert vectorizer.calls == 2
    weighted = result["weighted_route_contextual_internal_link_opportunities"]
    assert weighted["state"] == "candidate"
    row = next(
        candidate
        for candidate in weighted["candidates"]
        if candidate["source_url"] == source and candidate["target_url"] == pricing
    )
    assert row["observed_widest_path_hops"] == 1
    assert row["observed_widest_path_bottleneck_edge"]["strongest_zone"] == "navigation"
    assert result["sitewide_reachability_claim"] is False
    assert result["sitewide_orphan_claim"] is False
    assert result["customer_fix_created"] is False


def test_v13_no_semantic_candidate_remains_verified_without_extra_vector_calls():
    source = "https://e.test/a"
    target = "https://e.test/b"
    vectorizer = DistinctVectorizer()

    result = build_weighted_route_bound_semantic_graph_evidence(
        [page(source, "article"), page(target, "article")],
        [],
        vectorizer=vectorizer,
        seed_urls=[source],
        cluster_threshold=0.99,
        cannibalization_threshold=0.99,
        contextual_threshold=0.99,
    )

    assert vectorizer.calls == 2
    weighted = result["weighted_route_contextual_internal_link_opportunities"]
    assert weighted["state"] == "no_candidate_observed"
    assert weighted["candidate_count"] == 0
    assert weighted["weighted_route_candidate_population_complete"] is True
    assert weighted["sitewide_link_absence_claim"] is False
    assert result["customer_fix_created"] is False


def test_v13_preserves_v12_seed_failure_while_weighted_route_evidence_stays_descriptive():
    source = "https://e.test/"
    pricing = "https://e.test/pricing"
    vectorizer = CountingVectorizer()

    result = build_weighted_route_bound_semantic_graph_evidence(
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
    assert result["money_page_reachability"]["state"] == "not_verified"
    weighted = result["weighted_route_contextual_internal_link_opportunities"]
    assert weighted["state"] == "candidate"
    assert weighted["customer_fix_created"] is False
    assert result["customer_fix_created"] is False
