"""Extended 500 initial ScanRun seed: crash-safe owner-scoped request receipts.

ISOLATED CANDIDATE, OFF BY DEFAULT, NOT ROUTED. Nothing imports this module
from ``service.py``, Base44 functions or any customer path. Every public
operation refuses with ``extended500_seed_disabled`` unless the seeder is
constructed with ``enabled=True`` explicitly.

Problem (see README "Still blocked"): ``classifyExtended500DraftReplay`` in
``src/lib/extended500ScanRunDraft.js`` can only say ``requires_atomic_create``;
"query then create" is not atomic, and Firestore and Base44 do NOT share a
transaction. This module therefore never pretends the two writes are atomic.
Instead a Firestore-style transactional receipt makes the Base44 create call
*single-claim*:

    RESERVED --claim (CAS, one winner)--> CREATE_PENDING --200 + exact proof--> SEEDED
                                              |   \\--definite rejection--> FAILED (terminal)
                                              |
                     lost/ambiguous response, crash, timeout, 5xx
                                              v
                                       CREATE_UNCERTAIN --exact server-owned proof--> SEEDED
    SEEDED --verified terminal ScanRun--> RELEASED (terminal)

Invariants:

* At most one ACTIVE seed receipt per owner (owner slot document), so one
  owner can never hold more than one active Extended 500 seed/scan job.
* The receipt is keyed by sha256(owner, request_id) and binds exactly one
  owner/request/attempt fingerprint. The idempotency key is bound by its own
  owner-scoped index document to exactly one receipt; a different request
  reusing it is refused (``idempotency_key_reused``).
* ``create_scanrun`` is invoked ONLY by the caller whose transaction moved the
  receipt RESERVED -> CREATE_PENDING. Any later retry, restart or concurrent
  submission observes CREATE_PENDING/CREATE_UNCERTAIN and only performs a
  read-only lookup. A lost Base44 response never causes a second create.
* Reconciliation accepts only an exact server-owned ScanRun row (service-role
  lookup port) matching owner, project, ``extended_500`` mode, request id,
  idempotency key, attempt, Access provenance, root target, fingerprint,
  source, robots policy and ``queued`` status. Zero rows leaves the receipt
  pending; more than one row or any mismatch is refused without a write.
* Receipts hold identifiers and digests only: no Access row, Stripe session,
  signing key, proof, bearer token or raw idempotency key.

UNVERIFIED: the real Firestore adapter (``FirestoreSeedStore``) and real
cross-instance Firestore contention behaviour. Tests use a synthetic
optimistic-concurrency transactional fake. No Base44 port implementation is
provided; both ports must be server-owned (service role) when implemented.
"""
from __future__ import annotations

import copy
from datetime import datetime
import hashlib
import re
import time
from typing import Any, Callable, Protocol, TypeVar
from urllib.parse import urlsplit

import core

MODE = core.MODE  # "extended_500"
PLAN = core.PLAN  # "extended500_lifetime"
DRAFT_VERSION = "extended500_scanrun_draft_v1"  # extended500ScanRunDraft.js
SCAN_SOURCE = "extended500_private_candidate"
ACCESS_APP_ID = "6a498732ec779dfaaeab0e53"  # extended500EntitlementIssuer.js
INITIAL_ATTEMPT = 1

RECEIPT_SCHEMA = "extended500_scanrun_seed_receipt_v1"
SLOT_SCHEMA = "extended500_scanrun_seed_owner_slot_v1"
IDEMPOTENCY_SCHEMA = "extended500_scanrun_seed_idempotency_v1"
_RECEIPT_DOMAIN = "extended500_scanrun_seed_receipt_v1"
_IDEMPOTENCY_DOMAIN = "extended500_scanrun_seed_idempotency_v1"

DEFAULT_COLLECTIONS = {
    "receipt": "extended500_seed_receipts",
    "slot": "extended500_seed_owner_slots",
    "idempotency": "extended500_seed_idempotency",
}
# The admission coordinator's own collections (service.py). Never shared.
ADMISSION_COLLECTIONS = frozenset({"extended500_owner_slots", "extended500_request_receipts"})

RESERVED = "reserved"
CREATE_PENDING = "create_pending"
CREATE_UNCERTAIN = "create_uncertain"
SEEDED = "seeded"
FAILED = "failed"
RELEASED = "released"
ACTIVE_STATES = frozenset({RESERVED, CREATE_PENDING, CREATE_UNCERTAIN, SEEDED})
TERMINAL_STATES = frozenset({FAILED, RELEASED})
SLOT_ACTIVE = "active"
SLOT_RELEASED = "released"
# A CREATE_PENDING older than this is relabelled CREATE_UNCERTAIN by a reader.
# Relabelling never creates; the value is an UNVERIFIED operational choice.
DEFAULT_PENDING_STALE_SECONDS = 600

