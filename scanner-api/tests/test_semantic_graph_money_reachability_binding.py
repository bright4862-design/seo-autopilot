from app.semantic_graph_evidence_money_reachability_bound import (
    MONEY_REACHABILITY_BOUND_GRAPH_ENVELOPE_VERSION,
    build_money_reachability_bound_semantic_graph_evidence,
)
from app.semantic_graph_money_reachability import (
    WEIGHTED_MONEY_PAGE_REACHABILITY_VERSION,
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


class CountingVectorizer:
    version = "money_reachability_binding_v1"

    def __init__(self):
        self.calls = 0

    def vectors(self, pages):
        self.calls += 1
        return {row["url"]: {"shared_intent": 1.0} for row in pages}


def nav_link(source, target):
    return {
        "source_url": source,
        "target_url": target,
        "anchor_text": "Pricing",
        "ancestor_tags": ["a", "nav"],
        "ancestor_roles": ["navigation"],
    }


def test_v12_adds_weighted_money_reachability_without_extra_vector_calls():
    seed = "https://e.test/"
    pricing = "https://e.test/pricing"
    vectorizer = CountingVectorizer()

    result = build_money_reachability_bound_semantic_graph_evidence(
        [page(seed, "home"), page(pricing, "pricing_page")],
        [nav_link(seed, pricing)],
        vectorizer=vectorizer,
        seed_urls=[seed],
        cluster_threshold=0.99,
        cannibalization_threshold=0.99,
        contextual_threshold=0.58,
    )

    assert result["version"] == MONEY_REACHABILITY_BOUND_GRAPH_ENVELOPE_VERSION
    assert result["money_page_reachability_version"] == WEIGHTED_MONEY_PAGE_REACHABILITY_VERSION
    assert vectorizer.calls == 2
    reachability = result["money_page_reachability"]
    assert reachability["state"] == "verified"
    assert reachability["classified_money_page_count"] == 1
    assert reachability["pages"][0]["observed_depth_from_seed"] == 1
    assert reachability["pages"][0]["observed_navigation_in_edge_count"] == 1
    assert result["sitewide_reachability_claim"] is False
    assert result["sitewide_orphan_claim"] is False
    assert result["customer_fix_created"] is False


def test_v12_invalid_seed_binding_fails_closed_without_changing_vector_call_budget():
    seed = "https://e.test/"
    pricing = "https://e.test/pricing"
    vectorizer = CountingVectorizer()

    result = build_money_reachability_bound_semantic_graph_evidence(
        [page(seed, "home"), page(pricing, "pricing_page")],
        [nav_link(seed, pricing)],
        vectorizer=vectorizer,
        seed_urls=["https://e.test/not-assessed"],
        cluster_threshold=0.99,
        cannibalization_threshold=0.99,
    )

    assert vectorizer.calls == 2
    assert result["state"] == "not_verified"
    assert result["reason"] == "seed_population_mismatch"
    assert result["money_page_reachability"]["state"] == "not_verified"
    assert result["customer_fix_created"] is False


def test_v12_zero_money_pages_remains_non_sitewide_and_does_not_invent_candidates():
    first = "https://e.test/a"
    second = "https://e.test/b"
    vectorizer = CountingVectorizer()

    result = build_money_reachability_bound_semantic_graph_evidence(
        [page(first, "article"), page(second, "article")],
        [],
        vectorizer=vectorizer,
        seed_urls=[first],
        cluster_threshold=0.99,
        cannibalization_threshold=0.99,
    )

    assert vectorizer.calls == 2
    reachability = result["money_page_reachability"]
    assert reachability["state"] == "verified"
    assert reachability["classified_money_page_count"] == 0
    assert reachability["pages"] == []
    assert reachability["sitewide_reachability_claim"] is False
    assert result["sitewide_navigation_absence_claim"] is False
