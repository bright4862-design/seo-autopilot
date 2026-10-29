"""Serialized integration: a reconciled Base44 seed is required for admission.

Uses the existing coordinator's transactional fake. These tests prove source
routing and fail-closed behaviors, NOT live Firestore CAS or Base44 semantics.
"""
import copy
from concurrent.futures import ThreadPoolExecutor

import pytest

from test_extended500_atomic_service_adapter import (
    STORE, _load, _evidence,
)


def signed_candidate(service, index=None):
    ent, grant = _evidence(service)
    ent["idempotency_key"] = ent["request_id"]
    grant["idempotency_key"] = ent["request_id"]
    if index is not None:
        ent["request_id"] = grant["request_id"] = f"request_{index}"
        ent["idempotency_key"] = grant["idempotency_key"] = f"request_{index}"
        ent["scan_id"] = grant["scan_id"] = f"scan_{index}"
    for doc, key in ((ent, service.ENTITLEMENT_KEY),
                     (grant, service.PREFLIGHT_KEY)):
        doc["proof"] = service.seal(
            {k: v for k, v in doc.items() if k != "proof"}, key,
        )
    return ent, grant


def seeded_records(service, ent, grant):
    claim = service.core.canonical_request(ent)
    a = service.scanrun_seed
    rid = a.seed_receipt_id(claim["owner_user_id"], claim["request_id"])
    record = {
        "schema": a.RECEIPT_SCHEMA,
        "receipt_id": rid, "state": a.SEEDED,
        "owner_user_id": claim["owner_user_id"],
        "project_id": claim["project_id"],
        "request_id": claim["request_id"],
        "idempotency_ref": a.idempotency_ref(
            claim["owner_user_id"], claim["idempotency_key"],
        ),
        "attempt_count": claim["attempt_count"],
        "access_id": claim["access_id"], "scan_id": claim["scan_id"],
        "website_url": grant["website_url"],
        "normalized_domain": "example.com",
        "request_fingerprint": (
            f"extended_500|{grant['website_url']}|root|respect_robots_txt"
        ),
        "scan_mode": "extended_500",
        "scan_source": a.SCAN_SOURCE,
    }
    slot = {
        "schema": a.SLOT_SCHEMA,
        "state": a.SLOT_ACTIVE,
        "owner_user_id": claim["owner_user_id"],
        "request_id": claim["request_id"],
        "receipt_id": rid,
    }
    return record, slot


def record_seed(service, ent, grant):
    seed, slot = seeded_records(service, ent, grant)
    a = service.scanrun_seed
    STORE[f"{a.DEFAULT_COLLECTIONS['receipt']}/{seed['receipt_id']}"] = seed
    STORE[f"{a.DEFAULT_COLLECTIONS['slot']}/{ent['owner_user_id']}"] = slot


def test_reservation_denies_unreconciled_seed_before_any_admission_write(monkeypatch):
    STORE.clear()
    service = _load(monkeypatch)
    ent, grant = signed_candidate(service)
    with pytest.raises(service.core.AdmissionRefused, match="seed_receipt_unavailable"):
        service.reserve_seeded(ent, grant)
    assert STORE == {}


