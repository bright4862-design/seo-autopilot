"""Fail-closed Extended 500 worker PICKUP authorization. Pure and NOT wired.

Why a pickup-time decision is needed
------------------------------------
``base44/functions/issueExtended500AdmissionV1`` mints a preflight grant valid
for 120 seconds. The isolated coordinator (``extended500-admission/service.py``)
copies that grant verbatim into the body of a task on a dedicated queue that
``provision-queue.sh`` creates PAUSED with ``--max-concurrent-dispatches=1``.
Queue delay can therefore exceed the grant lifetime by hours, and
``extended500-admission/core.py`` states that a delayed task "remains
executable until a verified exact terminal release is committed".

So at pickup the grant is ONLY a signed integrity binding: it proves the task
body's identity fields were minted by the issuer under the Extended 500
admission key and were not edited in transit. It is never treated as live
authorization. Authorization comes from FRESH, service-owned reads performed
at pickup through injected ports:

* Base44 service role: ``ScanRun`` (looked up by the task's ``scan_id`` only),
  then ``BusinessProject``, owner ``User`` and ``Access`` rows, all looked up
  by keys taken from that fresh ScanRun, never from the task body;
* the coordinator's Firestore owner slot and immutable request receipt.

An expired grant is therefore accepted (and reported as ``grant_expired``) when
every fresh read authorizes the same exact identity. A grant that is tampered,
mis-shaped, issued for another purpose/mode, issued in the future, or older
than Cloud Tasks' maximum task retention is always refused.

What this module is NOT
-----------------------
No route, crawler, persistence, Base44/Firestore/HTTP client, Standard 150
admission import, ``main.py`` hook, or write of any kind. ``execution_enabled``
is always ``False``. ``decide_extended500_pickup_claim`` is a pure transaction
body for a FUTURE adaptor; nothing here calls a real transaction.

UNVERIFIED (needs real infrastructure; see docs/extended500/lane-b-pickup-auth.md):
that port adaptors really use the Base44 service role / coordinator Firestore
and are not caches; Cloud Run IAM and invoker identity of the future 500 route;
that ``X-CloudTasks-*`` delivery headers cannot be forged past IAM; Firestore
transaction serializability for the pickup claim under contention.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import inspect
import json
import re
from types import MappingProxyType
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import urlsplit

from .authority_seal import create_authority_seal
from .extended500_job_admission import (
    EXTENDED500_GRANT_AUDIENCE,
    EXTENDED500_GRANT_MAX_SECONDS,
    EXTENDED500_GRANT_VERSION,
    EXTENDED500_JOB_MODE,
)

PICKUP_AUTHORIZATION_VERSION = "extended500_pickup_authorization_v1"
PICKUP_CLAIM_VERSION = "extended500_pickup_claim_v1"
EXTENDED500_PLAN_ID = "extended500_lifetime"
STANDARD150_PLAN_ID = "standard150_lifetime"
# Mirrors EXTENDED500_ACCESS_APP_ID in the Base44 issuer package.
EXTENDED500_ACCESS_APP_ID = "6a498732ec779dfaaeab0e53"
# Coordinator document schemas and states (extended500-admission/core.py).
RECEIPT_SCHEMA = "extended500_request_receipt_v1"
SLOT_SCHEMA = "extended500_owner_slot_v1"
TASK_PREFIX = "extended500-"
ACTIVE_RESERVATION_STATES = frozenset({"reserved", "dispatch_unknown", "enqueued"})
TERMINAL_RUN_STATUSES = frozenset({"complete", "limited", "failed", "cancelled"})
STARTED_RUN_STATUSES = frozenset({"crawling", "reviewing"})

AUTHORITY_BASE44_SERVICE_ROLE = "base44_service_role"
AUTHORITY_COORDINATOR_FIRESTORE = "extended500_coordinator_firestore"
# Every authority read must be this recent when the decision is made.
MAX_SOURCE_AGE_SECONDS = 30
# Cloud Tasks retains an undelivered task for at most 31 days; an older body
# cannot be a genuine delivery of a coordinator-created task.
MAX_TASK_AGE_SECONDS = 31 * 24 * 60 * 60

# Pickup outcomes: authorized -> may attempt the atomic pickup claim (still not
# execution); skip -> benign stale/duplicate, ack and do nothing; deny ->
# integrity or entitlement refusal, ack, do nothing, alert; retry -> transient,
# no side effect, safe for Cloud Tasks to redeliver.
AUTHORIZED, SKIP, DENY, RETRY = "authorized", "skip", "deny", "retry"
# Revalidation outcomes: only CONTINUE permits the next side effect.
CONTINUE, ABORT, UNAVAILABLE = "continue", "abort", "unavailable"
CLAIMED = "claimed"

# Exact body built by extended500-admission/service.py enqueue().
TASK_FIELDS = frozenset({
    "scan_mode", "scan_id", "request_id", "idempotency_key", "project_id",
    "owner_user_id", "attempt_count", "website_url", "path_prefix",
    "respect_robots_txt", "owner_attested_robots_override", "signed_grant",
})
# Exact preflight grant minted by the issuer (plus its proof).
GRANT_FIELDS = frozenset({
    "version", "audience", "canonical_mode", "scan_id", "owner_user_id",
    "project_id", "request_id", "idempotency_key", "attempt_count",
    "website_url", "path_prefix", "respect_robots_txt",
    "owner_attested_robots_override", "issued_at", "expires_at", "proof",
})
_GRANT_TASK_FIELDS = (
    "scan_id", "owner_user_id", "project_id", "request_id", "idempotency_key",
    "attempt_count", "website_url", "path_prefix", "respect_robots_txt",
    "owner_attested_robots_override",
)
# Defensive: no schema field today, but any truthy marker is a refusal.
_REVOCATION_MARKERS = ("revoked_at", "refunded_at", "refund_id", "stripe_refund_id", "chargeback_at")
_BINDING_FIELDS = frozenset({
    "version", "scan_mode", "plan_id", "owner_user_id", "scan_id", "project_id",
    "request_id", "idempotency_key", "attempt_count", "access_id", "website_url",
    "host", "path_prefix", "respect_robots_txt", "owner_attested_robots_override",
    "receipt_id", "request_fingerprint", "task_name", "queue_path",
    "grant_issued_at", "grant_expires_at", "grant_expired_at_pickup", "authorized_at",
})
_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_HEX64 = re.compile(r"[a-f0-9]{64}\Z")
_QUEUE_PATH = re.compile(
    r"projects/[A-Za-z0-9_-]+/locations/[A-Za-z0-9_-]+/queues/(extended500-[A-Za-z0-9_-]+)\Z"
)
_NON_PUBLIC_SUFFIXES = (".localhost", ".local", ".internal", ".test", ".invalid", ".example")
_HOST = re.compile(r"[a-z0-9.-]{1,253}\Z")


@dataclass(frozen=True)
class SourceRead:
    """One authority read. ``authority`` is the adaptor's declared source.

    The async gatherers stamp ``fetched_at`` themselves from the injected
    clock immediately after the port returns; a port cannot backdate it.
    """

    authority: str
    value: Any
    fetched_at: datetime | None = None


@dataclass(frozen=True)
class PickupDecision:
    outcome: str
    reason: str
    binding: Mapping[str, Any] | None = None
    grant_expired: bool = False
    execution_enabled: bool = False

    @property
    def authorized(self) -> bool:
        return self.outcome == AUTHORIZED and self.binding is not None


@dataclass(frozen=True)
class RevalidationDecision:
    outcome: str
    reason: str
    execution_enabled: bool = False

    @property
    def may_continue(self) -> bool:
        return self.outcome == CONTINUE


@dataclass(frozen=True)
class PickupClaimResult:
    outcome: str
    reason: str
    pickup_claim: Mapping[str, Any] | None = None
    execution_enabled: bool = False


class Extended500PickupSources(Protocol):
    """Injected read ports. Each returns a ``SourceRead`` (sync or awaitable).

    Base44 ports MUST use the service role (never a customer session) and the
    coordinator ports MUST read the live Firestore documents, not a cache.
    """

    def read_scan_run(self, scan_id: str) -> Any: ...
    def read_business_project(self, project_id: str) -> Any: ...
    def read_owner_user(self, owner_user_id: str) -> Any: ...
    def filter_access_by_owner(self, owner_user_id: str) -> Any: ...
    def filter_access_by_email(self, user_email: str) -> Any: ...
    def read_owner_slot(self, owner_user_id: str) -> Any: ...
    def read_request_receipt(self, receipt_id: str) -> Any: ...


class Extended500PickupClaimPort(Protocol):
    """Must read slot+receipt, call ``decide(slot, receipt)`` and, only when
    the result's outcome is ``claimed``, write ``slot_write`` and
    ``receipt_write`` in the SAME transaction; then return that exact result."""

    def transact_pickup_claim(self, *, owner_user_id: str, receipt_id: str,
                              decide: Callable[[Any, Any], dict[str, Any]]) -> Any: ...


# ------------------------------------------------------------ primitives --

def _ident(value: Any) -> bool:
    return isinstance(value, str) and bool(_ID.fullmatch(value))


def _attempt(value: Any) -> int | None:
    return value if type(value) is int and 1 <= value <= 100_000 else None


def _zulu(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _instant(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _aware(moment: Any) -> bool:
    return isinstance(moment, datetime) and moment.tzinfo is not None


def _site_url(value: Any) -> str:
    """Exact comparable scheme://host/path, or '' when unusable."""
    if not isinstance(value, str) or len(value) > 2048:
        return ""
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return ""
    if (parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment or port not in (None, 80, 443)):
        return ""
    return f"{parsed.scheme}://{parsed.hostname.lower().rstrip('.')}{parsed.path or '/'}"


