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
import re
import secrets
import time
from typing import Any, Callable

from flask import Flask, jsonify, request
from google.cloud import firestore

import admission
import control
import target_contacts

app = Flask(__name__)

SIGNING_ROOT = os.environ["SCAN_EVIDENCE_SIGNING_KEY"]
OPERATOR_SIGNING_ROOT = os.environ["ADMISSION_OPERATOR_SIGNING_KEY"]
OPERATOR_SERVICE_ACCOUNT = os.environ["ADMISSION_OPERATOR_SERVICE_ACCOUNT"].strip()
OPERATOR_AUDIENCE = os.environ["ADMISSION_OPERATOR_AUDIENCE"].strip()
OPERATOR_ID = os.environ["ADMISSION_OPERATOR_ID"].strip()
COLLECTION = os.environ.get("ADMISSION_COLLECTION", "scan_admission").strip() or "scan_admission"
CONTROL_COLLECTION = os.environ.get("ADMISSION_CONTROL_COLLECTION", "scan_admission_control").strip() or "scan_admission_control"
SNAPSHOT_COLLECTION = os.environ.get("ADMISSION_SNAPSHOT_COLLECTION", "scan_admission_snapshots").strip() or "scan_admission_snapshots"
AUDIT_COLLECTION = os.environ.get("ADMISSION_AUDIT_COLLECTION", "scan_admission_audit").strip() or "scan_admission_audit"
COHORT_COLLECTION = os.environ.get("ADMISSION_COHORT_COLLECTION", "scan_admission_cohorts").strip() or "scan_admission_cohorts"
RECONCILIATION_COLLECTION = os.environ.get("ADMISSION_RECONCILIATION_COLLECTION", "scan_admission_reconciliation").strip() or "scan_admission_reconciliation"
TARGET_COOLDOWN_COLLECTION = "scan_target_cooldowns"
TARGET_CONTACT_GATE_COLLECTION = "scan_target_contact_gates"
TARGET_CONTACT_DELIVERY_COLLECTION = "scan_target_contact_deliveries"
CONTROL_DOCUMENT = "global"
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
if not OPERATOR_SIGNING_ROOT:
    raise RuntimeError("ADMISSION_OPERATOR_SIGNING_KEY must be configured")
if hmac.compare_digest(SIGNING_ROOT, OPERATOR_SIGNING_ROOT):
    raise RuntimeError("Admission operator and evidence signing roots must be distinct")
if not OPERATOR_SERVICE_ACCOUNT or not OPERATOR_AUDIENCE or not OPERATOR_ID:
    raise RuntimeError("Admission operator identity and audience must be configured")

app.config["MAX_CONTENT_LENGTH"] = MAX_BODY_BYTES

# Domain separation. The dispatch gateway derives its key with the label
# "fixlist-dispatch-gateway-v1"; a distinct label here means a signature
# captured from one service can never be replayed against the other, even
# though both hang off the same signing root.
DERIVATION_LABEL = b"fixlist-admission-coordinator-v1"
OPERATOR_DERIVATION_LABEL = b"fixlist-admission-operator-v1"
CLAIM_EVIDENCE_LABEL = b"fixlist-admission-claim-evidence-v1"
CLAIM_EVIDENCE_VERSION = "admission_claim_evidence_v1"

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


def _log_auth_rejection(reason: str, *, label: bytes, **fields: Any) -> None:
    """Emit one structured line whenever authentication rejects a request.

    Cloud Run turns a JSON object on stdout into a structured log entry. Until
    this existed the coordinator rejected every request in total silence, and
    an empty log was repeatedly misread as "the request never reached the
    application" -- which sent an outage investigation after the network path
    while the application was in fact running and returning 401.

    Only non-secret discriminators are recorded. The supplied signature, the
    expected signature, the signing roots and the request body never appear.
    """
    entry = {
        "severity": "WARNING",
        "message": f"admission authentication rejected: {reason}",
        "event": "admission_auth_rejected",
        "reason": reason,
        "auth_label": label.decode("ascii"),
        "path": request.path,
        **fields,
    }
    print(json.dumps(entry, sort_keys=True, default=str), flush=True)


@app.errorhandler(413)
def request_too_large(_error):
    return response_error("request_too_large", 413)


def _derive_key(root: str, label: bytes = DERIVATION_LABEL) -> bytes:
    return hmac.new(root.encode("utf-8"), label, hashlib.sha256).digest()


def _expected_signature(
    timestamp: str,
    raw_body: bytes,
    *,
    root: str = SIGNING_ROOT,
    label: bytes = DERIVATION_LABEL,
) -> str:
    key = _derive_key(root, label)
    signed = timestamp.encode("ascii") + b"\n" + raw_body
    return hmac.new(key, signed, hashlib.sha256).hexdigest()


def _authenticate_hmac(
    *,
    root: str,
    label: bytes,
    timestamp_header: str,
    signature_header: str,
) -> tuple[dict[str, Any] | None, tuple[Any, int] | None]:
    """Verify the timestamped HMAC over the exact raw request bytes.

    Signing the raw bytes rather than a re-serialized parse is what makes the
    signature immune to key ordering and number formatting differences between
    the JavaScript signer and this Python verifier.
    """
    raw = request.get_data(cache=True)
    timestamp = request.headers.get(timestamp_header, "").strip()
    supplied = request.headers.get(signature_header, "").strip().lower()

    try:
        request_time = int(timestamp)
    except (TypeError, ValueError):
        _log_auth_rejection(
            "invalid_timestamp",
            label=label,
            timestamp_present=bool(timestamp),
        )
        return None, response_error("invalid_timestamp", 401)
    skew_seconds = int(time.time()) - request_time
    if abs(skew_seconds) > MAX_CLOCK_SKEW_SECONDS:
        _log_auth_rejection(
            "stale_request",
            label=label,
            skew_seconds=skew_seconds,
            max_clock_skew_seconds=MAX_CLOCK_SKEW_SECONDS,
        )
        return None, response_error("stale_request", 401)

    expected = _expected_signature(timestamp, raw, root=root, label=label)
    if not supplied or not hmac.compare_digest(supplied, expected):
        # A signing root that carries surrounding whitespace is a server-side
        # configuration fact, not a property of the caller. Cloud Run injects a
        # secret payload verbatim. A caller configured through an unquoted dotenv
        # entry can instead receive the stripped root, leaving the two services
        # with different bytes. Reporting whether the caller signed with that
        # stripped root names the mismatch directly instead of leaving it to be
        # guessed. It is computed only when this service's own root is affected,
        # so it discloses nothing about a caller's key, and the request is
        # rejected either way.
        whitespace_fields: dict[str, Any] = {}
        if root != root.strip():
            whitespace_fields["root_has_surrounding_whitespace"] = True
            whitespace_fields["matches_whitespace_stripped_root"] = bool(
                supplied
                and hmac.compare_digest(
                    supplied,
                    _expected_signature(timestamp, raw, root=root.strip(), label=label),
                )
            )
        _log_auth_rejection(
            "invalid_signature",
            label=label,
            signature_present=bool(supplied),
            signature_length=len(supplied),
            body_bytes=len(raw),
            **whitespace_fields,
        )
        return None, response_error("invalid_signature", 401)

    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, response_error("invalid_json", 400)
    if not isinstance(payload, dict):
        return None, response_error("invalid_payload", 400)
    return payload, None


