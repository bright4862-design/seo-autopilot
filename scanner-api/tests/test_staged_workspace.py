"""Recovery protocol checks independent of the HTTP crawler and cloud services."""
import asyncio
from dataclasses import dataclass, field
from re import fullmatch

import pytest

from app.staged_scan import (
    FINALIZE_PERSIST_DRAIN_SECONDS, STAGE_LEASE_SECONDS, StageDependencies, StageRetry, StagedScanRuntime,
)
from app.workspace import MemoryWorkspace, WorkspaceConflict, WorkspaceUnavailable, attempt_prefix


@dataclass
class State:
    queue: list = field(default_factory=lambda: list(range(120)))
    pages: list = field(default_factory=list)
    limited: bool = False
    completion_reason: str = ""

    @property
    def finished(self):
        return not self.queue or self.limited

    def to_dict(self):
        return {"queue": self.queue, "pages": self.pages, "limited": self.limited, "completion_reason": self.completion_reason}

    @classmethod
    def from_dict(cls, value):
        return cls(**value)


class FaultStore(MemoryWorkspace):
    fail_once = None

    async def write(self, key, value, *, generation=0):
        if self.fail_once and self.fail_once(key, value):
            self.fail_once = None
            raise WorkspaceUnavailable("injected storage outage")
        return await super().write(key, value, generation=generation)


class Dispatcher:
    def __init__(self):
        self.tasks = {}
        self.calls = []
        self.fail_before = False
        self.fail_after = False

    async def enqueue(self, job, stage, batch, **options):
        if self.fail_before:
            self.fail_before = False
            raise RuntimeError("dispatch outage before request")
        self.calls.append((stage, batch, options))
        self.tasks[(stage, batch)] = (job, options)
        if self.fail_after:
            self.fail_after = False
            raise RuntimeError("dispatch acknowledgement lost")


class Harness:
    def __init__(self, monkeypatch):
        monkeypatch.setenv("SCAN_EVIDENCE_SIGNING_KEY", "test-only-key")
        self.now = 1000.0
        self.scan = {"id": "scan_test", "request_id": "request_test", "idempotency_key": "request_test",
                     "owner_user_id": "owner_test", "project_id": "project_test", "attempt_count": 1,
                     "status": "queued", "scan_mode": "standard_150", "page_cap": 150,
                     "pipeline_mode": "staged", "website_url": "https://example.com/",
                     "respect_robots_txt": True, "owner_attested_robots_override": False}
        self.job = {**self.scan, "scan_id": self.scan["id"]}
        self.store = FaultStore()
        self.dispatcher = Dispatcher()
        self.crawls, self.results, self.progresses, self.failures = [], [], [], []
        self.progress_failure = False
        self.crawl_gate = None
        self.crawl_entered = asyncio.Event()
        self.plan_seconds = 0
        self.engine_limit_reason = ""
        self.deps = StageDependencies(self.read, self.start, self.progress, self.complete, lambda r: r,
                                      self.fail, State, self.plan, self.crawl, self.finalize)
        self.runtime = StagedScanRuntime(self.store, self.dispatcher, self.deps, clock=lambda: self.now)
        self.prefix = attempt_prefix(self.scan["id"], 1)

    async def read(self, client, scan_id):
        assert scan_id == self.scan["id"]
        return dict(self.scan)

    async def start(self, client, scan):
        self.scan["status"] = "crawling"
        return dict(self.scan)

    async def progress(self, client, scan, crawled, planned, batch=None):
        assert batch is None or (type(batch) is int and batch >= 0)
        assert 0 <= crawled <= planned <= (scan.get("page_cap") or 150)
        if self.progress_failure:
            self.progress_failure = False
            raise RuntimeError("progress unavailable")
        self.progresses.append((crawled, planned, batch))

    async def complete(self, client, scan, result, key):
        self.results.append(result)
        self.scan["status"] = "limited" if result["pipeline_limited"] else "complete"
        return {"ok": True, "fix_list_id": "list_test"}

    async def fail(self, *args, **kwargs):
        self.failures.append((args, kwargs))

    async def plan(self, **kwargs):
        self.now += self.plan_seconds
        return State()

    async def crawl(self, state, *, max_pages):
        self.crawls.append(len(state.pages))
        self.crawl_entered.set()
        if self.crawl_gate:
            await self.crawl_gate.wait()
        for _ in range(min(max_pages, len(state.queue))):
            state.pages.append({"url": f"https://example.com/{state.queue.pop(0)}"})
        if self.engine_limit_reason:
            state.limited = True
            state.completion_reason = self.engine_limit_reason

    async def finalize(self, state):
        return {"success": True, "pages": state.pages, "pages_crawled": len(state.pages)}

    async def run(self, stage, *, batch=0, limited=False):
        return await self.runtime.process(None, stage, self.job, batch=batch, limited=limited)

    async def frontier(self):
        return await self.store.read(self.prefix + "frontier.json")


@pytest.fixture
def h(monkeypatch):
    return Harness(monkeypatch)