# Exact key set produced by buildExtended500QueuedScanDraft().record.
DRAFT_RECORD_FIELDS = frozenset({
    "project_id", "owner_user_id", "website_url", "submitted_url",
    "normalized_domain", "scan_mode", "status", "scan_source", "request_id",
    "idempotency_key", "request_fingerprint", "attempt_count", "queued_at",
    "respect_robots_txt", "owner_attested_robots_override",
    "admission_access_id", "pages_found", "pages_crawled", "pages_retained",
    "release_gate_eligible", "review_confidence_state",
})
_IDENTITY_FIELDS = (
    "owner_user_id", "project_id", "request_id", "idempotency_ref",
    "attempt_count", "access_id", "website_url", "normalized_domain",
    "request_fingerprint", "scan_mode", "scan_source",
)
RECEIPT_FIELDS = frozenset({
    "schema", "receipt_id", "fingerprint", *_IDENTITY_FIELDS, "state",
    "version", "reserved_at", "updated_at", "create_claimed_at", "scan_id",
    "uncertain_reason", "failure_code", "terminal_status", "released_at",
})
SLOT_FIELDS = frozenset({
    "schema", "owner_user_id", "receipt_id", "request_id", "state", "version", "updated_at",
})
IDEMPOTENCY_FIELDS = frozenset({
    "schema", "owner_user_id", "idempotency_ref", "receipt_id", "request_id",
    "attempt_count", "fingerprint", "bound_at",
})
_CODE = re.compile(r"[a-z0-9_]{1,64}\Z")
_HOST = re.compile(r"[a-z0-9.-]+\Z")
_BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".test", ".invalid", ".example")


class SeedRefused(core.AdmissionRefused):
    """Stable refusal code. Raised before, or instead of, any write."""


class ScanRunCreateRejected(Exception):
    """Port signal: Base44 DEFINITELY did not create a row (e.g. schema 4xx)."""

    def __init__(self, code: str = "create_rejected"):
        self.code = code if isinstance(code, str) and _CODE.fullmatch(code) else "create_rejected"
        super().__init__(self.code)


class ScanRunCreateOutcomeUnknown(Exception):
    """Port signal: request may or may not have committed (timeout, 5xx, reset)."""


class SeedStoreContention(Exception):
    """Store signal: transaction retries exhausted; nothing was committed."""


class SeedTransaction(Protocol):
    """Firestore discipline: every get() happens before any create()/set()."""

    def get(self, collection: str, doc_id: str) -> dict[str, Any] | None: ...
    def create(self, collection: str, doc_id: str, value: dict[str, Any]) -> None: ...
    def set(self, collection: str, doc_id: str, value: dict[str, Any]) -> None: ...


T = TypeVar("T")


class SeedStore(Protocol):
    """Serializable transaction runner. ``fn`` may be retried on contention."""

    def run_in_transaction(self, fn: Callable[[SeedTransaction], T]) -> T: ...


# ---------------------------------------------------------------- identities

def _digest(domain: str, *parts: str) -> str:
    return hashlib.sha256("\n".join((domain, *parts)).encode()).hexdigest()


def seed_receipt_id(owner_user_id: str, request_id: str) -> str:
    return _digest(_RECEIPT_DOMAIN, owner_user_id, request_id)


def idempotency_ref(owner_user_id: str, idempotency_key: str) -> str:
    # Owner-scoped: another owner choosing the same key cannot block this one.
    return _digest(_IDEMPOTENCY_DOMAIN, owner_user_id, idempotency_key)


def _refuse(code: str):
    raise SeedRefused(code)


def _root_site(url: Any) -> str:
    """Python mirror of siteOrigin() in extended500ScanRunDraft.js (stricter)."""
    if not isinstance(url, str) or len(url) > 2048:
        return ""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return ""
    host = (parts.hostname or "").lower()
    if (parts.scheme not in ("http", "https") or parts.username is not None
            or parts.password is not None or port is not None or parts.query
            or parts.fragment or parts.path not in ("", "/")
            or not host or len(host) > 253 or not _HOST.fullmatch(host)
            or "." not in host or host == "localhost" or host.endswith(_BLOCKED_SUFFIXES)
            or host.startswith(".") or host.endswith(".") or ".." in host
            or re.fullmatch(r"[0-9.]+", host) or "--." in host):
        return ""
    site = f"{parts.scheme}://{host}/"
    return site if site == url else ""


def _iso_z(value: Any) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        return datetime.fromisoformat(value).tzinfo is not None
    except ValueError:
        return False


