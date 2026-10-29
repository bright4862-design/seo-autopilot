"""Extended 500 initial ScanRun seed: CAS receipts and crash-safe single create.

Fully offline. A synthetic optimistic-concurrency transactional store stands in
for Firestore and an in-memory fake stands in for Base44 service-role
ScanRun.create/filter. These prove the state machine and adapter contract,
NOT real Firestore serializability (UNVERIFIED) or Base44 behaviour.
"""
import copy
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

ROOT = Path(__file__).resolve().parents[2]
SERVICE_DIR = ROOT / "extended500-admission"
sys.path.insert(0, str(SERVICE_DIR))
try:
    _spec = importlib.util.spec_from_file_location(
        "extended500_scanrun_seed", SERVICE_DIR / "scanrun_seed.py")
    seed = importlib.util.module_from_spec(_spec)
    assert _spec and _spec.loader
    _spec.loader.exec_module(seed)
finally:
    sys.path.remove(str(SERVICE_DIR))
core = seed.core

ACCESS_SESSION = "cs_test_secret_session_500"


# --------------------------------------------------------------- fixtures

def make_draft(owner="owner_one", project="project_one", request="req_500_once",
               idem=None, access_id="access_extended", site="https://www.example.com/", **over):
    record = {
        "project_id": project, "owner_user_id": owner,
        "website_url": site, "submitted_url": site,
        "normalized_domain": site.split("//", 1)[1].rstrip("/").removeprefix("www."),
        "scan_mode": "extended_500", "status": "queued",
        "scan_source": "extended500_private_candidate",
        "request_id": request, "idempotency_key": idem or request,
        "request_fingerprint": f"extended_500|{site}|root|respect_robots_txt",
        "attempt_count": 1, "queued_at": "2026-10-28T12:00:00.000Z",
        "respect_robots_txt": True, "owner_attested_robots_override": False,
        "admission_access_id": access_id,
        "pages_found": 0, "pages_crawled": 0, "pages_retained": 0,
        "release_gate_eligible": False, "review_confidence_state": "not_reviewed",
    }
    record.update(over)
    return {"ok": True, "draft_version": "extended500_scanrun_draft_v1", "record": record}


def make_access(owner="owner_one", access_id="access_extended", **over):
    row = {
        "id": access_id, "owner_user_id": owner, "user_email": f"{owner}@example.com",
        "app_id": "6a498732ec779dfaaeab0e53", "plan_id": "extended500_lifetime",
        "access_status": "active", "has_full_access": True,
        "grant_source": "stripe_checkout", "stripe_checkout_session_id": ACCESS_SESSION,
        "paid_at": "2026-10-27T12:00:00.000Z",
    }
    row.update(over)
    return row


class FakeTransactionalStore:
    """Optimistic, version-checked transactions with retry (Firestore-like).

    Reads record the version they saw; commit validates every read version
    under a short lock and aborts/retries on any interleaved write. This makes
    real thread interleaving possible (no global transaction lock).
    """

    def __init__(self, max_attempts=200, read_delay=0.0005):
        self.docs = {}
        self.lock = threading.Lock()
        self.max_attempts = max_attempts
        self.read_delay = read_delay
        self.commits = 0
        self.aborts = 0

    def run_in_transaction(self, fn):
        for _ in range(self.max_attempts):
            tx = _FakeTx(self)
            try:
                result = fn(tx)
            except Exception:
                # A refusal is only final if it was decided on a consistent
                # snapshot; a torn read is retried (serializable semantics).
                with self.lock:
                    stale = not self._reads_current(tx)
                if stale:
                    self.aborts += 1
                    continue
                raise  # nothing committed
            with self.lock:
                if self._reads_current(tx):
                    for op, key, value in tx.writes:
                        version, current = self.docs.get(key, (0, None))
                        if op == "create" and current is not None:
                            raise AssertionError("create on existing doc that was read as absent")
                        self.docs[key] = (version + 1, copy.deepcopy(value))
                    self.commits += 1
                    return result
                self.aborts += 1
        raise seed.SeedStoreContention()

    def _reads_current(self, tx):
        return all(self.docs.get(k, (0, None))[0] == v for k, v in tx.reads.items())

    def value(self, collection, doc_id):
        return copy.deepcopy(self.docs.get((collection, doc_id), (0, None))[1])

    def all_docs(self):
        return {key: copy.deepcopy(value) for key, (_, value) in self.docs.items()}