def _bare_host(value: Any) -> str:
    """Host comparison used by the Base44 issuer: lower, no www., no dot."""
    if not isinstance(value, str) or len(value) > 2048:
        return ""
    try:
        parsed = urlsplit(value)
    except ValueError:
        return ""
    if (parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username is not None or parsed.password is not None):
        return ""
    return parsed.hostname.lower().rstrip(".").removeprefix("www.")


def _public_host(host: str) -> bool:
    return bool(
        _HOST.fullmatch(host) and "." in host and ".." not in host
        and not host.startswith((".", "-")) and not host.endswith((".", "-"))
        and host != "localhost" and not host.endswith(_NON_PUBLIC_SUFFIXES)
        and not re.fullmatch(r"[0-9.]+", host)
    )


def _path(value: Any) -> str | None:
    """None for whole-site, the prefix, or '' when invalid (fail closed)."""
    if value is None or value == "":
        return None
    if (not isinstance(value, str) or not value.startswith("/") or len(value) > 2048
            or any(token in value for token in ("?", "#", "\\", "//"))):
        return ""
    return value


def _robots_pair(respect: Any, override: Any) -> bool:
    return type(respect) is bool and type(override) is bool and override == (respect is False)


def _same(left: Any, right: Any) -> bool:
    # In Python True == 1; a bool must never impersonate an int or vice versa.
    return type(left) is type(right) and left == right


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def extended500_request_fingerprint(request: Mapping[str, Any]) -> str:
    """Byte-identical to extended500-admission/core.py fingerprint()."""
    return hashlib.sha256(json.dumps(
        dict(request), sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode()).hexdigest()


def extended500_receipt_id(owner_user_id: str, request_id: str) -> str:
    """Byte-identical to extended500-admission/core.py receipt_id()."""
    return hashlib.sha256((owner_user_id + "\n" + request_id).encode()).hexdigest()


def extended500_task_name(queue_path: str, receipt_id: str, attempt_count: int) -> str:
    """Byte-identical to extended500-admission/core.py task_name()."""
    return f"{queue_path}/tasks/{TASK_PREFIX}{receipt_id}-a{attempt_count}"


def delivery_from_cloud_tasks_headers(headers: Mapping[str, Any]) -> dict[str, Any]:
    """Map Cloud Tasks HTTP-target headers to the delivery context.

    Header authenticity depends on Cloud Run IAM rejecting non-Cloud-Tasks
    callers (UNVERIFIED here). Counts are informational only.
    """
    lowered = {str(key).lower(): value for key, value in dict(headers or {}).items()}

    def count(name: str) -> int | None:
        try:
            parsed = int(str(lowered.get(name, "")).strip())
        except ValueError:
            return None
        return parsed if parsed >= 0 else None

    return {
        "queue_name": str(lowered.get("x-cloudtasks-queuename") or ""),
        "task_name": str(lowered.get("x-cloudtasks-taskname") or ""),
        "retry_count": count("x-cloudtasks-taskretrycount"),
        "execution_count": count("x-cloudtasks-taskexecutioncount"),
    }


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class _Refusal(Exception):
    def __init__(self, outcome: str, reason: str):
        super().__init__(reason)
        self.outcome = outcome
        self.reason = reason


def _refuse(outcome: str, reason: str) -> None:
    raise _Refusal(outcome, reason)


def _fresh(read: Any, authority: str, now: datetime, name: str) -> Any:
    if not isinstance(read, SourceRead):
        _refuse(DENY, f"{name}_provenance_invalid")
    if read.authority != authority:
        _refuse(DENY, f"{name}_not_service_owned")
    if not _aware(read.fetched_at):
        _refuse(DENY, f"{name}_freshness_unproven")
    if read.fetched_at > now or now - read.fetched_at > timedelta(seconds=MAX_SOURCE_AGE_SECONDS):
        _refuse(RETRY, f"{name}_stale")
    return read.value


def _paid_access_denial(record: Mapping[str, Any], owner_user_id: str, owner_email: str) -> str | None:
    """Mirror of issuer.js paidAccessRecord with specific refusal codes."""
    email = owner_email.strip().lower()
    if (record.get("owner_user_id") != owner_user_id or not email
            or str(record.get("user_email") or "").strip().lower() != email):
        return "access_owner_mismatch"
    if record.get("app_id") != EXTENDED500_ACCESS_APP_ID:
        return "access_app_mismatch"
    status = record.get("access_status")
    if status == "revoked":
        return "entitlement_revoked"
    if status == "pending":
        return "entitlement_pending"
    if status == "refunded":
        return "entitlement_refunded"
    if status != "active":
        return "entitlement_inactive"
    if any(record.get(marker) not in (None, "", False) for marker in _REVOCATION_MARKERS):
        return "entitlement_refunded_or_revoked"
    if record.get("has_full_access") is not True:
        return "entitlement_inactive"
    source = record.get("grant_source")
    if source == "owner_test":
        return "owner_test_access_not_paid"
    if source in ("manual_grant", "manual"):
        return "manual_access_not_paid"
    if source == "checkout_pending":
        return "entitlement_pending"
    if source != "stripe_checkout":
        return "access_not_stripe_paid"
    if not _ident(record.get("stripe_checkout_session_id")) or _instant(record.get("paid_at")) is None:
        return "access_not_stripe_paid"
    return None


# --------------------------------------------------------- staged checks --

class _Evaluation:
    """Ordered checks shared by pickup and mid-crawl revalidation.

    ``claimed`` is what must be proven: the grant-verified task identity at
    pickup, the server-derived binding during revalidation. Every authority
    value used afterwards comes from the fresh records, never from ``claimed``.
    """

    def __init__(self, phase: str, claimed: Mapping[str, Any], queue_path: str,
                 execution_id: str | None = None):
        self.phase = phase
        self.claimed = claimed
        self.queue_path = queue_path
        self.execution_id = execution_id
        self.scan: dict[str, Any] = {}
        self.host = ""
        self.owner_email = ""
        self.access: dict[str, Any] = {}
        self.receipt_id = ""
        self.fingerprint = ""
        self.task_name = ""

    # Lookup keys available to gatherers once the ScanRun was verified.
    @property
    def owner_user_id(self) -> str:
        return self.scan["owner_user_id"]

    def check_scan(self, read: Any, now: datetime) -> None:
        scan = _fresh(read, AUTHORITY_BASE44_SERVICE_ROLE, now, "scan_run")
        if scan is None:
            _refuse(RETRY, "scan_run_unavailable")
        if not isinstance(scan, dict):
            _refuse(DENY, "scan_run_invalid")
        claimed = self.claimed
        if not _same(scan.get("id"), claimed["scan_id"]) or scan.get("scan_id") not in (None, "", scan.get("id")):
            _refuse(DENY, "scan_identity_mismatch")
        if scan.get("scan_mode") != EXTENDED500_JOB_MODE:
            _refuse(DENY, "scan_mode_not_extended500")
        if not all(_ident(scan.get(key)) for key in
                   ("owner_user_id", "project_id", "request_id", "idempotency_key")):
            _refuse(DENY, "scan_identity_invalid")
        if scan["owner_user_id"] != claimed["owner_user_id"]:
            _refuse(DENY, "owner_mismatch")
        if scan["project_id"] != claimed["project_id"]:
            _refuse(DENY, "project_mismatch")
        if (scan["request_id"] != claimed["request_id"]
                or scan["idempotency_key"] != claimed["idempotency_key"]):
            _refuse(DENY, "request_identity_mismatch")
        attempt = _attempt(scan.get("attempt_count"))
        if attempt is None:
            _refuse(DENY, "scan_attempt_invalid")
        if attempt > claimed["attempt_count"]:
            _refuse(SKIP, "superseded_attempt")
        if attempt < claimed["attempt_count"]:
            _refuse(DENY, "attempt_ahead_of_run")
        status = scan.get("status")
        if status in TERMINAL_RUN_STATUSES:
            _refuse(SKIP, "run_already_terminal")
        if self.phase == "pickup":
            if status in STARTED_RUN_STATUSES:
                _refuse(SKIP, "run_already_started")
            if status != "queued":
                _refuse(DENY, "run_status_invalid")
        elif status != "queued" and status not in STARTED_RUN_STATUSES:
            _refuse(DENY, "run_status_invalid")
        url = _site_url(scan.get("website_url"))
        if not url or url != _site_url(claimed["website_url"]):
            _refuse(DENY, "target_mismatch")
        host = _bare_host(url)
        if not _public_host(host):
            _refuse(DENY, "target_not_public")
        domain = scan.get("normalized_domain")
        if domain not in (None, "") and (
                not isinstance(domain, str)
                or domain.lower().rstrip(".").removeprefix("www.") != host):
            _refuse(DENY, "domain_mismatch")
        prefix = _path(scan.get("path_prefix"))
        if prefix == "" or prefix != _path(claimed["path_prefix"]):
            _refuse(DENY, "scope_mismatch")
        respect, override = scan.get("respect_robots_txt"), scan.get("owner_attested_robots_override")
        if not _robots_pair(respect, override):
            _refuse(DENY, "robots_policy_invalid")
        if respect != claimed["respect_robots_txt"] or override != claimed["owner_attested_robots_override"]:
            _refuse(DENY, "robots_policy_mismatch")
        if not _ident(scan.get("admission_access_id")):
            _refuse(DENY, "scan_access_provenance_missing")
        self.scan = scan
        self.host = host
        self.receipt_id = extended500_receipt_id(scan["owner_user_id"], scan["request_id"])

    def check_project(self, read: Any, now: datetime) -> None:
        project = _fresh(read, AUTHORITY_BASE44_SERVICE_ROLE, now, "business_project")
        if project is None:
            _refuse(DENY, "project_not_found")
        if not isinstance(project, dict) or project.get("id") != self.scan["project_id"]:
            _refuse(DENY, "project_identity_mismatch")
        # BusinessProject is customer-writable except owner_user_id; only the
        # owner and the host are consulted, never subscription_plan or status.
        if project.get("owner_user_id") != self.owner_user_id:
            _refuse(DENY, "project_owner_mismatch")
        if _bare_host(project.get("website_url")) != self.host:
            _refuse(DENY, "project_domain_mismatch")

    def check_owner(self, read: Any, now: datetime) -> None:
        user = _fresh(read, AUTHORITY_BASE44_SERVICE_ROLE, now, "owner_user")
        if user is None:
            _refuse(DENY, "owner_not_found")
        if not isinstance(user, dict) or user.get("id") != self.owner_user_id:
            _refuse(DENY, "owner_identity_mismatch")
        email = user.get("email")
        if not isinstance(email, str) or not email.strip() or len(email) > 320:
            _refuse(DENY, "owner_email_unavailable")
        self.owner_email = email

    def check_access(self, by_owner: Any, by_email: Any, now: datetime) -> None:
        owned = _fresh(by_owner, AUTHORITY_BASE44_SERVICE_ROLE, now, "access_by_owner")
        mailed = _fresh(by_email, AUTHORITY_BASE44_SERVICE_ROLE, now, "access_by_email")
        if not isinstance(owned, list) or not isinstance(mailed, list):
            _refuse(RETRY, "access_read_unavailable")
        rows = [*owned, *mailed]
        if any(not isinstance(row, dict) or not _ident(row.get("id")) for row in rows):
            _refuse(DENY, "access_identity_invalid")
        distinct: dict[str, dict[str, Any]] = {}
        for row in rows:
            seen = distinct.setdefault(row["id"], row)
            if _canonical_json(seen) != _canonical_json(row):
                _refuse(DENY, "access_read_conflict")
        plan_rows = [row for row in distinct.values() if row.get("plan_id") == EXTENDED500_PLAN_ID]
        if not plan_rows:
            if any(row.get("plan_id") == STANDARD150_PLAN_ID for row in distinct.values()):
                _refuse(DENY, "standard150_access_cannot_authorize_extended500")
            _refuse(DENY, "extended500_paid_access_required")
        if len(plan_rows) != 1:
            _refuse(DENY, "duplicate_extended500_access")
        record = plan_rows[0]
        denial = _paid_access_denial(record, self.owner_user_id, self.owner_email)
        if denial:
            _refuse(DENY, denial)
        if record["id"] != self.scan["admission_access_id"]:
            _refuse(DENY, "entitlement_rebound")
        if self.phase == "revalidation" and record["id"] != self.claimed["access_id"]:
            _refuse(DENY, "entitlement_rebound")
        self.access = record

    def check_reservation(self, slot_read: Any, receipt_read: Any, now: datetime,
                          delivery: Mapping[str, Any] | None = None) -> None:
        receipt = _fresh(receipt_read, AUTHORITY_COORDINATOR_FIRESTORE, now, "request_receipt")
        slot = _fresh(slot_read, AUTHORITY_COORDINATOR_FIRESTORE, now, "owner_slot")
        scan = self.scan
        request = {
            "owner_user_id": scan["owner_user_id"], "scan_id": scan["id"],
            "project_id": scan["project_id"], "request_id": scan["request_id"],
            "idempotency_key": scan["idempotency_key"], "access_id": self.access["id"],
            "attempt_count": scan["attempt_count"],
        }
        rid = self.receipt_id
        fingerprint = extended500_request_fingerprint(request)
        task_name = extended500_task_name(self.queue_path, rid, scan["attempt_count"])
        if receipt is None:
            _refuse(DENY, "reservation_receipt_missing")
        if (not isinstance(receipt, dict) or receipt.get("schema") != RECEIPT_SCHEMA
                or receipt.get("receipt_id") != rid):
            _refuse(DENY, "reservation_receipt_invalid")
        if receipt.get("fingerprint") != fingerprint:
            # Covers a replaced Access row as well as changed attempt/request.
            _refuse(DENY, "reservation_fingerprint_mismatch")
        for key in ("owner_user_id", "request_id", "scan_id", "attempt_count"):
            if not _same(receipt.get(key), request[key]):
                _refuse(DENY, "reservation_identity_mismatch")
        if receipt.get("task_name") != task_name:
            _refuse(DENY, "reservation_task_mismatch")
        state = receipt.get("state")
        if state == "released":
            _refuse(SKIP, "reservation_released")
        if state not in ACTIVE_RESERVATION_STATES:
            _refuse(DENY, "reservation_state_invalid")
        if self.phase == "pickup":
            queue_name = _QUEUE_PATH.fullmatch(self.queue_path).group(1)
            if (not isinstance(delivery, Mapping)
                    or delivery.get("task_name") != task_name.rsplit("/", 1)[1]
                    or delivery.get("queue_name") != queue_name):
                _refuse(DENY, "delivery_task_mismatch")
        if slot is None:
            _refuse(DENY, "owner_slot_missing")
        if (not isinstance(slot, dict) or slot.get("schema") != SLOT_SCHEMA
                or slot.get("owner_user_id") != scan["owner_user_id"]):
            _refuse(DENY, "owner_slot_invalid")
        if slot.get("receipt_id") != rid:
            _refuse(DENY, "owner_slot_rebound")
        for key in ("request_id", "scan_id", "attempt_count"):
            if not _same(slot.get(key), request[key]):
                _refuse(DENY, "owner_slot_identity_mismatch")
        if slot.get("state") not in ACTIVE_RESERVATION_STATES or slot.get("state") != state:
            _refuse(DENY, "owner_slot_stale")
        receipt_claim, slot_claim = receipt.get("pickup_claim"), slot.get("pickup_claim")
        if self.phase == "pickup":
            if receipt_claim is not None and slot_claim is not None:
                _refuse(SKIP, "already_picked_up")
            if receipt_claim is not None or slot_claim is not None:
                _refuse(DENY, "reservation_integrity_mismatch")
        else:
            if (not isinstance(receipt_claim, dict) or not isinstance(slot_claim, dict)
                    or _canonical_json(receipt_claim) != _canonical_json(slot_claim)):
                _refuse(DENY, "pickup_claim_lost")
            if (receipt_claim.get("version") != PICKUP_CLAIM_VERSION
                    or receipt_claim.get("execution_id") != self.execution_id):
                _refuse(DENY, "pickup_claim_lost")
            if fingerprint != self.claimed["request_fingerprint"] or task_name != self.claimed["task_name"]:
                _refuse(DENY, "reservation_fingerprint_mismatch")
        self.fingerprint = fingerprint
        self.task_name = task_name


class _Pickup(_Evaluation):
    def __init__(self, task: Any, delivery: Any, grant_signing_key: Any, queue_path: Any):
        super().__init__("pickup", {}, queue_path if isinstance(queue_path, str) else "")
        self.task = task
        self.delivery = delivery
        self.grant_signing_key = grant_signing_key
        self.grant: dict[str, Any] = {}
        self.grant_expired = False

    def precheck(self, now: Any) -> None:
        """Pure task/grant integrity. Runs before ANY authority read."""
        if not _aware(now):
            _refuse(DENY, "clock_invalid")
        key = self.grant_signing_key
        if not isinstance(key, str) or len(key) < 32:
            _refuse(RETRY, "grant_signing_unavailable")
        if not _QUEUE_PATH.fullmatch(self.queue_path):
            _refuse(RETRY, "worker_queue_configuration_invalid")
        task = self.task
        # Exact shape: no client paid flag, plan, owner hint or access field
        # can ride along in the body.
        if not isinstance(task, dict) or set(task) != TASK_FIELDS:
            _refuse(DENY, "task_shape_invalid")
        if task["scan_mode"] != EXTENDED500_JOB_MODE:
            _refuse(DENY, "task_mode_invalid")
        if not all(_ident(task[key]) for key in
                   ("scan_id", "owner_user_id", "project_id", "request_id", "idempotency_key")):
            _refuse(DENY, "task_identity_invalid")
        if _attempt(task["attempt_count"]) is None:
            _refuse(DENY, "task_attempt_invalid")
        if not _robots_pair(task["respect_robots_txt"], task["owner_attested_robots_override"]):
            _refuse(DENY, "task_robots_policy_invalid")
        delivery = self.delivery
        if (not isinstance(delivery, Mapping)
                or not isinstance(delivery.get("task_name"), str) or not delivery["task_name"]
                or not isinstance(delivery.get("queue_name"), str) or not delivery["queue_name"]):
            _refuse(DENY, "delivery_metadata_missing")
        grant = task["signed_grant"]
        if not isinstance(grant, dict) or set(grant) != GRANT_FIELDS:
            _refuse(DENY, "grant_shape_invalid")
        proof = grant.get("proof")
        if not isinstance(proof, str) or not _HEX64.fullmatch(proof):
            _refuse(DENY, "grant_signature_invalid")
        try:
            expected = create_authority_seal({k: v for k, v in grant.items() if k != "proof"}, key)
        except Exception:  # noqa: BLE001 - any serialization failure is a refusal
            _refuse(DENY, "grant_signature_invalid")
        if not hmac.compare_digest(expected, proof):
            _refuse(DENY, "grant_signature_invalid")
        if grant["version"] != EXTENDED500_GRANT_VERSION or grant["audience"] != EXTENDED500_GRANT_AUDIENCE:
            _refuse(DENY, "grant_context_invalid")
        if grant["canonical_mode"] != EXTENDED500_JOB_MODE:
            _refuse(DENY, "grant_mode_invalid")
        for field in _GRANT_TASK_FIELDS:
            if not _same(grant[field], task[field]):
                _refuse(DENY, "grant_task_mismatch")
        issued, expires = _zulu(grant["issued_at"]), _zulu(grant["expires_at"])
        if (issued is None or expires is None
                or not timedelta(0) < expires - issued <= timedelta(seconds=EXTENDED500_GRANT_MAX_SECONDS)):
            _refuse(DENY, "grant_time_invalid")
        if issued > now:
            _refuse(DENY, "grant_issued_in_future")
        if now - issued > timedelta(seconds=MAX_TASK_AGE_SECONDS):
            _refuse(DENY, "task_older_than_queue_retention")
        self.grant = grant
        self.grant_expired = expires <= now
        self.claimed = {field: task[field] for field in _GRANT_TASK_FIELDS}

    def authorized(self, now: datetime) -> PickupDecision:
        scan = self.scan
        binding = {
            "version": PICKUP_AUTHORIZATION_VERSION,
            "scan_mode": EXTENDED500_JOB_MODE,
            "plan_id": EXTENDED500_PLAN_ID,
            "owner_user_id": scan["owner_user_id"],
            "scan_id": scan["id"],
            "project_id": scan["project_id"],
            "request_id": scan["request_id"],
            "idempotency_key": scan["idempotency_key"],
            "attempt_count": scan["attempt_count"],
            "access_id": self.access["id"],
            "website_url": _site_url(scan["website_url"]),
            "host": self.host,
            "path_prefix": _path(scan.get("path_prefix")),
            "respect_robots_txt": scan["respect_robots_txt"],
            "owner_attested_robots_override": scan["owner_attested_robots_override"],
            "receipt_id": self.receipt_id,
            "request_fingerprint": self.fingerprint,
            "task_name": self.task_name,
            "queue_path": self.queue_path,
            "grant_issued_at": self.grant["issued_at"],
            "grant_expires_at": self.grant["expires_at"],
            "grant_expired_at_pickup": self.grant_expired,
            "authorized_at": _iso(now),
        }
        return PickupDecision(
            AUTHORIZED,
            "fresh_paid_entitlement_and_reservation_verified",
            MappingProxyType(binding),
            grant_expired=self.grant_expired,
        )


EVIDENCE_KEYS = (
    "scan_run", "business_project", "owner_user", "access_by_owner",
    "access_by_email", "owner_slot", "request_receipt",
)


def evaluate_extended500_pickup(
    task: Any,
    delivery: Any,
    evidence: Mapping[str, Any],
    *,
    grant_signing_key: Any,
    queue_path: Any,
    now: Any,
) -> PickupDecision:
    """Decide one delivery from complete, freshly read evidence. Never writes.

    ``evidence`` maps each of ``EVIDENCE_KEYS`` to a ``SourceRead``. The task
    body is only a claim; it never supplies a lookup key beyond ``scan_id``.
    """
    pickup = _Pickup(task, delivery, grant_signing_key, queue_path)
    try:
        pickup.precheck(now)
        if not isinstance(evidence, Mapping) or any(key not in evidence for key in EVIDENCE_KEYS):
            _refuse(DENY, "evidence_incomplete")
        pickup.check_scan(evidence["scan_run"], now)
        pickup.check_project(evidence["business_project"], now)
        pickup.check_owner(evidence["owner_user"], now)
        pickup.check_access(evidence["access_by_owner"], evidence["access_by_email"], now)
        pickup.check_reservation(evidence["owner_slot"], evidence["request_receipt"], now, delivery)
    except _Refusal as refusal:
        return PickupDecision(refusal.outcome, refusal.reason, grant_expired=pickup.grant_expired)
    return pickup.authorized(now)


class _SourceFailure(Exception):
    pass


async def _read(sources: Any, method: str, argument: str, clock: Callable[[], datetime]) -> SourceRead:
    try:
        result = getattr(sources, method)(argument)
        if inspect.isawaitable(result):
            result = await result
    except Exception as exc:  # noqa: BLE001 - any transport failure is transient
        raise _SourceFailure(method) from exc
    if not isinstance(result, SourceRead):
        # Leave it unstamped so evaluation refuses it as unproven provenance.
        return result
    return replace(result, fetched_at=clock())


async def authorize_extended500_pickup(
    task: Any,
    delivery: Any,
    sources: Any,
    *,
    grant_signing_key: Any,
    queue_path: Any,
    clock: Callable[[], datetime] = _utc_now,
) -> PickupDecision:
    """Read fresh authority in dependency order, then decide.

    A tampered or mis-shaped task never triggers a read. A foreign owner or
    project never triggers an Access read. Keys after ``scan_id`` come from
    the fresh ScanRun (owner, project, request) and fresh User (email).
    The final verdict is exactly ``evaluate_extended500_pickup`` on what was
    read, re-checked against one final clock instant.
    """
    pickup = _Pickup(task, delivery, grant_signing_key, queue_path)
    evidence: dict[str, Any] = {}
    try:
        pickup.precheck(clock())
        evidence["scan_run"] = await _read(sources, "read_scan_run", task["scan_id"], clock)
        pickup.check_scan(evidence["scan_run"], clock())
        evidence["business_project"] = await _read(
            sources, "read_business_project", pickup.scan["project_id"], clock)
        pickup.check_project(evidence["business_project"], clock())
        evidence["owner_user"] = await _read(sources, "read_owner_user", pickup.owner_user_id, clock)
        pickup.check_owner(evidence["owner_user"], clock())
        evidence["access_by_owner"] = await _read(
            sources, "filter_access_by_owner", pickup.owner_user_id, clock)
        evidence["access_by_email"] = await _read(
            sources, "filter_access_by_email", pickup.owner_email, clock)
        pickup.check_access(evidence["access_by_owner"], evidence["access_by_email"], clock())
        evidence["owner_slot"] = await _read(sources, "read_owner_slot", pickup.owner_user_id, clock)
        evidence["request_receipt"] = await _read(
            sources, "read_request_receipt", pickup.receipt_id, clock)
    except _Refusal as refusal:
        return PickupDecision(refusal.outcome, refusal.reason, grant_expired=pickup.grant_expired)
    except _SourceFailure as failure:
        return PickupDecision(RETRY, f"source_unavailable:{failure}", grant_expired=pickup.grant_expired)
    return evaluate_extended500_pickup(
        task, delivery, evidence,
        grant_signing_key=grant_signing_key, queue_path=queue_path, now=clock(),
    )


# ------------------------------------------------------ atomic pickup claim --

def decide_extended500_pickup_claim(
    slot: Any,
    receipt: Any,
    binding: Mapping[str, Any],
    *,
    execution_id: Any,
    claimed_at: Any,
) -> dict[str, Any]:
    """Pure Firestore transaction body for exactly-one pickup per reservation.

    Must run INSIDE the transaction that read ``slot`` and ``receipt``. The
    claim is an extra ``pickup_claim`` field on both documents; ``state`` is
    left untouched, so core.py's dispatch/release decisions (which spread the
    existing dicts) keep working unchanged and preserve the marker.
    """
    if not _ident(execution_id):
        return {"outcome": DENY, "reason": "execution_id_invalid"}
    if not _aware(claimed_at):
        return {"outcome": DENY, "reason": "clock_invalid"}
    if not _binding_valid(binding):
        return {"outcome": DENY, "reason": "pickup_not_authorized"}
    if not isinstance(receipt, dict) or receipt.get("schema") != RECEIPT_SCHEMA:
        return {"outcome": DENY, "reason": "reservation_receipt_missing"}
    if (receipt.get("receipt_id") != binding["receipt_id"]
            or receipt.get("fingerprint") != binding["request_fingerprint"]
            or receipt.get("task_name") != binding["task_name"]):
        return {"outcome": DENY, "reason": "reservation_changed_before_claim"}
    if receipt.get("state") == "released":
        return {"outcome": SKIP, "reason": "reservation_released"}
    if receipt.get("state") not in ACTIVE_RESERVATION_STATES:
        return {"outcome": DENY, "reason": "reservation_state_invalid"}
    if (not isinstance(slot, dict) or slot.get("schema") != SLOT_SCHEMA
            or slot.get("owner_user_id") != binding["owner_user_id"]
            or slot.get("receipt_id") != binding["receipt_id"]):
        return {"outcome": DENY, "reason": "owner_slot_rebound"}
    if slot.get("state") != receipt.get("state"):
        return {"outcome": DENY, "reason": "owner_slot_stale"}
    existing, slot_existing = receipt.get("pickup_claim"), slot.get("pickup_claim")
    if existing is not None or slot_existing is not None:
        if (isinstance(existing, dict) and isinstance(slot_existing, dict)
                and existing.get("execution_id") == execution_id
                and _canonical_json(existing) == _canonical_json(slot_existing)):
            # Same executor retrying after an unknown commit outcome.
            return {"outcome": "already_claimed_by_self", "pickup_claim": existing}
        return {"outcome": SKIP, "reason": "already_picked_up"}
    claim = {
        "version": PICKUP_CLAIM_VERSION,
        "execution_id": execution_id,
        "scan_id": binding["scan_id"],
        "request_id": binding["request_id"],
        "attempt_count": binding["attempt_count"],
        "access_id": binding["access_id"],
        "task_name": binding["task_name"],
        "claimed_at": _iso(claimed_at),
    }
    return {
        "outcome": CLAIMED,
        "pickup_claim": claim,
        "slot_write": {**slot, "pickup_claim": claim},
        "receipt_write": {**receipt, "pickup_claim": claim},
    }


async def claim_extended500_pickup(
    port: Any,
    decision: PickupDecision,
    *,
    execution_id: Any,
    clock: Callable[[], datetime] = _utc_now,
) -> PickupClaimResult:
    """Run the pure claim decision through an injected transactional port.

    The port's return value must be the exact decision object it obtained from
    ``decide``; anything else (or an exception) is an unknown outcome that must
    be retried with the SAME execution_id, never with a new one.
    """
    if not isinstance(decision, PickupDecision) or not decision.authorized:
        return PickupClaimResult(DENY, "pickup_not_authorized")
    if not _ident(execution_id):
        return PickupClaimResult(DENY, "execution_id_invalid")
    binding = decision.binding
    claimed_at = clock()
    produced: list[dict[str, Any]] = []

    def decide(slot: Any, receipt: Any) -> dict[str, Any]:
        result = decide_extended500_pickup_claim(
            slot, receipt, binding, execution_id=execution_id, claimed_at=claimed_at,
        )
        produced.append(result)
        return result

    try:
        returned = port.transact_pickup_claim(
            owner_user_id=binding["owner_user_id"], receipt_id=binding["receipt_id"], decide=decide,
        )
        if inspect.isawaitable(returned):
            returned = await returned
    except Exception:  # noqa: BLE001 - commit may or may not have happened
        return PickupClaimResult(RETRY, "claim_outcome_unknown")
    if not produced or returned is not produced[-1]:
        return PickupClaimResult(RETRY, "claim_outcome_unknown")
    outcome = returned["outcome"]
    if outcome in (CLAIMED, "already_claimed_by_self"):
        reason = "pickup_claimed" if outcome == CLAIMED else "already_claimed_by_self"
        return PickupClaimResult(CLAIMED, reason, MappingProxyType(dict(returned["pickup_claim"])))
    return PickupClaimResult(outcome, returned.get("reason", "claim_refused"))


# ------------------------------------------------- mid-crawl revalidation --

def _binding_valid(binding: Any) -> bool:
    return (
        isinstance(binding, Mapping) and set(binding) == _BINDING_FIELDS
        and binding.get("version") == PICKUP_AUTHORIZATION_VERSION
        and binding.get("scan_mode") == EXTENDED500_JOB_MODE
        and binding.get("plan_id") == EXTENDED500_PLAN_ID
        and all(_ident(binding.get(key)) for key in (
            "owner_user_id", "scan_id", "project_id", "request_id", "idempotency_key", "access_id"))
        and _attempt(binding.get("attempt_count")) is not None
        and isinstance(binding.get("queue_path"), str)
        and bool(_QUEUE_PATH.fullmatch(binding["queue_path"]))
    )


def _revalidation(binding: Mapping[str, Any], execution_id: Any) -> _Evaluation:
    claimed = {key: binding[key] for key in (
        "scan_id", "owner_user_id", "project_id", "request_id", "idempotency_key",
        "attempt_count", "website_url", "path_prefix", "respect_robots_txt",
        "owner_attested_robots_override", "access_id", "request_fingerprint", "task_name",
    )}
    return _Evaluation("revalidation", claimed, binding["queue_path"], execution_id)


def _as_revalidation(refusal: _Refusal) -> RevalidationDecision:
    return RevalidationDecision(UNAVAILABLE if refusal.outcome == RETRY else ABORT, refusal.reason)


def evaluate_extended500_revalidation(
    binding: Any,
    evidence: Mapping[str, Any],
    *,
    execution_id: Any,
    now: Any,
) -> RevalidationDecision:
    """Re-check a running execution before a side effect (e.g. persisting).

    Every fresh source must still authorize the SAME binding: active paid
    Extended 500 Access with the same id, non-terminal current-attempt
    ScanRun, and the coordinator slot+receipt still carrying this executor's
    pickup claim. ``unavailable`` is NOT permission; only ``continue`` is.
    """
    if not _binding_valid(binding):
        return RevalidationDecision(ABORT, "binding_invalid")
    if not _ident(execution_id):
        return RevalidationDecision(ABORT, "execution_id_invalid")
    if not _aware(now):
        return RevalidationDecision(ABORT, "clock_invalid")
    check = _revalidation(binding, execution_id)
    try:
        if not isinstance(evidence, Mapping) or any(key not in evidence for key in EVIDENCE_KEYS):
            _refuse(DENY, "evidence_incomplete")
        check.check_scan(evidence["scan_run"], now)
        check.check_project(evidence["business_project"], now)
        check.check_owner(evidence["owner_user"], now)
        check.check_access(evidence["access_by_owner"], evidence["access_by_email"], now)
        check.check_reservation(evidence["owner_slot"], evidence["request_receipt"], now)
    except _Refusal as refusal:
        return _as_revalidation(refusal)
    return RevalidationDecision(CONTINUE, "fresh_authorization_still_valid")


async def revalidate_extended500_pickup(
    binding: Any,
    sources: Any,
    *,
    execution_id: Any,
    clock: Callable[[], datetime] = _utc_now,
) -> RevalidationDecision:
    """Fresh re-read of every authority using binding (server-derived) keys."""
    if not _binding_valid(binding):
        return RevalidationDecision(ABORT, "binding_invalid")
    if not _ident(execution_id):
        return RevalidationDecision(ABORT, "execution_id_invalid")
    check = _revalidation(binding, execution_id)
    evidence: dict[str, Any] = {}
    try:
        evidence["scan_run"] = await _read(sources, "read_scan_run", binding["scan_id"], clock)
        check.check_scan(evidence["scan_run"], clock())
        evidence["business_project"] = await _read(
            sources, "read_business_project", binding["project_id"], clock)
        evidence["owner_user"] = await _read(sources, "read_owner_user", binding["owner_user_id"], clock)
        check.check_owner(evidence["owner_user"], clock())
        evidence["access_by_owner"] = await _read(
            sources, "filter_access_by_owner", binding["owner_user_id"], clock)
        evidence["access_by_email"] = await _read(
            sources, "filter_access_by_email", check.owner_email, clock)
        evidence["owner_slot"] = await _read(sources, "read_owner_slot", binding["owner_user_id"], clock)
        evidence["request_receipt"] = await _read(
            sources, "read_request_receipt", binding["receipt_id"], clock)
    except _Refusal as refusal:
        return _as_revalidation(refusal)
    except _SourceFailure as failure:
        return RevalidationDecision(UNAVAILABLE, f"source_unavailable:{failure}")
    return evaluate_extended500_revalidation(binding, evidence, execution_id=execution_id, now=clock())