def _validate_paid_access(access: Any, owner: str, access_id: str) -> None:
    """Mirror of paidAccessRecord() minus the e-mail check.

    The JS draft builder already enforced the e-mail binding against the
    authenticated user; this boundary re-checks owner/plan/provenance so a
    foreign or unpaid Access row cannot be bound to a seed receipt.
    """
    if not isinstance(access, dict):
        _refuse("extended500_paid_access_required")
    if access.get("id") != access_id or access.get("owner_user_id") != owner:
        _refuse("foreign_access")
    if access.get("plan_id") != PLAN:
        _refuse("wrong_entitlement_plan")
    session = access.get("stripe_checkout_session_id")
    if (access.get("app_id") != ACCESS_APP_ID or access.get("access_status") != "active"
            or access.get("has_full_access") is not True
            or access.get("grant_source") != "stripe_checkout"
            or not isinstance(session, str) or not core.IDENTIFIER.fullmatch(session)
            or not _iso_z(access.get("paid_at"))):
        _refuse("extended500_paid_access_required")


class SeedRequest:
    """Canonical, validated seed request. ``record`` goes to Base44 create."""

    __slots__ = ("identity", "record", "receipt_id", "fingerprint")

    def __init__(self, identity: dict[str, Any], record: dict[str, Any]):
        self.identity = identity
        self.record = record
        self.receipt_id = seed_receipt_id(identity["owner_user_id"], identity["request_id"])
        self.fingerprint = core.fingerprint(identity)

    @property
    def owner_user_id(self) -> str:
        return self.identity["owner_user_id"]

    @property
    def request_id(self) -> str:
        return self.identity["request_id"]


def canonical_seed_request(draft: Any, access: Any) -> SeedRequest:
    """Validate a buildExtended500QueuedScanDraft() result + server-read Access.

    Both inputs MUST come from service-role reads in the caller; nothing here
    is customer-electable. Mode is checked first so Standard 150 / legacy
    modes are refused with ``invalid_scan_mode`` regardless of other fields.
    """
    if (not isinstance(draft, dict) or not set(draft) <= {"ok", "draft_version", "record"}
            or draft.get("ok", True) is not True or draft.get("draft_version") != DRAFT_VERSION
            or not isinstance(draft.get("record"), dict)):
        _refuse("invalid_scanrun_draft")
    record = draft["record"]
    if record.get("scan_mode") != MODE:
        _refuse("invalid_scan_mode")
    if set(record) != DRAFT_RECORD_FIELDS:
        _refuse("scanrun_draft_shape_invalid")
    owner = core.required_identifier(record["owner_user_id"], "owner_user_id")
    project = core.required_identifier(record["project_id"], "project_id")
    request_id = core.required_identifier(record["request_id"], "request_id")
    idem = core.required_identifier(record["idempotency_key"], "idempotency_key")
    access_id = core.required_identifier(record["admission_access_id"], "access_id")
    if core.safe_attempt(record["attempt_count"]) != INITIAL_ATTEMPT:
        _refuse("initial_seed_attempt_required")
    if record["status"] != "queued":
        _refuse("scanrun_draft_status_invalid")
    if record["scan_source"] != SCAN_SOURCE:
        _refuse("scanrun_draft_source_invalid")
    if record["respect_robots_txt"] is not True or record["owner_attested_robots_override"] is not False:
        _refuse("scanrun_draft_robots_invalid")
    for counter in ("pages_found", "pages_crawled", "pages_retained"):
        if type(record[counter]) is not int or record[counter] != 0:
            _refuse("scanrun_draft_counters_invalid")
    if record["release_gate_eligible"] is not False or record["review_confidence_state"] != "not_reviewed":
        _refuse("scanrun_draft_authority_invalid")
    if not _iso_z(record["queued_at"]):
        _refuse("scanrun_draft_time_invalid")
    site = _root_site(record["website_url"])
    host = urlsplit(site).hostname if site else ""
    if (not site or record["submitted_url"] != site
            or record["normalized_domain"] != host.removeprefix("www.")
            or record["request_fingerprint"] != f"{MODE}|{site}|root|respect_robots_txt"):
        _refuse("scanrun_draft_target_invalid")
    _validate_paid_access(access, owner, access_id)
    identity = {
        "owner_user_id": owner,
        "project_id": project,
        "request_id": request_id,
        "idempotency_ref": idempotency_ref(owner, idem),
        "attempt_count": INITIAL_ATTEMPT,
        "access_id": access_id,
        "website_url": site,
        "normalized_domain": record["normalized_domain"],
        "request_fingerprint": record["request_fingerprint"],
        "scan_mode": MODE,
        "scan_source": SCAN_SOURCE,
    }
    return SeedRequest(identity, copy.deepcopy(record))


