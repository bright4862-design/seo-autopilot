"""Read-only, fail-closed Extended 500 Cloud Tasks pickup authorization.

NOT a worker route or an execution permit. The result `ready_for_atomic_claim`
requires a *separate* Firestore transaction that atomically creates a unique
pickup-claim document before any crawl. An ordinary read cannot fence two
concurrent Cloud Tasks deliveries. The caller must independently verify Cloud
Run IAM/OIDC, private Cloud Tasks queue identity and service-role read sources.

All inputs from the task body are untrusted, including owner and paid flags.
The signed issuance grant is checked for integrity but is allowed to expire
while queued; authorization is freshly re-derived from server-owned records.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import re
from typing import Any, Protocol
from urllib.parse import urlsplit

from .authority_seal import create_authority_seal

MODE = "extended_500"
PLAN = "extended500_lifetime"
APP_ID = "6a498732ec779dfaaeab0e53"
SLOT_SCHEMA = "extended500_owner_slot_v1"
RECEIPT_SCHEMA = "extended500_request_receipt_v1"
GRANT_VERSION = "extended500_preflight_grant_v1"
GRANT_AUDIENCE = "fixlist_extended500_worker"
PICKUP_CLAIM_SCHEMA = "extended500_pickup_claim_v1"
ACTIVE_DISPATCH_STATES = frozenset({"enqueued", "dispatch_unknown"})
IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
HEX64 = re.compile(r"[a-f0-9]{64}\Z")
QUEUE = re.compile(r"projects/[A-Za-z0-9_-]+/locations/[A-Za-z0-9_-]+/queues/extended500-[A-Za-z0-9_-]+\Z")
TASK_FIELDS = frozenset({
    "scan_mode", "scan_id", "request_id", "idempotency_key", "project_id",
    "owner_user_id", "attempt_count", "website_url", "path_prefix",
    "respect_robots_txt", "owner_attested_robots_override", "signed_grant",
})
GRANT_FIELDS = frozenset({
    "version", "audience", "canonical_mode", "owner_user_id", "scan_id",
    "project_id", "request_id", "idempotency_key", "attempt_count",
    "website_url", "path_prefix", "respect_robots_txt",
    "owner_attested_robots_override", "issued_at", "expires_at", "proof",
})
IDENTITIES = ("scan_id", "owner_user_id", "project_id", "request_id", "idempotency_key")


class PickupReader(Protocol):
    """Every method must be a fresh, authenticated service-owned read.

    Access rows MUST be all matching owner rows (including revoked/duplicate
    Extended 500 rows), not a client-filtered active-only projection. Slot and
    receipt MUST come from the isolated coordinator Firestore collections.
    """
    def read_scanrun(self, scan_id: str) -> dict[str, Any] | None: ...
    def read_project(self, project_id: str) -> dict[str, Any] | None: ...
    def read_access_rows(self, owner_id: str) -> list[dict[str, Any]]: ...
    def read_owner_slot(self, owner_id: str) -> dict[str, Any] | None: ...
    def read_request_receipt(self, receipt_id: str) -> dict[str, Any] | None: ...
    def read_pickup_claim(self, receipt_id: str) -> dict[str, Any] | None: ...


@dataclass(frozen=True)
class PickupVerdict:
    code: str
    ready_for_atomic_claim: bool = False
    # Deliberately never true: this module cannot commit a CAS claim.
    execution_allowed: bool = False
    receipt_id: str = ""
    task_name: str = ""


def _deny(code: str) -> PickupVerdict:
    return PickupVerdict(code)


def _id(value: Any) -> bool:
    return isinstance(value, str) and bool(IDENTIFIER.fullmatch(value))


def _attempt(value: Any) -> bool:
    return type(value) is int and 1 <= value <= 100_000


def _root_url(value: Any) -> str:
    """Only a canonical, public DNS root URL is admitted by this R4 lane."""
    if not isinstance(value, str) or len(value) > 2048:
        return ""
    try:
        p = urlsplit(value)
        host = (p.hostname or "").lower().rstrip(".")
        if (p.scheme not in ("http", "https") or p.netloc != host
                or p.username or p.password or p.port is not None
                or p.query or p.fragment or p.path not in ("", "/")
                or len(host) > 253 or "." not in host
                or not re.fullmatch(r"[a-z0-9.-]+", host)
                or host.startswith(".") or host.endswith(".") or ".." in host
                or re.fullmatch(r"[0-9.]+", host)
                or host.endswith((".localhost", ".local", ".internal", ".test", ".invalid", ".example"))):
            return ""
        return f"{p.scheme}://{host}/"
    except ValueError:
        return ""


def _time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        moment = datetime.fromisoformat(value[:-1] + "+00:00")
        return moment if moment.tzinfo else None
    except ValueError:
        return None


def _receipt_id(owner: str, request: str) -> str:
    return hashlib.sha256(f"{owner}\n{request}".encode()).hexdigest()


def _fingerprint(scan: dict[str, Any]) -> str:
    # Byte-identical to extended500-admission/core.py fingerprint(canonical_request).
    fields = ("owner_user_id", "scan_id", "project_id", "request_id",
              "idempotency_key", "access_id", "attempt_count")
    claim = {k: scan["admission_access_id"] if k == "access_id" else scan["id"]
             if k == "scan_id" else scan[k] for k in fields}
    return hashlib.sha256(json.dumps(claim, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode()).hexdigest()


def _grant_check(task: dict[str, Any], key: str, now: datetime) -> str:
    grant = task.get("signed_grant")
    if not isinstance(grant, dict) or set(grant) != GRANT_FIELDS:
        return "grant_shape_invalid"
    if grant.get("version") != GRANT_VERSION or grant.get("audience") != GRANT_AUDIENCE or grant.get("canonical_mode") != MODE:
        return "grant_context_invalid"
    if not isinstance(key, str) or len(key) < 32:
        return "grant_signing_unavailable"
    proof = grant.get("proof")
    if not isinstance(proof, str) or not HEX64.fullmatch(proof):
        return "grant_signature_invalid"
    try:
        expected = create_authority_seal({k: v for k, v in grant.items() if k != "proof"}, key)
    except (ValueError, TypeError):
        return "grant_signature_invalid"
    if not hmac.compare_digest(proof, expected):
        return "grant_signature_invalid"
    for k in IDENTITIES + ("attempt_count", "website_url", "path_prefix",
                           "respect_robots_txt", "owner_attested_robots_override"):
        if type(grant.get(k)) is not type(task.get(k)) or grant.get(k) != task.get(k):
            return "grant_identity_mismatch"
    issued, expires = _time(grant.get("issued_at")), _time(grant.get("expires_at"))
    if not issued or not expires or issued > now or not timedelta(0) < expires - issued <= timedelta(seconds=300):
        return "grant_time_invalid"
    # Expired issuance proof is not a durable authorization. Accept its signed
    # identity ONLY after fresh reads; deny tasks older than seven days.
    if now - issued > timedelta(days=7):
        return "task_age_exceeded"
    return ""


def authorize_extended500_pickup(
    task: dict[str, Any], reader: PickupReader, *,
    signing_key: str, queue_path: str, trusted_task_name: str,
    verified_private_invoker: bool = False, feature_enabled: bool = False,
    now: datetime | None = None,
) -> PickupVerdict:
    """Read-only eligibility check; ALWAYS requires a subsequent atomic CAS.

    The invoker/queue identity must be verified by private IAM/OIDC middleware,
    NOT inferred from HTTP task headers. `trusted_task_name` must be supplied
    only after that boundary. No call to this function may launch a crawl.
    """
    if feature_enabled is not True:
        return _deny("pickup_disabled")
    if verified_private_invoker is not True:
        return _deny("private_invoker_required")
    if not isinstance(queue_path, str) or not QUEUE.fullmatch(queue_path):
        return _deny("dedicated_queue_required")
    if not isinstance(task, dict) or set(task) != TASK_FIELDS:
        return _deny("task_shape_invalid")
    if task.get("scan_mode") != MODE:
        return _deny("mode_invalid")
    if not all(_id(task.get(k)) for k in IDENTITIES) or not _attempt(task.get("attempt_count")):
        return _deny("task_identity_invalid")
    if task["idempotency_key"] != task["request_id"]:
        return _deny("request_idempotency_mismatch")
    if task.get("path_prefix") is not None or task.get("respect_robots_txt") is not True or task.get("owner_attested_robots_override") is not False:
        return _deny("scope_or_robots_invalid")
    target = _root_url(task.get("website_url"))
    if not target or target != task["website_url"]:
        return _deny("target_invalid")
    instant = now if now is not None else datetime.now(timezone.utc)
    if not isinstance(instant, datetime) or instant.tzinfo is None:
        return _deny("clock_invalid")
    instant = instant.astimezone(timezone.utc)
    grant_error = _grant_check(task, signing_key, instant)
    if grant_error:
        return _deny(grant_error)

    # Task-supplied identities are used only as lookup hints. All authority is
    # checked against independently fetched durable service-owned records.
    try:
        scan = reader.read_scanrun(task["scan_id"])
        if not isinstance(scan, dict) or scan.get("id") != task["scan_id"]:
            return _deny("scan_missing")
        if scan.get("scan_mode") != MODE or scan.get("status") != "queued":
            return _deny("scan_not_queued_extended500")
        for k in IDENTITIES:
            stored = scan.get("id") if k == "scan_id" else scan.get(k)
            if not _id(stored) or stored != task[k]:
                return _deny("scan_identity_mismatch")
        if not _attempt(scan.get("attempt_count")) or scan["attempt_count"] != task["attempt_count"]:
            return _deny("superseded_attempt")
        if not _id(scan.get("admission_access_id")):
            return _deny("access_provenance_missing")
        if (scan.get("scan_source") != "extended500_private_candidate"
                or scan.get("path_prefix") not in (None, "")
                or scan.get("scope_type") not in (None, "")
                or scan.get("respect_robots_txt") is not True
                or scan.get("owner_attested_robots_override") is not False):
            return _deny("frozen_scope_invalid")
        if (_root_url(scan.get("website_url")) != target
                or scan.get("website_url") != target
                or scan.get("submitted_url") != target
                or scan.get("normalized_domain") != urlsplit(target).hostname.removeprefix("www.")
                or scan.get("request_fingerprint") != f"{MODE}|{target}|root|respect_robots_txt"):
            return _deny("frozen_target_mismatch")
        project = reader.read_project(scan["project_id"])
        if (not isinstance(project, dict) or project.get("id") != scan["project_id"]
                or project.get("owner_user_id") != scan["owner_user_id"]
                or project.get("status") not in ("setup", "active")
                or _root_url(project.get("website_url")) != target
                or project.get("website_url") != target):
            return _deny("project_not_owned_or_active")
        rows = reader.read_access_rows(scan["owner_user_id"])
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            return _deny("access_read_invalid")
        matching = [row for row in rows if row.get("plan_id") == PLAN]
        if len(matching) != 1:
            return _deny("paid_access_missing_or_duplicate")
        access = matching[0]
        if (access.get("id") != scan["admission_access_id"]
                or access.get("owner_user_id") != scan["owner_user_id"]
                or access.get("app_id") != APP_ID or access.get("plan_id") != PLAN
                or access.get("access_status") != "active"
                or access.get("has_full_access") is not True
                or access.get("grant_source") != "stripe_checkout"
                or not _id(access.get("stripe_checkout_session_id"))
                or not isinstance(access.get("user_email"), str)
                or not access["user_email"].strip()
                or _time(access.get("paid_at")) is None):
            return _deny("paid_access_not_active")
        rid = _receipt_id(scan["owner_user_id"], scan["request_id"])
        expected_name = f"{queue_path}/tasks/extended500-{rid}-a{scan['attempt_count']}"
        if trusted_task_name != expected_name:
            return _deny("task_name_mismatch")
        slot = reader.read_owner_slot(scan["owner_user_id"])
        receipt = reader.read_request_receipt(rid)
        if not isinstance(slot, dict) or not isinstance(receipt, dict):
            return _deny("reservation_missing")
        if (slot.get("schema") != SLOT_SCHEMA or receipt.get("schema") != RECEIPT_SCHEMA
                or slot.get("owner_user_id") != scan["owner_user_id"]
                or receipt.get("owner_user_id") != scan["owner_user_id"]
                or slot.get("receipt_id") != rid or receipt.get("receipt_id") != rid
                or slot.get("request_id") != scan["request_id"]
                or receipt.get("request_id") != scan["request_id"]
                or slot.get("scan_id") != scan["id"] or receipt.get("scan_id") != scan["id"]
                or type(slot.get("attempt_count")) is not int
                or type(receipt.get("attempt_count")) is not int
                or slot["attempt_count"] != scan["attempt_count"]
                or receipt["attempt_count"] != scan["attempt_count"]
                or receipt.get("fingerprint") != _fingerprint(scan)
                or receipt.get("task_name") != expected_name):
            return _deny("reservation_identity_mismatch")
        if (slot.get("state") not in ACTIVE_DISPATCH_STATES
                or receipt.get("state") not in ACTIVE_DISPATCH_STATES
                or slot["state"] != receipt["state"]):
            return _deny("reservation_not_dispatched")
        if reader.read_pickup_claim(rid) is not None:
            return _deny("pickup_replay_or_claim_conflict")
        # A positive read is NOT a CAS commit. The integrator must atomically
        # create extended500_pickup_claims/{rid} and recheck current authority
        # under a coherent transaction/claim-fencing protocol before crawling.
        return PickupVerdict("ready_for_atomic_claim", True, False, rid, expected_name)
    except Exception:
        # Missing credentials, failed service-role/Firestore reads, timeouts,
        # adapter exceptions and ambiguous values all fail closed.
        return _deny("durable_authority_unavailable")
