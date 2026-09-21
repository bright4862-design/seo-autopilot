from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from app.connected_evidence import (
    normalize_bing_ai_performance_csv,
    normalize_bing_ai_performance_rows,
    normalize_ga4_ai_referral_rows,
    normalize_google_url_inspection,
    normalize_gsc_search_analytics,
    parse_csv_dict_rows,
    unavailable_evidence,
)

NOW = datetime(2026, 9, 21, 20, 30, tzinfo=timezone.utc)


def test_explicit_not_connected_contract_is_fail_closed():
    evidence = unavailable_evidence(
        provider="google_search_console",
        source_kind="search_analytics",
        state="not_connected",
        reason="property is not connected",
        retrieved_at=NOW,
    )
    assert evidence["state"] == "not_connected"
    assert evidence["records"] == []
    assert evidence["schema_version"] == "connected_evidence_v1"


def test_unavailable_contract_rejects_verified_state():
    with pytest.raises(ValueError):
        unavailable_evidence(
            provider="x",
            source_kind="y",
            state="verified",
            reason="wrong helper",
            retrieved_at=NOW,
        )


def test_gsc_search_analytics_normalizes_dimensions_metrics_and_provenance():
    result = normalize_gsc_search_analytics(
        {
            "rows": [
                {
                    "keys": ["2026-09-20", "technical seo"],
                    "clicks": 4,
                    "impressions": 100,
                    "ctr": 0.04,
                    "position": 8.2,
                }
            ]
        },
        dimensions=["date", "query"],
        property_uri="sc-domain:getfixlist.com",
        retrieved_at=NOW,
        stale_after_days=7,
    )
    assert result["state"] == "verified"
    assert result["coverage"]["period_start"] == "2026-09-20"
    assert result["coverage"]["period_end"] == "2026-09-20"
    assert result["records"][0]["dimensions"]["query"] == "technical seo"
    assert result["records"][0]["impressions"] == 100
    assert result["provenance"]["provider_operation"] == "searchanalytics.query"
    assert result["surface"] == "google_search_console.search_analytics"
    assert result["method"] == "api_response_normalization"
    assert result["sample"]["coverage_complete_claim"] is False
    assert result["confidence"]["level"] == "first_party_provider_observed"


def test_gsc_search_analytics_malformed_key_cardinality_is_not_verified():
    result = normalize_gsc_search_analytics(
        {"rows": [{"keys": ["technical seo"], "clicks": 1}]},
        dimensions=["date", "query"],
        property_uri="sc-domain:getfixlist.com",
        retrieved_at=NOW,
    )
    assert result["state"] == "not_verified"
    assert result["records"] == []
    assert "cardinality" in result["reason"]


def test_gsc_search_analytics_provider_error_is_explicit():
    result = normalize_gsc_search_analytics(
        {"error": {"code": 403}},
        dimensions=["query"],
        property_uri="sc-domain:getfixlist.com",
        retrieved_at=NOW,
    )
    assert result["state"] == "provider_error"


def test_google_url_inspection_normalizes_official_index_status_fields():
    result = normalize_google_url_inspection(
        {
            "inspectionResult": {
                "inspectionResultLink": "https://search.google.com/search-console/inspect?x=1",
                "indexStatusResult": {
                    "verdict": "PASS",
                    "coverageState": "Submitted and indexed",
                    "robotsTxtState": "ALLOWED",
                    "indexingState": "INDEXING_ALLOWED",
                    "pageFetchState": "SUCCESSFUL",
                    "googleCanonical": "https://getfixlist.com/technical-seo",
                    "userCanonical": "https://getfixlist.com/technical-seo",
                    "lastCrawlTime": "2026-09-20T10:00:00Z",
                    "crawledAs": "DESKTOP",
                    "referringUrls": ["https://getfixlist.com/"],
                    "sitemap": ["https://getfixlist.com/sitemap.xml"],
                },
            }
        },
        inspection_url="https://getfixlist.com/technical-seo",
        property_uri="sc-domain:getfixlist.com",
        retrieved_at=NOW,
    )
    assert result["state"] == "verified"
    row = result["records"][0]
    assert row["verdict"] == "PASS"
    assert row["robots_txt_state"] == "ALLOWED"
    assert row["page_fetch_state"] == "SUCCESSFUL"


def test_url_inspection_missing_result_fails_closed():
    result = normalize_google_url_inspection(
        {},
        inspection_url="https://getfixlist.com/",
        property_uri="sc-domain:getfixlist.com",
        retrieved_at=NOW,
    )
    assert result["state"] == "not_verified"
    assert result["records"] == []


