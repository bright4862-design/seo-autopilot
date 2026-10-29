"""Lane E: independent, candidate-blind Extended 500 release negative matrix.

Candidate under test: draft PR #377 head 002b84c9b6eaef78babec6081df150f31a000b11.
Matrix and evidence ledger: docs/extended500/lane-e-acceptance-matrix.md.

Fully offline. Firestore, Flask, Cloud Tasks, gcloud and Base44 are replaced with
in-process fakes. A passing test here proves a *source decision* of the candidate;
it does NOT prove Firestore serializability, Cloud Run IAM, Cloud Tasks delivery,
Stripe behaviour, deployed bytes or customer correctness.

Test names carry their matrix row id (iso/own/q/c/t/g/f/w/d/p/chain). RED tests
use ``xfail(strict=True, raises=AssertionError)``: each executes the real
requirement assertion, an unexpected pass FAILS the suite (forcing removal of the
marker), and any non-assertion error is reported as a real failure instead of
being hidden as an expected failure.
"""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
import copy
from datetime import datetime, timedelta, timezone
import functools
import hashlib
import hmac
import importlib.util
import itertools
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import types

from fastapi.testclient import TestClient
import pytest

from app import main as main_module
from app.authority_seal import create_authority_seal
from app.extended500_evidence_handoff import build_extended500_evidence_handoff
from app.extended500_job_admission import evaluate_extended500_preflight
from app.scan_job import (
    COMPLETION_VERSION,
    LIMITED_COMPLETION_VERSION,
    build_authority_review_payload,
    build_completion_envelope,
    build_limited_envelope,
    build_scan_attestation,
)
from app.scanner import resolve_scan_budget

ROOT = Path(__file__).resolve().parents[2]
SERVICE_DIR = ROOT / "extended500-admission"
GATEWAY_DIR = ROOT / "dispatch-gateway"
CANDIDATE = "002b84c"
_MODULE_IDS = itertools.count()

COORDINATOR_KEY = "lane-e-coordinator-root-" + "a" * 24
ENTITLEMENT_KEY = "lane-e-entitlement-root-" + "b" * 24
ADMISSION_KEY = "lane-e-admission-grant-root-" + "c" * 20
TERMINAL_KEY = "lane-e-terminal-release-root-" + "d" * 20
STANDARD150_EVIDENCE_KEY = "lane-e-standard150-evidence-root-" + "e" * 16
EXT500_QUEUE = "projects/lane-e/locations/us-east1/queues/extended500-lane-e"
STD150_QUEUE = "projects/lane-e/locations/us-east1/queues/fixlist-standard150"
STD150_DRAIN = "projects/lane-e/locations/us-east1/queues/fixlist-standard150-drain"
EXT500_WORKER = "https://extended500-worker.example/scan-job-extended500"
STD150_WORKER = "https://standard150-worker.example/scan-job"

SERVICE_ENV = {
    "EXTENDED500_COORDINATOR_SIGNING_KEY": COORDINATOR_KEY,
    "EXTENDED500_ENTITLEMENT_SIGNING_KEY": ENTITLEMENT_KEY,
    "EXTENDED500_ADMISSION_SIGNING_KEY": ADMISSION_KEY,
    "EXTENDED500_TERMINAL_SIGNING_KEY": TERMINAL_KEY,
    "EXTENDED500_TASKS_QUEUE_PATH": EXT500_QUEUE,
    "EXTENDED500_WORKER_ORIGIN": EXT500_WORKER,
    "EXTENDED500_INVOKER_SERVICE_ACCOUNT": "ext500-invoker@lane-e.iam.gserviceaccount.com",
}
ALL_GATES_ON = {
    "EXTENDED500_ATOMIC_ADMISSION_ENABLED": "true",
    "EXTENDED500_QUEUE_DISPATCH_ENABLED": "true",
    "EXTENDED500_WORKER_READY": "true",
}


def red(requirement: str):
    """Strict RED marker: real assertion, unexpected pass fails, errors are not hidden."""
    return pytest.mark.xfail(
        strict=True,
        raises=AssertionError,
        reason=f"RED: {requirement} not implemented on candidate {CANDIDATE}",
    )


# ---------------------------------------------------------------------------
# Optimistic-concurrency Firestore fake.
#
# Unlike a global-lock fake, reads are NOT serialized: every transaction records
# the version of each document it read and the commit is rejected (ABORTED) if any
# of them changed, exactly like Firestore's server-side commit validation. The
# decorator retries an aborted transaction like google-cloud-firestore's
# ``transactional`` (max 5 attempts). A barrier can force every contender to finish
# its reads and decision before anyone commits, which is the worst-case race.
# ---------------------------------------------------------------------------
class _Aborted(Exception):
    pass


class FakeFirestore:
    def __init__(self, *, serializable: bool = True, max_attempts: int = 5):
        self.docs: dict[str, tuple[int, dict]] = {}
        self.serializable = serializable
        self.max_attempts = max_attempts
        self.lock = threading.Lock()
        self.barrier: threading.Barrier | None = None
        self.conflicts = 0
        self.commits = 0

    def values(self) -> dict[str, dict]:
        with self.lock:
            return {path: dict(value) for path, (_, value) in self.docs.items()}

    def put(self, path: str, value: dict) -> None:
        with self.lock:
            version = self.docs.get(path, (0, None))[0]
            self.docs[path] = (version + 1, dict(value))


def _fake_firestore_module(store: FakeFirestore) -> types.ModuleType:
    module = types.ModuleType("google.cloud.firestore")

    class Snapshot:
        def __init__(self, value):
            self._value = None if value is None else dict(value)
            self.exists = value is not None

        def to_dict(self):
            return dict(self._value) if self.exists else None

    class Ref:
        def __init__(self, path):
            self.path = path

        def get(self, transaction=None):
            with store.lock:
                version, value = store.docs.get(self.path, (0, None))
            if transaction is not None:
                transaction.reads.setdefault(self.path, version)
            return Snapshot(value)

    class Collection:
        def __init__(self, name):
            self.name = name

        def document(self, key):
            return Ref(f"{self.name}/{key}")

    class Transaction:
        def __init__(self):
            self.reads: dict[str, int] = {}
            self.writes: list[tuple[str, str, dict]] = []

        def begin(self):
            self.reads, self.writes = {}, []

        def create(self, ref, value):
            self.writes.append(("create", ref.path, dict(value)))

        def set(self, ref, value):
            self.writes.append(("set", ref.path, dict(value)))

    class Client:
        def collection(self, name):
            return Collection(name)

        def transaction(self):
            return Transaction()

    def commit(tx):
        with store.lock:
            if store.serializable:
                for path, version in tx.reads.items():
                    if store.docs.get(path, (0, None))[0] != version:
                        raise _Aborted(path)
            for op, path, _ in tx.writes:
                if op == "create" and path in store.docs:
                    raise _Aborted(path)  # create() precondition: document must not exist
            for _, path, value in tx.writes:
                version = store.docs.get(path, (0, None))[0]
                store.docs[path] = (version + 1, value)
            store.commits += 1

    def transactional(func):
        @functools.wraps(func)
        def execute(tx, *args, **kwargs):
            for attempt in range(store.max_attempts):
                tx.begin()
                result = func(tx, *args, **kwargs)
                if attempt == 0 and store.barrier is not None:
                    try:
                        store.barrier.wait(timeout=10)
                    except threading.BrokenBarrierError:
                        pass
                try:
                    commit(tx)
                    return result
                except _Aborted:
                    with store.lock:
                        store.conflicts += 1
            raise RuntimeError("transaction aborted after max attempts")
        return execute

    module.Client = Client
    module.transactional = transactional
    return module


def _fake_flask(monkeypatch) -> types.ModuleType:
    fake = types.ModuleType("flask")

    class FakeFlask:
        def __init__(self, _name):
            self.config = {}

        def get(self, _path):
            return lambda handler: handler

        def post(self, _path):
            return lambda handler: handler

        def errorhandler(self, _code):
            return lambda handler: handler

    fake.Flask = FakeFlask
    fake.jsonify = lambda value: value
    fake.request = None
    monkeypatch.setitem(sys.modules, "flask", fake)
    return fake