@pytest.mark.parametrize("mutation,error", [
    ("reserved", "seed_not_reconciled"),
    ("create_pending", "seed_not_reconciled"),
    ("create_uncertain", "seed_not_reconciled"),
    ("released", "seed_not_reconciled"),
    ("foreign_scan", "seed_admission_identity_mismatch"),
    ("foreign_owner", "seed_admission_identity_mismatch"),
    ("foreign_project", "seed_admission_identity_mismatch"),
    ("foreign_access", "seed_admission_identity_mismatch"),
    ("foreign_idem", "seed_admission_identity_mismatch"),
    ("wrong_attempt", "seed_admission_identity_mismatch"),
    ("wrong_site", "seed_target_mismatch"),
    ("wrong_domain", "seed_target_mismatch"),
    ("wrong_fingerprint", "seed_target_mismatch"),
    ("wrong_source", "seed_admission_identity_mismatch"),
    ("slot_missing", "seed_owner_slot_not_bound"),
    ("slot_foreign_request", "seed_owner_slot_not_bound"),
    ("slot_released", "seed_owner_slot_not_bound"),
])
def test_seed_tampering_cannot_reserve_slot(monkeypatch, mutation, error):
    STORE.clear()
    service = _load(monkeypatch)
    ent, grant = signed_candidate(service)
    seed, slot = seeded_records(service, ent, grant)
    if mutation in {"reserved", "create_pending", "create_uncertain", "released"}:
        seed["state"] = mutation
    elif mutation == "foreign_scan":
        seed["scan_id"] = "other"
    elif mutation == "foreign_owner":
        seed["owner_user_id"] = "other"
    elif mutation == "foreign_project":
        seed["project_id"] = "other"
    elif mutation == "foreign_access":
        seed["access_id"] = "other"
    elif mutation == "foreign_idem":
        seed["idempotency_ref"] = "bad"
    elif mutation == "wrong_attempt":
        seed["attempt_count"] = 2
    elif mutation == "wrong_site":
        seed["website_url"] = "https://wrong.com/"
    elif mutation == "wrong_domain":
        seed["normalized_domain"] = "wrong.com"
    elif mutation == "wrong_fingerprint":
        seed["request_fingerprint"] = "other"
    elif mutation == "wrong_source":
        seed["scan_source"] = "standard150"
    elif mutation == "slot_missing":
        slot = None
    elif mutation == "slot_foreign_request":
        slot["request_id"] = "other"
    elif mutation == "slot_released":
        slot["state"] = "released"
    a = service.scanrun_seed
    STORE[f"{a.DEFAULT_COLLECTIONS['receipt']}/{seed['receipt_id']}"] = seed
    if slot is not None:
        STORE[f"{a.DEFAULT_COLLECTIONS['slot']}/{ent['owner_user_id']}"] = slot
    before = copy.deepcopy(STORE)
    with pytest.raises(service.core.AdmissionRefused, match=error):
        service.reserve_seeded(ent, grant)
    assert STORE == before


def test_verified_seed_can_reserve_and_replay_without_new_receipt(monkeypatch):
    STORE.clear()
    service = _load(monkeypatch)
    ent, grant = signed_candidate(service)
    record_seed(service, ent, grant)
    first = service.reserve_seeded(ent, grant)
    assert first["outcome"] == "reserved"
    assert len(STORE) == 4  # two seed docs plus two admission docs
    assert service.reserve_seeded(ent, grant)["outcome"] == "replayed"
    assert len(STORE) == 4
    assert service.QUEUE_ENABLED is False and service.WORKER_READY is False


def test_many_contending_admission_requests_only_seeded_owner_wins(monkeypatch):
    STORE.clear()
    service = _load(monkeypatch)
    candidates = [signed_candidate(service, i) for i in range(12)]
    record_seed(service, *candidates[0])
    def attempt(pair):
        try:
            return service.reserve_seeded(*pair)["outcome"]
        except service.core.AdmissionRefused as exc:
            return exc.code
    with ThreadPoolExecutor(max_workers=12) as pool:
        outcomes = list(pool.map(attempt, candidates))
    assert outcomes.count("reserved") == 1, outcomes
    assert all(x == "seed_receipt_unavailable" for x in outcomes[1:])
    assert len(STORE) == 4