class _FakeTx:
    def __init__(self, store):
        self.store, self.reads, self.writes = store, {}, []

    def get(self, collection, doc_id):
        assert not self.writes, "read after write in transaction"
        key = (collection, doc_id)
        with self.store.lock:
            version, value = self.store.docs.get(key, (0, None))
        self.reads[key] = version
        time.sleep(self.store.read_delay)  # widen interleaving windows
        return copy.deepcopy(value)

    def create(self, collection, doc_id, value):
        self.writes.append(("create", (collection, doc_id), value))

    def set(self, collection, doc_id, value):
        self.writes.append(("set", (collection, doc_id), value))


class SimulatedCrash(BaseException):
    """Process death: not an Exception, so the seeder cannot handle it."""


class FakeBase44:
    def __init__(self):
        self.rows = {}
        self.lock = threading.Lock()
        self.create_calls = 0
        self.lookup_calls = 0
        self.mode = "ok"
        self.hidden = False
        self.create_delay = 0.0
        self.mutate_response = None

    def create(self, record):
        with self.lock:
            self.create_calls += 1
            number = self.create_calls
        if self.mode == "reject":
            raise seed.ScanRunCreateRejected("schema_rejected")
        if self.mode == "crash_before_send":
            raise SimulatedCrash()
        time.sleep(self.create_delay)
        row = {**copy.deepcopy(record), "id": f"scanrun_{number}"}
        with self.lock:
            self.rows[row["id"]] = row
        if self.mode == "lose_response":
            raise seed.ScanRunCreateOutcomeUnknown()
        if self.mode == "timeout":
            raise TimeoutError("read timed out")
        if self.mode == "crash_after_commit":
            raise SimulatedCrash()
        response = copy.deepcopy(row)
        if self.mutate_response:
            response.update(self.mutate_response)
        return response

    def find(self, owner_user_id, request_id):
        with self.lock:
            self.lookup_calls += 1
            if self.hidden:
                return []
            return [copy.deepcopy(r) for r in self.rows.values()
                    if r.get("owner_user_id") == owner_user_id and r.get("request_id") == request_id]

    def forge(self, row):
        with self.lock:
            self.rows[row["id"]] = copy.deepcopy(row)


class Clock:
    def __init__(self, now=1_800_000_000):
        self.now = now

    def __call__(self):
        return self.now


def make_seeder(store=None, base44=None, clock=None, **kwargs):
    store = store or FakeTransactionalStore()
    base44 = base44 or FakeBase44()
    seeder = seed.Extended500ScanRunSeeder(
        store, base44.create, base44.find, enabled=True, clock=clock or Clock(), **kwargs)
    return seeder, store, base44


def receipt_for(store, draft):
    rec = draft["record"]
    return store.value("extended500_seed_receipts",
                       seed.seed_receipt_id(rec["owner_user_id"], rec["request_id"]))


def slot_for(store, owner="owner_one"):
    return store.value("extended500_seed_owner_slots", owner)


def refused(code, fn, *args, **kwargs):
    with pytest.raises(core.AdmissionRefused) as info:
        fn(*args, **kwargs)
    assert info.value.code == code, info.value.code
    return info.value


# ---------------------------------------------------------------- tests

def test_seeder_is_off_by_default_and_touches_nothing():
    store, base44 = FakeTransactionalStore(), FakeBase44()
    seeder = seed.Extended500ScanRunSeeder(store, base44.create, base44.find)
    refused("extended500_seed_disabled", seeder.submit, make_draft(), make_access())
    refused("extended500_seed_disabled", seeder.reconcile, make_draft(), make_access())
    refused("extended500_seed_disabled", seeder.release_after_verified_terminal,
            owner_user_id="owner_one", request_id="req_500_once", scan_id="x",
            terminal_status="complete", verified_terminal=True)
    truthy = seed.Extended500ScanRunSeeder(store, base44.create, base44.find, enabled="true")
    refused("extended500_seed_disabled", truthy.submit, make_draft(), make_access())
    assert store.docs == {} and base44.create_calls == 0 and base44.lookup_calls == 0