def _load_service(monkeypatch, store: FakeFirestore | None = None, **env):
    """Import the REAL extended500-admission/service.py with faked infrastructure."""
    store = store or FakeFirestore()
    monkeypatch.syspath_prepend(str(SERVICE_DIR))
    for key in list(os.environ):
        if key.startswith("EXTENDED500_"):
            monkeypatch.delenv(key, raising=False)
    for key in ("SCAN_TASKS_QUEUE_PATH", "SCAN_DRAIN_QUEUE_PATH"):
        monkeypatch.delenv(key, raising=False)
    for key, value in {**SERVICE_ENV, **env}.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    _fake_flask(monkeypatch)
    import google
    cloud = types.ModuleType("google.cloud")
    cloud.__path__ = []
    firestore = _fake_firestore_module(store)
    cloud.firestore = firestore
    monkeypatch.setitem(sys.modules, "google.cloud", cloud)
    monkeypatch.setitem(sys.modules, "google.cloud.firestore", firestore)
    monkeypatch.setattr(google, "cloud", cloud, raising=False)
    spec = importlib.util.spec_from_file_location(
        f"lane_e_extended500_service_{next(_MODULE_IDS)}", SERVICE_DIR / "service.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    module.lane_e_store = store
    return module


def _load_gateway(monkeypatch, signing_root: str = STANDARD150_EVIDENCE_KEY):
    """Import the REAL Standard 150 dispatch-gateway/main.py offline."""
    for key, value in {
        "SCAN_TASKS_QUEUE_PATH": STD150_QUEUE,
        "SCAN_DRAIN_QUEUE_PATH": STD150_DRAIN,
        "SCAN_WORKER_URL": STD150_WORKER,
        "TASKS_INVOKER_SERVICE_ACCOUNT": "std150-invoker@lane-e.iam.gserviceaccount.com",
        "SCAN_EVIDENCE_SIGNING_KEY": signing_root,
    }.items():
        monkeypatch.setenv(key, value)
    _fake_flask(monkeypatch)
    werkzeug = types.ModuleType("werkzeug")
    exceptions = types.ModuleType("werkzeug.exceptions")

    class RequestEntityTooLarge(Exception):
        pass

    exceptions.RequestEntityTooLarge = RequestEntityTooLarge
    werkzeug.exceptions = exceptions
    monkeypatch.setitem(sys.modules, "werkzeug", werkzeug)
    monkeypatch.setitem(sys.modules, "werkzeug.exceptions", exceptions)
    spec = importlib.util.spec_from_file_location(
        f"lane_e_dispatch_gateway_{next(_MODULE_IDS)}", GATEWAY_DIR / "main.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _iso(moment: datetime) -> str:
    # Same shape as JavaScript Date#toISOString() used by the Base44 issuer.
    return moment.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _seal(document: dict, key: str) -> dict:
    unsigned = {k: v for k, v in document.items() if k != "proof"}
    return {**unsigned, "proof": create_authority_seal(unsigned, key)}


def _mint(*, owner="owner_500", request="request_500", attempt=1, access="access_500",
          project="project_500", issued: datetime | None = None, ttl=120,
          entitlement_key=ENTITLEMENT_KEY, grant_key=ADMISSION_KEY):
    """Independent re-implementation of the issuer's two documents (not service.seal)."""
    issued = issued or (datetime.now(timezone.utc) - timedelta(seconds=5))
    common = {
        "owner_user_id": owner, "scan_id": f"scan_{request}", "project_id": project,
        "request_id": request, "idempotency_key": f"idem_{request}", "attempt_count": attempt,
    }
    stamps = {"issued_at": _iso(issued), "expires_at": _iso(issued + timedelta(seconds=ttl))}
    entitlement = {
        "version": "extended500_paid_entitlement_v1", "plan_id": "extended500_lifetime",
        "scan_mode": "extended_500", "entitlement_state": "active_paid",
        **common, "access_id": access, **stamps,
    }
    grant = {
        "version": "extended500_preflight_grant_v1", "audience": "fixlist_extended500_worker",
        "canonical_mode": "extended_500", **common,
        "website_url": "https://example.com/", "path_prefix": None,
        "respect_robots_txt": True, "owner_attested_robots_override": False, **stamps,
    }
    return _seal(entitlement, entitlement_key), _seal(grant, grant_key)


def _terminal(entitlement: dict, status="complete", key=TERMINAL_KEY, **overrides) -> dict:
    document = {
        "version": "extended500_verified_terminal_release_v1",
        **{k: entitlement[k] for k in (
            "owner_user_id", "scan_id", "project_id", "request_id",
            "idempotency_key", "access_id", "attempt_count",
        )},
        "terminal_status": status,
        **overrides,
    }
    return _seal(document, key)


class FakeCloudTasks:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls: list[dict] = []

    def post(self, url, **kwargs):
        self.calls.append({"url": url, "task": kwargs["json"]["task"], "timeout": kwargs.get("timeout")})
        outcome = self.outcomes.pop(0) if self.outcomes else 409
        if isinstance(outcome, BaseException):
            raise outcome
        return types.SimpleNamespace(status_code=outcome, ok=200 <= outcome < 300)


def _install_tasks(monkeypatch, service, outcomes) -> FakeCloudTasks:
    class Credentials:
        valid = True
        token = "lane-e-fake-token"

    monkeypatch.setattr(service.google.auth, "default", lambda **_: (Credentials(), None))
    fake = FakeCloudTasks(outcomes)
    monkeypatch.setattr(service.requests, "post", fake.post)
    return fake


def _route(monkeypatch, service, handler, body):
    monkeypatch.setattr(service, "authenticate", lambda: (body, None))
    return handler()


def _reserve_route(monkeypatch, service, entitlement, grant):
    return _route(monkeypatch, service, service.reservation_route,
                  {"entitlement": entitlement, "preflight_grant": grant})


def _release_route(monkeypatch, service, entitlement, terminal):
    return _route(monkeypatch, service, service.release_route,
                  {"entitlement": entitlement, "terminal": terminal})


def _states(service) -> dict[str, str]:
    return {path: value.get("state") for path, value in service.lane_e_store.values().items()}


def _frozen500(grant: dict) -> dict:
    return {
        "id": grant["scan_id"], "owner_user_id": grant["owner_user_id"],
        "project_id": grant["project_id"], "request_id": grant["request_id"],
        "idempotency_key": grant["idempotency_key"], "attempt_count": grant["attempt_count"],
        "website_url": grant["website_url"], "normalized_domain": "example.com",
        "path_prefix": grant["path_prefix"], "scan_mode": "extended_500", "status": "queued",
        "respect_robots_txt": grant["respect_robots_txt"],
        "owner_attested_robots_override": grant["owner_attested_robots_override"],
    }


def _task_body(call: dict) -> dict:
    return json.loads(base64.b64decode(call["task"]["httpRequest"]["body"]))


def _std150_task(frozen: dict) -> dict:
    return {
        "scan_id": frozen["id"], "request_id": frozen["request_id"],
        "idempotency_key": frozen["idempotency_key"], "project_id": frozen["project_id"],
        "owner_user_id": frozen["owner_user_id"], "attempt_count": frozen["attempt_count"],
        "website_url": frozen["website_url"], "normalized_domain": frozen["normalized_domain"],
        "scan_mode": "standard_150", "respect_robots_txt": True,
        "owner_attested_robots_override": False,
    }


def _scan150(**overrides) -> dict:
    return {
        "scan_mode": "standard_150", "owner_user_id": "owner_150", "id": "scan_150",
        "project_id": "project_150", "request_id": "request_150", "idempotency_key": "idem_150",
        "attempt_count": 1, "normalized_domain": "example.com", **overrides,
    }


def _short_result(**overrides) -> dict:
    pages = [{"url": f"https://example.com/p{i}", "final_url": f"https://example.com/p{i}",
              "status_code": 200} for i in range(3)]
    return {
        "scan_id": "scan_150", "request_id": "request_150", "idempotency_key": "idem_150",
        "normalized_domain": "example.com", "pages_crawled": len(pages),
        "pages": pages, "crawled_pages": copy.deepcopy(pages), **overrides,
    }


def _scan500(**overrides) -> dict:
    return {
        "scan_mode": "extended_500", "owner_user_id": "owner_500", "id": "scan_request_500",
        "project_id": "project_500", "request_id": "request_500",
        "idempotency_key": "idem_request_500", "normalized_domain": "example.com",
        "attempt_count": 1, **overrides,
    }


PRIVATE_SENTINELS = ("LANE-E-PRIVATE-MAIN-TEXT", "<html data-lane-e-raw>", "LANE-E-RAW-LINK")


def _result500(size=500, page_extra=None) -> dict:
    pages = []
    for index in range(size):
        page = {
            "url": f"https://example.com/p-{index:04d}",
            "final_url": f"https://example.com/p-{index:04d}",
            "status_code": 200, "title": f"Page {index}",
            "main_text": PRIVATE_SENTINELS[0], "main_text_signature": "sig",
            "html": PRIVATE_SENTINELS[1], "raw_html": PRIVATE_SENTINELS[1],
            "body": PRIVATE_SENTINELS[1], "text": PRIVATE_SENTINELS[0],
            "_reachability_links": [{"href": PRIVATE_SENTINELS[2]}],
            "local_entity_observations": [{"raw": PRIVATE_SENTINELS[0]}],
            "contextual_freshness_evidence": {"raw": PRIVATE_SENTINELS[0]},
            "debug_future_field": PRIVATE_SENTINELS[0],
        }
        page.update(page_extra or {})
        pages.append(page)
    return {
        "scan_mode": "extended_500", "canonical_mode": "extended_500",
        "scan_id": "scan_request_500", "request_id": "request_500",
        "idempotency_key": "idem_request_500", "normalized_domain": "example.com",
        "pages_found": size + 40, "pages_crawled": size,
        "pages": pages, "crawled_pages": copy.deepcopy(pages),
        "scan_coverage": {"urls_attempted": size + 7, "usable_html_pages": size,
                          "unique_retained_destinations": size},
        "scanner_source_sha": "c" * 40, "beta_revision_fingerprint": "d" * 16,
    }


def _source_files(*roots: str, suffixes=(".py", ".js", ".ts", ".mjs")):
    for root in roots:
        base = ROOT / root
        if not base.exists():
            continue
        for path in base.rglob("*"):
            parts = set(path.parts)
            if (path.is_file() and path.suffix in suffixes and "node_modules" not in parts
                    and "tests" not in parts and "__pycache__" not in parts):
                yield path


# ===========================================================================
# ISO: 150/500 mode isolation
# ===========================================================================
@pytest.mark.parametrize("mode", ["extended_500", "EXTENDED_500", "advanced", ""])
def test_iso_01_standard150_worker_route_refuses_non_standard_task_before_any_read(monkeypatch, mode):
    reads = []

    async def read(_client, scan_id):
        reads.append(scan_id)
        raise AssertionError("Standard 150 worker must not read a foreign-mode task's ScanRun")

    monkeypatch.setattr(main_module, "require_cloud_tasks_oidc", lambda _token: None)
    monkeypatch.setattr(main_module, "read_scan_run", read)
    frozen = _frozen500(_mint()[1])
    with TestClient(main_module.app) as client:
        response = client.post("/scan-job", json={**_std150_task(frozen), "scan_mode": mode})
    assert response.status_code == 400
    assert reads == []


@red("Standard 150 /scan-job refusing a FROZEN extended_500 ScanRun (identity_matches ignores scan_mode)")
def test_iso_02_standard150_worker_refuses_frozen_extended500_scanrun_before_start_or_crawl(monkeypatch):
    """A standard_150 task naming an extended_500 ScanRun must never start or crawl it.

    The PR #377 schema now admits extended_500 rows, so the Standard 150 worker can
    no longer rely on every ScanRun it reads being Standard 150.
    """
    frozen = _frozen500(_mint()[1])
    started = []

    async def read(_client, _scan_id):
        return dict(frozen)

    async def mark_started(_client, scan):
        started.append(("mark_scan_started", scan.get("scan_mode")))
        raise RuntimeError("lane-e: stop before any crawl")

    async def crawl(**_kwargs):
        started.append(("run_scan", "extended_500"))
        raise AssertionError("never crawl")

    async def terminal(*_args, **_kwargs):
        return {}

    monkeypatch.setattr(main_module, "require_cloud_tasks_oidc", lambda _token: None)
    monkeypatch.setattr(main_module, "read_scan_run", read)
    monkeypatch.setattr(main_module, "mark_scan_started", mark_started)
    monkeypatch.setattr(main_module, "run_scan", crawl)
    monkeypatch.setattr(main_module, "persist_terminal_failure_bounded", terminal)
    with TestClient(main_module.app) as client:
        client.post("/scan-job", json=_std150_task(frozen))
    assert started == [], f"Standard 150 worker began work on an extended_500 ScanRun: {started}"


def _std150_builders():
    return {
        "completion": lambda scan, result: build_completion_envelope(scan, result, {}, STANDARD150_EVIDENCE_KEY),
        "limited": lambda scan, result: build_limited_envelope(scan, result, {}, STANDARD150_EVIDENCE_KEY),
        "review_payload": lambda _scan, result: build_authority_review_payload(result),
        "attestation": lambda scan, result: build_scan_attestation(result, scan, STANDARD150_EVIDENCE_KEY),
    }


@pytest.mark.parametrize("builder", sorted(_std150_builders()))
@pytest.mark.parametrize("modes", [
    {"scan_mode": "extended_500"},
    {"canonical_mode": "extended_500"},
    {"scan_mode": "advanced", "canonical_mode": "extended_500"},
    {"scan_mode": "standard_150", "canonical_mode": "extended_500"},
])
def test_iso_03_every_standard150_signer_refuses_short_extended500_results(builder, modes):
    # Three pages: the page-count guard alone could never catch this.
    with pytest.raises(ValueError, match="foreign"):
        _std150_builders()[builder](_scan150(), _short_result(**modes))


@red("Standard 150 completion/limited signers checking the FROZEN ScanRun scan_mode (only result mode keys are checked)")
@pytest.mark.parametrize("builder", ["completion", "limited"])
def test_iso_04_standard150_signers_refuse_frozen_extended500_scanrun_when_result_mode_absent(builder):
    frozen = _scan150(scan_mode="extended_500")
    result = _short_result()  # an adapter that drops/never sets scan_mode
    try:
        envelope = _std150_builders()[builder](frozen, result)
    except ValueError:
        return
    raise AssertionError(f"Standard 150 signer produced {envelope['version']} for a frozen extended_500 ScanRun")


def test_iso_05_unreviewed_500_handoff_cannot_be_relabelled_as_standard150_authority():
    key = STANDARD150_EVIDENCE_KEY  # worst case: an operator reuses the 150 root
    handoff = build_extended500_evidence_handoff(_scan500(), _result500(size=4), key)
    assert handoff["version"] not in (COMPLETION_VERSION, LIMITED_COMPLETION_VERSION)
    assert set(handoff) == {"version", "identity", "scan", "review", "proof"}
    signed = {k: handoff[k] for k in ("version", "identity", "scan", "review")}
    assert create_authority_seal(signed, key) == handoff["proof"]
    for version in (COMPLETION_VERSION, LIMITED_COMPLETION_VERSION):
        relabelled = {**signed, "version": version}
        assert create_authority_seal(relabelled, key) != handoff["proof"], version
    for frozen_mode in ("standard_150", "advanced", None):
        with pytest.raises(ValueError, match="frozen Extended 500"):
            build_extended500_evidence_handoff(_scan500(scan_mode=frozen_mode), _result500(size=4), key)


@pytest.mark.parametrize("job_mode", [False, True])
def test_iso_06_public_scanner_budget_and_response_never_widen_to_500(job_mode):
    assert resolve_scan_budget("extended_500", job_mode=job_mode)["max_pages"] == 150
    assert resolve_scan_budget("EXTENDED_500", 120, job_mode=job_mode)["max_pages"] == 150
    pages = [{"url": f"https://example.com/p{i}", "final_url": f"https://example.com/p{i}",
              "status_code": 200} for i in range(500)]
    result = main_module.enforce_scan_response_page_budget(
        {"pages": pages, "crawled_pages": list(pages), "pages_crawled": 500}, "extended_500",
    )
    assert len(result["pages"]) == len(result["crawled_pages"]) == 150
    assert result["pages_crawled"] == 150


def test_iso_07_standard150_dispatch_gateway_refuses_every_coordinator_built_500_task(monkeypatch):
    service = _load_service(monkeypatch, **ALL_GATES_ON)
    tasks = _install_tasks(monkeypatch, service, [200])
    entitlement, grant = _mint()
    reply, status = _reserve_route(monkeypatch, service, entitlement, grant)
    assert (status, reply["state"]) == (200, "enqueued")
    ext_task = tasks.calls[0]["task"]
    body = _task_body(tasks.calls[0])
    gateway = _load_gateway(monkeypatch)

    # 1. The exact 500 task, presented on its own queue.
    assert gateway.validate_dispatch({"queue_path": EXT500_QUEUE, "task": ext_task}) == (None, "invalid_queue")
    # 2. The exact 500 task smuggled onto the Standard 150 queue path.
    assert gateway.validate_dispatch({"queue_path": STD150_QUEUE, "task": ext_task}) == (None, "invalid_task_name")
    # 3. A forged Standard 150-shaped task carrying the 500 job body.
    forged = copy.deepcopy(ext_task)
    forged["name"] = f"{STD150_QUEUE}/tasks/standard150-{body['scan_id']}-a1"
    forged["httpRequest"]["url"] = STD150_WORKER
    forged["httpRequest"]["oidcToken"] = {
        "serviceAccountEmail": "std150-invoker@lane-e.iam.gserviceaccount.com",
        "audience": "https://standard150-worker.example",
    }
    assert gateway.validate_dispatch({"queue_path": STD150_QUEUE, "task": forged}) == (None, "invalid_scan_mode")
    # 4. Same forgery pointed at the 500 worker target is refused as a foreign target.
    retarget = copy.deepcopy(forged)
    retarget["httpRequest"]["url"] = EXT500_WORKER
    assert gateway.validate_dispatch({"queue_path": STD150_QUEUE, "task": retarget}) == (None, "invalid_worker_target")
    # Control: the gateway does accept a genuine Standard 150 body for the same forged envelope.
    genuine = copy.deepcopy(forged)
    genuine["httpRequest"]["body"] = base64.b64encode(json.dumps({
        "scan_id": body["scan_id"], "request_id": body["request_id"], "website_url": body["website_url"],
        "scan_mode": "standard_150", "respect_robots_txt": True, "owner_attested_robots_override": False,
    }).encode()).decode()
    accepted, error = gateway.validate_dispatch({"queue_path": STD150_QUEUE, "task": genuine})
    assert error is None and accepted is genuine


@pytest.mark.parametrize("overrides,expected", [
    ({"SCAN_TASKS_QUEUE_PATH": EXT500_QUEUE}, "Standard 150 queue"),
    ({"SCAN_DRAIN_QUEUE_PATH": EXT500_QUEUE}, "Standard 150 queue"),
    ({"EXTENDED500_TASKS_QUEUE_PATH": STD150_QUEUE}, "dedicated queue"),
    ({"EXTENDED500_WORKER_ORIGIN": STD150_WORKER}, "own worker endpoint"),
    ({"EXTENDED500_WORKER_ORIGIN": "http://extended500-worker.example/scan-job-extended500"}, "required"),
    ({"EXTENDED500_ADMISSION_SIGNING_KEY": ENTITLEMENT_KEY}, "distinct"),
    ({"EXTENDED500_TERMINAL_SIGNING_KEY": COORDINATOR_KEY}, "distinct"),
    ({"EXTENDED500_ENTITLEMENT_SIGNING_KEY": "too-short"}, "at least 32"),
    ({"EXTENDED500_TERMINAL_SIGNING_KEY": None}, "EXTENDED500_TERMINAL_SIGNING_KEY"),
])
def test_iso_08_coordinator_refuses_shared_queues_targets_and_roots_at_startup(monkeypatch, overrides, expected):
    with pytest.raises((RuntimeError, KeyError), match=expected):
        _load_service(monkeypatch, **overrides)


class _FakeRequest:
    def __init__(self, headers, raw):
        self.headers = headers
        self._raw = raw

    def get_data(self, cache=True):
        return self._raw


def test_iso_09_coordinator_and_standard150_gateway_hmac_domains_never_cross_verify(monkeypatch):
    shared_root = COORDINATOR_KEY  # worst case: an operator reuses one root for both services
    service = _load_service(monkeypatch)
    gateway = _load_gateway(monkeypatch, signing_root=shared_root)
    raw = json.dumps({"entitlement": {}, "preflight_grant": {}}).encode()
    stamp = str(int(time.time()))
    derived = hmac.new(shared_root.encode(), b"fixlist-extended500-atomic-admission-v1", hashlib.sha256).digest()
    coordinator_sig = hmac.new(derived, stamp.encode() + b"\n" + raw, hashlib.sha256).hexdigest()
    gateway_sig = gateway._expected_signature(stamp, raw)
    assert coordinator_sig != gateway_sig

    def call(signature, timestamp=stamp, body=raw):
        monkeypatch.setattr(service, "request", _FakeRequest(
            {"x-fixlist-timestamp": timestamp, "x-fixlist-signature": signature}, body,
        ))
        return service.authenticate()

    payload, failure = call(coordinator_sig)
    assert failure is None and payload == {"entitlement": {}, "preflight_grant": {}}
    _, failure = call(gateway_sig)
    assert failure == ({"success": False, "error": "invalid_signature"}, 401)
    stale = str(int(time.time()) - 3600)
    _, failure = call(hmac.new(derived, stale.encode() + b"\n" + raw, hashlib.sha256).hexdigest(), stale)
    assert failure == ({"success": False, "error": "stale_request"}, 401)
    for hostile in (b'{"entitlement":{},"entitlement":{}}', b'{"entitlement":NaN}', b"[]"):
        sig = hmac.new(derived, stamp.encode() + b"\n" + hostile, hashlib.sha256).hexdigest()
        _, failure = call(sig, body=hostile)
        assert failure is not None and failure[1] == 400, hostile


@red("runtime separation of EXTENDED500_ADMISSION_SIGNING_KEY from the Standard 150 SCAN_EVIDENCE_SIGNING_KEY")
def test_iso_10_preflight_refuses_admission_key_equal_to_standard150_evidence_root(monkeypatch):
    entitlement, grant = _mint(grant_key=STANDARD150_EVIDENCE_KEY)
    monkeypatch.setenv("FIXLIST_EXTENDED500_PREFLIGHT_ENABLED", "true")
    monkeypatch.setenv("EXTENDED500_ADMISSION_SIGNING_KEY", STANDARD150_EVIDENCE_KEY)
    monkeypatch.setenv("SCAN_EVIDENCE_SIGNING_KEY", STANDARD150_EVIDENCE_KEY)

    async def read(_client, _scan_id):
        return _frozen500(grant)

    monkeypatch.setattr(main_module, "require_cloud_tasks_oidc", lambda _token: None)
    monkeypatch.setattr(main_module, "read_scan_run", read)
    job = {k: grant[k] for k in (
        "scan_id", "request_id", "idempotency_key", "project_id", "owner_user_id",
        "attempt_count", "website_url", "path_prefix", "respect_robots_txt",
        "owner_attested_robots_override",
    )}
    with TestClient(main_module.app) as client:
        response = client.post("/scan-job-extended500-preflight", json={
            **job, "scan_mode": "extended_500", "signed_grant": grant,
        })
    assert response.status_code == 503, response.text


def test_iso_11_worker_preflight_refuses_grants_signed_by_other_roots_or_150_envelopes():
    _, grant = _mint()
    frozen = _frozen500(grant)
    job = {**{k: grant[k] for k in (
        "scan_id", "request_id", "idempotency_key", "project_id", "owner_user_id",
        "attempt_count", "website_url", "path_prefix", "respect_robots_txt",
        "owner_attested_robots_override",
    )}, "scan_mode": "extended_500"}
    now = datetime.now(timezone.utc)
    assert evaluate_extended500_preflight(job, frozen, grant, ADMISSION_KEY, now=now) == "verified_read_only"
    for other_root in (STANDARD150_EVIDENCE_KEY, ENTITLEMENT_KEY, COORDINATOR_KEY, TERMINAL_KEY):
        forged = _seal(grant, other_root)
        assert evaluate_extended500_preflight(job, frozen, forged, ADMISSION_KEY, now=now) == "grant_signature_invalid"
    std150_envelope = build_completion_envelope(_scan150(), _short_result(), {}, ADMISSION_KEY)
    assert evaluate_extended500_preflight(job, frozen, std150_envelope, ADMISSION_KEY, now=now) == "grant_shape_invalid"


# ===========================================================================
# OWN: owner / project / paid-access mismatch at the coordinator
# ===========================================================================
@pytest.mark.parametrize("field,value,code", [
    ("owner_user_id", "owner_other", "preflight_identity_mismatch"),
    ("project_id", "project_other", "preflight_identity_mismatch"),
    ("scan_id", "scan_other", "preflight_identity_mismatch"),
    ("request_id", "request_other", "preflight_identity_mismatch"),
    ("idempotency_key", "idem_other", "preflight_identity_mismatch"),
    ("attempt_count", 2, "preflight_identity_mismatch"),
    ("attempt_count", True, "preflight_identity_mismatch"),
    ("audience", "fixlist_standard150_worker", "preflight_context_invalid"),
    ("canonical_mode", "standard_150", "preflight_context_invalid"),
    ("website_url", "ftp://example.com/", "invalid_worker_target"),
    ("owner_attested_robots_override", True, "invalid_robots_policy"),
])
def test_own_01_validly_signed_grant_for_other_identity_never_reserves(monkeypatch, field, value, code):
    service = _load_service(monkeypatch, **ALL_GATES_ON)
    tasks = _install_tasks(monkeypatch, service, [200])
    entitlement, grant = _mint()
    forged = _seal({**grant, field: value}, ADMISSION_KEY)
    reply, status = _reserve_route(monkeypatch, service, entitlement, forged)
    assert (status, reply) == (409, {"success": False, "error": code})
    assert service.lane_e_store.values() == {} and tasks.calls == []


@pytest.mark.parametrize("field,value,code", [
    ("plan_id", "standard150_lifetime", "wrong_entitlement_plan"),
    ("version", "standard150_paid_entitlement_v1", "wrong_entitlement_plan"),
    ("entitlement_state", "active", "paid_entitlement_required"),
    ("entitlement_state", "preview", "paid_entitlement_required"),
    ("entitlement_state", "owner_test", "paid_entitlement_required"),
    ("scan_mode", "standard_150", "invalid_scan_mode"),
    ("access_id", "", "invalid_access_id"),
    ("owner_user_id", "owner/../other", "invalid_owner_user_id"),
])
def test_own_02_validly_signed_unpaid_or_cross_plan_entitlement_never_reserves(monkeypatch, field, value, code):
    service = _load_service(monkeypatch, **ALL_GATES_ON)
    tasks = _install_tasks(monkeypatch, service, [200])
    entitlement, grant = _mint()
    forged = _seal({**entitlement, field: value}, ENTITLEMENT_KEY)
    reply, status = _reserve_route(monkeypatch, service, forged, grant)
    assert (status, reply) == (409, {"success": False, "error": code})
    assert service.lane_e_store.values() == {} and tasks.calls == []


def test_own_03_signing_root_confusion_extra_fields_and_expiry_never_reserve(monkeypatch):
    service = _load_service(monkeypatch, **ALL_GATES_ON)
    tasks = _install_tasks(monkeypatch, service, [200])
    entitlement, grant = _mint()
    cases = [
        (_seal(entitlement, ADMISSION_KEY), grant, "entitlement_signature_invalid"),
        (_seal(entitlement, STANDARD150_EVIDENCE_KEY), grant, "entitlement_signature_invalid"),
        (entitlement, _seal(grant, ENTITLEMENT_KEY), "preflight_signature_invalid"),
        (entitlement, _seal(grant, TERMINAL_KEY), "preflight_signature_invalid"),
        (_seal({**entitlement, "has_full_access": True}, ENTITLEMENT_KEY), grant, "entitlement_signature_invalid"),
        ({k: v for k, v in entitlement.items() if k != "proof"}, grant, "entitlement_signature_invalid"),
        (*_mint(issued=datetime.now(timezone.utc) - timedelta(seconds=200)), "entitlement_expired"),
        (*_mint(issued=datetime.now(timezone.utc) + timedelta(seconds=30)), "entitlement_expired"),
        (*_mint(ttl=301), "entitlement_expired"),
    ]
    for ent, gr, code in cases:
        reply, status = _reserve_route(monkeypatch, service, ent, gr)
        assert (status, reply) == (409, {"success": False, "error": code}), code
    mismatched_time = _seal({**grant, "expires_at": _iso(datetime.now(timezone.utc) + timedelta(seconds=60))}, ADMISSION_KEY)
    reply, status = _reserve_route(monkeypatch, service, entitlement, mismatched_time)
    assert (status, reply["error"]) == (409, "preflight_time_mismatch")
    assert service.lane_e_store.values() == {} and tasks.calls == []


# ===========================================================================
# CHAIN: Base44 package issuer (JS) -> coordinator (Python) -> Cloud Tasks body
#        -> worker preflight (Python). Offline; proves wire-format parity only.
# ===========================================================================
_JS_MINT = """
import { readFileSync } from 'node:fs';
import { mintExtended500AdmissionEvidence } from './base44/functions/issueExtended500AdmissionV1/issuer.js';
const input = JSON.parse(readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(await mintExtended500AdmissionEvidence(input)));
"""


def _js_mint(now_ms: int, **scan_overrides) -> dict:
    user = {"id": "owner_500", "email": "owner500@example.com"}
    scan = {
        "id": "scan_request_500", "owner_user_id": "owner_500", "project_id": "project_500",
        "request_id": "request_500", "idempotency_key": "idem_request_500", "attempt_count": 1,
        "scan_mode": "extended_500", "status": "queued", "website_url": "https://example.com/",
        "path_prefix": None, "respect_robots_txt": True, "owner_attested_robots_override": False,
        **scan_overrides,
    }
    access = {
        "id": "access_500", "owner_user_id": "owner_500", "user_email": "owner500@example.com",
        "app_id": "6a498732ec779dfaaeab0e53", "plan_id": "extended500_lifetime",
        "access_status": "active", "has_full_access": True, "grant_source": "stripe_checkout",
        "stripe_checkout_session_id": "cs_test_lane_e", "paid_at": "2026-10-28T12:00:00.000Z",
    }
    child = subprocess.run(
        ["node", "--input-type=module", "-e", _JS_MINT],
        input=json.dumps({
            "user": user, "scan": scan, "accessRows": [access], "nowMs": now_ms,
            "entitlementSigningKey": ENTITLEMENT_KEY, "grantSigningKey": ADMISSION_KEY,
        }),
        cwd=ROOT, text=True, capture_output=True, check=True, timeout=30,
    )
    return json.loads(child.stdout)


def test_chain_01_js_issued_evidence_reserves_enqueues_and_passes_worker_preflight_only_in_window(monkeypatch):
    issued = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(seconds=5)
    evidence = _js_mint(int(issued.timestamp() * 1000))
    assert evidence["ok"] is True, evidence
    service = _load_service(monkeypatch, **ALL_GATES_ON)
    tasks = _install_tasks(monkeypatch, service, [200])
    reply, status = _reserve_route(monkeypatch, service, evidence["entitlement"], evidence["preflight_grant"])
    assert status == 200 and reply["state"] == "enqueued" and reply["admitted"] is False
    assert len(tasks.calls) == 1
    call = tasks.calls[0]
    assert call["url"] == f"https://cloudtasks.googleapis.com/v2/{EXT500_QUEUE}/tasks"
    assert call["task"]["httpRequest"]["url"] == EXT500_WORKER
    assert call["task"]["httpRequest"]["oidcToken"]["audience"] == "https://extended500-worker.example"
    body = _task_body(call)
    job = {k: v for k, v in body.items() if k != "signed_grant"}
    frozen = _frozen500(body["signed_grant"])
    verdict = lambda delta, scan=frozen: evaluate_extended500_preflight(  # noqa: E731
        job, scan, body["signed_grant"], ADMISSION_KEY, now=issued + timedelta(seconds=delta),
    )
    assert verdict(30) == "verified_read_only"
    assert verdict(30, {**frozen, "owner_user_id": "owner_other"}) == "owner_request_identity_mismatch"
    assert verdict(30, {**frozen, "project_id": "project_other"}) == "owner_request_identity_mismatch"
    assert verdict(30, {**frozen, "attempt_count": 2}) == "superseded_attempt"
    assert verdict(30, {**frozen, "status": "complete"}) == "run_not_queued"
    # Short-lived grant expired while queued (Cloud Tasks may retry for up to an hour).
    assert verdict(120) == "grant_expired_or_out_of_window"
    assert verdict(3600) == "grant_expired_or_out_of_window"


# ===========================================================================
# Q: unknown queue outcomes and retry behaviour
# ===========================================================================
@pytest.mark.parametrize("outcome,http,state", [
    (ConnectionError("network reset"), 202, "dispatch_unknown"),
    (TimeoutError("read timeout"), 202, "dispatch_unknown"),
    (500, 202, "dispatch_unknown"),
    (503, 202, "dispatch_unknown"),
    (429, 202, "dispatch_unknown"),
    (409, 202, "dispatch_unknown"),
    (200, 200, "enqueued"),
])
def test_q_01_every_cloud_tasks_outcome_keeps_slot_and_never_claims_admission(monkeypatch, outcome, http, state):
    service = _load_service(monkeypatch, **ALL_GATES_ON)
    tasks = _install_tasks(monkeypatch, service, [outcome])
    entitlement, grant = _mint()
    reply, status = _reserve_route(monkeypatch, service, entitlement, grant)
    assert status == http
    assert reply["success"] is True and reply["reserved"] is True and reply["state"] == state
    assert reply["admitted"] is False and reply["worker_execution_enabled"] is False
    assert set(_states(service).values()) == {state}
    assert len(tasks.calls) == 1 and tasks.calls[0]["task"]["name"] == reply["task_name"]
    assert tasks.calls[0]["timeout"] == 20


def test_q_02_unknown_outcome_retry_with_reminted_evidence_reuses_exact_receipt_and_task(monkeypatch):
    service = _load_service(monkeypatch, **ALL_GATES_ON)
    tasks = _install_tasks(monkeypatch, service, [ConnectionError("lost"), 200])
    first, grant = _mint(issued=datetime.now(timezone.utc) - timedelta(seconds=30))
    reply1, status1 = _reserve_route(monkeypatch, service, first, grant)
    assert (status1, reply1["state"], reply1["replayed"]) == (202, "dispatch_unknown", False)
    # Base44 re-mints a NEW short-lived pair for the same frozen ScanRun.
    again, grant2 = _mint()
    assert again["issued_at"] != first["issued_at"]
    reply2, status2 = _reserve_route(monkeypatch, service, again, grant2)
    assert (status2, reply2["state"], reply2["replayed"]) == (200, "enqueued", True)
    assert reply2["task_name"] == reply1["task_name"]
    assert [c["task"]["name"] for c in tasks.calls] == [reply1["task_name"]] * 2
    assert len(service.lane_e_store.values()) == 2
    assert set(_states(service).values()) == {"enqueued"}


def test_q_03_late_unknown_or_409_never_downgrades_a_confirmed_enqueue(monkeypatch):
    service = _load_service(monkeypatch, **ALL_GATES_ON)
    _install_tasks(monkeypatch, service, [200, 409, ConnectionError("late")])
    entitlement, grant = _mint()
    for expected_reply in ("enqueued", "dispatch_unknown", "dispatch_unknown"):
        reply, _ = _reserve_route(monkeypatch, service, entitlement, grant)
        assert reply["state"] == expected_reply and reply["admitted"] is False
        assert set(_states(service).values()) == {"enqueued"}


def test_q_04_post_enqueue_state_write_failure_reports_unavailable_and_keeps_reservation(monkeypatch):
    service = _load_service(monkeypatch, **ALL_GATES_ON)
    tasks = _install_tasks(monkeypatch, service, [200, 409])
    entitlement, grant = _mint()

    def broken(_claim, _state):
        raise RuntimeError("firestore write lost after enqueue")

    original = service.update_dispatch_state
    monkeypatch.setattr(service, "update_dispatch_state", broken)
    reply, status = _reserve_route(monkeypatch, service, entitlement, grant)
    assert (status, reply) == (503, {"success": False, "error": "extended500_coordinator_unavailable"})
    assert set(_states(service).values()) == {"reserved"}  # never released, never claimed enqueued
    monkeypatch.setattr(service, "update_dispatch_state", original)
    reply, status = _reserve_route(monkeypatch, service, entitlement, grant)
    assert (status, reply["state"], reply["replayed"]) == (202, "dispatch_unknown", True)
    assert len({c["task"]["name"] for c in tasks.calls}) == 1


def test_q_05_firestore_failure_before_reservation_never_enqueues(monkeypatch):
    service = _load_service(monkeypatch, **ALL_GATES_ON)
    tasks = _install_tasks(monkeypatch, service, [200])

    def unavailable(*_args):
        raise RuntimeError("firestore unavailable")

    monkeypatch.setattr(service, "reserve", unavailable)
    reply, status = _reserve_route(monkeypatch, service, *_mint())
    assert (status, reply["error"]) == (503, "extended500_coordinator_unavailable")
    assert tasks.calls == []


def _fake_gcloud(tmp_path: Path, describe_exit: int) -> tuple[dict, Path]:
    log = tmp_path / "gcloud.log"
    script = tmp_path / "bin" / "gcloud"
    script.parent.mkdir()
    script.write_text(
        "#!/usr/bin/env bash\n"
        f'echo "$*" >> "{log}"\n'
        f'if [[ "$*" == *"queues describe"* && ! -f "{tmp_path}/created" ]]; then exit {describe_exit}; fi\n'
        f'if [[ "$*" == *"queues create"* ]]; then touch "{tmp_path}/created"; fi\n'
        "exit 0\n"
    )
    script.chmod(0o755)
    env = {"PATH": f"{script.parent}{os.pathsep}{os.environ.get('PATH', '')}",
           "GCP_PROJECT": "lane-e", "GCP_LOCATION": "us-east1"}
    return env, log


@pytest.mark.parametrize("queue,extra,code", [
    ("fixlist-standard150", {}, 2),
    ("extended500-x", {"SCAN_TASKS_QUEUE_NAME": "extended500-x"}, 2),
    ("extended500-x", {"SCAN_DRAIN_QUEUE_NAME": "extended500-x"}, 2),
    ("extended500-x", {}, 0),
])
def test_q_06_queue_provisioning_is_dedicated_dry_run_by_default(tmp_path, queue, extra, code):
    env, log = _fake_gcloud(tmp_path, describe_exit=1)
    child = subprocess.run(
        ["bash", str(SERVICE_DIR / "provision-queue.sh")],
        env={**env, "EXTENDED500_QUEUE_NAME": queue, **extra},
        text=True, capture_output=True, timeout=30,
    )
    assert child.returncode == code, child.stderr
    assert not log.exists(), "no gcloud call without explicit operator approval"
    if code == 0:
        assert "DRY RUN" in child.stdout


def test_q_07_approved_provisioning_creates_then_pauses_and_never_resumes(tmp_path):
    env, log = _fake_gcloud(tmp_path, describe_exit=1)
    child = subprocess.run(
        ["bash", str(SERVICE_DIR / "provision-queue.sh")],
        env={**env, "EXTENDED500_QUEUE_NAME": "extended500-lane-e",
             "EXTENDED500_QUEUE_PROVISION_APPROVED": "YES"},
        text=True, capture_output=True, timeout=30,
    )
    assert child.returncode == 0, child.stderr
    calls = log.read_text().splitlines()
    verbs = [line.split()[2] for line in calls]
    assert verbs == ["describe", "create", "pause", "describe"], calls
    assert all("extended500-lane-e" in line for line in calls)
    assert not any("resume" in line or "fixlist-standard150" in line for line in calls)


# ===========================================================================
# C: concurrency (optimistic-transaction fake) and the Firestore live gap
# ===========================================================================
def _contend(service, candidates):
    def attempt(candidate):
        try:
            result = service.reserve(*candidate)
            return ("ok", result["outcome"], result["task_name"])
        except service.core.AdmissionRefused as exc:
            return ("refused", exc.code, "")

    service.lane_e_store.barrier = threading.Barrier(len(candidates))
    with ThreadPoolExecutor(max_workers=len(candidates)) as executor:
        decisions = list(executor.map(attempt, candidates))
    service.lane_e_store.barrier = None
    return decisions


def test_c_01_twelve_contending_requests_for_one_owner_have_exactly_one_winner(monkeypatch):
    service = _load_service(monkeypatch)
    decisions = _contend(service, [_mint(request=f"request_c01_{n}") for n in range(12)])
    winners = [d for d in decisions if d[0] == "ok"]
    assert len(winners) == 1 and winners[0][1] == "reserved", decisions
    assert sorted(d[1] for d in decisions if d[0] == "refused") == ["owner_slot_busy"] * 11
    assert len(service.lane_e_store.values()) == 2
    assert service.lane_e_store.conflicts >= 11, "contention must actually have been exercised"
    slot = service.lane_e_store.values()["extended500_owner_slots/owner_500"]
    assert slot["state"] == "reserved" and winners[0][2].endswith(f"{slot['receipt_id']}-a1")


def test_c_02_twelve_concurrent_retries_of_one_request_reserve_once_and_replay_eleven(monkeypatch):
    service = _load_service(monkeypatch)
    one = _mint(request="request_c02")
    decisions = _contend(service, [one] * 12)
    assert sorted(d[1] for d in decisions) == ["replayed"] * 11 + ["reserved"]
    assert len({d[2] for d in decisions}) == 1
    assert len(service.lane_e_store.values()) == 2
    assert service.lane_e_store.conflicts >= 11


def test_c_03_twelve_distinct_owners_never_block_each_other(monkeypatch):
    service = _load_service(monkeypatch)
    decisions = _contend(service, [_mint(owner=f"owner_c03_{n}", request=f"request_c03_{n}") for n in range(12)])
    assert [d[1] for d in decisions] == ["reserved"] * 12
    assert len(service.lane_e_store.values()) == 24


def test_c_04_gap_single_winner_depends_entirely_on_transaction_serializability(monkeypatch):
    """Characterizes the Firestore emulator/live gap; this is NOT a pass of the gate.

    With the same decision core but a store that does not validate reads at commit
    (what a mis-wired adapter, a non-transactional write, or a wrong client would
    give), several contenders win and orphan receipts appear. Single-winner is
    therefore a property of Firestore transaction isolation, which no offline test
    in this repository proves. See RED c_05.
    """
    service = _load_service(monkeypatch, store=FakeFirestore(serializable=False))
    decisions = _contend(service, [_mint(request=f"request_c04_{n}") for n in range(12)])
    winners = [d for d in decisions if d[0] == "ok" and d[1] == "reserved"]
    assert len(winners) > 1
    assert len(service.lane_e_store.values()) > 2


@red("a CI job running the Extended 500 reservation contention test against the Firestore emulator")
def test_c_05_ci_runs_extended500_contention_against_firestore_emulator():
    workflows = sorted((ROOT / ".github" / "workflows").glob("*.y*ml"))
    assert workflows, "workflow inventory unavailable"
    matches = [
        path.name for path in workflows
        if re.search(r"firestore", text := path.read_text(), re.I)
        and re.search(r"emulator", text, re.I)
        and re.search(r"extended500", text, re.I)
    ]
    assert matches, "no workflow runs an Extended 500 Firestore-emulator contention test"


# ===========================================================================
# T: released-slot tombstones and verified terminal release
# ===========================================================================
def test_t_01_released_receipt_is_a_permanent_tombstone_and_frees_only_the_slot(monkeypatch):
    service = _load_service(monkeypatch, **ALL_GATES_ON)
    tasks = _install_tasks(monkeypatch, service, [200, 200])
    entitlement, grant = _mint(request="request_t01")
    reply, _ = _reserve_route(monkeypatch, service, entitlement, grant)
    first_task = reply["task_name"]
    out = _release_route(monkeypatch, service, entitlement, _terminal(entitlement))
    assert out == {"success": True, "outcome": "released"}  # success path is a bare 200 body
    assert set(_states(service).values()) == {"released"}

    reply, status = _reserve_route(monkeypatch, service, *_mint(request="request_t01"))
    assert (status, reply) == (409, {"success": False, "state": "terminal_replay", "admitted": False})
    assert len(tasks.calls) == 1, "a tombstoned request must never be re-dispatched"

    nxt, nxt_grant = _mint(request="request_t01_next")
    reply, status = _reserve_route(monkeypatch, service, nxt, nxt_grant)
    assert status == 200 and reply["task_name"] != first_task
    slot = service.lane_e_store.values()["extended500_owner_slots/owner_500"]
    assert slot["state"] == "enqueued" and slot["request_id"] == "request_t01_next"

    out = _release_route(monkeypatch, service, entitlement, _terminal(entitlement))
    assert out == {"success": True, "outcome": "already_released"}
    out, status = _release_route(monkeypatch, service, entitlement, _terminal(entitlement, status="failed"))
    assert (status, out["error"]) == (409, "terminal_conflict")
    slot_after = service.lane_e_store.values()["extended500_owner_slots/owner_500"]
    assert slot_after == slot, "a late release of an old receipt must not touch the newer active slot"


def test_t_02_release_requires_exact_terminal_proof_from_the_terminal_root(monkeypatch):
    service = _load_service(monkeypatch, **ALL_GATES_ON)
    _install_tasks(monkeypatch, service, [200])
    entitlement, grant = _mint(request="request_t02")
    _reserve_route(monkeypatch, service, entitlement, grant)
    before = service.lane_e_store.values()
    other, _ = _mint(request="request_t02_never_reserved")
    cases = [
        (entitlement, _terminal(entitlement, key=ENTITLEMENT_KEY), "verified_terminal_proof_invalid"),
        (entitlement, _terminal(entitlement, key=STANDARD150_EVIDENCE_KEY), "verified_terminal_proof_invalid"),
        (entitlement, {**_terminal(entitlement), "verified_terminal": True}, "verified_terminal_proof_invalid"),
        (entitlement, _terminal(entitlement, attempt_count=2), "verified_terminal_identity_mismatch"),
        (entitlement, _terminal(entitlement, owner_user_id="owner_other"), "verified_terminal_identity_mismatch"),
        (entitlement, _terminal(entitlement, access_id="access_other"), "verified_terminal_identity_mismatch"),
        (entitlement, _terminal(entitlement, version="extended500_terminal_v0"), "verified_terminal_version_invalid"),
        (entitlement, _terminal(entitlement, status="running"), "verified_terminal_required"),
        (entitlement, _terminal(entitlement, status="queued"), "verified_terminal_required"),
        (_seal(entitlement, ADMISSION_KEY), _terminal(entitlement), "entitlement_signature_invalid"),
        (other, _terminal(other), "reservation_not_found"),
    ]
    for ent, terminal, code in cases:
        out, status = _release_route(monkeypatch, service, ent, terminal)
        assert (status, out["error"]) == (409, code), code
    assert service.lane_e_store.values() == before


def test_t_03_tombstone_cannot_be_reopened_by_reminted_evidence_with_other_access_or_attempt(monkeypatch):
    service = _load_service(monkeypatch, **ALL_GATES_ON)
    tasks = _install_tasks(monkeypatch, service, [200])
    entitlement, grant = _mint(request="request_t03")
    _reserve_route(monkeypatch, service, entitlement, grant)
    _release_route(monkeypatch, service, entitlement, _terminal(entitlement, status="failed"))
    before = service.lane_e_store.values()
    for overrides in ({"access": "access_second_purchase"}, {"attempt": 2}):
        reply, status = _reserve_route(monkeypatch, service, *_mint(request="request_t03", **overrides))
        assert (status, reply["error"]) == (409, "request_replay_conflict"), overrides
    assert service.lane_e_store.values() == before and len(tasks.calls) == 1


@red("an independent verified terminal-release issuer that signs extended500_verified_terminal_release_v1")
def test_t_04_a_terminal_release_issuer_exists_outside_the_coordinator():
    issuers = [
        str(path.relative_to(ROOT)) for path in _source_files("scanner-api/app", "src", "base44/functions", "extended500-admission")
        if path.name != "service.py" and "extended500_verified_terminal_release_v1" in path.read_text(errors="ignore")
    ]
    assert issuers, "no source signs a verified terminal release; reserved owner slots can never be released"


# ===========================================================================
# G: short-lived grants expiring while queued; pickup re-authorization
# ===========================================================================
def test_g_01_expired_grant_never_authorizes_and_the_paid_owner_stays_wedged(monkeypatch):
    service = _load_service(monkeypatch, **ALL_GATES_ON)
    tasks = _install_tasks(monkeypatch, service, [200])
    issued = datetime.now(timezone.utc) - timedelta(seconds=5)
    entitlement, grant = _mint(issued=issued, request="request_g01")
    reply, _ = _reserve_route(monkeypatch, service, entitlement, grant)
    assert reply["state"] == "enqueued"
    body = _task_body(tasks.calls[0])
    job = {k: v for k, v in body.items() if k != "signed_grant"}
    frozen = _frozen500(body["signed_grant"])
    assert tasks.calls[0]["task"]["dispatchDeadline"] == "480s"
    for delay in (120, 121, 480, 3600):  # queue wait / dispatch deadline / max retry duration
        assert evaluate_extended500_preflight(
            job, frozen, body["signed_grant"], ADMISSION_KEY, now=issued + timedelta(seconds=delay),
        ) == "grant_expired_or_out_of_window", delay
    with pytest.raises(service.core.AdmissionRefused, match="entitlement_expired"):
        service.verify_assertions(entitlement, grant, now=issued + timedelta(seconds=121))
    # No lease expiry: with the grant dead and no terminal issuer, the owner cannot start again.
    reply, status = _reserve_route(monkeypatch, service, *_mint(request="request_g01_next"))
    assert (status, reply["error"]) == (409, "owner_slot_busy")


@red("a dedicated /scan-job-extended500 worker with pickup-time durable (ScanRun + paid Access) re-authorization")
def test_g_02_dedicated_extended500_worker_route_exists():
    paths = {getattr(route, "path", "") for route in main_module.app.routes}
    assert "/scan-job-extended500-preflight" in paths  # control: the read-only preflight exists
    assert "/scan-job-extended500" in paths, "the coordinator's task target does not exist"


# ===========================================================================
# F: false-success prevention
# ===========================================================================
def test_f_01_unreviewed_handoff_ignores_every_result_claim_of_review_or_completion():
    claims = {
        "review_status": "reviewed", "pages_reviewed": 500, "status": "complete",
        "scan_status": "complete", "fix_list_id": "fl_forged", "authority_proof": "f" * 64,
        "health_score": 99, "release_gate_eligible": False,
    }
    handoff = build_extended500_evidence_handoff(_scan500(), {**_result500(size=3), **claims}, ENTITLEMENT_KEY)
    assert handoff["review"] == {"review_status": "not_reviewed", "pages_reviewed": 0, "release_gate_eligible": False}
    flat = json.dumps(handoff)
    for forbidden in ("fl_forged", "f" * 64, '"complete"', '"health_score"', '"status"', '"reviewed"'):
        assert forbidden not in flat, forbidden
    with pytest.raises(ValueError, match="release authority"):
        build_extended500_evidence_handoff(_scan500(), {**_result500(size=3), "release_gate_eligible": True}, ENTITLEMENT_KEY)


def test_f_02_coordinator_health_never_advertises_worker_completion(monkeypatch):
    for env in ({}, ALL_GATES_ON):
        health = _load_service(monkeypatch, **env).health()
        assert health["worker_completion_enabled"] is False
        assert health["service"] == "fixlist-extended500-admission"


@red("a reviewed, signed Extended 500 authority protocol (Python builder + Base44/JS validator)")
def test_f_03_reviewed_extended500_authority_protocol_exists():
    pattern = re.compile(r"extended_?500.*review", re.I)
    python = [p for p in _source_files("scanner-api/app", suffixes=(".py",)) if pattern.search(p.name)]
    javascript = [p for p in _source_files("src/lib", "base44/functions", suffixes=(".js", ".ts")) if pattern.search(str(p.relative_to(ROOT)))]
    assert python and javascript, "no reviewed 500 authority: the only 500 envelope is the unreviewed handoff"


# ===========================================================================
# W: worker / coordinator disabled by default
# ===========================================================================
def test_w_01_coordinator_defaults_off_and_refuses_before_reading_the_body(monkeypatch):
    service = _load_service(monkeypatch)
    assert (service.ENABLED, service.QUEUE_ENABLED, service.WORKER_READY) == (False, False, False)
    tasks = _install_tasks(monkeypatch, service, [200])
    for handler in (service.reservation_route, service.release_route):
        reply, status = _route(monkeypatch, service, handler, {"unexpected": "shape"})
        assert (status, reply["error"]) == (503, "extended500_admission_disabled")
    admission_only = _load_service(monkeypatch, EXTENDED500_ATOMIC_ADMISSION_ENABLED="true")
    reply, status = _reserve_route(monkeypatch, admission_only, *_mint())
    assert (status, reply["error"]) == (503, "extended500_dispatch_not_ready")
    assert service.lane_e_store.values() == {} and admission_only.lane_e_store.values() == {}
    assert tasks.calls == []


@pytest.mark.parametrize("env", [
    {},
    {"FIXLIST_EXTENDED500_PREFLIGHT_ENABLED": "false"},
    {"FIXLIST_EXTENDED500_PREFLIGHT_ENABLED": "true"},
    {"FIXLIST_EXTENDED500_PREFLIGHT_ENABLED": "true", "EXTENDED500_ADMISSION_SIGNING_KEY": "short"},
])
def test_w_02_preflight_defaults_off_and_needs_its_own_key_before_any_read(monkeypatch, env):
    monkeypatch.delenv("FIXLIST_EXTENDED500_PREFLIGHT_ENABLED", raising=False)
    monkeypatch.delenv("EXTENDED500_ADMISSION_SIGNING_KEY", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    reads = []

    async def read(_client, scan_id):
        reads.append(scan_id)
        raise AssertionError("no ScanRun read while disabled")

    monkeypatch.setattr(main_module, "require_cloud_tasks_oidc", lambda _token: None)
    monkeypatch.setattr(main_module, "read_scan_run", read)
    _, grant = _mint()
    job = {k: grant[k] for k in (
        "scan_id", "request_id", "idempotency_key", "project_id", "owner_user_id",
        "attempt_count", "website_url", "path_prefix", "respect_robots_txt",
        "owner_attested_robots_override",
    )}
    with TestClient(main_module.app) as client:
        response = client.post("/scan-job-extended500-preflight",
                               json={**job, "scan_mode": "extended_500", "signed_grant": grant})
    assert response.status_code == 503 and reads == []


def test_w_03_standard150_build_and_deploy_configs_never_supply_extended500_switches():
    configs = sorted(ROOT.glob("cloudbuild*.yaml")) + sorted((ROOT / ".github" / "workflows").glob("*.y*ml"))
    configs += [ROOT / "Dockerfile", ROOT / "scanner-api" / "Dockerfile"]
    assert len(configs) > 5
    leaking = [p.name for p in configs if p.exists() and re.search(r"EXTENDED500_|FIXLIST_EXTENDED500_", p.read_text())]
    assert leaking == []


@red("feature switches enabling ONLY on the exact lowercase value 'true' (README contract); case-folded variants enable today")
@pytest.mark.parametrize("surface,value", [
    ("coordinator", "TRUE"),
    ("coordinator", "True"),
    ("preflight", " TRUE "),
])
def test_w_04_feature_switches_require_exact_true(monkeypatch, surface, value):
    if surface == "coordinator":
        service = _load_service(monkeypatch, **{key: value for key in ALL_GATES_ON})
        assert (service.ENABLED, service.QUEUE_ENABLED, service.WORKER_READY) == (False, False, False)
        return
    monkeypatch.setenv("FIXLIST_EXTENDED500_PREFLIGHT_ENABLED", value)
    monkeypatch.setenv("EXTENDED500_ADMISSION_SIGNING_KEY", ADMISSION_KEY)
    reads = []

    async def read(_client, scan_id):
        reads.append(scan_id)
        return None

    monkeypatch.setattr(main_module, "require_cloud_tasks_oidc", lambda _token: None)
    monkeypatch.setattr(main_module, "read_scan_run", read)
    _, grant = _mint()
    with TestClient(main_module.app) as client:
        client.post("/scan-job-extended500-preflight", json={
            **{k: grant[k] for k in (
                "scan_id", "request_id", "idempotency_key", "project_id", "owner_user_id",
                "attempt_count", "website_url", "path_prefix", "respect_robots_txt",
                "owner_attested_robots_override",
            )},
            "scan_mode": "extended_500", "signed_grant": grant,
        })
    assert reads == [], "preflight read a ScanRun although the switch was not exactly 'true'"


# ===========================================================================
# D: duplicate payment / grant duplication (candidate has fingerprint + slot code)
# ===========================================================================
def test_d_01_a_second_paid_access_cannot_mint_a_second_reservation(monkeypatch):
    service = _load_service(monkeypatch, **ALL_GATES_ON)
    tasks = _install_tasks(monkeypatch, service, [200])
    _reserve_route(monkeypatch, service, *_mint(request="request_d01"))
    before = service.lane_e_store.values()
    reply, status = _reserve_route(monkeypatch, service, *_mint(request="request_d01", access="access_dup"))
    assert (status, reply["error"]) == (409, "request_replay_conflict")
    reply, status = _reserve_route(monkeypatch, service, *_mint(request="request_d01_b", access="access_dup"))
    assert (status, reply["error"]) == (409, "owner_slot_busy")
    assert service.lane_e_store.values() == before and len(tasks.calls) == 1


# ===========================================================================
# P: per-page privacy across the boundary
# ===========================================================================
def test_p_01_full_500_page_handoff_carries_no_raw_html_main_text_or_link_cache():
    result = _result500()
    pristine = copy.deepcopy(result)
    handoff = build_extended500_evidence_handoff(_scan500(), result, ENTITLEMENT_KEY)
    assert len(handoff["scan"]["pages"]) == 500
    flat = json.dumps(handoff)
    for sentinel in PRIVATE_SENTINELS:
        assert sentinel not in flat
    forbidden = {"main_text", "main_text_signature", "html", "raw_html", "body", "text",
                 "_reachability_links", "local_entity_observations",
                 "contextual_freshness_evidence", "debug_future_field"}
    assert all(not (forbidden & set(page)) for page in handoff["scan"]["pages"])
    assert result == pristine, "projection must not mutate internal review evidence"


@red("recursive privacy projection: allowlisted container fields can smuggle raw HTML/main text")
def test_p_02_nested_private_content_never_crosses_the_500_handoff_boundary():
    smuggle = {
        "geo_evidence": {"main_text": PRIVATE_SENTINELS[0], "snapshot": PRIVATE_SENTINELS[1]},
        "redirect_fetch_evidence": {"raw_html": PRIVATE_SENTINELS[1]},
        "url_verification": {"body": PRIVATE_SENTINELS[1]},
    }
    handoff = build_extended500_evidence_handoff(_scan500(), _result500(size=2, page_extra=smuggle), ENTITLEMENT_KEY)
    flat = json.dumps(handoff)
    leaked = [sentinel for sentinel in PRIVATE_SENTINELS if sentinel in flat]
    assert leaked == [], f"nested private page content crossed the signed boundary: {leaked}"


def test_p_03_queue_body_and_firestore_documents_carry_no_payment_or_private_material(monkeypatch):
    service = _load_service(monkeypatch, **ALL_GATES_ON)
    tasks = _install_tasks(monkeypatch, service, [200])
    entitlement, grant = _mint(request="request_p03")
    _reserve_route(monkeypatch, service, entitlement, grant)
    body = _task_body(tasks.calls[0])
    assert set(body) == {
        "scan_mode", "scan_id", "request_id", "idempotency_key", "project_id", "owner_user_id",
        "attempt_count", "website_url", "path_prefix", "respect_robots_txt",
        "owner_attested_robots_override", "signed_grant",
    }
    assert body["signed_grant"] == grant
    wire = json.dumps(tasks.calls[0]["task"])
    for secret in ("access_500", entitlement["proof"], ENTITLEMENT_KEY, ADMISSION_KEY, COORDINATOR_KEY):
        assert secret not in wire
    docs = service.lane_e_store.values()
    slot = docs["extended500_owner_slots/owner_500"]
    receipt = next(v for k, v in docs.items() if k.startswith("extended500_request_receipts/"))
    assert set(slot) == {"schema", "owner_user_id", "receipt_id", "request_id", "scan_id",
                         "attempt_count", "state", "issued_at"}
    assert set(receipt) == {"schema", "receipt_id", "fingerprint", "owner_user_id", "request_id",
                            "scan_id", "attempt_count", "task_name", "state", "issued_at"}
    stored = json.dumps(docs)
    for secret in ("access_500", entitlement["proof"], grant["proof"], "https://example.com/"):
        assert secret not in stored
