from copy import deepcopy

import pytest

from app.semantic_graph import build_weighted_internal_link_graph
from app.semantic_graph_analysis_bound import (
    VECTOR_BOUND_SEMANTIC_ANALYSIS_VERSION,
    vector_bound_semantic_analysis_evidence,
)
from app.semantic_graph_vector_contract import SEMANTIC_VECTOR_CONTRACT_VERSION


def page(url, *, indexable=True):
    return {
        "url": url,
        "status_code": 200,
        "page_evidence_class": "usable_html",
        "indexable": indexable,
    }


class MappingVectorizer:
    version = "mapping_v1"

    def __init__(self):
        self.calls = 0

    def vectors(self, pages):
        self.calls += 1
        return {row["url"]: {"shared_intent": 1.0} for row in pages}


class ThirdCallChangesVectorizer:
    version = "third_call_changes_v1"

    def __init__(self):
        self.calls = 0

    def vectors(self, pages):
        self.calls += 1
        weight = 1.0 if self.calls <= 2 else 999.0
        return {row["url"]: {"shared_intent": weight} for row in pages}


class NondeterministicVectorizer:
    version = "nondeterministic_v1"

    def __init__(self):
        self.calls = 0

    def vectors(self, pages):
        self.calls += 1
        weight = 1.0 if self.calls == 1 else 2.0
        return {row["url"]: {"shared_intent": weight} for row in pages}


class ForeignVectorizer:
    version = "foreign_v1"

    def __init__(self):
        self.calls = 0

    def vectors(self, pages):
        self.calls += 1
        return {
            pages[0]["url"]: {"shared_intent": 1.0},
            "https://foreign.test/page": {"shared_intent": 1.0},
        }


class CountingVectorizer:
    version = "counting_v1"

    def __init__(self):
        self.calls = 0

    def vectors(self, pages):
        self.calls += 1
        return {row["url"]: {"shared_intent": 1.0} for row in pages}


def test_valid_bundle_uses_one_verified_snapshot_for_all_semantic_outputs():
    left = "https://e.test/a"
    right = "https://e.test/b"
    pages = [page(left), page(right)]
    graph = build_weighted_internal_link_graph(pages, [])
    vectorizer = MappingVectorizer()

    result = vector_bound_semantic_analysis_evidence(
        pages,
        graph,
        vectorizer=vectorizer,
        cluster_threshold=0.99,
        cannibalization_threshold=0.99,
        contextual_threshold=0.99,
    )

    assert result["version"] == VECTOR_BOUND_SEMANTIC_ANALYSIS_VERSION
    assert result["semantic_vector_contract_version"] == SEMANTIC_VECTOR_CONTRACT_VERSION
    assert result["semantic_vector_integrity_state"] == "verified"
    assert result["semantic_vector_determinism_verified"] is True
    assert result["graph_integrity_state"] == "verified"
    assert vectorizer.calls == 2
    assert result["semantic_clusters"]["state"] == "candidate"
    assert len(result["semantic_clusters"]["clusters"]) == 1
    assert result["cannibalization_candidates"]["candidate_count"] == 1
    assert result["contextual_internal_link_opportunities"]["candidate_count"] == 2
    assert result["customer_fix_created"] is False


def test_underlying_adapter_is_never_called_after_contract_verification():
    left = "https://e.test/a"
    right = "https://e.test/b"
    pages = [page(left), page(right)]
    graph = build_weighted_internal_link_graph(pages, [])
    vectorizer = ThirdCallChangesVectorizer()

    result = vector_bound_semantic_analysis_evidence(
        pages,
        graph,
        vectorizer=vectorizer,
        cluster_threshold=0.99,
        cannibalization_threshold=0.99,
        contextual_threshold=0.99,
    )

    assert vectorizer.calls == 2
    assert result["semantic_vector_integrity_state"] == "verified"
    assert result["semantic_clusters"]["state"] == "candidate"
    assert result["cannibalization_candidates"]["candidate_count"] == 1
    assert result["contextual_internal_link_opportunities"]["candidate_count"] == 2


