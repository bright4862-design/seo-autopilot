from copy import deepcopy

import pytest

from app.semantic_graph import build_weighted_internal_link_graph
from app.semantic_graph_analysis_profile_bound import (
    CLUSTER_PROFILE_BOUND_SEMANTIC_ANALYSIS_VERSION,
    cluster_profile_bound_semantic_analysis_evidence,
)
from app.semantic_graph_cluster_profile import SEMANTIC_CLUSTER_PROFILE_VERSION
from app.semantic_graph_evidence_cluster_profile_bound import (
    CLUSTER_PROFILE_BOUND_GRAPH_ENVELOPE_VERSION,
    build_cluster_profile_bound_semantic_graph_evidence,
)


def page(url):
    return {
        "url": url,
        "status_code": 200,
        "page_evidence_class": "usable_html",
        "indexable": True,
        "page_template_family": "article",
    }


class CompleteVectorizer:
    version = "complete_profile_binding_v1"

    def __init__(self):
        self.calls = 0

    def vectors(self, pages):
        self.calls += 1
        return {row["url"]: {"shared_intent": 1.0} for row in pages}


class ThirdCallChangesVectorizer:
    version = "third_call_changes_profile_binding_v1"

    def __init__(self):
        self.calls = 0

    def vectors(self, pages):
        self.calls += 1
        weight = 1.0 if self.calls <= 2 else 999.0
        return {row["url"]: {"shared_intent": weight} for row in pages}


class NondeterministicVectorizer:
    version = "nondeterministic_profile_binding_v1"

    def __init__(self):
        self.calls = 0

    def vectors(self, pages):
        self.calls += 1
        weight = 1.0 if self.calls == 1 else 2.0
        return {row["url"]: {"shared_intent": weight} for row in pages}


class PartialVectorizer:
    version = "partial_profile_binding_v1"

    def __init__(self):
        self.calls = 0

    def vectors(self, pages):
        self.calls += 1
        return {
            pages[0]["url"]: {"shared_intent": 1.0},
            pages[1]["url"]: {"shared_intent": 1.0},
        }


class CountingVectorizer:
    version = "counting_profile_binding_v1"

    def __init__(self):
        self.calls = 0

    def vectors(self, pages):
        self.calls += 1
        return {row["url"]: {"shared_intent": 1.0} for row in pages}


def test_v3_profiles_cluster_from_same_validated_snapshot_with_two_adapter_calls():
    pages = [page("https://e.test/a"), page("https://e.test/b")]
    graph = build_weighted_internal_link_graph(pages, [])
    vectorizer = CompleteVectorizer()

    result = cluster_profile_bound_semantic_analysis_evidence(
        pages,
        graph,
        vectorizer=vectorizer,
        cluster_threshold=0.99,
        cannibalization_threshold=0.99,
        contextual_threshold=0.99,
    )

    assert result["version"] == CLUSTER_PROFILE_BOUND_SEMANTIC_ANALYSIS_VERSION
    assert vectorizer.calls == 2
    assert result["semantic_cluster_profile_version"] == SEMANTIC_CLUSTER_PROFILE_VERSION
    assert result["semantic_cluster_profile"]["state"] == "verified"
    assert result["semantic_cluster_profile"]["profile_count"] == 1
    assert result["semantic_cluster_profile"]["profiles"][0]["representative_url"] == (
        "https://e.test/a"
    )
    assert result["customer_fix_created"] is False


def test_v3_never_reinvokes_stateful_adapter_after_contract_verification():
    pages = [page("https://e.test/a"), page("https://e.test/b")]
    graph = build_weighted_internal_link_graph(pages, [])
    vectorizer = ThirdCallChangesVectorizer()

    result = cluster_profile_bound_semantic_analysis_evidence(
        pages,
        graph,
        vectorizer=vectorizer,
        cluster_threshold=0.99,
    )

    assert vectorizer.calls == 2
    assert result["semantic_vector_integrity_state"] == "verified"
    assert result["semantic_cluster_profile"]["state"] == "verified"
    top_terms = result["semantic_cluster_profile"]["profiles"][0]["top_terms"]
    assert top_terms == [{"term": "shared_intent", "centroid_weight": 1.0}]


