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
        "retrieved_at": "2026-09-22T15:00:00Z",
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


def _gsc(property_uri):
    return _unavailable(
        provider="google_search_console",
        source_kind="search_analytics",
        surface="google_search_console.search_analytics",
        method="api_response_normalization",
        provenance={
            "transport": "provided_payload",
            "provider_operation": "searchanalytics.query",
            "property_uri": property_uri,
        },
    )


def _bing(site_url):
    return _unavailable(
        provider="microsoft_bing_webmaster_tools",
        source_kind="ai_performance_export",
        surface="bing_webmaster_tools.ai_performance",
        method="manual_export_normalization",
        provenance={
            "transport": "manual_export",
            "provider_surface": "bing_webmaster_tools_ai_performance",
            "site_url": site_url,
            "api_used": False,
        },
    )


def test_sc_domain_accepts_dns_identity_with_case_and_trailing_dot():
    evidence = _gsc("sc-domain:GetFixList.COM.")
    assert validate_connected_evidence_source_identity(evidence) is evidence


@pytest.mark.parametrize(
    "property_uri,match",
    [
        ("sc-domain:", "non-empty string"),
        ("sc-domain:https://getfixlist.com", "invalid sc-domain property"),
        ("sc-domain:127.0.0.1", "DNS domain"),
        ("sc-domain:*.getfixlist.com", "invalid host"),
    ],
)
def test_sc_domain_rejects_non_dns_property_identities(property_uri, match):
    with pytest.raises(ValueError, match=match):
        validate_connected_evidence_source_identity(_gsc(property_uri))


def test_gsc_url_prefix_rejects_embedded_userinfo():
    with pytest.raises(ValueError, match="must not contain URL userinfo"):
        validate_connected_evidence_source_identity(
            _gsc("https://user:password@getfixlist.com/docs/")
        )


def test_gsc_url_prefix_rejects_malformed_host_identity():
    with pytest.raises(ValueError, match="invalid host"):
        validate_connected_evidence_source_identity(
            _gsc("https://bad host.example/docs/")
        )


def test_bing_site_prefix_rejects_embedded_userinfo():
    with pytest.raises(ValueError, match="must not contain URL userinfo"):
        validate_connected_evidence_source_identity(
            _bing("https://user:password@getfixlist.com/docs/")
        )