def test_nondeterministic_vectors_fail_closed_before_semantic_analyzers():
    left = "https://e.test/a"
    right = "https://e.test/b"
    pages = [page(left), page(right)]
    graph = build_weighted_internal_link_graph(pages, [])
    vectorizer = NondeterministicVectorizer()

    result = vector_bound_semantic_analysis_evidence(
        pages,
        graph,
        vectorizer=vectorizer,
    )

    assert vectorizer.calls == 2
    assert result["semantic_vector_integrity_state"] == "not_verified"
    assert result["semantic_vector_integrity_reason"] == "vectorizer_nondeterministic"
    assert result["graph_integrity_state"] == "not_evaluated"
    assert result["semantic_clusters"]["state"] == "not_verified"
    assert result["semantic_clusters"]["clusters"] == []
    assert result["cannibalization_candidates"]["candidate_count"] == 0
    assert result["contextual_internal_link_opportunities"]["candidate_count"] == 0


def test_foreign_vector_population_fails_closed_but_keeps_independent_near_duplicate_evidence():
    left = "https://e.test/a"
    right = "https://e.test/b"
    pages = [page(left), page(right)]
    graph = build_weighted_internal_link_graph(pages, [])
    vectorizer = ForeignVectorizer()

    result = vector_bound_semantic_analysis_evidence(
        pages,
        graph,
        vectorizer=vectorizer,
    )

    assert result["semantic_vector_integrity_state"] == "not_verified"
    assert result["semantic_vector_integrity_reason"] == "vector_population_mismatch"
    assert result["near_duplicate_candidates"]["version"] == "near_duplicate_candidate_v1"
    assert result["near_duplicate_candidates"]["state"] == "not_verified"
    assert result["cannibalization_candidates"]["state"] == "not_verified"


def test_graph_failure_is_isolated_from_valid_cluster_and_cannibalization_evidence():
    left = "https://e.test/a"
    right = "https://e.test/b"
    pages = [page(left), page(right)]
    foreign_graph = build_weighted_internal_link_graph([page(left)], [])
    vectorizer = MappingVectorizer()

    result = vector_bound_semantic_analysis_evidence(
        pages,
        foreign_graph,
        vectorizer=vectorizer,
        cluster_threshold=0.99,
        cannibalization_threshold=0.99,
        contextual_threshold=0.99,
    )

    assert vectorizer.calls == 2
    assert result["semantic_vector_integrity_state"] == "verified"
    assert result["semantic_clusters"]["state"] == "candidate"
    assert result["cannibalization_candidates"]["candidate_count"] == 1
    assert result["graph_integrity_state"] == "not_verified"
    assert result["graph_integrity_reason"] == "graph_page_population_mismatch"
    assert result["contextual_internal_link_opportunities"]["state"] == "not_verified"
    assert result["contextual_internal_link_opportunities"]["candidate_count"] == 0


def test_duplicate_page_identity_fails_before_vectorizer_execution():
    url = "https://e.test/a"
    pages = [page(url), page(url)]
    graph = build_weighted_internal_link_graph([page(url)], [])
    vectorizer = CountingVectorizer()

    result = vector_bound_semantic_analysis_evidence(
        pages,
        graph,
        vectorizer=vectorizer,
    )

    assert vectorizer.calls == 0
    assert result["semantic_vector_integrity_state"] == "not_verified"
    assert result["semantic_vector_integrity_reason"] == "duplicate_page_identity"
    assert result["semantic_clusters"]["state"] == "not_verified"
    assert result["contextual_internal_link_opportunities"]["state"] == "not_verified"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"cluster_threshold": True}, "cluster_threshold out of bounds"),
        ({"contextual_threshold": float("nan")}, "contextual_threshold out of bounds"),
        ({"duplicate_threshold": 0.49}, "duplicate_threshold out of bounds"),
    ],
)
def test_thresholds_fail_closed_before_vectorizer_execution(kwargs, message):
    pages = [page("https://e.test/a"), page("https://e.test/b")]
    graph = build_weighted_internal_link_graph(pages, [])
    vectorizer = CountingVectorizer()

    with pytest.raises(ValueError, match=message):
        vector_bound_semantic_analysis_evidence(
            pages,
            graph,
            vectorizer=vectorizer,
            **kwargs,
        )

    assert vectorizer.calls == 0


def test_bundle_does_not_mutate_pages_or_graph():
    pages = [page("https://e.test/a"), page("https://e.test/b")]
    graph = build_weighted_internal_link_graph(pages, [])
    before_pages = deepcopy(pages)
    before_graph = deepcopy(graph)

    vector_bound_semantic_analysis_evidence(
        pages,
        graph,
        vectorizer=MappingVectorizer(),
    )

    assert pages == before_pages
    assert graph == before_graph
