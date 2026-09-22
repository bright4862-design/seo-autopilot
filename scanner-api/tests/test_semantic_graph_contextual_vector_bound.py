from copy import deepcopy

from app.semantic_graph import build_weighted_internal_link_graph
from app.semantic_graph_contextual_vector_bound import (
    VECTOR_BOUND_CONTEXTUAL_OPPORTUNITY_VERSION,
    vector_bound_contextual_internal_link_opportunities,
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
    version = "test_mapping_v1"

    def vectors(self, pages):
        return {row["url"]: {"shared_intent": 1.0} for row in pages}


class ForeignVectorizer:
    version = "foreign_mapping_v1"

    def vectors(self, pages):
        return {
            pages[0]["url"]: {"shared_intent": 1.0},
            "https://foreign.test/page": {"shared_intent": 1.0},
        }


class BoolWeightVectorizer:
    version = "bool_weight_v1"

    def vectors(self, pages):
        return {row["url"]: {"shared_intent": True} for row in pages}


class NondeterministicVectorizer:
    version = "nondeterministic_v1"

    def __init__(self):
        self.calls = 0

    def vectors(self, pages):
        self.calls += 1
        weight = 1.0 if self.calls == 1 else 2.0
        return {row["url"]: {"shared_intent": weight} for row in pages}


class ThirdCallChangesVectorizer:
    version = "third_call_changes_v1"

    def __init__(self):
        self.calls = 0

    def vectors(self, pages):
        self.calls += 1
        weight = 1.0 if self.calls <= 2 else 999.0
        return {row["url"]: {"shared_intent": weight} for row in pages}


class CountingVectorizer:
    version = "counting_v1"

    def __init__(self):
        self.calls = 0

    def vectors(self, pages):
        self.calls += 1
        return {row["url"]: {"shared_intent": 1.0} for row in pages}


def test_valid_semantic_vectors_are_bound_before_contextual_opportunity_scoring():
    left = "https://e.test/a"
    right = "https://e.test/b"
    pages = [page(left), page(right)]
    graph = build_weighted_internal_link_graph(pages, [])

    result = vector_bound_contextual_internal_link_opportunities(
        pages,
        graph,
        semantic_threshold=0.99,
        vectorizer=MappingVectorizer(),
    )

    assert result["version"] == VECTOR_BOUND_CONTEXTUAL_OPPORTUNITY_VERSION
    assert result["graph_integrity_state"] == "verified"
    assert result["semantic_vector_integrity_state"] == "verified"
    assert result["semantic_vector_integrity_reason"] == "validated"
    assert (
        result["semantic_vector_contract_version"]
        == SEMANTIC_VECTOR_CONTRACT_VERSION
    )
    assert result["semantic_vector_determinism_checked"] is True
    assert result["semantic_vector_determinism_verified"] is True
    assert result["customer_fix_created"] is False
    assert result["candidate_count"] == 2


def test_foreign_semantic_vector_population_fails_closed():
    left = "https://e.test/a"
    right = "https://e.test/b"
    pages = [page(left), page(right)]
    graph = build_weighted_internal_link_graph(pages, [])

    result = vector_bound_contextual_internal_link_opportunities(
        pages,
        graph,
        semantic_threshold=0.99,
        vectorizer=ForeignVectorizer(),
    )

    assert result["state"] == "not_verified"
    assert result["graph_integrity_state"] == "verified"
    assert result["semantic_vector_integrity_state"] == "not_verified"
    assert result["semantic_vector_integrity_reason"] == "vector_population_mismatch"
    assert result["reason"] == "semantic_vector_vector_population_mismatch"
    assert result["candidate_count"] == 0
    assert result["candidates"] == []
    assert result["semantic_pair_scan_complete"] is False


def test_bool_semantic_weight_fails_closed():
    left = "https://e.test/a"
    right = "https://e.test/b"
    pages = [page(left), page(right)]
    graph = build_weighted_internal_link_graph(pages, [])

    result = vector_bound_contextual_internal_link_opportunities(
        pages,
        graph,
        semantic_threshold=0.99,
        vectorizer=BoolWeightVectorizer(),
    )

    assert result["state"] == "not_verified"
    assert result["semantic_vector_integrity_state"] == "not_verified"
    assert result["semantic_vector_integrity_reason"] == "vector_weight_invalid"
    assert result["candidate_count"] == 0


def test_nondeterministic_semantic_vectors_fail_closed():
    left = "https://e.test/a"
    right = "https://e.test/b"
    pages = [page(left), page(right)]
    graph = build_weighted_internal_link_graph(pages, [])
    vectorizer = NondeterministicVectorizer()

    result = vector_bound_contextual_internal_link_opportunities(
        pages,
        graph,
        semantic_threshold=0.99,
        vectorizer=vectorizer,
    )

    assert vectorizer.calls == 2
    assert result["state"] == "not_verified"
    assert result["semantic_vector_integrity_state"] == "not_verified"
    assert result["semantic_vector_integrity_reason"] == "vectorizer_nondeterministic"
    assert result["semantic_vector_determinism_checked"] is True
    assert result["semantic_vector_determinism_verified"] is False
    assert result["candidate_count"] == 0


def test_delegate_uses_sealed_snapshot_instead_of_third_adapter_result():
    left = "https://e.test/a"
    right = "https://e.test/b"
    pages = [page(left), page(right)]
    graph = build_weighted_internal_link_graph(pages, [])
    vectorizer = ThirdCallChangesVectorizer()

    result = vector_bound_contextual_internal_link_opportunities(
        pages,
        graph,
        semantic_threshold=0.99,
        vectorizer=vectorizer,
    )

    assert vectorizer.calls == 2
    assert result["state"] == "candidate"
    assert result["semantic_vector_integrity_state"] == "verified"
    assert result["candidate_count"] == 2


def test_invalid_graph_fails_before_caller_vectorizer_executes():
    left = "https://e.test/a"
    right = "https://e.test/b"
    pages = [page(left), page(right)]
    graph = build_weighted_internal_link_graph([page(left)], [])
    vectorizer = CountingVectorizer()

    result = vector_bound_contextual_internal_link_opportunities(
        pages,
        graph,
        semantic_threshold=0.99,
        vectorizer=vectorizer,
    )

    assert vectorizer.calls == 0
    assert result["state"] == "not_verified"
    assert result["graph_integrity_state"] == "not_verified"
    assert result["semantic_vector_integrity_state"] == "not_evaluated"
    assert result["semantic_vector_integrity_reason"] == "graph_not_verified"
    assert result["reason"] == "graph_page_population_mismatch"
    assert result["candidate_count"] == 0


def test_vector_bound_helper_does_not_mutate_pages_or_graph():
    left = "https://e.test/a"
    right = "https://e.test/b"
    pages = [page(left), page(right)]
    graph = build_weighted_internal_link_graph(pages, [])
    before_pages = deepcopy(pages)
    before_graph = deepcopy(graph)

    vector_bound_contextual_internal_link_opportunities(
        pages,
        graph,
        semantic_threshold=0.99,
        vectorizer=MappingVectorizer(),
    )

    assert pages == before_pages
    assert graph == before_graph
