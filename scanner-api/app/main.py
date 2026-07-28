import asyncio
import os
from typing import Any

from fastapi import Body, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .evidence_quality import EVIDENCE_QUALITY_GATE_VERSION, apply_evidence_quality_gate
from .grok_chat import GROK_CHAT_VERSION, GROK_MODEL_ID, run_grok_chat
from .indexability_postprocess import apply_indexability_quality_to_result
from .indexability_quality import INDEXABILITY_QUALITY_VERSION
from .navigation_indexability import NAVIGATION_INDEXABILITY_VERSION
from .render_evidence_quality import (
    RENDER_EVIDENCE_QUALITY_VERSION,
    apply_render_evidence_quality,
)
from .beta_revision import live_revision
from .observability import (
    OBSERVABILITY_VERSION,
    RequestTimer,
    review_metrics,
    scan_metrics,
    website_host,
)
from .review import ARCHETYPE_CLASSIFIER_VERSION, REVIEW_VERSION, run_review
from .review_calibration import CALIBRATION_VERSION, apply_review_evidence_calibration
from .scan_timing import SITEMAP_TIME_RESERVATION_VERSION
from .scanner import VERSION, run_scan
from .trust_discovery import apply_trust_discovery_gate, enrich_scan_with_trust_pages

SCANNER_API_KEY = os.getenv("SCANNER_API_KEY", "")
TRUST_DISCOVERY_TIMEOUTS = {"basic": 2.0, "quick": 3.0, "deep": 5.0, "advanced": 7.0}
SCAN_RESPONSE_PAGE_LIMITS = {"basic": 25, "quick": 40, "deep": 85, "advanced": 150}
SCANNER_BUILD_REVISION = "leaf_seed_grok_proxy_v1"

app = FastAPI(title="FixList Scanner API", version=VERSION)


class ScanRequest(BaseModel):
    website_url: str
    path_prefix: str | None = None
    scan_mode: str = "advanced"
    business_name: str | None = None
    cms_platform: str | None = None


class ChatRequest(BaseModel):
    message: str
    scan: dict[str, Any] = Field(default_factory=dict)


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
    return result


@app.get("/health")
def health():
    return {
        "ok": True,
        "version": VERSION,
        "scanner_build_revision": SCANNER_BUILD_REVISION,
        "grok_chat_version": GROK_CHAT_VERSION,
        "grok_model_id": GROK_MODEL_ID,
        "grok_proxy_enabled": True,
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


@app.get("/revision")
def revision():
    """Live beta-revision fingerprint for verifying a deployed scanner against
    the recorded freeze in data/beta-crawler-revision.json."""
    return live_revision()


@app.post("/chat")
async def chat(payload: ChatRequest, x_scanner_key: str | None = Header(default=None)):
    if SCANNER_API_KEY and x_scanner_key != SCANNER_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    message = str(payload.message or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Enter a question about the current scan.")
    if len(message) > 4000:
        raise HTTPException(status_code=400, detail="Question is too long.")

    try:
        answer = await run_grok_chat(message, payload.scan if isinstance(payload.scan, dict) else {})
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
    if SCANNER_API_KEY and x_scanner_key != SCANNER_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    timer = RequestTimer(
        "scan",
        website_host=website_host(payload.website_url),
        scan_mode=payload.scan_mode,
        scanner_version=VERSION,
        beta_revision_fingerprint=live_revision()["fingerprint"],
    )
    try:
        result = await run_scan(
            website_url=payload.website_url,
            path_prefix=payload.path_prefix,
            scan_mode=payload.scan_mode,
            business_name=payload.business_name or "",
            cms_platform=payload.cms_platform or "",
        )
        trust_timeout = TRUST_DISCOVERY_TIMEOUTS.get(str(payload.scan_mode or "advanced").lower(), 7.0)
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
    except Exception as exc:  # noqa: BLE001 - customer-safe envelope, full detail logged
        return timer.failed(exc)
    timer.completed(**scan_metrics(result))
    return result


@app.post("/review")
async def review(payload: dict[str, Any] = Body(default_factory=dict), x_scanner_key: str | None = Header(default=None)):
    if SCANNER_API_KEY and x_scanner_key != SCANNER_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

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