def authenticate() -> tuple[dict[str, Any] | None, tuple[Any, int] | None]:
    return _authenticate_hmac(
        root=SIGNING_ROOT,
        label=DERIVATION_LABEL,
        timestamp_header="x-fixlist-timestamp",
        signature_header="x-fixlist-signature",
    )


def _verify_google_operator_token(token: str, audience: str) -> dict[str, Any]:
    # Imported lazily so the pure/unit suites can install their Firestore fake
    # without having to emulate the entire google-auth namespace.
    from google.auth.transport.requests import Request as GoogleRequest
    from google.oauth2 import id_token

    return id_token.verify_oauth2_token(token, GoogleRequest(), audience=audience)


OPERATOR_TOKEN_VERIFIER = _verify_google_operator_token


def authenticate_operator() -> tuple[dict[str, Any] | None, tuple[Any, int] | None]:
    authorization = request.headers.get("authorization", "").strip()
    if not authorization.lower().startswith("bearer "):
        return None, response_error("operator_identity_missing", 401)
    token = authorization.split(" ", 1)[1].strip()
    try:
        claims = OPERATOR_TOKEN_VERIFIER(token, OPERATOR_AUDIENCE)
    except Exception:
        return None, response_error("operator_identity_invalid", 401)
    issuer = str(claims.get("iss") or "")
    email = str(claims.get("email") or "")
    if (
        issuer not in {"accounts.google.com", "https://accounts.google.com"}
        or str(claims.get("aud") or "") != OPERATOR_AUDIENCE
        or email != OPERATOR_SERVICE_ACCOUNT
        or claims.get("email_verified") is not True
    ):
        return None, response_error("operator_identity_forbidden", 403)
    payload, failure = _authenticate_hmac(
        root=OPERATOR_SIGNING_ROOT,
        label=OPERATOR_DERIVATION_LABEL,
        timestamp_header="x-fixlist-operator-timestamp",
        signature_header="x-fixlist-operator-signature",
    )
    if failure:
        return None, failure
    assert payload is not None
    supplied_operator = str(payload.get("operator_id") or OPERATOR_ID).strip()
    if supplied_operator != OPERATOR_ID:
        return None, response_error("operator_identity_conflict", 403)
    return payload, None


def run_in_transaction(
    owner_user_id: str,
    decide: Callable[[dict[str, Any] | None], dict[str, Any]],
    *,
    terminal_release: bool = False,
    terminal_cooldown: dict[str, Any] | None = None,
):
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
        if decision.get("error"):
            return decision
        moment = int(time.time())
        cooldown = None
        if terminal_cooldown is not None:
            # A different owner must never observe the released slot without
            # the origin deadline from the same Firestore commit.
            cooldown_ref = _target_cooldown_ref(client, terminal_cooldown["target_origin"])
            cooldown = admission.decide_target_cooldown(
                document, _document_value(cooldown_ref.get(transaction=transaction)),
                terminal_cooldown, now=moment, clock_skew_seconds=MAX_CLOCK_SKEW_SECONDS,
                terminal_release_retry=decision["outcome"] == admission.OUTCOME_ALREADY_RELEASED,
            )
            if cooldown.get("error"):
                return cooldown
        if terminal_release:
            decision = target_contacts.terminal_fence(document, decision, now=moment)
        if cooldown is not None:
            if cooldown.get("write"):
                transaction.set(cooldown_ref, cooldown["write"])
            decision["target_cooldown_outcome"] = cooldown["outcome"]
        write = decision.get("write")
        if write:
            transaction.set(ref, write)
        return decision

    return _apply(client.transaction())


def _document_value(snapshot: Any) -> dict[str, Any] | None:
    return snapshot.to_dict() if getattr(snapshot, "exists", False) else None


def _transaction_documents(transaction: firestore.Transaction, collection: Any) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for snapshot in transaction.get(collection):
        value = _document_value(snapshot)
        if isinstance(value, dict):
            values.append(value)
    return values


def _active_admission_query(client: firestore.Client):
    return (
        client.collection(COLLECTION)
        .where("state", "in", [admission.STATE_CLAIMED, admission.STATE_BOUND])
        .limit(control.MAX_INTERNAL_OBLIGATIONS + 1)
    )


def _live_reconciliation_query(client: firestore.Client):
    return (
        client.collection(RECONCILIATION_COLLECTION)
        .where("state", "==", "live")
        .limit(control.MAX_INTERNAL_OBLIGATIONS + 1)
    )


def _target_cooldown_ref(client: firestore.Client, target_origin: str):
    key = target_contacts.origin_key(target_origin)
    return client.collection(TARGET_COOLDOWN_COLLECTION).document(key)


def _target_contact_gate_ref(client: firestore.Client, target_origin: str):
    return client.collection(TARGET_CONTACT_GATE_COLLECTION).document(target_contacts.origin_key(target_origin))


def run_target_contact_transaction(payload: dict[str, Any], decide: Callable):
    client = _firestore_client()
    owner_ref = client.collection(COLLECTION).document(payload["owner_user_id"])
    gate_ref = _target_contact_gate_ref(client, payload["target_origin"])
    cooldown_ref = _target_cooldown_ref(client, payload["target_origin"])
    delivery_ref = client.collection(TARGET_CONTACT_DELIVERY_COLLECTION).document(target_contacts.delivery_key(payload))

    @firestore.transactional
    def _apply(transaction: firestore.Transaction) -> dict[str, Any]:
        result = decide(
            _document_value(owner_ref.get(transaction=transaction)),
            _document_value(delivery_ref.get(transaction=transaction)),
            _document_value(gate_ref.get(transaction=transaction)),
            _document_value(cooldown_ref.get(transaction=transaction)),
            payload, now=int(time.time()),
        )
        for key, ref in (
            ("owner_write", owner_ref), ("delivery_write", delivery_ref),
            ("gate_write", gate_ref), ("cooldown_write", cooldown_ref),
        ):
            if key in result:
                transaction.set(ref, result[key])
        return result

    return _apply(client.transaction())


def run_claim_transaction(
    owner_user_id: str,
    target_origin: str,
    decide: Callable[[dict[str, Any] | None, dict[str, Any] | None, Callable[[int], dict[str, Any]]], dict[str, Any]],
):
    """Serialize one claim against the global barrier and owner slot.

    A fresh claim writes ``claim_sequence`` on the same global control document
    that barrier close writes. Firestore therefore orders the two commits: the
    claim either precedes the close cutoff or retries against the closed mode.
    """
    client = _firestore_client()
    owner_ref = client.collection(COLLECTION).document(owner_user_id)
    control_ref = client.collection(CONTROL_COLLECTION).document(CONTROL_DOCUMENT)

    @firestore.transactional
    def _apply(transaction: firestore.Transaction) -> dict[str, Any]:
        control_document = _document_value(control_ref.get(transaction=transaction))
        owner_document = _document_value(owner_ref.get(transaction=transaction))

        def read_origin_wait(now: int) -> dict[str, Any]:
            if not target_origin:
                return {}
            cooldown_ref = _target_cooldown_ref(client, target_origin)
            gate_ref = _target_contact_gate_ref(client, target_origin)
            return target_contacts.origin_wait(
                _document_value(gate_ref.get(transaction=transaction)),
                _document_value(cooldown_ref.get(transaction=transaction)), now=now,
            )

        decision = decide(owner_document, control_document, read_origin_wait)
        if decision.get("control_write"):
            transaction.set(control_ref, admission.durable_control(decision["control_write"]))
        if decision.get("write"):
            transaction.set(owner_ref, decision["write"])
        return decision

    return _apply(client.transaction())


