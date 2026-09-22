from app.semantic_graph import cannibalization_candidates


def page(url, *, main=None):
    row = {
        "url": url,
        "status_code": 200,
        "page_evidence_class": "usable_html",
        "indexable": True,
    }
    if main is not None:
        row.update(
            {
                "main_text_verified": True,
                "main_text_representation": "sha256_5_token_shingles_v1",
                "main_text": " ".join(main),
            }
        )
    return row


class MappingVectorizer:
    version = "test_mapping_v1"

    def __init__(self, urls):
        self._vectors = {url: {"shared_intent": 1.0} for url in urls}

    def vectors(self, pages):
        urls = {row["url"] for row in pages}
        return {url: dict(vector) for url, vector in self._vectors.items() if url in urls}


def test_cannibalization_does_not_claim_duplicate_exclusion_without_b10_evidence():
    pages = [page("https://e.test/a"), page("https://e.test/b")]
    result = cannibalization_candidates(
        pages,
        semantic_threshold=0.99,
        vectorizer=MappingVectorizer(row["url"] for row in pages),
    )

    assert result["candidate_count"] == 1
    assert result["near_duplicate_filtered_count"] == 0
    assert result["near_duplicate_comparison_verified_count"] == 0
    assert result["near_duplicate_comparison_not_verified_count"] == 1

    candidate = result["candidates"][0]
    assert candidate["near_duplicate_comparison_state"] == "not_verified"
    assert candidate["near_duplicate_similarity"] is None
    assert candidate["near_duplicate_exclusion_verified"] is False
    assert candidate["reason"] == "indexable_pages_share_local_semantic_intent_duplicate_status_not_verified"


def test_cannibalization_separates_verified_distinct_from_verified_near_duplicate():
    left_main = [f"{index:016x}" for index in range(1, 11)]
    distinct_main = [f"{index:016x}" for index in range(101, 111)]

    distinct_pages = [
        page("https://e.test/a", main=left_main),
        page("https://e.test/b", main=distinct_main),
    ]
    vectorizer = MappingVectorizer(row["url"] for row in distinct_pages)
    distinct = cannibalization_candidates(
        distinct_pages,
        semantic_threshold=0.99,
        duplicate_threshold=0.82,
        vectorizer=vectorizer,
    )

    assert distinct["candidate_count"] == 1
    assert distinct["near_duplicate_filtered_count"] == 0
    assert distinct["near_duplicate_comparison_verified_count"] == 1
    assert distinct["near_duplicate_comparison_not_verified_count"] == 0
    candidate = distinct["candidates"][0]
    assert candidate["near_duplicate_comparison_state"] == "verified_distinct"
    assert candidate["near_duplicate_similarity"] == 0.0
    assert candidate["near_duplicate_exclusion_verified"] is True
    assert candidate["reason"] == "distinct_indexable_pages_share_local_semantic_intent"

    duplicate_pages = [
        page("https://e.test/a", main=left_main),
        page("https://e.test/b", main=left_main),
    ]
    duplicate = cannibalization_candidates(
        duplicate_pages,
        semantic_threshold=0.99,
        duplicate_threshold=0.82,
        vectorizer=vectorizer,
    )

    assert duplicate["candidate_count"] == 0
    assert duplicate["near_duplicate_filtered_count"] == 1
    assert duplicate["near_duplicate_comparison_verified_count"] == 0
    assert duplicate["near_duplicate_comparison_not_verified_count"] == 0
    assert duplicate["candidates"] == []