# ------------------------------------------------------------- proof checks

def validate_scanrun_proof(receipt: dict[str, Any], row: Any) -> str:
    """Return the ScanRun id iff ``row`` is the exact ScanRun this receipt seeds.

    ``row`` must come from a server-owned (service-role) Base44 read or the
    create response itself. Every check is exact and type-strict; a Python
    ``True`` or ``1.0`` never stands in for attempt 1.
    """
    if not isinstance(row, dict):
        _refuse("scanrun_proof_invalid")
    scan_id = row.get("id")
    if not isinstance(scan_id, str) or not core.IDENTIFIER.fullmatch(scan_id):
        _refuse("scanrun_proof_id_invalid")
    if row.get("owner_user_id") != receipt["owner_user_id"]:
        _refuse("scanrun_proof_owner_mismatch")
    if row.get("project_id") != receipt["project_id"]:
        _refuse("scanrun_proof_project_mismatch")
    if row.get("scan_mode") != MODE:
        _refuse("scanrun_proof_mode_mismatch")
    if row.get("request_id") != receipt["request_id"]:
        _refuse("scanrun_proof_request_mismatch")
    key = row.get("idempotency_key")
    if (not isinstance(key, str) or not core.IDENTIFIER.fullmatch(key)
            or idempotency_ref(receipt["owner_user_id"], key) != receipt["idempotency_ref"]):
        _refuse("scanrun_proof_idempotency_mismatch")
    if type(row.get("attempt_count")) is not int or row["attempt_count"] != receipt["attempt_count"]:
        _refuse("scanrun_proof_attempt_mismatch")
    if row.get("admission_access_id") != receipt["access_id"]:
        _refuse("scanrun_proof_access_mismatch")
    if (row.get("website_url") != receipt["website_url"]
            or row.get("normalized_domain") != receipt["normalized_domain"]
            or row.get("request_fingerprint") != receipt["request_fingerprint"]
            or row.get("path_prefix") not in (None, "")):
        _refuse("scanrun_proof_target_mismatch")
    if row.get("scan_source") != receipt["scan_source"]:
        _refuse("scanrun_proof_source_mismatch")
    if row.get("respect_robots_txt") is not True or row.get("owner_attested_robots_override") is not False:
        _refuse("scanrun_proof_robots_mismatch")
    if row.get("scan_id") not in (None, "", scan_id):
        _refuse("scanrun_proof_scan_id_mismatch")
    if row.get("status") != "queued":
        _refuse("scanrun_proof_status_invalid")
    return scan_id


# ------------------------------------------------------- pure decisions

def _write(kind: str, op: str, doc_id: str, value: dict[str, Any]) -> tuple[str, str, str, dict[str, Any]]:
    expected = {"receipt": RECEIPT_FIELDS, "slot": SLOT_FIELDS, "idempotency": IDEMPOTENCY_FIELDS}[kind]
    if set(value) != expected:  # allowlist: nothing credential-like can be persisted
        raise AssertionError(f"seed {kind} field allowlist violated")
    return (kind, op, doc_id, value)


def _bound(receipt: Any, req: SeedRequest) -> dict[str, Any]:
    if receipt is None:
        _refuse("seed_receipt_not_found")
    if (not isinstance(receipt, dict) or receipt.get("schema") != RECEIPT_SCHEMA
            or receipt.get("receipt_id") != req.receipt_id
            or receipt.get("fingerprint") != req.fingerprint):
        _refuse("request_replay_conflict")
    return receipt


def _slot_holds(slot: Any, receipt: dict[str, Any]) -> bool:
    return (isinstance(slot, dict) and slot.get("schema") == SLOT_SCHEMA
            and slot.get("receipt_id") == receipt["receipt_id"]
            and slot.get("owner_user_id") == receipt["owner_user_id"]
            and slot.get("state") == SLOT_ACTIVE)


def _require_slot(slot: Any, receipt: dict[str, Any]) -> None:
    if not _slot_holds(slot, receipt):
        _refuse("reservation_integrity_mismatch")


def _advance(receipt: dict[str, Any], state: str, now: int, **fields: Any) -> dict[str, Any]:
    return {**receipt, **fields, "state": state, "version": receipt["version"] + 1, "updated_at": now}


def _release_slot(slot: dict[str, Any], now: int) -> dict[str, Any]:
    return {**slot, "state": SLOT_RELEASED, "version": slot["version"] + 1, "updated_at": now}


def _refuse_inactive(receipt: dict[str, Any]) -> None:
    if receipt["state"] in TERMINAL_STATES:
        _refuse("terminal_receipt_replay")
    if receipt["state"] not in ACTIVE_STATES:
        _refuse("receipt_state_invalid")


