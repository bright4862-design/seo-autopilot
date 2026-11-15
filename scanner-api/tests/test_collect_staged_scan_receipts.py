"""Verify the collector against actual staged-workspace write shapes."""

import asyncio
import gzip
import hashlib
import json
import stat
import sys
from datetime import datetime, timedelta, timezone

import pytest

from app.staged_scan import StageRetry
from app.workspace import WorkspaceObject
from scripts import collect_staged_scan_receipts as collector
from tests.test_staged_workspace import Harness


class Reader:
    def __init__(self, workspace):
        self.workspace = workspace
        self.body_reads = []
        self.metadata_reads = []

    async def read(self, key):
        self.body_reads.append(key)
        return await self.workspace.read(key)

    async def generation(self, key):
        self.metadata_reads.append(key)
        generation = self.workspace.objects.get(key, (None, None))[1]
        return str(generation) if generation is not None else None


async def simulated_canary(monkeypatch, *, limited=False, fail_first_finalize=False):
    from app import staged_telemetry

    started = datetime.now(timezone.utc) - timedelta(seconds=1)
    harness = Harness(monkeypatch)
    harness.scan.update(scan_mode="standard_500", page_cap=500)
    harness.job.update(scan_mode="standard_500", page_cap=500)
    owner = harness.scan["owner_user_id"]
    source, config, fingerprint = "a" * 40, "b" * 64, "a" * 16
    revision = collector.WORKER_SERVICE + "-00100-abc"
    for key, value in {
        "FIXLIST_WORKER_SOURCE_SHA": source, "FIXLIST_STAGED_CONFIG_SHA256": config,
        "K_SERVICE": collector.WORKER_SERVICE, "K_REVISION": revision,
        "SCAN_PIPELINE_MODE": "staged", "SCAN_STAGED_OWNER_IDS": owner,
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(staged_telemetry, "live_revision", lambda: {"fingerprint": fingerprint})
    monkeypatch.setattr(staged_telemetry, "measure_worker_peak_memory_bytes", lambda: 140_000_000)
    monkeypatch.setattr(staged_telemetry, "_kernel_memory_bound", lambda: {
        "scope": "cgroup_lifetime", "peak_bytes": 480_000_000, "limit_bytes": 1_073_741_824,
    })
    calls = []
    body = b'{"synthetic":"evidence"}'

    async def review(result):
        staged_telemetry.active_delivery.get().observe_review_memory(350_000_000)
        return {"evidence": "private-review"}

    async def complete(client, scan, result, key, *, review):
        delivery = staged_telemetry.active_delivery.get()
        function = "persistLimitedScanResultV9" if result["pipeline_limited"] else "persistDurableScanAuthorityV9"
        calls.append(function)
        delivery.observe_completion_request(function, body)
        if fail_first_finalize and len(calls) == 1:
            delivery.observe_completion_response(503)
            return {"ok": False, "transient": True}
        delivery.observe_completion_response(200)
        return await harness.complete(client, scan, result, key)

    harness.deps.review, harness.deps.complete = review, complete
    await harness.run("plan")
    for batch in range(3):
        await harness.run("batch", batch=batch)
    if fail_first_finalize:
        with pytest.raises(StageRetry):
            await harness.run("finalize", batch=3, limited=limited)
    await harness.run("finalize", batch=3, limited=limited)
    frontier = await harness.frontier()
    ended = datetime.now(timezone.utc).isoformat()
    report = {
        "schema_version": "staged_500_canary_v1", "production_freeze": False,
        "terminal_outcome_verified": True, "durable_worker_owned": True,
        "attempt_count": 1, "page_cap": 500, "scan_id": harness.scan["id"],
        "request_id": harness.scan["request_id"], "expected_owner_user_id": owner,
        "observed_at": started.isoformat(), "scan_started_at": started.isoformat(), "scan_completed_at": ended,
        "pages_crawled": 120, "pages_planned": 120, "committed_batch_count": 3,
        "terminal_status": "limited" if limited else "complete", "source_sha": source, "release_fingerprint": fingerprint,
        "provenance": {
            "source_sha": source, "release_fingerprint": fingerprint, "worker_config_sha256": config,
            "worker_revision": revision, "prerequisite_sha256": "f" * 64,
            "staged_owner_cohort_sha256": hashlib.sha256(json.dumps([owner]).encode()).hexdigest(),
        },
    }
    return harness, report, frontier, body


@pytest.mark.asyncio
async def test_deferred_ordinary_task_must_be_bound_before_gcs_receipt_collection(monkeypatch):
    _, report, _, _ = await simulated_canary(monkeypatch)
    report["execution_mode"] = "ordinary_user_readback"
    report["provenance"]["ordinary_task_observation"] = "deferred"
    with pytest.raises(collector.EvidenceError, match="ordinary_stage_task_observation_unverified"):
        collector.canary_identity(report)
    report["provenance"]["ordinary_stage_task_observation_sha256"] = "b" * 64
    assert collector.canary_identity(report).scan_id == report["scan_id"]
    del report["execution_mode"]
    with pytest.raises(collector.EvidenceError, match="ordinary_stage_task_observation_unverified"):
        collector.canary_identity(report)


@pytest.mark.asyncio
@pytest.mark.parametrize("limited", [False, True])
async def test_collects_committed_chain_and_an_earlier_review_producer(monkeypatch, limited):
    harness, report, frontier, body = await simulated_canary(monkeypatch, limited=limited, fail_first_finalize=True)
    storage = Reader(harness.store)
    evidence = await collector.collect(collector.canary_identity(report), storage)
    assert evidence["receipt_evidence_verified"] is True
    assert evidence["worker_runtime_verified"] is True
    assert evidence["delivery_count"] == 6
    assert evidence["committed_delivery_count"] == 5
    assert evidence["frontier_generation"] == str(frontier.generation)
    assert evidence["memory"]["sampled_aggregate_rss_peak_bytes"] == 350_000_000
    assert evidence["memory"]["cgroup_lifetime_peak_upper_bound_bytes"] == 480_000_000
    assert evidence["memory"]["all_stages_verified"] is True
    assert evidence["completion_request"] == {
        "function": "persistLimitedScanResultV9" if limited else "persistDurableScanAuthorityV9",
        "body_bytes": len(body), "body_sha256": hashlib.sha256(body).hexdigest(), "status_code": 200,
    }
    assert harness.prefix + "review.json.gz" in storage.metadata_reads
    assert not set(storage.body_reads) & set(storage.metadata_reads)
    assert "private-review" not in json.dumps(evidence)


@pytest.mark.asyncio
@pytest.mark.parametrize(("mutation", "failure"), [
    ("missing_pair", "delivery_receipt_missing"),
    ("wrong_revision", "delivery_runtime_mismatch"),
    ("wrong_attempt", "delivery_receipt_identity_mismatch"),
    ("replaced_state", "batch_checkpoint_lineage_mismatch"),
    ("untrusted_path", "committed_state_reference_invalid"),
    ("incomplete_history", "delivery_history_incomplete"),
    ("deleted", "workspace_deleted"),
    ("frontier_changed", "workspace_changed_during_collection"),
])
async def test_missing_foreign_or_changed_evidence_is_unverified(monkeypatch, mutation, failure):
    harness, report, frontier, _body = await simulated_canary(monkeypatch)
    storage = Reader(harness.store)
    first_batch = frontier.value["committed_batches"][0]
    if mutation == "missing_pair":
        del harness.store.objects[harness.prefix + first_batch["receipt_ref"]]
    elif mutation in {"wrong_revision", "wrong_attempt"}:
        for ref in (first_batch["receipt_ref"], first_batch["receipt_ref"].replace(".finished.", ".started.")):
            key = harness.prefix + ref
            stored = await harness.store.read(key)
            changed = stored.value
            if mutation == "wrong_revision":
                changed["runtime"]["revision"] = collector.WORKER_SERVICE + "-other"
            else:
                changed["attempt"] = 2
            await harness.store.write(key, changed, generation=stored.generation)
    elif mutation == "replaced_state":
        key = harness.prefix + first_batch["state"]
        stored = await harness.store.read(key)
        await harness.store.write(key, stored.value, generation=stored.generation)
    elif mutation == "untrusted_path":
        first_batch["state"] = "../../outside"
        await harness.store.write(harness.prefix + "frontier.json", frontier.value, generation=frontier.generation)
    elif mutation == "incomplete_history":
        frontier.value["telemetry_history_complete"] = False
        await harness.store.write(harness.prefix + "frontier.json", frontier.value, generation=frontier.generation)
    elif mutation == "deleted":
        await harness.store.write("deleted/scans/scan_test/", {"deleted_at": 1})
    elif mutation == "frontier_changed":
        observed = storage.read

        async def alternating(key):
            returned = await observed(key)
            if key.endswith("frontier.json") and storage.body_reads.count(key) == 2:
                return WorkspaceObject(returned.value, returned.generation + 1)
            return returned

        storage.read = alternating
    monkeypatch.setattr(collector, "RECEIPT_GRACE_SECONDS", 0)
    with pytest.raises(collector.EvidenceError, match=f"^{failure}$"):
        await collector.collect(collector.canary_identity(report), storage)
    assert "../../outside" not in "\n".join(storage.metadata_reads)


@pytest.mark.asyncio
async def test_sampled_memory_and_wrong_completion_are_reported_as_unverified(monkeypatch):
    harness, report, frontier, _body = await simulated_canary(monkeypatch)
    key = harness.prefix + frontier.value["finalize_receipt_ref"]
    stored = await harness.store.read(key)
    stored.value["memory"]["cgroup"] = None
    stored.value["completion_request"]["status_code"] = 503
    await harness.store.write(key, stored.value, generation=stored.generation)
    evidence = await collector.collect(collector.canary_identity(report), Reader(harness.store))
    assert evidence["worker_runtime_verified"] is True
    assert evidence["receipt_evidence_verified"] is False
    assert evidence["memory"]["all_stages_verified"] is False
    assert evidence["memory"]["sampled_aggregate_rss_peak_bytes"] == 350_000_000
    assert evidence["completion_request"] is None
    assert evidence["unverified"] == ["cgroup_lifetime_bound_unverified", "terminal_completion_request_unverified"]


def test_transport_pins_generation_and_reads_artifacts_only_as_metadata():
    calls = []

    class Blob:
        generation = "9876543210123456"
        size = 64

        def reload(self, **kwargs):
            calls.append(("reload", kwargs))

        def download_as_bytes(self, **kwargs):
            calls.append(("download", kwargs))
            return gzip.compress(b'{"evidence":"bounded"}')

    class Bucket:
        def blob(self, _key):
            return Blob()

    async def read():
        store = collector.ReceiptStorage(Bucket())
        control = await store.read("control")
        assert control == WorkspaceObject({"evidence": "bounded"}, 9876543210123456)
        assert await store.generation("state") == "9876543210123456"

    asyncio.run(read())
    assert [operation for operation, _ in calls] == ["reload", "download", "reload"]
    assert calls[1][1]["if_generation_match"] == 9876543210123456
    assert all(arguments["retry"] is None for _, arguments in calls)


@pytest.mark.asyncio
async def test_cli_saves_one_private_report_with_unverified_readback(monkeypatch, tmp_path):
    _harness, report, _frontier, _body = await simulated_canary(monkeypatch)
    source = tmp_path.resolve() / "canary.json"
    source.write_text(json.dumps(report))
    output = source.with_name("evidence.json")
    monkeypatch.setenv("STORAGE_EMULATOR_HOST", "http://127.0.0.1:9980")
    monkeypatch.setattr(sys, "argv", ["collect", "--canary-report", str(source), "--output", str(output)])
    assert await asyncio.to_thread(collector._main) == 1
    evidence = json.loads(output.read_text())
    assert evidence["schema_version"] == "staged_500_receipt_evidence_v1"
    assert evidence["canary_report_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert evidence["worker_runtime_verified"] is False
    assert evidence["receipt_evidence_verified"] is False
    assert evidence["unverified"] == ["workspace_emulator_refused"]
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert await asyncio.to_thread(collector._main) == 2
    assert json.loads(output.read_text()) == evidence
