"""Durable Standard 150 job worker.

Base44 functions are reaped once the HTTP response returns, so a crawl started
with waitUntil() dies mid-flight: ScanRun 6a748d5f9e8a27963ae678dc logged
worker_scan_start and then produced nothing for 247s until the watchdog closed
it as orphaned_no_terminal_state.

Cloud Run holds a request for up to 300s (--timeout=300 in cloudbuild.yaml), so
the crawl runs here instead. Cloud Tasks delivers the job with an OIDC token,
retries safely, and the exact ScanRun carries the result.

Split of responsibility:
  Base44 startStandardScanJob  -> authenticate, verify the owner-bound ScanRun,
                                  enqueue the task, answer immediately.
  Cloud Run   /scan-job        -> crawl (the slow part), then hand the result to
                                  Base44 completeStandardScanJob, which already
                                  holds the signing key and does review +
                                  persistScanAuthority + allowance.

Idempotency is keyed on the existing scan_id: the task name is derived from it,
and this worker refuses to run against a ScanRun that already reached a terminal
state, so a Cloud Tasks retry can never produce a second FixList or a second
allowance charge.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

WORKER_VERSION = "scan_job_worker_v1_cloud_tasks"

# Cloud Run allows 300s; leave room to hand off the result and write a terminal
# state before the platform closes the request.
CRAWL_BUDGET_SECONDS = 210.0
HANDOFF_TIMEOUT_SECONDS = 60.0

TERMINAL_STATUSES = frozenset({"complete", "limited", "failed", "cancelled"})


def base44_api_url() -> str:
    return str(os.getenv("BASE44_API_URL") or "https://base44.app").rstrip("/")


def base44_app_id() -> str:
    return str(os.getenv("BASE44_APP_ID") or "")


def base44_service_token() -> str:
    return str(os.getenv("BASE44_SERVICE_TOKEN") or "")


def _service_headers() -> dict[str, str]:
    return {
        "content-type": "application/json",
        "Base44-Service-Authorization": base44_service_token(),
        "Base44-App-Id": base44_app_id(),
    }


def _function_url(name: str) -> str:
    return f"{base44_api_url()}/api/apps/{base44_app_id()}/functions/{name}"


async def read_scan_run(client: httpx.AsyncClient, scan_id: str) -> dict[str, Any] | None:
    """Read the exact ScanRun through the service-role entity API."""
    url = f"{base44_api_url()}/api/apps/{base44_app_id()}/entities/ScanRun/{scan_id}"
    try:
        response = await client.get(url, headers=_service_headers(), timeout=20.0)
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    try:
        body = response.json()
    except ValueError:
        return None
    return body if isinstance(body, dict) else None


async def write_terminal_failure(
    client: httpx.AsyncClient,
    scan_id: str,
    failure_code: str,
    detail: str,
) -> bool:
    """Close the exact ScanRun truthfully. Never fabricates evidence."""
    url = f"{base44_api_url()}/api/apps/{base44_app_id()}/entities/ScanRun/{scan_id}"
    payload = {
        "status": "failed",
        "status_detail": detail,
        "error_code": failure_code,
        "error_message": detail,
        "completed_at": _now_iso(),
        "release_gate_eligible": False,
    }
    try:
        response = await client.put(url, headers=_service_headers(), json=payload, timeout=20.0)
    except httpx.HTTPError:
        return False
    return response.status_code < 300


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def identity_matches(scan: dict[str, Any], job: dict[str, Any]) -> bool:
    """The task must name the same durable request the ScanRun was created for."""
    for field in ("request_id", "idempotency_key", "project_id"):
        stored = str(scan.get(field) or "").strip()
        claimed = str(job.get(field) or "").strip()
        if stored and claimed and stored != claimed:
            return False
    return True


def already_terminal(scan: dict[str, Any]) -> bool:
    return str(scan.get("status") or "").lower() in TERMINAL_STATUSES


def has_authority_proof(record: dict[str, Any]) -> bool:
    proof = str(record.get("authority_proof") or "")
    return len(proof) == 64 and all(c in "0123456789abcdef" for c in proof)


async def hand_off_result(
    client: httpx.AsyncClient,
    job: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    """Give the crawl result to Base44 for review + authority persistence.

    That side already holds SCAN_EVIDENCE_SIGNING_KEY and the review pipeline,
    and it is fast enough to finish inside a normal function invocation.
    """
    response = await client.post(
        _function_url("completeStandardScanJob"),
        headers=_service_headers(),
        json={
            "scan_id": job.get("scan_id"),
            "request_id": job.get("request_id"),
            "idempotency_key": job.get("idempotency_key"),
            "project_id": job.get("project_id"),
            "owner_user_id": job.get("owner_user_id"),
            "normalized_domain": job.get("normalized_domain"),
            "worker_version": WORKER_VERSION,
            "scanner_result": result,
        },
        timeout=HANDOFF_TIMEOUT_SECONDS,
    )
    try:
        body = response.json()
    except ValueError:
        body = {}
    return {"status_code": response.status_code, "body": body if isinstance(body, dict) else {}}
