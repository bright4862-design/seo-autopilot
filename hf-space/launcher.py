from __future__ import annotations

import os
import runpy
import time
from urllib.parse import urlparse

import requests


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


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
    rollout_attempts = _env_int("SCANNER_VERIFY_ATTEMPTS", 30)
    retry_delay = _env_int("SCANNER_VERIFY_DELAY_SECONDS", 10)
    request_timeout = _env_int("SCANNER_VERIFY_TIMEOUT_SECONDS", 12)
    transport_attempt_limit = min(rollout_attempts, 6)
    last_error = "Scanner verification did not complete."

    for attempt in range(1, rollout_attempts + 1):
        try:
            response = requests.get(
                endpoint,
                headers={"X-Scanner-Key": key},
                timeout=request_timeout,
            )
            if response.status_code == 401:
                return False, "SCANNER_API_KEY was rejected by Cloud Run."
            if response.status_code == 404:
                last_error = "Cloud Run has not published the authenticated health endpoint yet."
                if attempt < rollout_attempts:
                    print(
                        f"[FixList launcher] Waiting for scanner rollout "
                        f"({attempt}/{rollout_attempts}).",
                        flush=True,
                    )
                    time.sleep(retry_delay)
                    continue
                return False, last_error
            if response.status_code >= 500:
                last_error = f"Cloud Run health probe returned {response.status_code}."
                if attempt < rollout_attempts:
                    time.sleep(retry_delay)
                    continue
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or payload.get("authenticated") is not True:
                return False, "Cloud Run returned an invalid authentication response."
            revision = str(payload.get("scanner_build_revision") or "unknown")
            return True, f"Scanner authenticated ({revision})."
        except (requests.RequestException, ValueError) as exc:
            last_error = f"Scanner verification failed: {type(exc).__name__}: {str(exc)[:180]}"
            if attempt < transport_attempt_limit:
                time.sleep(retry_delay)
                continue
            return False, last_error

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
