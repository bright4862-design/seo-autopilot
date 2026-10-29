"""Single-use Extended 500 Firestore pickup CAS, deliberately NOT worker execution.

Requires Agent B's fresh service-role authorization and trusted Cloud Run OIDC
context. Uses exactly one Firestore transaction for owner slot, request receipt,
and immutable pickup claim. A claim's existence forever fences task retries.
The claimed result remains INERT until a separately reviewed entitlement
revocation barrier, live IAM, reviewer and persistence path are operational.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Any, Callable, Protocol, TypeVar

from .extended500_pickup_authorization import authorize_extended500_pickup, PickupReader

T = TypeVar("T")
PICKUP_COLLECTION = "extended500_pickup_claims"
SLOT_COLLECTION = "extended500_owner_slots"
RECEIPT_COLLECTION = "extended500_request_receipts"
CLAIM_SCHEMA = "extended500_pickup_claim_v1"
SLOT_SCHEMA = "extended500_owner_slot_v1"
RECEIPT_SCHEMA = "extended500_request_receipt_v1"


class PickupTransaction(Protocol):
    def get(self, collection: str, doc_id: str) -> dict[str, Any] | None: ...
    def create(self, collection: str, doc_id: str, value: dict[str, Any]) -> None: ...


class PickupClaimStore(Protocol):
    def run_in_transaction(self, callback: Callable[[PickupTransaction], T]) -> T: ...


@dataclass(frozen=True)
class PickupClaimDecision:
    code: str
    receipt_id: str = ""
    task_name: str = ""
    claimed: bool = False
    # True pickup execution requires independent service authorization and
    # a separate reviewed, deployment-verified final boundary.
    execution_allowed: bool = False


def _fingerprint(task: dict, access_id: str) -> str:
    request = {
        "owner_user_id": task["owner_user_id"],
        "scan_id": task["scan_id"],
        "project_id": task["project_id"],
        "request_id": task["request_id"],
        "idempotency_key": task["idempotency_key"],
        "access_id": access_id,
        "attempt_count": task["attempt_count"],
    }
    return hashlib.sha256(json.dumps(
        request, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode()).hexdigest()


def claim_extended500_pickup(
    task: dict[str, Any], reader: PickupReader, store: PickupClaimStore, *,
    signing_key: str, queue_path: str, trusted_task_name: str,
    verified_private_invoker: bool = False, feature_enabled: bool = False,
    now: datetime | None = None,
) -> PickupClaimDecision:
    """Read exact paid authority then commit one *inert* pickup claim.

    Calling code must authenticate Cloud Run invoker identity OUTSIDE task
    headers. Source reads and Firestore CAS are separate backends: this does
    NOT grant work execution and a paid revocation barrier is still required.
    """
    preflight = authorize_extended500_pickup(
        task, reader, signing_key=signing_key, queue_path=queue_path,
        trusted_task_name=trusted_task_name,
        verified_private_invoker=verified_private_invoker,
        feature_enabled=feature_enabled, now=now,
    )
    if not preflight.ready_for_atomic_claim or preflight.execution_allowed:
        return PickupClaimDecision(preflight.code)
    rid, name = preflight.receipt_id, preflight.task_name
    owner, request_id, scan_id = task["owner_user_id"], task["request_id"], task["scan_id"]
    try:
        # This second service-role read is advisory; the claim is still inert
        # because revocation may race against the Firestore transaction.
        scan = reader.read_scanrun(scan_id)
        if not isinstance(scan, dict) or scan.get("id") != scan_id:
            return PickupClaimDecision("scan_missing_after_preflight")
        fingerprint = _fingerprint(task, scan["admission_access_id"])

        def apply(tx: PickupTransaction) -> str:
            # ALL reads before any write; Firestore serializes collisions.
            slot = tx.get(SLOT_COLLECTION, owner)
            receipt = tx.get(RECEIPT_COLLECTION, rid)
            duplicate = tx.get(PICKUP_COLLECTION, rid)
            if duplicate is not None:
                return "pickup_already_claimed"
            if not isinstance(slot, dict) or not isinstance(receipt, dict):
                return "reservation_missing_at_cas"
            if (
                slot.get("schema") != SLOT_SCHEMA
                or receipt.get("schema") != RECEIPT_SCHEMA
                or slot.get("state") != "enqueued"
                or receipt.get("state") != "enqueued"
                or slot.get("owner_user_id") != owner
                or receipt.get("owner_user_id") != owner
                or slot.get("receipt_id") != rid
                or receipt.get("receipt_id") != rid
                or slot.get("request_id") != request_id
                or receipt.get("request_id") != request_id
                or slot.get("scan_id") != scan_id
                or receipt.get("scan_id") != scan_id
                or slot.get("attempt_count") != task["attempt_count"]
                or receipt.get("attempt_count") != task["attempt_count"]
                or receipt.get("task_name") != name
                or receipt.get("fingerprint") != fingerprint
            ):
                return "pickup_cas_reservation_changed"
            # Claimed once, never automatically freed on task timeout,
            # deployment restart, unknown outcome, revocation or failed review.
            tx.create(PICKUP_COLLECTION, rid, {
                "schema": CLAIM_SCHEMA,
                "receipt_id": rid,
                "owner_user_id": owner,
                "scan_id": scan_id,
                "project_id": task["project_id"],
                "request_id": request_id,
                "idempotency_key_digest": hashlib.sha256(
                    task["idempotency_key"].encode("utf-8")
                ).hexdigest(),
                "attempt_count": task["attempt_count"],
                "task_name": name,
                "reservation_fingerprint": fingerprint,
                "state": "claimed_execution_disabled",
                "execution_allowed": False,
            })
            return "claimed_execution_disabled"

        code = store.run_in_transaction(apply)
    except Exception:
        # Unknown transaction outcomes are NOT retried as a second attempt.
        return PickupClaimDecision("pickup_claim_outcome_unknown", rid, name)
    return PickupClaimDecision(
        code=code, receipt_id=rid, task_name=name,
        claimed=code == "claimed_execution_disabled",
    )


class FirestorePickupClaimStore:
    """Injectable Cloud Firestore transactional port, NOT exercised live.

    The operator must inject a correctly scoped google.cloud.firestore.Client
    and firestore.transactional decorator. This adapter has NO account
    credentials in source, no endpoint and never launches a crawler.
    """

    def __init__(self, client: Any, transactional: Callable[..., Any]):
        if client is None or not callable(transactional):
            raise ValueError("Firestore client and transaction decorator required")
        self.client = client
        self.transactional = transactional

    def run_in_transaction(self, callback: Callable[[PickupTransaction], T]) -> T:
        @self.transactional
        def run(transaction):
            return callback(_FirestorePickupView(self.client, transaction))
        return run(self.client.transaction())


class _FirestorePickupView:
    def __init__(self, client: Any, transaction: Any):
        self.client = client
        self.transaction = transaction

    def _ref(self, collection: str, doc_id: str):
        if collection not in (PICKUP_COLLECTION, SLOT_COLLECTION, RECEIPT_COLLECTION):
            raise ValueError("foreign extended500 collection")
        if not isinstance(doc_id, str) or not doc_id:
            raise ValueError("invalid Firestore document identity")
        return self.client.collection(collection).document(doc_id)

    def get(self, collection: str, doc_id: str) -> dict[str, Any] | None:
        snap = self._ref(collection, doc_id).get(transaction=self.transaction)
        return snap.to_dict() if snap.exists else None

    def create(self, collection: str, doc_id: str, value: dict[str, Any]) -> None:
        self.transaction.create(self._ref(collection, doc_id), value)