@pytest.mark.asyncio
async def test_memory_store_enforces_create_only_and_generation_compare_and_set():
    store = MemoryWorkspace()
    first = await store.write("frontier", {"batch": 1})
    with pytest.raises(WorkspaceConflict):
        await store.write("frontier", {"batch": 2})
    second = await store.write("frontier", {"batch": 2}, generation=first)
    with pytest.raises(WorkspaceConflict):
        await store.write("frontier", {"batch": 3}, generation=first)
    assert (await store.read("frontier")).generation == second


@pytest.mark.asyncio
async def test_plan_uses_none_for_no_committed_batch_and_budget_starts_before_discovery(h):
    h.plan_seconds = 35
    await h.run("plan")
    assert h.progresses == [(0, 120, None)]
    assert (await h.frontier()).value["wall_deadline"] == 1600
    assert ("batch", 0) in h.dispatcher.tasks


@pytest.mark.parametrize("legacy_row", [{}, {"page_cap": None}, {"scan_mode": "advanced", "page_cap": None}])
@pytest.mark.asyncio
async def test_legacy_staged_row_accepts_its_implicit_standard_150_task(h, legacy_row):
    h.scan.pop("page_cap")
    h.scan.update(legacy_row)
    await h.run("plan")
    job, _ = h.dispatcher.tasks[("batch", 0)]
    assert (job["scan_mode"], job["page_cap"], job["pipeline_mode"]) == ("standard_150", 150, "staged")
    for batch in range(3):
        await h.runtime.process(None, "batch", job, batch=batch)
    assert (await h.runtime.process(None, "finalize", job, batch=3))["fix_list_id"] == "list_test"


@pytest.mark.asyncio
async def test_plan_retry_does_not_extend_scan_wall_deadline(h):
    h.plan_seconds = 35
    h.store.fail_once = lambda key, value: key.endswith("plan.json")
    with pytest.raises(StageRetry):
        await h.run("plan")
    assert (await h.frontier()).value["wall_deadline"] == 1600
    h.now += 50
    await h.run("plan")
    assert (await h.frontier()).value["wall_deadline"] == 1600


@pytest.mark.parametrize("failure", ["progress", "enqueue_before", "enqueue_after"])
@pytest.mark.asyncio
async def test_retry_after_batch_commit_replays_next_intent_without_fetching_again(h, failure):
    await h.run("plan")
    if failure == "progress":
        h.progress_failure = True
    elif failure == "enqueue_before":
        h.dispatcher.fail_before = True
    else:
        h.dispatcher.fail_after = True
    with pytest.raises(RuntimeError):
        await h.run("batch", batch=0)
    assert (await h.frontier()).value["batch"] == 1
    await h.run("batch", batch=0)
    assert len(h.crawls) == 1
    assert ("batch", 1) in h.dispatcher.tasks
    assert h.progresses[-1] == (50, 120, 0)


@pytest.mark.parametrize("failure_point", ["before_state", "before_commit"])
@pytest.mark.asyncio
async def test_uncommitted_artifacts_are_never_adopted_and_handled_error_releases_lease(h, failure_point):
    await h.run("plan")
    if failure_point == "before_state":
        h.store.fail_once = lambda key, value: "/batches/" in key and ".state." in key
    else:
        h.store.fail_once = lambda key, value: key.endswith("frontier.json") and value.get("batch") == 1
    with pytest.raises(StageRetry):
        await h.run("batch", batch=0)
    stored = await h.frontier()
    assert stored.value["batch"] == 0
    assert stored.value["state_ref"] == "plan.json"
    assert stored.value["lease_until"] == 0
    orphans = {key for key in h.store.objects if "/batches/" in key}
    await h.run("batch", batch=0)
    committed = (await h.frontier()).value
    assert len(committed["committed_batches"]) == 1
    assert h.prefix + committed["state_ref"] not in orphans
    assert committed["pages_crawled"] == 50


@pytest.mark.asyncio
async def test_concurrent_duplicate_does_not_fetch_and_expired_owner_cannot_commit(h):
    await h.run("plan")
    h.crawl_gate = asyncio.Event()
    running = asyncio.create_task(h.run("batch", batch=0))
    await h.crawl_entered.wait()
    old = await h.frontier()
    with pytest.raises(StageRetry) as blocked:
        await h.run("batch", batch=0)
    assert blocked.value.retry_after >= STAGE_LEASE_SECONDS
    assert len(h.crawls) == 1
    h.crawl_gate.set()
    await running
    with pytest.raises(WorkspaceConflict):
        await h.store.write(h.prefix + "frontier.json", old.value, generation=old.generation)


@pytest.mark.asyncio
async def test_crashed_delivery_lease_expires_and_is_resumed(h):
    await h.run("plan")
    stored = await h.frontier()
    crashed = {**stored.value, "lease_owner": "dead-process", "lease_until": h.now + STAGE_LEASE_SECONDS}
    await h.store.write(h.prefix + "frontier.json", crashed, generation=stored.generation)
    h.now += STAGE_LEASE_SECONDS + 1
    await h.run("batch", batch=0)
    frontier = (await h.frontier()).value
    assert frontier["pages_crawled"] == 50
    assert frontier["telemetry_history_complete"] is False


