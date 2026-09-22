from app.semantic_graph_vector_contract import semantic_vector_contract_evidence


class MappingVectorizer:
    version = "coverage_mapping_v1"

    def __init__(self, payload):
        self.payload = payload

    def vectors(self, pages):
        return {url: dict(vector) for url, vector in self.payload.items()}


def test_partial_vector_population_is_integrity_verified_but_coverage_partial():
    pages = [
        {"url": "https://e.test/a"},
        {"url": "https://e.test/b"},
    ]
    result = semantic_vector_contract_evidence(
        pages,
        MappingVectorizer({"https://e.test/a": {"topic": 1.0}}),
    )

    assert result["state"] == "verified"
    assert result["semantic_vector_coverage_state"] == "partial"
    assert result["semantic_pair_population_complete"] is False
    assert result["semantic_pair_scope"] == "vectorized_assessed_page_subset"
    assert result["unvectorized_page_identity_count"] == 1
    assert result["sitewide_semantic_coverage_claim"] is False


def test_complete_vector_population_is_explicitly_complete():
    pages = [
        {"url": "https://e.test/a"},
        {"url": "https://e.test/b"},
    ]
    result = semantic_vector_contract_evidence(
        pages,
        MappingVectorizer({
            "https://e.test/a": {"topic": 1.0},
            "https://e.test/b": {"topic": 2.0},
        }),
    )

    assert result["semantic_vector_coverage_state"] == "complete"
    assert result["semantic_pair_population_complete"] is True
    assert result["semantic_pair_scope"] == "all_assessed_page_identities"
    assert result["unvectorized_page_identity_count"] == 0


def test_missing_page_identity_is_explicitly_partial_even_when_all_identified_pages_vectorize():
    pages = [
        {"url": "https://e.test/a"},
        {"title": "identity unavailable"},
    ]
    result = semantic_vector_contract_evidence(
        pages,
        MappingVectorizer({"https://e.test/a": {"topic": 1.0}}),
    )

    assert result["state"] == "verified"
    assert result["page_identity_coverage_state"] == "partial"
    assert result["semantic_vector_coverage_state"] == "partial"
    assert result["unidentified_page_count"] == 1
    assert result["semantic_pair_population_complete"] is False


def test_invalid_vector_integrity_never_produces_verified_coverage():
    pages = [
        {"url": "https://e.test/a"},
        {"url": "https://e.test/b"},
    ]
    result = semantic_vector_contract_evidence(
        pages,
        MappingVectorizer({"https://foreign.test/x": {"topic": 1.0}}),
    )

    assert result["state"] == "not_verified"
    assert result["reason"] == "vector_population_mismatch"
    assert result["semantic_vector_coverage_state"] == "not_verified"
    assert result["semantic_pair_population_complete"] is False
    assert result["semantic_pair_scope"] == "not_verified"
