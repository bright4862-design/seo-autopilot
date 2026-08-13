from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
from typing import Any
from urllib.parse import urlsplit

import google.auth
from flask import Flask, jsonify, request
from google.auth.transport.requests import Request as GoogleAuthRequest
import requests

app = Flask(__name__)

QUEUE_PATH = os.environ["SCAN_TASKS_QUEUE_PATH"].strip()
WORKER_URL = os.environ["SCAN_WORKER_URL"].strip().rstrip("/")
INVOKER_SA = os.environ["TASKS_INVOKER_SERVICE_ACCOUNT"].strip()
SIGNING_ROOT = os.environ["SCAN_EVIDENCE_SIGNING_KEY"]
MAX_CLOCK_SKEW_SECONDS = int(os.environ.get("DISPATCH_MAX_CLOCK_SKEW_SECONDS", "300"))

_worker = urlsplit(WORKER_URL)
if _worker.scheme != "https" or not _worker.netloc:
    raise RuntimeError("SCAN_WORKER_URL must be an HTTPS URL")
WORKER_ORIGIN = f"{_worker.scheme}://{_worker.netloc}"
DRAIN_URL = f"{WORKER_ORIGIN}/scan-job-drain"
ALLOWED_TARGETS = {WORKER_URL, DRAIN_URL}
TASK_PREFIX = f"{QUEUE_PATH}/tasks/"
TASK_RE = re.compile(r"^standard150-(?:(drain)-)?([A-Za-z0-9_-]+)-a([1-9][0-9]*)$")


def _json_error(code: str, status: int):
    return jsonify({"success": False, "error": code}), status


def _derive_dispatch_key(root: str) -> bytes:
    return hmac.new(root.encode("utf-8"), b"fixlist-dispatch-gateway-v1", hashlib.sha256).digest()


def _expected_signature(timestamp: str, raw_body: bytes) -> str:
    key = _derive_dispatch_key(SIGNING_ROOT)
    signed = timestamp.encode("ascii") + b"\n" + raw_body
    return hmac.new(key, signed, hashlib.sha256).hexdigest()


def _safe_scan_id(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "", str(value or ""))


def _decode_task_payload(task: dict[str, Any]) -> dict[str, Any] | None:
    try:
        encoded = task["httpRequest"]["body"]
        decoded = base64.b64decode(encoded, validate=True)
        value = json.loads(decoded)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def validate_dispatch(payload: Any) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(payload, dict):
        return None, "invalid_payload"
    if payload.get("queue_path") != QUEUE_PATH:
        return None, "invalid_queue"
    task = payload.get("task")
    if not isinstance(task, dict):
        return None, "invalid_task"

    name = str(task.get("name") or "")
    if not name.startswith(TASK_PREFIX):
        return None, "invalid_task_name"
    short_name = name[len(TASK_PREFIX):]
    match = TASK_RE.fullmatch(short_name)
    if not match:
        return None, "invalid_task_name"
    is_drain = bool(match.group(1))
    name_scan_id = match.group(2)

    if task.get("dispatchDeadline") != "480s":
        return None, "invalid_dispatch_deadline"

    http = task.get("httpRequest")
    if not isinstance(http, dict):
        return None, "invalid_http_request"
    if str(http.get("httpMethod") or "").upper() != "POST":
        return None, "invalid_method"

    target = str(http.get("url") or "").rstrip("/")
    expected_target = DRAIN_URL if is_drain else WORKER_URL
    if target not in ALLOWED_TARGETS or target != expected_target:
        return None, "invalid_worker_target"

    oidc = http.get("oidcToken")
    if not isinstance(oidc, dict):
        return None, "missing_oidc"
    if oidc.get("serviceAccountEmail") != INVOKER_SA:
        return None, "invalid_invoker"
    if oidc.get("audience") != WORKER_ORIGIN:
        return None, "invalid_audience"

    body = _decode_task_payload(task)
    if body is None:
        return None, "invalid_task_body"
    scan_id = _safe_scan_id(body.get("scan_id"))
    if not scan_id or scan_id != name_scan_id:
        return None, "scan_identity_mismatch"

    if is_drain:
        if not task.get("scheduleTime"):
            return None, "missing_drain_schedule"
    else:
        if task.get("scheduleTime"):
            return None, "unexpected_scan_schedule"
        if body.get("scan_mode") != "standard_150":
            return None, "invalid_scan_mode"
        if body.get("respect_robots_txt") is not True:
            return None, "invalid_robots_policy"

    return task, None


@app.get("/health")
def health():
    return jsonify({"ok": True, "service": "fixlist-dispatch-gateway", "queue": QUEUE_PATH, "worker_origin": WORKER_ORIGIN})


@app.post("/dispatch")
def dispatch():
    raw = request.get_data(cache=True)
    timestamp = request.headers.get("x-fixlist-timestamp", "").strip()
    supplied = request.headers.get("x-fixlist-signature", "").strip().lower()

    try:
        request_time = int(timestamp)
    except (TypeError, ValueError):
        return _json_error("invalid_timestamp", 401)
    if abs(int(time.time()) - request_time) > MAX_CLOCK_SKEW_SECONDS:
        return _json_error("stale_request", 401)

    expected = _expected_signature(timestamp, raw)
    if not supplied or not hmac.compare_digest(supplied, expected):
        return _json_error("invalid_signature", 401)

    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _json_error("invalid_json", 400)

    task, validation_error = validate_dispatch(payload)
    if validation_error:
        return _json_error(validation_error, 400)
    assert task is not None

    try:
        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        if not credentials.valid or not credentials.token:
            credentials.refresh(GoogleAuthRequest())
    except Exception:
        return _json_error("adc_auth_failed", 503)

    endpoint = f"https://cloudtasks.googleapis.com/v2/{QUEUE_PATH}/tasks"
    try:
        upstream = requests.post(
            endpoint,
            headers={"authorization": f"Bearer {credentials.token}", "content-type": "application/json"},
            json={"task": task},
            timeout=20,
        )
    except requests.RequestException:
        return _json_error("cloud_tasks_unreachable", 503)

    if upstream.status_code == 409:
        return jsonify({"success": True, "deduplicated": True, "taskName": task["name"]})
    if not upstream.ok:
        status = 503 if upstream.status_code >= 500 else 403
        return jsonify({"success": False, "error": "cloud_tasks_rejected", "upstream_status": upstream.status_code}), status

    try:
        created = upstream.json()
    except ValueError:
        created = {}
    return jsonify({"success": True, "deduplicated": False, "taskName": created.get("name") or task["name"]})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
