import pytest

from app.connected_evidence_source_contract import validate_connected_evidence_source_identity


def _unavailable(*, provider, source_kind, surface, method, provenance):
    return {
        "schema_version": "connected_evidence_v1",
        "provider": provider,
        "surface": surface,
        "method": method,
        "source_kind": source_kind,
        "state": "provider_error",
        "retrieved_at": "2026-09-22T12:00:00Z",
        "observed_at": None,
        "sample": {"coverage_complete_claim": False},
        "confidence": {
            "kind": "evidence_quality_not_statistical_probability",
            "level": "none",
        },
        "provenance": provenance,
        "coverage": {},
        "records": [],
        "reason": "provider unavailable",
    }


def test_gsc_search_analytics_rejects_unregistered_provenance_fields():
    evidence = _unavailable(
        provider="google_search_console",
        source_kind="search_analytics",
        surface="google_search_console.search_analytics",
        method="api_response_normalization",
        provenance={
            "transport": "provided_payload",
            "provider_operation": "searchanalytics.query",
            "property_uri": "sc-domain:getfixlist.com",
            "oauth_scope": "should-not-be-carried",
        },
    )
    with pytest.raises(ValueError, match="unregistered fields"):
        validate_connected_evidence_source_identity(evidence)


def test_url_inspection_rejects_unregistered_provenance_fields():
    evidence = _unavailable(
        provider="google_search_console",
        source_kind="url_inspection",
        surface="google_search_console.url_inspection",
        method="api_response_normalization",
        provenance={
            "transport": "provided_payload",
            "provider_operation": "urlInspection.index.inspect",
            "property_uri": "sc-domain:getfixlist.com",
            "inspection_url": "https://getfixlist.com/a",
            "credential_id": "should-not-be-carried",
        },
    )
    with pytest.raises(ValueError, match="unregistered fields"):
        validate_connected_evidence_source_identity(evidence)


def test_bing_registered_optional_import_name_is_accepted():
    evidence = _unavailable(
        provider="microsoft_bing_webmaster_tools",
        source_kind="ai_performance_export",
        surface="bing_webmaster_tools.ai_performance",
        method="manual_export_normalization",
        provenance={
            "transport": "manual_export",
            "provider_surface": "bing_webmaster_tools_ai_performance",
            "site_url": "https://getfixlist.com/",
            "import_name": "ai-performance.csv",
            "api_used": False,
        },
    )
    assert validate_connected_evidence_source_identity(evidence) is evidence


def test_bing_rejects_unregistered_programmatic_provenance_claim():
    evidence = _unavailable(
        provider="microsoft_bing_webmaster_tools",
        source_kind="ai_performance_export",
        surface="bing_webmaster_tools.ai_performance",
        method="manual_export_normalization",
        provenance={
            "transport": "manual_export",
            "provider_surface": "bing_webmaster_tools_ai_performance",
            "site_url": "https://getfixlist.com/",
            "api_used": False,
            "api_endpoint": "https://example.invalid/undocumented",
        },
    )
    with pytest.raises(ValueError, match="unregistered fields"):
        validate_connected_evidence_source_identity(evidence)


def test_ga4_registered_optional_import_name_is_accepted():
    evidence = _unavailable(
        provider="google_analytics_4",
        source_kind="ai_assistant_referrals",
        surface="google_analytics_4.referral_traffic",
        method="aggregate_row_normalization",
        provenance={
            "transport": "provided_rows",
            "provider_surface": "ga4_reporting_export_or_response",
            "property_id": "properties/123",
            "import_name": "ga4-export.csv",
        },
    )
    assert validate_connected_evidence_source_identity(evidence) is evidence


def test_ga4_rejects_unregistered_connection_provenance_claim():
    evidence = _unavailable(
        provider="google_analytics_4",
        source_kind="ai_assistant_referrals",
        surface="google_analytics_4.referral_traffic",
        method="aggregate_row_normalization",
        provenance={
            "transport": "provided_rows",
            "provider_surface": "ga4_reporting_export_or_response",
            "property_id": "properties/123",
            "oauth_scope": "should-not-be-carried",
        },
    )
    with pytest.raises(ValueError, match="unregistered fields"):
        validate_connected_evidence_source_identity(evidence)
