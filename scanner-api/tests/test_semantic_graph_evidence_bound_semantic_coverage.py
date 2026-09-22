from app.semantic_graph_evidence_bound import (
    VECTOR_BOUND_GRAPH_ENVELOPE_VERSION,
    build_vector_bound_semantic_graph_evidence,
)


def page(url):
    return {
        "url": url,
        "status_code": 200,
        "page_evidence_class": "usable_html",
        "indexable": True,
        "page_template_family": "article",
    }


class PartialVectorizer:
    version = "partial_mapping_v1"

    def __init__(self):
        self.calls = 0

    def vectors(self, pages):
        self.calls += 1
        return {
            pages[0]["url"]: {"shared_intent": 1.0},
            pages[1]["url"]: {"shared_intent": 1.0},
        }


class CompleteVectorizer:
    version = "complete_mapping_v1"

    def __init__(self):
        self.calls = 0

    def vectors(self, pages):
        self.calls += 1
        return {row["url"]: {"shared_intent": 1.0} for row in pages}


class EmptyVectorizer:
    version = "empty_mapping_v1"

    def __init__(self):
        self.calls = 0

    def vectors(self, pages):
        self.calls += 1
        return {}


def test_partial_vector_population_is_never_promoted_to_fully_verified_semantic_coverage():
    pages = [
        page("https://e.test/a"),
        page("https://e.test/b"),
        page("https://e.test/c"),
    ]
    vectorizer = PartialVectorizer()

    result = build_vector_bound_semantic_graph_evidence(
        pages,
        [],
        vectorizer=vectorizer,
        cluster_threshold=0.99,
        cannibalization_threshold=0.99,
        contextual_threshold=0.99,
    )

    assert result["version"] == VECTOR_BOUND_GRAPH_ENVELOPE_VERSION
    assert vectorizer.calls == 2
    assert result["state"] == "partial"
    assert result["reason"] == "semantic_vector_coverage_partial"
    assert result["semantic_vector_coverage_state"] == "partial"
    assert result["semantic_pair_population_complete"] is False
    assert result["semantic_pair_scope"] == "vectorized_assessed_page_subset"
    assert result["unvectorized_page_identity_count"] == 1
    assert result["sitewide_semantic_coverage_claim"] is False
    assert result["semantic_clusters"]["semantic_pair_population_complete"] is False
    assert result["cannibalization_candidates"]["semantic_pair_scope"] == (
        "vectorized_assessed_page_subset"
    )
    assert result["contextual_internal_link_opportunities"][
        "sitewide_semantic_coverage_claim"
    ] is False


def test_complete_vector_population_preserves_verified_envelope_state():
    pages = [page("https://e.test/a"), page("https://e.test/b")]
    vectorizer = CompleteVectorizer()

    result = build_vector_bound_semantic_graph_evidence(
        pages,
        [],
        vectorizer=vectorizer,
        cluster_threshold=0.99,
        cannibalization_threshold=0.99,
        contextual_threshold=0.99,
    )

    assert result["state"] == "verified"
    assert result["reason"] == "validated"
    assert result["semantic_vector_coverage_state"] == "complete"
    assert result["semantic_pair_population_complete"] is True
    assert result["semantic_pair_scope"] == "all_assessed_page_identities"
    assert result["unvectorized_page_identity_count"] == 0


def test_zero_semantic_vectors_remain_not_verified_not_a_clean_no_candidate_result():
    pages = [page("https://e.test/a"), page("https://e.test/b")]
    vectorizer = EmptyVectorizer()

    result = build_vector_bound_semantic_graph_evidence(
        pages,
        [],
        vectorizer=vectorizer,
    )

    assert vectorizer.calls == 2
    assert result["state"] == "not_verified"
    assert result["reason"] == "semantic_vector_coverage_unavailable"
    assert result["semantic_vector_coverage_state"] == "none"
    assert result["semantic_pair_population_complete"] is False
    assert result["semantic_pair_scope"] == "no_vectorized_pages"
    assert result["semantic_clusters"]["state"] == "not_verified"
