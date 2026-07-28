from __future__ import annotations

import os
import runpy
import time
from urllib.parse import urlparse

import requests


def scanner_base_url(raw_url: str) -> str:
    base = (raw_url or "").strip().rstrip("/")
    for suffix in ("/scan", "/review", "/chat", "/health", "/health/auth", "/revision"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    parsed = urlparse(base)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return base


def verify_scanner_connection() -> tuple[bool, str]:
    base = scanner_base_url(os.getenv("SCANNER_API_URL", ""))
    key = os.getenv("SCANNER_API_KEY", "").strip()
    if not base:
        return False, "SCANNER_API_URL is missing or invalid."
    if not key:
        return False, "SCANNER_API_KEY is missing."

    endpoint = f"{base}/health/auth"
    last_error = "Scanner verification did not complete."
    for attempt in range(1, 4):
        try:
            response = requests.get(
                endpoint,
                headers={"X-Scanner-Key": key},
                timeout=20,
            )
            if response.status_code == 401:
                return False, "SCANNER_API_KEY was rejected by Cloud Run."
            if response.status_code == 404:
                return False, "Cloud Run is missing the authenticated health endpoint."
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or payload.get("authenticated") is not True:
                return False, "Cloud Run returned an invalid authentication response."
            revision = str(payload.get("scanner_build_revision") or "unknown")
            return True, f"Scanner authenticated ({revision})."
        except (requests.RequestException, ValueError) as exc:
            last_error = f"Scanner verification failed: {type(exc).__name__}: {str(exc)[:180]}"
            if attempt < 3:
                time.sleep(attempt * 2)

    return False, last_error


def main() -> None:
    connected, detail = verify_scanner_connection()
    os.environ["SCANNER_CONNECTION_VERIFIED"] = "1" if connected else "0"
    os.environ["SCANNER_CONNECTION_DETAIL"] = detail

    if connected:
        print(f"[FixList launcher] {detail}", flush=True)
    else:
        # app.py enables the scan controls whenever both values are non-empty.
        # Remove the rejected key before importing the UI so it cannot show a
        # false green status or submit requests that are guaranteed to fail.
        os.environ["SCANNER_API_KEY"] = ""
        print(f"[FixList launcher] Scanning disabled: {detail}", flush=True)

    runpy.run_path("app_redesign.py", run_name="__main__")


if __name__ == "__main__":
    main()
