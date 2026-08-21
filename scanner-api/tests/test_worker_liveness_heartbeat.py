"""Worker liveness contract for the GetYourGuide post-crawl heartbeat gap.

ScanRun 6a85a93ab35fa769e397f194 reached `crawling`, heartbeat, then silence:
it never reached `reviewing` and the reconciler closed it 15 minutes later as
`worker_heartbeat_timeout`. Admission was fine -- the lease released cleanly --
and GetYourGuide HTML was independently retrievable, so this was not a site
block.

Two defects produced that shape:

1. Liveness was written only at phase edges. Every phase is bounded well below
   the reconciler's 15-minute window, but a phase that legitimately ran for
   minutes left the row silent for its whole duration.
2. The post-crawl transforms ran synchronously and unbounded on the event loop.
   A blocked loop starves the heartbeat AND every asyncio deadline, so no wall
   timeout could fire and no terminal state was ever written.

These tests pin the behaviors, not the strings: the heartbeat must beat while
real work continues, must stop at the end of the job, must never fail a scan,
and must never keep beating for work that has already stopped.
"""

import asyncio

import pytest

from app.scan_job import (
    WORKER_HEARTBEAT_INTERVAL_SECONDS,
    worker_liveness_heartbeat,
)

SCAN = {"id": "6a85a93ab35fa769e397f194", "scan_id": "6a85a93ab35fa769e397f194"}


class _Recorder:
    """Counts heartbeat writes without touching Base44."""

    def __init__(self, fail: bool = False) -> None:
        self.beats = 0
        self.scan_ids: list[str] = []
        self.fail = fail

    async def __call__(self, _client, scan):
        self.beats += 1
        self.scan_ids.append(str(scan.get("id") or ""))
        if self.fail:
            raise RuntimeError("durable start state unavailable")
        return scan


@pytest.fixture
def recorder(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr("app.scan_job.mark_scan_started", rec)
    return rec


# ------------------------------------------------------- liveness coverage --

@pytest.mark.asyncio
async def test_heartbeat_beats_while_legitimate_post_crawl_work_continues(recorder):
    """The GetYourGuide gap: slow post-crawl work must not look like a dead worker."""
    async with worker_liveness_heartbeat(None, SCAN, interval=0.01):
        # Stand in for normalization/synthesis that legitimately takes a while.
        await asyncio.sleep(0.12)

    assert recorder.beats >= 3, f"expected repeated liveness, saw {recorder.beats}"
    assert set(recorder.scan_ids) == {SCAN["id"]}, "heartbeat must target the exact ScanRun"


@pytest.mark.asyncio
async def test_heartbeat_stops_when_the_job_ends(recorder):
    """A finished job must stop claiming liveness, so the reconciler still works."""
    async with worker_liveness_heartbeat(None, SCAN, interval=0.01):
        await asyncio.sleep(0.05)
    settled = recorder.beats

    await asyncio.sleep(0.08)
    assert recorder.beats == settled, "heartbeat kept beating after the job ended"


@pytest.mark.asyncio
async def test_heartbeat_stops_when_the_job_raises(recorder):
    """An exception path must not leak a beating task that fakes liveness forever."""
    with pytest.raises(ValueError):
        async with worker_liveness_heartbeat(None, SCAN, interval=0.01):
            await asyncio.sleep(0.03)
            raise ValueError("synthesis failed")
    settled = recorder.beats

    await asyncio.sleep(0.06)
    assert recorder.beats == settled, "heartbeat survived a failing job"


@pytest.mark.asyncio
async def test_a_failing_beat_never_fails_the_scan(monkeypatch):
    """Liveness is best effort. The reconciler remains the backstop."""
    rec = _Recorder(fail=True)
    monkeypatch.setattr("app.scan_job.mark_scan_started", rec)

    async with worker_liveness_heartbeat(None, SCAN, interval=0.01):
        await asyncio.sleep(0.05)

    assert rec.beats >= 2, "a failing beat must be retried, not abandoned"


@pytest.mark.asyncio
async def test_heartbeat_does_not_beat_for_instant_work(recorder):
    """The beat is periodic, not per-call: a fast job costs no extra writes."""
    async with worker_liveness_heartbeat(None, SCAN, interval=5.0):
        pass

    assert recorder.beats == 0


# --------------------------------------------------------------- interval ---

def test_heartbeat_interval_stays_well_inside_the_reconciler_window():
    """A beat must be far more frequent than the 15-minute reconciler threshold.

    reconciliation.js closes a run at RECONCILE_HEARTBEAT_AFTER_MS = 15 minutes.
    """
    assert 0 < WORKER_HEARTBEAT_INTERVAL_SECONDS <= 300, WORKER_HEARTBEAT_INTERVAL_SECONDS


@pytest.mark.asyncio
async def test_heartbeat_cannot_hide_an_unbounded_wait(recorder):
    """Liveness must never be able to extend a phase deadline.

    The heartbeat keeps the row alive, but the work it covers still has to carry
    its own bound. Here the bounded operation times out on schedule even while
    the heartbeat is happily beating.
    """
    async with worker_liveness_heartbeat(None, SCAN, interval=0.01):
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(asyncio.Event().wait(), timeout=0.05)

    assert recorder.beats >= 1, "the heartbeat should have been alive throughout"