@pytest.mark.asyncio
async def test_telemetry_history_is_bounded_without_interrupting_scans(h, monkeypatch):
    monkeypatch.setattr("app.staged_scan.MAX_RECORDED_DELIVERIES", 1)
    await h.run("plan")
    await h.run("batch", batch=0)
    frontier = (await h.frontier()).value
    assert frontier["pages_crawled"] == 50
    assert len(frontier["telemetry_delivery_ids"]) == 1
    assert frontier["telemetry_history_complete"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "malformed",
    [None, 5, "not-a-list", {"entry": "a" * 32}, [], ["a" * 32, None], ["bad/id"], ["a" * 32] * 2],
)
async def test_malformed_telemetry_history_does_not_strand_a_scan(h, malformed):
    await h.run("plan")
    key = h.prefix + "frontier.json"
    stored = await h.frontier()
    await h.store.write(
        key, {**stored.value, "telemetry_delivery_ids": malformed}, generation=stored.generation,
    )

    assert (await h.run("batch", batch=0))["success"] is True
    frontier = (await h.frontier()).value
    assert frontier["pages_crawled"] == 50
    assert frontier["telemetry_history_complete"] is False
    [delivery_id] = frontier["telemetry_delivery_ids"]
    assert fullmatch(r"[a-f0-9]{32}", delivery_id)


@pytest.mark.asyncio
async def test_configured_ten_attempt_retry_schedule_outlives_crashed_lease_and_keeps_wall_budget(h):
    await h.run("plan")
    await h.run("batch", batch=0)
    stored = await h.frontier()
    await h.store.write(h.prefix + "frontier.json", {**stored.value, "lease_owner": "killed-worker", "lease_until": h.now + STAGE_LEASE_SECONDS}, generation=stored.generation)
    # Queue contract: min10s, max120s, maxDoublings4, maxAttempts10.
    # Model the earliest retry times without assuming Retry-After is honored.
    resumed = False
    for retry in range(9):
        h.now += min(10 * 2 ** min(retry, 4), 120)
        try:
            await h.run("batch", batch=1)
        except StageRetry:
            continue
        resumed = True
        break
    assert resumed and h.now == 1510
    assert (await h.frontier()).value["pages_crawled"] == 100
    assert (await h.frontier()).value["wall_deadline"] == 1600
    h.now += 91
    await h.run("batch", batch=2)
    frontier = (await h.frontier()).value
    await h.run("finalize", batch=frontier["batch"])
    assert h.results[-1]["pipeline_limited"] is True
    assert h.results[-1]["pages_crawled"] == 100


@pytest.mark.parametrize(("cause", "result_reason"), [
    ("wall_clock", "wall_budget"),
    ("engine_deadline", "wall_budget"),
    ("rate_limit", "rate_limit"),
    ("watchdog", "stalled"),
])
@pytest.mark.asyncio
async def test_partial_evidence_finalizes_as_limited(h, cause, result_reason):
    await h.run("plan")
    if cause in {"engine_deadline", "rate_limit"}:
        h.engine_limit_reason = result_reason
    await h.run("batch", batch=0)
    if cause == "wall_clock":
        h.now += 601
        await h.run("batch", batch=1)
    elif cause == "watchdog":
        await h.runtime.request_partial_finalize(None, h.job)
    frontier = (await h.frontier()).value
    assert frontier["stage"] == "finalize"
    await h.runtime.process(
        None, "finalize", h.job, batch=frontier["batch"],
        recovery_generation=int(cause == "watchdog"),
    )
    assert len(h.results) == 1
    assert h.results[0]["pipeline_limited"] is True
    assert h.results[0]["pipeline_limit_reason"] == result_reason
    assert h.results[0]["pages_crawled"] == 50
    assert h.scan["status"] == "limited"


@pytest.mark.asyncio
async def test_terminal_duplicate_finalize_is_inert(h):
    await h.run("plan")
    for batch in range(3):
        await h.run("batch", batch=batch)
    await h.run("finalize", batch=3)
    assert (await h.run("finalize", batch=3))["skipped"] == "already_terminal"
    assert len(h.results) == 1
    assert h.results[0]["normalized_domain"] == "example.com"


