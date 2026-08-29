"""Durable Standard 150 job worker helpers.

Base44 functions are reaped once the HTTP response returns, so a crawl started
with waitUntil() dies mid-flight. Cloud Tasks now delivers one durable request
to a private Cloud Run worker. The worker crawls and reviews locally, then sends
signed control and completion envelopes to Base44-hosted functions. Only those
hosted functions use Base44 service-role entity access.

Idempotency is keyed on the existing scan_id. A terminal run is never scanned
twice, permanent failures close the exact ScanRun, and transient persistence
failures raise so Cloud Tasks retries the same durable request.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import json
import multiprocessing as mp
import os
import time
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlparse

import httpx

from .acceptance_evidence import (
    build_classification_integrity,
    measure_worker_peak_memory_bytes,
)
from .observability import emit

WORKER_VERSION = "scan_job_worker_v1_cloud_tasks"
CONTROL_VERSION = "durable_standard150_control_v1"
COMPLETION_VERSION = "durable_standard150_completion_v1"

# Cloud Run allows 300s; leave room to review, persist, and write a terminal
# state before the platform closes the request.
CRAWL_BUDGET_SECONDS = 210.0
HANDOFF_TIMEOUT_SECONDS = 60.0
# The local review is CPU/synchronous work. It runs in a separate process,
# rather than merely a thread, so a pathological regex/parser that monopolizes
# the Python GIL cannot starve the durable worker event loop or its deadlines.
# Normal Standard 150 reviews finish far below this ceiling.
LOCAL_REVIEW_WALL_TIMEOUT_SECONDS = 20.0
LOCAL_REVIEW_PROCESS_JOIN_GRACE_SECONDS = 1.0

# The reconciler closes any run whose heartbeat is older than 15 minutes. Each
# worker phase is individually bounded well below that, but liveness used to be
# written only at phase edges, so the row stayed silent for the whole of a slow
# phase. A periodic beat keeps `worker_heartbeat_at` truthful for exactly as
# long as real work is still running.
WORKER_HEARTBEAT_INTERVAL_SECONDS = 60.0

TERMINAL_STATUSES = frozenset({"complete", "limited", "failed", "cancelled"})
BASE44_WORKER_USER_AGENT = (
    "Mozilla/5.0 (compatible; FixListStandard150Worker/1.0; +https://getfixlist.com)"
)


def base44_api_url() -> str:
    return str(os.getenv("BASE44_API_URL") or "https://base44.app").rstrip("/")


def base44_app_id() -> str:
    return str(os.getenv("BASE44_APP_ID") or "")


def _service_headers() -> dict[str, str]:
    """Headers for signed Base44 function calls.

    Service-role entity access is intentionally not attempted from Cloud Run.
    The Base44-hosted function verifies the HMAC envelope and then uses
    createClientFromRequest(req).asServiceRole internally.
    """
    return {
        "content-type": "application/json",
        "X-FixList-Worker": WORKER_VERSION,
        "User-Agent": BASE44_WORKER_USER_AGENT,
    }


def _function_url(name: str) -> str:
    return f"{base44_api_url()}/api/apps/{base44_app_id()}/functions/{name}"


async def invoke_function(
    client: httpx.AsyncClient,
    name: str,
    payload: dict[str, Any],
    timeout: float = HANDOFF_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Call one Base44-hosted function with a signed worker envelope."""
    try:
        response = await client.post(
            _function_url(name), headers=_service_headers(), json=payload, timeout=timeout
        )
    except httpx.HTTPError as error:
        emit(
            "base44_function_handoff",
            severity="WARNING",
            function=name,
            transport_error_class=type(error).__name__,
        )
        return {"status_code": 503, "body": {}}

    response_headers = getattr(response, "headers", {}) or {}
    content_type = str(response_headers.get("content-type") or "").split(";", 1)[0][:120]
    base44_request_id = str(
        response_headers.get("x-base44-request-id")
        or response_headers.get("x-request-id")
        or ""
    )[:160]
    cloudflare_ray_id = str(response_headers.get("cf-ray") or "")[:160]
    emit(
        "base44_function_handoff",
        severity="WARNING" if response.status_code >= 400 else "INFO",
        function=name,
        response_status=int(response.status_code),
        content_type=content_type,
        base44_request_id=base44_request_id or None,
        cloudflare_ray_id=cloudflare_ray_id or None,
    )

    try:
        body = response.json()
    except ValueError:
        body = {}
    if isinstance(body, dict):
        body = body.get("data") if isinstance(body.get("data"), dict) else body
    return {"status_code": response.status_code, "body": body if isinstance(body, dict) else {}}


# ---------------------------------------------------------------- authority --
# Canonical serialisation must match authoritySeal.js byte for byte: object
# keys sorted, unsupported values dropped/nulled, and no whitespace.