def test_v3_nondeterministic_adapter_fails_profile_closed():
    pages = [page("https://e.test/a"), page("https://e.test/b")]
    graph = build_weighted_internal_link_graph(pages, [])
    vectorizer = NondeterministicVectorizer()

    result = cluster_profile_bound_semantic_analysis_evidence(
        pages,
        graph,
        vectorizer=vectorizer,
    )

    assert vectorizer.calls == 2
    assert result["semantic_vector_integrity_state"] == "not_verified"
    assert result["semantic_cluster_profile"]["state"] == "not_verified"
    assert result["semantic_cluster_profile"]["profiles"] == []


def test_v3_partial_vector_population_profiles_only_covered_cluster_without_sitewide_claim():
    pages = [
        page("https://e.test/a"),
        page("https://e.test/b"),
        page("https://e.test/c"),
    ]
    graph = build_weighted_internal_link_graph(pages, [])
    vectorizer = PartialVectorizer()

    result = cluster_profile_bound_semantic_analysis_evidence(
        pages,
        graph,
        vectorizer=vectorizer,
        cluster_threshold=0.99,
    )

    assert vectorizer.calls == 2
    profile = result["semantic_cluster_profile"]
    assert result["semantic_vector_coverage_state"] == "partial"
    assert result["semantic_pair_population_complete"] is False
    assert profile["state"] == "verified"
    assert profile["semantic_vector_coverage_state"] == "partial"
    assert profile["semantic_pair_population_complete"] is False
    assert profile["sitewide_semantic_coverage_claim"] is False
    assert profile["profiles"][0]["urls"] == [
        "https://e.test/a",
        "https://e.test/b",
    ]


def test_v3_does_not_mutate_pages_or_graph():
    pages = [page("https://e.test/a"), page("https://e.test/b")]
    graph = build_weighted_internal_link_graph(pages, [])
    before_pages = deepcopy(pages)
    before_graph = deepcopy(graph)

    cluster_profile_bound_semantic_analysis_evidence(
        pages,
        graph,
        vectorizer=CompleteVectorizer(),
    )

    assert pages == before_pages
    assert graph == before_graph


def test_v7_envelope_carries_profile_and_preserves_non_sitewide_non_fix_guards():
    pages = [page("https://e.test/a"), page("https://e.test/b")]
    vectorizer = CompleteVectorizer()

    result = build_cluster_profile_bound_semantic_graph_evidence(
        pages,
        [],
        vectorizer=vectorizer,
        cluster_threshold=0.99,
        cannibalization_threshold=0.99,
        contextual_threshold=0.99,
    )

    assert result["version"] == CLUSTER_PROFILE_BOUND_GRAPH_ENVELOPE_VERSION
    assert result["state"] == "verified"
    assert result["semantic_analysis_version"] == CLUSTER_PROFILE_BOUND_SEMANTIC_ANALYSIS_VERSION
    assert result["semantic_cluster_profile_version"] == SEMANTIC_CLUSTER_PROFILE_VERSION
    assert result["semantic_cluster_profile"]["state"] == "verified"
    assert vectorizer.calls == 2
    assert result["sitewide_orphan_claim"] is False
    assert result["sitewide_link_absence_claim"] is False
    assert result["sitewide_template_flow_claim"] is False
    assert result["sitewide_link_distribution_claim"] is False
    assert result["sitewide_semantic_coverage_claim"] is False
    assert result["customer_fix_created"] is False


def test_v7_partial_vector_population_remains_partial():
    pages = [
        page("https://e.test/a"),
        page("https://e.test/b"),
        page("https://e.test/c"),
    ]
    vectorizer = PartialVectorizer()

    result = build_cluster_profile_bound_semantic_graph_evidence(
        pages,
        [],
        vectorizer=vectorizer,
        cluster_threshold=0.99,
        cannibalization_threshold=0.99,
        contextual_threshold=0.99,
    )

    assert vectorizer.calls == 2
    assert result["state"] == "partial"
    assert result["reason"] == "semantic_vector_coverage_partial"
    assert result["semantic_vector_coverage_state"] == "partial"
    assert result["semantic_cluster_profile"]["state"] == "verified"
    assert result["semantic_cluster_profile"]["semantic_vector_coverage_state"] == "partial"


def test_v7_duplicate_page_identity_fails_before_vectorizer_execution():
    duplicate = page("https://e.test/a")
    vectorizer = CountingVectorizer()

    with pytest.raises(ValueError, match="duplicate_page_identity"):
        build_cluster_profile_bound_semantic_graph_evidence(
            [duplicate, dict(duplicate)],
            [],
            vectorizer=vectorizer,
        )

    assert vectorizer.calls == 0
