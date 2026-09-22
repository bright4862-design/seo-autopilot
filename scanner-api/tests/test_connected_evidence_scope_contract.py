from copy import deepcopy

import pytest

import app.connected_evidence_scope_contract as scope_contract


def _gsc_search(*, property_uri="sc-domain:example.test", page="https://www.example.test/a"):
    return {
        "provider": "google_search_console",
        "source_kind": "search_analytics",
        "state": "verified",
        "provenance": {"property_uri": property_uri},
        "coverage": {"dimensions": ["page", "query"]},
        "records": [
            {
                "dimensions": {"page": page, "query": "technical seo"},
                "row_number": 1,
            }
        ],
    }


def _inspection(*, property_uri="sc-domain:example.test", url="https://www.example.test/a"):
    return {
        "provider": "google_search_console",
        "source_kind": "url_inspection",
        "state": "verified",
        "provenance": {"property_uri": property_uri, "inspection_url": url},
        "coverage": {"url_count": 1},
        "records": [{"inspection_url": url}],
    }


def _bing(*, site_url="https://example.test/docs/", url="https://example.test/docs/a"):
    return {
        "provider": "microsoft_bing_webmaster_tools",
        "source_kind": "ai_performance_export",
        "state": "verified",
        "provenance": {"site_url": site_url},
        "coverage": {},
        "records": [{"url": url}],
    }


def _ga4(*, property_id="properties/123", landing_page="/a?src=chatgpt"):
    return {
        "provider": "google_analytics_4",
        "source_kind": "ai_assistant_referrals",
        "state": "verified",
        "provenance": {"property_id": property_id},
        "coverage": {},
        "records": [{"landing_page": landing_page}],
    }


def test_scope_contract_version_is_explicit():
    assert scope_contract.SCOPE_SEMANTICS_VERSION == "connected_evidence_scope_semantics_v1"


def test_sc_domain_accepts_subdomain_page_and_preserves_input():
    evidence = _gsc_search()
    before = deepcopy(evidence)
    assert scope_contract.validate_connected_evidence_scope_semantics(evidence) is evidence
    assert evidence == before


def test_sc_domain_rejects_foreign_page_dimension():
    with pytest.raises(ValueError, match="outside the declared Search Console domain property"):
        scope_contract.validate_connected_evidence_scope_semantics(
            _gsc_search(page="https://example.test.evil.example/a")
        )


def test_sc_domain_property_rejects_path_or_port_syntax():
    for property_uri in ("sc-domain:example.test/path", "sc-domain:example.test:443"):
        with pytest.raises(ValueError, match="invalid sc-domain property"):
            scope_contract.validate_connected_evidence_scope_semantics(
                _gsc_search(property_uri=property_uri)
            )


def test_url_prefix_property_accepts_page_inside_prefix():
    evidence = _gsc_search(
        property_uri="https://example.test/docs/",
        page="https://example.test/docs/technical-seo?x=1",
    )
    assert scope_contract.validate_connected_evidence_scope_semantics(evidence) is evidence


def test_url_prefix_property_rejects_sibling_path():
    with pytest.raises(ValueError, match="outside the declared Search Console URL-prefix property"):
        scope_contract.validate_connected_evidence_scope_semantics(
            _gsc_search(
                property_uri="https://example.test/docs/",
                page="https://example.test/blog/a",
            )
        )


def test_url_prefix_property_rejects_host_confusion():
    with pytest.raises(ValueError, match="outside the declared Search Console URL-prefix property"):
        scope_contract.validate_connected_evidence_scope_semantics(
            _gsc_search(
                property_uri="https://example.test/",
                page="https://example.test.evil.example/a",
            )
        )


def test_url_inspection_accepts_subdomain_of_domain_property():
    evidence = _inspection(url="https://shop.example.test/a")
    assert scope_contract.validate_connected_evidence_scope_semantics(evidence) is evidence


def test_url_inspection_rejects_url_outside_domain_property():
    with pytest.raises(ValueError, match="outside the declared Search Console domain property"):
        scope_contract.validate_connected_evidence_scope_semantics(
            _inspection(url="https://other.test/a")
        )


def test_url_inspection_rejects_url_outside_url_prefix_path():
    with pytest.raises(ValueError, match="outside the declared Search Console URL-prefix property"):
        scope_contract.validate_connected_evidence_scope_semantics(
            _inspection(
                property_uri="https://example.test/docs/",
                url="https://example.test/other/a",
            )
        )


def test_search_analytics_without_page_dimension_has_no_page_scope_claim():
    evidence = _gsc_search()
    evidence["coverage"]["dimensions"] = ["query"]
    evidence["records"][0]["dimensions"] = {"query": "technical seo"}
    assert scope_contract.validate_connected_evidence_scope_semantics(evidence) is evidence


def test_bing_site_url_prefix_accepts_cited_page_inside_scope():
    evidence = _bing()
    assert scope_contract.validate_connected_evidence_scope_semantics(evidence) is evidence


def test_bing_site_url_prefix_rejects_same_host_page_outside_path_scope():
    with pytest.raises(ValueError, match="outside provenance.site_url scope"):
        scope_contract.validate_connected_evidence_scope_semantics(
            _bing(url="https://example.test/other/a")
        )


def test_ga4_accepts_native_property_resource_and_root_relative_landing_page():
    evidence = _ga4()
    assert scope_contract.validate_connected_evidence_scope_semantics(evidence) is evidence


def test_ga4_accepts_bare_numeric_property_id_for_import_compatibility():
    evidence = _ga4(property_id="123")
    assert scope_contract.validate_connected_evidence_scope_semantics(evidence) is evidence


def test_ga4_rejects_ambiguous_property_identifier():
    with pytest.raises(ValueError, match="not a GA4 property identifier"):
        scope_contract.validate_connected_evidence_scope_semantics(
            _ga4(property_id="UA-123")
        )


def test_ga4_rejects_absolute_or_scheme_relative_landing_page():
    for landing_page in ("https://evil.example/a", "//evil.example/a"):
        with pytest.raises(ValueError, match="root-relative GA4 landing-page path"):
            scope_contract.validate_connected_evidence_scope_semantics(
                _ga4(landing_page=landing_page)
            )


def test_ga4_allows_provider_not_set_landing_page_without_inventing_url_identity():
    evidence = _ga4(landing_page="(not set)")
    assert scope_contract.validate_connected_evidence_scope_semantics(evidence) is evidence