def run_reconciliation_start_transaction(
    invocation_id: str,
    decide: Callable[[dict[str, Any] | None, dict[str, Any] | None], dict[str, Any]],
):
    """Atomically order a fresh reconciler against barrier close."""
    client = _firestore_client()
    invocation_ref = client.collection(RECONCILIATION_COLLECTION).document(invocation_id)
    control_ref = client.collection(CONTROL_COLLECTION).document(CONTROL_DOCUMENT)

    @firestore.transactional
    def _apply(transaction: firestore.Transaction) -> dict[str, Any]:
        control_document = _document_value(control_ref.get(transaction=transaction))
        invocation_document = _document_value(invocation_ref.get(transaction=transaction))
        decision = decide(invocation_document, control_document)
        if decision.get("control_write"):
            transaction.set(control_ref, admission.durable_control(decision["control_write"]))
        if decision.get("write"):
            transaction.create(invocation_ref, decision["write"])
        return decision

    return _apply(client.transaction())


def run_reconciliation_finish_transaction(
    invocation_id: str,
    decide: Callable[[dict[str, Any] | None], dict[str, Any]],
):
    client = _firestore_client()
    invocation_ref = client.collection(RECONCILIATION_COLLECTION).document(invocation_id)

    @firestore.transactional
    def _apply(transaction: firestore.Transaction) -> dict[str, Any]:
        invocation_document = _document_value(invocation_ref.get(transaction=transaction))
        decision = decide(invocation_document)
        if decision.get("write"):
            transaction.set(invocation_ref, decision["write"])
        return decision

    return _apply(client.transaction())


def _new_record_id(prefix: str) -> str:
    return f"{prefix}_{int(time.time())}_{secrets.token_hex(8)}"


def _claim_evidence(document: dict[str, Any]) -> tuple[dict[str, Any], str]:
    evidence = {
        "version": CLAIM_EVIDENCE_VERSION,
        "owner_user_id": str(document.get("owner_user_id") or ""),
        "request_id": str(document.get("request_id") or ""),
        "barrier_generation": admission.normalize_barrier_generation(document.get("barrier_generation", 0)),
        "claim_sequence": admission.normalize_claim_sequence(document.get("claim_sequence", 0)),
        "admission_mode": str(document.get("admission_mode") or admission.BARRIER_OPEN),
        "acceptance_cohort_id": str(document.get("acceptance_cohort_id") or ""),
        "acceptance_release_id": str(document.get("acceptance_release_id") or ""),
        "acceptance_source_sha": str(document.get("acceptance_source_sha") or ""),
        "acceptance_expires_at": document.get("acceptance_expires_at"),
    }
    proof = control.sign_record(SIGNING_ROOT, CLAIM_EVIDENCE_LABEL, evidence)
    return evidence, proof


def _operator_error_status(code: str) -> int:
    if code.startswith("invalid_"):
        return 400
    return 409