def test_bing_ai_export_normalizes_page_query_mapping_without_claiming_api():
    result = normalize_bing_ai_performance_rows(
        [
            {
                "Date": "2026-09-20",
                "Grounding Query": "best technical seo audit",
                "Cited Page": "https://getfixlist.com/technical-seo",
                "Citation Count": "7",
                "Topic": "technical seo",
                "Intent": "commercial",
                "Citation Share": "12.5%",
                "Country": "FR",
                "Surface": "Copilot",
            }
        ],
        site_url="https://getfixlist.com",
        retrieved_at=NOW,
        import_name="ai-performance.xlsx",
    )
    assert result["state"] == "verified"
    assert result["records"][0]["kind"] == "grounding_query_page"
    assert result["records"][0]["citations"] == 7
    assert result["provenance"]["transport"] == "manual_export"
    assert result["provenance"]["api_used"] is False
    assert result["records"][0]["topic"] == "technical seo"
    assert result["records"][0]["intent"] == "commercial"
    assert result["records"][0]["citation_share"] == pytest.approx(0.125)
    assert result["records"][0]["country"] == "FR"
    assert result["records"][0]["surface"] == "Copilot"
    assert result["confidence"]["kind"] == "evidence_quality_not_statistical_probability"


def test_bing_ai_export_unknown_columns_are_not_supported():
    result = normalize_bing_ai_performance_rows(
        [{"Something Else": "x"}],
        site_url="https://getfixlist.com",
        retrieved_at=NOW,
    )
    assert result["state"] == "not_supported"
    assert result["records"] == []


def test_bing_csv_parser_handles_bom_and_alias_headers():
    result = normalize_bing_ai_performance_csv(
        "\ufeffDate,URL,Citations\n2026-09-20,https://getfixlist.com/a,3\n",
        site_url="https://getfixlist.com",
        retrieved_at=NOW,
    )
    assert result["state"] == "verified"
    assert result["records"][0]["url"] == "https://getfixlist.com/a"
    assert result["records"][0]["citations"] == 3


def test_ga4_normalizer_keeps_known_ai_referrals_and_excludes_normal_search():
    result = normalize_ga4_ai_referral_rows(
        [
            {
                "date": "20260920",
                "sessionSource": "chatgpt.com",
                "sessionMedium": "referral",
                "landingPagePlusQueryString": "/technical-seo?src=ai",
                "sessions": "12",
                "engagedSessions": "9",
                "keyEvents": "2",
                "country": "France",
                "deviceCategory": "desktop",
            },
            {
                "date": "20260920",
                "sessionSource": "google",
                "sessionMedium": "organic",
                "landingPage": "/technical-seo",
                "sessions": "50",
            },
        ],
        property_id="properties/123",
        retrieved_at=NOW,
        stale_after_days=None,
    )
    assert result["state"] == "verified"
    assert len(result["records"]) == 1
    assert result["records"][0]["assistant"] == "chatgpt"
    assert result["records"][0]["sessions"] == 12
    assert result["coverage"]["unmatched_row_count"] == 1
    assert result["records"][0]["country"] == "France"
    assert result["records"][0]["device_category"] == "desktop"
    assert result["sample"]["coverage_complete_claim"] is False


def test_ga4_unrecognized_referrals_are_not_verified_not_zero_visibility():
    result = normalize_ga4_ai_referral_rows(
        [{"sessionSource": "google", "sessions": 10}],
        property_id="properties/123",
        retrieved_at=NOW,
    )
    assert result["state"] == "not_verified"
    assert result["records"] == []


def test_old_export_is_explicitly_stale_while_retaining_records():
    result = normalize_bing_ai_performance_rows(
        [{"Date": "2026-08-01", "URL": "https://getfixlist.com/a", "Citations": 1}],
        site_url="https://getfixlist.com",
        retrieved_at=NOW,
        stale_after_days=7,
    )
    assert result["state"] == "stale"
    assert len(result["records"]) == 1


def test_csv_parser_rejects_duplicate_headers_after_normalization():
    with pytest.raises(ValueError):
        parse_csv_dict_rows("Grounding Query,grounding-query\na,b\n")


def test_sanitized_connector_fixtures_normalize_without_network_io():
    fixture_dir = Path(__file__).with_name("fixtures_connected_evidence")
    gsc = json.loads((fixture_dir / "gsc_search_analytics.json").read_text())
    inspection = json.loads((fixture_dir / "google_url_inspection.json").read_text())
    bing = json.loads((fixture_dir / "bing_ai_performance_rows.json").read_text())
    ga4 = json.loads((fixture_dir / "ga4_ai_referral_rows.json").read_text())

    assert normalize_gsc_search_analytics(
        gsc,
        dimensions=["date", "query"],
        property_uri="sc-domain:example.test",
        retrieved_at=NOW,
    )["state"] == "verified"
    assert normalize_google_url_inspection(
        inspection,
        inspection_url="https://example.test/technical-seo",
        property_uri="sc-domain:example.test",
        retrieved_at=NOW,
    )["state"] == "verified"
    assert normalize_bing_ai_performance_rows(
        bing,
        site_url="https://example.test",
        retrieved_at=NOW,
    )["state"] == "verified"
    assert normalize_ga4_ai_referral_rows(
        ga4,
        property_id="properties/000000000",
        retrieved_at=NOW,
        stale_after_days=None,
    )["state"] == "verified"


