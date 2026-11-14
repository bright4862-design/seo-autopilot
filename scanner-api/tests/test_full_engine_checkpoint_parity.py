"""Exact current-engine parity through real fetch/extraction and JSON checkpoints.

The network maps are hand-authored fixture responses, not live third-party
captures. This establishes checkpoint equivalence at the current source; the
historical selection-v8/pre-extraction baseline does not exist in Git history.
Clock sources are fixed before either execution. No output fields are removed.
"""
from datetime import datetime, timezone
import json
import time

import pytest

from app import page_importance, scan_job, scan_timing, scanner, stage2_freshness_producer
from tests import fixtures as fx


_FIXED_NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return _FIXED_NOW.astimezone(tz) if tz is not None else _FIXED_NOW.replace(tzinfo=None)


@pytest.fixture
def fixed_scan_clock(monkeypatch):
    # Monotonic controls deadlines/pacing/elapsed fields; wall time controls the
    # checkpoint conversion. datetime sources control timestamps and recency.
    monkeypatch.setattr(time, "monotonic", lambda: 1000.0)
    monkeypatch.setattr(time, "time", lambda: _FIXED_NOW.timestamp())
    for module in (scanner, scan_timing, page_importance, stage2_freshness_producer):
        monkeypatch.setattr(module, "datetime", _FrozenDatetime)


def _checkpoint_fixture():
    origin = "https://checkpoint-parity.example"
    hubs = [f"{origin}/{section}" for section in ("products", "solutions", "insights")]
    leaves = [f"{hub}/page-{index}" for hub in hubs for index in range(30)]
    target = origin + "/products/target"
    # Lower depth importance ensures this redirect is fetched in a later batch
    # than its homepage-linked target, exercising cross-checkpoint dedup.
    alias = origin + "/solutions/old/deep/examples/late-target"
    private = origin + "/private/page"
    inventory = hubs + leaves + [target, alias, private]
    routes = {
        origin + "/": fx._html(fx._page("Home", links=hubs + [target])),
        origin + "/robots.txt": fx._text("User-agent: *\nDisallow: /private\n"),
        origin + "/sitemap.xml": fx._xml(fx._sitemap(inventory)),
        **{url: fx._html(fx._page(url, links=[target])) for url in hubs + leaves},
        target: fx._html(fx._page("Target", canonical=target)),
        alias: {"status": 301, "headers": {"location": target}, "body": ""},
    }
    return origin + "/", None, routes, target, alias


def _canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


@pytest.mark.asyncio
@pytest.mark.parametrize("fixture", ["pretto", "funbooker", "center_street", "meilleurtaux", "cross_batch"])
async def test_full_results_and_legacy_signed_bytes_survive_every_json_checkpoint(
    fixture, fixed_scan_clock, mock_network,
):
    cases = {
        "pretto": (fx.PRETTO_START, fx.PRETTO_PREFIX, fx.PRETTO_ROUTES),
        "funbooker": (fx.FB_START, fx.FB_PREFIX, fx.FB_ROUTES),
        "center_street": (fx.CS_START, fx.CS_PREFIX, fx.CS_ROUTES),
        "meilleurtaux": (fx.MT_START, fx.MT_PREFIX, fx.MT_ROUTES),
    }
    target = alias = None
    if fixture == "cross_batch":
        start, prefix, routes, target, alias = _checkpoint_fixture()
    else:
        start, prefix, routes = cases[fixture]
    first_requests = mock_network(routes)
    uninterrupted = await scanner.run_scan(start, path_prefix=prefix, concurrency=1)
    first_request_identities = [(request.method, request.headers["host"], request.url.raw_path)
                                for request in first_requests]

    restored_requests = mock_network(routes)
    state = await scanner.plan_scan(start, path_prefix=prefix, concurrency=1)
    state = scanner.ScanState.from_dict(json.loads(json.dumps(state.to_dict())))
    batches = 0
    first_batch_merges = None
    while not state.finished:
        await scanner.crawl_batch(state, max_pages=50)
        batches += 1
        if batches == 1:
            first_batch_merges = len(state.duplicate_merges)
        state = scanner.ScanState.from_dict(json.loads(json.dumps(state.to_dict())))
    restored = await scanner.finalize_scan(state)

    assert uninterrupted["success"] is True
    assert _canonical_bytes(restored) == _canonical_bytes(uninterrupted)
    assert [(request.method, request.headers["host"], request.url.raw_path)
            for request in restored_requests] == first_request_identities
    if fixture == "cross_batch":
        assert batches >= 2
        assert len(state.duplicate_merges) > first_batch_merges
        assert any(merge["duplicate_url"] == alias and merge["retained_url"] == target
                   for merge in state.duplicate_merges)
        assert state.robots_policy.allowed("FixListPythonScanner", start + "private/page") is False

    scan = {"id": "checkpoint-scan", "owner_user_id": "checkpoint-owner",
            "project_id": "checkpoint-project", "request_id": "checkpoint-request",
            "idempotency_key": "checkpoint-request", "attempt_count": 1}
    with scan_job.worker_function_generation("V8"):
        original_envelope = scan_job.build_completion_envelope(
            scan, uninterrupted, scan_job.build_local_review(uninterrupted), "checkpoint-key",
        )
        restored_envelope = scan_job.build_completion_envelope(
            scan, restored, scan_job.build_local_review(restored), "checkpoint-key",
        )
    assert _canonical_bytes(restored_envelope) == _canonical_bytes(original_envelope)
    assert restored_envelope["proof"] == original_envelope["proof"]
