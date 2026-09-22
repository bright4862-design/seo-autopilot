from copy import deepcopy
from datetime import datetime, timezone

import pytest

import app.connected_evidence_bundle_contract as bundle_contract
from app.connected_evidence import (
    normalize_bing_ai_performance_rows,
    normalize_ga4_ai_referral_rows,
    normalize_google_url_inspection,
    normalize_gsc_search_analytics,
)


UNAVAILABLE = {"not_connected", "not_supported", "not_verified", "provider_error"}
NOW = datetime(2026, 9, 21, 20, 30, tzinfo=timezone.utc)


def _gsc(*, period_end="2026-09-20", state="verified", property_uri="sc-domain:example.test"):
    return {
        "provider": "google_search_console",
        "source_kind": "search_analytics",
        "state": state,
        "observed_at": None if state in UNAVAILABLE else f"{period_end}T00:00:00Z",
        "provenance": {"property_uri": property_uri},
        "coverage": {}
        if state in UNAVAILABLE
        else {
            "dimensions": ["date", "query"],
            "period_start": period_end,
            "period_end": period_end,
        },
    }


def _inspection(*, url="https://example.test/a", property_uri="sc-domain:example.test", state="verified"):
    return {
        "provider": "google_search_console",
        "source_kind": "url_inspection",
        "state": state,
        "observed_at": None if state in UNAVAILABLE else "2026-09-20T00:00:00Z",
        "provenance": {
            "property_uri": property_uri,
            "inspection_url": url,
        },
        "coverage": {} if state in UNAVAILABLE else {"url_count": 1},
    }


def _bing(*, period_end="2026-09-20", import_name="a.csv", state="verified", site_url="https://example.test"):
    return {
        "provider": "microsoft_bing_webmaster_tools",
        "source_kind": "ai_performance_export",
        "state": state,
        "observed_at": None if state in UNAVAILABLE else f"{period_end}T00:00:00Z",
        "provenance": {
            "site_url": site_url,
            "import_name": import_name,
        },
        "coverage": {} if state in UNAVAILABLE else {"period_start": period_end, "period_end": period_end},
    }


def _ga4(*, period_end="2026-09-20", state="verified", property_id="properties/123"):
    return {
        "provider": "google_analytics_4",
        "source_kind": "ai_assistant_referrals",
        "state": state,
        "observed_at": None if state in UNAVAILABLE else f"{period_end}T00:00:00Z",
        "provenance": {"property_id": property_id},
        "coverage": {} if state in UNAVAILABLE else {"period_start": period_end, "period_end": period_end},
    }


@pytest.fixture
def bypass_upstream(monkeypatch):
    seen = []

    def _accept(evidence):
        seen.append(evidence)
        return evidence

    monkeypatch.setattr(
        bundle_contract,
        "validate_connected_evidence_record_identity_semantics",
        _accept,
    )
    return seen


def test_empty_snapshot_bundle_is_valid_and_unchanged(bypass_upstream):
    items = []
    assert bundle_contract.validate_connected_evidence_snapshot_bundle(items) is items
    assert bypass_upstream == []


def test_snapshot_bundle_rejects_non_sequence():
    with pytest.raises(ValueError, match="must be a sequence"):
        bundle_contract.validate_connected_evidence_snapshot_bundle(iter(()))


def test_snapshot_bundle_rejects_oversized_input(bypass_upstream):
    items = [_gsc(period_end=f"2026-08-{(index % 28) + 1:02d}") for index in range(65)]
    with pytest.raises(ValueError, match="exceeds item bound"):
        bundle_contract.validate_connected_evidence_snapshot_bundle(items)


def test_snapshot_bundle_rejects_non_mapping_member(bypass_upstream):
    with pytest.raises(ValueError, match=r"evidence_items\[0\] must be an object"):
        bundle_contract.validate_connected_evidence_snapshot_bundle(["not-an-envelope"])


def test_snapshot_bundle_invokes_record_identity_boundary_for_every_item(bypass_upstream):
    first = _gsc()
    second = _inspection()
    items = [first, second]
    assert bundle_contract.validate_connected_evidence_snapshot_bundle(items) is items
    assert bypass_upstream == [first, second]


