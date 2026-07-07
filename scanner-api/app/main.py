import os

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from .scanner import run_scan

VERSION = "python_scanner_v1"
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
    return {"ok": True, "version": VERSION}


@app.post("/scan")
async def scan(payload: ScanRequest, x_scanner_key: str | None = Header(default=None)):
    if SCANNER_API_KEY and x_scanner_key != SCANNER_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    return await run_scan(
        website_url=payload.website_url,
        path_prefix=payload.path_prefix,
        scan_mode=payload.scan_mode,
        business_name=payload.business_name or "",
        cms_platform=payload.cms_platform or "",
    )