def test_seed_collections_are_isolated_from_admission_coordinator():
    store, base44 = FakeTransactionalStore(), FakeBase44()
    for bad in ({"slot": "extended500_owner_slots"}, {"receipt": "extended500_request_receipts"},
                {"slot": "extended500_seed_receipts"}, {"bogus": "x"}):
        with pytest.raises(ValueError):
            seed.Extended500ScanRunSeeder(store, base44.create, base44.find, collections=bad)


def test_real_js_draft_is_accepted_and_create_receives_exactly_that_record():
    script = """
import { buildExtended500QueuedScanDraft } from './src/lib/extended500ScanRunDraft.js';
const user = { id: 'owner_one', email: 'owner_one@example.com' };
const project = { id: 'project_one', owner_user_id: 'owner_one', website_url: 'https://www.example.com/' };
const access = JSON.parse(process.env.SEED_ACCESS);
const draft = buildExtended500QueuedScanDraft({ user, project, accessRows: [access],
  requestId: 'req_500_once', nowMs: Date.parse('2026-10-28T12:00:00.000Z') });
process.stdout.write(JSON.stringify(draft));
"""
    access = make_access()
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script], cwd=ROOT, text=True,
        capture_output=True, check=True, timeout=25,
        env={**os.environ, "SEED_ACCESS": json.dumps(access)},
    )
    js_draft = json.loads(result.stdout)
    assert js_draft == make_draft(), "Python fixture must equal the real JS draft"
    seeder, store, base44 = make_seeder()
    created = []
    original = base44.create
    seeder._create = lambda record: created.append(copy.deepcopy(record)) or original(record)
    outcome = seeder.submit(js_draft, access)
    assert outcome["outcome"] == "created" and outcome["state"] == "seeded"
    assert created == [js_draft["record"]], "no extra/unknown ScanRun fields are sent"
    assert outcome["scan_id"] == "scanrun_1"


def test_single_submit_creates_once_and_exact_replays_never_create_again():
    seeder, store, base44 = make_seeder()
    first = seeder.submit(make_draft(), make_access())
    assert first == {"outcome": "created", "receipt_id": first["receipt_id"], "state": "seeded",
                     "scan_id": "scanrun_1", "create_invoked": True}
    for _ in range(3):
        again = seeder.submit(make_draft(), make_access())
        assert again["outcome"] == "seeded_replay" and again["scan_id"] == "scanrun_1"
        assert again["create_invoked"] is False
    # A brand-new process (restart) replays from the durable receipt.
    restarted, _, _ = make_seeder(store=store, base44=base44)
    assert restarted.submit(make_draft(), make_access())["outcome"] == "seeded_replay"
    assert base44.create_calls == 1
    assert slot_for(store)["state"] == "active"


def test_twelve_contending_identical_submissions_yield_exactly_one_create():
    seeder, store, base44 = make_seeder()
    base44.create_delay = 0.02
    barrier = threading.Barrier(12)

    def go(_):
        barrier.wait()
        return seeder.submit(make_draft(), make_access())

    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(go, range(12)))
    assert base44.create_calls == 1, results
    assert [r["outcome"] for r in results].count("created") == 1
    assert sum(r["create_invoked"] for r in results) == 1
    assert {r["outcome"] for r in results} <= {
        "created", "seeded_replay", "reconciled", "create_in_progress"}
    assert {r["receipt_id"] for r in results} == {results[0]["receipt_id"]}
    assert receipt_for(store, make_draft())["state"] == "seeded"
    assert len(base44.rows) == 1
    after = seeder.submit(make_draft(), make_access())
    assert after["outcome"] == "seeded_replay" and after["scan_id"] == "scanrun_1"


def test_twelve_contending_distinct_requests_one_owner_slot_one_create():
    seeder, store, base44 = make_seeder()
    barrier = threading.Barrier(12)

    def go(n):
        barrier.wait()
        try:
            return ("ok", seeder.submit(make_draft(request=f"req_{n}"), make_access()))
        except core.AdmissionRefused as exc:
            return ("refused", exc.code)

    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(go, range(12)))
    winners = [r for r in results if r[0] == "ok"]
    assert len(winners) == 1 and winners[0][1]["outcome"] == "created", results
    assert sorted(r[1] for r in results if r[0] == "refused") == ["owner_slot_busy"] * 11
    assert base44.create_calls == 1
    receipts = [k for k in store.docs if k[0] == "extended500_seed_receipts"]
    assert len(receipts) == 1
    assert store.aborts > 0, "fake must have exercised real interleaving/retries"