@pytest.mark.asyncio
async def test_committed_stage_receipts_are_bound_to_the_workspace_and_runtime(h, monkeypatch):
    from hashlib import sha256

    from app import staged_telemetry

    monkeypatch.setenv("FIXLIST_WORKER_SOURCE_SHA", "a" * 40)
    monkeypatch.setenv("FIXLIST_STAGED_CONFIG_SHA256", "b" * 64)
    monkeypatch.setenv("K_REVISION", "worker-00100-bbc")
    monkeypatch.setenv("K_SERVICE", "worker")
    monkeypatch.setenv("SCAN_PIPELINE_MODE", "staged")
    monkeypatch.setenv("SCAN_STAGED_OWNER_IDS", "owner_two,owner_one")
    monkeypatch.setattr(staged_telemetry, "measure_worker_peak_memory_bytes", lambda: 42_000_000)

    async def review(result):
        staged_telemetry.active_delivery.get().observe_review_memory(112_000_000)
        return {"success": True}

    async def complete(client, scan, result, key, *, review):
        return await h.complete(client, scan, result, key)

    h.deps.review, h.deps.complete = review, complete
    await h.run("plan")
    for batch in range(3):
        await h.run("batch", batch=batch)
    await h.run("finalize", batch=3)

    frontier = (await h.frontier()).value
    references = [frontier["plan_receipt_ref"], *(entry["receipt_ref"] for entry in frontier["committed_batches"]),
                  frontier["finalize_receipt_ref"]]
    assert len(set(references)) == 5
    receipts = [(await h.store.read(h.prefix + ref)).value for ref in references]
    assert frontier["telemetry_history_complete"] is True
    assert frontier["telemetry_delivery_ids"] == [receipt["delivery_id"] for receipt in receipts]
    lease_generations = [int(receipt["lease_generation"]) for receipt in receipts]
    assert lease_generations == sorted(set(lease_generations))
    assert [(r["stage"], r["batch"]) for r in receipts] == [
        ("plan", 0), ("batch", 0), ("batch", 1), ("batch", 2), ("finalize", 3),
    ]
    assert all(r["stage_committed"] and r["scan_id"] == h.scan["id"] and r["attempt"] == 1 for r in receipts)
    assert all(r["request_id_sha256"] == sha256(h.scan["request_id"].encode()).hexdigest() for r in receipts)
    assert all(r["runtime"] == {
        "source_sha": "a" * 40, "staged_config_sha256": "b" * 64,
        "revision": "worker-00100-bbc", "service": "worker",
        "release_fingerprint": staged_telemetry.live_revision()["fingerprint"],
        "pipeline_mode": "staged",
        "staged_owner_cohort_sha256": sha256(b'["owner_one","owner_two"]').hexdigest(),
    } for r in receipts)
    for receipt, ref in zip(receipts, references, strict=True):
        start = await h.store.read(h.prefix + ref.replace(".finished.", ".started."))
        assert start.value["delivery_id"] == receipt["delivery_id"]
        assert receipt["memory"]["parent_rss_peak_bytes"] == 42_000_000
        assert h.job["website_url"] not in str(receipt)
        assert "owner_one" not in str(receipt)
    assert receipts[-1]["memory"]["parent_and_review_child_rss_peak_bytes"] == 112_000_000
    assert receipts[-1]["artifacts"]["review"] == {
        "generation": str((await h.store.read(h.prefix + "review.json.gz")).generation), "produced": True,
    }
    assert await h.run("finalize", batch=3) == {
        "success": True, "skipped": "already_terminal", "status": "complete",
    }
    assert len(await h.store.keys(h.prefix + "receipts/")) == 10


@pytest.mark.asyncio
async def test_missing_finished_receipt_does_not_block_the_committed_plan(h):
    h.store.fail_once = lambda key, value: key.endswith(".finished.json.gz")
    assert (await h.run("plan"))["success"] is True
    frontier = (await h.frontier()).value
    ref = h.prefix + frontier["plan_receipt_ref"]
    assert await h.store.read(ref.replace(".finished.", ".started."))
    assert await h.store.read(ref) is None
    assert frontier["telemetry_history_complete"] is True
    assert frontier["telemetry_delivery_ids"][0] in ref
    assert ("batch", 0) in h.dispatcher.tasks


def test_missing_domain_is_derived_from_frozen_server_url(h):
    h.scan["website_url"] = "https://frozen.example.com/section"
    h.job["website_url"] = "https://task.example.com/other"
    canonical = h.runtime._canonical_job(h.scan, h.job)
    assert canonical["website_url"] == "https://frozen.example.com/section"
    assert canonical["normalized_domain"] == "frozen.example.com"


@pytest.mark.asyncio
async def test_authority_retry_reuses_persisted_result_and_review(h):
    await h.run("plan")
    for batch in range(3):
        await h.run("batch", batch=batch)
    reviewed, completed, stamps = [], [], []

    async def review(result):
        reviewed.append(result["pages_crawled"])
        return {"success": True, "recommendations": [{"id": "fix_1"}], "release_gate_eligible": True}

    async def complete(client, scan, result, key, *, review):
        completed.append(review)
        stamps.append(result["result_ready_at"])
        if len(completed) == 1:
            return {"ok": False, "transient": True}
        return await h.complete(client, scan, result, key)

    h.deps.review, h.deps.complete = review, complete
    h.now = 1017.0
    with pytest.raises(StageRetry):
        await h.run("finalize", batch=3)
    assert await h.store.read(h.prefix + "review.json.gz")
    assert await h.store.read(h.prefix + "result.json.gz")
    assert (await h.frontier()).value["lease_until"] == 0
    h.now += 20.0
    await h.run("finalize", batch=3)
    assert reviewed == [120]
    assert len(completed) == 2 and completed[0] == completed[1]
    assert stamps == ["1970-01-01T00:16:57.000Z"] * 2
    finished = [
        (await h.store.read(key)).value for key in await h.store.keys(h.prefix + "receipts/")
        if key.endswith(".finished.json.gz")
    ]
    retry = [r for r in finished if r["stage"] == "finalize" and r["stage_committed"]][0]
    producer = [r for r in finished if r["stage"] == "finalize" and not r["stage_committed"]][0]
    for artifact in ("result", "review"):
        assert producer["artifacts"][artifact]["produced"] is True
        assert retry["artifacts"][artifact] == {
            "generation": producer["artifacts"][artifact]["generation"], "produced": False,
        }


