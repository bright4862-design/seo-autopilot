"""Staged completion must retain the aggregate sample from its cached review."""

import pytest

from app import scan_job


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("review_peak", "parent_rss", "expected_peak"),
    [
        (536_870_912, 134_217_728, 536_870_912),
        (134_217_728, 268_435_456, 268_435_456),
        (536_870_912, None, 536_870_912),
        (None, 134_217_728, None),
        (0, 134_217_728, None),
        (True, 134_217_728, None),
        ("536870912", 134_217_728, None),
    ],
)
@pytest.mark.parametrize("limited", [False, True])
async def test_staged_completion_preserves_cached_aggregate_memory(
    monkeypatch, review_peak, parent_rss, expected_peak, limited
):
    scan = {
        "id": "scan-memory",
        "status": "crawling",
        "attempt_count": 1,
        "project_id": "project-memory",
        "owner_user_id": "owner-memory",
        "scan_mode": "standard_150",
        "page_cap": 150,
        "pipeline_mode": "staged",
        "respect_robots_txt": True,
        "owner_attested_robots_override": False,
    }
    result = {
        "normalized_domain": "example.com",
        "pages_crawled": 1,
        "pipeline_limited": limited,
        "pipeline_limit_reason": "wall_budget" if limited else "",
        "respect_robots_txt": True,
        "owner_attested_robots_override": False,
        "crawled_pages": [{"url": "https://example.com/", "status_code": 200,
                           "page_evidence_class": "usable_html", "title": "Example"}],
    }
    review = {"release_gate_eligible": True, "recommendations": [],
              "_worker_peak_memory_bytes": review_peak}
    captured = {}

    async def read(*_args, **_kwargs):
        return dict(scan)

    async def persist(_client, function, envelope):
        captured.update(function=function, envelope=envelope)
        return {"status_code": 200, "body": {
            "success": True, "fixListId": "fixlist-memory", "fixListVerified": True,
            "resultIntegrityVerified": True,
            "scanRun": {"fix_list_id": "fixlist-memory", "authority_proof": "a" * 64,
                        "result_integrity_proof": "b" * 64},
        }}

    def unexpected_review(*_args, **_kwargs):
        pytest.fail("A supplied review must be reused without running review again")

    monkeypatch.setattr(scan_job, "read_scan_run", read)
    monkeypatch.setattr(scan_job, "invoke_function", persist)
    monkeypatch.setattr(scan_job, "measure_worker_peak_memory_bytes", lambda: parent_rss)
    monkeypatch.setattr(scan_job, "run_local_review_isolated", unexpected_review)
    with scan_job.worker_function_generation("V9"):
        outcome = await scan_job.complete_authority(object(), scan, result, "test-key", review=review)

    assert outcome["ok"] is True
    assert captured["function"] == ("persistLimitedScanResultV9" if limited else "persistDurableScanAuthorityV9")
    signed_scan = captured["envelope"]["scan"]
    if expected_peak is None:
        assert "worker_peak_memory_bytes" not in signed_scan
        assert "peak_memory_bytes" not in signed_scan
    else:
        assert signed_scan["worker_peak_memory_bytes"] == expected_peak
        assert signed_scan["peak_memory_bytes"] == expected_peak
    assert "_worker_peak_memory_bytes" not in captured["envelope"]["review"]
    assert review["_worker_peak_memory_bytes"] == review_peak