def test_twelve_contending_requests_sharing_one_idempotency_key_bind_once():
    seeder, store, base44 = make_seeder()
    barrier = threading.Barrier(12)

    def go(n):
        barrier.wait()
        try:
            return ("ok", seeder.submit(make_draft(request=f"req_{n}", idem="idem_shared"), make_access()))
        except core.AdmissionRefused as exc:
            return ("refused", exc.code)

    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(go, range(12)))
    assert [r[0] for r in results].count("ok") == 1
    assert {r[1] for r in results if r[0] == "refused"} <= {"idempotency_key_reused", "owner_slot_busy"}
    assert base44.create_calls == 1


def test_lost_create_response_then_retry_and_restart_never_create_again():
    seeder, store, base44 = make_seeder()
    base44.mode, base44.hidden = "lose_response", True
    first = seeder.submit(make_draft(), make_access())
    assert first["outcome"] == "pending_reconciliation" and first["create_invoked"] is True
    assert first["state"] == "create_uncertain" and first["scan_id"] is None
    receipt = receipt_for(store, make_draft())
    assert receipt["uncertain_reason"] == "create_outcome_unknown"
    base44.mode = "ok"  # even a now-healthy Base44 must not see a second create
    for _ in range(3):
        retry = seeder.submit(make_draft(), make_access())
        assert retry["outcome"] == "pending_reconciliation" and retry["create_invoked"] is False
    restarted, _, _ = make_seeder(store=store, base44=base44)
    assert restarted.submit(make_draft(), make_access())["outcome"] == "pending_reconciliation"
    assert base44.create_calls == 1
    # A different request for the same owner is still blocked while uncertain.
    refused("owner_slot_busy", restarted.submit, make_draft(request="req_other"), make_access())
    # The lost row becomes visible: exact server-owned proof reconciles it.
    base44.hidden = False
    done = restarted.reconcile(make_draft(), make_access())
    assert done == {"outcome": "reconciled", "receipt_id": first["receipt_id"], "state": "seeded",
                    "scan_id": "scanrun_1", "create_invoked": False}
    assert seeder.submit(make_draft(), make_access())["outcome"] == "seeded_replay"
    assert base44.create_calls == 1


@pytest.mark.parametrize("mode", ["timeout", "lose_response"])
def test_any_non_definite_create_failure_is_uncertain_not_retried(mode):
    seeder, store, base44 = make_seeder()
    base44.mode = mode
    assert seeder.submit(make_draft(), make_access())["state"] == "create_uncertain"
    base44.mode = "ok"
    assert seeder.submit(make_draft(), make_access())["outcome"] == "reconciled"
    assert base44.create_calls == 1


def test_crash_after_base44_commit_restart_reconciles_without_second_create():
    clock = Clock()
    seeder, store, base44 = make_seeder(clock=clock)
    base44.mode = "crash_after_commit"
    with pytest.raises(SimulatedCrash):
        seeder.submit(make_draft(), make_access())
    assert receipt_for(store, make_draft())["state"] == "create_pending"
    base44.mode = "ok"
    restarted, _, _ = make_seeder(store=store, base44=base44, clock=clock)
    result = restarted.submit(make_draft(), make_access())
    assert result["outcome"] == "reconciled" and result["scan_id"] == "scanrun_1"
    assert base44.create_calls == 1


def test_crash_before_create_sent_stays_pending_and_is_never_auto_created():
    clock = Clock()
    seeder, store, base44 = make_seeder(clock=clock)
    base44.mode = "crash_before_send"
    with pytest.raises(SimulatedCrash):
        seeder.submit(make_draft(), make_access())
    base44.mode = "ok"
    restarted, _, _ = make_seeder(store=store, base44=base44, clock=clock)
    fresh = restarted.submit(make_draft(), make_access())
    assert fresh["outcome"] == "create_in_progress" and fresh["state"] == "create_pending"
    clock.now += seed.DEFAULT_PENDING_STALE_SECONDS
    stale = restarted.submit(make_draft(), make_access())
    assert stale["outcome"] == "pending_reconciliation" and stale["state"] == "create_uncertain"
    assert receipt_for(store, make_draft())["uncertain_reason"] == "create_claim_stale"
    clock.now += 10_000
    assert restarted.submit(make_draft(), make_access())["state"] == "create_uncertain"
    assert base44.create_calls == 1 and base44.rows == {}
    assert slot_for(store)["state"] == "active"