def decide_seed_reservation(slot, receipt, idem, req: SeedRequest, *, now: int) -> dict[str, Any]:
    if receipt is not None:
        receipt = _bound(receipt, req)
        if (not isinstance(idem, dict) or idem.get("receipt_id") != req.receipt_id
                or idem.get("fingerprint") != req.fingerprint):
            _refuse("idempotency_binding_mismatch")
        _refuse_inactive(receipt)
        _require_slot(slot, receipt)
        outcome = {
            SEEDED: "seeded_replay", RESERVED: "resume_reserved",
            CREATE_PENDING: "create_pending", CREATE_UNCERTAIN: "create_uncertain",
        }[receipt["state"]]
        return {"outcome": outcome, "receipt": receipt, "writes": []}
    if idem is not None:
        # Key already bound to another owner/request/attempt (or orphaned).
        _refuse("idempotency_key_reused")
    if isinstance(slot, dict) and slot.get("state") == SLOT_ACTIVE:
        _refuse("owner_slot_busy")
    if slot is not None and (not isinstance(slot, dict) or slot.get("state") != SLOT_RELEASED
                             or slot.get("schema") != SLOT_SCHEMA):
        _refuse("owner_slot_integrity_invalid")
    owner, request_id = req.owner_user_id, req.request_id
    new_receipt = {
        "schema": RECEIPT_SCHEMA, "receipt_id": req.receipt_id, "fingerprint": req.fingerprint,
        **req.identity, "state": RESERVED, "version": 1, "reserved_at": now, "updated_at": now,
        "create_claimed_at": None, "scan_id": None, "uncertain_reason": None,
        "failure_code": None, "terminal_status": None, "released_at": None,
    }
    new_slot = {
        "schema": SLOT_SCHEMA, "owner_user_id": owner, "receipt_id": req.receipt_id,
        "request_id": request_id, "state": SLOT_ACTIVE,
        "version": (slot["version"] + 1) if isinstance(slot, dict) else 1, "updated_at": now,
    }
    new_idem = {
        "schema": IDEMPOTENCY_SCHEMA, "owner_user_id": owner,
        "idempotency_ref": req.identity["idempotency_ref"], "receipt_id": req.receipt_id,
        "request_id": request_id, "attempt_count": req.identity["attempt_count"],
        "fingerprint": req.fingerprint, "bound_at": now,
    }
    return {
        "outcome": "reserved", "receipt": new_receipt,
        "writes": [
            _write("receipt", "create", req.receipt_id, new_receipt),
            _write("idempotency", "create", req.identity["idempotency_ref"], new_idem),
            _write("slot", "set", owner, new_slot),
        ],
    }


def decide_create_claim(slot, receipt, req: SeedRequest, *, now: int) -> dict[str, Any]:
    """CAS RESERVED -> CREATE_PENDING. Only the committed winner may call create."""
    receipt = _bound(receipt, req)
    _refuse_inactive(receipt)
    _require_slot(slot, receipt)
    if receipt["state"] != RESERVED:
        return {"outcome": "claim_lost", "receipt": receipt, "writes": []}
    claimed = _advance(receipt, CREATE_PENDING, now, create_claimed_at=now)
    return {"outcome": "claimed", "receipt": claimed,
            "writes": [_write("receipt", "set", req.receipt_id, claimed)]}


def decide_create_confirmed(slot, receipt, req: SeedRequest, row: Any, *, now: int) -> dict[str, Any]:
    receipt = _bound(receipt, req)
    _refuse_inactive(receipt)
    if receipt["state"] == SEEDED:
        if validate_scanrun_proof(receipt, row) != receipt["scan_id"]:
            _refuse("seeded_scan_conflict")
        return {"outcome": "already_seeded", "receipt": receipt, "writes": []}
    if receipt["state"] not in (CREATE_PENDING, CREATE_UNCERTAIN):
        _refuse("create_not_claimed")
    _require_slot(slot, receipt)
    scan_id = validate_scanrun_proof(receipt, row)
    seeded = _advance(receipt, SEEDED, now, scan_id=scan_id)
    return {"outcome": "seeded", "receipt": seeded,
            "writes": [_write("receipt", "set", req.receipt_id, seeded)]}


def decide_create_uncertain(slot, receipt, req: SeedRequest, reason: str, *, now: int) -> dict[str, Any]:
    receipt = _bound(receipt, req)
    _refuse_inactive(receipt)
    if receipt["state"] in (CREATE_UNCERTAIN, SEEDED):
        return {"outcome": "unchanged", "receipt": receipt, "writes": []}
    if receipt["state"] != CREATE_PENDING:
        _refuse("create_not_claimed")
    _require_slot(slot, receipt)
    reason = reason if isinstance(reason, str) and _CODE.fullmatch(reason) else "create_outcome_unknown"
    uncertain = _advance(receipt, CREATE_UNCERTAIN, now, uncertain_reason=reason)
    return {"outcome": "uncertain", "receipt": uncertain,
            "writes": [_write("receipt", "set", req.receipt_id, uncertain)]}


