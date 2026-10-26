"""Isolated Extended 500 Firestore reservation + deterministic Cloud Tasks dispatch.

A deployable but DEFAULT-DISABLED coordinator. NOT the published Standard 150
coordinator/gateway. It accepts only separately signed Base44 service-role
paid entitlements and preflight grants; it never trusts browser plan assertions.

Firestore owner slot+immutable request receipt are committed atomically.
Cloud Tasks is a separate network operation: its result may be unknown.
Retry uses the exact same task name and NEVER frees a possibly queued slot.
Only a separate verified terminal-release receipt can release a bound owner.
"""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
import re
import time
from typing import Any
from urllib.parse import urlsplit

from flask import Flask, jsonify, request
from google.cloud import firestore
import google.auth
from google.auth.transport.requests import Request as GoogleAuthRequest
import requests

import core

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 128 * 1024

# Independent service and keys. Never reuse the Standard150 admission collection,
# its Cloud Tasks queue, or its evidence-signing/dispatch HMAC root.
ROOT = os.environ["EXTENDED500_COORDINATOR_SIGNING_KEY"]
ENTITLEMENT_KEY = os.environ["EXTENDED500_ENTITLEMENT_SIGNING_KEY"]
PREFLIGHT_KEY = os.environ["EXTENDED500_ADMISSION_SIGNING_KEY"]
TERMINAL_KEY = os.environ["EXTENDED500_TERMINAL_SIGNING_KEY"]
COLLECTION_SLOTS = os.getenv("EXTENDED500_SLOT_COLLECTION", "extended500_owner_slots")
COLLECTION_RECEIPTS = os.getenv("EXTENDED500_RECEIPT_COLLECTION", "extended500_request_receipts")
QUEUE_PATH = os.environ["EXTENDED500_TASKS_QUEUE_PATH"].strip()
WORKER_ORIGIN = os.environ["EXTENDED500_WORKER_ORIGIN"].rstrip("/")
INVOKER_SA = os.environ["EXTENDED500_INVOKER_SERVICE_ACCOUNT"].strip()
ENABLED = os.getenv("EXTENDED500_ATOMIC_ADMISSION_ENABLED", "").lower() == "true"
QUEUE_ENABLED = os.getenv("EXTENDED500_QUEUE_DISPATCH_ENABLED", "").lower() == "true"
MAX_SKEW = 300
MODE = core.MODE
DOMAIN = b"fixlist-extended500-atomic-admission-v1"
TERMINAL_VERSION = "extended500_verified_terminal_release_v1"
HEX64 = re.compile(r"[a-f0-9]{64}\Z")
for secret in (ROOT, ENTITLEMENT_KEY, PREFLIGHT_KEY, TERMINAL_KEY):
    if len(secret) < 32:
        raise RuntimeError("Extended 500 signing keys must be at least 32 characters")
if len({ROOT, ENTITLEMENT_KEY, PREFLIGHT_KEY, TERMINAL_KEY}) != 4:
    raise RuntimeError("Extended 500 signing roots must be distinct")
if not QUEUE_PATH or not WORKER_ORIGIN.startswith("https://") or not INVOKER_SA:
    raise RuntimeError("Extended 500 queue, worker origin and invoker are required")
if not WORKER_ORIGIN.endswith("/scan-job-extended500"):
    raise RuntimeError("Extended 500 task target must be its own worker endpoint")
# Prohibit a queue whose explicit name is the Standard 150 queue or drain.
if not re.fullmatch(
    r"projects/[A-Za-z0-9_-]+/locations/[A-Za-z0-9_-]+/queues/extended500-[A-Za-z0-9_-]+",
    QUEUE_PATH,
):
    raise RuntimeError("Extended 500 must use its dedicated queue")
if QUEUE_PATH in {os.getenv("SCAN_TASKS_QUEUE_PATH"), os.getenv("SCAN_DRAIN_QUEUE_PATH")}:
    raise RuntimeError("Extended 500 queue cannot be a Standard 150 queue")

_client = None


def store():
    global _client
    if _client is None:
        _client = firestore.Client()
    return _client


def error(code: str, status: int):
    return jsonify({"success": False, "error": code}), status


