"""Keyless Firestore admission coordinator for FixList Standard 150.

Why this service exists
----------------------
Base44 documents ``updateMany(query, data)`` with matched/updated counts, but
does not document transactional, compare-and-set or linearizable semantics
strong enough to claim exactly-once cross-tab admission. Cloud Firestore
transactions are explicitly atomic with serializable isolation under
contention, so the admission decision moves here.

Why it is a separate Cloud Run service rather than Base44 code
--------------------------------------------------------------
Base44 functions have no Google Application Default Credentials, and the org
policy ``constraints/iam.disableServiceAccountKeyCreation`` forbids minting a
service-account key to give them any. This is the same constraint that put
Cloud Tasks dispatch behind a Cloud Run gateway. This service reuses that
proven shape exactly: Base44 HMAC-signs a request, Cloud Run performs the
privileged Google Cloud work under its own runtime identity via ADC.

Trust boundary
--------------
``owner_user_id`` arrives in the signed body and is trusted, because only
Base44 holds the signing root and Base44 authenticates the customer and
verifies paid entitlement before it signs anything. This service authenticates
the *caller*, not the end user, and deliberately performs no entitlement logic
of its own -- duplicating that check here would create a second place for it
to drift.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any, Callable

from flask import Flask, jsonify, request
from google.cloud import firestore

import admission

app = Flask(__name__)

SIGNING_ROOT = os.environ["SCAN_EVIDENCE_SIGNING_KEY"]
COLLECTION = os.environ.get("ADMISSION_COLLECTION", "scan_admission").strip() or "scan_admission"
FIRESTORE_PROJECT = os.environ.get("FIRESTORE_PROJECT", "").strip()
FIRESTORE_DATABASE = os.environ.get("FIRESTORE_DATABASE", "").strip()
MAX_CLOCK_SKEW_SECONDS = int(os.environ.get("ADMISSION_MAX_CLOCK_SKEW_SECONDS", "300"))
MAX_BODY_BYTES = int(os.environ.get("ADMISSION_MAX_BODY_BYTES", str(64 * 1024)))
LEASE_SECONDS = admission.normalize_lease_seconds(
    os.environ.get("ADMISSION_LEASE_SECONDS", admission.DEFAULT_LEASE_SECONDS)
)
SOURCE_SHA = os.environ.get("FIXLIST_COORDINATOR_SOURCE_SHA", "").strip()

if MAX_BODY_BYTES < 1024:
    raise RuntimeError("ADMISSION_MAX_BODY_BYTES is too small")
if not SIGNING_ROOT:
    raise RuntimeError("SCAN_EVIDENCE_SIGNING_KEY must be configured")

app.config["MAX_CONTENT_LENGTH"] = MAX_BODY_BYTES

# Domain separation. The dispatch gateway derives its key with the label
# "fixlist-dispatch-gateway-v1"; a distinct label here means a signature
# captured from one service can never be replayed against the other, even
# though both hang off the same signing root.
DERIVATION_LABEL = b"fixlist-admission-coordinator-v1"

_client: firestore.Client | None = None


def _firestore_client() -> firestore.Client:
    global _client
    if _client is None:
        kwargs: dict[str, Any] = {}
        if FIRESTORE_PROJECT:
            kwargs["project"] = FIRESTORE_PROJECT
        if FIRESTORE_DATABASE:
            kwargs["database"] = FIRESTORE_DATABASE
        _client = firestore.Client(**kwargs)
    return _client


def response_error(code: str, status: int):
    return jsonify({"success": False, "error": code}), status


@app.errorhandler(413)
def request_too_large(_error):
    return response_error("request_too_large", 413)


def _derive_key(root: str) -> bytes:
    return hmac.new(root.encode("utf-8"), DERIVATION_LABEL, hashlib.sha256).digest()


def _expected_signature(timestamp: str, raw_body: bytes) -> str:
    key = _derive_key(SIGNING_ROOT)
    signed = timestamp.encode("ascii") + b"\n" + raw_body
    return hmac.new(key, signed, hashlib.sha256).hexdigest()


def authenticate() -> tuple[dict[str, Any] | None, tuple[Any, int] | None]:
    """Verify the timestamped HMAC over the exact raw request bytes.

    Signing the raw bytes rather than a re-serialized parse is what makes the
    signature immune to key ordering and number formatting differences between
    the JavaScript signer and this Python verifier.
    """
    raw = request.get_data(cache=True)
    timestamp = request.headers.get("x-fixlist-timestamp", "").strip()
    supplied = request.headers.get("x-fixlist-signature", "").strip().lower()

    try:
        request_time = int(timestamp)
    except (TypeError, ValueError):
        return None, response_error("invalid_timestamp", 401)
    if abs(int(time.time()) - request_time) > MAX_CLOCK_SKEW_SECONDS:
        return None, response_error("stale_request", 401)

    expected = _expected_signature(timestamp, raw)
    if not supplied or not hmac.compare_digest(supplied, expected):
        return None, response_error("invalid_signature", 401)

    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, response_error("invalid_json", 400)
    if not isinstance(payload, dict):
        return None, response_error("invalid_payload", 400)
    return payload, None


def run_in_transaction(owner_user_id: str, decide: Callable[[dict[str, Any] | None], dict[str, Any]]):
    """Apply a pure decision function inside one Firestore transaction.

    The read and the conditional write share a transaction, so two concurrent
    callers cannot both observe "no active lease" and both win. Firestore
    retries the callback on contention; because ``decide`` is pure it is safe
    to re-run against the re-read document.
    """
    client = _firestore_client()
    ref = client.collection(COLLECTION).document(owner_user_id)

    @firestore.transactional
    def _apply(transaction: firestore.Transaction) -> dict[str, Any]:
        snapshot = ref.get(transaction=transaction)
        document = snapshot.to_dict() if snapshot.exists else None
        decision = decide(document)
        write = decision.get("write")
        if write:
            transaction.set(ref, write)
        return decision

    return _apply(client.transaction())


@app.get("/health")
def health():
    return jsonify({
        "ok": True,
        "service": "fixlist-admission-coordinator",
        "collection": COLLECTION,
        "lease_seconds": LEASE_SECONDS,
        "source_sha": SOURCE_SHA,
    })


@app.post("/claim")
def claim():
    payload, failure = authenticate()
    if failure:
        return failure
    assert payload is not None

    owner_user_id = str(payload.get("owner_user_id") or "").strip()
    request_id = str(payload.get("request_id") or "").strip()
    fingerprint = str(payload.get("request_fingerprint") or "").strip()

    # Minted here, never accepted from the caller: the token is the capability
    # that later authorizes the bind, so the coordinator must be its only source.
    minted_token = secrets.token_urlsafe(32)

    def decide(document: dict[str, Any] | None) -> dict[str, Any]:
        return admission.decide_claim(
            document,
            owner_user_id=owner_user_id,
            request_id=request_id,
            request_fingerprint=fingerprint,
            claim_token=minted_token,
            now=int(time.time()),
            lease_seconds=LEASE_SECONDS,
        )

    try:
        decision = run_in_transaction(owner_user_id, decide)
    except admission.AdmissionError as error:
        return response_error(error.code, 400)
    except Exception:
        return response_error("coordinator_unavailable", 503)

    if decision.get("error"):
        return response_error(decision["error"], 409)

    outcome = decision["outcome"]
    if outcome == admission.OUTCOME_BUSY:
        return jsonify({
            "success": False,
            "error": "admission_busy",
            "retry_after_seconds": decision.get("retry_after_seconds", 1),
        }), 429

    document = decision["document"]
    return jsonify({
        "success": True,
        "outcome": outcome,
        # On a fresh claim this is the token just minted; on an exact replay it
        # is the token the original winner was given, so a retried call can
        # still complete its bind.
        "claim_token": str(document.get("claim_token") or ""),
        "scan_id": str(document.get("scan_id") or ""),
        "lease_expires_at": document.get("lease_expires_at"),
    })


@app.post("/bind")
def bind():
    payload, failure = authenticate()
    if failure:
        return failure
    assert payload is not None

    owner_user_id = str(payload.get("owner_user_id") or "").strip()
    request_id = str(payload.get("request_id") or "").strip()
    claim_token = str(payload.get("claim_token") or "").strip()
    scan_id = str(payload.get("scan_id") or "").strip()

    def decide(document: dict[str, Any] | None) -> dict[str, Any]:
        return admission.decide_bind(
            document,
            request_id=request_id,
            claim_token=claim_token,
            scan_id=scan_id,
            now=int(time.time()),
        )

    try:
        decision = run_in_transaction(owner_user_id, decide)
    except admission.AdmissionError as error:
        return response_error(error.code, 400)
    except Exception:
        return response_error("coordinator_unavailable", 503)

    if decision.get("error"):
        status = 404 if decision["error"] == admission.ERROR_CLAIM_NOT_FOUND else 409
        return response_error(decision["error"], status)

    return jsonify({
        "success": True,
        "outcome": decision["outcome"],
        "scan_id": decision.get("scan_id", ""),
    })


@app.post("/release")
def release():
    payload, failure = authenticate()
    if failure:
        return failure
    assert payload is not None

    owner_user_id = str(payload.get("owner_user_id") or "").strip()
    scan_id = str(payload.get("scan_id") or "").strip()
    terminal_status = str(payload.get("terminal_status") or "").strip()

    def decide(document: dict[str, Any] | None) -> dict[str, Any]:
        return admission.decide_release(
            document,
            scan_id=scan_id,
            terminal_status=terminal_status,
            now=int(time.time()),
        )

    try:
        decision = run_in_transaction(owner_user_id, decide)
    except admission.AdmissionError as error:
        return response_error(error.code, 400)
    except Exception:
        return response_error("coordinator_unavailable", 503)

    if decision.get("error"):
        status = 404 if decision["error"] == admission.ERROR_CLAIM_NOT_FOUND else 409
        return response_error(decision["error"], status)

    return jsonify({"success": True, "outcome": decision["outcome"]})


@app.post("/status")
def status():
    """Read-only view, used by the watchdog to find leases worth investigating."""
    payload, failure = authenticate()
    if failure:
        return failure
    assert payload is not None

    owner_user_id = str(payload.get("owner_user_id") or "").strip()
    if not owner_user_id:
        return response_error("invalid_owner_user_id", 400)

    try:
        client = _firestore_client()
        snapshot = client.collection(COLLECTION).document(owner_user_id).get()
        document = snapshot.to_dict() if snapshot.exists else None
    except Exception:
        return response_error("coordinator_unavailable", 503)

    return jsonify({
        "success": True,
        "admission": admission.public_view(document),
        "lease_active": admission.is_lease_active(document, int(time.time())),
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