def test_live_reservation_route_calls_seed_fenced_path_only(monkeypatch):
    STORE.clear()
    service = _load(monkeypatch)
    ent, grant = signed_candidate(service)
    monkeypatch.setattr(service, "QUEUE_ENABLED", True)
    monkeypatch.setattr(service, "WORKER_READY", True)
    monkeypatch.setattr(service, "authenticate",
                        lambda: ({"entitlement": ent, "preflight_grant": grant}, None))
    monkeypatch.setattr(service, "enqueue", lambda *_: "enqueued")
    monkeypatch.setattr(service, "update_dispatch_state", lambda *_: None)
    def no_legacy(*_):
        raise AssertionError("unsafe legacy reserve path must never be invoked")
    monkeypatch.setattr(service, "reserve", no_legacy)
    response, status = service.reservation_route()
    assert status == 409
    assert response["error"] == "seed_receipt_unavailable"
    assert STORE == {}
    record_seed(service, ent, grant)
    response, status = service.reservation_route()
    assert status == 200
    assert response["state"] == "enqueued"
    assert response["admitted"] is False
    assert response["worker_execution_enabled"] is False


def test_real_seed_seeder_receipt_can_be_admitted_without_manual_seed_forgery(monkeypatch):
    """Connect the ACTUAL A seeder output to the ACTUAL coordinator transaction."""
    from test_extended500_scanrun_seed import make_draft, make_access, make_seeder
    STORE.clear()
    service = _load(monkeypatch)
    draft = make_draft(owner="owner_500", project="project_500", request="request_500",
                       access_id="access_500", site="https://example.com/")
    access = make_access(owner="owner_500", access_id="access_500")
    seeder, seedstore, base44 = make_seeder()
    created = seeder.submit(draft, access)
    assert created["outcome"] == "created"
    assert created["state"] == "seeded"
    assert base44.create_calls == 1
    ent, grant = signed_candidate(service)
    ent["scan_id"] = grant["scan_id"] = created["scan_id"]
    for document, key in ((ent, service.ENTITLEMENT_KEY), (grant, service.PREFLIGHT_KEY)):
        document["proof"] = service.seal(
            {k: v for k, v in document.items() if k != "proof"}, key,
        )
    for (collection, doc_id), doc in seedstore.all_docs().items():
        STORE[f"{collection}/{doc_id}"] = doc
    accepted = service.reserve_seeded(ent, grant)
    assert accepted["outcome"] == "reserved"
    assert service.reserve_seeded(ent, grant)["outcome"] == "replayed"
    assert base44.create_calls == 1


def test_lost_base44_create_response_blocks_admission_until_exact_reconciliation(monkeypatch):
    """Never let an uncertain initial create become an authorized crawl."""
    from test_extended500_scanrun_seed import make_draft, make_access, make_seeder
    STORE.clear()
    service = _load(monkeypatch)
    draft = make_draft(owner="owner_500", project="project_500", request="request_500",
                       access_id="access_500", site="https://example.com/")
    access = make_access(owner="owner_500", access_id="access_500")
    seeder, seedstore, base44 = make_seeder()
    base44.mode = "lose_response"
    pending = seeder.submit(draft, access)
    assert pending["state"] == "create_uncertain"
    assert base44.create_calls == 1
    ent, grant = signed_candidate(service)
    ent["scan_id"] = grant["scan_id"] = "scanrun_1"
    for document, key in ((ent, service.ENTITLEMENT_KEY), (grant, service.PREFLIGHT_KEY)):
        document["proof"] = service.seal(
            {k: v for k, v in document.items() if k != "proof"}, key,
        )
    for (collection, doc_id), doc in seedstore.all_docs().items():
        STORE[f"{collection}/{doc_id}"] = doc
    with pytest.raises(service.core.AdmissionRefused, match="seed_not_reconciled"):
        service.reserve_seeded(ent, grant)
    assert not any(k.startswith("extended500_request_receipts/") for k in STORE)
    recovered = seeder.reconcile(draft, access)
    assert recovered["outcome"] == "reconciled"
    assert recovered["scan_id"] == "scanrun_1"
    assert base44.create_calls == 1, "lost create response must NEVER create twice"
    for (collection, doc_id), doc in seedstore.all_docs().items():
        STORE[f"{collection}/{doc_id}"] = doc
    assert service.reserve_seeded(ent, grant)["outcome"] == "reserved"
    assert base44.create_calls == 1
