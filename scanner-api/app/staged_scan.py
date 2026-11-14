"""Sequential, retryable scan stages over a generation-fenced workspace.

The frontier is the commit record and contains a replayable next-task intent.
Evidence and state snapshots written by a losing or interrupted delivery are
never loaded by subsequent stages. Production dependencies are injected at the
HTTP boundary, keeping the recovery protocol independently testable.
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from .scan_job import already_terminal, current_attempt, identity_matches, is_superseded_attempt
from .observability import website_host
from .workspace import WorkspaceConflict, WorkspaceUnavailable, attempt_prefix


STAGE_LEASE_SECONDS = 450.0
STAGE_WORK_SECONDS = 180.0
SCAN_WALL_SECONDS = 600.0
BATCH_SIZE = 50
STAGED_SCAN_PIPELINE_VERSION = "staged_scan_pipeline_v2_owner_shortlist_cached_rss_admission"


class StageRetry(RuntimeError):
    """Transient failure; acknowledge only after the durable protocol succeeds."""

    def __init__(self, message: str, *, retry_after: int = 10):
        super().__init__(message)
        self.retry_after = max(1, int(retry_after))


def staged_pipeline_enabled(job: dict[str, Any]) -> bool:
    if str(os.getenv("SCAN_PIPELINE_MODE") or "monolith").lower() != "staged":
        return False
    owners = {item.strip() for item in str(os.getenv("SCAN_STAGED_OWNER_IDS") or os.getenv("SCAN_PIPELINE_OWNER_IDS") or "").split(",") if item.strip()}
    # A wildcard is a configuration error, not permission to route every owner.
    if "*" in owners:
        return False
    owner_id = job.get("owner_user_id")
    return isinstance(owner_id, str) and bool(owner_id) and owner_id in owners


@dataclass
class StageDependencies:
    read_scan: Callable
    start: Callable
    progress: Callable
    complete: Callable
    transform: Callable
    fail: Callable
    state_type: Any
    plan: Callable
    crawl: Callable
    finalize: Callable
    review: Callable | None = None


class StagedScanRuntime:
    def __init__(self, workspace: Any, dispatcher: Any, dependencies: StageDependencies, *, clock: Callable = time.time):
        self.store, self.dispatcher, self.dep, self.clock = workspace, dispatcher, dependencies, clock

    @staticmethod
    def _prefix(job: dict[str, Any]) -> str:
        return attempt_prefix(job["scan_id"], int(job.get("attempt_count") or 1))

    @staticmethod
    def _tombstone(job: dict[str, Any]) -> str:
        # One deletion fences every historical attempt, including old tasks
        # delivered after the current attempt's evidence has been removed.
        return "deleted/" + StagedScanRuntime._scan_prefix(job)

    @staticmethod
    def _scan_prefix(job: dict[str, Any]) -> str:
        prefix = StagedScanRuntime._prefix(job)
        return "/".join(prefix.split("/")[:2]) + "/"

    async def _fence(self, client: Any, job: dict[str, Any]) -> tuple[dict | None, dict | None]:
        scan = await self.dep.read_scan(client, job["scan_id"])
        if not isinstance(scan, dict):
            raise StageRetry("The scan record is unavailable")
        if not identity_matches(scan, job):
            return None, {"success": True, "skipped": "identity_mismatch"}
        attempt = int(job.get("attempt_count") or 1)
        if is_superseded_attempt(scan, attempt) or current_attempt(scan) != attempt:
            return None, {"success": True, "skipped": "superseded_attempt"}
        if already_terminal(scan):
            return None, {"success": True, "skipped": "already_terminal", "status": scan.get("status")}
        if await self.store.read(self._tombstone(job)):
            return None, {"success": True, "skipped": "workspace_deleted"}
        return scan, None

    @staticmethod
    def _canonical_job(scan: dict, job: dict) -> dict:
        if scan.get("pipeline_mode") != "staged":
            raise ValueError("The durable scan has not selected the staged pipeline")
        mode = str(scan.get("scan_mode") or "standard_150").lower()
        # Historical rows use advanced; only the server-owned V9 row can grant 500.
        if mode == "advanced":
            mode = "standard_150"
        cap = scan.get("page_cap", 150)
        if isinstance(cap, bool) or mode not in {"standard_150", "standard_500"} or cap != {"standard_150": 150, "standard_500": 500}[mode]:
            raise ValueError("The server-owned scan entitlement is invalid")
        if str(job.get("scan_mode") or "standard_150") != mode:
            raise ValueError("The task mode does not match its durable scan")
        result = dict(job)
        for field in ("owner_user_id", "request_id", "idempotency_key", "project_id", "website_url", "path_prefix", "normalized_domain", "respect_robots_txt", "owner_attested_robots_override"):
            if field in scan and scan[field] is not None:
                result[field] = scan[field]
        result["normalized_domain"] = result.get("normalized_domain") or website_host(result["website_url"])
        result.update({"scan_mode": mode, "page_cap": cap})
        return result

    async def _lease(self, prefix: str, stage: str, batch: int) -> tuple[dict, int] | None:
        key = prefix + "frontier.json"
        stored = await self.store.read(key)
        current = dict(stored.value) if stored else {"stage": "plan", "batch": 0, "committed_batches": [], "wall_deadline": self.clock() + SCAN_WALL_SECONDS}
        if current.get("stage") == "deleted":
            raise StageRetry("The workspace was deleted")
        if current.get("stage") != stage or int(current.get("batch") or 0) != batch:
            return None
        if float(current.get("lease_until") or 0) > self.clock():
            raise StageRetry("A delivery already owns this stage", retry_after=int(current["lease_until"] - self.clock()) + 1)
        current.update({"lease_owner": uuid.uuid4().hex, "lease_until": self.clock() + STAGE_LEASE_SECONDS})
        generation = await self.store.write(key, current, generation=stored.generation if stored else 0)
        return current, generation

    async def _commit(self, prefix: str, frontier: dict, generation: int, **changes: Any) -> dict:
        if self.clock() >= float(frontier["lease_until"]):
            raise StageRetry("The stage lease expired")
        committed = {**frontier, **changes, "lease_owner": "", "lease_until": 0}
        await self.store.write(prefix + "frontier.json", committed, generation=generation)
        return committed

    async def _replay(self, client: Any, scan: dict, job: dict, frontier: dict) -> dict:
        if frontier.get("stage") == "done":
            return {"success": True, "scan_id": job["scan_id"], "already_completed": True}
        if frontier.get("stage") not in {"batch", "finalize"}:
            raise StageRetry("The requested stage is not ready")
        scan, stopped = await self._fence(client, job)
        if stopped:
            return stopped
        # A progress or dispatch failure after commit is repaired here by every
        # duplicate delivery. Neither can strand a successfully committed batch.
        committed_batch = int(frontier.get("batch") or 0) - 1
        await self.dep.progress(client, scan, int(frontier.get("pages_crawled") or 0), int(frontier.get("pages_planned") or 0), committed_batch if committed_batch >= 0 else None)
        _, stopped = await self._fence(client, job)
        if stopped:
            return stopped
        dispatch_options = {"limited": bool(frontier.get("limited"))}
        if frontier["stage"] == "batch" and float(frontier.get("dispatch_after") or 0) > self.clock():
            dispatch_options["not_before"] = float(frontier["dispatch_after"])
        await self.dispatcher.enqueue(job, frontier["stage"], int(frontier["batch"]), **dispatch_options)
        return {"success": True, "scan_id": job["scan_id"], "stage": frontier["stage"], "batch": frontier["batch"], "pages_crawled": int(frontier.get("pages_crawled") or 0)}

    async def process(self, client: Any, stage: str, job: dict, *, batch: int = 0, limited: bool = False) -> dict:
        scan, skipped = await self._fence(client, job)
        if skipped:
            return skipped
        job = self._canonical_job(scan, job)
        prefix = self._prefix(job)
        frontier = None
        try:
            leased = await self._lease(prefix, stage, batch)
            if leased is None:
                stored = await self.store.read(prefix + "frontier.json")
                if not stored:
                    raise StageRetry("The plan has not committed")
                return await self._replay(client, scan, job, stored.value)
            frontier, generation = leased
            if stage == "plan":
                await self.dep.start(client, scan)
                planned = await self.store.read(prefix + "plan.json")
                if planned:
                    plan = planned.value
                else:
                    remaining = float(frontier["wall_deadline"]) - self.clock()
                    if remaining < 20:
                        await self.dep.fail(client, job["scan_id"], "scanner_wall_timeout", "The scan exhausted its time budget before collecting page evidence. Please try again.", attempt_count=job.get("attempt_count"))
                        return {"success": False, "error_code": "scanner_wall_timeout"}
                    from .robots_policy import owner_robots_override
                    with owner_robots_override(bool(job.get("owner_attested_robots_override"))):
                        state = await asyncio.wait_for(self.dep.plan(
                            website_url=job["website_url"], path_prefix=job.get("path_prefix"),
                            scan_mode=job["scan_mode"], timeout_seconds=remaining,
                            job_mode=True, staged=True,
                        ), timeout=STAGE_WORK_SECONDS)
                    plan = {"job": job, "state": state.to_dict(), "wall_deadline": frontier["wall_deadline"]}
                    # Recheck cancellation immediately before evidence enters storage.
                    _, stopped = await self._fence(client, job)
                    if stopped:
                        return stopped
                    await self.store.write(prefix + "plan.json", plan)
                state = self.dep.state_type.from_dict(plan["state"])
                planned_count = min(int(job["page_cap"]), max(len(state.queue), len(state.pages)))
                frontier = await self._commit(prefix, frontier, generation, stage="finalize" if state.finished else "batch", batch=0, state_ref="plan.json", wall_deadline=plan["wall_deadline"], pages_crawled=len(state.pages), pages_planned=planned_count)
                return await self._replay(client, scan, job, frontier)

            snapshot = await self.store.read(prefix + str(frontier["state_ref"]))
            if not snapshot:
                raise StageRetry("The committed state snapshot is unavailable")
            state = self.dep.state_type.from_dict(snapshot.value["state"])
            deadline_hit = self.clock() >= float(frontier["wall_deadline"])
            if stage == "batch":
                if not deadline_hit:
                    from .robots_policy import owner_robots_override
                    with owner_robots_override(bool(job.get("owner_attested_robots_override"))):
                        await asyncio.wait_for(self.dep.crawl(state, max_pages=BATCH_SIZE), timeout=STAGE_WORK_SECONDS)
                _, stopped = await self._fence(client, job)
                if stopped:
                    return stopped
                execution = uuid.uuid4().hex
                ref = f"batches/{batch}-{execution}.state.json.gz"
                checkpoint = state.to_dict()
                await self.store.write(prefix + ref, {"state": checkpoint})
                # Full state includes cross-batch identity merges and evidence;
                # immutable manifests avoid a non-atomic shared append object.
                evidence_ref = f"batches/{batch}-{execution}.pages.json.gz"
                await self.store.write(prefix + evidence_ref, {"pages": state.pages})
                cutoff = deadline_hit or self.clock() >= float(frontier["wall_deadline"]) or bool(getattr(state, "limited", False))
                limit_reason = str(getattr(state, "completion_reason", "")) if cutoff else ""
                done = state.finished or cutoff
                frontier = await self._commit(prefix, frontier, generation,
                    stage="finalize" if done else "batch", batch=batch + 1,
                    state_ref=ref, pages_crawled=len(state.pages),
                    pages_planned=min(int(job["page_cap"]), max(int(frontier.get("pages_planned") or 0), len(state.pages))),
                    committed_batches=[*frontier.get("committed_batches", []), {"batch": batch, "state": ref, "pages": evidence_ref}],
                    limited=bool(frontier.get("limited")) or cutoff,
                    limit_reason=limit_reason or ("wall_budget" if cutoff else ""),
                    dispatch_after=float(checkpoint.get("rate_limit_pacer", {}).get("next_request_at") or 0),
                )
                return await self._replay(client, scan, job, frontier)

            if stage != "finalize":
                raise ValueError("Invalid staged operation")
            # An authorized watchdog may finalize committed partial evidence.
            limited = limited or bool(frontier.get("limited")) or bool(getattr(state, "limited", False)) or not state.finished
            result_snapshot = await self.store.read(prefix + "result.json.gz")
            if result_snapshot:
                result = result_snapshot.value
            else:
                from .robots_policy import owner_robots_override
                with owner_robots_override(bool(job.get("owner_attested_robots_override"))):
                    result = await asyncio.wait_for(self.dep.finalize(state), timeout=STAGE_WORK_SECONDS)
                result.update({
                    "scan_mode": job["scan_mode"], "canonical_mode": job["scan_mode"], "page_cap": job["page_cap"],
                    "advanced_scan_backend": "python_scanner_api", "deno_fallback_used": False,
                    "request_id": job["request_id"], "idempotency_key": job.get("idempotency_key") or job["request_id"],
                    "scan_id": job["scan_id"], "scan_run_id": job["scan_id"], "submitted_url": job["website_url"],
                    "normalized_domain": job.get("normalized_domain") or website_host(job["website_url"]),
                    "respect_robots_txt": job["respect_robots_txt"], "owner_attested_robots_override": job["owner_attested_robots_override"],
                    "pipeline_mode": "staged", "pipeline_limited": limited,
                    "pipeline_limit_reason": frontier.get("limit_reason") or ("wall_budget" if deadline_hit else "stalled" if limited else ""),
                })
                result = await asyncio.wait_for(asyncio.to_thread(self.dep.transform, result), timeout=60)
                from .beta_revision import live_revision
                result["beta_revision_fingerprint"] = live_revision()["fingerprint"]
                _, stopped = await self._fence(client, job)
                if stopped:
                    return stopped
                await self.store.write(prefix + "result.json.gz", result)
            fresh, stopped = await self._fence(client, job)
            if stopped:
                return stopped
            signing_key = str(os.getenv("SCAN_EVIDENCE_SIGNING_KEY") or "")
            if not signing_key:
                raise StageRetry("Authority signing is not configured")
            reviewed = None
            if self.dep.review is not None:
                review_snapshot = await self.store.read(prefix + "review.json.gz")
                if review_snapshot:
                    reviewed = review_snapshot.value
                else:
                    reviewed = await asyncio.wait_for(self.dep.review(result), timeout=25)
                    _, stopped = await self._fence(client, job)
                    if stopped:
                        return stopped
                    await self.store.write(prefix + "review.json.gz", reviewed)
                fresh, stopped = await self._fence(client, job)
                if stopped:
                    return stopped
            completion = self.dep.complete(client, fresh, result, signing_key, review=reviewed) if reviewed is not None else self.dep.complete(client, fresh, result, signing_key)
            outcome = await asyncio.wait_for(completion, timeout=90)
            if outcome.get("transient"):
                raise StageRetry("Authority persistence is unavailable")
            if outcome.get("superseded"):
                return {"success": True, "skipped": "superseded_attempt"}
            if not outcome.get("ok"):
                await self.dep.fail(client, job["scan_id"], str(outcome.get("failure_code") or "staged_completion_failed"), str(outcome.get("customer_message") or "The scan result could not be saved."), attempt_count=job.get("attempt_count"))
                return {"success": False, "error_code": outcome.get("failure_code")}
            await self._commit(prefix, frontier, generation, stage="done", batch=batch, pages_crawled=len(state.pages))
            return {"success": True, "scan_id": job["scan_id"], "pages_crawled": len(state.pages), "fix_list_id": outcome.get("fix_list_id")}
        except (WorkspaceConflict, WorkspaceUnavailable, asyncio.TimeoutError) as exc:
            raise StageRetry("The stage did not finish its durable commit") from exc
        finally:
            # Release stopped deliveries immediately; a process crash instead
            # recovers through the bounded lease and duplicate Retry-After.
            if frontier and frontier.get("lease_owner"):
                try:
                    stored = await self.store.read(prefix + "frontier.json")
                    if stored and stored.value.get("lease_owner") == frontier["lease_owner"]:
                        released = {**stored.value, "lease_owner": "", "lease_until": 0}
                        await self.store.write(prefix + "frontier.json", released, generation=stored.generation)
                except (WorkspaceConflict, WorkspaceUnavailable):
                    pass

    async def request_partial_finalize(self, client: Any, job: dict) -> dict:
        scan, skipped = await self._fence(client, job)
        if skipped:
            return skipped
        job = self._canonical_job(scan, job)
        prefix = self._prefix(job)
        stored = await self.store.read(prefix + "frontier.json")
        if not stored or not stored.value.get("committed_batches"):
            raise StageRetry("There is no committed batch to finalize")
        frontier = dict(stored.value)
        if float(frontier.get("lease_until") or 0) > self.clock():
            raise StageRetry("The live batch lease has not expired")
        if frontier.get("stage") != "done":
            frontier.update({"stage": "finalize", "limited": True, "lease_owner": "", "lease_until": 0})
            await self.store.write(prefix + "frontier.json", frontier, generation=stored.generation)
        return await self._replay(client, scan, job, frontier)

    async def delete_workspace(self, client: Any, job: dict) -> dict:
        scan = await self.dep.read_scan(client, job["scan_id"])
        if not isinstance(scan, dict):
            raise StageRetry("The scan record is unavailable")
        if not identity_matches(scan, job) or current_attempt(scan) != int(job.get("attempt_count") or 1):
            return {"success": True, "skipped": "identity_mismatch"}
        if not already_terminal(scan):
            raise StageRetry("The scan must be stopped before deleting evidence")
        prefix = self._scan_prefix(job)
        tombstone_key = self._tombstone(job)
        tombstone = await self.store.read(tombstone_key)
        if not tombstone:
            # Also cover a delivery that passed its first durable fence just
            # before this tombstone, but has not written its lease yet. Every
            # HTTP stage is bounded to420s, with single SDK RPCs bounded20s;
            # 450s therefore drains that race before final prefix deletion.
            until = self.clock() + STAGE_LEASE_SECONDS
            for key in await self.store.keys(prefix):
                if key.endswith("/frontier.json"):
                    stored = await self.store.read(key)
                    if stored:
                        until = max(until, float(stored.value.get("lease_until") or 0))
            try:
                await self.store.write(tombstone_key, {"lease_until": until, "deleted_at": self.clock()})
            except WorkspaceConflict:
                pass
            tombstone = await self.store.read(tombstone_key)
        # A delivery may still be fetching. Tombstone stops its next fence, and
        # waiting out its bounded lease also covers interrupted storage writes.
        if float(tombstone.value.get("lease_until") or 0) > self.clock():
            raise StageRetry("The stopped stage is draining before evidence deletion", retry_after=int(tombstone.value["lease_until"] - self.clock()) + 1)
        await self.store.delete_prefix(prefix)
        return {"success": True, "scan_id": job["scan_id"], "workspace_deleted": True}
