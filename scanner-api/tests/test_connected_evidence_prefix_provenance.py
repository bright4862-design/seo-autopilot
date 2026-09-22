import pytest

from app.connected_evidence_source_contract import (
    validate_connected_evidence_source_identity,
)


def _envelope(*, provider, source_kind, surface, method, provenance):
    return {
        "schema_version": "connected_evidence_v1",
        "provider": provider,
        "surface": surface,
        "method": method,
        "source_kind": source_kind,
        "state": "verified",
        "retrieved_at": "2026-09-21T20:30:00Z",
        "observed_at": "2026-09-20T00:00:00Z",
        "sample": {"coverage_complete_claim": False},
        "confidence": {
            "kind": "evidence_quality_not_statistical_probability",
            "level": "first_party_provider_observed",
        },
        "provenance": provenance,
        "coverage": {},
        "records": [],
    }


def test_gsc_url_prefix_path_without_directory_boundary_fails_closed():
    evidence = _envelope(
        provider="google_search_console",
        source_kind="search_analytics",
        surface="google_search_console.search_analytics",
        method="api_response_normalization",
        provenance={
            "transport": "provided_payload",
            "provider_operation": "searchanalytics.query",
            "property_uri": "https://example.test/docs",
        },
    )
    with pytest.raises(ValueError, match="path-scoped prefixes must end"):
        validate_connected_evidence_source_identity(evidence)


def test_gsc_url_prefix_directory_form_is_accepted():
    evidence = _envelope(
        provider="google_search_console",
        source_kind="search_analytics",
        surface="google_search_console.search_analytics",
        method="api_response_normalization",
        provenance={
            "transport": "provided_payload",
            "provider_operation": "searchanalytics.query",
            "property_uri": "https://example.test/docs/",
        },
    )
    assert validate_connected_evidence_source_identity(evidence) is evidence


def test_bing_branch_path_without_directory_boundary_fails_closed():
    evidence = _envelope(
        provider="microsoft_bing_webmaster_tools",
        source_kind="ai_performance_export",
        surface="bing_webmaster_tools.ai_performance",
        method="manual_export_normalization",
        provenance={
            "transport": "manual_export",
            "provider_surface": "bing_webmaster_tools_ai_performance",
            "site_url": "https://example.test/docs",
            "api_used": False,
        },
    )
    with pytest.raises(ValueError, match="path-scoped prefixes must end"):
        validate_connected_evidence_source_identity(evidence)


def test_bing_branch_directory_form_is_accepted():
    evidence = _envelope(
        provider="microsoft_bing_webmaster_tools",
        source_kind="ai_performance_export",
        surface="bing_webmaster_tools.ai_performance",
        method="manual_export_normalization",
        provenance={
            "transport": "manual_export",
            "provider_surface": "bing_webmaster_tools_ai_performance",
            "site_url": "https://example.test/docs/",
            "api_used": False,
        },
    )
    assert validate_connected_evidence_source_identity(evidence) is evidence