def decide_create_rejected(slot, receipt, req: SeedRequest, code: str, *, now: int) -> dict[str, Any]:
    """Definite Base44 rejection of the single claimed create -> FAILED tombstone.

    Only valid from CREATE_PENDING. Once a receipt is UNCERTAIN (another
    reader declared the claim stale) only an exact proof may resolve it.
    """
    receipt = _bound(receipt, req)
    _refuse_inactive(receipt)
    if receipt["state"] in (CREATE_UNCERTAIN, SEEDED):
        return {"outcome": "unchanged", "receipt": receipt, "writes": []}
    if receipt["state"] != CREATE_PENDING:
        _refuse("create_not_claimed")
    _require_slot(slot, receipt)
    failed = _advance(receipt, FAILED, now, failure_code=code)
    return {"outcome": "failed", "receipt": failed, "writes": [
        _write("receipt", "set", req.receipt_id, failed),
        _write("slot", "set", req.owner_user_id, _release_slot(slot, now)),
    ]}


def decide_reconcile(slot, receipt, req: SeedRequest, rows: Any, *, now: int,
                     stale_after_seconds: int = DEFAULT_PENDING_STALE_SECONDS) -> dict[str, Any]:
    """Resolve a pending/uncertain receipt from a server-owned owner+request lookup."""
    receipt = _bound(receipt, req)
    _refuse_inactive(receipt)
    if receipt["state"] == SEEDED:
        return {"outcome": "already_seeded", "receipt": receipt, "writes": []}
    if receipt["state"] == RESERVED:
        _refuse("create_not_claimed")
    _require_slot(slot, receipt)
    if not isinstance(rows, list):
        _refuse("scanrun_lookup_invalid")
    if len(rows) > 1:
        _refuse("duplicate_scanrun_rows")
    if len(rows) == 1:
        scan_id = validate_scanrun_proof(receipt, rows[0])
        seeded = _advance(receipt, SEEDED, now, scan_id=scan_id)
        return {"outcome": "reconciled", "receipt": seeded,
                "writes": [_write("receipt", "set", req.receipt_id, seeded)]}
    claimed_at = receipt.get("create_claimed_at")
    if (receipt["state"] == CREATE_PENDING and isinstance(claimed_at, int)
            and now - claimed_at >= stale_after_seconds):
        uncertain = _advance(receipt, CREATE_UNCERTAIN, now, uncertain_reason="create_claim_stale")
        return {"outcome": "pending", "receipt": uncertain,
                "writes": [_write("receipt", "set", req.receipt_id, uncertain)]}
    return {"outcome": "pending", "receipt": receipt, "writes": []}


def decide_terminal_release(slot, receipt, *, owner_user_id: str, request_id: str, scan_id: str,
                            terminal_status: str, verified_terminal: bool, now: int) -> dict[str, Any]:
    """SEEDED -> RELEASED after a separately VERIFIED terminal ScanRun.

    ``verified_terminal`` must be established by a trusted server reader
    (as for core.decide_release); never from customer input.
    """
    if terminal_status not in core.TERMINALS or verified_terminal is not True:
        _refuse("verified_terminal_required")
    if (not isinstance(receipt, dict) or receipt.get("schema") != RECEIPT_SCHEMA
            or receipt.get("receipt_id") != seed_receipt_id(owner_user_id, request_id)
            or receipt.get("owner_user_id") != owner_user_id or receipt.get("request_id") != request_id):
        _refuse("seed_receipt_not_found")
    if receipt.get("scan_id") != scan_id:
        _refuse("release_identity_mismatch")
    if receipt["state"] == RELEASED:
        if receipt.get("terminal_status") == terminal_status:
            return {"outcome": "already_released", "receipt": receipt, "writes": []}
        _refuse("terminal_conflict")
    if receipt["state"] != SEEDED:
        _refuse("release_requires_seeded")
    if not _slot_holds(slot, receipt):
        _refuse("owner_slot_mismatch")
    released = _advance(receipt, RELEASED, now, terminal_status=terminal_status, released_at=now)
    return {"outcome": "released", "receipt": released, "writes": [
        _write("receipt", "set", receipt["receipt_id"], released),
        _write("slot", "set", owner_user_id, _release_slot(slot, now)),
    ]}


# ------------------------------------------------------------ orchestration

