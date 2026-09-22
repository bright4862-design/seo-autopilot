import copy

import pytest

from app.connected_evidence_record_contract import (
    RECORD_SEMANTICS_VERSION,
    validate_connected_evidence_record_semantics,
)


def _envelope(*, provider, source_kind, surface, method, provenance, records, state="verified"):
    return {
        "schema_version": "connected_evidence_v1",
        "provider": provider,
        "surface": surface,
        "method": method,
        "source_kind": source_kind,
        "state": state,
        "retrieved_at": "2026-09-21T20:30:00Z",
        "observed_at": "2026-09-20T00:00:00Z",
        "sample": {"coverage_complete_claim": False, "row_count": len(records)},
        "confidence": {
            "kind": "evidence_quality_not_statistical_probability",
            "level": "first_party_provider_observed",
        },
        "provenance": provenance,
        "coverage": {},
        "records": records,
    }


def _ga4(records):
    return _envelope(
        provider="google_analytics_4",
        source_kind="ai_assistant_referrals",
        surface="google_analytics_4.referral_traffic",
        method="aggregate_row_normalization",
        provenance={
            "transport": "provided_rows",
            "provider_surface": "ga4_reporting_export_or_response",
            "property_id": "properties/123",
        },
        records=records,
    )


def _inspection(record):
    return _envelope(
        provider="google_search_console",
        source_kind="url_inspection",
        surface="google_search_console.url_inspection",
        method="api_response_normalization",
        provenance={
            "transport": "provided_payload",
            "provider_operation": "urlInspection.index.inspect",
            "property_uri": "sc-domain:getfixlist.com",
            "inspection_url": "https://getfixlist.com/a",
        },
        records=[record],
    )


def _gsc(record):
    return _envelope(
        provider="google_search_console",
        source_kind="search_analytics",
        surface="google_search_console.search_analytics",
        method="api_response_normalization",
        provenance={
            "transport": "provided_payload",
            "provider_operation": "searchanalytics.query",
            "property_uri": "sc-domain:getfixlist.com",
        },
        records=[record],
    )


def _bing(record):
    return _envelope(
        provider="microsoft_bing_webmaster_tools",
        source_kind="ai_performance_export",
        surface="bing_webmaster_tools.ai_performance",
        method="manual_export_normalization",
        provenance={
            "transport": "manual_export",
            "provider_surface": "bing_webmaster_tools_ai_performance",
            "site_url": "https://getfixlist.com",
            "api_used": False,
        },
        records=[record],
    )


def test_record_semantics_contract_is_versioned_and_non_mutating():
    evidence = _ga4(
        [
            {
                "assistant": "chatgpt",
                "source": "chatgpt.com",
                "sessions": 3,
                "engaged_sessions": 2,
                "users": 2,
                "key_events": 1.0,
                "revenue": 0.0,
                "row_number": 1,
            }
        ]
    )
    before = copy.deepcopy(evidence)
    assert RECORD_SEMANTICS_VERSION == "connected_evidence_record_semantics_v1"
    assert validate_connected_evidence_record_semantics(evidence) is evidence
    assert evidence == before


def test_ga4_spoof_host_containing_chatgpt_token_is_rejected():
    evidence = _ga4(
        [{"assistant": "chatgpt", "source": "notchatgpt.example", "sessions": 1, "row_number": 1}]
    )
    with pytest.raises(ValueError, match="registered AI-assistant host"):
        validate_connected_evidence_record_semantics(evidence)


def test_ga4_arbitrary_explicit_assistant_label_is_rejected():
    evidence = _ga4(
        [{"assistant": "random_bot", "source": None, "sessions": 1, "row_number": 1}]
    )
    with pytest.raises(ValueError, match="registered AI assistant"):
        validate_connected_evidence_record_semantics(evidence)


def test_ga4_known_explicit_assistant_without_source_is_accepted():
    evidence = _ga4(
        [{"assistant": "Microsoft Copilot", "source": None, "sessions": 1, "row_number": 1}]
    )
    assert validate_connected_evidence_record_semantics(evidence) is evidence


def test_ga4_assistant_must_match_source_host():
    evidence = _ga4(
        [{"assistant": "claude", "source": "chatgpt.com / referral", "sessions": 1, "row_number": 1}]
    )
    with pytest.raises(ValueError, match="contradicts source host"):
        validate_connected_evidence_record_semantics(evidence)


def test_ga4_source_rejects_out_of_range_port():
    evidence = _ga4(
        [{"assistant": "chatgpt", "source": "chatgpt.com:99999 / referral", "sessions": 1, "row_number": 1}]
    )
    with pytest.raises(ValueError, match="valid source host"):
        validate_connected_evidence_record_semantics(evidence)


def test_ga4_source_rejects_userinfo_without_scheme():
    evidence = _ga4(
        [{"assistant": "chatgpt", "source": "user:secret@chatgpt.com / referral", "sessions": 1, "row_number": 1}]
    )
    with pytest.raises(ValueError, match="valid source host"):
        validate_connected_evidence_record_semantics(evidence)