def test_gsc_date_less_observation_fails_closed_when_freshness_is_required():
    result = normalize_gsc_search_analytics(
        {"rows": [{"keys": ["technical seo"], "clicks": 1, "impressions": 10, "ctr": 0.1, "position": 5}]},
        dimensions=["query"],
        property_uri="sc-domain:getfixlist.com",
        retrieved_at=NOW,
        stale_after_days=7,
    )
    assert result["state"] == "not_verified"
    assert result["records"] == []
    assert result["observed_at"] is None
    assert "freshness could not be verified" in result["reason"]


def test_bing_date_less_observation_fails_closed_when_freshness_is_required():
    result = normalize_bing_ai_performance_rows(
        [{"URL": "https://getfixlist.com/a", "Citations": 2}],
        site_url="https://getfixlist.com",
        retrieved_at=NOW,
        stale_after_days=7,
    )
    assert result["state"] == "not_verified"
    assert result["records"] == []
    assert result["observed_at"] is None
    assert "freshness could not be verified" in result["reason"]


def test_ga4_date_less_observation_fails_closed_when_freshness_is_required():
    result = normalize_ga4_ai_referral_rows(
        [{"sessionSource": "chatgpt.com", "sessions": 3}],
        property_id="properties/123",
        retrieved_at=NOW,
        stale_after_days=7,
    )
    assert result["state"] == "not_verified"
    assert result["records"] == []
    assert result["observed_at"] is None
    assert "freshness could not be verified" in result["reason"]


def test_date_less_observation_can_be_retained_when_freshness_check_is_explicitly_disabled():
    result = normalize_bing_ai_performance_rows(
        [{"URL": "https://getfixlist.com/a", "Citations": 2}],
        site_url="https://getfixlist.com",
        retrieved_at=NOW,
        stale_after_days=None,
    )
    assert result["state"] == "verified"
    assert len(result["records"]) == 1
    assert result["observed_at"] is None


def test_future_observation_timestamp_fails_closed_instead_of_becoming_verified():
    result = normalize_bing_ai_performance_rows(
        [{"URL": "https://getfixlist.com/a", "Citations": 2}],
        site_url="https://getfixlist.com",
        retrieved_at=NOW,
        source_observed_at="2026-09-22T21:30:00Z",
        stale_after_days=7,
    )
    assert result["state"] == "not_verified"
    assert result["records"] == []
    assert result["observed_at"] is None


def test_unparseable_retrieved_at_is_rejected_before_any_envelope_is_emitted():
    with pytest.raises(ValueError, match="retrieved_at must be a parseable timestamp"):
        unavailable_evidence(
            provider="google_search_console",
            source_kind="search_analytics",
            state="not_connected",
            reason="property is not connected",
            retrieved_at="not-a-timestamp",
        )


def test_bing_rejected_recent_row_cannot_make_old_accepted_evidence_fresh():
    result = normalize_bing_ai_performance_rows(
        [
            {"Date": "2026-08-01", "URL": "https://getfixlist.com/a", "Citations": 1},
            {"Date": "2026-09-20", "Topic": "recognized but not an evidence-bearing row"},
        ],
        site_url="https://getfixlist.com",
        retrieved_at=NOW,
        stale_after_days=7,
    )
    assert result["state"] == "stale"
    assert result["observed_at"] == "2026-08-01T00:00:00Z"
    assert result["coverage"]["period_end"] == "2026-08-01"
    assert result["coverage"]["rejected_row_count"] == 1
    assert len(result["records"]) == 1


def test_ga4_rejected_recent_row_cannot_make_old_accepted_evidence_fresh():
    result = normalize_ga4_ai_referral_rows(
        [
            {"date": "2026-08-01", "sessionSource": "chatgpt.com", "sessions": 1},
            {"date": "2026-09-20", "sessionSource": "chatgpt.com", "sessions": -1},
        ],
        property_id="properties/123",
        retrieved_at=NOW,
        stale_after_days=7,
    )
    assert result["state"] == "stale"
    assert result["observed_at"] == "2026-08-01T00:00:00Z"
    assert result["coverage"]["period_end"] == "2026-08-01"
    assert result["coverage"]["rejected_row_count"] == 1
    assert len(result["records"]) == 1
