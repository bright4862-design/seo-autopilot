"""Isolated coordinator adapter tests with transactional Firestore and HTTP stubs.

No Google Cloud access. These prove requested transaction shapes, not real
Firestore serializability, IAM, or exactly-once Cloud Tasks delivery.
"""
import functools
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import types

import pytest

ROOT = Path(__file__).resolve().parents[2]
SERVICE_DIR = ROOT / "extended500-admission"
KEYS = {
    "EXTENDED500_COORDINATOR_SIGNING_KEY": "coordinator-fixture-aaaaaaaaaaaaaaaaaaaaaa",
    "EXTENDED500_ENTITLEMENT_SIGNING_KEY": "entitlement-fixture-bbbbbbbbbbbbbbbbbbb",
    "EXTENDED500_ADMISSION_SIGNING_KEY": "admission-fixture-cccccccccccccccccccccc",
    "EXTENDED500_TERMINAL_SIGNING_KEY": "terminal-fixture-ddddddddddddddddddddd",
    "EXTENDED500_TASKS_QUEUE_PATH": "projects/p-1/locations/us-east1/queues/extended500-test",
    "EXTENDED500_WORKER_ORIGIN": "https://worker.example/scan-job-extended500",
    "EXTENDED500_INVOKER_SERVICE_ACCOUNT": "runner@example.iam.gserviceaccount.com",
    "EXTENDED500_ATOMIC_ADMISSION_ENABLED": "true",
    "EXTENDED500_QUEUE_DISPATCH_ENABLED": "false",
}
STORE = {}
LOCK = threading.RLock()


class Snapshot:
    def __init__(self, value):
        self.value = value
        self.exists = value is not None

    def to_dict(self):
        return dict(self.value) if self.exists else None


class Ref:
    def __init__(self, path):
        self.path = path

    def get(self, transaction=None):
        return Snapshot(STORE.get(self.path))


class Collection:
    def __init__(self, prefix):
        self.prefix = prefix

    def document(self, key):
        return Ref(self.prefix + "/" + key)


class Transaction:
    def __init__(self):
        self.pending = []

    def create(self, ref, value):
        self.pending.append(("create", ref.path, dict(value)))

    def set(self, ref, value):
        self.pending.append(("set", ref.path, dict(value)))

    def commit(self):
        for op, path, _ in self.pending:
            if op == "create" and path in STORE:
                raise RuntimeError("concurrent receipt already exists")
        for _, path, value in self.pending:
            STORE[path] = value


class Client:
    def collection(self, name):
        return Collection(name)

    def transaction(self):
        return Transaction()


def transactional(func):
    @functools.wraps(func)
    def execute(tx):
        with LOCK:
            result = func(tx)
            tx.commit()
            return result
    return execute


