import copy

import pytest

from app.connected_evidence_coverage_contract import (
    COVERAGE_SEMANTICS_VERSION,
    validate_connected_evidence_coverage_semantics,
)


def _envelope(*, provider, source_kind, surface, method, provenance, records, sample, coverage):
    return {
        "schema_version": "connected_evidence_v1",
        "provider": provider,
        "surface": surface,
        "method": method,
        "source_kind": source_kind,
        "state": "verified",
        "retrieved_at": "2026-09-21T20:30:00Z",
        "observed_at": "2026-09-20T00:00:00Z",
        "sample": {"coverage_complete_claim": False, **sample},
        "confidence": {
            "kind": "evidence_quality_not_statistical_probability",
            "level": "first_party_provider_observed",
        },
        "provenance": provenance,
        "coverage": coverage,
        "records": records,
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
        records=[
            {
                "dimensions": {"date": "2026-09-20", "query": "technical seo"},
                "clicks": 1,
                "impressions": 10,
                "ctr": 0.1,
                "position": 2.0,
                "row_number": 1,
            }
        ],
        sample={"kind": "provider_aggregate_rows", "row_count": 1},
        coverage={
            "period_start": "2026-09-19",
            "period_end": "2026-09-20",
            "row_count": 1,
            "dimensions": ["date", "query"],
            "response_aggregation_type": "byProperty",
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
        records=[
            {
                "inspection_url": "https://getfixlist.com/a",
                "referring_urls": [],
                "sitemap": [],
            }
        ],
        sample={"kind": "single_url_inspection", "url_count": 1},
        coverage={"url_count": 1},
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
            "site_url": "https://getfixlist.com",
            "api_used": False,
        },
        records=[
            {
                "kind": "page_citation",
                "date": "2026-09-20",
                "url": "https://getfixlist.com/a",
                "grounding_query": None,
                "citations": 2,
                "average_cited_pages": None,
                "citation_share": 0.2,
                "row_number": 1,
            }
        ],
        sample={"kind": "provider_export_rows", "row_count": 1},
        coverage={
            "input_row_count": 2,
            "normalized_row_count": 1,
            "rejected_row_count": 1,
            "period_end": "2026-09-20",
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
        records=[
            {
                "assistant": "chatgpt",
                "date": "2026-09-20",
                "source": "chatgpt.com / referral",
                "sessions": 3,
                "engaged_sessions": 2,
                "users": 2,
                "key_events": 1.0,
                "revenue": 0.0,
                "row_number": 1,
            }
        ],
        sample={"kind": "analytics_aggregate_rows", "row_count": 1},
        coverage={
            "input_row_count": 3,
            "normalized_row_count": 1,
            "unmatched_row_count": 1,
            "rejected_row_count": 1,
            "period_end": "2026-09-20",
        },
    )


def test_coverage_contract_is_versioned_non_mutating_and_accepts_valid_gsc():
    evidence = _gsc()
    before = copy.deepcopy(evidence)
    assert COVERAGE_SEMANTICS_VERSION == "connected_evidence_coverage_semantics_v1"
    assert validate_connected_evidence_coverage_semantics(evidence) is evidence
    assert evidence == before


def test_gsc_sample_count_must_match_carried_records():
    evidence = _gsc()
    evidence["sample"]["row_count"] = 2
    with pytest.raises(ValueError, match="sample.row_count did not match"):
        validate_connected_evidence_coverage_semantics(evidence)


def test_gsc_coverage_count_must_match_carried_records():
    evidence = _gsc()
    evidence["coverage"]["row_count"] = 2
    with pytest.raises(ValueError, match="coverage.row_count did not match"):
        validate_connected_evidence_coverage_semantics(evidence)


def test_gsc_coverage_dimensions_must_match_each_record():
    evidence = _gsc()
    evidence["coverage"]["dimensions"] = ["date", "page"]
    with pytest.raises(ValueError, match="dimensions did not match coverage.dimensions"):
        validate_connected_evidence_coverage_semantics(evidence)


def test_gsc_date_dimension_must_fit_declared_period():
    evidence = _gsc()
    evidence["records"][0]["dimensions"]["date"] = "2026-09-18"
    with pytest.raises(ValueError, match="preceded coverage.period_start"):
        validate_connected_evidence_coverage_semantics(evidence)


def test_gsc_date_dimension_requires_period_bounds():
    evidence = _gsc()
    evidence["coverage"]["period_start"] = None
    with pytest.raises(ValueError, match="date-dimension evidence requires coverage period bounds"):
        validate_connected_evidence_coverage_semantics(evidence)


def test_url_inspection_sample_url_count_must_match_records():
    evidence = _inspection()
    evidence["sample"]["url_count"] = 2
    with pytest.raises(ValueError, match="sample.url_count did not match"):
        validate_connected_evidence_coverage_semantics(evidence)


def test_url_inspection_requires_observed_at():
    evidence = _inspection()
    evidence["observed_at"] = None
    with pytest.raises(ValueError, match="URL Inspection observed coverage requires observed_at"):
        validate_connected_evidence_coverage_semantics(evidence)


def test_bing_normalized_count_must_match_records():
    evidence = _bing()
    evidence["coverage"]["normalized_row_count"] = 2
    with pytest.raises(ValueError, match="normalized_row_count did not match"):
        validate_connected_evidence_coverage_semantics(evidence)


def test_bing_input_accounting_must_balance():
    evidence = _bing()
    evidence["coverage"]["input_row_count"] = 3
    with pytest.raises(ValueError, match="normalized_row_count \\+ rejected_row_count"):
        validate_connected_evidence_coverage_semantics(evidence)


def test_bing_record_date_cannot_exceed_observed_at():
    evidence = _bing()
    evidence["records"][0]["date"] = "2026-09-21"
    with pytest.raises(ValueError, match="date cannot be later than observed_at"):
        validate_connected_evidence_coverage_semantics(evidence)


def test_bing_period_end_requires_observed_at():
    evidence = _bing()
    evidence["observed_at"] = None
    with pytest.raises(ValueError, match="coverage.period_end requires observed_at"):
        validate_connected_evidence_coverage_semantics(evidence)


def test_bing_date_less_observation_can_remain_unbounded():
    evidence = _bing()
    evidence["observed_at"] = None
    evidence["coverage"]["period_end"] = None
    evidence["records"][0]["date"] = None
    assert validate_connected_evidence_coverage_semantics(evidence) is evidence


def test_ga4_normalized_count_must_match_records():
    evidence = _ga4()
    evidence["coverage"]["normalized_row_count"] = 2
    with pytest.raises(ValueError, match="normalized_row_count did not match"):
        validate_connected_evidence_coverage_semantics(evidence)


def test_ga4_input_accounting_must_balance():
    evidence = _ga4()
    evidence["coverage"]["input_row_count"] = 4
    with pytest.raises(ValueError, match="unmatched_row_count \\+ rejected_row_count"):
        validate_connected_evidence_coverage_semantics(evidence)


def test_period_end_must_match_observed_at():
    evidence = _ga4()
    evidence["coverage"]["period_end"] = "2026-09-19"
    with pytest.raises(ValueError, match="period_end did not match observed_at"):
        validate_connected_evidence_coverage_semantics(evidence)


def test_ga4_dated_record_requires_observed_at_even_without_period_end():
    evidence = _ga4()
    evidence["observed_at"] = None
    evidence["coverage"]["period_end"] = None
    with pytest.raises(ValueError, match="dated records require observed_at"):
        validate_connected_evidence_coverage_semantics(evidence)


def test_unavailable_evidence_keeps_no_record_accounting_claim():
    evidence = _ga4()
    evidence.update(
        {
            "state": "not_verified",
            "observed_at": None,
            "sample": {"coverage_complete_claim": False},
            "confidence": {
                "kind": "evidence_quality_not_statistical_probability",
                "level": "none",
            },
            "coverage": {},
            "records": [],
            "reason": "freshness could not be verified",
        }
    )
    assert validate_connected_evidence_coverage_semantics(evidence) is evidence