def _barrier_response(operation: str, payload: dict[str, Any]) -> dict[str, Any]:
    context = control.validate_operator_context(payload)
    scoped_pilot_version = {
        "start_500_pilot": control.PUBLISHED_500_PILOT_SNAPSHOT_VERSION,
        "hold_500_pilot": control.PUBLISHED_500_PILOT_SNAPSHOT_VERSION,
        "hold_150_pilot": control.PUBLISHED_150_PILOT_SNAPSHOT_VERSION,
        "hold_public_150": control.PUBLIC_150_HOLD_SNAPSHOT_VERSION,
        "start_eligible_500": control.ELIGIBLE_500_SNAPSHOT_VERSION,
        "hold_eligible_500": control.ELIGIBLE_500_SNAPSHOT_VERSION,
    }.get(operation)
    snapshot_field = (
        "eligible_500_snapshot" if scoped_pilot_version == control.ELIGIBLE_500_SNAPSHOT_VERSION
        else "public_150_snapshot" if operation == "hold_public_150"
        else "pilot_snapshot" if scoped_pilot_version else "drain_snapshot"
    )
    now = int(time.time())
    snapshot_id = _new_record_id("snapshot")
    audit_event_id = _new_record_id("audit")
    client = _firestore_client()
    control_ref = client.collection(CONTROL_COLLECTION).document(CONTROL_DOCUMENT)
    snapshot_ref = client.collection(SNAPSHOT_COLLECTION).document(snapshot_id)
    audit_ref = client.collection(AUDIT_COLLECTION).document(audit_event_id)

    @firestore.transactional
    def _apply(transaction: firestore.Transaction) -> dict[str, Any]:
        current = admission.normalized_control(
            _document_value(control_ref.get(transaction=transaction))
        )
        admissions, invocations = [], []
        if not scoped_pilot_version:
            admissions = _transaction_documents(transaction, _active_admission_query(client))
            invocations = _transaction_documents(transaction, _live_reconciliation_query(client))

        def record_cohorts(*definitions: dict[str, Any]) -> None:
            refs = [client.collection(COHORT_COLLECTION).document(item["cohort_id"]) for item in definitions]
            if any(_document_value(ref.get(transaction=transaction)) is not None for ref in refs):
                raise control.ControlError("acceptance_cohort_exists")
            for ref, definition in zip(refs, definitions, strict=True):
                transaction.create(ref, control.signed_acceptance_definition(definition, OPERATOR_SIGNING_ROOT))

        published_500_pilot = current.get(admission.PUBLISHED_500_PILOT)
        legacy_access = current.get(admission.LEGACY_CUSTOMER_ACCESS)
        public_150 = current.get(admission.PUBLIC_150)
        public_500 = current.get(admission.PUBLIC_500)
        if operation == "status":
            try:
                expected_generation = admission.normalize_barrier_generation(payload.get("expected_generation"))
            except admission.AdmissionError as error:
                raise control.ControlError(error.code) from None
            if expected_generation != current["generation"]:
                raise control.ControlError("barrier_generation_conflict")
            result = {**current, "current_snapshot_id": snapshot_id}
            boundary = {
                "observed_mode": current["mode"],
                "observed_generation": current["generation"],
                "claim_sequence_cutoff": current["claim_sequence"],
            }
            if isinstance(published_500_pilot, dict):
                state = "configured" if published_500_pilot["expires_at"] > now else "expired"
                boundary[admission.PUBLISHED_500_PILOT] = control.published_500_pilot_boundary(published_500_pilot, state=state)
            if isinstance(legacy_access, dict):
                boundary[admission.LEGACY_CUSTOMER_ACCESS] = control.legacy_access_boundary(legacy_access, now=now)
            if isinstance(public_150, dict):
                boundary[admission.PUBLIC_150] = control.public_150_boundary(public_150, now=now)
            if isinstance(public_500, dict):
                boundary[admission.PUBLIC_500] = control.eligible_500_boundary(public_500, now=now)
        else:
            close_replay = operation == "close" and control.is_exact_close_replay(
                current,
                payload.get("intended_prior"),
                operator_id=OPERATOR_ID,
                **context,
            )
            if close_replay:
                prior = current
                result = {**current, "current_snapshot_id": snapshot_id}
                boundary = {
                    "replayed_close": True,
                    "prior_mode": current.get("intended_prior_mode"),
                    "prior_generation": current.get("intended_prior_generation"),
                    "closed_generation": current["generation"],
                    "claim_sequence_cutoff": current["claim_sequence"],
                    "original_close_snapshot_id": current.get("close_snapshot_id"),
                    "original_close_audit_event_id": current.get("close_audit_event_id"),
                }
            else:
                prior = control.require_intended_prior(current, payload.get("intended_prior"))
            if close_replay:
                pass
            elif operation == "close":
                result = control.close_control(
                    current,
                    snapshot_id=snapshot_id,
                    operator_id=OPERATOR_ID,
                    now=now,
                    **context,
                )
                result["close_audit_event_id"] = audit_event_id
                boundary = {
                    "prior_mode": prior["mode"],
                    "prior_generation": prior["generation"],
                    "closed_generation": result["generation"],
                    "claim_sequence_cutoff": prior["claim_sequence"],
                }
            elif operation in {"open", "open_public_150"}:
                # Opening public claims is allowed only from a freshly proven
                # drained closed generation. This check and the mode change are
                # one transaction, so no claim can appear between them.
                preflight = control.build_snapshot(
                    snapshot_id=snapshot_id,
                    control=current,
                    admission_documents=admissions,
                    reconciliation_documents=invocations,
                    now=now,
                    operator_id=OPERATOR_ID,
                    signing_root=OPERATOR_SIGNING_ROOT,
                    boundary={"preflight": True},
                    **context,
                )
                if not preflight["drain_ready"]:
                    raise control.ControlError("barrier_not_drained")
                definition = (
                    control.public_150_definition(payload[admission.PUBLIC_150], now=now, operator_id=OPERATOR_ID)
                    if operation == "open_public_150" else None
                )
                result = control.open_control(
                    current,
                    snapshot_id=snapshot_id,
                    operator_id=OPERATOR_ID,
                    now=now,
                    public_150=definition,
                    **context,
                )
                boundary = {
                    "prior_mode": prior["mode"],
                    "prior_generation": prior["generation"],
                    "opened_generation": result["generation"],
                    "claim_sequence_cutoff": prior["claim_sequence"],
                }
                if definition is not None:
                    record_cohorts(definition)
                    boundary[admission.PUBLIC_150] = control.public_150_boundary(definition, now=now)
            elif operation == "acceptance_only":
                preflight = control.build_snapshot(
                    snapshot_id=snapshot_id,
                    control=current,
                    admission_documents=admissions,
                    reconciliation_documents=invocations,
                    now=now,
                    operator_id=OPERATOR_ID,
                    signing_root=OPERATOR_SIGNING_ROOT,
                    boundary={"preflight": True},
                    **context,
                )
                if not preflight["drain_ready"]:
                    raise control.ControlError("barrier_not_drained")
                definition = control.acceptance_definition(
                    payload.get("acceptance"),
                    now=now,
                    operator_id=OPERATOR_ID,
                )
                legacy = control.legacy_access_definition(
                    payload["legacy_access"], definition, now=now, operator_id=OPERATOR_ID,
                ) if "legacy_access" in payload else None
                if legacy:
                    legacy["verified_at"] = control.verify_legacy_access_preflight(
                        payload["legacy_preflight"], legacy, now=now,
                    )
                result = control.acceptance_control(
                    current,
                    definition,
                    snapshot_id=snapshot_id,
                    operator_id=OPERATOR_ID,
                    now=now,
                    legacy_access=legacy,
                    **context,
                )
                if legacy:
                    record_cohorts(definition, legacy)
                else:
                    record_cohorts(definition)
                boundary = {
                    "prior_mode": prior["mode"],
                    "prior_generation": prior["generation"],
                    "acceptance_generation": result["generation"],
                    "claim_sequence_cutoff": prior["claim_sequence"],
                    "cohort_id": definition["cohort_id"],
                    "release_id": definition["release_id"],
                    "source_sha": definition["source_sha"],
                }
                if definition.get("required_launcher_build_id"):
                    boundary["required_launcher_build_id"] = definition["required_launcher_build_id"]
                if legacy:
                    boundary[admission.LEGACY_CUSTOMER_ACCESS] = control.legacy_access_boundary(legacy, now=now)
            elif operation == "hold_150_pilot":
                pilot = current.get("acceptance")
                if (current["mode"] != admission.BARRIER_ACCEPTANCE_ONLY
                        or not isinstance(legacy_access, dict) or not isinstance(pilot, dict)
                        or pilot.get("cohort_id") != payload.get("cohort_id")
                        or not pilot.get("required_launcher_build_id") or pilot.get("source_sha") != SOURCE_SHA):
                    raise control.ControlError("published_150_pilot_scope_mismatch")
                result = {**current, "acceptance": None, "generation": int(current["generation"]) + 1,
                          "current_snapshot_id": snapshot_id}
                boundary = {
                    "published_150_pilot": {
                        "state": "held", "cohort_id": pilot["cohort_id"], "source_sha": pilot["source_sha"],
                    },
                    admission.LEGACY_CUSTOMER_ACCESS: control.legacy_access_boundary(legacy_access, now=now),
                }
            elif operation == "start_500_pilot":
                if published_500_pilot is not None or control.eligible_500_active(public_500, now=now):
                    raise control.ControlError("published_500_pilot_already_configured")
                definition = control.acceptance_definition(payload.get("acceptance"), now=now, operator_id=OPERATOR_ID)
                if len(definition["owner_allowlist"]) > control.MAX_PUBLISHED_500_PILOT_OWNERS:
                    raise control.ControlError("invalid_acceptance_owner_allowlist")
                definition["page_cap"] = 500
                result = control.update_published_500_pilot(current, snapshot_id=snapshot_id, definition=definition)
                record_cohorts(definition)
                boundary = {
                    admission.PUBLISHED_500_PILOT: control.published_500_pilot_boundary(definition, state="configured"),
                }
            elif operation == "hold_500_pilot":
                if not isinstance(published_500_pilot, dict) or published_500_pilot["cohort_id"] != payload.get("cohort_id"):
                    raise control.ControlError("published_500_pilot_scope_mismatch")
                result = control.update_published_500_pilot(current, snapshot_id=snapshot_id, definition=None)
                boundary = {
                    admission.PUBLISHED_500_PILOT: control.published_500_pilot_boundary(published_500_pilot, state="held"),
                }
            elif operation in {"start_eligible_500", "hold_eligible_500"}:
                definition = (control.eligible_500_definition(payload.get(admission.PUBLIC_500), now=now, operator_id=OPERATOR_ID)
                              if operation == "start_eligible_500" else None)
                if definition is None and isinstance(public_500, dict) and public_500["source_sha"] != SOURCE_SHA:
                    raise control.ControlError("acceptance_source_mismatch")
                result = control.update_eligible_500(
                    current, snapshot_id=snapshot_id, now=now, definition=definition, cohort_id=payload.get("cohort_id"),
                )
                if definition is not None:
                    record_cohorts(definition)
                boundary = {admission.PUBLIC_500: control.eligible_500_boundary(result[admission.PUBLIC_500], now=now)}
                if isinstance(public_150, dict):
                    boundary[admission.PUBLIC_150] = control.public_150_boundary(public_150, now=now)
            elif operation == "hold_public_150":
                result = control.hold_public_150(
                    current, snapshot_id=snapshot_id, cohort_id=payload.get("cohort_id"), now=now,
                )
                boundary = {
                    admission.PUBLIC_150: control.public_150_boundary(result[admission.PUBLIC_150], now=now),
                }
            else:
                raise control.ControlError("invalid_barrier_operation")
            if operation in {"start_500_pilot", "hold_500_pilot"} and isinstance(public_150, dict):
                boundary[admission.PUBLIC_150] = control.public_150_boundary(public_150, now=now)
            if operation == "hold_public_150" and isinstance(public_500, dict):
                boundary[admission.PUBLIC_500] = control.eligible_500_boundary(public_500, now=now)
            if operation == "hold_public_150" and isinstance(published_500_pilot, dict):
                state = "configured" if published_500_pilot["expires_at"] > now else "expired"
                boundary[admission.PUBLISHED_500_PILOT] = control.published_500_pilot_boundary(published_500_pilot, state=state)
            transaction.set(control_ref, admission.durable_control(result))

        # Status is an audited observation rather than a pure GET. Persisting
        # its immutable snapshot pointer makes the response independently
        # discoverable without changing mode, generation, or either sequence.
        if operation == "status":
            transaction.set(control_ref, admission.durable_control(result))

        snapshot = control.build_snapshot(
            snapshot_id=snapshot_id,
            control=result,
            admission_documents=admissions,
            reconciliation_documents=invocations,
            now=now,
            operator_id=OPERATOR_ID,
            signing_root=OPERATOR_SIGNING_ROOT,
            boundary=boundary,
            scoped_pilot_version=scoped_pilot_version,
            **context,
        )
        audit = control.build_audit_event(
            event_id=audit_event_id,
            operation=operation,
            operator_id=OPERATOR_ID,
            now=now,
            prior=current,
            result=result,
            snapshot_id=snapshot_id,
            signing_root=OPERATOR_SIGNING_ROOT,
            **context,
        )
        transaction.create(snapshot_ref, snapshot)
        transaction.create(audit_ref, audit)
        return {
            "success": True,
            "operation": operation,
            "barrier": {
                "mode": result["mode"],
                "generation": result["generation"],
                "claim_sequence": result["claim_sequence"],
                "current_snapshot_id": snapshot_id,
            },
            snapshot_field: control.public_snapshot(snapshot),
            "audit_event_id": audit_event_id,
        }

    return _apply(client.transaction())