def test_duplicate_gsc_snapshot_identity_fails_closed(bypass_upstream):
    items = [_gsc(), deepcopy(_gsc())]
    with pytest.raises(ValueError, match="duplicate connected-evidence snapshot identity"):
        bundle_contract.validate_connected_evidence_snapshot_bundle(items)


def test_gsc_same_property_different_periods_are_distinct(bypass_upstream):
    items = [_gsc(period_end="2026-09-19"), _gsc(period_end="2026-09-20")]
    assert bundle_contract.validate_connected_evidence_snapshot_bundle(items) is items


def test_gsc_unavailable_states_share_one_source_scope_and_cannot_conflict(bypass_upstream):
    first = _gsc(state="not_connected")
    second = _gsc(state="provider_error")
    with pytest.raises(ValueError, match="duplicate connected-evidence snapshot identity"):
        bundle_contract.validate_connected_evidence_snapshot_bundle([first, second])


def test_duplicate_url_inspection_identity_fails_even_if_observation_time_differs(bypass_upstream):
    first = _inspection()
    second = deepcopy(first)
    second["observed_at"] = "2026-09-21T00:00:00Z"
    with pytest.raises(ValueError, match="duplicate connected-evidence snapshot identity"):
        bundle_contract.validate_connected_evidence_snapshot_bundle([first, second])


def test_bing_import_filename_is_not_part_of_observation_identity(bypass_upstream):
    first = _bing(import_name="export-a.csv")
    second = _bing(import_name="renamed-copy.csv")
    with pytest.raises(ValueError, match="duplicate connected-evidence snapshot identity"):
        bundle_contract.validate_connected_evidence_snapshot_bundle([first, second])


def test_ga4_same_property_same_window_fails_closed_as_duplicate(bypass_upstream):
    first = _ga4()
    second = deepcopy(first)
    with pytest.raises(ValueError, match="duplicate connected-evidence snapshot identity"):
        bundle_contract.validate_connected_evidence_snapshot_bundle([first, second])


def test_snapshot_identity_is_deterministic_and_does_not_mutate_input(bypass_upstream):
    evidence = _bing(import_name="one.csv")
    before = deepcopy(evidence)
    first = bundle_contract.connected_evidence_snapshot_identity(evidence)
    evidence["provenance"]["import_name"] = "two.csv"
    second = bundle_contract.connected_evidence_snapshot_identity(evidence)
    assert first == second
    assert before["coverage"] == evidence["coverage"]


def test_real_composed_boundary_rejects_invalid_envelope_without_monkeypatch():
    with pytest.raises(ValueError):
        bundle_contract.validate_connected_evidence_snapshot_bundle([{}])


def test_real_composed_boundary_accepts_all_registered_normalizer_outputs():
    gsc = normalize_gsc_search_analytics(
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
        property_uri="sc-domain:example.test",
        retrieved_at=NOW,
    )
    inspection = normalize_google_url_inspection(
        {
            "inspectionResult": {
                "inspectionResultLink": "https://search.google.com/search-console/inspect?x=1",
                "indexStatusResult": {
                    "verdict": "PASS",
                    "coverageState": "Submitted and indexed",
                    "robotsTxtState": "ALLOWED",
                    "indexingState": "INDEXING_ALLOWED",
                    "pageFetchState": "SUCCESSFUL",
                    "googleCanonical": "https://example.test/a",
                    "userCanonical": "https://example.test/a",
                    "lastCrawlTime": "2026-09-20T10:00:00Z",
                    "crawledAs": "DESKTOP",
                    "referringUrls": ["https://example.test/"],
                    "sitemap": ["https://example.test/sitemap.xml"],
                },
            }
        },
        inspection_url="https://example.test/a",
        property_uri="sc-domain:example.test",
        retrieved_at=NOW,
    )
    bing = normalize_bing_ai_performance_rows(
        [
            {
                "Date": "2026-09-20",
                "Grounding Query": "best technical seo audit",
                "Cited Page": "https://example.test/a",
                "Citation Count": "7",
                "Topic": "technical seo",
                "Intent": "commercial",
                "Citation Share": "12.5%",
                "Country": "FR",
                "Surface": "Copilot",
            }
        ],
        site_url="https://example.test",
        retrieved_at=NOW,
    )
    ga4 = normalize_ga4_ai_referral_rows(
        [
            {
                "date": "20260920",
                "sessionSource": "chatgpt.com",
                "sessionMedium": "referral",
                "landingPagePlusQueryString": "/a?src=ai",
                "sessions": "12",
                "engagedSessions": "9",
                "keyEvents": "2",
                "country": "France",
                "deviceCategory": "desktop",
            }
        ],
        property_id="properties/123",
        retrieved_at=NOW,
        stale_after_days=None,
    )
    items = [gsc, inspection, bing, ga4]
    assert bundle_contract.validate_connected_evidence_snapshot_bundle(items) is items


