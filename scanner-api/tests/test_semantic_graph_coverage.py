import pytest

from app.semantic_graph_coverage import (
    SEMANTIC_VECTOR_COVERAGE_VERSION,
    semantic_vector_coverage_evidence,
)


def test_complete_coverage_is_explicit_and_pair_population_complete():
    result = semantic_vector_coverage_evidence(
        input_page_count=3,
        assessed_page_identity_count=3,
        vectorized_pages=3,
        semantic_vector_integrity_state="verified",
    )
    assert result["version"] == SEMANTIC_VECTOR_COVERAGE_VERSION
    assert result["state"] == "verified"
    assert result["semantic_vector_coverage_state"] == "complete"
    assert result["page_identity_coverage_state"] == "complete"
    assert result["semantic_pair_population_complete"] is True
    assert result["semantic_pair_scope"] == "all_assessed_page_identities"
    assert result["unidentified_page_count"] == 0
    assert result["unvectorized_page_identity_count"] == 0
    assert result["sitewide_semantic_coverage_claim"] is False


def test_partial_vector_population_stays_truthfully_subset_scoped():
    result = semantic_vector_coverage_evidence(
        input_page_count=3,
        assessed_page_identity_count=3,
        vectorized_pages=2,
        semantic_vector_integrity_state="verified",
    )
    assert result["state"] == "verified"
    assert result["reason"] == "semantic_vector_population_partial"
    assert result["semantic_vector_coverage_state"] == "partial"
    assert result["semantic_pair_population_complete"] is False
    assert result["semantic_pair_scope"] == "vectorized_assessed_page_subset"
    assert result["unvectorized_page_identity_count"] == 1


def test_missing_page_identity_prevents_complete_semantic_coverage_claim():
    result = semantic_vector_coverage_evidence(
        input_page_count=3,
        assessed_page_identity_count=2,
        vectorized_pages=2,
        semantic_vector_integrity_state="verified",
    )
    assert result["page_identity_coverage_state"] == "partial"
    assert result["semantic_vector_coverage_state"] == "partial"
    assert result["reason"] == "page_identity_coverage_incomplete"
    assert result["unidentified_page_count"] == 1
    assert result["semantic_pair_population_complete"] is False


def test_zero_vectors_is_not_misrepresented_as_complete_pair_coverage():
    result = semantic_vector_coverage_evidence(
        input_page_count=2,
        assessed_page_identity_count=2,
        vectorized_pages=0,
        semantic_vector_integrity_state="verified",
    )
    assert result["semantic_vector_coverage_state"] == "none"
    assert result["reason"] == "no_semantic_vectors_available"
    assert result["semantic_pair_scope"] == "no_vectorized_pages"
    assert result["semantic_pair_population_complete"] is False


def test_invalid_vector_integrity_keeps_coverage_not_verified():
    result = semantic_vector_coverage_evidence(
        input_page_count=2,
        assessed_page_identity_count=2,
        vectorized_pages=0,
        semantic_vector_integrity_state="not_verified",
    )
    assert result["state"] == "verified"
    assert result["semantic_vector_coverage_state"] == "not_verified"
    assert result["reason"] == "semantic_vector_integrity_not_verified"
    assert result["semantic_pair_scope"] == "not_verified"


@pytest.mark.parametrize(
    "kwargs,reason",
    [
        ({"input_page_count": True}, "semantic_coverage_count_invalid"),
        ({"assessed_page_identity_count": -1}, "semantic_coverage_count_invalid"),
        ({"vectorized_pages": 3}, "semantic_vector_count_exceeds_identity_population"),
        ({"assessed_page_identity_count": 3}, "semantic_identity_count_exceeds_input"),
        ({"semantic_vector_integrity_state": "unknown"}, "semantic_vector_integrity_state_invalid"),
    ],
)
def test_invalid_counts_or_integrity_state_fail_closed(kwargs, reason):
    payload = {
        "input_page_count": 2,
        "assessed_page_identity_count": 2,
        "vectorized_pages": 2,
        "semantic_vector_integrity_state": "verified",
    }
    payload.update(kwargs)
    result = semantic_vector_coverage_evidence(**payload)
    assert result["state"] == "not_verified"
    assert result["reason"] == reason
    assert result["semantic_vector_coverage_state"] == "not_verified"
    assert result["semantic_pair_population_complete"] is False
