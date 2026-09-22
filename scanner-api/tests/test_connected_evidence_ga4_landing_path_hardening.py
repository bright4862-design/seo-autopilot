import copy

import pytest

from app.connected_evidence_scope_contract import validate_connected_evidence_scope_semantics


def _ga4_evidence(landing_page):
    return {
        "provider": "google_analytics_4",
        "source_kind": "ai_assistant_referrals",
        "provenance": {"property_id": "properties/123"},
        "records": [{"landing_page": landing_page}],
    }


def test_ga4_landing_page_accepts_unambiguous_encoded_leaf_and_query():
    evidence = _ga4_evidence("/docs%20guide?from=ai")
    before = copy.deepcopy(evidence)
    assert validate_connected_evidence_scope_semantics(evidence) is evidence
    assert evidence == before


@pytest.mark.parametrize(
    ("landing_page", "message"),
    [
        ("/docs/../admin", "dot-segment"),
        ("/docs/%2e%2e/admin", "dot-segment"),
        ("/docs%2fadmin", "encoded path separator"),
        ("/docs\\admin", "ambiguous path separator"),
        ("/docs/%GG", "malformed percent escape"),
        ("/docs;param/x", "path parameters"),
        ("/docs/\x00x", "control character"),
    ],
)
def test_ga4_landing_page_rejects_ambiguous_path_forms(landing_page, message):
    with pytest.raises(ValueError, match=message):
        validate_connected_evidence_scope_semantics(_ga4_evidence(landing_page))
