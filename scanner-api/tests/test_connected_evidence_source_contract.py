import copy

import pytest

from app.connected_evidence_source_contract import (
    SOURCE_PROFILE_VERSION,
    validate_connected_evidence_source_identity,
)


def _envelope(*, provider, source_kind, surface, method, provenance, records=None, state="verified"):
    unavailable = state in {"not_connected", "not_supported", "not_verified", "provider_error"}
    return {
        "schema_version": "connected_evidence_v1",
        "provider": provider,
        "surface": surface,
        "method": method,
        "source_kind": source_kind,
        "state": state,
        "retrieved_at": "2026-09-21T20:30:00Z",
        "observed_at": None if unavailable else "2026-09-20T00:00:00Z",
        "sample": {"coverage_complete_claim": False},
        "confidence": {
            "kind": "evidence_quality_not_statistical_probability",
            "level": "none" if unavailable else "first_party_provider_observed",
        },
        "provenance": provenance,
        "coverage": {},
        "records": [] if unavailable else list(records or []),
        **({"reason": "provider unavailable"} if unavailable else {}),
    }


def test_source_profile_contract_is_versioned_and_accepts_gsc_search_analytics():
    evidence = _envelope(
        provider="google_search_console",
        source_kind="search_analytics",
        surface="google_search_console.search_analytics",
        method="api_response_normalization",
        provenance={
            "transport": "provided_payload",
            "provider_operation": "searchanalytics.query",
            "property_uri": "sc-domain:getfixlist.com",
        },
        records=[{"dimensions": {"query": "seo audit"}, "row_number": 1}],
    )
    assert SOURCE_PROFILE_VERSION == "connected_evidence_source_profile_v1"
    assert validate_connected_evidence_source_identity(evidence) is evidence


def test_gsc_search_analytics_rejects_wrong_provider_operation():
    evidence = _envelope(
        provider="google_search_console",
        source_kind="search_analytics",
        surface="google_search_console.search_analytics",
        method="api_response_normalization",
        provenance={
            "transport": "provided_payload",
            "provider_operation": "urlInspection.index.inspect",
            "property_uri": "sc-domain:getfixlist.com",
        },
    )
    with pytest.raises(ValueError, match="provider_operation"):
        validate_connected_evidence_source_identity(evidence)


def test_wrong_surface_fails_closed_even_when_provider_and_source_kind_match():
    evidence = _envelope(
        provider="google_search_console",
        source_kind="search_analytics",
        surface="google_search_console.url_inspection",
        method="api_response_normalization",
        provenance={
            "transport": "provided_payload",
            "provider_operation": "searchanalytics.query",
            "property_uri": "sc-domain:getfixlist.com",
        },
    )
    with pytest.raises(ValueError, match="surface"):
        validate_connected_evidence_source_identity(evidence)


def test_url_inspection_record_identity_must_match_provenance():
    evidence = _envelope(
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
        records=[{"inspection_url": "https://getfixlist.com/b"}],
    )
    with pytest.raises(ValueError, match="record identity"):
        validate_connected_evidence_source_identity(evidence)


def test_url_inspection_provider_error_still_preserves_source_provenance():
    evidence = _envelope(
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
        state="provider_error",
    )
    assert validate_connected_evidence_source_identity(evidence) is evidence


def test_bing_manual_export_requires_explicit_api_used_false():
    evidence = _envelope(
        provider="microsoft_bing_webmaster_tools",
        source_kind="ai_performance_export",
        surface="bing_webmaster_tools.ai_performance",
        method="manual_export_normalization",
        provenance={
            "transport": "manual_export",
            "provider_surface": "bing_webmaster_tools_ai_performance",
            "site_url": "https://getfixlist.com",
            "api_used": True,
        },
    )
    with pytest.raises(ValueError, match="api_used"):
        validate_connected_evidence_source_identity(evidence)


def test_bing_cited_page_must_match_imported_site_host():
    evidence = _envelope(
        provider="microsoft_bing_webmaster_tools",
        source_kind="ai_performance_export",
        surface="bing_webmaster_tools.ai_performance",
        method="manual_export_normalization",
        provenance={
            "transport": "manual_export",
            "provider_surface": "bing_webmaster_tools_ai_performance",
            "site_url": "https://getfixlist.com",
            "api_used": False,
            "import_name": "ai-performance.csv",
        },
        records=[{"url": "https://example.com/foreign", "row_number": 1}],
    )
    with pytest.raises(ValueError, match="cited-page host"):
        validate_connected_evidence_source_identity(evidence)


def test_bing_relative_cited_page_fails_closed_instead_of_being_attributed():
    evidence = _envelope(
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
        records=[{"url": "/relative", "row_number": 1}],
    )
    with pytest.raises(ValueError, match=r"absolute HTTP\(S\) URL"):
        validate_connected_evidence_source_identity(evidence)


def test_ga4_profile_requires_property_identity_and_expected_transport():
    evidence = _envelope(
        provider="google_analytics_4",
        source_kind="ai_assistant_referrals",
        surface="google_analytics_4.referral_traffic",
        method="aggregate_row_normalization",
        provenance={
            "transport": "provided_rows",
            "provider_surface": "ga4_reporting_export_or_response",
            "property_id": "properties/123",
        },
        records=[{"assistant": "chatgpt", "sessions": 3, "row_number": 1}],
    )
    assert validate_connected_evidence_source_identity(evidence) is evidence


def test_ga4_missing_property_identity_fails_closed():
    evidence = _envelope(
        provider="google_analytics_4",
        source_kind="ai_assistant_referrals",
        surface="google_analytics_4.referral_traffic",
        method="aggregate_row_normalization",
        provenance={
            "transport": "provided_rows",
            "provider_surface": "ga4_reporting_export_or_response",
            "property_id": "",
        },
    )
    with pytest.raises(ValueError, match="property_id"):
        validate_connected_evidence_source_identity(evidence)


def test_unregistered_provider_source_pair_fails_closed():
    evidence = _envelope(
        provider="google_search_console",
        source_kind="generative_ai_visibility",
        surface="google_search_console.generative_ai_visibility",
        method="api_response_normalization",
        provenance={"transport": "provided_payload"},
    )
    with pytest.raises(ValueError, match="unsupported connected-evidence provider/source_kind profile"):
        validate_connected_evidence_source_identity(evidence)


def test_validation_does_not_mutate_evidence():
    evidence = _envelope(
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
        records=[{"url": "https://getfixlist.com/a", "row_number": 1}],
    )
    before = copy.deepcopy(evidence)
    validate_connected_evidence_source_identity(evidence)
    assert evidence == before