def _handle_barrier_operation(operation: str):
    payload, failure = authenticate_operator()
    if failure:
        return failure
    assert payload is not None
    supplied_operation = str(payload.get("operation") or operation).strip().replace("-", "_")
    published_pilot = operation == "acceptance_only" and supplied_operation in {
        "published_pilot_acceptance", "published_pilot_with_legacy",
    }
    scoped_public_open = operation == "open" and supplied_operation == "open_public_150"
    if supplied_operation != operation and not (published_pilot or scoped_public_open):
        return response_error("barrier_operation_conflict", 409)
    wants_legacy = published_pilot and supplied_operation == "published_pilot_with_legacy"
    if ("legacy_access" in payload) != wants_legacy or ("legacy_preflight" in payload) != wants_legacy:
        return response_error("invalid_legacy_access_operation", 400)
    if not scoped_public_open and admission.PUBLIC_150 in payload:
        return response_error("barrier_operation_conflict", 409)
    if (admission.PUBLIC_500 in payload) != (operation == "start_eligible_500"):
        return response_error("barrier_operation_conflict", 409)
    if published_pilot or operation in {"start_500_pilot", "start_eligible_500"} or scoped_public_open:
        policy_key = (admission.PUBLIC_150 if scoped_public_open else admission.PUBLIC_500
                      if operation == "start_eligible_500" else "acceptance")
        acceptance = payload.get(policy_key)
        launcher = acceptance.get("required_launcher_build_id") if isinstance(acceptance, dict) else None
        if not isinstance(launcher, str) or not re.fullmatch(r"[0-9a-f]{64}", launcher):
            return response_error("invalid_acceptance_launcher_build_id", 400)
        if not re.fullmatch(r"[0-9a-f]{40}", SOURCE_SHA) or acceptance.get("source_sha") != SOURCE_SHA:
            return response_error("acceptance_source_mismatch", 409)
    if operation in {"hold_150_pilot", "hold_eligible_500"} and (not re.fullmatch(r"[0-9a-f]{40}", SOURCE_SHA)
                                           or payload.get("source_sha") != SOURCE_SHA):
        return response_error("acceptance_source_mismatch", 409)
    try:
        return jsonify(_barrier_response("open_public_150" if scoped_public_open else operation, payload))
    except (control.ControlError, admission.AdmissionError) as error:
        return response_error(error.code, _operator_error_status(error.code))
    except Exception:
        return response_error("barrier_unavailable", 503)


@app.post("/ops/barrier/close")
def barrier_close():
    return _handle_barrier_operation("close")


@app.post("/ops/barrier/status")
def barrier_status():
    return _handle_barrier_operation("status")


@app.post("/ops/barrier/open")
def barrier_open():
    return _handle_barrier_operation("open")


@app.post("/ops/barrier/acceptance-only")
def barrier_acceptance_only():
    return _handle_barrier_operation("acceptance_only")


@app.post("/ops/barrier/pilot-500/start")
def barrier_start_500_pilot():
    return _handle_barrier_operation("start_500_pilot")


@app.post("/ops/barrier/pilot-500/hold")
def barrier_hold_500_pilot():
    return _handle_barrier_operation("hold_500_pilot")


@app.post("/ops/barrier/pilot-150/hold")
def barrier_hold_150_pilot():
    return _handle_barrier_operation("hold_150_pilot")


@app.post("/ops/barrier/eligible-500/start")
def barrier_start_eligible_500():
    return _handle_barrier_operation("start_eligible_500")


@app.post("/ops/barrier/eligible-500/hold")
def barrier_hold_eligible_500():
    return _handle_barrier_operation("hold_eligible_500")


@app.post("/ops/barrier/public-150/hold")
def barrier_hold_public_150():
    return _handle_barrier_operation("hold_public_150")