@pytest.mark.asyncio
async def test_watchdog_replaces_a_lost_finalize_without_downgrading_saved_evidence(h):
    await h.run("plan")
    for batch in range(3):
        await h.run("batch", batch=batch)
    attempts = []

    async def complete(client, scan, result, key):
        attempts.append(result)
        if len(attempts) == 1:
            return {"ok": False, "transient": True}
        return await h.complete(client, scan, result, key)

    h.deps.complete = complete
    with pytest.raises(StageRetry):
        await h.run("finalize", batch=3)
    progress_before = list(h.progresses)
    h.dispatcher.fail_after = True
    with pytest.raises(RuntimeError, match="dispatch acknowledgement lost"):
        await h.runtime.request_partial_finalize(None, h.job)
    cutoff = (await h.frontier()).value["finalize_recovery_until"]
    h.now += 30
    result = await h.runtime.request_partial_finalize(None, h.job)
    assert result["finalize_recovery_pending"] is True
    assert (await h.frontier()).value["finalize_recovery_until"] == cutoff
    assert h.dispatcher.calls[-2:] == [("finalize", 3, {"limited": False, "recovery_generation": 1})] * 2
    assert (await h.run("finalize", batch=3))["skipped"] == "superseded_finalize_delivery"
    assert h.progresses == progress_before

    recovered = await h.runtime.process(None, "finalize", h.job, batch=3, recovery_generation=1)
    assert recovered["fix_list_id"] == "list_test"
    assert attempts[1] == attempts[0]
    assert h.scan["status"] == "complete"
    assert not h.failures


@pytest.mark.asyncio
async def test_watchdog_fences_expired_recovery_and_closes_only_the_current_attempt(h):
    await h.run("plan")
    await h.run("batch", batch=0)
    await h.runtime.request_partial_finalize(None, h.job)
    cutoff = (await h.frontier()).value["finalize_recovery_until"]
    h.now = cutoff
    with pytest.raises(StageRetry):
        await h.runtime.process(None, "finalize", h.job, batch=1, recovery_generation=1)
    assert not h.results and not h.failures

    h.now += STAGE_LEASE_SECONDS
    with pytest.raises(StageRetry, match="still draining"):
        await h.runtime.request_partial_finalize(None, h.job)
    assert not h.failures

    h.now = cutoff + FINALIZE_PERSIST_DRAIN_SECONDS
    writes = []

    async def write_failure(client, scan_id, code, detail, *, attempt_count):
        writes.append((scan_id, code, attempt_count))
        if len(writes) == 1:
            raise RuntimeError("terminal write was unavailable")
        if len(writes) == 2:
            return True  # Provider acknowledged without a visible terminal state.
        h.scan.update(status="failed", error_code=code)
        return True

    h.deps.fail = write_failure
    with pytest.raises(RuntimeError, match="terminal write was unavailable"):
        await h.runtime.request_partial_finalize(None, h.job)
    with pytest.raises(StageRetry, match="was not persisted"):
        await h.runtime.request_partial_finalize(None, h.job)
    result = await h.runtime.request_partial_finalize(None, h.job)
    assert result == {"success": False, "error_code": "staged_finalize_timeout"}
    assert writes == [(h.scan["id"], "staged_finalize_timeout", 1)] * 3
    assert not h.results
    assert (await h.runtime.request_partial_finalize(None, h.job))["status"] == "failed"


@pytest.mark.asyncio
async def test_recovery_reports_an_existing_terminal_result_from_the_failure_readback(h):
    await h.run("plan")
    await h.run("batch", batch=0)
    await h.runtime.request_partial_finalize(None, h.job)
    h.now = (await h.frontier()).value["finalize_recovery_until"] + FINALIZE_PERSIST_DRAIN_SECONDS

    async def replay_terminal(*args, **kwargs):
        h.scan["status"] = "complete"
        return True

    h.deps.fail = replay_terminal
    assert await h.runtime.request_partial_finalize(None, h.job) == {
        "success": True, "skipped": "already_terminal", "status": "complete",
    }


