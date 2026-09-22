from copy import deepcopy

import pytest

import app.connected_evidence_bundle_contract as bundle_contract


def _gsc(
    *,
    dimensions=None,
    period_start="2026-09-20",
    period_end="2026-09-20",
    observed_at="2026-09-20T00:00:00Z",
):
    return {
        "provider": "google_search_console",
        "source_kind": "search_analytics",
        "state": "verified",
        "observed_at": observed_at,
        "provenance": {"property_uri": "sc-domain:example.test"},
        "coverage": {
            "dimensions": dimensions or ["date", "query"],
            "period_start": period_start,
            "period_end": period_end,
        },
        "records": [],
    }


def _bing(*, start_date="2026-09-01"):
    return {
        "provider": "microsoft_bing_webmaster_tools",
        "source_kind": "ai_performance_export",
        "state": "verified",
        "observed_at": "2026-09-20T00:00:00Z",
        "provenance": {
            "site_url": "https://example.test",
            "import_name": "ai-performance.csv",
        },
        "coverage": {"period_end": "2026-09-20"},
        "records": [{"date": start_date}],
    }


def _ga4(*, start_date="2026-09-01"):
    return {
        "provider": "google_analytics_4",
        "source_kind": "ai_assistant_referrals",
        "state": "verified",
        "observed_at": "2026-09-20T00:00:00Z",
        "provenance": {"property_id": "properties/123"},
        "coverage": {"period_end": "2026-09-20"},
        "records": [{"date": start_date}],
    }


@pytest.fixture(autouse=True)
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


def test_snapshot_observation_identity_version_is_explicit():
    assert (
        bundle_contract.SNAPSHOT_OBSERVATION_IDENTITY_VERSION
        == "connected_evidence_snapshot_observation_identity_v1"
    )


def test_gsc_dimension_order_alias_cannot_evade_duplicate_detection():
    first = _gsc(dimensions=["date", "query"])
    second = _gsc(dimensions=["query", "date"])
    with pytest.raises(ValueError, match="duplicate connected-evidence snapshot identity"):
        bundle_contract.validate_connected_evidence_snapshot_bundle([first, second])


def test_temporal_aliases_for_same_utc_window_cannot_evade_duplicate_detection():
    first = _gsc(
        period_start="2026-09-20",
        period_end="2026-09-20",
        observed_at="2026-09-20T00:00:00Z",
    )
    second = _gsc(
        period_start="2026-09-20T00:00:00+00:00",
        period_end="2026-09-19T20:00:00-04:00",
        observed_at="2026-09-19T20:00:00-04:00",
    )
    with pytest.raises(ValueError, match="duplicate connected-evidence snapshot identity"):
        bundle_contract.validate_connected_evidence_snapshot_bundle([first, second])


def test_bing_record_dates_distinguish_same_end_different_windows_without_period_start():
    first = _bing(start_date="2026-09-01")
    second = _bing(start_date="2026-09-10")
    items = [first, second]
    assert bundle_contract.validate_connected_evidence_snapshot_bundle(items) is items


def test_ga4_record_dates_distinguish_same_end_different_windows_without_period_start():
    first = _ga4(start_date="2026-09-01")
    second = _ga4(start_date="2026-09-10")
    items = [first, second]
    assert bundle_contract.validate_connected_evidence_snapshot_bundle(items) is items


def test_same_inferred_bing_window_still_fails_closed_as_duplicate():
    first = _bing(start_date="2026-09-01")
    second = deepcopy(first)
    second["provenance"]["import_name"] = "renamed-export.csv"
    with pytest.raises(ValueError, match="duplicate connected-evidence snapshot identity"):
        bundle_contract.validate_connected_evidence_snapshot_bundle([first, second])
