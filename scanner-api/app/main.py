import asyncio
import os
import secrets
from typing import Any

import httpx
from fastapi import Body, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .beta_revision import SCANNER_BUILD_REVISION, live_revision
from .evidence_quality import EVIDENCE_QUALITY_GATE_VERSION, apply_evidence_quality_gate
from .grok_chat import (
    GROK_CHAT_VERSION,
    GROK_MODEL_ID,
    GrokUpstreamError,
    run_grok_chat,
)
from .indexability_postprocess import apply_indexability_quality_to_result
from .indexability_quality import INDEXABILITY_QUALITY_VERSION
from .navigation_indexability import NAVIGATION_INDEXABILITY_VERSION
from .observability import (
    OBSERVABILITY_VERSION,
    RequestTimer,
    review_metrics,
    scan_metrics,
    website_host,
)
from .render_evidence_quality import (
    RENDER_EVIDENCE_QUALITY_VERSION,
    apply_render_evidence_quality,
)
from .review import ARCHETYPE_CLASSIFIER_VERSION, REVIEW_VERSION, run_review
from .review_calibration import CALIBRATION_VERSION, apply_review_evidence_calibration
from .scan_timing import SITEMAP_TIME_RESERVATION_VERSION
from .scan_job import (
    CRAWL_BUDGET_SECONDS,
    current_attempt,
    is_superseded_attempt,
    normalize_attempt,
    WORKER_VERSION,
    already_terminal,
    complete_authority,
    identity_matches,
    read_scan_run,
    write_terminal_failure,
)
from .scanner import VERSION, run_scan
from .trust_discovery import apply_trust_discovery_gate, enrich_scan_with_trust_pages
from .url_evidence import URL_EVIDENCE_VERSION, apply_verified_url_contract

SCANNER_API_KEY = os.getenv("SCANNER_API_KEY", "")
GROK_PROXY_ENABLED = os.getenv("GROK_PROXY_ENABLED", "").strip().lower() == "true"
TRUST_DISCOVERY_TIMEOUTS = {"basic": 2.0, "quick": 3.0, "deep": 5.0, "advanced": 7.0}
SCAN_RESPONSE_PAGE_LIMITS = {"basic": 25, "quick": 40, "deep": 85, "advanced": 150}
GROK_ERROR_DETAIL_VERSION = "grok_upstream_detail_v1"

app = FastAPI(title="FixList Scanner API", version=VERSION)


def require_scanner_api_key(x_scanner_key: str | None) -> None:
    """Fail closed unless a configured scanner key matches the request key."""
    expected_key = str(SCANNER_API_KEY or "")
    supplied_key = str(x_scanner_key or "")
    if (
        not expected_key
        or not supplied_key
        or not secrets.compare_digest(supplied_key, expected_key)
    ):
        raise HTTPException(status_code=401, detail="Unauthorized")


class ScanRequest(BaseModel):
    website_url: str
    path_prefix: str | None = None
    scan_mode: str = "advanced"
    business_name: str | None = None
    cms_platform: str | None = None
    request_id: str | None = None
    idempotency_key: str | None = None
    scan_id: str | None = None
    scan_run_id: str | None = None
    submitted_url: str | None = None
    normalized_domain: str | None = None
    respect_robots_txt: bool = True
    # Trusted-gateway runtime cap. Synchronous requests stay clamped to the
    # safe 20s..75s range; only an asynchronous durable job may use the
    # 120-second ceiling. The 150-page cap is never affected.
    advisory_crawl_timeout_ms: int | None = Field(default=None, ge=20_000, le=120_000)
    # Set by the Base44 async job gateway. Unlocks only the longer crawl
    # ceiling in scanner.py (job_mode); every other budget rule is unchanged.
    async_job: bool = False


class ChatRequest(BaseModel):
    message: str
    scan: dict[str, Any] = Field(default_factory=dict)
    history: list[dict[str, Any]] = Field(default_factory=list)


