import copy

import pytest

from app.connected_evidence_record_contract import (
    RECORD_SHAPE_VERSION,
    validate_connected_evidence_record_semantics,
)


def _envelope(*, provider, source_kind, surface, method, provenance, record):
    return {
        "schema_version": "connected_evidence_v1",
        "provider": provider,
        "surface": surface,
        "method": method,
        "source_kind": source_kind,
        "state": "verified",
        "retrieved_at": "2026-09-21T20:30:00Z",
        "observed_at": "2026-09-20T00:00:00Z",
        "sample": {"coverage_complete_claim": False, "row_count": 1},
        "confidence": {
            "kind": "evidence_quality_not_statistical_probability",
            "level": "first_party_provider_observed",
        },
        "provenance": provenance,
        "coverage": {},
        "records": [record],
    }


def _gsc():
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
        record={
            "dimensions": {"query": "technical seo"},
            "clicks": 1,
            "impressions": 10,
            "ctr": 0.1,
            "position": 2.0,
            "row_number": 1,
        },
    )


def _inspection():
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
        record={
            "inspection_url": "https://getfixlist.com/a",
            "referring_urls": [],
            "sitemap": [],
        },
    )


def _bing():
    return _envelope(
        provider="microsoft_bing_webmaster_tools",
        source_kind="ai_performance_export",
        surface="bing_webmaster_tools.ai_performance",
        method="manual_export_normalization",
        provenance={
            "transport": "manual_export",
            "provider_surface": "bing_webmaster_tools_ai_performance",
            "site_url": "https://getfixlist.com/",
            "api_used": False,
        },
        record={
            "kind": "page_citation",
            "date": "2026-09-20",
            "url": "https://getfixlist.com/a",
            "grounding_query": None,
            "citations": 1,
            "average_cited_pages": None,
            "citation_share": 0.1,
            "row_number": 1,
        },
    )


def _ga4():
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
        record={
            "assistant": "chatgpt",
            "date": "2026-09-20",
            "source": "chatgpt.com / referral",
            "sessions": 1,
            "engaged_sessions": 1,
            "users": 1,
            "key_events": 0.0,
            "revenue": 0.0,
            "row_number": 1,
        },
    )


@pytest.mark.parametrize("factory", [_gsc, _inspection, _bing, _ga4])
def test_registered_record_fields_remain_accepted(factory):
    evidence = factory()
    before = copy.deepcopy(evidence)
    assert RECORD_SHAPE_VERSION == "connected_evidence_record_shape_v1"
    assert validate_connected_evidence_record_semantics(evidence) is evidence
    assert evidence == before


@pytest.mark.parametrize("factory", [_gsc, _inspection, _bing, _ga4])
def test_unregistered_record_fields_fail_closed(factory):
    evidence = factory()
    evidence["records"][0]["unregistered_provider_claim"] = "do-not-accept"
    with pytest.raises(ValueError, match="unregistered fields"):
        validate_connected_evidence_record_semantics(evidence)
