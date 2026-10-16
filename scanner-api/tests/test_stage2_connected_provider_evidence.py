from datetime import date

import pytest

from app.stage2_connected_provider_evidence import (
    CONNECTED_PROVIDER_EVIDENCE_VERSION,
    build_crux_scan_evidence,
    build_gsc_scan_evidence,
)
from app.stage2_coverage_evidence import CRUX_ADAPTER_VERSION, GSC_ADAPTER_VERSION


def test_crux_disconnected_and_unauthorized_connected_are_explicit_unknown_states():
    disconnected = build_crux_scan_evidence(
        expected_scan_id="scan-1",
        payload={"scan_id": "scan-1", "connection_state": "disconnected"},
        as_of=date(2026, 9, 20),
    )
    assert disconnected == {
        "version": CONNECTED_PROVIDER_EVIDENCE_VERSION,
        "adapter_version": CRUX_ADAPTER_VERSION,
        "provider": "CrUX",
        "scan_id": "scan-1",
        "source_scan_id": "scan-1",
        "state": "disconnected",
        "reason": "provider_disconnected",
        "observed_at": None,
        "coverage_complete_claim": False,
        "scope": None,
        "metrics": None,
    }

    unauthorized = build_crux_scan_evidence(
        expected_scan_id="scan-1",
        payload={
            "scan_id": "scan-1",
            "connection_state": "connected",
            "authorized": False,
            "observed_at": "2026-09-20",
            "scope": "origin",
            "metrics": {"lcp_ms": 1000},
        },
        as_of=date(2026, 9, 20),
    )
    assert unauthorized["state"] == "unavailable"
    assert unauthorized["reason"] == "owner_authorization_unverified"
    assert unauthorized["metrics"] is None


def test_crux_cross_scan_and_stale_payloads_fail_closed_without_metrics():
    mismatch = build_crux_scan_evidence(
        expected_scan_id="scan-current",
        payload={
            "scan_id": "scan-other",
            "connection_state": "connected",
            "authorized": True,
            "observed_at": "2026-09-20",
            "scope": "origin",
            "metrics": {"lcp_ms": 1000, "inp_ms": 100, "cls": 0.03},
        },
        as_of=date(2026, 9, 20),
    )
    assert mismatch["state"] == "unavailable"
    assert mismatch["reason"] == "scan_identity_mismatch"
    assert mismatch["metrics"] is None

    stale = build_crux_scan_evidence(
        expected_scan_id="scan-current",
        payload={
            "scan_id": "scan-current",
            "connection_state": "connected",
            "authorized": True,
            "observed_at": "2026-07-01",
            "scope": "origin",
            "metrics": {"lcp_ms": 1000, "inp_ms": 100, "cls": 0.03},
        },
        as_of=date(2026, 9, 20),
    )
    assert stale["state"] == "stale"
    assert stale["reason"] == "crux_evidence_stale"
    assert stale["metrics"] is None


def test_crux_connected_retains_only_bounded_metrics_scope_and_time():
    evidence = build_crux_scan_evidence(
        expected_scan_id="scan-current",
        payload={
            "scan_id": "scan-current",
            "connection_state": "connected",
            "authorized": True,
            "observed_at": "2026-09-10",
            "scope": "https://example.com/",
            "metrics": {
                "lcp_ms": 1800,
                "inp_ms": 120,
                "cls": 0.05,
                "html_bytes": 999999,
                "query": "never retain me",
            },
        },
        as_of=date(2026, 9, 20),
    )
    assert evidence["state"] == "connected"
    assert evidence["reason"] == "authorized_current_crux_evidence"
    assert evidence["scope"] == "https://example.com/"
    assert evidence["observed_at"] == "2026-09-10"
    assert evidence["metrics"] == {"lcp_ms": 1800, "inp_ms": 120, "cls": 0.05}
    assert evidence["coverage_complete_claim"] is False


