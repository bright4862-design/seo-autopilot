from copy import deepcopy

import pytest

from app.semantic_graph import build_weighted_internal_link_graph
from app.semantic_graph_analysis_near_duplicate_cluster_bound import (
    NEAR_DUPLICATE_CLUSTER_BOUND_SEMANTIC_ANALYSIS_VERSION,
    _bind_near_duplicate_cluster_evidence,
    near_duplicate_cluster_bound_semantic_analysis_evidence,
)
from app.semantic_graph_analysis_profile_bound import (
    cluster_profile_bound_semantic_analysis_evidence,
)
from app.semantic_graph_evidence_near_duplicate_cluster_bound import (
    NEAR_DUPLICATE_CLUSTER_BOUND_GRAPH_ENVELOPE_VERSION,
    build_near_duplicate_cluster_bound_semantic_graph_evidence,
)
from app.semantic_graph_near_duplicate_clusters import NEAR_DUPLICATE_CLUSTER_VERSION


SHINGLES = ["aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb", "cccccccccccccccc"]


def page(url, *, shingles=SHINGLES, b10_verified=True):
    row = {
        "url": url,
        "status_code": 200,
        "page_evidence_class": "usable_html",
        "indexable": True,
        "page_template_family": "article",
    }
    if b10_verified:
        row.update(
            {
                "main_text_verified": True,
                "main_text_representation": "sha256_5_token_shingles_v1",
                "main_text": " ".join(shingles),
            }
        )
    return row


class CompleteVectorizer:
    version = "complete_b10_cluster_binding_v1"

    def __init__(self):
        self.calls = 0

    def vectors(self, pages):
        self.calls += 1
        return {row["url"]: {"shared_intent": 1.0} for row in pages}


def test_v4_binds_pair_candidates_and_b10_clusters_without_extra_vector_calls():
    pages = [page("https://e.test/a"), page("https://e.test/b"), page("https://e.test/c")]
    graph = build_weighted_internal_link_graph(pages, [])
    vectorizer = CompleteVectorizer()

    result = near_duplicate_cluster_bound_semantic_analysis_evidence(
        pages,
        graph,
        vectorizer=vectorizer,
        duplicate_threshold=0.82,
        cluster_threshold=0.99,
    )

    assert result["version"] == NEAR_DUPLICATE_CLUSTER_BOUND_SEMANTIC_ANALYSIS_VERSION
    assert vectorizer.calls == 2
    assert result["near_duplicate_cluster_version"] == NEAR_DUPLICATE_CLUSTER_VERSION
    assert result["near_duplicate_cluster_binding_state"] == "verified"
    assert result["near_duplicate_candidates"]["candidate_count"] == 3
    cluster = result["near_duplicate_cluster_evidence"]
    assert cluster["qualifying_pair_count"] == 3
    assert cluster["cluster_count"] == 1
    assert cluster["clusters"][0]["page_count"] == 3
    assert result["sitewide_near_duplicate_claim"] is False
    assert result["customer_fix_created"] is False


def test_v4_partial_b10_population_stays_explicitly_partial():
    pages = [
        page("https://e.test/a"),
        page("https://e.test/b"),
        page("https://e.test/c", b10_verified=False),
    ]
    graph = build_weighted_internal_link_graph(pages, [])

    result = near_duplicate_cluster_bound_semantic_analysis_evidence(
        pages,
        graph,
        vectorizer=CompleteVectorizer(),
    )

    assert result["semantic_vector_coverage_state"] == "complete"
    assert result["near_duplicate_cluster_binding_state"] == "verified"
    assert result["near_duplicate_cluster_coverage_state"] == "partial"
    cluster = result["near_duplicate_cluster_evidence"]
    assert cluster["eligible_page_count"] == 2
    assert cluster["unverified_main_content_page_count"] == 1
    assert cluster["sitewide_coverage_claim"] is False


def test_v4_missing_b10_evidence_is_unknown_not_a_clean_duplicate_result():
    pages = [
        page("https://e.test/a", b10_verified=False),
        page("https://e.test/b", b10_verified=False),
    ]
    graph = build_weighted_internal_link_graph(pages, [])

    result = near_duplicate_cluster_bound_semantic_analysis_evidence(
        pages,
        graph,
        vectorizer=CompleteVectorizer(),
    )

    assert result["semantic_vector_integrity_state"] == "verified"
    assert result["near_duplicate_candidates"]["state"] == "not_verified"
    assert result["near_duplicate_cluster_binding_state"] == "not_verified"
    assert result["near_duplicate_cluster_evidence"]["state"] == "not_verified"
    assert result["near_duplicate_cluster_evidence"]["reason"] == "no_verified_b10_main_content"


