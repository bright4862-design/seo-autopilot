from datetime import datetime, timezone

import pytest

from app.connected_evidence import (
    normalize_bing_ai_performance_rows,
    normalize_gsc_search_analytics,
)
from app.connected_evidence_record_identity_contract import (
    validate_connected_evidence_record_identity_semantics,
)

NOW = datetime(2026, 9, 21, 20, 30, tzinfo=timezone.utc)


def test_gsc_page_url_aliases_cannot_evade_logical_row_deduplication():
    evidence = normalize_gsc_search_analytics(
        {
            "rows": [
                {
                    "keys": ["2026-09-20", "https://Example.test:443/a?x=1"],
                    "clicks": 1,
                    "impressions": 10,
                    "ctr": 0.1,
                    "position": 4.0,
                },
                {
                    "keys": ["2026-09-20", "https://example.test/a?x=1"],
                    "clicks": 2,
                    "impressions": 20,
                    "ctr": 0.1,
                    "position": 5.0,
                },
            ]
        },
        dimensions=["date", "page"],
        property_uri="sc-domain:example.test",
        retrieved_at=NOW,
    )
    assert evidence["state"] == "verified"
    with pytest.raises(ValueError, match="duplicate connected-evidence logical record"):
        validate_connected_evidence_record_identity_semantics(evidence)


def test_gsc_page_query_string_remains_part_of_logical_identity():
    evidence = normalize_gsc_search_analytics(
        {
            "rows": [
                {
                    "keys": ["2026-09-20", "https://example.test/a?x=1"],
                    "clicks": 1,
                    "impressions": 10,
                    "ctr": 0.1,
                    "position": 4.0,
                },
                {
                    "keys": ["2026-09-20", "https://example.test/a?x=2"],
                    "clicks": 2,
                    "impressions": 20,
                    "ctr": 0.1,
                    "position": 5.0,
                },
            ]
        },
        dimensions=["date", "page"],
        property_uri="sc-domain:example.test",
        retrieved_at=NOW,
    )
    assert validate_connected_evidence_record_identity_semantics(evidence) is evidence


def test_bing_cited_page_url_aliases_cannot_evade_logical_row_deduplication():
    evidence = normalize_bing_ai_performance_rows(
        [
            {
                "Date": "2026-09-20",
                "URL": "https://Example.test:443/path",
                "Citations": 1,
            },
            {
                "Date": "2026-09-20",
                "URL": "https://example.test/path",
                "Citations": 2,
            },
        ],
        site_url="https://example.test",
        retrieved_at=NOW,
    )
    assert evidence["state"] == "verified"
    with pytest.raises(ValueError, match="duplicate connected-evidence logical record"):
        validate_connected_evidence_record_identity_semantics(evidence)


def test_bing_distinct_cited_paths_remain_distinct_logical_rows():
    evidence = normalize_bing_ai_performance_rows(
        [
            {"Date": "2026-09-20", "URL": "https://example.test/a", "Citations": 1},
            {"Date": "2026-09-20", "URL": "https://example.test/b", "Citations": 1},
        ],
        site_url="https://example.test",
        retrieved_at=NOW,
    )
    assert validate_connected_evidence_record_identity_semantics(evidence) is evidence
