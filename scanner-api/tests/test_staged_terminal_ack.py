import json
from types import SimpleNamespace

import httpx
import pytest

from app import main, scan_job, staged_completion as completion
from app.authority_seal import create_authority_seal
from app.stage_tasks import StageTaskDispatcher
from app.staged_scan import StageRetry, StagedScanRuntime
from app.workspace import MemoryWorkspace, attempt_prefix
from tests.test_stage_tasks import Client


KEY = "fixture-staged-acknowledgement-key"


class SavedJob:
    async def prepare(self, monkeypatch, *, cap=150, status="complete"):
        monkeypatch.setenv("SCAN_EVIDENCE_SIGNING_KEY", KEY)
        monkeypatch.setenv("BASE44_API_URL", "https://fixture.invalid")
        monkeypatch.setenv("BASE44_APP_ID", "staged-fixture")
        scan = self.scan = {
            "id": "scan-1", "status": status, "owner_user_id": "user-1", "request_id": "req-1",
            "idempotency_key": "req-1", "project_id": "project-1", "attempt_count": 1,
            "website_url": "https://fixture.invalid/", "normalized_domain": "fixture.invalid",
            "path_prefix": "", "respect_robots_txt": True, "owner_attested_robots_override": False,
            "page_cap": cap, "scan_mode": f"standard_{cap}", "pipeline_mode": "staged",
            "fix_list_id": "list-1", "admission_access_id": "access-1",
            "admission_claim_sequence": 1, "admission_barrier_generation": 1,
            "beta_revision_fingerprint": completion.V9_WORKER_RELEASE_FINGERPRINT,
            "admission_release_state": "pending",
        }
        self.writer = completion.WRITERS[status]
        scan["authority_proof" if status == "complete" else "result_integrity_proof"] = "a" * 64

        async def read(_client, scan_id):
            assert scan_id == scan["id"]
            return dict(scan)

        self.store = MemoryWorkspace()
        self.runtime = StagedScanRuntime(self.store, None, SimpleNamespace(read_scan=read))
        # Start with only the launcher's required fields, let the plan-stage
        # canonicalizer populate the downstream task from the durable row.
        launch = main.ScanJobRequest(scan_id=scan["id"], request_id=scan["request_id"],
                                     website_url=scan["website_url"], scan_mode=scan["scan_mode"]).model_dump()
        self.job = self.runtime._canonical_job(scan, launch)
        self.prefix = attempt_prefix(scan["id"], 1)
        self.frontier = {"stage": "finalize", "state_ref": "batches/0.state.json.gz", "batch": 1, "pages_crawled": 1}
        await self.store.write(self.prefix + "frontier.json", self.frontier)
        generations = {}
        for label, name in (("input_state", self.frontier["state_ref"]), ("result", "result.json.gz"), ("review", "review.json.gz")):
            generations[label] = str(await self.store.write(self.prefix + name, {"fixture": label}))
        stamp = "2026-11-27T12:00:00.000Z"
        await self.store.write(self.prefix + "completion.json", {"result_ready_at": stamp})
        self.binding = completion.binding_for(self.job, scan, self.frontier, 1, generations, stamp, self.writer)
        signed = {"version": "fixture", "scan": {"result_ready_at": stamp}, "identity": {"scan_id": scan["id"]},
                  "review": {"fixture": True}}
        self.envelope = {**signed, "proof": create_authority_seal(signed, KEY)}
        scan["staged_writer_request_proof"] = self.envelope["proof"]
        await completion.retain_packet(self.store, self.prefix, self.binding, self.envelope, KEY)
        self.calls = []
        self.reply = {}
        self.release = True
        self.codes = []
        original_invoke = scan_job.invoke_function

        async def invoke(_client, writer, envelope):
            assert writer == self.writer and envelope == self.envelope
            async with httpx.AsyncClient(transport=httpx.MockTransport(self.send)) as local:
                return await original_invoke(local, writer, envelope)
        monkeypatch.setattr(scan_job, "invoke_function", invoke)

    def send(self, request):
        packet = json.loads(request.content)
        runtime = packet["runtime_request"]
        assert packet["runtime_proof"] == create_authority_seal(runtime, KEY)
        assert runtime["payload"] == self.envelope and request.url.path.endswith(self.binding["route"])
        self.calls.append(runtime["nonce"])
        assert len(set(self.calls)) == len(self.calls)
        code = self.codes.pop(0) if self.codes else 200
        receipt = {"protocol": runtime["protocol"], "function_name": self.writer, "action": "invoke",
                   "nonce": runtime["nonce"], "build_id": self.binding["runtime"]["build_id"],
                   "runtime_activation_id": self.binding["runtime"]["runtime_activation_id"],
                   "release_fingerprint": self.binding["release"], "http_status": code}
        if self.release:
            self.scan.update(admission_release_state="released", admission_release_outcome="released",
                             admission_release_coordinator_request_id=self.scan["request_id"])
        if self.scan["status"] == "complete":
            self.scan["customer_preview_proof"] = "b" * 64
        body = {"success": True, "replayed": True, "fixListVerified": self.scan["status"] == "complete",
                "resultIntegrityVerified": self.scan["status"] == "limited", "scanId": self.scan["id"],
                "fixListId": self.scan["fix_list_id"], "scanRun": dict(self.scan), **self.reply,
                "_worker_runtime": {"receipt": receipt, "proof": create_authority_seal(receipt, KEY)}}
        return httpx.Response(code, json=body)

    async def deliver(self, **kwargs):
        return await self.runtime.process(None, "finalize", self.job, batch=1, **kwargs)

    async def frontier_row(self):
        return (await self.store.read(self.prefix + "frontier.json")).value