class Extended500ScanRunSeeder:
    """Adapter boundary: injectable transactional store + Base44 ports.

    ``create_scanrun(record) -> row``: service-role ``ScanRun.create``. Must
    raise ``ScanRunCreateRejected`` ONLY when Base44 definitely wrote nothing;
    every other failure is treated as an unknown outcome.
    ``find_scanruns(owner_user_id, request_id) -> list[row]``: service-role
    ``ScanRun.filter({owner_user_id, request_id})`` returning ALL matches.
    """

    def __init__(self, store: SeedStore, create_scanrun: Callable[[dict[str, Any]], Any],
                 find_scanruns: Callable[[str, str], Any], *, enabled: bool = False,
                 clock: Callable[[], float] = time.time,
                 pending_stale_seconds: int = DEFAULT_PENDING_STALE_SECONDS,
                 collections: dict[str, str] | None = None):
        names = {**DEFAULT_COLLECTIONS, **(collections or {})}
        if (set(names) != set(DEFAULT_COLLECTIONS) or len(set(names.values())) != 3
                or set(names.values()) & ADMISSION_COLLECTIONS
                or not all(isinstance(v, str) and core.IDENTIFIER.fullmatch(v) for v in names.values())):
            raise ValueError("Extended 500 seed collections must be distinct and isolated")
        if type(pending_stale_seconds) is not int or pending_stale_seconds < 1:
            raise ValueError("pending_stale_seconds must be a positive integer")
        self._enabled = enabled is True
        self._store = store
        self._create = create_scanrun
        self._find = find_scanruns
        self._clock = clock
        self._stale = pending_stale_seconds
        self._names = names

    # -- plumbing
    def _now(self) -> int:
        return int(self._clock())

    def _require_enabled(self) -> None:
        if not self._enabled:
            _refuse("extended500_seed_disabled")

    def _transact(self, req: SeedRequest, decide: Callable[..., dict[str, Any]],
                  *, idempotency: bool = False) -> dict[str, Any]:
        names = self._names

        def run(tx: SeedTransaction) -> dict[str, Any]:
            slot = tx.get(names["slot"], req.owner_user_id)
            receipt = tx.get(names["receipt"], req.receipt_id)
            idem = tx.get(names["idempotency"], req.identity["idempotency_ref"]) if idempotency else None
            decision = decide(slot, receipt, idem) if idempotency else decide(slot, receipt)
            for kind, op, doc_id, value in decision["writes"]:
                getattr(tx, op)(names[kind], doc_id, copy.deepcopy(value))
            return decision

        try:
            return self._store.run_in_transaction(run)
        except SeedRefused:
            raise
        except SeedStoreContention:
            raise SeedRefused("seed_store_contention_retry") from None
        except Exception:
            # Commit outcome unknown: callers never infer a create claim from it.
            raise SeedRefused("seed_store_unavailable") from None

    @staticmethod
    def _result(outcome: str, receipt: dict[str, Any], *, create_invoked: bool) -> dict[str, Any]:
        return {
            "outcome": outcome, "receipt_id": receipt["receipt_id"], "state": receipt["state"],
            "scan_id": receipt.get("scan_id"), "create_invoked": create_invoked,
        }

    def _pending(self, receipt: dict[str, Any], *, create_invoked: bool) -> dict[str, Any]:
        outcome = "create_in_progress" if receipt["state"] == CREATE_PENDING else "pending_reconciliation"
        return self._result(outcome, receipt, create_invoked=create_invoked)

    # -- public operations
    def submit(self, draft: Any, access: Any) -> dict[str, Any]:
        self._require_enabled()
        req = canonical_seed_request(draft, access)
        now = self._now()
        reserved = self._transact(
            req, lambda s, r, i: decide_seed_reservation(s, r, i, req, now=now), idempotency=True,
        )
        if reserved["outcome"] == "seeded_replay":
            return self._result("seeded_replay", reserved["receipt"], create_invoked=False)
        if reserved["outcome"] in ("create_pending", "create_uncertain"):
            return self._reconcile(req)
        claim = self._transact(req, lambda s, r: decide_create_claim(s, r, req, now=self._now()))
        if claim["outcome"] != "claimed":
            return self._reconcile(req)
        return self._invoke_single_create(req)

    def _invoke_single_create(self, req: SeedRequest) -> dict[str, Any]:
        # Reached at most once per receipt: only after OUR committed claim.
        try:
            row = self._create(copy.deepcopy(req.record))
        except ScanRunCreateRejected as exc:
            decision = self._transact(
                req, lambda s, r: decide_create_rejected(s, r, req, exc.code, now=self._now()),
            )
            if decision["outcome"] == "failed":
                return self._result("failed", decision["receipt"], create_invoked=True)
            return self._pending(decision["receipt"], create_invoked=True)
        except Exception:
            decision = self._transact(
                req, lambda s, r: decide_create_uncertain(s, r, req, "create_outcome_unknown", now=self._now()),
            )
            return self._pending(decision["receipt"], create_invoked=True)
        row = copy.deepcopy(row)
        try:
            decision = self._transact(
                req, lambda s, r: decide_create_confirmed(s, r, req, row, now=self._now()),
            )
        except SeedRefused as exc:
            if not exc.code.startswith("scanrun_proof_"):
                raise
            # Base44 answered with a row that is not our exact ScanRun.
            decision = self._transact(
                req, lambda s, r: decide_create_uncertain(s, r, req, "created_row_proof_mismatch", now=self._now()),
            )
            return self._pending(decision["receipt"], create_invoked=True)
        return self._result("created", decision["receipt"], create_invoked=True)

    def reconcile(self, draft: Any, access: Any) -> dict[str, Any]:
        self._require_enabled()
        return self._reconcile(canonical_seed_request(draft, access))

    def _reconcile(self, req: SeedRequest) -> dict[str, Any]:
        try:
            rows = self._find(req.owner_user_id, req.request_id)
        except Exception:
            raise SeedRefused("scanrun_lookup_unavailable") from None
        rows = copy.deepcopy(rows)
        decision = self._transact(
            req, lambda s, r: decide_reconcile(
                s, r, req, rows, now=self._now(), stale_after_seconds=self._stale),
        )
        receipt = decision["receipt"]
        if decision["outcome"] == "already_seeded":
            return self._result("seeded_replay", receipt, create_invoked=False)
        if decision["outcome"] == "reconciled":
            return self._result("reconciled", receipt, create_invoked=False)
        return self._pending(receipt, create_invoked=False)

    def release_after_verified_terminal(self, *, owner_user_id: str, request_id: str, scan_id: str,
                                        terminal_status: str, verified_terminal: bool) -> dict[str, Any]:
        self._require_enabled()
        owner = core.required_identifier(owner_user_id, "owner_user_id")
        request = core.required_identifier(request_id, "request_id")
        rid = seed_receipt_id(owner, request)
        names, now = self._names, self._now()

        def run(tx: SeedTransaction) -> dict[str, Any]:
            slot = tx.get(names["slot"], owner)
            receipt = tx.get(names["receipt"], rid)
            decision = decide_terminal_release(
                slot, receipt, owner_user_id=owner, request_id=request, scan_id=scan_id,
                terminal_status=terminal_status, verified_terminal=verified_terminal, now=now,
            )
            for kind, op, doc_id, value in decision["writes"]:
                getattr(tx, op)(names[kind], doc_id, copy.deepcopy(value))
            return decision

        try:
            decision = self._store.run_in_transaction(run)
        except SeedRefused:
            raise
        except Exception:
            raise SeedRefused("seed_store_unavailable") from None
        return self._result(decision["outcome"], decision["receipt"], create_invoked=False)


