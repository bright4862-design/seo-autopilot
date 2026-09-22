from copy import deepcopy

import pytest

import app.connected_evidence_bundle_contract as bundle_contract


def _gsc(*, period_end="2026-09-20", state="verified", property_uri="sc-domain:example.test"):
    return {
        "provider": "google_search_console",
        "source_kind": "search_analytics",
        "state": state,
        "observed_at": None if state in {"not_connected", "not_supported", "not_verified", "provider_error"} else f"{period_end}T00:00:00Z",
        "provenance": {"property_uri": property_uri},
        "coverage": {}
        if state in {"not_connected", "not_supported", "not_verified", "provider_error"}
        else {
            "dimensions": ["date", "query"],
            "period_start": period_end,
            "period_end": period_end,
        },
    }


def _inspection(*, url="https://example.test/a"):
    return {
        "provider": "google_search_console",
        "source_kind": "url_inspection",
        "state": "verified",
        "observed_at": "2026-09-20T00:00:00Z",
        "provenance": {
            "property_uri": "sc-domain:example.test",
            "inspection_url": url,
        },
        "coverage": {"url_count": 1},
    }


def _bing(*, period_end="2026-09-20", import_name="a.csv"):
    return {
        "provider": "microsoft_bing_webmaster_tools",
        "source_kind": "ai_performance_export",
        "state": "verified",
        "observed_at": f"{period_end}T00:00:00Z",
        "provenance": {
            "site_url": "https://example.test",
            "import_name": import_name,
        },
        "coverage": {"period_start": period_end, "period_end": period_end},
    }


def _ga4(*, period_end="2026-09-20"):
    return {
        "provider": "google_analytics_4",
        "source_kind": "ai_assistant_referrals",
        "state": "verified",
        "observed_at": f"{period_end}T00:00:00Z",
        "provenance": {"property_id": "properties/123"},
        "coverage": {"period_start": period_end, "period_end": period_end},
    }


@pytest.fixture
def bypass_upstream(monkeypatch):
    seen = []

    def _accept(evidence):
        seen.append(evidence)
        return evidence

    monkeypatch.setattr(
        bundle_contract,
        "validate_connected_evidence_scope_semantics",
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


def test_snapshot_bundle_invokes_full_scope_boundary_for_every_item(bypass_upstream):
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