@pytest.mark.asyncio
@pytest.mark.parametrize("cap,status", [(150, "complete"), (500, "complete"), (150, "limited"), (500, "limited")])
async def test_serialized_queue_task_reaches_finalizer_and_observes_new_signed_response(monkeypatch, cap, status):
    saved = SavedJob()
    await saved.prepare(monkeypatch, cap=cap, status=status)
    queue = Client()
    dispatch = StageTaskDispatcher("projects/example/locations/europe-west1/queues/scans",
                                   "https://fixture.invalid", "worker@example.invalid", client=queue)
    await dispatch.enqueue(saved.job, "finalize", 1)
    http = queue.requests[0]["task"]["http_request"]
    monkeypatch.setattr(main, "build_staged_runtime", lambda: saved.runtime)
    monkeypatch.setattr(main, "require_cloud_tasks_oidc", lambda token: None)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="https://fixture.invalid") as client:
        response = await client.post(http["url"], content=http["body"], headers=http["headers"])
        assert response.status_code == 200 and response.json()["fix_list_id"] == "list-1"
        duplicate = await client.post(http["url"], content=http["body"], headers=http["headers"])
        assert duplicate.json()["skipped"] == "already_terminal" and len(saved.calls) == 1
    frontier = await saved.frontier_row()
    observed = (await saved.store.read(saved.prefix + frontier["finalize_receipt_ref"])).value
    assert frontier["stage"] == "done" and observed["stage_committed"]
    assert observed["completion_request"]["function"] == saved.writer and observed["completion_request"]["status_code"] == 200
    assert observed["completion_request"]["body_bytes"] > 0 and len(observed["completion_request"]["body_sha256"]) == 64
    assert {k: v["generation"] for k, v in observed["artifacts"].items()} == saved.binding["generations"]
    assert all(v["produced"] is False for v in observed["artifacts"].values())
    assert observed["memory"]["parent_and_review_child_rss_samples"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("wrong", ["owner", "attempt", "cap", "pipeline", "project", "idempotency", "missing_mode", "terminal_status",
                                    "tombstone", "superseded", "early_duplicate", "historical", "wrong_proof", "missing_cache",
                                    "changed_review", "different_writer_route", "changed_scope", "tampered_packet"])
async def test_no_writer_for_unbound_deleted_or_stale_requests(monkeypatch, wrong):
    saved = SavedJob()
    await saved.prepare(monkeypatch)
    change = {"owner": ("owner_user_id", "someone-else"), "project": ("project_id", None), "attempt": ("attempt_count", 2),
              "cap": ("page_cap", None), "pipeline": ("pipeline_mode", None), "idempotency": ("idempotency_key", ""),
              "missing_mode": ("scan_mode", None)}
    if wrong in change:
        field, value = change[wrong]
        saved.job[field] = value
    elif wrong == "terminal_status":
        saved.scan["status"] = "cancelled"
    elif wrong == "historical":
        del saved.scan["staged_writer_request_proof"]
    elif wrong == "tombstone":
        await saved.store.write(saved.runtime._tombstone(saved.job), {"deleted": True})
    elif wrong == "wrong_proof":
        saved.scan["staged_writer_request_proof"] = "3" * 64
    elif wrong == "missing_cache":
        await saved.store.delete_prefix(saved.prefix + "review.json.gz")
    elif wrong == "changed_review":
        path = saved.prefix + "review.json.gz"
        old = await saved.store.read(path)
        await saved.store.write(path, old.value, generation=old.generation)
    elif wrong == "changed_scope":
        saved.scan["admission_claim_sequence"] += 1
    elif wrong in {"different_writer_route", "tampered_packet"}:
        path = saved.prefix + completion.ARCHIVE_NAME
        old = await saved.store.read(path)
        if wrong == "different_writer_route":
            old.value["binding"]["route"] += "other"
        else:
            old.value["envelope"]["review"]["fixture"] = False
        await saved.store.write(path, old.value, generation=old.generation)

    if wrong in {"wrong_proof", "missing_cache", "changed_review", "different_writer_route", "changed_scope", "tampered_packet"}:
        with pytest.raises(StageRetry):
            await saved.deliver()
    elif wrong == "early_duplicate":
        outcome = await saved.runtime.process(None, "batch", saved.job, batch=1)
        assert outcome["skipped"] == "already_terminal"
    else:
        outcome = await saved.deliver(recovery_generation=int(wrong == "superseded"))
        assert outcome.get("skipped")
    assert not saved.calls and (await saved.frontier_row())["stage"] == "finalize"


@pytest.mark.asyncio
@pytest.mark.parametrize("incomplete", ["pending_release", "unconfirmed_proof", "wrong_list", "not_replay", "bad_status"])
async def test_writer_must_verify_terminal_rows_and_release_before_commit(monkeypatch, incomplete):
    saved = SavedJob()
    await saved.prepare(monkeypatch, status="limited")
    if incomplete == "bad_status":
        saved.codes = [503]
    elif incomplete == "pending_release":
        saved.release = False
    else:
        saved.reply = {"unconfirmed_proof": {"resultIntegrityVerified": False}, "wrong_list": {"fixListId": "other"},
                       "not_replay": {"replayed": False}}[incomplete]
    with pytest.raises(StageRetry):
        await saved.deliver()
    assert "finalize_receipt_ref" not in (await saved.frontier_row())
    saved.reply = {}
    saved.release = True
    assert (await saved.deliver())["fix_list_id"] == "list-1"
    assert len(saved.calls) == 2