def enforce_scan_response_page_budget(result: dict[str, Any], scan_mode: str) -> dict[str, Any]:
    """Enforce mode page limits at the final HTTP response boundary.

    The crawler already owns a cap, but this second boundary protects callers from
    concurrent/post-processing overruns and keeps every count consistent with the
    actual evidence arrays returned to Base44.
    """
    if not isinstance(result, dict):
        return result
    mode = str(scan_mode or result.get("scan_mode") or "advanced").lower()
    limit = SCAN_RESPONSE_PAGE_LIMITS.get(mode, SCAN_RESPONSE_PAGE_LIMITS["advanced"])
    pages: list[dict[str, Any]] = []
    for key in ("crawled_pages", "pages", "scanned_pages", "crawl_pages"):
        value = result.get(key)
        if isinstance(value, list) and value:
            pages = value[:limit]
            break
    reported = result.get("pages_crawled")
    try:
        reported_count = max(0, int(reported or 0))
    except (TypeError, ValueError):
        reported_count = 0
    pages_crawled = min(limit, len(pages) if pages else reported_count)
    if pages:
        result["pages"] = pages
        result["crawled_pages"] = pages
        if isinstance(result.get("scanned_pages"), list):
            result["scanned_pages"] = pages
        if isinstance(result.get("crawl_pages"), list):
            result["crawl_pages"] = pages
    result["pages_crawled"] = pages_crawled
    result["scanner_build_revision"] = SCANNER_BUILD_REVISION
    technical = result.get("technical_audit_summary")
    if not isinstance(technical, dict):
        technical = {}
        result["technical_audit_summary"] = technical
    technical["pages_crawled"] = pages_crawled
    technical["scanner_build_revision"] = SCANNER_BUILD_REVISION
    summary = result.get("scan_summary")
    if isinstance(summary, dict):
        if "pages_scanned" in summary:
            summary["pages_scanned"] = min(limit, int(summary.get("pages_scanned") or pages_crawled))
        if "pages_crawled" in summary:
            summary["pages_crawled"] = min(limit, int(summary.get("pages_crawled") or pages_crawled))
    return apply_verified_url_contract(result)


def health_payload() -> dict[str, Any]:
    return {
        "ok": True,
        "key_required": True,
        "version": VERSION,
        "scanner_build_revision": SCANNER_BUILD_REVISION,
        "grok_chat_version": GROK_CHAT_VERSION,
        "grok_error_detail_version": GROK_ERROR_DETAIL_VERSION,
        "grok_model_id": GROK_MODEL_ID,
        "grok_proxy_enabled": GROK_PROXY_ENABLED,
        "url_evidence_version": URL_EVIDENCE_VERSION,
        "review_version": REVIEW_VERSION,
        "archetype_classifier_version": ARCHETYPE_CLASSIFIER_VERSION,
        "review_evidence_calibration_version": CALIBRATION_VERSION,
        "indexability_quality_version": INDEXABILITY_QUALITY_VERSION,
        "navigation_indexability_version": NAVIGATION_INDEXABILITY_VERSION,
        "render_evidence_quality_version": RENDER_EVIDENCE_QUALITY_VERSION,
        "evidence_quality_gate_version": EVIDENCE_QUALITY_GATE_VERSION,
        "sitemap_time_reservation_version": SITEMAP_TIME_RESERVATION_VERSION,
        "beta_revision_fingerprint": live_revision()["fingerprint"],
        "observability_version": OBSERVABILITY_VERSION,
    }


@app.get("/health")
def health():
    return health_payload()


@app.get("/health/auth")
def authenticated_health(x_scanner_key: str | None = Header(default=None)):
    """Verify both scanner reachability and the caller's shared scanner key."""
    require_scanner_api_key(x_scanner_key)
    return {
        **health_payload(),
        "authenticated": True,
    }


@app.get("/revision")
def revision():
    """Live beta-revision fingerprint for verifying a deployed scanner against
    the recorded freeze in data/beta-crawler-revision.json."""
    return live_revision()


@app.post("/chat")
async def chat(payload: ChatRequest, x_scanner_key: str | None = Header(default=None)):
    require_scanner_api_key(x_scanner_key)
    if not GROK_PROXY_ENABLED:
        raise HTTPException(status_code=503, detail="Grok is unavailable.")

    message = str(payload.message or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Enter a question about the current scan.")
    if len(message) > 4000:
        raise HTTPException(status_code=400, detail="Question is too long.")

    try:
        answer = await run_grok_chat(
            message,
            payload.scan if isinstance(payload.scan, dict) else {},
            payload.history if isinstance(payload.history, list) else [],
        )
    except GrokUpstreamError as exc:
        raise HTTPException(status_code=502, detail=exc.public_detail) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Grok is temporarily unavailable ({type(exc).__name__}).",
        ) from exc
    return {
        "success": True,
        "answer": answer,
        "model": GROK_MODEL_ID,
        "grok_chat_version": GROK_CHAT_VERSION,
    }