@pytest.mark.parametrize("mode,cap", [("standard_150", 150), ("standard_500", 500)])
@pytest.mark.asyncio
async def test_blocked_crawl_can_finish_without_starting_review(h, monkeypatch, mode, cap):
    from app import scan_job

    h.scan.update(scan_mode=mode, page_cap=cap)
    h.job.update(scan_mode=mode, page_cap=cap)
    monkeypatch.setattr(scan_job, "read_scan_run", h.read)

    async def blocked_result(state):
        return {"pages_crawled": 1, "pages": [{
            "url": h.scan["website_url"],
            "status_code": 403,
            "page_evidence_class": "failed_access",
            "access_block_vendor": "cloudflare",
            "access_block_kind": "challenge",
        }]}

    async def review(result):
        pytest.fail("The reviewer should not run when the crawl found zero usable pages")

    h.deps.finalize = blocked_result
    h.deps.review = review
    h.deps.complete = scan_job.complete_authority
    await h.run("plan")
    for batch in range(3):
        await h.run("batch", batch=batch)

    outcome = await h.run("finalize", batch=3)

    assert outcome == {"success": False, "error_code": "scan_access_limited"}
    assert len(h.failures) == 1
    args, kwargs = h.failures[0]
    assert args[1:3] == (h.scan["id"], "scan_access_limited")
    assert "Cloudflare returned a bot challenge" in args[3]
    assert kwargs["attempt_count"] == h.scan["attempt_count"]
    assert await h.store.read(h.prefix + "review.json.gz") is None


@pytest.mark.parametrize("change,expected", [({"attempt_count": 2}, "superseded_attempt"), ({"status": "cancelled"}, "already_terminal"), ({"owner_user_id": "other-owner"}, "identity_mismatch")])
@pytest.mark.asyncio
async def test_fences_prevent_any_crawl_or_storage(h, change, expected):
    h.scan.update(change)
    assert (await h.run("plan"))["skipped"] == expected
    assert not h.crawls and not h.store.objects


@pytest.mark.asyncio
async def test_cancel_during_fetch_prevents_evidence_commit(h):
    await h.run("plan")
    h.crawl_gate = asyncio.Event()
    running = asyncio.create_task(h.run("batch", batch=0))
    await h.crawl_entered.wait()
    h.scan["status"] = "cancelled"
    h.crawl_gate.set()
    assert (await running)["skipped"] == "already_terminal"
    assert not any("/batches/" in key for key in h.store.objects)


@pytest.mark.asyncio
async def test_task_cannot_upgrade_server_cap_or_select_monolith_record(h):
    h.job["scan_mode"] = "standard_500"
    assert (await h.run("plan"))["skipped"] == "scan_contract_mismatch"
    h.scan.update(scan_mode="standard_500", page_cap=None)
    h.job["page_cap"] = 500
    assert (await h.run("plan"))["skipped"] == "scan_contract_mismatch"
    h.scan.update(scan_mode="standard_150", page_cap=150, pipeline_mode="monolith")
    h.job["scan_mode"] = "standard_150"
    h.job["page_cap"] = 150
    assert (await h.run("plan"))["skipped"] == "scan_contract_mismatch"
    assert not h.store.objects


@pytest.mark.asyncio
async def test_deletion_waits_out_active_lease_and_tombstone_blocks_recreation(h):
    await h.run("plan")
    stored = await h.frontier()
    await h.store.write(h.prefix + "frontier.json", {**stored.value, "lease_until": h.now + STAGE_LEASE_SECONDS}, generation=stored.generation)
    h.scan["status"] = "cancelled"
    with pytest.raises(StageRetry):
        await h.runtime.delete_workspace(None, h.job)
    assert await h.store.read(h.runtime._tombstone(h.job))
    h.now += STAGE_LEASE_SECONDS + 1
    assert (await h.runtime.delete_workspace(None, h.job))["workspace_deleted"]
    assert not any(key.startswith(h.prefix) for key in h.store.objects)
    # Even a temporarily stale nonterminal control read cannot recreate data.
    h.scan["status"] = "crawling"
    assert (await h.run("batch"))["skipped"] == "workspace_deleted"


@pytest.mark.asyncio
async def test_deletion_removes_historical_attempts_and_waits_for_their_leases(h):
    old_prefix = attempt_prefix(h.scan["id"], 1)
    await h.store.write(old_prefix + "frontier.json", {"lease_until": h.now + 100})
    await h.store.write(old_prefix + "orphan.pages.json.gz", {"pages": [{"private": True}]})
    h.scan["attempt_count"] = h.job["attempt_count"] = 2
    await h.run("plan")
    h.scan["status"] = "cancelled"
    with pytest.raises(StageRetry):
        await h.runtime.delete_workspace(None, h.job)
    h.now += STAGE_LEASE_SECONDS + 1
    await h.runtime.delete_workspace(None, h.job)
    assert not any(key.startswith("scans/scan_test/") for key in h.store.objects)


