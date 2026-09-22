import math

import pytest

from app.semantic_graph_vector_contract import (
    MAX_DIMENSIONS_PER_PAGE,
    SemanticVectorContractError,
    ValidatedSemanticVectorizer,
    semantic_vector_contract_evidence,
)


PAGES = [
    {"url": "https://e.test/a"},
    {"url": "https://e.test/b"},
]


class MappingVectorizer:
    version = "mapping_v1"

    def __init__(self, payload):
        self.payload = payload

    def vectors(self, pages):
        return {url: dict(vector) for url, vector in self.payload.items()}


class AlternatingVectorizer:
    version = "alternating_v1"

    def __init__(self):
        self.calls = 0

    def vectors(self, pages):
        self.calls += 1
        value = 1.0 if self.calls % 2 else 2.0
        return {"https://e.test/a": {"topic": value}}


class MutatingVectorizer:
    version = "mutating_v1"

    def vectors(self, pages):
        pages[0]["title"] = "adapter-mutated"
        return {"https://e.test/a": {"topic": 1.0}}


class SecondCallMutatingVectorizer:
    version = "second_call_mutating_v1"

    def __init__(self):
        self.calls = 0

    def vectors(self, pages):
        self.calls += 1
        if self.calls == 2:
            pages[1]["semantic_terms"] = ["mutated"]
        return {"https://e.test/a": {"topic": 1.0}}


def test_valid_vectors_are_verified_copied_and_deterministic():
    payload = {
        "https://e.test/b": {"beta": 2, "alpha": -1.5},
        "https://e.test/a": {"topic": 1.0},
    }
    evidence = semantic_vector_contract_evidence(PAGES, MappingVectorizer(payload))
    assert evidence["state"] == "verified"
    assert evidence["reason"] == "validated"
    assert evidence["determinism_verified"] is True
    assert list(evidence["vectors"]) == ["https://e.test/a", "https://e.test/b"]
    assert evidence["vectors"]["https://e.test/b"] == {"alpha": -1.5, "beta": 2.0}
    assert evidence["customer_fix_created"] is False
    assert payload["https://e.test/b"] == {"beta": 2, "alpha": -1.5}


def test_page_identity_uses_shared_internal_whitespace_normalization():
    pages = [
        {"url": "https://e.test/a   b"},
        {"url": "https://e.test/c"},
    ]
    evidence = semantic_vector_contract_evidence(
        pages,
        MappingVectorizer({
            "https://e.test/a b": {"topic": 1.0},
            "https://e.test/c": {"topic": 1.0},
        }),
    )

    assert evidence["state"] == "verified"
    assert evidence["reason"] == "validated"
    assert evidence["assessed_page_identity_count"] == 2
    assert evidence["semantic_vector_coverage_state"] == "complete"
    assert list(evidence["vectors"]) == ["https://e.test/a b", "https://e.test/c"]


def test_foreign_vector_url_fails_closed():
    evidence = semantic_vector_contract_evidence(
        PAGES,
        MappingVectorizer({"https://foreign.test/x": {"topic": 1.0}}),
    )
    assert evidence["state"] == "not_verified"
    assert evidence["reason"] == "vector_population_mismatch"
    assert evidence["vectors"] == {}


def test_duplicate_assessed_page_identity_fails_closed():
    pages = [{"url": "https://e.test/a"}, {"final_url": "https://e.test/a"}]
    evidence = semantic_vector_contract_evidence(
        pages,
        MappingVectorizer({"https://e.test/a": {"topic": 1.0}}),
    )
    assert evidence["reason"] == "duplicate_page_identity"


@pytest.mark.parametrize("weight", [True, math.nan, math.inf, -math.inf])
def test_invalid_numeric_weights_fail_closed(weight):
    evidence = semantic_vector_contract_evidence(
        PAGES,
        MappingVectorizer({"https://e.test/a": {"topic": weight}}),
    )
    assert evidence["state"] == "not_verified"
    assert evidence["reason"] == "vector_weight_invalid"


def test_zero_norm_vector_fails_closed():
    evidence = semantic_vector_contract_evidence(
        PAGES,
        MappingVectorizer({"https://e.test/a": {"topic": 0.0}}),
    )
    assert evidence["reason"] == "vector_zero_norm"


def test_dimension_limit_is_bounded():
    vector = {f"d{index}": 1.0 for index in range(MAX_DIMENSIONS_PER_PAGE + 1)}
    evidence = semantic_vector_contract_evidence(
        PAGES,
        MappingVectorizer({"https://e.test/a": vector}),
    )
    assert evidence["reason"] == "vector_dimension_limit_exceeded"


def test_nondeterministic_adapter_fails_closed():
    evidence = semantic_vector_contract_evidence(PAGES, AlternatingVectorizer())
    assert evidence["state"] == "not_verified"
    assert evidence["reason"] == "vectorizer_nondeterministic"
    assert evidence["vectors"] == {}


def test_mutating_adapter_fails_closed_without_mutating_caller_pages():
    pages = [
        {"url": "https://e.test/a", "title": "Original"},
        {"url": "https://e.test/b"},
    ]
    evidence = semantic_vector_contract_evidence(pages, MutatingVectorizer())
    assert evidence["state"] == "not_verified"
    assert evidence["reason"] == "vectorizer_input_mutation"
    assert evidence["vectors"] == {}
    assert pages == [
        {"url": "https://e.test/a", "title": "Original"},
        {"url": "https://e.test/b"},
    ]


def test_second_determinism_call_mutation_fails_closed_and_isolated():
    pages = [
        {"url": "https://e.test/a"},
        {"url": "https://e.test/b", "semantic_terms": ["stable"]},
    ]
    evidence = semantic_vector_contract_evidence(
        pages,
        SecondCallMutatingVectorizer(),
    )
    assert evidence["state"] == "not_verified"
    assert evidence["reason"] == "vectorizer_input_mutation"
    assert evidence["determinism_checked"] is True
    assert evidence["determinism_verified"] is False
    assert pages[1]["semantic_terms"] == ["stable"]


def test_strict_adapter_preserves_interface_for_valid_local_vectors():
    adapter = ValidatedSemanticVectorizer(
        MappingVectorizer({
            "https://e.test/a": {"topic": 1.0},
            "https://e.test/b": {"topic": 2.0},
        })
    )
    assert adapter.version.startswith("validated_semantic_vectorizer_v1:")
    assert adapter.vectors(PAGES) == {
        "https://e.test/a": {"topic": 1.0},
        "https://e.test/b": {"topic": 2.0},
    }


def test_strict_adapter_raises_reasoned_error_instead_of_returning_bad_vectors():
    adapter = ValidatedSemanticVectorizer(
        MappingVectorizer({"https://foreign.test/x": {"topic": 1.0}})
    )
    with pytest.raises(SemanticVectorContractError) as exc:
        adapter.vectors(PAGES)
    assert exc.value.reason == "vector_population_mismatch"


def test_strict_adapter_raises_when_delegate_mutates_input():
    adapter = ValidatedSemanticVectorizer(MutatingVectorizer())
    pages = [{"url": "https://e.test/a"}, {"url": "https://e.test/b"}]
    with pytest.raises(SemanticVectorContractError) as exc:
        adapter.vectors(pages)
    assert exc.value.reason == "vectorizer_input_mutation"
    assert pages == [{"url": "https://e.test/a"}, {"url": "https://e.test/b"}]