@app.post("/scan")
async def scan(payload: ScanRequest, x_scanner_key: str | None = Header(default=None)):
    require_scanner_api_key(x_scanner_key)

    request_id = str(payload.request_id or payload.idempotency_key or "").strip()
    idempotency_key = str(payload.idempotency_key or request_id).strip()
    scan_id = str(payload.scan_id or payload.scan_run_id or "").strip()
    identity = {
        "request_id": request_id,
        "idempotency_key": idempotency_key,
        "scan_id": scan_id,
        "scan_run_id": scan_id,
        "submitted_url": str(payload.submitted_url or payload.website_url),
        "normalized_domain": website_host(payload.website_url),
        "respect_robots_txt": True,
    }
    if request_id and idempotency_key and request_id != idempotency_key:
        raise HTTPException(status_code=409, detail="request_id and idempotency_key must match.")
    if payload.respect_robots_txt is not True:
        raise HTTPException(status_code=400, detail="Standard scans must respect robots.txt.")

    timer = RequestTimer(
        "scan",
        website_host=website_host(payload.website_url),
        scan_mode=payload.scan_mode,
        scanner_version=VERSION,
        beta_revision_fingerprint=live_revision()["fingerprint"],
        request_id=request_id,
        idempotency_key=idempotency_key,
        scan_id=scan_id,
        scan_run_id=scan_id,
    )
    try:
        request_timeout_seconds = (
            float(payload.advisory_crawl_timeout_ms) / 1000.0
            if payload.advisory_crawl_timeout_ms is not None
            else None
        )
        result = await run_scan(
            website_url=payload.website_url,
            path_prefix=payload.path_prefix,
            scan_mode=payload.scan_mode,
            business_name=payload.business_name or "",
            cms_platform=payload.cms_platform or "",
            timeout_seconds=request_timeout_seconds,
            job_mode=bool(payload.async_job),
        )
        trust_timeout = TRUST_DISCOVERY_TIMEOUTS.get(str(payload.scan_mode or "advanced").lower(), 7.0)
        if request_timeout_seconds is not None:
            # Keep post-crawl trust enrichment inside the gateway-safe envelope.
            trust_timeout = min(trust_timeout, 3.0)
        try:
            result = await asyncio.wait_for(enrich_scan_with_trust_pages(result), timeout=trust_timeout)
        except asyncio.TimeoutError:
            warnings = list(result.get("crawl_warnings") or [])
            warnings.append("Bounded trust-page discovery timed out; existing crawl evidence was preserved.")
            result["crawl_warnings"] = warnings
            result["trust_page_discovery"] = {"version": "trust_page_discovery_v1", "attempted": True, "conclusive": False, "timed_out": True, "checked": 0, "responses_received": 0, "found": [], "found_urls": [], "evidence": []}
        result = apply_indexability_quality_to_result(result)
        result = apply_render_evidence_quality(result)
        result = enforce_scan_response_page_budget(result, payload.scan_mode)
        result["beta_revision_fingerprint"] = live_revision()["fingerprint"]
        if payload.advisory_crawl_timeout_ms is not None:
            result["requested_crawl_timeout_ms"] = int(payload.advisory_crawl_timeout_ms)
        pages = result.get("crawled_pages") or result.get("pages") or []
        first_page = pages[0] if isinstance(pages, list) and pages else {}
        final_url = str(
            result.get("final_url")
            or result.get("resolved_start_url")
            or (first_page.get("final_url") if isinstance(first_page, dict) else "")
            or result.get("normalized_url")
            or result.get("website_url")
            or payload.website_url
        )
        result.update({
            **identity,
            "final_url": final_url,
            "normalized_domain": website_host(final_url) or identity["normalized_domain"],
            "release_id": ":".join(filter(None, [
                str(result.get("scanner_version") or VERSION),
                SCANNER_BUILD_REVISION,
                str(result.get("beta_revision_fingerprint") or ""),
            ])),
        })
    except Exception as exc:  # noqa: BLE001 - customer-safe envelope, full detail logged
        return {**timer.failed(exc), **identity}
    timer.completed(**scan_metrics(result))
    return result