@app.get("/health")
def health():
    return jsonify({
        "ok": True,
        "service": "fixlist-admission-coordinator",
        "collection": COLLECTION,
        "lease_seconds": LEASE_SECONDS,
        "source_sha": SOURCE_SHA,
        "barrier_modes": sorted(admission.BARRIER_MODES),
        "claim_evidence_version": CLAIM_EVIDENCE_VERSION,
        "published_pilot_launcher_binding": True,
        "published_pilot_legacy_access": True,
        "published_500_pilot_admission": True,
        "public_standard_150_cohort_admission": True,
        "eligible_500_admission": True,
        "claim_evidence_proof_label": CLAIM_EVIDENCE_LABEL.decode("ascii"),
        "drain_snapshot_version": control.DRAIN_SNAPSHOT_VERSION,
        "drain_snapshot_proof_label": control.SNAPSHOT_LABEL.decode("ascii"),
        "operator_audit_version": control.AUDIT_EVENT_VERSION,
        "reconciliation_invocation_version": control.RECONCILIATION_INVOCATION_VERSION,
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
    queue_if_origin_busy = payload.get("queue_if_origin_busy") is True
    launcher_build = payload.get("pilot_launcher_build_id", "")
    if not isinstance(launcher_build, str) or (launcher_build and not re.fullmatch(r"[0-9a-f]{64}", launcher_build)):
        return response_error("invalid_pilot_launcher_build_id", 400)
    pilot_page_cap = payload.get("pilot_page_cap")
    if "pilot_page_cap" in payload and (type(pilot_page_cap) is not int or pilot_page_cap not in (150, 500) or not launcher_build):
        return response_error("invalid_pilot_page_cap", 400)
    published_500_pilot = pilot_page_cap == 500
    standard_150_launcher = payload.get("standard_150_launcher_build_id", "")
    if "standard_150_launcher_build_id" in payload and (
        not isinstance(standard_150_launcher, str) or not re.fullmatch(r"[0-9a-f]{64}", standard_150_launcher)
        or published_500_pilot or launcher_build
    ):
        return response_error("invalid_standard_150_launcher_build_id", 400)
    standard_500_launcher = payload.get("standard_500_launcher_build_id", "")
    if "standard_500_launcher_build_id" in payload and (
        not isinstance(standard_500_launcher, str) or not re.fullmatch(r"[a-f0-9]{64}", standard_500_launcher)
        or launcher_build or standard_150_launcher
    ):
        return response_error("invalid_standard_500_launcher_build_id", 400)
    pilot_replay_only = "pilot_replay_only" in payload
    if pilot_replay_only and (payload["pilot_replay_only"] is not True or pilot_page_cap is None):
        return response_error("invalid_pilot_replay_only", 400)
    try:
        target_origin = admission.normalize_target_origin(payload["target_origin"]) if "target_origin" in payload else ""
    except admission.AdmissionError as error:
        return response_error(error.code, 400)

    # Minted here, never accepted from the caller: the token is the capability
    # that later authorizes the bind, so the coordinator must be its only source.
    minted_token = secrets.token_urlsafe(32)

    def decide(
        document: dict[str, Any] | None,
        control_document: dict[str, Any] | None,
        read_origin_wait: Callable[[int], dict[str, Any]],
    ) -> dict[str, Any]:
        moment = int(time.time())
        current = admission.normalized_control(control_document)
        # An exact retry is not a new admission. It must remain recoverable
        # while the barrier is closed so a lost claim response cannot strand a
        # pre-boundary claim. No new lease or budget is created on this path.
        candidate = admission.decide_claim(
            document,
            owner_user_id=owner_user_id,
            request_id=request_id,
            request_fingerprint=fingerprint,
            claim_token=minted_token,
            now=moment,
            lease_seconds=LEASE_SECONDS,
            barrier_generation=current["generation"],
            claim_sequence=int(current["claim_sequence"]) + 1,
            admission_mode=current["mode"],
            target_origin=target_origin,
        )
        if candidate.get("outcome") == admission.OUTCOME_REPLAYED:
            admitted_150_launcher = (document or {}).get("standard_150_launcher_build_id")
            admitted_500_launcher = (document or {}).get("standard_500_launcher_build_id", "")
            if ((document or {}).get("pilot_launcher_build_id", "") != launcher_build
                    or (document or {}).get("pilot_page_cap") != pilot_page_cap
                    or (admitted_150_launcher is not None and admitted_150_launcher != standard_150_launcher)
                    or admitted_500_launcher != standard_500_launcher):
                return {"outcome": None, "error": admission.ERROR_SCAN_INTAKE_PAUSED}
            return candidate
        # Rule A can release an expired or terminal slot for a new request.
        # A broad 500 transition must not recycle the same stored request ID,
        # since its existing ScanRun and admission proof keep their original cap.
        if (candidate.get("outcome") == admission.OUTCOME_CLAIMED and isinstance(document, dict)
                and document.get("request_id") == request_id
                and (standard_500_launcher or document.get("standard_500_launcher_build_id"))):
            return {"outcome": None, "error": admission.ERROR_REQUEST_CONFLICT}
        if pilot_replay_only:
            return {"outcome": None, "error": admission.ERROR_SCAN_INTAKE_PAUSED}
        acceptance_key = admission.PUBLIC_500 if standard_500_launcher else admission.claim_cohort_key(current)
        if published_500_pilot:
            acceptance_key = admission.PUBLISHED_500_PILOT
        acceptance = current.get(acceptance_key)
        if acceptance_key in {admission.PUBLIC_150, admission.PUBLISHED_500_PILOT, admission.PUBLIC_500}:
            expected_cap = 150 if acceptance_key == admission.PUBLIC_150 else 500
            if (not isinstance(acceptance, dict) or acceptance.get("source_sha") != SOURCE_SHA
                    or acceptance.get("page_cap") != expected_cap):
                return {"outcome": None, "error": admission.ERROR_SCAN_INTAKE_PAUSED}
        elif current["mode"] == admission.BARRIER_ACCEPTANCE_ONLY:
            pilot = current.get("acceptance")
            if current.get(admission.LEGACY_CUSTOMER_ACCESS) is not None:
                if not launcher_build:
                    if standard_150_launcher:
                        return {"outcome": None, "error": admission.ERROR_SCAN_INTAKE_PAUSED}
                    acceptance_key = admission.LEGACY_CUSTOMER_ACCESS
                elif pilot_page_cap != 150 or not isinstance(pilot, dict) or pilot.get("source_sha") != SOURCE_SHA:
                    return {"outcome": None, "error": admission.ERROR_SCAN_INTAKE_PAUSED}
            acceptance = current.get(acceptance_key)
            if acceptance_key == admission.LEGACY_CUSTOMER_ACCESS and (
                    not isinstance(acceptance, dict) or acceptance.get("coordinator_source_sha") != SOURCE_SHA
                    or acceptance.get("page_cap") != 150
                    or (isinstance(pilot, dict) and owner_user_id in pilot.get("owner_allowlist", ()))):
                return {"outcome": None, "error": admission.ERROR_SCAN_INTAKE_PAUSED}
        required_launcher = acceptance.get("required_launcher_build_id", "") if isinstance(acceptance, dict) else ""
        actual_launcher = (standard_150_launcher if acceptance_key == admission.PUBLIC_150
                           else standard_500_launcher if acceptance_key == admission.PUBLIC_500 else launcher_build)
        if actual_launcher != required_launcher or (acceptance_key == admission.PUBLIC_150 and not actual_launcher):
            return {"outcome": None, "error": admission.ERROR_SCAN_INTAKE_PAUSED}
        policy = admission.decide_claim_policy(
            control_document,
            owner_user_id=owner_user_id,
            now=moment,
            acceptance_key=acceptance_key,
        )
        if not policy.get("allowed"):
            return {"outcome": None, "error": policy.get("error", admission.ERROR_SCAN_INTAKE_PAUSED)}
        if candidate.get("outcome") != admission.OUTCOME_CLAIMED:
            return candidate
        reservation = admission.reserve_fresh_claim(
            control_document,
            owner_user_id=owner_user_id,
            now=moment,
            acceptance_key=acceptance_key,
        )
        if not reservation.get("allowed"):
            return {"outcome": None, "error": reservation.get("error", admission.ERROR_SCAN_INTAKE_PAUSED)}
        # Reservation is a pure decision. Discard it on an origin refusal so
        # the barrier sequence, cohort budget and owner slot are untouched.
        origin_wait = read_origin_wait(moment)
        if origin_wait and not (queue_if_origin_busy and origin_wait["error"] == target_contacts.ORIGIN_BUSY):
            return origin_wait
        claimed = admission.decide_claim(
            document,
            owner_user_id=owner_user_id,
            request_id=request_id,
            request_fingerprint=fingerprint,
            claim_token=minted_token,
            now=moment,
            lease_seconds=LEASE_SECONDS,
            barrier_generation=reservation["barrier_generation"],
            claim_sequence=reservation["claim_sequence"],
            admission_mode=reservation["mode"],
            acceptance=reservation.get("acceptance"),
            target_origin=target_origin,
        )
        if launcher_build:
            claimed["write"]["pilot_launcher_build_id"] = launcher_build
        if pilot_page_cap is not None:
            claimed["write"]["pilot_page_cap"] = pilot_page_cap
        if acceptance_key == admission.PUBLIC_150:
            claimed["write"]["standard_150_launcher_build_id"] = standard_150_launcher
        if acceptance_key == admission.PUBLIC_500:
            claimed["write"]["standard_500_launcher_build_id"] = standard_500_launcher
        claimed["control_write"] = reservation["control_write"]
        return claimed

    try:
        decision = run_claim_transaction(owner_user_id, target_origin, decide)
    except admission.AdmissionError as error:
        return response_error(error.code, 400)
    except Exception:
        return response_error("coordinator_unavailable", 503)

    if decision.get("error"):
        if "retry_after_seconds" in decision:
            return target_contact_refusal(decision)
        if decision["error"] == admission.ERROR_SCAN_INTAKE_PAUSED:
            return response_error(decision["error"], 423)
        return response_error(decision["error"], 409)

    outcome = decision["outcome"]
    if outcome == admission.OUTCOME_BUSY:
        return jsonify({
            "success": False,
            "error": "admission_busy",
            "retry_after_seconds": decision.get("retry_after_seconds", 1),
        }), 429

    document = decision["document"]
    claim_evidence, claim_evidence_proof = _claim_evidence(document)
    result = {
        "success": True,
        "outcome": outcome,
        # On a fresh claim this is the token just minted; on an exact replay it
        # is the token the original winner was given, so a retried call can
        # still complete its bind.
        "claim_token": str(document.get("claim_token") or ""),
        "request_id": str(document.get("request_id") or ""),
        "scan_id": str(document.get("scan_id") or ""),
        "lease_expires_at": document.get("lease_expires_at"),
        "barrier_generation": admission.normalize_barrier_generation(document.get("barrier_generation", 0)),
        "claim_sequence": admission.normalize_claim_sequence(document.get("claim_sequence", 0)),
        "admission_mode": str(document.get("admission_mode") or admission.BARRIER_OPEN),
        "cohort_evidence": claim_evidence,
        "cohort_evidence_proof": claim_evidence_proof,
    }
    if document.get("target_origin"):
        result["target_origin"] = document["target_origin"]
    if document.get("pilot_launcher_build_id"):
        result["pilot_launcher_build_id"] = document["pilot_launcher_build_id"]
    if "pilot_page_cap" in document:
        result["pilot_page_cap"] = document["pilot_page_cap"]
    if document.get("standard_500_launcher_build_id"):
        result["standard_500_launcher_build_id"] = document["standard_500_launcher_build_id"]
    return jsonify(result)


def target_contact_refusal(decision):
    error = decision["error"]
    status = 429 if error == "target_cooldown_active" else 409
    if error == target_contacts.CONTACTS_DRAINING:
        status = 503
    retry_after = decision["retry_after_seconds"]
    fields = {
        "success": False, "error": error, "retry_after_seconds": retry_after,
    }
    if decision.get("expires_source") == "default":
        fields["expires_source"] = "default"
    return jsonify(fields), status, {"Retry-After": str(retry_after)}


@app.post("/acquire-target-contact")
@app.post("/settle-target-contact")
def target_contact():
    payload, failure = authenticate()
    if failure:
        return failure
    assert payload is not None
    acquire = request.path == "/acquire-target-contact"
    try:
        target_contacts.validate(payload, action=target_contacts.ACQUIRE_ACTION if acquire else target_contacts.SETTLE_ACTION)
        decision = run_target_contact_transaction(
            payload, target_contacts.decide_acquire if acquire else target_contacts.decide_settle,
        )
    except admission.AdmissionError as error:
        return response_error(error.code, 400)
    except Exception:
        return response_error("coordinator_unavailable", 503)
    if "retry_after_seconds" in decision:
        return target_contact_refusal(decision)
    if decision.get("error"):
        status = 400 if decision["error"] == target_contacts.INVALID_CONTACT else 409
        return response_error(decision["error"], status)
    result = {"success": True, "outcome": decision["outcome"]}
    if acquire:
        result["seconds_remaining"] = decision["seconds_remaining"]
    return jsonify(result)


@app.post("/observe-target-cooldown")
def observe_target_cooldown():
    payload, failure = authenticate()
    if failure:
        return failure
    assert payload is not None

    try:
        observation = admission.validate_cooldown_observation(
            payload, now=int(time.time()), clock_skew_seconds=MAX_CLOCK_SKEW_SECONDS,
        )
    except admission.AdmissionError as error:
        return response_error(error.code, 400)

    try:
        client = _firestore_client()
        owner_ref = client.collection(COLLECTION).document(observation["owner_user_id"])
        cooldown_ref = _target_cooldown_ref(client, observation["target_origin"])

        @firestore.transactional
        def apply_observation(transaction: firestore.Transaction) -> dict[str, Any]:
            decision = admission.decide_target_cooldown(
                _document_value(owner_ref.get(transaction=transaction)),
                _document_value(cooldown_ref.get(transaction=transaction)),
                observation, now=int(time.time()), clock_skew_seconds=MAX_CLOCK_SKEW_SECONDS,
            )
            if decision.get("write"):
                transaction.set(cooldown_ref, decision["write"])
            return decision

        decision = apply_observation(client.transaction())
    except Exception:
        return response_error("coordinator_unavailable", 503)

    if decision.get("error"):
        return response_error(decision["error"], 409)
    return jsonify({"success": True, "outcome": decision["outcome"]})


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
    if "barrier_generation" not in payload:
        return response_error("invalid_barrier_generation", 400)
    barrier_generation = payload.get("barrier_generation")

    def decide(document: dict[str, Any] | None) -> dict[str, Any]:
        return admission.decide_bind(
            document,
            request_id=request_id,
            claim_token=claim_token,
            scan_id=scan_id,
            now=int(time.time()),
            barrier_generation=barrier_generation,
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
        "request_id": decision.get("request_id", ""),
        "scan_id": decision.get("scan_id", ""),
        "barrier_generation": decision.get("barrier_generation", 0),
        "claim_sequence": decision.get("claim_sequence", 0),
    })


@app.post("/release")
@app.post("/release-with-target-cooldown")
def release():
    payload, failure = authenticate()
    if failure:
        return failure
    assert payload is not None

    owner_user_id = str(payload.get("owner_user_id") or "").strip()
    scan_id = str(payload.get("scan_id") or "").strip()
    terminal_status = str(payload.get("terminal_status") or "").strip()
    terminal_cooldown = None
    # Older coordinators ignore extra fields on /release. Giving this handoff
    # its own path makes a mixed deployment fail before releasing admission.
    if request.path == "/release-with-target-cooldown":
        try:
            terminal_cooldown = admission.validate_terminal_cooldown_observation(
                payload, now=int(time.time()), clock_skew_seconds=MAX_CLOCK_SKEW_SECONDS,
            )
        except admission.AdmissionError as error:
            return response_error(error.code, 400)
    elif "target_cooldown" in payload:
        return response_error("target_cooldown_release_endpoint_required", 400)

    def decide(document: dict[str, Any] | None) -> dict[str, Any]:
        decision = admission.decide_release(
            document,
            scan_id=scan_id,
            terminal_status=terminal_status,
            now=int(time.time()),
        )
        if (
            terminal_cooldown is not None
            and decision["outcome"] == admission.OUTCOME_ALREADY_RELEASED
            and (document or {}).get("terminal_status") != terminal_status
        ):
            return {"error": "target_cooldown_claim_conflict"}
        return decision

    try:
        decision = run_in_transaction(owner_user_id, decide, terminal_release=True, terminal_cooldown=terminal_cooldown)
    except admission.AdmissionError as error:
        return response_error(error.code, 400)
    except Exception:
        return response_error("coordinator_unavailable", 503)

    if decision.get("error"):
        if "retry_after_seconds" in decision:
            return target_contact_refusal(decision)
        status = 404 if decision["error"] == admission.ERROR_CLAIM_NOT_FOUND else 409
        return response_error(decision["error"], status)

    result = {
        "success": True,
        "outcome": decision["outcome"],
        "request_id": decision.get("request_id", ""),
        "scan_id": decision.get("scan_id", ""),
        "barrier_generation": decision.get("barrier_generation", 0),
        "claim_sequence": decision.get("claim_sequence", 0),
    }
    if terminal_cooldown is not None:
        result["target_cooldown_outcome"] = decision["target_cooldown_outcome"]
    return jsonify(result)


@app.post("/satisfy-unbound")
def satisfy_unbound():
    """Release one exact expired claim that never acquired a ScanRun id."""
    payload, failure = authenticate()
    if failure:
        return failure
    assert payload is not None
    owner_user_id = str(payload.get("owner_user_id") or "").strip()
    request_id = str(payload.get("request_id") or "").strip()
    if "barrier_generation" not in payload:
        return response_error("invalid_barrier_generation", 400)

    def decide(document: dict[str, Any] | None) -> dict[str, Any]:
        return admission.decide_satisfy_unbound(
            document,
            request_id=request_id,
            barrier_generation=payload.get("barrier_generation"),
            now=int(time.time()),
        )

    try:
        decision = run_in_transaction(owner_user_id, decide)
    except admission.AdmissionError as error:
        return response_error(error.code, 400)
    except Exception:
        return response_error("coordinator_unavailable", 503)
    if decision.get("error"):
        status_code = 404 if decision["error"] == admission.ERROR_CLAIM_NOT_FOUND else 409
        return response_error(decision["error"], status_code)
    return jsonify({
        "success": True,
        "outcome": decision["outcome"],
        "request_id": decision.get("request_id", ""),
        "scan_id": decision.get("scan_id", ""),
        "barrier_generation": decision.get("barrier_generation", 0),
        "claim_sequence": decision.get("claim_sequence", 0),
    })


def _reconciliation_error_status(code: str) -> int:
    if code.startswith("invalid_"):
        return 400
    if code == "reconciliation_invocation_not_found":
        return 404
    return 409


@app.post("/reconciliation/start")
def reconciliation_start():
    """Register one live reconciler before it reads or mutates scan rows."""
    payload, failure = authenticate()
    if failure:
        return failure
    assert payload is not None
    try:
        invocation_id = control.reconciliation_invocation_id(payload.get("invocation_id"))
    except control.ControlError as error:
        return response_error(error.code, 400)

    def decide(
        document: dict[str, Any] | None,
        control_document: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return control.decide_reconciliation_start(
            document,
            control_document,
            invocation_id=invocation_id,
            source_sha=payload.get("source_sha"),
            lease_seconds=payload.get("lease_seconds"),
            now=int(time.time()),
        )

    try:
        decision = run_reconciliation_start_transaction(invocation_id, decide)
    except (control.ControlError, admission.AdmissionError) as error:
        return response_error(error.code, _reconciliation_error_status(error.code))
    except Exception:
        return response_error("coordinator_unavailable", 503)
    if decision.get("error"):
        return response_error(
            decision["error"],
            _reconciliation_error_status(decision["error"]),
        )
    return jsonify({
        "success": True,
        "outcome": decision["outcome"],
        "invocation": decision["invocation"],
    })


@app.post("/reconciliation/finish")
def reconciliation_finish():
    """Finish one exact reconciler, including a lease that elapsed mid-run."""
    payload, failure = authenticate()
    if failure:
        return failure
    assert payload is not None
    try:
        invocation_id = control.reconciliation_invocation_id(payload.get("invocation_id"))
    except control.ControlError as error:
        return response_error(error.code, 400)

    def decide(document: dict[str, Any] | None) -> dict[str, Any]:
        return control.decide_reconciliation_finish(
            document,
            invocation_id=invocation_id,
            source_sha=payload.get("source_sha"),
            outcome=payload.get("outcome"),
            now=int(time.time()),
        )

    try:
        decision = run_reconciliation_finish_transaction(invocation_id, decide)
    except (control.ControlError, admission.AdmissionError) as error:
        return response_error(error.code, _reconciliation_error_status(error.code))
    except Exception:
        return response_error("coordinator_unavailable", 503)
    if decision.get("error"):
        return response_error(
            decision["error"],
            _reconciliation_error_status(decision["error"]),
        )
    return jsonify({
        "success": True,
        "outcome": decision["outcome"],
        "invocation": decision["invocation"],
    })


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
