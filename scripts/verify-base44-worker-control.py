#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import urllib.error
import urllib.request
from pathlib import Path

WORKER_VERSION = "scan_job_worker_v1_cloud_tasks"
CONTROL_VERSION = "durable_standard150_control_v1"
USER_AGENT = "Mozilla/5.0 (compatible; FixListStandard150Worker/1.0; +https://getfixlist.com)"
SENTINEL_SCAN_ID = "fixlist_preflight_missing_scan_v1"


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-id", required=True)
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--secret-file", required=True)
    args = parser.parse_args()

    if not args.api_url.startswith("https://"):
        raise SystemExit("Base44 API URL must use HTTPS.")
    secret_path = Path(args.secret_file)
    secret = secret_path.read_bytes()
    if not secret:
        raise SystemExit("Signing secret is empty.")

    signed = {
        "version": CONTROL_VERSION,
        "action": "read",
        "scan_id": SENTINEL_SCAN_ID,
        "identity": None,
        "failure": None,
    }
    proof = hmac.new(secret, canonical(signed), hashlib.sha256).hexdigest()
    payload = canonical({**signed, "proof": proof})

    url = f"{args.api_url.rstrip('/')}/api/apps/{args.app_id}/functions/durableScanWorkerControl"
    request = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-FixList-Worker": WORKER_VERSION,
            "User-Agent": USER_AGENT,
        },
    )

    status = 0
    headers = {}
    body_bytes = b""
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            status = int(response.status)
            headers = dict(response.headers.items())
            body_bytes = response.read(16_384)
    except urllib.error.HTTPError as error:
        status = int(error.code)
        headers = dict(error.headers.items())
        body_bytes = error.read(16_384)
    except Exception as error:
        print(f"BASE44_SIGNED_CONTROL_PROBE transport_error={type(error).__name__}")
        return 1
    finally:
        # Minimize plaintext secret lifetime in process state.
        secret = b""

    try:
        body = json.loads(body_bytes.decode("utf-8"))
    except Exception:
        body = {}
    error_code = str(body.get("error_code") or "") if isinstance(body, dict) else ""
    content_type = str(headers.get("Content-Type") or headers.get("content-type") or "").split(";", 1)[0][:120]
    cf_ray = str(headers.get("CF-Ray") or headers.get("cf-ray") or "")[:160]

    print(
        "BASE44_SIGNED_CONTROL_PROBE "
        f"status={status} error_code={error_code or 'none'} "
        f"content_type={content_type or 'none'} cf_ray={cf_ray or 'none'}"
    )
    if status != 404 or error_code != "worker_record_not_found":
        print("Refusing promotion: signed read-only Base44 worker-control handoff did not reach the deployed control function.")
        return 1

    print("BASE44_SIGNED_CONTROL_VERIFIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