def test_gsc_disconnected_unauthorized_and_cross_scan_never_retain_page_metrics():
    assessed = ["https://example.com/", "https://example.com/pricing"]
    for payload, reason, state in [
        ({"scan_id": "scan-1", "connection_state": "disconnected"}, "provider_disconnected", "disconnected"),
        (
            {
                "scan_id": "scan-1",
                "connection_state": "connected",
                "authorized": False,
                "observed_at": "2026-09-20",
                "pages": [{"url": assessed[0], "metrics": {"clicks": 10}}],
            },
            "owner_authorization_unverified",
            "unavailable",
        ),
        (
            {
                "scan_id": "scan-other",
                "connection_state": "connected",
                "authorized": True,
                "observed_at": "2026-09-20",
                "pages": [{"url": assessed[0], "metrics": {"clicks": 10}}],
            },
            "scan_identity_mismatch",
            "unavailable",
        ),
    ]:
        evidence = build_gsc_scan_evidence(
            expected_scan_id="scan-1",
            assessed_urls=assessed,
            payload=payload,
            as_of=date(2026, 9, 20),
        )
        assert evidence["state"] == state
        assert evidence["reason"] == reason
        assert evidence["pages"] == []
        assert evidence["coverage_complete_claim"] is False


def test_gsc_connected_filters_to_exact_assessed_urls_and_drops_unapproved_fields():
    assessed = ["https://example.com/Page", "https://example.com/page?x=1"]
    evidence = build_gsc_scan_evidence(
        expected_scan_id="scan-1",
        assessed_urls=assessed,
        payload={
            "scan_id": "scan-1",
            "connection_state": "connected",
            "authorized": True,
            "observed_at": "2026-09-19",
            "pages": [
                {
                    "url": "https://example.com/Page",
                    "metrics": {
                        "clicks": 12,
                        "impressions": 120,
                        "position": 3.5,
                        "index_state": "indexed",
                        "query": "secret query",
                    },
                },
                {
                    "url": "https://example.com/page",
                    "metrics": {"clicks": 999, "index_state": "indexed"},
                },
                {
                    "url": "https://example.com/page?x=1",
                    "metrics": {"clicks": -1, "impressions": 10, "position": 4, "index_state": "unknown"},
                },
            ],
        },
        as_of=date(2026, 9, 20),
    )
    assert evidence["state"] == "connected"
    assert evidence["adapter_version"] == GSC_ADAPTER_VERSION
    assert evidence["candidate_page_rows"] == 3
    assert evidence["selected_page_rows"] == 2
    assert evidence["rejected_outside_scan"] == 1
    by_url = {row["url"]: row for row in evidence["pages"]}
    assert by_url["https://example.com/Page"]["metrics"] == {
        "clicks": 12,
        "impressions": 120,
        "position": 3.5,
        "index_state": "indexed",
    }
    assert by_url["https://example.com/page?x=1"]["metrics"] == {
        "impressions": 10,
        "position": 4,
        "index_state": "unknown",
    }
    assert "query" not in repr(evidence)


def test_gsc_stale_data_and_conflicting_duplicate_rows_fail_closed():
    assessed = ["https://example.com/pricing"]
    stale = build_gsc_scan_evidence(
        expected_scan_id="scan-1",
        assessed_urls=assessed,
        payload={
            "scan_id": "scan-1",
            "connection_state": "connected",
            "authorized": True,
            "observed_at": "2026-09-01",
            "pages": [{"url": assessed[0], "metrics": {"clicks": 20, "index_state": "indexed"}}],
        },
        as_of=date(2026, 9, 20),
    )
    assert stale["state"] == "stale"
    assert stale["pages"][0]["state"] == "stale"
    assert stale["pages"][0]["metrics"] is None

    conflicted = build_gsc_scan_evidence(
        expected_scan_id="scan-1",
        assessed_urls=assessed,
        payload={
            "scan_id": "scan-1",
            "connection_state": "connected",
            "authorized": True,
            "observed_at": "2026-09-19",
            "pages": [
                {"url": assessed[0], "metrics": {"clicks": 10, "index_state": "indexed"}},
                {"url": assessed[0], "metrics": {"clicks": 11, "index_state": "indexed"}},
            ],
        },
        as_of=date(2026, 9, 20),
    )
    assert conflicted["state"] == "unavailable"
    assert conflicted["duplicate_conflicts"] == 1
    assert conflicted["pages"] == [
        {
            "url": assessed[0],
            "state": "unavailable",
            "reason": "duplicate_page_metrics_conflict",
            "metrics": None,
        }
    ]


def test_provider_assessed_url_bound_is_standard_150_not_silently_truncated():
    with pytest.raises(ValueError, match="at most 150"):
        build_gsc_scan_evidence(
            expected_scan_id="scan-1",
            assessed_urls=[f"https://example.com/{index}" for index in range(151)],
            payload={"scan_id": "scan-1", "connection_state": "disconnected"},
            as_of=date(2026, 9, 20),
        )