def _uncertain_with_hidden_row():
    seeder, store, base44 = make_seeder()
    base44.mode, base44.hidden = "lose_response", True
    seeder.submit(make_draft(), make_access())
    exact = copy.deepcopy(base44.rows["scanrun_1"])
    base44.rows.clear()
    base44.hidden, base44.mode = False, "ok"
    return seeder, store, base44, exact


@pytest.mark.parametrize("field,value,code", [
    ("owner_user_id", "owner_foreign", "scanrun_proof_owner_mismatch"),
    ("project_id", "project_foreign", "scanrun_proof_project_mismatch"),
    ("scan_mode", "standard_150", "scanrun_proof_mode_mismatch"),
    ("scan_mode", "advanced", "scanrun_proof_mode_mismatch"),
    ("request_id", "req_other", "scanrun_proof_request_mismatch"),
    ("idempotency_key", "idem_other", "scanrun_proof_idempotency_mismatch"),
    ("attempt_count", 2, "scanrun_proof_attempt_mismatch"),
    ("attempt_count", True, "scanrun_proof_attempt_mismatch"),
    ("attempt_count", 1.0, "scanrun_proof_attempt_mismatch"),
    ("admission_access_id", "access_foreign", "scanrun_proof_access_mismatch"),
    ("website_url", "https://evil.example.org/", "scanrun_proof_target_mismatch"),
    ("request_fingerprint", "extended_500|x|root|respect_robots_txt", "scanrun_proof_target_mismatch"),
    ("path_prefix", "/blog", "scanrun_proof_target_mismatch"),
    ("scan_source", "standard_customer", "scanrun_proof_source_mismatch"),
    ("respect_robots_txt", False, "scanrun_proof_robots_mismatch"),
    ("scan_id", "scanrun_other", "scanrun_proof_scan_id_mismatch"),
    ("status", "crawling", "scanrun_proof_status_invalid"),
    ("id", "bad/id", "scanrun_proof_id_invalid"),
])
def test_mismatched_scanrun_proof_is_rejected_and_receipt_stays_pending(field, value, code):
    seeder, store, base44, exact = _uncertain_with_hidden_row()
    # The row's owner/request must still match the lookup filter for the fake
    # to return it; a real filter bug could return a foreign row regardless.
    forged = {**exact, field: value}
    base44.find = lambda owner, request: [copy.deepcopy(forged)]
    seeder._find = base44.find
    before = receipt_for(store, make_draft())
    refused(code, seeder.reconcile, make_draft(), make_access())
    refused(code, seeder.submit, make_draft(), make_access())
    assert receipt_for(store, make_draft()) == before
    assert before["state"] == "create_uncertain" and before["scan_id"] is None
    assert base44.create_calls == 1


def test_duplicate_or_malformed_lookup_rows_are_refused_without_write():
    seeder, store, base44, exact = _uncertain_with_hidden_row()
    base44.forge(exact)
    base44.forge({**exact, "id": "scanrun_dup"})
    before = receipt_for(store, make_draft())
    refused("duplicate_scanrun_rows", seeder.reconcile, make_draft(), make_access())
    seeder._find = lambda owner, request: {"rows": []}
    refused("scanrun_lookup_invalid", seeder.reconcile, make_draft(), make_access())

    def broken(owner, request):
        raise ConnectionError("lookup down")
    seeder._find = broken
    refused("scanrun_lookup_unavailable", seeder.reconcile, make_draft(), make_access())
    assert receipt_for(store, make_draft()) == before
    assert base44.create_calls == 1


def test_created_response_that_is_not_our_exact_row_is_kept_uncertain():
    seeder, store, base44 = make_seeder()
    base44.mutate_response = {"scan_mode": "standard_150"}
    result = seeder.submit(make_draft(), make_access())
    assert result["outcome"] == "pending_reconciliation" and result["create_invoked"] is True
    assert receipt_for(store, make_draft())["uncertain_reason"] == "created_row_proof_mismatch"
    # The stored row itself is exact, so the server-owned lookup reconciles.
    base44.mutate_response = None
    assert seeder.submit(make_draft(), make_access())["outcome"] == "reconciled"
    assert base44.create_calls == 1


