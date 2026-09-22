import pytest

import app.connected_evidence_bundle_contract as bundle_contract


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


def _gsc(*, start, end, dimensions=("date", "query")):
    return {
        "provider": "google_search_console",
        "source_kind": "search_analytics",
        "state": "verified",
        "observed_at": f"{end}T00:00:00Z",
        "provenance": {"property_uri": "sc-domain:example.test"},
        "coverage": {
            "dimensions": list(dimensions),
            "period_start": start,
            "period_end": end,
        },
        "records": [],
    }


def _bing(*, start=None, end="2026-09-20"):
    coverage = {"period_end": end}
    if start is not None:
        coverage["period_start"] = start
    return {
        "provider": "microsoft_bing_webmaster_tools",
        "source_kind": "ai_performance_export",
        "state": "verified",
        "observed_at": f"{end}T00:00:00Z",
        "provenance": {"site_url": "https://example.test/"},
        "coverage": coverage,
        "records": [],
    }


def _ga4(*, start=None, end="2026-09-20"):
    coverage = {"period_end": end}
    if start is not None:
        coverage["period_start"] = start
    return {
        "provider": "google_analytics_4",
        "source_kind": "ai_assistant_referrals",
        "state": "verified",
        "observed_at": f"{end}T00:00:00Z",
        "provenance": {"property_id": "properties/123"},
        "coverage": coverage,
        "records": [],
    }


def test_snapshot_window_coherence_version_is_explicit():
    assert (
        bundle_contract.SNAPSHOT_WINDOW_COHERENCE_VERSION
        == "connected_evidence_snapshot_window_coherence_v1"
    )


def test_gsc_same_series_rejects_overlapping_windows_after_dimension_canonicalization(
    bypass_upstream,
):
    first = _gsc(
        start="2026-09-01",
        end="2026-09-15",
        dimensions=("date", "query"),
    )
    second = _gsc(
        start="2026-09-10",
        end="2026-09-20",
        dimensions=("query", "date"),
    )
    with pytest.raises(ValueError, match="overlapping connected-evidence observation windows"):
        bundle_contract.validate_connected_evidence_snapshot_bundle([first, second])


def test_gsc_same_series_allows_disjoint_windows(bypass_upstream):
    items = [
        _gsc(start="2026-09-01", end="2026-09-09"),
        _gsc(start="2026-09-10", end="2026-09-20"),
    ]
    assert bundle_contract.validate_connected_evidence_snapshot_bundle(items) is items


def test_gsc_different_dimension_series_may_overlap(bypass_upstream):
    items = [
        _gsc(
            start="2026-09-01",
            end="2026-09-20",
            dimensions=("date", "query"),
        ),
        _gsc(
            start="2026-09-10",
            end="2026-09-20",
            dimensions=("date", "page"),
        ),
    ]
    assert bundle_contract.validate_connected_evidence_snapshot_bundle(items) is items


def test_bing_same_site_rejects_overlapping_windows(bypass_upstream):
    first = _bing(start="2026-09-01", end="2026-09-15")
    second = _bing(start="2026-09-10", end="2026-09-20")
    with pytest.raises(ValueError, match="overlapping connected-evidence observation windows"):
        bundle_contract.validate_connected_evidence_snapshot_bundle([first, second])


def test_bing_same_site_allows_disjoint_windows(bypass_upstream):
    items = [
        _bing(start="2026-09-01", end="2026-09-09"),
        _bing(start="2026-09-10", end="2026-09-20"),
    ]
    assert bundle_contract.validate_connected_evidence_snapshot_bundle(items) is items


def test_ga4_same_property_rejects_overlapping_windows(bypass_upstream):
    first = _ga4(start="2026-09-01", end="2026-09-15")
    second = _ga4(start="2026-09-10", end="2026-09-20")
    with pytest.raises(ValueError, match="overlapping connected-evidence observation windows"):
        bundle_contract.validate_connected_evidence_snapshot_bundle([first, second])


def test_ga4_same_property_allows_disjoint_windows(bypass_upstream):
    items = [
        _ga4(start="2026-09-01", end="2026-09-09"),
        _ga4(start="2026-09-10", end="2026-09-20"),
    ]
    assert bundle_contract.validate_connected_evidence_snapshot_bundle(items) is items


def test_date_less_bing_windows_do_not_invent_overlap_start(bypass_upstream):
    items = [
        _bing(start=None, end="2026-09-19"),
        _bing(start=None, end="2026-09-20"),
    ]
    assert bundle_contract.validate_connected_evidence_snapshot_bundle(items) is items