@pytest.mark.asyncio
async def test_plan_uses_real_signed_progress_contract(h, monkeypatch):
    from app import scan_job
    envelopes = []

    async def invoke(client, function, envelope, **kwargs):
        assert function == "durableScanWorkerControlV9"
        envelopes.append(envelope)
        return {"status_code": 200, "body": {"success": True, "scanRun": dict(h.scan)}}

    monkeypatch.setattr(scan_job, "invoke_function", invoke)
    h.deps.progress = scan_job.mark_scan_progress
    await h.run("plan")
    await h.run("batch", batch=0)
    assert "batch_committed" not in envelopes[0]["progress"]
    assert envelopes[1]["progress"]["batch_committed"] == 0


@pytest.mark.parametrize("staged_worker", [False, True])
@pytest.mark.asyncio
async def test_v9_monolith_keeps_generation_through_completion(h, monkeypatch, staged_worker):
    from app import main, scan_job
    h.scan["pipeline_mode"] = "monolith"
    h.job["pipeline_mode"] = "monolith"
    monkeypatch.delenv("SCAN_WORKSPACE_BUCKET", raising=False)
    monkeypatch.setenv("SCAN_PIPELINE_MODE", "monolith")
    if staged_worker:
        monkeypatch.setenv("SCAN_WORKSPACE_BUCKET", "private-test-bucket")
        monkeypatch.setenv("SCAN_PIPELINE_MODE", "staged")
        monkeypatch.setenv("SCAN_STAGED_OWNER_IDS", h.scan["owner_user_id"])
    monkeypatch.setattr(main, "require_cloud_tasks_oidc", lambda _: None)
    monkeypatch.setattr(main, "read_scan_run", h.read)
    observed = []

    async def cannot_switch_pipeline(*args, **kwargs):
        pytest.fail("A stored monolith attempt must not switch pipelines")

    async def started(client, scan):
        observed.append(scan_job.worker_function_name("durableScanWorkerControlV8"))
        return scan

    async def crawl(**kwargs):
        return {"success": True, "pages": [], "pages_crawled": 0}

    async def complete(client, scan, result, key):
        observed.append(scan_job.worker_function_name("persistDurableScanAuthorityV8"))
        return {"ok": True}

    monkeypatch.setattr(main, "mark_scan_started", started)
    monkeypatch.setattr(main, "run_staged_delivery", cannot_switch_pipeline)
    monkeypatch.setattr(main, "run_scan", crawl)
    monkeypatch.setattr(main, "apply_post_crawl_transforms", lambda r: r)
    monkeypatch.setattr(main, "complete_authority", complete)
    result = await main.scan_job(main.ScanJobRequest(**h.job), authorization=None)
    assert result["success"] is True
    assert observed == ["durableScanWorkerControlV9", "durableScanWorkerControlV9", "persistDurableScanAuthorityV9"]
    assert scan_job.worker_function_name("durableScanWorkerControlV8") == "durableScanWorkerControlV8"


@pytest.mark.asyncio
async def test_v9_monolith_watchdog_failure_uses_the_v9_control_function(h, monkeypatch):
    from app import main, scan_job

    h.scan["pipeline_mode"] = "monolith"

    async def fail(client, scan_id, code, detail, *, attempt_count):
        assert scan_job.worker_function_name("durableScanWorkerControlV8") == "durableScanWorkerControlV9"
        assert (scan_id, attempt_count) == (h.scan["id"], 1)
        return True

    monkeypatch.setattr(main, "write_terminal_failure", fail)
    assert await main.write_drain_failure(None, h.scan, h.scan["id"], "timeout", "detail", attempt_count=1)


@pytest.mark.asyncio
async def test_staged_scan_cannot_run_on_a_worker_without_staged_storage(h, monkeypatch):
    from fastapi import HTTPException
    from app import main

    monkeypatch.delenv("SCAN_WORKSPACE_BUCKET", raising=False)
    monkeypatch.setenv("SCAN_PIPELINE_MODE", "monolith")
    monkeypatch.setattr(main, "require_cloud_tasks_oidc", lambda _: None)
    monkeypatch.setattr(main, "read_scan_run", h.read)

    async def cannot_start(*args, **kwargs):
        pytest.fail("A staged attempt cannot start a monolith worker")

    monkeypatch.setattr(main, "mark_scan_started", cannot_start)

    with pytest.raises(HTTPException) as retry:
        await main.scan_job(main.ScanJobRequest(**h.job), authorization=None)
    assert retry.value.status_code == 503