def test_different_request_reusing_idempotency_key_is_rejected():
    seeder, store, base44 = make_seeder()
    seeder.submit(make_draft(request="req_a", idem="idem_k"), make_access())
    refused("idempotency_key_reused", seeder.submit,
            make_draft(request="req_b", idem="idem_k"), make_access())
    # Same request id presenting a different idempotency key is a conflict.
    refused("request_replay_conflict", seeder.submit,
            make_draft(request="req_a", idem="idem_other"), make_access())
    # Still rejected after the first request is released (binding is permanent).
    seeder.release_after_verified_terminal(
        owner_user_id="owner_one", request_id="req_a", scan_id="scanrun_1",
        terminal_status="complete", verified_terminal=True)
    refused("idempotency_key_reused", seeder.submit,
            make_draft(request="req_b", idem="idem_k"), make_access())
    # Owner-scoped: another owner's identical key is independent.
    other = seeder.submit(make_draft(owner="owner_two", project="project_two", request="req_a",
                                     idem="idem_k", access_id="access_two"),
                          make_access(owner="owner_two", access_id="access_two"))
    assert other["outcome"] == "created"
    assert base44.create_calls == 2


@pytest.mark.parametrize("over", [
    {"project_id": "project_moved"},
    {"admission_access_id": "access_other"},
])
def test_same_request_with_changed_binding_is_replay_conflict(over):
    seeder, store, base44 = make_seeder()
    seeder.submit(make_draft(), make_access())
    access = make_access(access_id=over.get("admission_access_id", "access_extended"))
    refused("request_replay_conflict", seeder.submit, make_draft(**over), access)
    assert base44.create_calls == 1


@pytest.mark.parametrize("mode", ["standard_150", "advanced", "basic", None, "EXTENDED_500"])
def test_standard150_and_other_modes_are_rejected_before_any_write(mode):
    seeder, store, base44 = make_seeder()
    refused("invalid_scan_mode", seeder.submit, make_draft(scan_mode=mode), make_access())
    assert store.docs == {} and base44.create_calls == 0


@pytest.mark.parametrize("access,code", [
    (make_access(owner="owner_foreign"), "foreign_access"),
    (make_access(access_id="access_other"), "foreign_access"),
    (make_access(plan_id="standard150_lifetime"), "wrong_entitlement_plan"),
    (make_access(access_status="checkout_pending"), "extended500_paid_access_required"),
    (make_access(grant_source="manual_grant"), "extended500_paid_access_required"),
    (make_access(grant_source="owner_test"), "extended500_paid_access_required"),
    (make_access(has_full_access=1), "extended500_paid_access_required"),
    (make_access(app_id="another_app"), "extended500_paid_access_required"),
    (None, "extended500_paid_access_required"),
])
def test_foreign_or_unpaid_access_cannot_be_bound(access, code):
    seeder, store, base44 = make_seeder()
    refused(code, seeder.submit, make_draft(), access)
    assert store.docs == {} and base44.create_calls == 0


@pytest.mark.parametrize("over,code", [
    ({"attempt_count": 2}, "initial_seed_attempt_required"),
    ({"attempt_count": True}, "invalid_attempt_count"),
    ({"status": "crawling"}, "scanrun_draft_status_invalid"),
    ({"owner_attested_robots_override": True}, "scanrun_draft_robots_invalid"),
    ({"pages_crawled": 500}, "scanrun_draft_counters_invalid"),
    ({"release_gate_eligible": True}, "scanrun_draft_authority_invalid"),
    ({"path_prefix": "/blog"}, "scanrun_draft_shape_invalid"),
    ({"authority_proof": "x"}, "scanrun_draft_shape_invalid"),
    ({"website_url": "https://127.0.0.1/"}, "scanrun_draft_target_invalid"),
    ({"submitted_url": "https://other.example.org/"}, "scanrun_draft_target_invalid"),
    ({"request_fingerprint": "extended_500|https://x.org/|root|respect_robots_txt"},
     "scanrun_draft_target_invalid"),
    ({"owner_user_id": "owner/one"}, "invalid_owner_user_id"),
    ({"scan_source": "customer"}, "scanrun_draft_source_invalid"),
])
def test_tampered_draft_is_rejected_before_any_write(over, code):
    seeder, store, base44 = make_seeder()
    refused(code, seeder.submit, make_draft(**over), make_access())
    assert store.docs == {} and base44.create_calls == 0


