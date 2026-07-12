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
from .review import REVIEW_VERSION, run_review
from .review_calibration import CALIBRATION_VERSION, apply_review_evidence_calibration
from .scanner import VERSION, run_scan
from .trust_discovery import apply_trust_discovery_gate, enrich_scan_with_trust_pages

SCANNER_API_KEY = os.getenv("SCANNER_API_KEY", "")

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
    }


@app.post("/scan")
async def scan(payload: ScanRequest, x_scanner_key: str | None = Header(default=None)):
    if SCANNER_API_KEY and x_scanner_key != SCANNER_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    result = await run_scan(
        website_url=payload.website_url,
        path_prefix=payload.path_prefix,
        scan_mode=payload.scan_mode,
        business_name=payload.business_name or "",
        cms_platform=payload.cms_platform or "",
    )
    result = await enrich_scan_with_trust_pages(result)
    result = apply_indexability_quality_to_result(result)
    return apply_render_evidence_quality(result)


@app.post("/review")
async def review(payload: dict[str, Any] = Body(default_factory=dict), x_scanner_key: str | None = Header(default=None)):
    if SCANNER_API_KEY and x_scanner_key != SCANNER_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    result = run_review(payload)
    result = apply_trust_discovery_gate(result, payload)
    return apply_review_evidence_calibration(result, payload)
