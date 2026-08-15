"""Queue-safe worker lifecycle regression tests."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app import main
from app.main import ScanDrainRequest


def _payload() -> ScanDrainRequest:
    return ScanDrainRequest(
        scan_id="scan-1",
        request_id="req-1",
        idempotency_key="req-1",
        project_id="project-1",
        owner_user_id="owner-1",
        website_url="https://example.com/",
        normalized_domain="example.com",
        drain_after=(datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
    )


def _scan(*, status: str, started_at: str = "") -> dict:
    return {
        "id": "scan-1",
        "scan_id": "scan-1",
        "request_id": "req-1",
        "idempotency_key": "req-1",
        "project_id": "project-1",
        "owner_user_id": "owner-1",
        "website_url": "https://example.com/",
        "normalized_domain": "example.com",
        "attempt_count": 1,
        "status": status,
        "started_at": started_at,
    }


@pytest.mark.asyncio
async def test_drain_never_terminalizes_a_scan_still_waiting_in_queue(monkeypatch):
    monkeypatch.setattr(main, "require_cloud_tasks_oidc", lambda _: None)
    monkeypatch.setattr(main, "read_scan_run", lambda *_: _async_value(_scan(status="queued")))
    called = False

    async def fail(*_args, **_kwargs):
        nonlocal called
        called = True
        return True

    monkeypatch.setattr(main, "write_terminal_failure", fail)
    with pytest.raises(HTTPException) as exc:
        await main.scan_job_drain(_payload(), authorization="test")
    assert exc.value.status_code == 503
    assert "not started" in str(exc.value.detail).lower()
    assert called is False


@pytest.mark.asyncio
async def test_drain_deadline_is_measured_from_worker_started_at(monkeypatch):
    monkeypatch.setattr(main, "require_cloud_tasks_oidc", lambda _: None)
    started = datetime.now(timezone.utc) - timedelta(seconds=300)
    monkeypatch.setattr(main, "read_scan_run", lambda *_: _async_value(_scan(status="crawling", started_at=started.isoformat())))
    called = False

    async def fail(*_args, **_kwargs):
        nonlocal called
        called = True
        return True

    monkeypatch.setattr(main, "write_terminal_failure", fail)
    with pytest.raises(HTTPException) as exc:
        await main.scan_job_drain(_payload(), authorization="test")
    assert exc.value.status_code == 503
    assert "deadline" in str(exc.value.detail).lower()
    assert called is False


@pytest.mark.asyncio
async def test_drain_closes_only_after_worker_start_deadline(monkeypatch):
    monkeypatch.setattr(main, "require_cloud_tasks_oidc", lambda _: None)
    started = datetime.now(timezone.utc) - timedelta(seconds=main.WORKER_TERMINAL_DRAIN_AFTER_START_SECONDS + 30)
    monkeypatch.setattr(main, "read_scan_run", lambda *_: _async_value(_scan(status="crawling", started_at=started.isoformat())))
    calls = []

    async def fail(*args, **kwargs):
        calls.append((args, kwargs))
        return True

    monkeypatch.setattr(main, "write_terminal_failure", fail)
    result = await main.scan_job_drain(_payload(), authorization="test")
    assert result["success"] is True
    assert result["closed"] is True
    assert result["status"] == "failed"
    assert len(calls) == 1


async def _async_value(value):
    return value


def test_terminal_drain_waits_for_the_full_three_dispatch_attempt_envelope():
    assert main.WORKER_TERMINAL_DRAIN_AFTER_START_SECONDS >= (3 * 480) + 30


@pytest.mark.asyncio
async def test_reconcile_route_is_private_and_returns_only_safe_counts(monkeypatch):
    monkeypatch.setattr(main, "require_cloud_tasks_oidc", lambda _: None)

    async def reconcile(_client):
        return {"examined": 4, "closed": 1, "released": 2, "skipped": 1, "errors": 0}

    monkeypatch.setattr(main, "reconcile_stale_scans", reconcile)
    result = await main.scan_reconcile(authorization="test")
    assert result["success"] is True
    assert result["reconciliation"] == {
        "examined": 4,
        "closed": 1,
        "released": 2,
        "skipped": 1,
        "errors": 0,
    }


@pytest.mark.asyncio
async def test_reconcile_route_fails_transiently_when_base44_sweep_is_unavailable(monkeypatch):
    monkeypatch.setattr(main, "require_cloud_tasks_oidc", lambda _: None)

    async def reconcile(_client):
        raise RuntimeError("unavailable")

    monkeypatch.setattr(main, "reconcile_stale_scans", reconcile)
    with pytest.raises(HTTPException) as exc:
        await main.scan_reconcile(authorization="test")
    assert exc.value.status_code == 503