def test_definite_rejection_is_terminal_and_replay_is_refused():
    seeder, store, base44 = make_seeder()
    base44.mode = "reject"
    failed = seeder.submit(make_draft(), make_access())
    assert failed["outcome"] == "failed" and failed["state"] == "failed"
    assert receipt_for(store, make_draft())["failure_code"] == "schema_rejected"
    assert slot_for(store)["state"] == "released"
    base44.mode = "ok"
    refused("terminal_receipt_replay", seeder.submit, make_draft(), make_access())
    refused("terminal_receipt_replay", seeder.reconcile, make_draft(), make_access())
    assert base44.create_calls == 1
    # The owner may seed a genuinely new request afterwards.
    assert seeder.submit(make_draft(request="req_next"), make_access())["outcome"] == "created"
    assert base44.create_calls == 2


def test_verified_terminal_release_then_replay_refused_and_old_receipt_inert():
    seeder, store, base44 = make_seeder()
    seeder.submit(make_draft(), make_access())
    kwargs = dict(owner_user_id="owner_one", request_id="req_500_once", scan_id="scanrun_1")
    refused("verified_terminal_required", seeder.release_after_verified_terminal,
            **kwargs, terminal_status="complete", verified_terminal="true")
    refused("verified_terminal_required", seeder.release_after_verified_terminal,
            **kwargs, terminal_status="crawling", verified_terminal=True)
    refused("release_identity_mismatch", seeder.release_after_verified_terminal,
            **{**kwargs, "scan_id": "scanrun_foreign"}, terminal_status="complete", verified_terminal=True)
    done = seeder.release_after_verified_terminal(**kwargs, terminal_status="complete", verified_terminal=True)
    assert done["outcome"] == "released" and slot_for(store)["state"] == "released"
    refused("terminal_receipt_replay", seeder.submit, make_draft(), make_access())
    nxt = seeder.submit(make_draft(request="req_next"), make_access())
    assert nxt["outcome"] == "created"
    again = seeder.release_after_verified_terminal(**kwargs, terminal_status="complete", verified_terminal=True)
    assert again["outcome"] == "already_released"
    refused("terminal_conflict", seeder.release_after_verified_terminal,
            **kwargs, terminal_status="failed", verified_terminal=True)
    slot = slot_for(store)
    assert slot["state"] == "active" and slot["request_id"] == "req_next"


def test_receipts_store_no_credentials_or_raw_access_material():
    seeder, store, base44 = make_seeder()
    seeder.submit(make_draft(request="req_a", idem="idem_private_value"), make_access())
    base44.mode, base44.hidden = "lose_response", True
    seeder.submit(make_draft(owner="owner_two", project="project_two", request="req_b",
                             access_id="access_two"),
                  make_access(owner="owner_two", access_id="access_two"))
    docs = store.all_docs()
    assert docs
    banned_values = {ACCESS_SESSION, "idem_private_value", "owner_one@example.com",
                     "6a498732ec779dfaaeab0e53", "stripe_checkout"}
    for (collection, _), doc in docs.items():
        allowed = {"extended500_seed_receipts": seed.RECEIPT_FIELDS,
                   "extended500_seed_owner_slots": seed.SLOT_FIELDS,
                   "extended500_seed_idempotency": seed.IDEMPOTENCY_FIELDS}[collection]
        assert set(doc) == allowed
        for key, value in doc.items():
            assert not any(word in key for word in ("proof", "secret", "token", "signature",
                                                    "password", "session", "email"))
            assert value not in banned_values
            assert value is None or isinstance(value, (str, int))


def test_contention_exhaustion_refuses_without_create():
    class AlwaysAbort(FakeTransactionalStore):
        def run_in_transaction(self, fn):
            fn(_FakeTx(self))
            raise seed.SeedStoreContention()
    seeder, store, base44 = make_seeder(store=AlwaysAbort())
    refused("seed_store_contention_retry", seeder.submit, make_draft(), make_access())
    assert base44.create_calls == 0 and store.docs == {}


