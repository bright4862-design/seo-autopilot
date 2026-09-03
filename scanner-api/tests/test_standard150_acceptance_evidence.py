from types import SimpleNamespace

import pytest

from app.acceptance_evidence import (
    ACCEPTANCE_EVIDENCE_VERSION,
    build_classification_integrity,
    measure_worker_peak_memory_bytes,
)
from app.beta_revision import live_revision


def test_classification_integrity_uses_the_reviewed_classifier_verdict():
    integrity = build_classification_integrity({
        "archetype_classifier_version": "classifier_v10",
        "site_fingerprint": {
            "classification": {
                "state": "classified",
                "evidence_sufficiency": "sufficient",
                "usable_pages": 150,
                "complete_small_site_inventory": False,
            },
        },
    })

    assert integrity == {
        "version": ACCEPTANCE_EVIDENCE_VERSION,
        "state": "classified",
        "verdict": "classified",
        "classifier_version": "classifier_v10",
        "evidence_sufficiency": "sufficient",
        "usable_pages": 150,
        "complete_small_site_inventory": False,
    }


def test_classification_integrity_does_not_invent_a_verdict_from_an_archetype():
    assert build_classification_integrity({
        "archetype_classifier_version": "classifier_v10",
        "site_fingerprint": {"primary_archetype": "ecommerce"},
    }) == {}


def test_worker_peak_memory_sums_parent_and_active_review_child_rss():
    rss = {
        101: 128 * 1024 * 1024,
        202: 192 * 1024 * 1024,
    }

    measured = measure_worker_peak_memory_bytes(
        child_pid=202,
        rss_reader=lambda pid: rss.get(pid),
        self_pid=101,
        platform="linux",
    )

    assert measured == 320 * 1024 * 1024


def test_worker_peak_memory_measurement_fails_closed_when_child_rss_is_unavailable():
    assert measure_worker_peak_memory_bytes(
        child_pid=202,
        rss_reader=lambda pid: 128 * 1024 * 1024 if pid == 101 else None,
        self_pid=101,
        platform="linux",
    ) is None


@pytest.mark.asyncio
async def test_completion_envelope_carries_measured_classification_and_memory(monkeypatch):
    from app import scan_job

    scan = {
        "id": "scan-acceptance",
        "status": "crawling",
        "attempt_count": 1,
        "project_id": "project-acceptance",
        "owner_user_id": "owner-acceptance",
    }
    result = {
        "normalized_domain": "example.com",
        "crawled_pages": [{
            "url": "https://example.com/",
            "status_code": 200,
            "page_evidence_class": "usable_html",
            "title": "Example",
        }],
    }
    review = {
        "release_gate_eligible": True,
        "site_fingerprint": {
            "classification": {
                "state": "classified",
                "evidence_sufficiency": "sufficient",
                "usable_pages": 1,
                "complete_small_site_inventory": True,
            },
        },
        "archetype_classifier_version": "classifier_v10",
        "beta_revision_fingerprint": live_revision()["fingerprint"],
    }
    captured = {}
    events = []

    async def read(*_args, **_kwargs):
        return dict(scan)

    async def persist(_client, function, envelope):
        captured["function"] = function
        captured["envelope"] = envelope
        return {
            "status_code": 200,
            "body": {
                "success": True,
                "fixListId": "fixlist-acceptance",
                "fixListVerified": True,
                "scanRun": {
                    "fix_list_id": "fixlist-acceptance",
                    "authority_proof": "a" * 64,
                },
            },
        }

    def capture_event(event, **fields):
        events.append((event, fields))
        return fields

    monkeypatch.setattr(scan_job, "read_scan_run", read)
    monkeypatch.setattr(scan_job, "invoke_function", persist)
    monkeypatch.setattr(scan_job, "measure_worker_peak_memory_bytes", lambda: 268_435_456)
    monkeypatch.setattr(scan_job, "emit", capture_event)

    outcome = await scan_job.complete_authority(
        object(),
        scan,
        result,
        "test-signing-key",
        review=review,
    )

    assert outcome["ok"] is True
    assert captured["function"] == "persistDurableScanAuthorityV2"
    assert captured["envelope"]["scan"]["peak_memory_bytes"] == 268_435_456
    assert captured["envelope"]["scan"]["worker_peak_memory_bytes"] == 268_435_456
    assert captured["envelope"]["review"]["classification_verdict"] == "classified"
    assert captured["envelope"]["review"]["classification_integrity"]["classifier_version"] == "classifier_v10"
    persist_start = next(
        fields for event, fields in events
        if event == "scan_job_completion_phase" and fields.get("phase") == "persist_start"
    )
    assert persist_start["archetype_classifier_version"] == "classifier_v10"
    assert persist_start["beta_revision_fingerprint"] == captured["envelope"]["review"]["beta_revision_fingerprint"]
    assert persist_start["scan_id"] == "scan-acceptance"
    assert persist_start["attempt_count"] == 1
    assert "review" not in persist_start
    assert "envelope" not in persist_start


@pytest.mark.asyncio
async def test_limited_envelope_carries_the_same_measured_acceptance_evidence(monkeypatch):
    from app import scan_job

    scan = {
        "id": "scan-limited-acceptance",
        "status": "crawling",
        "attempt_count": 1,
        "project_id": "project-acceptance",
        "owner_user_id": "owner-acceptance",
    }
    result = {"normalized_domain": "example.com", "pages_found": 500, "pages_crawled": 25}
    review = {
        "release_gate_eligible": False,
        "score_is_provisional": True,
        "scan_status": "inconclusive_insufficient_evidence",
        "recommendations": [{"fix_id": "fix-1", "issue_title": "Fix one checked page"}],
        "coverage_authority_evidence": {
            "coverage_authority_evidence_version": "coverage_v2",
            "assessment": "insufficient_sample",
        },
        "site_fingerprint": {
            "coverage_assessment": {"state": "limited_coverage", "reasons": ["sample_too_small"]},
            "classification": {
                "state": "classified",
                "evidence_sufficiency": "limited",
                "usable_pages": 25,
                "complete_small_site_inventory": False,
            },
        },
        "archetype_classifier_version": "classifier_v10",
    }
    captured = {}

    async def read(*_args, **_kwargs):
        return dict(scan)

    async def persist(_client, function, envelope):
        captured["function"] = function
        captured["envelope"] = envelope
        return {
            "status_code": 200,
            "body": {
                "success": True,
                "fixListId": "fixlist-limited-acceptance",
                "resultIntegrityVerified": True,
                "scanRun": {
                    "fix_list_id": "fixlist-limited-acceptance",
                    "result_integrity_proof": "b" * 64,
                },
            },
        }

    monkeypatch.setattr(scan_job, "read_scan_run", read)
    monkeypatch.setattr(scan_job, "invoke_function", persist)
    monkeypatch.setattr(scan_job, "measure_worker_peak_memory_bytes", lambda: 201_326_592)

    outcome = await scan_job.complete_authority(
        object(),
        scan,
        result,
        "test-signing-key",
        review=review,
    )

    assert outcome["ok"] is True
    assert outcome["limited"] is True
    assert captured["function"] == "persistLimitedScanResultV2"
    assert captured["envelope"]["scan"]["worker_peak_memory_bytes"] == 201_326_592
    assert captured["envelope"]["review"]["coverage_authority_evidence"]["assessment"] == "insufficient_sample"
    assert captured["envelope"]["review"]["classification_verdict"] == "classified"
    assert captured["envelope"]["review"]["classification_integrity"]["usable_pages"] == 25
