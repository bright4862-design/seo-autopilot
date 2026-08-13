import base64
import hashlib
import hmac
import json
import os
from urllib.parse import urlsplit

import google.auth
from flask import Flask, jsonify, request
from google.auth.transport.requests import Request as GoogleAuthRequest
import requests

app = Flask(__name__)

CLOUD_SCOPE = "https://www.googleapis.com/auth/cloud-platform"

QUEUE_PATH = os.environ["SCAN_TASKS_QUEUE_PATH"]
WORKER_URL = os.environ["SCAN_WORKER_URL"].rstrip("/")
INVOKER_SA = os.environ["TASKS_INVOKER_SERVICE_ACCOUNT"]
SIGNING_KEY = os.environ["SCAN_EVIDENCE_SIGNING_KEY"]

worker_parts = urlsplit(WORKER_URL)
WORKER_ORIGIN = f"{worker_parts.scheme}://{worker_parts.netloc}"
DRAIN_URL = f"{WORKER_ORIGIN}/scan-job-drain"

ALLOWED_URLS = {WORKER_URL, DRAIN_URL}


def response_error(code, status):
    return jsonify({"success": False, "error": code}), status


@app.get("/health")
def health():
    return jsonify({
        "ok": True,
        "service": "fixlist-dispatch-gateway",
        "queue": QUEUE_PATH,
    })


@app.post("/dispatch")
def dispatch():
    raw = request.get_data(cache=True)
    supplied = request.headers.get("x-fixlist-signature", "").strip().lower()

    expected = hmac.new(
        SIGNING_KEY.encode("utf-8"),
        raw,
        hashlib.sha256,
    ).hexdigest()

    if not supplied or not hmac.compare_digest(supplied, expected):
        return response_error("invalid_signature", 401)

    try:
        payload = json.loads(raw)
    except Exception:
        return response_error("invalid_json", 400)

    if payload.get("queue_path") != QUEUE_PATH:
        return response_error("invalid_queue", 400)

    task = payload.get("task")
    if not isinstance(task, dict):
        return response_error("invalid_task", 400)

    name = str(task.get("name") or "")
    if not name.startswith(f"{QUEUE_PATH}/tasks/standard150-"):
        return response_error("invalid_task_name", 400)

    http = task.get("httpRequest")
    if not isinstance(http, dict):
        return response_error("invalid_http_request", 400)

    target = str(http.get("url") or "")
    if target not in ALLOWED_URLS:
        return response_error("invalid_worker_target", 400)

    if str(http.get("httpMethod") or "").upper() != "POST":
        return response_error("invalid_method", 400)

    oidc = http.get("oidcToken")
    if not isinstance(oidc, dict):
        return response_error("missing_oidc", 400)

    if oidc.get("serviceAccountEmail") != INVOKER_SA:
        return response_error("invalid_invoker", 400)

    if oidc.get("audience") != WORKER_ORIGIN:
        return response_error("invalid_audience", 400)

    if task.get("dispatchDeadline") != "480s":
        return response_error("invalid_dispatch_deadline", 400)

    try:
        decoded = base64.b64decode(http.get("body") or "", validate=True)
        job = json.loads(decoded)
    except Exception:
        return response_error("invalid_task_body", 400)

    scan_id = str(job.get("scan_id") or "").strip()
    if not scan_id:
        return response_error("missing_scan_id", 400)

    if job.get("scan_mode") not in (None, "standard_150"):
        return response_error("invalid_scan_mode", 400)

    try:
        credentials, _ = google.auth.default(scopes=[CLOUD_SCOPE])
        if not credentials.valid or not credentials.token:
            credentials.refresh(GoogleAuthRequest())
    except Exception:
        return response_error("adc_auth_failed", 503)

    endpoint = f"https://cloudtasks.googleapis.com/v2/{QUEUE_PATH}/tasks"

    try:
        upstream = requests.post(
            endpoint,
            headers={
                "authorization": f"Bearer {credentials.token}",
                "content-type": "application/json",
            },
            json={"task": task},
            timeout=20,
        )
    except requests.RequestException:
        return response_error("cloud_tasks_unreachable", 503)

    if upstream.status_code == 409:
        return jsonify({
            "success": True,
            "deduplicated": True,
            "taskName": name,
        })

    if upstream.status_code >= 400:
        return jsonify({
            "success": False,
            "error": "cloud_tasks_rejected",
            "upstream_status": upstream.status_code,
        }), 502 if upstream.status_code >= 500 else 403

    try:
        created = upstream.json()
    except Exception:
        created = {}

    return jsonify({
        "success": True,
        "deduplicated": False,
        "taskName": created.get("name") or name,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
