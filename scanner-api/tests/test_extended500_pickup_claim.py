"""Atomic pickup claim integration tests — still never permits crawl execution."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import RLock

import pytest

from app.extended500_pickup_claim import (
    claim_extended500_pickup,
    CLAIM_SCHEMA,
    PICKUP_COLLECTION, SLOT_COLLECTION, RECEIPT_COLLECTION,
)
from test_extended500_pickup_authorization import fixture, KEY, QUEUE, NOW


class FakeTransaction:
    def __init__(self, items):
        self.items = items
        self.writes = []

    def get(self, collection, doc_id):
        return deepcopy(self.items.get(f"{collection}/{doc_id}"))

    def create(self, collection, doc_id, value):
        self.writes.append((f"{collection}/{doc_id}", deepcopy(value)))

    def commit(self):
        for key, _ in self.writes:
            if key in self.items:
                raise RuntimeError("Firestore already exists")
        for key, value in self.writes:
            self.items[key] = value


class FakeStore:
    def __init__(self, task, reader, *, explode=False):
        self.items = {
            f"{SLOT_COLLECTION}/{task['owner_user_id']}": deepcopy(reader.slot),
            f"{RECEIPT_COLLECTION}/{reader.receipt['receipt_id']}": deepcopy(reader.receipt),
        }
        self.lock = RLock()
        self.explode = explode
        self.commits = 0

    def run_in_transaction(self, callback):
        with self.lock:
            if self.explode:
                raise RuntimeError("Unknown Firestore commit outcome")
            tx = FakeTransaction(self.items)
            result = callback(tx)
            tx.commit()
            self.commits += 1
            return result


def run(task, reader, name, store, **kw):
    settings = dict(signing_key=KEY, queue_path=QUEUE, trusted_task_name=name,
                    verified_private_invoker=True, feature_enabled=True, now=NOW)
    settings.update(kw)
    return claim_extended500_pickup(task, reader, store, **settings)


def test_valid_paid_owner_task_creates_one_inert_immutable_claim():
    task, reader, name = fixture()
    store = FakeStore(task, reader)
    result = run(task, reader, name, store)
    assert result.code == "claimed_execution_disabled"
    assert result.claimed is True
    assert result.execution_allowed is False
    assert result.task_name == name
    key = f"{PICKUP_COLLECTION}/{reader.receipt['receipt_id']}"
    row = store.items[key]
    assert row["schema"] == CLAIM_SCHEMA
    assert row["scan_id"] == task["scan_id"]
    assert row["owner_user_id"] == task["owner_user_id"]
    assert row["request_id"] == task["request_id"]
    assert row["state"] == "claimed_execution_disabled"
    assert row["execution_allowed"] is False
    assert row["reservation_fingerprint"] == reader.receipt["fingerprint"]
    assert "stripe_checkout_session_id" not in row
    assert "idempotency_key" not in row


def test_twelve_concurrent_deliveries_admit_only_one_claim_without_execution():
    task, reader, name = fixture()
    store = FakeStore(task, reader)
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(lambda _: run(task, reader, name, store), range(12)))
    assert sum(x.claimed for x in results) == 1, results
    assert sorted(x.code for x in results) == [
        "claimed_execution_disabled",
        *(["pickup_already_claimed"] * 11),
    ]
    assert not any(x.execution_allowed for x in results)
    assert len([k for k in store.items if k.startswith(PICKUP_COLLECTION + "/")]) == 1


@pytest.mark.parametrize("mutate", [
    lambda slot, receipt: slot.update(state="reserved"),
    lambda slot, receipt: slot.update(state="dispatch_unknown"),
    lambda slot, receipt: receipt.update(state="dispatch_unknown"),
    lambda slot, receipt: receipt.update(task_name="wrong-task"),
    lambda slot, receipt: slot.update(scan_id="wrong-scan"),
    lambda slot, receipt: receipt.update(fingerprint="0" * 64),
    lambda slot, receipt: slot.update(attempt_count=2),
    lambda slot, receipt: receipt.update(receipt_id="wrong"),
    lambda slot, receipt: slot.update(owner_user_id="attacker"),
])
def test_reservation_changed_between_preflight_and_atomic_claim_fails(mutate):
    task, reader, name = fixture()
    store = FakeStore(task, reader)
    slot = store.items[f"{SLOT_COLLECTION}/{task['owner_user_id']}"]
    receipt = store.items[f"{RECEIPT_COLLECTION}/{reader.receipt['receipt_id']}"]
    mutate(slot, receipt)
    result = run(task, reader, name, store)
    assert result.code == "pickup_cas_reservation_changed"
    assert not result.claimed and not result.execution_allowed
    assert not any(k.startswith(PICKUP_COLLECTION + "/") for k in store.items)


def test_missing_or_ambiguous_firestore_state_does_not_launch_scan():
    task, reader, name = fixture()
    store = FakeStore(task, reader)
    store.items.pop(f"{SLOT_COLLECTION}/{task['owner_user_id']}")
    result = run(task, reader, name, store)
    assert result.code == "reservation_missing_at_cas"
    assert not result.claimed

    error_store = FakeStore(task, reader, explode=True)
    result = run(task, reader, name, error_store)
    assert result.code == "pickup_claim_outcome_unknown"
    assert not result.claimed and not result.execution_allowed


def test_paid_grant_revocation_and_invoker_failure_do_not_open_transaction():
    task, reader, name = fixture()
    store = FakeStore(task, reader)
    reader.rows[0]["access_status"] = "revoked"
    result = run(task, reader, name, store)
    assert result.code == "paid_access_not_active"
    assert store.commits == 0

    reader.rows[0]["access_status"] = "active"
    result = run(task, reader, name, store, verified_private_invoker=False)
    assert result.code == "private_invoker_required"
    assert store.commits == 0

    result = run(task, reader, name, store, feature_enabled=False)
    assert result.code == "pickup_disabled"
    assert store.commits == 0


def test_disabled_pickup_never_contacts_durable_sources():
    task, reader, name = fixture()
    reader.fail_method = "scan"
    store = FakeStore(task, reader, explode=True)
    result = run(task, reader, name, store, feature_enabled=False)
    assert result.code == "pickup_disabled"
    assert reader.calls == []
    assert store.commits == 0