def _load(monkeypatch):
    monkeypatch.syspath_prepend(str(SERVICE_DIR))
    for key, value in KEYS.items():
        monkeypatch.setenv(key, value)
    fake_flask = types.ModuleType("flask")

    class FakeFlask:
        def __init__(self, _name):
            self.config = {}
        def get(self, _path):
            return lambda handler: handler
        def post(self, _path):
            return lambda handler: handler

    fake_flask.Flask = FakeFlask
    fake_flask.jsonify = lambda value: value
    fake_flask.request = None
    monkeypatch.setitem(sys.modules, "flask", fake_flask)

    import google
    cloud = types.ModuleType("google.cloud")
    cloud.__path__ = []
    firestore = types.ModuleType("google.cloud.firestore")
    firestore.Client = Client
    firestore.transactional = transactional
    cloud.firestore = firestore
    monkeypatch.setitem(sys.modules, "google.cloud", cloud)
    monkeypatch.setitem(sys.modules, "google.cloud.firestore", firestore)
    monkeypatch.setattr(google, "cloud", cloud, raising=False)
    spec = importlib.util.spec_from_file_location("extended500_candidate_service", SERVICE_DIR / "service.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _evidence(service):
    entitlement = {
        "version": "extended500_paid_entitlement_v1",
        "plan_id": "extended500_lifetime", "scan_mode": "extended_500",
        "entitlement_state": "active_paid",
        "owner_user_id": "owner_500", "scan_id": "scan_500",
        "project_id": "project_500", "request_id": "request_500",
        "idempotency_key": "idem_500", "access_id": "access_500",
        "attempt_count": 1,
        "issued_at": (datetime.now(timezone.utc) - timedelta(seconds=15)).isoformat().replace("+00:00", "Z"),
        "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=120)).isoformat().replace("+00:00", "Z"),
    }
    grant = {
        "version": "extended500_preflight_grant_v1", "audience": "fixlist_extended500_worker",
        "canonical_mode": "extended_500",
        "owner_user_id": "owner_500", "scan_id": "scan_500",
        "project_id": "project_500", "request_id": "request_500",
        "idempotency_key": "idem_500", "attempt_count": 1,
        "website_url": "https://example.com/", "path_prefix": None,
        "respect_robots_txt": True, "owner_attested_robots_override": False,
        "issued_at": entitlement["issued_at"], "expires_at": entitlement["expires_at"],
    }
    return (
        {**entitlement, "proof": service.seal(entitlement, service.ENTITLEMENT_KEY)},
        {**grant, "proof": service.seal(grant, service.PREFLIGHT_KEY)},
    )


def test_isolated_firestore_transactions_reserve_replay_and_preserve_tombstones(monkeypatch):
    STORE.clear()
    service = _load(monkeypatch)
    entitlement, grant = _evidence(service)
    service.verify_assertions(
        entitlement, grant,
        now=datetime.now(timezone.utc),
    )
    first = service.reserve(entitlement, grant)
    assert first["outcome"] == "reserved"
    assert len(STORE) == 2
    again = service.reserve(entitlement, grant)
    assert again["outcome"] == "replayed"
    assert again["task_name"] == first["task_name"]
    assert len(STORE) == 2
    request_claim = service.core.canonical_request(entitlement)
    service.update_dispatch_state(request_claim, "dispatch_unknown")
    assert service.reserve(entitlement, grant)["task_name"] == first["task_name"]
    service.update_dispatch_state(request_claim, "enqueued")
    slot = STORE["extended500_owner_slots/owner_500"]
    receipt = STORE["extended500_request_receipts/" + first["receipt_id"]]
    assert slot["state"] == receipt["state"] == "enqueued"
    decision = service.core.decide_release(
        slot, receipt, request_claim, terminal_status="complete",
        verified_terminal=True, released_at=10,
    )
    for key in ("slot_write", "receipt_write"):
        assert decision[key]["state"] == "released"
    STORE["extended500_owner_slots/owner_500"] = decision["slot_write"]
    STORE["extended500_request_receipts/" + first["receipt_id"]] = decision["receipt_write"]
    assert service.reserve(entitlement, grant)["outcome"] == "terminal_replay"


def test_paid_proofs_reject_foreign_purpose_and_identity_without_firestore_write(monkeypatch):
    STORE.clear()
    service = _load(monkeypatch)
    entitlement, grant = _evidence(service)
    moment = datetime.now(timezone.utc)
    foreign = {**entitlement, "plan_id": "standard150_lifetime"}
    foreign["proof"] = service.seal({k: v for k, v in foreign.items() if k != "proof"}, service.ENTITLEMENT_KEY)
    with pytest.raises(service.core.AdmissionRefused, match="wrong_entitlement_plan"):
        service.verify_assertions(foreign, grant, now=moment)
    tampered = {**grant, "request_id": "different"}
    with pytest.raises(service.core.AdmissionRefused, match="preflight_signature_invalid"):
        service.verify_assertions(entitlement, tampered, now=moment)
    signed_wrong = {**grant, "attempt_count": 2}
    signed_wrong["proof"] = service.seal({k: v for k, v in signed_wrong.items() if k != "proof"}, service.PREFLIGHT_KEY)
    with pytest.raises(service.core.AdmissionRefused, match="preflight_identity_mismatch"):
        service.verify_assertions(entitlement, signed_wrong, now=moment)
    assert STORE == {}


def test_enqueue_is_separately_disabled_and_409_does_not_establish_success(monkeypatch):
    STORE.clear()
    service = _load(monkeypatch)
    entitlement, grant = _evidence(service)
    claim = service.core.canonical_request(entitlement)
    task = service.core.task_name(service.QUEUE_PATH, claim)
    assert service.enqueue(claim, grant, task) == "dispatch_disabled"

    class Credentials:
        valid = True
        token = "fake-token"
    monkeypatch.setattr(service.google.auth, "default", lambda **_: (Credentials(), None))
    captured = []
    class Response:
        status_code = 409
        ok = False
    def fake_post(url, **kwargs):
        captured.append((url, kwargs["json"]["task"]))
        return Response()
    monkeypatch.setattr(service.requests, "post", fake_post)
    monkeypatch.setattr(service, "QUEUE_ENABLED", True)
    assert service.enqueue(claim, grant, task) == "dispatch_unknown"
    assert len(captured) == 1
    name, http = captured[0][1]["name"], captured[0][1]["httpRequest"]
    assert name == task
    assert service.QUEUE_PATH in captured[0][0]
    assert http["url"] == service.WORKER_ORIGIN
    assert http["oidcToken"]["serviceAccountEmail"] == service.INVOKER_SA
    assert http["oidcToken"]["audience"] == "https://worker.example"
    assert json.loads(__import__("base64").b64decode(http["body"]))["scan_mode"] == "extended_500"
    assert STORE == {}


def test_js_issued_paid_entitlement_verifies_in_python_isolated_service(monkeypatch):
    STORE.clear()
    service = _load(monkeypatch)
    script = """
import { mintExtended500AdmissionEvidence } from './src/lib/extended500EntitlementIssuer.js';
const user = {id:'owner_500', email:'owner@example.com'};
const scan = {
 id:'scan_500',owner_user_id:'owner_500',project_id:'project_500',
 request_id:'request_500',idempotency_key:'idem_500',attempt_count:1,
 scan_mode:'extended_500',status:'queued',website_url:'https://example.com/',
 path_prefix:null,respect_robots_txt:true,owner_attested_robots_override:false
};
const access = { id:'access_500',owner_user_id:'owner_500',user_email:'owner@example.com',
 app_id:'6a498732ec779dfaaeab0e53',plan_id:'extended500_lifetime',
 access_status:'active',has_full_access:true,grant_source:'stripe_checkout',
 stripe_checkout_session_id:'cs_test_fixture',paid_at:'2026-10-26T20:00:00Z' };
const evidence = await mintExtended500AdmissionEvidence({
 user, scan,accessRows:[access],nowMs:Date.now(),
 entitlementSigningKey: process.env.EXTENDED500_ENTITLEMENT_SIGNING_KEY,
 grantSigningKey: process.env.EXTENDED500_ADMISSION_SIGNING_KEY,
});
process.stdout.write(JSON.stringify(evidence));
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT, text=True, capture_output=True, check=True, timeout=25,
        env={**os.environ, **KEYS},
    )
    payload = json.loads(result.stdout)
    assert payload["ok"] is True, payload
    request = service.verify_assertions(
        payload["entitlement"], payload["preflight_grant"],
        now=datetime.now(timezone.utc),
    )
    assert request["owner_user_id"] == "owner_500"
    assert request["attempt_count"] == 1


@pytest.mark.parametrize(("queue_ready", "worker_ready"), [
    (False, False),
    (False, True),
    (True, False),
])
def test_reserved_owner_slot_cannot_be_created_before_queue_and_worker_ready(
    monkeypatch, queue_ready, worker_ready,
):
    """Even with a correctly signed claim, inactive worker cannot wedge owner."""
    STORE.clear()
    service = _load(monkeypatch)
    entitlement, grant = _evidence(service)
    monkeypatch.setattr(service, "QUEUE_ENABLED", queue_ready)
    monkeypatch.setattr(service, "WORKER_READY", worker_ready)
    monkeypatch.setattr(
        service, "authenticate",
        lambda: ({"entitlement": entitlement, "preflight_grant": grant}, None),
    )
    def forbidden_reserve(*_args):
        raise AssertionError("No Firestore reservation before both gates")
    monkeypatch.setattr(service, "reserve", forbidden_reserve)
    reply, status = service.reservation_route()
    assert status == 503
    assert reply["error"] == "extended500_dispatch_not_ready"
    assert STORE == {}


def test_release_route_stays_independent_from_dispatch_gate(monkeypatch):
    """A future terminal issuer must still be able to clean up after intake off."""
    service = _load(monkeypatch)
    assert service.WORKER_READY is False
    assert service.ENABLED is True
    assert service.QUEUE_ENABLED is False


def test_contending_owner_requests_have_one_atomic_winner_and_stable_replay(monkeypatch):
    """A locked fake transaction checks CAS state flow, not live Firestore isolation."""
    STORE.clear()
    service = _load(monkeypatch)
    candidates = []
    for number in range(12):
        entitlement, preflight = _evidence(service)
        entitlement.update({
            "scan_id": f"scan_candidate_{number}",
            "request_id": f"request_candidate_{number}",
            "idempotency_key": f"idem_candidate_{number}",
        })
        preflight.update({
            "scan_id": f"scan_candidate_{number}",
            "request_id": f"request_candidate_{number}",
            "idempotency_key": f"idem_candidate_{number}",
        })
        for doc, key in (
            (entitlement, service.ENTITLEMENT_KEY),
            (preflight, service.PREFLIGHT_KEY),
        ):
            doc["proof"] = service.seal(
                {field: value for field, value in doc.items() if field != "proof"}, key,
            )
        candidates.append((entitlement, preflight))

    def try_reserve(candidate):
        try:
            result = service.reserve(*candidate)
            return ("ok", result["outcome"], result["task_name"])
        except service.core.AdmissionRefused as exc:
            return ("refused", exc.code, "")

    with ThreadPoolExecutor(max_workers=12) as executor:
        decisions = list(executor.map(try_reserve, candidates))
    won = [v for v in decisions if v[0] == "ok"]
    denied = [v for v in decisions if v[0] == "refused"]
    assert len(won) == 1, decisions
    assert won[0][1] == "reserved"
    assert len(denied) == 11
    assert all(v[1] == "owner_slot_busy" for v in denied)
    assert len(STORE) == 2
    winning_index = decisions.index(won[0])
    replay = service.reserve(*candidates[winning_index])
    assert replay["outcome"] == "replayed"
    assert replay["task_name"] == won[0][2]
    assert len(STORE) == 2
