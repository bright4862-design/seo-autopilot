"""Exercise real staged deliveries against deterministic target-site HTTP 429s."""

from collections import Counter
from datetime import datetime, timezone
from functools import partial

import pytest
from fastapi import HTTPException
from google.api_core.exceptions import AlreadyExists

from app import main, scan_job, scanner
from app.stage_tasks import STAGE_ROUTES, StageTaskDispatcher, stage_task_id
from app.staged_scan import StageDependencies, StagedScanRuntime
from app.workspace import MemoryWorkspace, attempt_prefix
from tests import fixtures as fx


class FixtureRoutes(dict):
    throttle_url = None
    retry_after = None
    throttle_count = 0

    def get(self, url, default=None):
        if url == self.throttle_url and (self.retry_after == "3600" or self.throttle_count == 0):
            self.throttle_count += 1
            return {"status": 429, "headers": {"Retry-After": self.retry_after}, "body": "Too many requests"}
        return super().get(url, default)


class TaskTransport:
    def __init__(self, lost_ack_name):
        self.accepted = {}
        self.attempts = Counter()
        self.lost_ack_name = lost_ack_name

    def create_task(self, *, request, timeout, retry):
        task = request["task"]
        name = task["name"]
        self.attempts[name] += 1
        if name in self.accepted:
            raise AlreadyExists("fixture task already accepted")
        self.accepted[name] = task
        if name == self.lost_ack_name:
            raise RuntimeError("fixture task was accepted before its acknowledgement was lost")