def test_real_composed_boundary_accepts_registered_unavailable_provider_error():
    evidence = normalize_gsc_search_analytics(
        {"error": {"code": 403}},
        dimensions=["query"],
        property_uri="sc-domain:example.test",
        retrieved_at=NOW,
    )
    assert evidence["state"] == "provider_error"
    items = [evidence]
    assert bundle_contract.validate_connected_evidence_snapshot_bundle(items) is items


def test_real_composed_boundary_rejects_unavailable_observation_metadata_smuggling():
    evidence = normalize_gsc_search_analytics(
        {"error": {"code": 403}},
        dimensions=["query"],
        property_uri="sc-domain:example.test",
        retrieved_at=NOW,
    )
    evidence["coverage"] = {"row_count": 0, "period_end": "2026-09-20"}
    with pytest.raises(ValueError, match="cannot claim coverage observations"):
        bundle_contract.validate_connected_evidence_snapshot_bundle([evidence])


def test_snapshot_source_identity_version_is_explicit():
    assert (
        bundle_contract.SNAPSHOT_SOURCE_IDENTITY_VERSION
        == "connected_evidence_snapshot_source_identity_v1"
    )


def test_gsc_snapshot_identity_canonicalizes_domain_case_and_trailing_dot(bypass_upstream):
    first = _gsc(property_uri="sc-domain:Example.Test.")
    second = _gsc(property_uri="sc-domain:example.test")
    with pytest.raises(ValueError, match="duplicate connected-evidence snapshot identity"):
        bundle_contract.validate_connected_evidence_snapshot_bundle([first, second])


def test_url_inspection_snapshot_identity_canonicalizes_default_port_and_host_case(bypass_upstream):
    first = _inspection(
        property_uri="sc-domain:Example.Test.",
        url="https://EXAMPLE.test:443/a",
    )
    second = _inspection(
        property_uri="sc-domain:example.test",
        url="https://example.test/a",
    )
    with pytest.raises(ValueError, match="duplicate connected-evidence snapshot identity"):
        bundle_contract.validate_connected_evidence_snapshot_bundle([first, second])


def test_bing_snapshot_identity_canonicalizes_default_port_and_root_slash(bypass_upstream):
    first = _bing(site_url="https://EXAMPLE.test:443")
    second = _bing(site_url="https://example.test/")
    with pytest.raises(ValueError, match="duplicate connected-evidence snapshot identity"):
        bundle_contract.validate_connected_evidence_snapshot_bundle([first, second])


def test_ga4_snapshot_identity_canonicalizes_property_resource_alias(bypass_upstream):
    first = _ga4(property_id="properties/123")
    second = _ga4(property_id="123")
    with pytest.raises(ValueError, match="duplicate connected-evidence snapshot identity"):
        bundle_contract.validate_connected_evidence_snapshot_bundle([first, second])


def test_gsc_observed_and_unavailable_same_property_fail_closed(bypass_upstream):
    with pytest.raises(ValueError, match="contradictory connected-evidence availability states"):
        bundle_contract.validate_connected_evidence_snapshot_bundle(
            [_gsc(state="verified"), _gsc(state="not_connected")]
        )


def test_bing_observed_and_unavailable_same_site_fail_closed(bypass_upstream):
    with pytest.raises(ValueError, match="contradictory connected-evidence availability states"):
        bundle_contract.validate_connected_evidence_snapshot_bundle(
            [_bing(state="verified"), _bing(state="provider_error")]
        )


def test_ga4_observed_and_unavailable_same_property_fail_closed(bypass_upstream):
    with pytest.raises(ValueError, match="contradictory connected-evidence availability states"):
        bundle_contract.validate_connected_evidence_snapshot_bundle(
            [_ga4(state="stale"), _ga4(state="not_verified")]
        )