SCAN_ATTESTATION_VERSION = "standard_scan_review_payload_hmac_v2"
REVIEW_PAGE_SAMPLE_LIMIT = 60
REVIEW_FINDING_LIMIT = 100


def canonicalize(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        return int(value) if value.is_integer() else value
    if isinstance(value, int):
        return value
    if isinstance(value, list):
        return [canonicalize(item) for item in value]
    if isinstance(value, dict):
        return {key: canonicalize(value[key]) for key in sorted(value)}
    return None


def stable_serialize(value: Any) -> str:
    return json.dumps(canonicalize(value), separators=(",", ":"), ensure_ascii=False)


def create_authority_seal(payload: Any, secret: str) -> str:
    return hmac.new(secret.encode(), stable_serialize(payload).encode(), hashlib.sha256).hexdigest()


def build_control_envelope(
    action: str,
    signing_key: str,
    *,
    scan_id: str | None = None,
    identity: dict[str, Any] | None = None,
    failure: dict[str, Any] | None = None,
) -> dict[str, Any]:
    signed = {
        "version": CONTROL_VERSION,
        "action": action,
        "scan_id": scan_id,
        "identity": identity,
        "failure": failure,
    }
    return {**signed, "proof": create_authority_seal(signed, signing_key)}


def normalize_attempt(value: Any) -> int:
    """Attempts are 1-based; anything unparseable is attempt 1."""
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 1


def current_attempt(scan: dict[str, Any]) -> int:
    return normalize_attempt(scan.get("attempt_count"))


def is_superseded_attempt(scan: dict[str, Any], job_attempt: Any) -> bool:
    """True when the durable row has moved on past the task's attempt.

    Cloud Tasks can deliver a task minted for attempt 1 long after the browser
    restarted the row as attempt 2. That task must not crawl, write a failure,
    persist authority, charge allowance or finalise -- the newer attempt owns
    the row. A task ahead of the row is also refused: it cannot be legitimate.
    """
    return normalize_attempt(job_attempt) != current_attempt(scan)


def _scan_identity(scan: dict[str, Any]) -> dict[str, str]:
    website = str(scan.get("normalized_domain") or scan.get("website_url") or scan.get("submitted_url") or "")
    return {
        "owner_user_id": str(scan.get("owner_user_id") or scan.get("created_by_id") or ""),
        "scan_id": str(scan.get("id") or ""),
        "project_id": str(scan.get("project_id") or ""),
        "request_id": str(scan.get("request_id") or ""),
        "idempotency_key": str(scan.get("idempotency_key") or scan.get("request_id") or ""),
        "normalized_domain": _normalize_domain(website),
        # Signed into every control/completion envelope so Base44 can refuse a
        # superseded attempt even if the worker were compromised or replayed.
        "attempt_count": str(current_attempt(scan)),
    }


def _normalize_domain(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    return str(parsed.hostname or "").lower().removeprefix("www.").rstrip(".")


async def read_scan_run(client: httpx.AsyncClient, scan_id: str) -> dict[str, Any] | None:
    """Read the exact ScanRun through a signed Base44-hosted control function."""
    signing_key = str(os.getenv("SCAN_EVIDENCE_SIGNING_KEY") or "")
    clean_scan_id = str(scan_id or "").strip()
    if not signing_key or not clean_scan_id:
        return None
    envelope = build_control_envelope("read", signing_key, scan_id=clean_scan_id)
    response = await invoke_function(client, "durableScanWorkerControl", envelope, timeout=20.0)
    if response["status_code"] != 200 or response["body"].get("success") is not True:
        return None
    scan = response["body"].get("scanRun")
    return scan if isinstance(scan, dict) else None


async def mark_scan_started(client: httpx.AsyncClient, scan: dict[str, Any]) -> dict[str, Any]:
    """Mark worker liveness without resetting the attempt's original start time."""
    signing_key = str(os.getenv("SCAN_EVIDENCE_SIGNING_KEY") or "")
    identity = _scan_identity(scan)
    if not signing_key or not all(identity.values()):
        raise RuntimeError("Durable scan start signing is not configured.")
    envelope = build_control_envelope("start", signing_key, identity=identity)
    response = await invoke_function(client, "durableScanWorkerControl", envelope, timeout=20.0)
    if response["status_code"] >= 300 or response["body"].get("success") is not True:
        raise RuntimeError("The durable scan start state could not be verified.")
    persisted = response["body"].get("scanRun")
    if not isinstance(persisted, dict):
        raise RuntimeError("The durable scan start response is missing its ScanRun.")
    return persisted


@asynccontextmanager
async def worker_liveness_heartbeat(
    client: httpx.AsyncClient,
    scan: dict[str, Any],
    *,
    interval: float = WORKER_HEARTBEAT_INTERVAL_SECONDS,
):
    """Keep worker liveness fresh for a whole job, not just at its phase edges.

    A beat proves the worker is still alive. It never extends a phase deadline:
    every external operation keeps its own bounded timeout, so this can carry an
    honest slow run past 15 minutes but can never hide an infinite wait. A beat
    that fails is logged and ignored -- liveness is best effort, and the
    reconciler remains the backstop.

    The beat only runs while the event loop is free. Post-crawl work must
    therefore stay off the loop (see the worker's bounded ``to_thread`` phases),
    or a blocked loop would silence the heartbeat exactly as it did before.
    """
    stop = asyncio.Event()
    scan_id = str(scan.get("id") or scan.get("scan_id") or "")
    # Floor mirrors await_hard_deadline: a guard against a pathological
    # configured value, not a lower bound on how often a beat may occur.
    beat_interval = max(0.001, float(interval))

    async def _beat() -> None:
        while True:
            try:
                await asyncio.wait_for(stop.wait(), timeout=beat_interval)
                return
            except asyncio.TimeoutError:
                pass
            try:
                await mark_scan_started(client, scan)
                emit("scan_job_heartbeat", scan_id=scan_id)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - liveness must never fail a scan
                emit("scan_job_heartbeat_failed", severity="WARNING", scan_id=scan_id)

    task = asyncio.create_task(_beat())
    try:
        yield
    finally:
        stop.set()
        task.cancel()
        with contextlib.suppress(BaseException):
            await task


async def reconcile_stale_scans(client: httpx.AsyncClient) -> dict[str, Any]:
    """Run one signed, parameter-free stale-scan reconciliation sweep."""
    signing_key = str(os.getenv("SCAN_EVIDENCE_SIGNING_KEY") or "")
    if not signing_key:
        raise RuntimeError("Durable reconciliation signing is not configured.")
    envelope = build_control_envelope("sweep", signing_key)
    response = await invoke_function(client, "durableScanWorkerControl", envelope, timeout=60.0)
    if response["status_code"] >= 300 or response["body"].get("success") is not True:
        raise RuntimeError("Durable scan reconciliation could not be verified.")
    counts = response["body"].get("reconciliation")
    if not isinstance(counts, dict):
        raise RuntimeError("Durable scan reconciliation response is malformed.")
    return {
        key: max(0, int(counts.get(key) or 0))
        for key in (
            "examined",
            "closed",
            "released",
            "superseded",
            "satisfied_unbound",
            "pending",
            "retryable",
            "paginated",
            "skipped",
            "errors",
        )
    }


async def write_terminal_failure(
    client: httpx.AsyncClient,
    scan_id: str,
    failure_code: str,
    detail: str,
    *,
    attempt_count: Any = None,
) -> bool:
    """Close the exact ScanRun or raise so Cloud Tasks retries safely."""
    signing_key = str(os.getenv("SCAN_EVIDENCE_SIGNING_KEY") or "")
    if not signing_key:
        raise RuntimeError("Durable failure signing is not configured.")
    scan = await read_scan_run(client, scan_id)
    if not isinstance(scan, dict):
        raise RuntimeError("The durable ScanRun could not be re-read for failure persistence.")
    identity = _scan_identity(scan)
    if not all(identity.values()):
        raise RuntimeError("The durable ScanRun identity is incomplete.")
    # Re-read immediately before writing: if the row advanced to a newer
    # attempt while this task ran, the failure belongs to nobody and must not
    # be written over the live attempt.
    if attempt_count is not None and is_superseded_attempt(scan, attempt_count):
        return False
    envelope = build_control_envelope(
        "fail",
        signing_key,
        identity=identity,
        failure={"code": str(failure_code or "scan_failed"), "detail": str(detail or "")},
    )
    response = await invoke_function(client, "durableScanWorkerControl", envelope, timeout=20.0)
    if response["status_code"] >= 300 or response["body"].get("success") is not True:
        raise RuntimeError("The durable failure state could not be verified.")
    return True


def identity_matches(scan: dict[str, Any], job: dict[str, Any]) -> bool:
    """The task must name the same owner-bound durable request."""
    for field in ("owner_user_id", "request_id", "idempotency_key", "project_id"):
        stored = str(scan.get(field) or "").strip()
        claimed = str(job.get(field) or "").strip()
        if stored and claimed and stored != claimed:
            return False
    stored_domain = _normalize_domain(
        str(scan.get("normalized_domain") or scan.get("website_url") or scan.get("submitted_url") or "")
    )
    claimed_domain = _normalize_domain(
        str(job.get("normalized_domain") or job.get("website_url") or "")
    )
    return not (stored_domain and claimed_domain and stored_domain != claimed_domain)


def already_terminal(scan: dict[str, Any]) -> bool:
    return str(scan.get("status") or "").lower() in TERMINAL_STATUSES


def has_authority_proof(record: dict[str, Any]) -> bool:
    proof = str(record.get("authority_proof") or "")
    return len(proof) == 64 and all(c in "0123456789abcdef" for c in proof)


def _first_list(result: dict[str, Any], keys: tuple[str, ...]) -> list:
    for key in keys:
        value = result.get(key)
        if isinstance(value, list):
            return value
    return []


def build_authority_review_payload(result: dict[str, Any]) -> dict[str, Any]:
    """Bounded review envelope retained for compatibility evidence.

    pages_found carries the full discovery inventory; only the review page
    sample is bounded. The 150-page crawl cap never truncates discovery.
    """
    pages = _first_list(result, ("crawled_pages", "pages", "scanned_pages", "crawl_pages"))[:REVIEW_PAGE_SAMPLE_LIMIT]
    findings = _first_list(result, ("grouped_findings", "recommendations", "findings", "raw_findings", "fixes"))[:REVIEW_FINDING_LIMIT]
    technical = result.get("technical_audit_summary") if isinstance(result.get("technical_audit_summary"), dict) else {}
    scan_summary = result.get("scan_summary") if isinstance(result.get("scan_summary"), dict) else {}
    n = lambda v: max(0, int(v)) if isinstance(v, (int, float)) else 0  # noqa: E731

    return {
        "success": True,
        "review_payload_version": SCAN_ATTESTATION_VERSION,
        "scanner_version": result.get("scanner_version"),
        "scanner_build_revision": result.get("scanner_build_revision") or technical.get("scanner_build_revision"),
        "scanner_wrapper_version": result.get("scanner_wrapper_version"),
        "beta_revision_fingerprint": result.get("beta_revision_fingerprint"),
        "advanced_scan_backend": result.get("advanced_scan_backend"),
        "deno_fallback_used": False,
        "scan_mode": "standard_150",
        "canonical_mode": "standard_150",
        "request_id": result.get("request_id"),
        "idempotency_key": result.get("idempotency_key"),
        "scan_id": result.get("scan_id"),
        "scan_run_id": result.get("scan_run_id"),
        "submitted_url": result.get("submitted_url"),
        "website_url": result.get("website_url"),
        "final_url": result.get("final_url"),
        "normalized_domain": result.get("normalized_domain"),
        "respect_robots_txt": True,
        "pages_crawled": n(result.get("pages_crawled")),
        "pages_found": n(result.get("pages_found")),
        "queued_remaining": n(result.get("queued_remaining")),
        "sampled_pages_sent_to_review": len(pages),
        "sampled_findings_sent_to_review": len(findings),
        "page_sample_truncated": n(result.get("pages_crawled")) > len(pages),
        "scanner_elapsed_ms": n(result.get("scanner_elapsed_ms")),
        "scanner_total_budget_seconds": float(result.get("scanner_total_budget_seconds") or 0),
        "scan_deadline_reached": result.get("scan_deadline_reached") is True,
        "requested_crawl_timeout_ms": n(result.get("requested_crawl_timeout_ms")),
        "metadata_evidence_version": result.get("metadata_evidence_version") or technical.get("metadata_evidence_version") or "",
        "title_evidence_version": result.get("title_evidence_version") or technical.get("title_evidence_version") or "",
        "sampling_evidence": result.get("sampling_evidence") or {},
        "crawl_timing": result.get("crawl_timing") or technical.get("crawl_timing") or {},
        "scan_summary": scan_summary,
        "technical_audit_summary": technical,
        "crawl_warnings": (result.get("crawl_warnings") or [])[:12] if isinstance(result.get("crawl_warnings"), list) else [],
        "crawled_pages": pages,
        "grouped_findings": findings,
    }


def build_scan_attestation(result: dict[str, Any], scan: dict[str, Any], signing_key: str) -> dict[str, Any]:
    """Legacy compatibility helper retained for release-pinned tests."""
    review_payload = build_authority_review_payload(result)
    identity = {
        "version": SCAN_ATTESTATION_VERSION,
        "owner_user_id": str(scan.get("owner_user_id") or ""),
        "scan_id": str(scan.get("id") or ""),
        "project_id": str(scan.get("project_id") or ""),
        "normalized_domain": str(result.get("normalized_domain") or "").lower().removeprefix("www."),
    }
    proof = create_authority_seal({**identity, "result": review_payload}, signing_key)
    return {
        "authority_review_payload": review_payload,
        "authority_scan_attestation": {**identity, "proof": proof},
    }


LIMITED_COMPLETION_VERSION = "durable_standard150_limited_v1"

# Coverage states that produce a truthful limited result rather than a failure.
LIMITED_COVERAGE_STATES = frozenset({"limited_coverage", "inventory_unproven", "access_limited"})


def coverage_state_of(review: dict[str, Any]) -> str:
    fingerprint = review.get("site_fingerprint") if isinstance(review, dict) else None
    fingerprint = fingerprint if isinstance(fingerprint, dict) else {}
    assessment = fingerprint.get("coverage_assessment")
    if isinstance(assessment, dict):
        return str(assessment.get("state") or "")
    return str(review.get("coverage_state") or "") if isinstance(review, dict) else ""


def limited_result_payload(review: dict[str, Any]) -> dict[str, Any]:
    """The review fields the limited-result contract binds into its proof."""
    fingerprint = review.get("site_fingerprint") if isinstance(review.get("site_fingerprint"), dict) else {}
    assessment = fingerprint.get("coverage_assessment") if isinstance(fingerprint.get("coverage_assessment"), dict) else {}
    return {
        "scan_status": review.get("scan_status"),
        "health_score": review.get("health_score"),
        "health_grade": review.get("health_grade"),
        "limitation": review.get("limitation"),
        "release_gate_eligible": review.get("release_gate_eligible"),
        "score_is_provisional": review.get("score_is_provisional"),
        "coverage_state": assessment.get("state") or coverage_state_of(review),
        "coverage_reasons": assessment.get("reasons") or [],
        "coverage_authority_version": assessment.get("coverage_authority_version") or "",
        "coverage_authority_evidence": review.get("coverage_authority_evidence") or {},
        "classification_integrity": review.get("classification_integrity") or {},
        "classification_verdict": review.get("classification_verdict") or "",
        "recommendations": review.get("recommendations") or review.get("fixes") or [],
    }


def build_limited_envelope(
    scan: dict[str, Any],
    result: dict[str, Any],
    review: dict[str, Any],
    signing_key: str,
) -> dict[str, Any]:
    identity = {
        "owner_user_id": str(scan.get("owner_user_id") or ""),
        "scan_id": str(scan.get("id") or ""),
        "project_id": str(scan.get("project_id") or ""),
        "request_id": str(scan.get("request_id") or result.get("request_id") or ""),
        "normalized_domain": str(result.get("normalized_domain") or "").lower().removeprefix("www."),
        "attempt_count": str(current_attempt(scan)),
    }
    signed = {
        "version": LIMITED_COMPLETION_VERSION,
        "identity": identity,
        "scan": result,
        "review": limited_result_payload(review),
    }
    return {**signed, "proof": create_authority_seal(signed, signing_key)}


def build_completion_envelope(
    scan: dict[str, Any],
    result: dict[str, Any],
    review: dict[str, Any],
    signing_key: str,
) -> dict[str, Any]:
    identity = {
        "owner_user_id": str(scan.get("owner_user_id") or ""),
        "scan_id": str(scan.get("id") or ""),
        "project_id": str(scan.get("project_id") or ""),
        "request_id": str(scan.get("request_id") or result.get("request_id") or ""),
        "idempotency_key": str(scan.get("idempotency_key") or result.get("idempotency_key") or ""),
        "normalized_domain": str(result.get("normalized_domain") or "").lower().removeprefix("www."),
        "attempt_count": str(current_attempt(scan)),
    }
    signed = {
        "version": COMPLETION_VERSION,
        "identity": identity,
        "scan": result,
        "review": review,
    }
    return {**signed, "proof": create_authority_seal(signed, signing_key)}


def fix_list_belongs_to_scan(fix_list: dict[str, Any], scan: dict[str, Any]) -> bool:
    """A FixList may only be accepted for the exact owner, project and ScanRun."""
    return (
        str(fix_list.get("scan_run_id") or "") == str(scan.get("id") or "")
        and str(fix_list.get("project_id") or "") == str(scan.get("project_id") or "")
        and str(fix_list.get("owner_user_id") or "") == str(scan.get("owner_user_id") or "")
    )


def build_local_review(result: dict[str, Any]) -> dict[str, Any]:
    """Run the exact Python review pipeline inside the durable worker."""
    from .beta_revision import live_revision
    from .coverage_authority import attach_coverage_authority_evidence
    from .evidence_quality import apply_evidence_quality_gate
    from .repair_contract_v2 import apply_canonical_repair_contract
    from .review import run_review
    from .review_calibration import apply_review_evidence_calibration
    from .trust_discovery import apply_trust_discovery_gate

    review = run_review(result)
    review = apply_trust_discovery_gate(review, result)
    review = apply_review_evidence_calibration(review, result)
    review = apply_evidence_quality_gate(review, result)
    review = attach_coverage_authority_evidence(review, result)
    review.update({
        "success": True,
        "ai_review_backend": "python_review_api",
        "python_review_fallback_used": False,
        "beta_revision_fingerprint": live_revision()["fingerprint"],
    })
    return apply_canonical_repair_contract(review, result)


class LocalReviewProcessTimeout(RuntimeError):
    """The isolated local-review child exceeded its hard wall-clock budget."""


def _local_review_process_entry(result: dict[str, Any], send_conn: Any) -> None:
    """Run local review in a child process and return only a bounded result envelope."""
    try:
        reviewed = build_local_review(result)
        send_conn.send(("ok", reviewed))
    except BaseException as exc:  # noqa: BLE001 - child must never strand its parent
        try:
            send_conn.send(("error", type(exc).__name__))
        except Exception:
            pass
    finally:
        try:
            send_conn.close()
        except Exception:
            pass


def run_local_review_isolated(
    result: dict[str, Any],
    timeout_seconds: float = LOCAL_REVIEW_WALL_TIMEOUT_SECONDS,
    *,
    entrypoint: Any = None,
) -> dict[str, Any]:
    """Run review in a killable child so GIL starvation cannot defeat the deadline."""
    timeout = max(0.001, float(timeout_seconds or LOCAL_REVIEW_WALL_TIMEOUT_SECONDS))
    ctx = mp.get_context("spawn")
    recv_conn, send_conn = ctx.Pipe(duplex=False)
    process = ctx.Process(target=entrypoint or _local_review_process_entry, args=(result, send_conn), daemon=True)
    process.start()
    send_conn.close()
    deadline = time.monotonic() + timeout
    payload: Any = None
    review_peak_memory_bytes: int | None = None

    def sample_review_memory() -> None:
        nonlocal review_peak_memory_bytes
        sampled = measure_worker_peak_memory_bytes(child_pid=process.pid)
        if sampled is not None:
            review_peak_memory_bytes = max(review_peak_memory_bytes or 0, sampled)

    try:
        sample_review_memory()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise LocalReviewProcessTimeout("local review exceeded its process wall time")
            if recv_conn.poll(min(0.05, remaining)):
                sample_review_memory()
                try:
                    payload = recv_conn.recv()
                except EOFError as exc:
                    raise RuntimeError("local review process closed without a result") from exc
                break
            sample_review_memory()
            if not process.is_alive():
                if recv_conn.poll():
                    payload = recv_conn.recv()
                    break
                raise RuntimeError("local review process exited without a result")

        if not isinstance(payload, tuple) or len(payload) != 2:
            raise RuntimeError("local review process returned an invalid envelope")
        state, value = payload
        if state != "ok" or not isinstance(value, dict):
            raise RuntimeError(f"local review process failed: {str(value or 'unknown_error')[:80]}")
        reviewed = dict(value)
        if review_peak_memory_bytes is not None:
            reviewed["_worker_peak_memory_bytes"] = review_peak_memory_bytes
        return reviewed
    finally:
        try:
            recv_conn.close()
        except Exception:
            pass
        if process.is_alive():
            process.terminate()
        process.join(timeout=LOCAL_REVIEW_PROCESS_JOIN_GRACE_SECONDS)
        if process.is_alive():
            process.kill()
            process.join(timeout=LOCAL_REVIEW_PROCESS_JOIN_GRACE_SECONDS)


def terminal_crawl_limitation(result: dict[str, Any]) -> dict[str, str] | None:
    """Short-circuit a definitively blocked crawl before full local review.

    This is intentionally narrow: at least one page must carry the existing
    blocked-access classifier and there must be zero usable HTML pages. Other
    crawl failures continue through the normal review contract.
    """
    if not isinstance(result, dict):
        return None
    pages = result.get("crawled_pages") if isinstance(result.get("crawled_pages"), list) else result.get("pages")
    if not isinstance(pages, list) or not pages:
        return None

    from .page_evidence_gate import page_has_usable_html
    from .review import is_blocked_access_page

    blocked = sum(1 for page in pages if isinstance(page, dict) and is_blocked_access_page(page))
    usable = sum(1 for page in pages if isinstance(page, dict) and page_has_usable_html(page))
    if blocked > 0 and usable == 0:
        return {
            "code": "scan_access_limited",
            "detail": (
                "The site rate-limited or challenged the scanner, so FixList could not collect enough verified HTML "
                "to save an authoritative result. Please try again later."
            ),
        }
    return None


def terminal_review_limitation(review: dict[str, Any]) -> dict[str, str] | None:
    """Translate known fail-closed review states into truthful terminal errors.

    A provisional review must never be persisted as authoritative. For access
    failures we can still tell the customer what actually happened instead of
    surfacing an opaque authority-persistence error that sounds like data loss.
    """
    if not isinstance(review, dict) or review.get("release_gate_eligible") is True:
        return None
    fingerprint = review.get("site_fingerprint") if isinstance(review.get("site_fingerprint"), dict) else {}
    blocked = int(fingerprint.get("blocked_or_429_pages") or fingerprint.get("blocked_access_pages") or 0)
    usable = int((fingerprint.get("classification") or {}).get("usable_pages") or 0) if isinstance(fingerprint.get("classification"), dict) else 0
    access_state = str(review.get("access_evidence_state") or "")
    confidence = str(review.get("review_confidence_state") or "")
    if access_state == "blocked" or confidence == "blocked_access_needs_verification" or (blocked > 0 and usable == 0):
        return {
            "code": "scan_access_limited",
            "detail": (
                "The site rate-limited or challenged the scanner, so FixList could not collect enough verified HTML "
                "to save an authoritative result. Please try again later."
            ),
        }
    return None


async def persist_limited_result(
    client: httpx.AsyncClient,
    scan: dict[str, Any],
    result: dict[str, Any],
    review: dict[str, Any],
    signing_key: str,
    *,
    phase_started: float,
) -> dict[str, Any]:
    """Save a provisional result under its own integrity proof, never authority."""
    scan_id = str(scan.get("id") or "")
    attempt_count = current_attempt(scan)
    envelope = build_limited_envelope(scan, result, review, signing_key)
    emit(
        "scan_job_completion_phase",
        scan_id=scan_id,
        attempt_count=attempt_count,
        phase="limited_persist_start",
        elapsed_ms=int((time.monotonic() - phase_started) * 1000),
        coverage_state=coverage_state_of(review),
    )
    persisted = await invoke_function(client, "persistLimitedScanResult", envelope)
    status_code = int(persisted.get("status_code") or 0)
    emit(
        "scan_job_completion_phase",
        scan_id=scan_id,
        attempt_count=attempt_count,
        phase="limited_persist_done",
        elapsed_ms=int((time.monotonic() - phase_started) * 1000),
        status_code=status_code,
    )
    if status_code >= 500:
        return {"ok": False, "transient": True, "failure_code": "persistence_unavailable"}
    body = persisted.get("body") if isinstance(persisted.get("body"), dict) else {}
    if status_code >= 400 or body.get("success") is False:
        return {
            "ok": False,
            "transient": False,
            "failure_code": str(body.get("error_code") or "limited_result_failed"),
        }
    scan_run = body.get("scanRun") if isinstance(body.get("scanRun"), dict) else {}
    fix_list_id = str(body.get("fixListId") or scan_run.get("fix_list_id") or "")
    if not fix_list_id or body.get("resultIntegrityVerified") is not True:
        return {"ok": False, "transient": False, "failure_code": "limited_result_failed"}
    return {
        "ok": True,
        "transient": False,
        "failure_code": "",
        "limited": True,
        "fix_list_id": fix_list_id,
        "result_integrity_proof": str(scan_run.get("result_integrity_proof") or ""),
    }


async def complete_authority(
    client: httpx.AsyncClient,
    scan: dict[str, Any],
    result: dict[str, Any],
    signing_key: str,
    review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Review locally and persist one signed completion through Base44.

    `scan` was read before a crawl that may have run for minutes. Re-read the
    row and refuse if a newer attempt has taken over, so a superseded task can
    never finalise, overwrite a seal, or trigger an allowance charge.
    """
    scan_id = str(scan.get("id") or scan.get("scan_id") or "")
    attempt_count = current_attempt(scan)
    phase_started = time.monotonic()
    emit(
        "scan_job_completion_phase",
        scan_id=scan_id,
        attempt_count=attempt_count,
        phase="enter",
    )
    fresh = await read_scan_run(client, scan_id)
    emit(
        "scan_job_completion_phase",
        scan_id=scan_id,
        attempt_count=attempt_count,
        phase="fresh_read_done",
        elapsed_ms=int((time.monotonic() - phase_started) * 1000),
        readable=isinstance(fresh, dict),
    )
    if not isinstance(fresh, dict):
        return {"ok": False, "transient": True, "failure_code": "scan_unreadable"}
    if is_superseded_attempt(fresh, current_attempt(scan)):
        return {"ok": False, "transient": False, "failure_code": "superseded_attempt", "superseded": True}
    if already_terminal(fresh) and has_authority_proof(fresh):
        # Terminal authority is immutable. A retry that finds a sealed row
        # reports the existing result rather than persisting a second one.
        return {
            "ok": True,
            "transient": False,
            "failure_code": "",
            "already_sealed": True,
            "fix_list_id": str(fresh.get("fix_list_id") or ""),
            "authority_proof": str(fresh.get("authority_proof") or ""),
        }
    scan = fresh

    crawl_limitation = terminal_crawl_limitation(result)
    emit(
        "scan_job_completion_phase",
        scan_id=scan_id,
        attempt_count=attempt_count,
        phase="crawl_limitation_done",
        elapsed_ms=int((time.monotonic() - phase_started) * 1000),
        limited=crawl_limitation is not None,
    )
    if crawl_limitation is not None:
        return {
            "ok": False,
            "transient": False,
            "failure_code": crawl_limitation["code"],
            "customer_message": crawl_limitation["detail"],
        }

    try:
        emit(
            "scan_job_completion_phase",
            scan_id=scan_id,
            attempt_count=attempt_count,
            phase="review_start",
            elapsed_ms=int((time.monotonic() - phase_started) * 1000),
            supplied_review=isinstance(review, dict),
        )
        supplied_review = isinstance(review, dict)
        if supplied_review:
            reviewed = review
        else:
            reviewed = await asyncio.wait_for(
                asyncio.to_thread(
                    run_local_review_isolated,
                    result,
                    LOCAL_REVIEW_WALL_TIMEOUT_SECONDS,
                ),
                timeout=LOCAL_REVIEW_WALL_TIMEOUT_SECONDS + 5.0,
            )
    except (asyncio.TimeoutError, LocalReviewProcessTimeout):
        return {
            "ok": False,
            "transient": False,
            "failure_code": "review_wall_timeout",
            "customer_message": "The scan finished crawling, but its review exceeded the bounded worker time. Please try again.",
        }
    except Exception:
        return {"ok": False, "transient": False, "failure_code": "review_failed"}

    emit(
        "scan_job_completion_phase",
        scan_id=scan_id,
        attempt_count=attempt_count,
        phase="review_done",
        elapsed_ms=int((time.monotonic() - phase_started) * 1000),
        release_gate_eligible=reviewed.get("release_gate_eligible") is True,
    )
    worker_peak_memory = (
        measure_worker_peak_memory_bytes()
        if supplied_review
        else reviewed.pop("_worker_peak_memory_bytes", None)
    )
    classification_integrity = build_classification_integrity(reviewed)
    if classification_integrity:
        reviewed["classification_integrity"] = classification_integrity
        reviewed["classification_verdict"] = classification_integrity["state"]
    if isinstance(worker_peak_memory, int) and worker_peak_memory > 0:
        result["peak_memory_bytes"] = worker_peak_memory
        result["worker_peak_memory_bytes"] = worker_peak_memory
    limitation = terminal_review_limitation(reviewed)
    if limitation is not None:
        return {
            "ok": False,
            "transient": False,
            "failure_code": limitation["code"],
            "customer_message": limitation["detail"],
        }

    # A scan the coverage assessment limited is not authoritative, but it is not
    # nothing either. Failing it here would throw away evidence the customer can
    # act on, which is a worse answer than the overclaim it replaced -- so it
    # takes the separate integrity-verified path. Only a scan with no useful
    # evidence at all still ends as a failure, which persistLimitedScanResult
    # enforces server-side rather than trusting this decision.
    if reviewed.get("release_gate_eligible") is not True:
        coverage_state = coverage_state_of(reviewed)
        if coverage_state in LIMITED_COVERAGE_STATES and (reviewed.get("recommendations") or reviewed.get("fixes")):
            return await persist_limited_result(
                client, scan, result, reviewed, signing_key, phase_started=phase_started,
            )
        # The local review already decided this result is not release-eligible.
        # Useful limited evidence took the integrity-only path above. Every
        # remaining noneligible review must fail closed before durable authority.
        emit(
            "scan_job_completion_phase",
            scan_id=scan_id,
            attempt_count=attempt_count,
            phase="not_release_eligible",
            elapsed_ms=int((time.monotonic() - phase_started) * 1000),
            coverage_state=coverage_state,
        )
        return {
            "ok": False,
            "transient": False,
            "failure_code": "review_not_release_eligible",
            "customer_message": (
                "The scan finished, but there was not enough verified evidence "
                "to save a trustworthy FixList. Please try again."
            ),
        }

    envelope = build_completion_envelope(scan, result, reviewed, signing_key)
    emit(
        "scan_job_completion_phase",
        scan_id=scan_id,
        attempt_count=attempt_count,
        phase="envelope_done",
        elapsed_ms=int((time.monotonic() - phase_started) * 1000),
    )
    emit(
        "scan_job_completion_phase",
        scan_id=scan_id,
        attempt_count=attempt_count,
        phase="persist_start",
        elapsed_ms=int((time.monotonic() - phase_started) * 1000),
    )
    persisted = await invoke_function(client, "persistDurableScanAuthority", envelope)
    emit(
        "scan_job_completion_phase",
        scan_id=scan_id,
        attempt_count=attempt_count,
        phase="persist_done",
        elapsed_ms=int((time.monotonic() - phase_started) * 1000),
        status_code=int(persisted.get("status_code") or 0),
    )
    if persisted["status_code"] >= 500:
        return {"ok": False, "transient": True, "failure_code": "persistence_unavailable"}
    scan_run = persisted["body"].get("scanRun") if isinstance(persisted["body"].get("scanRun"), dict) else {}
    fix_list_id = str(persisted["body"].get("fixListId") or scan_run.get("fix_list_id") or "")
    if persisted["status_code"] >= 400 or persisted["body"].get("success") is False:
        return {
            "ok": False,
            "transient": False,
            "failure_code": str(persisted["body"].get("error_code") or "authority_persistence_failed"),
        }
    if (
        not has_authority_proof(scan_run)
        or not fix_list_id
        or persisted["body"].get("fixListVerified") is not True
    ):
        return {"ok": False, "transient": False, "failure_code": "authority_persistence_failed"}

    return {
        "ok": True,
        "transient": False,
        "failure_code": "",
        "fix_list_id": fix_list_id,
        "authority_proof": str(scan_run.get("authority_proof") or ""),
    }