# ------------------------------------------------------ Firestore adapter

class FirestoreSeedStore:
    """Thin google-cloud-firestore mapping. UNVERIFIED against real Firestore.

    ``client`` is a ``firestore.Client``; ``transactional`` is
    ``firestore.transactional``. Injected so this module never imports
    Google Cloud libraries and stays inert unless an operator composes it.
    """

    def __init__(self, client: Any, transactional: Callable[[Callable[..., T]], Callable[..., T]],
                 *, max_attempts: int = 5):
        self._client = client
        self._transactional = transactional
        self._max_attempts = max_attempts

    def run_in_transaction(self, fn: Callable[[SeedTransaction], T]) -> T:
        client = self._client

        @self._transactional
        def apply(transaction):
            return fn(_FirestoreTransactionView(client, transaction))

        return apply(client.transaction(max_attempts=self._max_attempts))


class _FirestoreTransactionView:
    def __init__(self, client: Any, transaction: Any):
        self._client = client
        self._transaction = transaction
        self._wrote = False

    def _ref(self, collection: str, doc_id: str):
        return self._client.collection(collection).document(doc_id)

    def get(self, collection: str, doc_id: str) -> dict[str, Any] | None:
        if self._wrote:
            raise RuntimeError("Firestore transactions require all reads before writes")
        snapshot = self._ref(collection, doc_id).get(transaction=self._transaction)
        return snapshot.to_dict() if snapshot.exists else None

    def create(self, collection: str, doc_id: str, value: dict[str, Any]) -> None:
        self._wrote = True
        self._transaction.create(self._ref(collection, doc_id), value)

    def set(self, collection: str, doc_id: str, value: dict[str, Any]) -> None:
        self._wrote = True
        self._transaction.set(self._ref(collection, doc_id), value)