def test_binder_fails_closed_when_pair_and_cluster_full_counts_diverge():
    pages = [page("https://e.test/a"), page("https://e.test/b")]
    graph = build_weighted_internal_link_graph(pages, [])
    base = cluster_profile_bound_semantic_analysis_evidence(
        pages,
        graph,
        vectorizer=CompleteVectorizer(),
    )
    tampered = deepcopy(base)
    tampered["near_duplicate_candidates"]["candidate_count"] += 1

    result = _bind_near_duplicate_cluster_evidence(
        pages,
        tampered,
        duplicate_threshold=0.82,
    )

    assert result["near_duplicate_cluster_binding_state"] == "not_verified"
    assert result["near_duplicate_cluster_binding_reason"] == (
        "pair_cluster_qualifying_pair_count_mismatch"
    )
    assert result["customer_fix_created"] is False


def test_binder_does_not_mutate_input_analysis_or_pages():
    pages = [page("https://e.test/a"), page("https://e.test/b")]
    graph = build_weighted_internal_link_graph(pages, [])
    base = cluster_profile_bound_semantic_analysis_evidence(
        pages,
        graph,
        vectorizer=CompleteVectorizer(),
    )
    before_pages = deepcopy(pages)
    before_base = deepcopy(base)

    _bind_near_duplicate_cluster_evidence(
        pages,
        base,
        duplicate_threshold=0.82,
    )

    assert pages == before_pages
    assert base == before_base


def test_v8_envelope_carries_v4_b10_cluster_evidence_with_two_adapter_calls():
    pages = [page("https://e.test/a"), page("https://e.test/b")]
    vectorizer = CompleteVectorizer()

    result = build_near_duplicate_cluster_bound_semantic_graph_evidence(
        pages,
        [],
        vectorizer=vectorizer,
        cluster_threshold=0.99,
        cannibalization_threshold=0.99,
        contextual_threshold=0.99,
    )

    assert result["version"] == NEAR_DUPLICATE_CLUSTER_BOUND_GRAPH_ENVELOPE_VERSION
    assert result["semantic_analysis_version"] == NEAR_DUPLICATE_CLUSTER_BOUND_SEMANTIC_ANALYSIS_VERSION
    assert result["semantic_analysis"]["version"] == NEAR_DUPLICATE_CLUSTER_BOUND_SEMANTIC_ANALYSIS_VERSION
    assert vectorizer.calls == 2
    assert result["near_duplicate_cluster_binding_state"] == "verified"
    assert result["near_duplicate_cluster_evidence"]["cluster_count"] == 1
    assert result["sitewide_near_duplicate_claim"] is False
    assert result["sitewide_orphan_claim"] is False
    assert result["sitewide_link_absence_claim"] is False
    assert result["customer_fix_created"] is False


def test_v8_partial_b10_coverage_does_not_poison_independent_verified_graph_evidence():
    pages = [
        page("https://e.test/a"),
        page("https://e.test/b"),
        page("https://e.test/c", b10_verified=False),
    ]

    result = build_near_duplicate_cluster_bound_semantic_graph_evidence(
        pages,
        [],
        vectorizer=CompleteVectorizer(),
        cluster_threshold=0.99,
        cannibalization_threshold=0.99,
        contextual_threshold=0.99,
    )

    assert result["state"] == "verified"
    assert result["semantic_vector_coverage_state"] == "complete"
    assert result["near_duplicate_cluster_coverage_state"] == "partial"
    assert result["near_duplicate_cluster_evidence"]["sitewide_coverage_claim"] is False


def test_v8_duplicate_identity_fails_before_vectorizer_execution():
    duplicate = page("https://e.test/a")
    vectorizer = CompleteVectorizer()

    with pytest.raises(ValueError, match="duplicate_page_identity"):
        build_near_duplicate_cluster_bound_semantic_graph_evidence(
            [duplicate, dict(duplicate)],
            [],
            vectorizer=vectorizer,
        )

    assert vectorizer.calls == 0
