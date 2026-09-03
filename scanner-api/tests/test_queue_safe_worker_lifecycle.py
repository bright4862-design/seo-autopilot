"""Queue-safe worker lifecycle regression tests."""

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app import main
from app import scan_job
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


def _scan(*, status: str, started_at: str = "", queued_at: str = "", worker_heartbeat_at: str = "") -> dict:
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
        "worker_heartbeat_at": worker_heartbeat_at,
        "queued_at": queued_at,
    }


@pytest.mark.asyncio
async def test_drain_never_terminalizes_a_fresh_scan_still_waiting_in_queue(monkeypatch):
    monkeypatch.setattr(main, "require_cloud_tasks_oidc", lambda _: None)
    queued = datetime.now(timezone.utc) - timedelta(seconds=300)
    monkeypatch.setattr(main, "read_scan_run", lambda *_: _async_value(_scan(status="queued", queued_at=queued.isoformat())))
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
async def test_drain_closes_an_exact_attempt_after_thirty_minutes_queued(monkeypatch):
    monkeypatch.setattr(main, "require_cloud_tasks_oidc", lambda _: None)
    queued = datetime.now(timezone.utc) - timedelta(seconds=main.WORKER_QUEUED_DRAIN_AFTER_QUEUE_SECONDS + 30)
    monkeypatch.setattr(main, "read_scan_run", lambda *_: _async_value(_scan(status="queued", queued_at=queued.isoformat())))
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
    args, kwargs = calls[0]
    assert args[1] == "scan-1"
    assert args[2] == "scan_queue_drain_timeout"
    assert kwargs["attempt_count"] == 1


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
async def test_drain_closes_a_vanished_worker_after_heartbeat_deadline(monkeypatch):
    monkeypatch.setattr(main, "require_cloud_tasks_oidc", lambda _: None)
    started = datetime.now(timezone.utc) - timedelta(minutes=20)
    heartbeat = datetime.now(timezone.utc) - timedelta(seconds=main.WORKER_HEARTBEAT_DRAIN_AFTER_SECONDS + 30)
    monkeypatch.setattr(main, "read_scan_run", lambda *_: _async_value(_scan(
        status="crawling",
        started_at=started.isoformat(),
        worker_heartbeat_at=heartbeat.isoformat(),
    )))
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
    args, kwargs = calls[0]
    assert args[2] == "worker_heartbeat_timeout"
    assert kwargs["attempt_count"] == 1


@pytest.mark.asyncio
async def test_drain_preserves_a_worker_with_a_fresh_heartbeat(monkeypatch):
    monkeypatch.setattr(main, "require_cloud_tasks_oidc", lambda _: None)
    started = datetime.now(timezone.utc) - timedelta(minutes=20)
    heartbeat = datetime.now(timezone.utc) - timedelta(seconds=60)
    monkeypatch.setattr(main, "read_scan_run", lambda *_: _async_value(_scan(
        status="crawling",
        started_at=started.isoformat(),
        worker_heartbeat_at=heartbeat.isoformat(),
    )))
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
    assert main.WORKER_QUEUED_DRAIN_AFTER_QUEUE_SECONDS >= 30 * 60
    assert main.WORKER_HEARTBEAT_DRAIN_AFTER_SECONDS > 480 + 300
    assert main.WORKER_HEARTBEAT_DRAIN_AFTER_SECONDS < main.WORKER_TERMINAL_DRAIN_AFTER_START_SECONDS


@pytest.mark.asyncio
async def test_reconcile_route_is_private_and_returns_only_safe_counts(monkeypatch):
    monkeypatch.setattr(main, "require_cloud_tasks_oidc", lambda _: None)

    async def reconcile(_client):
        return {
            "examined": 8,
            "closed": 1,
            "released": 2,
            "superseded": 1,
            "satisfied_unbound": 1,
            "pending": 2,
            "retryable": 0,
            "paginated": 3,
            "skipped": 1,
            "errors": 0,
        }

    monkeypatch.setattr(main, "reconcile_stale_scans", reconcile)
    result = await main.scan_reconcile(authorization="test")
    assert result["success"] is True
    assert result["reconciliation"] == {
        "examined": 8,
        "closed": 1,
        "released": 2,
        "superseded": 1,
        "satisfied_unbound": 1,
        "pending": 2,
        "retryable": 0,
        "paginated": 3,
        "skipped": 1,
        "errors": 0,
    }


@pytest.mark.asyncio
async def test_reconcile_client_preserves_every_safe_durable_counter(monkeypatch):
    monkeypatch.setenv("SCAN_EVIDENCE_SIGNING_KEY", "test-signing-key")

    async def invoke(_client, function_name, _payload, *, timeout):
        assert function_name == "durableScanWorkerControlV2"
        assert timeout <= 60.0
        return {
            "status_code": 200,
            "body": {
                "success": True,
                "reconciliation": {
                    "examined": 61,
                    "closed": 2,
                    "released": 17,
                    "superseded": 11,
                    "satisfied_unbound": 7,
                    "pending": 19,
                    "retryable": 0,
                    "paginated": 75,
                    "skipped": 5,
                    "errors": 0,
                    "secret": "must-not-pass",
                },
            },
        }

    monkeypatch.setattr(scan_job, "invoke_function", invoke)
    counts = await scan_job.reconcile_stale_scans(object())
    assert counts == {
        "examined": 61,
        "closed": 2,
        "released": 17,
        "superseded": 11,
        "satisfied_unbound": 7,
        "pending": 19,
        "retryable": 0,
        "paginated": 75,
        "skipped": 5,
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body,expected",
    [
        ({"success": False, "error_code": "worker_reconciliation_tracking_failed"},
         "worker_reconciliation_tracking_failed"),
        ({"success": False, "error_code": "worker_reconciliation_source_invalid"},
         "worker_reconciliation_source_invalid"),
        ({"success": False, "error_code": "worker_reconciliation_query_failed"},
         "worker_reconciliation_query_failed"),
        ({"success": False}, "absent"),
        ({"success": False, "error_code": "Not an identifier!"}, "unrecognized"),
        ({"success": False, "error_code": "x" * 200}, "unrecognized"),
    ],
)
async def test_reconcile_records_the_code_base44_actually_returned(monkeypatch, capsys, body, expected):
    """A rejected sweep must name its upstream cause.

    The sweep's first act is a coordinator call, made before any scan row is
    read, so a rejected signing root, a missing release identity and a failed
    candidate query all reach the worker as one opaque 503. Without the upstream
    code in the log the three are indistinguishable from Cloud Logging alone.
    """
    monkeypatch.setenv("SCAN_EVIDENCE_SIGNING_KEY", "test-signing-key")

    async def invoke(_client, _function_name, _payload, *, timeout):
        return {"status_code": 503, "body": body}

    monkeypatch.setattr(scan_job, "invoke_function", invoke)
    with pytest.raises(RuntimeError):
        await scan_job.reconcile_stale_scans(object())

    records = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("{")
    ]
    rejected = [r for r in records if r.get("event") == "scan_reconcile_rejected"]
    assert len(rejected) == 1, records
    assert rejected[0]["severity"] == "WARNING"
    assert rejected[0]["status_code"] == 503
    assert rejected[0]["upstream_error_code"] == expected

    # An unrecognized upstream body must be reported by shape, never by content.
    if expected == "unrecognized":
        assert "x" * 200 not in json.dumps(rejected[0])
        assert "Not an identifier!" not in json.dumps(rejected[0])
