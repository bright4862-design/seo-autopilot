"""Read-only Standard 150 Base44 handoff preflight.

This module is executed only by the disposable Cloud Run Job created while
building a worker candidate. It proves the candidate image can reach the
deployed Base44 durable control function with the same app origin and pinned
signing secret that production will use.

The probe intentionally names a ScanRun ID that cannot be a customer scan. A
healthy Base44 handoff verifies the signed envelope, executes the control
function, attempts the service-role read, and returns the function-level
404/error_code=worker_record_not_found response. No entity is created, updated,
released, or reconciled.
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

import httpx

from .scan_job import (
    DEFAULT_BASE44_API_URL,
    build_control_envelope,
    base44_api_url,
    base44_app_id,
    invoke_function,
)

PROBE_SCAN_ID = "fixlist_handoff_probe_nonexistent"
PROBE_FUNCTION = "durableScanWorkerControl"
EXPECTED_STATUS = 404
EXPECTED_ERROR_CODE = "worker_record_not_found"


async def run_handoff_probe(client: httpx.AsyncClient | None = None) -> dict[str, Any]:
    """Return safe probe metadata; never return or log the signed envelope."""
    signing_key = str(os.getenv("SCAN_EVIDENCE_SIGNING_KEY") or "")
    if not signing_key:
        return {"ok": False, "status_code": 0, "error_code": "signing_key_missing"}
    if not base44_app_id():
        return {"ok": False, "status_code": 0, "error_code": "base44_app_id_missing"}
    if base44_api_url() != DEFAULT_BASE44_API_URL:
        return {"ok": False, "status_code": 0, "error_code": "base44_app_origin_mismatch"}

    envelope = build_control_envelope("read", signing_key, scan_id=PROBE_SCAN_ID)
    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient()
    try:
        response = await invoke_function(
            client,
            PROBE_FUNCTION,
            envelope,
            timeout=20.0,
        )
    finally:
        if owns_client and client is not None:
            await client.aclose()

    status_code = int(response.get("status_code") or 0)
    body = response.get("body") if isinstance(response.get("body"), dict) else {}
    error_code = str(body.get("error_code") or "")
    return {
        "ok": status_code == EXPECTED_STATUS and error_code == EXPECTED_ERROR_CODE,
        "status_code": status_code,
        "error_code": error_code or "unexpected_response",
    }


async def _main() -> int:
    result = await run_handoff_probe()
    if result["ok"]:
        print("BASE44_HANDOFF_PREFLIGHT_OK")
        return 0
    print(
        "BASE44_HANDOFF_PREFLIGHT_FAILED "
        f"status={result['status_code']} code={result['error_code']}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
