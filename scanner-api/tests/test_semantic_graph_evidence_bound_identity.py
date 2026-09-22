from app.semantic_graph import LOCAL_SEMANTIC_VERSION
from app.semantic_graph_evidence_bound import build_vector_bound_semantic_graph_evidence


def test_missing_page_identity_remains_explicit_and_cannot_be_promoted_to_verified_envelope():
    pages = [
        {
            "url": "https://e.test/articles/identified-page",
            "status_code": 200,
            "page_evidence_class": "usable_html",
            "indexable": True,
            "title": "Shared Intent Guide",
            "h1": "Shared Intent Guide",
        },
        {
            "status_code": 200,
            "page_evidence_class": "usable_html",
            "indexable": True,
            "title": "Unidentified page evidence",
        },
    ]

    result = build_vector_bound_semantic_graph_evidence(pages, [])

    assert result["input_page_count"] == 2
    assert result["assessed_page_identity_count"] == 1
    assert result["page_identity_coverage_state"] == "partial"
    assert result["state"] == "not_verified"
    assert result["reason"] == "page_identity_coverage_incomplete"
    assert result["semantic_analysis"]["semantic_vector_integrity_state"] == "verified"
    assert result["semantic_analysis"]["semantic_vectorizer_version"] == LOCAL_SEMANTIC_VERSION
    assert result["graph"]["nodes"][0]["url"] == "https://e.test/articles/identified-page"
    assert any(
        row["state"] == "not_verified" and not row["url"]
        for row in result["template_evidence"]["pages"]
    )
    assert result["customer_fix_created"] is False
