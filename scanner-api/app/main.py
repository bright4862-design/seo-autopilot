import os
from typing import Any

from fastapi import Body, FastAPI, Header, HTTPException
from pydantic import BaseModel

from .review import REVIEW_VERSION, run_review
from .scanner import VERSION, run_scan
from .trust_discovery import enrich_scan_with_trust_pages

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
    return {"ok": True, "version": VERSION, "review_version": REVIEW_VERSION}


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
    return await enrich_scan_with_trust_pages(result)


@app.post("/review")
async def review(payload: dict[str, Any] = Body(default_factory=dict), x_scanner_key: str | None = Header(default=None)):
    if SCANNER_API_KEY and x_scanner_key != SCANNER_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    return run_review(payload)