@pytest.mark.asyncio
@pytest.mark.parametrize("retry_after", ["1", "3600"], ids=["recovers", "exhausts-crawl-budget"])
async def test_staged_429_after_committed_batch_retries_without_duplicate_evidence(mock_network, monkeypatch, retry_after):
    origin = "https://staged-throttle-rehearsal.example"
    urls = [f"{origin}/products/widget-{index}" for index in range(51)]
    routes = FixtureRoutes({
        origin + "/": fx._html(fx._page("Fixture home", links=[urls[0]])),
        origin + "/robots.txt": fx._text(f"User-agent: *\nAllow: /\nSitemap: {origin}/sitemap.xml\n"),
        origin + "/sitemap.xml": fx._xml(fx._sitemap(urls)),
        **{url: fx._html(fx._page(f"Widget {index}", h1=f"Widget {index}", canonical=url))
           for index, url in enumerate(urls)},
    })
    requests = mock_network(routes)
    signing_key = "offline-staged-throttle-test"
    monkeypatch.setenv("SCAN_EVIDENCE_SIGNING_KEY", signing_key)
    scan = {
        "id": "scan_throttle", "owner_user_id": "fixture_owner", "project_id": "fixture_project",
        "request_id": "fixture_request", "idempotency_key": "fixture_request", "attempt_count": 1,
        "scan_mode": "standard_150", "page_cap": 150, "pipeline_mode": "staged", "website_url": origin + "/",
        "respect_robots_txt": True, "owner_attested_robots_override": False, "status": "queued",
    }
    job = {**scan, "scan_id": scan["id"]}
    writes = []

    async def read(client, scan_id):
        assert scan_id == scan["id"]
        return dict(scan)

    async def start(client, current):
        scan.update(status="crawling", started_at=datetime.now(timezone.utc).isoformat(timespec="milliseconds"))
        return dict(scan)

    async def fail(*args, **kwargs):
        pytest.fail(f"A staged fixture with committed useful HTML must not fail: {args[2]}")

    async def persist(client, name, envelope, **kwargs):
        assert envelope["proof"] == scan_job.create_authority_seal(
            {key: value for key, value in envelope.items() if key != "proof"}, signing_key,
        )
        if name == "durableScanWorkerControlV9":
            assert envelope["action"] == "progress"
            return {"status_code": 200, "body": {"success": True, "scanRun": dict(scan)}}
        writes.append((name, envelope))
        if name == "persistLimitedScanResultV9":
            scan.update(status="limited", result_integrity_proof=envelope["proof"])
            return {"status_code": 200, "body": {
                "success": True, "resultIntegrityVerified": True, "fixListId": "fixture_fix_list", "scanRun": dict(scan),
            }}
        assert name == "persistDurableScanAuthorityV9"
        scan.update(status="complete", authority_proof=envelope["proof"], authority_seal_version="fixture", fix_list_id="fixture_fix_list")
        return {"status_code": 200, "body": {"success": True, "fixListVerified": True, "scanRun": dict(scan)}}

    monkeypatch.setattr(scan_job, "invoke_function", persist)
    monkeypatch.setattr(scan_job, "read_scan_run", read)
    queue = "projects/fixture-project/locations/europe-west1/queues/fixture-stages"

    def task_name(stage, batch):
        return f"{queue}/tasks/{stage_task_id(job, stage, batch)}"

    tasks = TaskTransport(task_name("batch", 1))
    store = MemoryWorkspace()
    runtime = StagedScanRuntime(store, StageTaskDispatcher(
        queue, "https://fixture-worker.example", "fixture-invoker@fixture.example", client=tasks,
    ), StageDependencies(
        read, start, scan_job.mark_scan_progress, scan_job.complete_authority, main.apply_post_crawl_transforms, fail,
        scanner.ScanState, partial(scanner.plan_scan, concurrency=1), scanner.crawl_batch,
        scanner.finalize_scan, main.review_staged_result,
    ))
    monkeypatch.setattr(main, "build_staged_runtime", lambda: runtime)
    prefix = attempt_prefix(scan["id"], scan["attempt_count"])
    frontier_key = prefix + "frontier.json"

    async def deliver(stage, batch):
        request = tasks.accepted[task_name(stage, batch)]["http_request"]
        assert request["url"] == "https://fixture-worker.example" + STAGE_ROUTES[stage]
        payload = main.ScanStageRequest.model_validate_json(request["body"])
        return await main.run_staged_delivery(
            stage, payload.model_dump(exclude={"batch", "limited", "recovery_generation"}),
            batch=payload.batch, limited=payload.limited, recovery_generation=payload.recovery_generation,
        )

    await main.run_staged_delivery("plan", job)
    plan = (await store.read(prefix + "plan.json")).value["state"]
    assert set(plan["queued"]) == {origin + "/", *urls}
    with pytest.raises(HTTPException) as error:
        await deliver("batch", 0)
    assert error.value.status_code == 503
    committed = await store.read(frontier_key)
    assert (committed.value["stage"], committed.value["batch"], committed.value["pages_crawled"]) == ("batch", 1, 50)
    healthy = (await store.read(prefix + committed.value["committed_batches"][0]["pages"])).value["pages"]
    assert len(healthy) == 50 and all(page["status_code"] == 200 for page in healthy)

    request_count = len(requests)
    assert (await deliver("batch", 0))["batch"] == 1
    assert tasks.attempts[task_name("batch", 1)] == 2
    assert len(requests) == request_count
    assert await store.read(frontier_key) == committed

    pending = (await store.read(prefix + committed.value["state_ref"])).value["state"]
    routes.throttle_url, routes.retry_after = pending["queue"][0][-1], retry_after
    await deliver("batch", 1)
    finalizing = (await store.read(frontier_key)).value
    assert routes.throttle_count == 1
    assert (finalizing["stage"], finalizing["batch"], finalizing["pages_planned"]) == ("finalize", 2, 52)
    evidence = (await store.read(prefix + finalizing["committed_batches"][-1]["pages"])).value["pages"]
    retained = {page["url"] for page in evidence}
    assert len(retained) == len(evidence)
    assert {page["url"] for page in healthy} <= retained <= set(plan["queued"])
    assert [row["batch"] for row in finalizing["committed_batches"]] == [0, 1]

    assert (await deliver("finalize", 2))["success"] is True
    assert len(writes) == 1
    writer, envelope = writes[0]
    assert envelope["identity"]["scan_id"] == scan["id"] and envelope["identity"]["attempt_count"] == "1"
    assert envelope["scan"]["page_cap"] == 150 and envelope["scan"]["pages_crawled"] == len(retained)
    assert envelope["scan"]["sampling_evidence"]["pages_checked"] == len(retained)
    if retry_after == "3600":
        assert finalizing["limited"] and finalizing["limit_reason"] == "rate_limit"
        assert Counter(page["status_code"] for page in evidence) == {200: 50, 429: 1}
        assert writer == "persistLimitedScanResultV9"
        review = envelope["review"]
        assert review["scan_status"] == "limited" and review["coverage_state"] == "limited_coverage"
        assert review["score_is_provisional"] is True and review["release_gate_eligible"] is False
        assert "staged_rate_limit" in review["coverage_reasons"] and review["recommendations"]
    else:
        assert not finalizing["limited"] and retained == set(plan["queued"])
        assert all(page["status_code"] == 200 for page in evidence)
        pacer = (await store.read(prefix + finalizing["state_ref"])).value["state"]["rate_limit_pacer"]
        assert pacer["retry_after_max_seconds"] == 1 and pacer["recovered_count"] == 1
        assert writer == "persistDurableScanAuthorityV9"

    done = await store.read(frontier_key)
    assert done.value["stage"] == "done"
    assert set(tasks.accepted) == {task_name("batch", 0), task_name("batch", 1), task_name("finalize", 2)}
    assert (await deliver("finalize", 2))["skipped"] == "already_terminal"
    assert len(writes) == 1 and await store.read(frontier_key) == done