@pytest.mark.asyncio
async def test_reconciler_and_drain_finalize_committed_partial_instead_of_failure(h, monkeypatch):
    from fastapi import HTTPException
    from app import main, scan_job
    await h.run("plan")
    await h.run("batch", batch=0)
    h.scan.update({"started_at": "2026-01-01T00:00:00Z", "worker_heartbeat_at": "2026-01-01T00:00:00Z"})
    monkeypatch.setenv("SCAN_WORKSPACE_BUCKET", "private-test-bucket")
    monkeypatch.setattr(main, "require_cloud_tasks_oidc", lambda _: None)
    monkeypatch.setattr(main, "build_staged_runtime", lambda: h.runtime)
    monkeypatch.setattr(main, "read_scan_run", h.read)

    async def reconcile(client):
        assert scan_job.worker_function_name("durableScanWorkerControlV8") == "durableScanWorkerControlV9"
        return {"examined": 1, "finalize_candidates": [{"scan_id": h.scan["id"], "attempt_count": 1}]}

    async def unexpected_failure(*args, **kwargs):
        pytest.fail("Committed staged evidence must be finalized")

    monkeypatch.setattr(main, "reconcile_stale_scans", reconcile)
    monkeypatch.setattr(main, "write_terminal_failure", unexpected_failure)
    response = await main.scan_reconcile(authorization=None)
    assert response["reconciliation"]["finalize_recovery_pending"] == 1
    drain_payload = main.ScanDrainRequest(**h.job, drain_after="2026-01-01T00:00:00Z")
    with pytest.raises(HTTPException) as retry:
        await main.scan_job_drain(drain_payload, authorization=None)
    assert retry.value.status_code == 503
    assert ("finalize", 1) in h.dispatcher.tasks


@pytest.mark.asyncio
async def test_existing_staged_intake_continues_after_cohort_is_disabled(h, monkeypatch):
    from app import main
    monkeypatch.setenv("SCAN_PIPELINE_MODE", "monolith")
    monkeypatch.setenv("SCAN_WORKSPACE_BUCKET", "private-test-bucket")
    monkeypatch.setattr(main, "require_cloud_tasks_oidc", lambda _: None)
    monkeypatch.setattr(main, "read_scan_run", h.read)
    calls = []

    async def staged(stage, job, **kwargs):
        calls.append(stage)
        return {"success": True}

    monkeypatch.setattr(main, "run_staged_delivery", staged)
    assert (await main.scan_job(main.ScanJobRequest(**h.job), authorization=None))["success"]
    assert calls == ["plan"]


@pytest.mark.parametrize("stored_scope,task_scope,allowed", [
    ("paid", "paid", True),
    ("paid", None, False),
    (None, "paid", False),
    (None, None, True),
])
@pytest.mark.asyncio
async def test_scan_entry_requires_the_durable_rollout_scope(h, monkeypatch, stored_scope, task_scope, allowed):
    from app import main
    h.scan["staged_rollout_scope"] = stored_scope
    h.job["staged_rollout_scope"] = task_scope
    monkeypatch.setenv("SCAN_WORKSPACE_BUCKET", "private-test-bucket")
    monkeypatch.setattr(main, "require_cloud_tasks_oidc", lambda _: None)
    monkeypatch.setattr(main, "read_scan_run", h.read)

    async def staged(stage, job, **kwargs):
        return await h.runtime.process(None, stage, job)

    monkeypatch.setattr(main, "run_staged_delivery", staged)
    response = await main.scan_job(main.ScanJobRequest(**h.job), authorization=None)
    assert (("batch", 0) in h.dispatcher.tasks) == allowed
    if not allowed:
        assert response["skipped"] == "scan_contract_mismatch"


@pytest.mark.parametrize("contract", [
    {"page_cap": None, "pipeline_mode": "staged"},
    {"page_cap": 150, "pipeline_mode": "monolith"},
    {"page_cap": 500, "scan_mode": "standard_500"},
])
@pytest.mark.asyncio
async def test_task_contract_cannot_change_saved_entry_drain_or_cleanup(h, monkeypatch, contract):
    from app import main

    monkeypatch.setattr(main, "require_cloud_tasks_oidc", lambda _: None)
    monkeypatch.setattr(main, "read_scan_run", h.read)
    job = {**h.job, **contract}
    assert (await main.scan_job(main.ScanJobRequest(**job), authorization=None))["skipped"] == "scan_contract_mismatch"
    drain = main.ScanDrainRequest(**job, drain_after="2026-01-01T00:00:00Z")
    assert (await main.scan_job_drain(drain, authorization=None))["skipped"] == "scan_contract_mismatch"
    assert (await h.runtime.process(None, "plan", job))["skipped"] == "scan_contract_mismatch"
    h.scan["status"] = "failed"
    assert (await h.runtime.delete_workspace(None, job))["skipped"] == "scan_contract_mismatch"
    assert not h.crawls and not h.failures and not h.store.objects


@pytest.mark.parametrize("route", ["/scan-batch", "/scan-finalize", "/scan-workspace-delete"])
def test_new_stage_routes_require_oidc_even_with_valid_scanner_key(h, monkeypatch, route):
    from app import main
    from fastapi.testclient import TestClient
    monkeypatch.setattr(main, "SCANNER_API_KEY", "valid-scanner-key")
    monkeypatch.setenv("TASKS_INVOKER_SERVICE_ACCOUNT", "invoker@example.invalid")
    with TestClient(main.app) as client:
        response = client.post(route, json=h.job, headers={"X-Scanner-Key": "valid-scanner-key"})
    assert response.status_code == 401