def test_claim_commit_outcome_unknown_never_invokes_create():
    class FailSecondCommit(FakeTransactionalStore):
        calls = 0

        def run_in_transaction(self, fn):
            self.calls += 1
            result = super().run_in_transaction(fn)
            if self.calls == 2:  # claim committed, but the ack is lost
                raise ConnectionError("commit ack lost")
            return result
    seeder, store, base44 = make_seeder(store=FailSecondCommit())
    refused("seed_store_unavailable", seeder.submit, make_draft(), make_access())
    assert base44.create_calls == 0
    assert receipt_for(store, make_draft())["state"] == "create_pending"
    assert seeder.submit(make_draft(), make_access())["outcome"] == "create_in_progress"
    assert base44.create_calls == 0


def test_crash_after_reserve_before_claim_resumes_with_single_create():
    """RESERVED means no create was ever sent, so a retry may claim exactly once."""
    class DieBeforeSecondCommit(FakeTransactionalStore):
        calls = 0

        def run_in_transaction(self, fn):
            self.calls += 1
            if self.calls == 2:
                raise SimulatedCrash()  # process dies before the claim commits
            return super().run_in_transaction(fn)
    store = DieBeforeSecondCommit()
    seeder, _, base44 = make_seeder(store=store)
    with pytest.raises(SimulatedCrash):
        seeder.submit(make_draft(), make_access())
    assert receipt_for(store, make_draft())["state"] == "reserved"
    assert base44.create_calls == 0
    restarted, _, _ = make_seeder(store=store, base44=base44)
    assert restarted.submit(make_draft(), make_access())["outcome"] == "created"
    assert restarted.submit(make_draft(), make_access())["outcome"] == "seeded_replay"
    assert base44.create_calls == 1


def test_firestore_adapter_maps_transactions_and_enforces_read_before_write():
    """Shape-only: a lock-serialized fake of google.cloud.firestore (UNVERIFIED live)."""
    docs, lock = {}, threading.RLock()

    class Snap:
        def __init__(self, value):
            self.exists, self._value = value is not None, value

        def to_dict(self):
            return copy.deepcopy(self._value)

    class Ref:
        def __init__(self, path):
            self.path = path

        def get(self, transaction=None):
            assert transaction is not None, "reads must be transactional"
            return Snap(docs.get(self.path))

    class Tx:
        def __init__(self, max_attempts):
            self.max_attempts, self.ops = max_attempts, []

        def create(self, ref, value):
            self.ops.append(("create", ref.path, copy.deepcopy(value)))

        def set(self, ref, value):
            self.ops.append(("set", ref.path, copy.deepcopy(value)))

    class Client:
        def collection(self, name):
            return types_ns(document=lambda key: Ref(f"{name}/{key}"))

        def transaction(self, max_attempts):
            return Tx(max_attempts)

    def types_ns(**kw):
        return type("NS", (), {k: staticmethod(v) for k, v in kw.items()})

    def transactional(func):
        def run(tx):
            with lock:
                result = func(tx)
                for op, path, value in tx.ops:
                    assert not (op == "create" and path in docs)
                    docs[path] = value
                return result
        return run

    store = seed.FirestoreSeedStore(Client(), transactional)
    base44 = FakeBase44()
    seeder = seed.Extended500ScanRunSeeder(store, base44.create, base44.find, enabled=True, clock=Clock())
    assert seeder.submit(make_draft(), make_access())["outcome"] == "created"
    assert seeder.submit(make_draft(), make_access())["outcome"] == "seeded_replay"
    assert sorted(p.split("/")[0] for p in docs) == [
        "extended500_seed_idempotency", "extended500_seed_owner_slots", "extended500_seed_receipts"]
    view = seed._FirestoreTransactionView(Client(), Tx(5))
    view.set("c", "d", {})
    with pytest.raises(RuntimeError, match="reads before writes"):
        view.get("c", "d")
    assert base44.create_calls == 1


def test_module_has_no_live_imports_or_routes():
    source = (SERVICE_DIR / "scanrun_seed.py").read_text()
    for forbidden in ("google.cloud", "import requests", "flask", "urllib.request", "http.client",
                      "base44.asServiceRole", "@app."):
        assert forbidden not in source
    service = (SERVICE_DIR / "service.py").read_text()
    assert "scanrun_seed" not in service, "seed must stay unwired from the coordinator"
    assert "scanrun_seed.py" not in (SERVICE_DIR / "Dockerfile").read_text()