def canonical(value: Any):
    if isinstance(value, dict):
        return {key: canonical(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [canonical(v) for v in value]
    return value


def serialize(value: Any) -> bytes:
    return json.dumps(canonical(value), ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def seal(document: dict[str, Any], key: str) -> str:
    return hmac.new(key.encode(), serialize(document), hashlib.sha256).hexdigest()


def check_proof(document: Any, key: str, *, allowed_fields: set[str]) -> bool:
    if not isinstance(document, dict) or set(document) != allowed_fields | {"proof"}:
        return False
    proof = document.get("proof")
    if not isinstance(proof, str) or not HEX64.fullmatch(proof):
        return False
    signed = {key: val for key, val in document.items() if key != "proof"}
    try:
        return hmac.compare_digest(proof, seal(signed, key))
    except (TypeError, ValueError):
        return False


ENTITLEMENT_KEYS = {
    "version", "plan_id", "scan_mode", "entitlement_state",
    "owner_user_id", "scan_id", "project_id", "request_id",
    "idempotency_key", "access_id", "attempt_count", "issued_at", "expires_at",
}
GRANT_KEYS = {
    "version", "audience", "canonical_mode", "owner_user_id", "scan_id",
    "project_id", "request_id", "idempotency_key", "attempt_count",
    "website_url", "path_prefix", "respect_robots_txt",
    "owner_attested_robots_override", "issued_at", "expires_at",
}
TERMINAL_KEYS = {
    "version", "owner_user_id", "scan_id", "project_id", "request_id",
    "idempotency_key", "access_id", "attempt_count", "terminal_status",
}


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        time_value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return time_value if time_value.tzinfo else None
    except ValueError:
        return None


def verify_assertions(entitlement: Any, grant: Any, *, now: datetime | None = None) -> dict[str, Any]:
    if not check_proof(entitlement, ENTITLEMENT_KEY, allowed_fields=ENTITLEMENT_KEYS):
        raise core.AdmissionRefused("entitlement_signature_invalid")
    if not check_proof(grant, PREFLIGHT_KEY, allowed_fields=GRANT_KEYS):
        raise core.AdmissionRefused("preflight_signature_invalid")
    claim = core.canonical_request(entitlement)
    moment = now or datetime.now(timezone.utc)
    for doc in (entitlement, grant):
        issued, expires = parse_time(doc.get("issued_at")), parse_time(doc.get("expires_at"))
        if (not issued or not expires or issued > moment or expires <= moment
                or not timedelta(0) < (expires - issued) <= timedelta(seconds=300)):
            raise core.AdmissionRefused("entitlement_expired")
    if (grant.get("version") != "extended500_preflight_grant_v1"
            or grant.get("audience") != "fixlist_extended500_worker"
            or grant.get("canonical_mode") != MODE):
        raise core.AdmissionRefused("preflight_context_invalid")
    for key in ("scan_id", "owner_user_id", "project_id", "request_id", "idempotency_key", "attempt_count"):
        if type(grant.get(key)) is not type(claim[key]) or grant[key] != claim[key]:
            raise core.AdmissionRefused("preflight_identity_mismatch")
    if grant.get("issued_at") != entitlement.get("issued_at") or grant.get("expires_at") != entitlement.get("expires_at"):
        raise core.AdmissionRefused("preflight_time_mismatch")
    if not isinstance(grant.get("website_url"), str) or not grant["website_url"].startswith(("https://", "http://")):
        raise core.AdmissionRefused("invalid_worker_target")
    if type(grant.get("respect_robots_txt")) is not bool or type(grant.get("owner_attested_robots_override")) is not bool:
        raise core.AdmissionRefused("invalid_robots_policy")
    if grant["owner_attested_robots_override"] != (grant["respect_robots_txt"] is False):
        raise core.AdmissionRefused("invalid_robots_policy")
    return claim


def authenticate():
    stamp = request.headers.get("x-fixlist-timestamp", "")
    provided = request.headers.get("x-fixlist-signature", "").lower()
    try:
        stamp_int = int(stamp)
    except (TypeError, ValueError):
        return None, error("invalid_timestamp", 401)
    if abs(int(time.time()) - stamp_int) > MAX_SKEW:
        return None, error("stale_request", 401)
    raw = request.get_data(cache=True)
    derived = hmac.new(ROOT.encode(), DOMAIN, hashlib.sha256).digest()
    expected = hmac.new(derived, stamp.encode() + b"\n" + raw, hashlib.sha256).hexdigest()
    if not provided or not hmac.compare_digest(provided, expected):
        return None, error("invalid_signature", 401)
    try:
        # Reject nonfinite values, duplicate keys and non-object bodies.
        def unique(pairs):
            out = {}
            for key, value in pairs:
                if key in out:
                    raise ValueError("duplicate key")
                out[key] = value
            return out
        payload = json.loads(raw, object_pairs_hook=unique, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeDecodeError):
        return None, error("invalid_json", 400)
    return (payload, None) if isinstance(payload, dict) else (None, error("invalid_payload", 400))


def reserve(entitlement: dict, grant: dict) -> dict:
    claim = verify_assertions(entitlement, grant)
    client = store()
    slot_ref = client.collection(COLLECTION_SLOTS).document(claim["owner_user_id"])
    rid = core.receipt_id(claim)
    receipt_ref = client.collection(COLLECTION_RECEIPTS).document(rid)

    @firestore.transactional
    def apply(transaction):
        # Read both before any writes (Firestore transaction discipline).
        slot_doc = slot_ref.get(transaction=transaction)
        receipt_doc = receipt_ref.get(transaction=transaction)
        decision = core.decide_reservation(
            slot_doc.to_dict() if slot_doc.exists else None,
            receipt_doc.to_dict() if receipt_doc.exists else None,
            entitlement, QUEUE_PATH, issued_at=int(time.time()),
        )
        if decision["outcome"] == "reserved":
            transaction.create(receipt_ref, decision["receipt_write"])
            transaction.set(slot_ref, decision["slot_write"])
        return decision

    return apply(client.transaction())


def update_dispatch_state(claim: dict, state: str) -> None:
    client = store()
    slot_ref = client.collection(COLLECTION_SLOTS).document(claim["owner_user_id"])
    receipt_ref = client.collection(COLLECTION_RECEIPTS).document(core.receipt_id(claim))

    @firestore.transactional
    def apply(transaction):
        s, r = slot_ref.get(transaction=transaction), receipt_ref.get(transaction=transaction)
        decision = core.decide_dispatch_state(
            s.to_dict() if s.exists else None, r.to_dict() if r.exists else None, state=state,
        )
        if decision["outcome"] == "updated":
            transaction.set(slot_ref, decision["slot_write"])
            transaction.set(receipt_ref, decision["receipt_write"])
    apply(client.transaction())


def enqueue(claim: dict, grant: dict, task_name: str) -> str:
    """Return enqueued or dispatch_unknown. Never assume network timeout = absent."""
    if not QUEUE_ENABLED:
        return "dispatch_disabled"
    payload = {
        "scan_mode": MODE,
        "scan_id": claim["scan_id"], "request_id": claim["request_id"],
        "idempotency_key": claim["idempotency_key"], "project_id": claim["project_id"],
        "owner_user_id": claim["owner_user_id"], "attempt_count": claim["attempt_count"],
        "website_url": grant["website_url"], "path_prefix": grant["path_prefix"],
        "respect_robots_txt": grant["respect_robots_txt"],
        "owner_attested_robots_override": grant["owner_attested_robots_override"],
        "signed_grant": grant,
    }
    task = {
        "name": task_name, "dispatchDeadline": "480s",
        "httpRequest": {
            "httpMethod": "POST", "url": WORKER_ORIGIN,
            "headers": {"content-type": "application/json"},
            "oidcToken": {
                "serviceAccountEmail": INVOKER_SA,
                "audience": WORKER_ORIGIN.rsplit("/", 1)[0],
            },
            "body": base64.b64encode(serialize(payload)).decode(),
        },
    }
    try:
        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        if not credentials.valid or not credentials.token:
            credentials.refresh(GoogleAuthRequest())
        response = requests.post(
            f"https://cloudtasks.googleapis.com/v2/{QUEUE_PATH}/tasks",
            headers={"authorization": f"Bearer {credentials.token}", "content-type": "application/json"},
            json={"task": task}, timeout=20,
        )
        if response.ok:
            return "enqueued"
        # 409 may be the exact prior task or a conflicting actor's task.
        # Never interpret it as proof without a separately authenticated read.
        return "dispatch_unknown"
    except Exception:
        return "dispatch_unknown"


@app.get("/health")
def health():
    return jsonify({
        "ok": True, "service": "fixlist-extended500-admission",
        "atomic_admission_enabled": ENABLED,
        "queue_dispatch_enabled": QUEUE_ENABLED,
        "worker_completion_enabled": False,
    })


@app.post("/reserve")
def reservation_route():
    body, failure = authenticate()
    if failure:
        return failure
    if not ENABLED:
        return error("extended500_admission_disabled", 503)
    if set(body) != {"entitlement", "preflight_grant"}:
        return error("invalid_reservation_shape", 400)
    try:
        entitlement, grant = body["entitlement"], body["preflight_grant"]
        claim = verify_assertions(entitlement, grant)
        decision = reserve(entitlement, grant)
        if decision["outcome"] == "terminal_replay":
            return jsonify({"success": False, "state": "terminal_replay", "admitted": False}), 409
        dispatch_state = enqueue(claim, grant, decision["task_name"])
        if dispatch_state in {"enqueued", "dispatch_unknown"}:
            update_dispatch_state(claim, dispatch_state)
        # Reservation is real; dispatch may not be. Never return accepted=true
        # for an unverified queue result or before a working 500 worker exists.
        return jsonify({
            "success": True, "state": dispatch_state,
            "reserved": True, "admitted": False,
            "worker_execution_enabled": False,
            "replayed": decision["outcome"] == "replayed",
            "task_name": decision["task_name"],
        }), 200 if dispatch_state == "enqueued" else 202
    except core.AdmissionRefused as exc:
        return error(exc.code, 409)
    except Exception:
        return error("extended500_coordinator_unavailable", 503)


@app.post("/release")
def release_route():
    body, failure = authenticate()
    if failure:
        return failure
    if not ENABLED:
        return error("extended500_admission_disabled", 503)
    if set(body) != {"entitlement", "terminal"}:
        return error("invalid_release_shape", 400)
    entitlement, terminal = body["entitlement"], body["terminal"]
    if not check_proof(terminal, TERMINAL_KEY, allowed_fields=TERMINAL_KEYS):
        return error("verified_terminal_proof_invalid", 409)
    try:
        claim = core.canonical_request(entitlement)
        if not check_proof(entitlement, ENTITLEMENT_KEY, allowed_fields=ENTITLEMENT_KEYS):
            raise core.AdmissionRefused("entitlement_signature_invalid")
        for key in ("owner_user_id", "scan_id", "project_id", "request_id", "idempotency_key", "access_id", "attempt_count"):
            if type(terminal.get(key)) is not type(claim[key]) or terminal[key] != claim[key]:
                raise core.AdmissionRefused("verified_terminal_identity_mismatch")
        if terminal.get("version") != TERMINAL_VERSION:
            raise core.AdmissionRefused("verified_terminal_version_invalid")
        client = store()
        slot_ref = client.collection(COLLECTION_SLOTS).document(claim["owner_user_id"])
        receipt_ref = client.collection(COLLECTION_RECEIPTS).document(core.receipt_id(claim))
        @firestore.transactional
        def apply(transaction):
            s, r = slot_ref.get(transaction=transaction), receipt_ref.get(transaction=transaction)
            decision = core.decide_release(
                s.to_dict() if s.exists else None,
                r.to_dict() if r.exists else None, claim,
                terminal_status=terminal["terminal_status"], verified_terminal=True,
                released_at=int(time.time()),
            )
            if decision["outcome"] == "released":
                transaction.set(slot_ref, decision["slot_write"])
                transaction.set(receipt_ref, decision["receipt_write"])
            return decision
        result = apply(client.transaction())
        return jsonify({"success": True, "outcome": result["outcome"]})
    except core.AdmissionRefused as exc:
        return error(exc.code, 409)
    except Exception:
        return error("extended500_coordinator_unavailable", 503)
