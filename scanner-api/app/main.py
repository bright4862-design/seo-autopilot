import asyncio
import os
from typing import Any

from fastapi import Body, FastAPI, Header, HTTPException
from pydantic import BaseModel

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
from .review import REVIEW_VERSION, run_review
from .review_calibration import CALIBRATION_VERSION, apply_review_evidence_calibration
from .scanner import VERSION, run_scan
from .trust_discovery import apply_trust_discovery_gate, enrich_scan_with_trust_pages

SCANNER_API_KEY = os.getenv("SCANNER_API_KEY", "")
TRUST_DISCOVERY_TIMEOUTS = {"basic": 2.0, "quick": 3.0, "deep": 5.0, "advanced": 7.0}

app = FastAPI(title="FixList Scanner API", version=VERSION)


class ScanRequest(BaseModel):
    website_url: str
    path_prefix: str | None = None
    scan_mode: str = "advanced"
    business_name: str | None = None
    cms_platform: str | None = None


@app.get("/health")
def health():
    return {
        "ok": True,
        "version": VERSION,
        "review_version": REVIEW_VERSION,
        "review_evidence_calibration_version": CALIBRATION_VERSION,
        "indexability_quality_version": INDEXABILITY_QUALITY_VERSION,
        "navigation_indexability_version": NAVIGATION_INDEXABILITY_VERSION,
        "render_evidence_quality_version": RENDER_EVIDENCE_QUALITY_VERSION,
        "beta_revision_fingerprint": live_revision()["fingerprint"],
        "observability_version": OBSERVABILITY_VERSION,
    }


@app.get("/revision")
def revision():
    """Live beta-revision fingerprint for verifying a deployed scanner against
    the recorded freeze in data/beta-crawler-revision.json."""
    return live_revision()


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
    except Exception as exc:  # noqa: BLE001 - customer-safe envelope, full detail logged
        return timer.failed(exc)
    timer.completed(**review_metrics(result))
    return result