@app.post("/review")
async def review(payload: dict[str, Any] = Body(default_factory=dict), x_scanner_key: str | None = Header(default=None)):
    require_scanner_api_key(x_scanner_key)

    timer = RequestTimer(
        "review",
        website_host=website_host(payload.get("website_url")),
        review_version=REVIEW_VERSION,
        beta_revision_fingerprint=live_revision()["fingerprint"],
    )
    try:
        result = run_review(payload)
        result = apply_trust_discovery_gate(result, payload)
        result = apply_review_evidence_calibration(result, payload)
        result = apply_evidence_quality_gate(result, payload)
        result["beta_revision_fingerprint"] = live_revision()["fingerprint"]
    except Exception as exc:  # noqa: BLE001 - customer-safe envelope, full detail logged
        return timer.failed(exc)
    timer.completed(**review_metrics(result))
    return result

class ScanJobRequest(BaseModel):
    """Payload Cloud Tasks delivers for one durable Standard 150 job."""

    scan_id: str
    request_id: str
    # The attempt this task was minted for. Bound end to end so a task from an
    # earlier attempt cannot crawl, fail, finalise or charge a newer one.
    attempt_count: int = 1
    idempotency_key: str | None = None
    project_id: str | None = None
    owner_user_id: str | None = None
    website_url: str
    path_prefix: str | None = None
    normalized_domain: str | None = None
    business_name: str | None = None
    cms_platform: str | None = None
    scan_mode: str = "standard_150"
    respect_robots_txt: bool = True


def require_cloud_tasks_oidc(authorization: str | None) -> None:
    """Check the invoker identity on an already-IAM-validated Cloud Tasks token.

    This function does NOT verify the token signature and does NOT check the
    `aud` claim. It base64-decodes the JWT payload and compares the `email`
    claim against TASKS_INVOKER_SERVICE_ACCOUNT. Read it as a second, weaker
    gate -- not as OIDC verification.

    Token validation (signature, issuer, audience, expiry) is performed by
    Cloud Run IAM before the request reaches this process, which is only true
    while the service is deployed --no-allow-unauthenticated. That deployment
    flag is therefore load-bearing for security here: on a public service this
    check is trivially forgeable, because an unsigned payload with the expected
    email claim would pass.

    The application-level value it does add is restricting which *authenticated*
    principal may drive jobs, so another caller with run.invoker in the project
    cannot enqueue work through this route.
    """
    token = str(authorization or "")
    if not token.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    expected_sa = str(os.getenv("TASKS_INVOKER_SERVICE_ACCOUNT") or "")
    if not expected_sa:
        raise HTTPException(status_code=503, detail="Worker authentication is not configured.")
    import base64
    import json as _json

    parts = token.split(" ", 1)[1].split(".")
    if len(parts) != 3:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        padded = parts[1] + "=" * (-len(parts[1]) % 4)
        claims = _json.loads(base64.urlsafe_b64decode(padded))
    except Exception:  # noqa: BLE001 - malformed token is simply unauthorized
        raise HTTPException(status_code=401, detail="Unauthorized") from None
    if str(claims.get("email") or "") != expected_sa:
        raise HTTPException(status_code=403, detail="Forbidden")


