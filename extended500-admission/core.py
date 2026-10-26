"""Extended 500 reservation decisions. No Firestore, HTTP, or Cloud Tasks imports.

Atomicity is supplied by the Firestore adapter: read owner-slot and immutable
request receipt, then commit both writes in ONE transaction. Retrying after an
unknown Cloud Tasks outcome uses the *same* deterministic task name.
A released request receipt remains a tombstone; it can never be re-admitted.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

MODE = "extended_500"
PLAN = "extended500_lifetime"
ENTITLEMENT_VERSION = "extended500_paid_entitlement_v1"
SLOT_SCHEMA = "extended500_owner_slot_v1"
RECEIPT_SCHEMA = "extended500_request_receipt_v1"
TASK_PREFIX = "extended500-"
IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
ACTIVE_STATES = frozenset({"reserved", "dispatch_unknown", "enqueued"})
TERMINALS = frozenset({"complete", "limited", "failed", "cancelled"})


class AdmissionRefused(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def required_identifier(value: Any, field: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise AdmissionRefused("invalid_" + field)
    return value


def safe_attempt(value: Any) -> int:
    if type(value) is not int or not 1 <= value <= 100_000:
        raise AdmissionRefused("invalid_attempt_count")
    return value


def canonical_request(entitlement: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(entitlement, dict):
        raise AdmissionRefused("invalid_entitlement")
    if entitlement.get("version") != ENTITLEMENT_VERSION or entitlement.get("plan_id") != PLAN:
        raise AdmissionRefused("wrong_entitlement_plan")
    if entitlement.get("scan_mode") != MODE:
        raise AdmissionRefused("invalid_scan_mode")
    request = {
        "owner_user_id": required_identifier(entitlement.get("owner_user_id"), "owner_user_id"),
        "scan_id": required_identifier(entitlement.get("scan_id"), "scan_id"),
        "project_id": required_identifier(entitlement.get("project_id"), "project_id"),
        "request_id": required_identifier(entitlement.get("request_id"), "request_id"),
        "idempotency_key": required_identifier(entitlement.get("idempotency_key"), "idempotency_key"),
        "access_id": required_identifier(entitlement.get("access_id"), "access_id"),
        "attempt_count": safe_attempt(entitlement.get("attempt_count")),
    }
    if entitlement.get("entitlement_state") != "active_paid":
        raise AdmissionRefused("paid_entitlement_required")
    return request


def fingerprint(request: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(
        request, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode()).hexdigest()


def receipt_id(request: dict[str, Any]) -> str:
    # Stable, collision-resistant and free of customer-controlled document-path
    # separators. A receipt is never deleted/reused after terminal release.
    return hashlib.sha256(
        (request["owner_user_id"] + "\n" + request["request_id"]).encode()
    ).hexdigest()


def task_name(queue_path: str, request: dict[str, Any]) -> str:
    if not re.fullmatch(
        r"projects/[A-Za-z0-9_-]+/locations/[A-Za-z0-9_-]+/queues/[A-Za-z0-9_-]+",
        queue_path,
    ):
        raise AdmissionRefused("invalid_extended500_queue_path")
    # Naming by exact immutable request receipt rather than delivery-time retry
    # lets a 409 ALREADY_EXISTS mean a duplicate of *this* owner/request only.
    return f"{queue_path}/tasks/{TASK_PREFIX}{receipt_id(request)}-a{request['attempt_count']}"


def decide_reservation(
    slot: dict[str, Any] | None,
    receipt: dict[str, Any] | None,
    entitlement: dict[str, Any],
    queue_path: str,
    *,
    issued_at: int,
) -> dict[str, Any]:
    request = canonical_request(entitlement)
    fp = fingerprint(request)
    rid = receipt_id(request)
    name = task_name(queue_path, request)

    if receipt is not None:
        if (receipt.get("schema") != RECEIPT_SCHEMA or receipt.get("fingerprint") != fp
                or receipt.get("receipt_id") != rid or receipt.get("task_name") != name):
            raise AdmissionRefused("request_replay_conflict")
        if receipt.get("state") == "released":
            return {"outcome": "terminal_replay", "receipt_id": rid, "task_name": name}
        if receipt.get("state") not in ACTIVE_STATES:
            raise AdmissionRefused("receipt_state_invalid")
        if not isinstance(slot, dict) or slot.get("receipt_id") != rid or slot.get("state") not in ACTIVE_STATES:
            raise AdmissionRefused("reservation_integrity_mismatch")
        return {"outcome": "replayed", "receipt_id": rid, "task_name": name}

    # No lease expiry automatically frees an active slot. A delayed Cloud Task
    # remains executable until a *verified exact terminal* release is committed.
    if isinstance(slot, dict) and slot.get("state") in ACTIVE_STATES:
        raise AdmissionRefused("owner_slot_busy")
    if slot is not None and slot.get("state") not in ("released",):
        raise AdmissionRefused("owner_slot_integrity_invalid")

    new_receipt = {
        "schema": RECEIPT_SCHEMA,
        "receipt_id": rid,
        "fingerprint": fp,
        "owner_user_id": request["owner_user_id"],
        "request_id": request["request_id"],
        "scan_id": request["scan_id"],
        "attempt_count": request["attempt_count"],
        "task_name": name,
        "state": "reserved",
        "issued_at": issued_at,
    }
    new_slot = {
        "schema": SLOT_SCHEMA,
        "owner_user_id": request["owner_user_id"],
        "receipt_id": rid,
        "request_id": request["request_id"],
        "scan_id": request["scan_id"],
        "attempt_count": request["attempt_count"],
        "state": "reserved",
        "issued_at": issued_at,
    }
    return {
        "outcome": "reserved", "receipt_id": rid, "task_name": name,
        "receipt_write": new_receipt, "slot_write": new_slot,
    }


def decide_dispatch_state(
    slot: dict[str, Any],
    receipt: dict[str, Any],
    *,
    state: str,
) -> dict[str, Any]:
    if state not in ("dispatch_unknown", "enqueued"):
        raise AdmissionRefused("invalid_dispatch_state")
    if not isinstance(slot, dict) or not isinstance(receipt, dict):
        raise AdmissionRefused("reservation_not_found")
    if slot.get("receipt_id") != receipt.get("receipt_id"):
        raise AdmissionRefused("reservation_integrity_mismatch")
    if slot.get("state") not in ACTIVE_STATES or receipt.get("state") not in ACTIVE_STATES:
        raise AdmissionRefused("already_released")
    if receipt.get("state") == "enqueued" and state == "dispatch_unknown":
        # A late network failure must not downgrade known successful enqueue.
        return {"outcome": "unchanged"}
    return {
        "outcome": "updated",
        "slot_write": {**slot, "state": state},
        "receipt_write": {**receipt, "state": state},
    }


def decide_release(
    slot: dict[str, Any] | None,
    receipt: dict[str, Any] | None,
    request: dict[str, Any],
    *,
    terminal_status: str,
    verified_terminal: bool,
    released_at: int,
) -> dict[str, Any]:
    if terminal_status not in TERMINALS or verified_terminal is not True:
        raise AdmissionRefused("verified_terminal_required")
    if not isinstance(receipt, dict) or receipt.get("schema") != RECEIPT_SCHEMA:
        raise AdmissionRefused("reservation_not_found")
    if receipt.get("fingerprint") != fingerprint(request):
        raise AdmissionRefused("release_identity_mismatch")
    if receipt.get("state") == "released":
        if receipt.get("terminal_status") == terminal_status:
            return {"outcome": "already_released"}
        raise AdmissionRefused("terminal_conflict")
    if not isinstance(slot, dict) or slot.get("receipt_id") != receipt.get("receipt_id"):
        raise AdmissionRefused("owner_slot_mismatch")
    if slot.get("state") not in ACTIVE_STATES or receipt.get("state") not in ACTIVE_STATES:
        raise AdmissionRefused("reservation_integrity_mismatch")
    return {
        "outcome": "released",
        "slot_write": {**slot, "state": "released", "released_at": released_at, "terminal_status": terminal_status},
        "receipt_write": {**receipt, "state": "released", "released_at": released_at, "terminal_status": terminal_status},
    }