def test_ga4_source_rejects_userinfo_with_scheme():
    evidence = _ga4(
        [{"assistant": "chatgpt", "source": "https://user@chatgpt.com / referral", "sessions": 1, "row_number": 1}]
    )
    with pytest.raises(ValueError, match="valid source host"):
        validate_connected_evidence_record_semantics(evidence)


def test_ga4_engaged_sessions_cannot_exceed_sessions():
    evidence = _ga4(
        [
            {
                "assistant": "chatgpt",
                "source": "chatgpt.com",
                "sessions": 2,
                "engaged_sessions": 3,
                "row_number": 1,
            }
        ]
    )
    with pytest.raises(ValueError, match="engaged_sessions cannot exceed sessions"):
        validate_connected_evidence_record_semantics(evidence)


def test_url_inspection_rejects_non_url_referring_values():
    evidence = _inspection(
        {
            "inspection_url": "https://getfixlist.com/a",
            "referring_urls": ["not-a-url"],
            "sitemap": [],
        }
    )
    with pytest.raises(ValueError, match=r"referring_urls\[0\].*absolute HTTP\(S\) URL"):
        validate_connected_evidence_record_semantics(evidence)


def test_url_inspection_rejects_relative_canonical():
    evidence = _inspection(
        {
            "inspection_url": "https://getfixlist.com/a",
            "google_canonical": "/a",
            "referring_urls": [],
            "sitemap": [],
        }
    )
    with pytest.raises(ValueError, match=r"google_canonical.*absolute HTTP\(S\) URL"):
        validate_connected_evidence_record_semantics(evidence)


def test_url_inspection_rejects_out_of_range_port_canonical():
    evidence = _inspection(
        {
            "inspection_url": "https://getfixlist.com/a",
            "google_canonical": "https://getfixlist.com:99999/a",
            "referring_urls": [],
            "sitemap": [],
        }
    )
    with pytest.raises(ValueError, match=r"google_canonical.*absolute HTTP\(S\) URL"):
        validate_connected_evidence_record_semantics(evidence)


def test_url_inspection_rejects_future_last_crawl_time():
    evidence = _inspection(
        {
            "inspection_url": "https://getfixlist.com/a",
            "last_crawl_time": "2026-09-22T00:00:00Z",
            "referring_urls": [],
            "sitemap": [],
        }
    )
    with pytest.raises(ValueError, match="last_crawl_time cannot be later"):
        validate_connected_evidence_record_semantics(evidence)


def test_gsc_rejects_clicks_greater_than_impressions():
    evidence = _gsc(
        {
            "dimensions": {"query": "technical seo"},
            "clicks": 11,
            "impressions": 10,
            "ctr": 1.0,
            "position": 2.0,
            "row_number": 1,
        }
    )
    with pytest.raises(ValueError, match="clicks cannot exceed impressions"):
        validate_connected_evidence_record_semantics(evidence)


def test_gsc_rejects_ctr_that_contradicts_clicks_and_impressions():
    evidence = _gsc(
        {
            "dimensions": {"query": "technical seo"},
            "clicks": 1,
            "impressions": 10,
            "ctr": 0.9,
            "position": 2.0,
            "row_number": 1,
        }
    )
    with pytest.raises(ValueError, match="ctr contradicts clicks/impressions"):
        validate_connected_evidence_record_semantics(evidence)


def test_gsc_rejects_negative_position():
    evidence = _gsc(
        {
            "dimensions": {"query": "technical seo"},
            "clicks": 1,
            "impressions": 10,
            "ctr": 0.1,
            "position": -1.0,
            "row_number": 1,
        }
    )
    with pytest.raises(ValueError, match="position must be non-negative"):
        validate_connected_evidence_record_semantics(evidence)


def test_bing_kind_must_match_url_and_query_identity():
    evidence = _bing(
        {
            "kind": "grounding_query",
            "url": "https://getfixlist.com/a",
            "grounding_query": "best seo audit",
            "citations": 1,
            "average_cited_pages": None,
            "citation_share": 0.1,
            "row_number": 1,
        }
    )
    with pytest.raises(ValueError, match="kind contradicts URL/query identity"):
        validate_connected_evidence_record_semantics(evidence)


def test_bing_rejects_out_of_range_citation_share():
    evidence = _bing(
        {
            "kind": "page_citation",
            "url": "https://getfixlist.com/a",
            "grounding_query": None,
            "citations": 1,
            "average_cited_pages": None,
            "citation_share": 1.2,
            "row_number": 1,
        }
    )
    with pytest.raises(ValueError, match="citation_share must be within 0..1"):
        validate_connected_evidence_record_semantics(evidence)


def test_tabular_records_require_unique_positive_row_numbers():
    evidence = _ga4(
        [
            {"assistant": "chatgpt", "source": "chatgpt.com", "sessions": 1, "row_number": 1},
            {"assistant": "claude", "source": "claude.ai", "sessions": 1, "row_number": 1},
        ]
    )
    with pytest.raises(ValueError, match="row_number values must be unique"):
        validate_connected_evidence_record_semantics(evidence)