@app.post("/scan-job")
async def scan_job(
    payload: ScanJobRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Run one durable Standard 150 job to a terminal state.

    Returns 200 for any outcome Cloud Tasks must not retry (success, or a
    permanent failure already written to the ScanRun). Returns 5xx only for
    transient conditions where a retry against the same scan_id is safe.
    """
    require_cloud_tasks_oidc(authorization)

    scan_id = str(payload.scan_id or "").strip()
    if not scan_id or not str(payload.request_id or "").strip():
        raise HTTPException(status_code=400, detail="A durable scan_id and request_id are required.")
    if str(payload.scan_mode or "").lower() != "standard_150":
        raise HTTPException(status_code=400, detail="Only the Standard 150 scan is available.")
    if payload.respect_robots_txt is not True:
        raise HTTPException(status_code=400, detail="Standard scans must respect robots.txt.")

    job = payload.model_dump()
    job_attempt = normalize_attempt(payload.attempt_count)

    async with httpx.AsyncClient() as client:
        scan = await read_scan_run(client, scan_id)
        if scan is None:
            # Transient: the row must exist, so let Cloud Tasks retry it.
            raise HTTPException(status_code=503, detail="The scan record is unavailable.")
        if not identity_matches(scan, job):
            await write_terminal_failure(
                client, scan_id, "scan_identity_mismatch",
                "This scan could not be matched to your request. Please start a new scan.",
                attempt_count=job_attempt,
            )
            return {"success": False, "worker_version": WORKER_VERSION, "error_code": "scan_identity_mismatch"}
        # A superseded task must do nothing at all: no crawl, no failure write,
        # no persistence, no charge. It is not an error -- the newer attempt
        # owns the row -- so return 200 and let Cloud Tasks drop the task.
        if is_superseded_attempt(scan, job_attempt):
            return {
                "success": True,
                "worker_version": WORKER_VERSION,
                "skipped": "superseded_attempt",
                "scan_id": scan_id,
                "task_attempt": job_attempt,
                "current_attempt": current_attempt(scan),
            }
        # Idempotency: a retry after a completed run must not scan again.
        if already_terminal(scan):
            return {
                "success": True,
                "worker_version": WORKER_VERSION,
                "skipped": "already_terminal",
                "status": scan.get("status"),
                "scan_id": scan_id,
            }

        try:
            result = await run_scan(
                website_url=payload.website_url,
                path_prefix=payload.path_prefix,
                scan_mode="advanced",
                business_name=payload.business_name or "",
                cms_platform=payload.cms_platform or "",
                timeout_seconds=CRAWL_BUDGET_SECONDS,
                job_mode=True,
            )
            result = apply_indexability_quality_to_result(result)
            result = apply_render_evidence_quality(result)
            # Server-side 150-page cap. Discovery stays broad; only the crawl
            # sample is bounded.
            result = enforce_scan_response_page_budget(result, "advanced")
            result["beta_revision_fingerprint"] = live_revision()["fingerprint"]
            result.update({
                "request_id": payload.request_id,
                "idempotency_key": payload.idempotency_key or payload.request_id,
                "scan_id": scan_id,
                "scan_run_id": scan_id,
                "submitted_url": payload.website_url,
                "normalized_domain": payload.normalized_domain or website_host(payload.website_url),
                "respect_robots_txt": True,
            })
        except Exception:  # noqa: BLE001 - customer-safe envelope
            await write_terminal_failure(
                client, scan_id, "scanner_failed",
                "The scan stopped unexpectedly. No partial result was saved. Please try again.",
                attempt_count=job_attempt,
            )
            return {"success": False, "worker_version": WORKER_VERSION, "error_code": "scanner_failed"}

        signing_key = str(os.getenv("SCAN_EVIDENCE_SIGNING_KEY") or "")
        if not signing_key:
            raise HTTPException(status_code=503, detail="Authority signing is not configured.")

        outcome = await complete_authority(client, scan, result, signing_key)
        if outcome.get("transient"):
            # ScanRun untouched: Cloud Tasks retries the same scan_id safely.
            raise HTTPException(status_code=503, detail="Authority persistence is unavailable.")
        if outcome.get("superseded"):
            # A newer attempt owns the row: write nothing, charge nothing.
            return {
                "success": True,
                "worker_version": WORKER_VERSION,
                "skipped": "superseded_attempt",
                "scan_id": scan_id,
                "task_attempt": job_attempt,
            }
        if not outcome.get("ok"):
            await write_terminal_failure(
                client, scan_id, str(outcome.get("failure_code") or "authority_persistence_failed"),
                "The scan finished, but its result could not be saved. Please try again.",
                attempt_count=job_attempt,
            )
            return {"success": False, "worker_version": WORKER_VERSION, "error_code": outcome.get("failure_code")}

        return {
            "success": True,
            "worker_version": WORKER_VERSION,
            "scan_id": scan_id,
            "pages_crawled": result.get("pages_crawled"),
            "pages_found": result.get("pages_found"),
            "fix_list_id": outcome.get("fix_list_id"),
            "authority_proof_present": len(str(outcome.get("authority_proof") or "")) == 64,
        }
