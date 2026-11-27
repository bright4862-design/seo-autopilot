"""Sequential, retryable scan stages over a generation-fenced workspace.

The frontier is the commit record and contains a replayable next-task intent.
Evidence and state snapshots written by a losing or interrupted delivery are
never loaded by subsequent stages. Production dependencies are injected at the
HTTP boundary, keeping the recovery protocol independently testable.
"""

from __future__ import annotations

import asyncio
import os
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from .scan_job import (
    already_terminal,
    current_attempt,
    identity_matches,
    is_superseded_attempt,
    terminal_crawl_limitation,
)
from .observability import website_host
from .scan_limits import standard_scan_contract, task_matches_scan_contract
from . import staged_completion
from .staged_telemetry import MAX_RECORDED_DELIVERIES, DeliveryReceipt, active_delivery
from .target_contact import TargetContactRetry, TargetContacts, target_contact_scope
from .target_cooldown import TargetCooldownPending, TargetCooldownRelay, explicit_http_origin, target_cooldown_scope
from .workspace import WorkspaceConflict, WorkspaceUnavailable, attempt_prefix


STAGE_LEASE_SECONDS = 450.0
STAGE_WORK_SECONDS = 180.0
STAGE_DELIVERY_SECONDS = 420.0
FINALIZE_RECOVERY_SECONDS = 1800.0
# A delivery admitted before the cutoff can spend its full lease issuing
# requests. Base44 then allows each HTTP function up to five minutes.
FINALIZE_PERSIST_DRAIN_SECONDS = STAGE_LEASE_SECONDS + 300.0
SCAN_WALL_SECONDS = 600.0
BATCH_SIZE = 50
STAGED_SCAN_PIPELINE_VERSION = "staged_scan_pipeline_v2_owner_shortlist_cached_rss_admission"
_DELIVERY_ID_RE = re.compile(r"[a-f0-9]{32}")


class StageRetry(RuntimeError):
    """Transient failure; acknowledge only after the durable protocol succeeds."""

    def __init__(self, message: str, *, retry_after: int = 10):
        super().__init__(message)
        self.retry_after = max(1, int(retry_after))


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
    publish_target_cooldown: Callable | None = None
    request_target_contact: Callable | None = None


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

    async def _fence(self, client: Any, job: dict[str, Any], *, allow_saved_result: bool = False) -> tuple[dict | None, dict | None]:
        scan = await self.dep.read_scan(client, job["scan_id"])
        if not isinstance(scan, dict):
            raise StageRetry("The scan record is unavailable")
        if not identity_matches(scan, job):
            return None, {"success": True, "skipped": "identity_mismatch"}
        if not task_matches_scan_contract(scan, job):
            return None, {"success": True, "skipped": "scan_contract_mismatch"}
        attempt = int(job.get("attempt_count") or 1)
        if is_superseded_attempt(scan, attempt) or current_attempt(scan) != attempt:
            return None, {"success": True, "skipped": "superseded_attempt"}
        if already_terminal(scan) and not (allow_saved_result and scan.get("status") in staged_completion.WRITERS):
            return None, {"success": True, "skipped": "already_terminal", "status": scan.get("status")}
        if await self.store.read(self._tombstone(job)):
            return None, {"success": True, "skipped": "workspace_deleted"}
        return scan, None

    @staticmethod
    def _canonical_job(scan: dict, job: dict) -> dict:
        if scan.get("pipeline_mode") != "staged":
            raise ValueError("The durable scan has not selected the staged pipeline")
        contract = standard_scan_contract(scan)
        if contract is None:
            raise ValueError("The server-owned scan entitlement is invalid")
        mode, cap, pipeline = contract
        if str(job.get("scan_mode") or "standard_150") != mode:
            raise ValueError("The task mode does not match its durable scan")
        result = dict(job)
        for field in ("owner_user_id", "request_id", "idempotency_key", "project_id", "website_url", "path_prefix", "normalized_domain", "respect_robots_txt", "owner_attested_robots_override"):
            if field in scan and scan[field] is not None:
                result[field] = scan[field]
        result["normalized_domain"] = result.get("normalized_domain") or website_host(result["website_url"])
        result.update({"scan_mode": mode, "page_cap": cap, "pipeline_mode": pipeline})
        return result

    def _target_cooldown(self, client: Any, scan: dict, job: dict, prefix: str, stage: str) -> TargetCooldownRelay | None:
        origin = scan.get("admission_target_origin")
        publish = self.dep.publish_target_cooldown
        if publish is None or not origin or explicit_http_origin(job["website_url"]) != origin:
            return None
        return TargetCooldownRelay(
            self.store, prefix, origin, lambda observation: publish(client, scan, observation), self.clock,
            optional=stage == "finalize",
        )

    async def _run_site_stage(
        self, operation, client, scan, job, frontier, cooldown,
        *, allow_contact=True, contact_deadline=None, **arguments,
    ):
        from .robots_policy import owner_robots_override

        contacts = None
        request = self.dep.request_target_contact
        if request is not None:
            cutoff = self.clock() + STAGE_WORK_SECONDS
            if contact_deadline is not None:
                cutoff = min(float(contact_deadline), cutoff)
            contacts = TargetContacts(
                delivery_id=frontier["lease_owner"], cutoff=int(cutoff), clock=self.clock,
                send=(lambda action, fields: request(client, scan, action, fields)) if allow_contact else None,
            )
        async with target_contact_scope(contacts):
            with owner_robots_override(bool(job.get("owner_attested_robots_override"))), target_cooldown_scope(cooldown):
                result = await asyncio.wait_for(operation(**arguments), timeout=STAGE_WORK_SECONDS)
        if contacts is not None and contacts.failure is not None:
            # Discovery and optional probes can classify network exceptions.
            # A denied grant must retry without committing false page evidence.
            raise contacts.failure
        return result

    @staticmethod
    def _require_contact_ready(cooldown: TargetCooldownRelay | None) -> None:
        if cooldown is not None and (waiting := cooldown.remaining_hold()):
            raise StageRetry("A replayed target cooldown is still active", retry_after=waiting)

    @staticmethod
    def _finalize_deadline(frontier: dict) -> float:
        return float(frontier.get("finalize_cooldown_fallback_until") or frontier["finalize_recovery_until"])

    @staticmethod
    def _verified_cooldown_result(frontier: dict, snapshot: Any, job: dict) -> bool:
        # Only the exact result checkpointed by the lease that observed the
        # auxiliary failure can receive the final bounded persistence window.
        if (
            snapshot is None or type(frontier.get("target_cooldown_result_generation")) is not int
            or frontier["target_cooldown_result_generation"] != snapshot.generation
        ):
            return False
        result = snapshot.value
        return (
            isinstance(result, dict) and result.get("success") is True
            and result.get("scan_id") == job["scan_id"]
            and result.get("request_id") == job["request_id"]
            and result.get("pipeline_mode") == "staged"
            and result.get("scan_mode") == job["scan_mode"]
            and result.get("page_cap") == job["page_cap"]
            and type(result.get("pipeline_limited")) is bool
            and isinstance(result.get("pages"), list)
            and result.get("pages_crawled") == len(result["pages"])
            and 0 < len(result["pages"]) <= job["page_cap"]
        )

    async def _lease(self, prefix: str, stage: str, batch: int, recovery_generation: int = 0) -> tuple[dict, int, bool] | None:
        key = prefix + "frontier.json"
        stored = await self.store.read(key)
        current = dict(stored.value) if stored else {
            "stage": "plan", "batch": 0, "committed_batches": [],
            "wall_deadline": self.clock() + SCAN_WALL_SECONDS,
            "finalize_optional_probes_claimed": False,
        }
        if current.get("stage") == "deleted":
            raise StageRetry("The workspace was deleted")
        if current.get("stage") != stage or int(current.get("batch") or 0) != batch:
            return None
        if stage == "finalize" and recovery_generation != int("finalize_recovery_until" in current):
            return None
        if float(current.get("lease_until") or 0) > self.clock():
            raise StageRetry("A delivery already owns this stage", retry_after=int(current["lease_until"] - self.clock()) + 1)
        delivery_id = uuid.uuid4().hex
        deliveries = current.get("telemetry_delivery_ids")
        complete_history = stored is None
        if (
            isinstance(deliveries, list)
            and 0 < len(deliveries) <= MAX_RECORDED_DELIVERIES
            and all(isinstance(item, str) and _DELIVERY_ID_RE.fullmatch(item) for item in deliveries)
            and len(set(deliveries)) == len(deliveries)
        ):
            complete_history = current.get("telemetry_history_complete") is True
        else:
            # This metadata is optional. A malformed history cannot own or
            # prevent a lease; record new deliveries and preserve the gap.
            deliveries = []
        previous_owner = current.get("lease_owner")
        if previous_owner and (not deliveries or deliveries[-1] != previous_owner):
            complete_history = False
        if len(deliveries) < MAX_RECORDED_DELIVERIES:
            current["telemetry_delivery_ids"] = [*deliveries, delivery_id]
        else:
            complete_history = False
        current.update({
            "lease_owner": delivery_id, "lease_until": self.clock() + STAGE_LEASE_SECONDS,
            "telemetry_history_complete": complete_history,
        })
        allow_optional_probes = False
        if stage == "finalize":
            # Spend the attempt's permit before any optional I/O. A lost
            # receipt, missing result or replacement task must not renew it.
            # Legacy frontiers and watchdog recovery use retained evidence.
            allow_optional_probes = not recovery_generation and current.get("finalize_optional_probes_claimed") is False
            current["finalize_optional_probes_claimed"] = True
        generation = await self.store.write(key, current, generation=stored.generation if stored else 0)
        return current, generation, allow_optional_probes

    async def _commit(self, prefix: str, frontier: dict, generation: int, **changes: Any) -> dict:
        if self.clock() >= float(frontier["lease_until"]):
            raise StageRetry("The stage lease expired")
        committed = {**frontier, **changes, "lease_owner": "", "lease_until": 0}
        await self.store.write(prefix + "frontier.json", committed, generation=generation)
        return committed

    async def _replay(self, client: Any, scan: dict, job: dict, frontier: dict) -> dict:
        if frontier.get("stage") == "done":
            return {"success": True, "scan_id": job["scan_id"], "already_completed": True}
        if "finalize_recovery_until" in frontier:
            # The watchdog owns dispatch now. A delayed batch must not
            # refresh the heartbeat or issue the previous finalize task.
            return {"success": True, "skipped": "finalize_recovery_pending"}
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

    async def _recover_acknowledgement(self, client, scan, job, prefix, frontier, generation, receipt):
        from .scan_job import invoke_function

        status = scan["status"]
        writer = staged_completion.WRITERS[status]
        signing_key = os.getenv("SCAN_EVIDENCE_SIGNING_KEY")
        if not signing_key:
            raise StageRetry("Authority signing is not configured")
        saved = await self.store.read(prefix + staged_completion.ARCHIVE_NAME)
        stamp = await self.store.read(prefix + "completion.json")
        if not saved or not stamp or not isinstance(stamp.value.get("result_ready_at"), str):
            raise StageRetry("The original staged completion is unavailable")
        generations = {}
        for label, ref in (("input_state", frontier["state_ref"]), ("result", "result.json.gz"), ("review", "review.json.gz")):
            artifact = await self.store.read(prefix + ref)
            if not artifact:
                raise StageRetry("The committed staged evidence is unavailable")
            generations[label] = str(artifact.generation)
            receipt.observe_artifact(label, artifact.generation, produced=False)
        binding = staged_completion.binding_for(job, scan, frontier, frontier["batch"], generations, stamp.value["result_ready_at"], writer)
        packet = staged_completion.verified_packet(saved.value, binding, signing_key)
        if (not packet or packet["proof"] != scan.get("staged_writer_request_proof")
                or packet["scan"].get("result_ready_at") != stamp.value["result_ready_at"]):
            raise StageRetry("The original staged writer request could not be verified")

        def same_saved_result(row):
            return (isinstance(row, dict) and staged_completion.exact_job(row, job) and row.get("status") == status
                    and row.get("staged_writer_request_proof") == packet["proof"]
                    and staged_completion.terminal_seal(row) == staged_completion.terminal_seal(scan)
                    and row.get("fix_list_id") == scan.get("fix_list_id")
                    and binding == staged_completion.binding_for(job, row, frontier, frontier["batch"],
                                                                 generations, stamp.value["result_ready_at"], writer))

        fresh, stopped = await self._fence(client, job, allow_saved_result=True)
        if stopped:
            return stopped
        if not same_saved_result(fresh):
            raise StageRetry("The saved staged completion changed")
        if self.clock() >= float(frontier["lease_until"]):
            raise StageRetry("The stage lease expired")
        # invoke_function creates a fresh runtime challenge and verifies its signed
        # response. The inner worker request is exactly the one the terminal row accepted.
        response = await asyncio.wait_for(invoke_function(client, writer, packet), timeout=90)
        body = response.get("body") or {}
        row = body.get("scanRun")
        verified_field = "fixListVerified" if status == "complete" else "resultIntegrityVerified"
        if status == "complete" and (not isinstance(row, dict)
                or row.get("beta_revision_fingerprint") != binding["release"]
                or not isinstance(row.get("customer_preview_proof"), str)
                or not staged_completion.HEX_PROOF.fullmatch(row["customer_preview_proof"])):
            raise StageRetry("The staged writer has not verified the saved preview")
        observed_request = receipt.completion_request or {}
        if not (observed_request.get("function") == writer and observed_request.get("status_code") == 200
                and response.get("status_code") == 200 and body.get("success") is True and body.get("replayed") is True
                and body.get(verified_field) is True and body.get("scanId") == scan["id"]
                and body.get("fixListId") == scan["fix_list_id"] and same_saved_result(row)
                and staged_completion.released(row)):
            raise StageRetry("The staged writer has not acknowledged the saved result")
        fresh, stopped = await self._fence(client, job, allow_saved_result=True)
        if stopped:
            return stopped
        if not same_saved_result(fresh) or not staged_completion.released(fresh):
            raise StageRetry("The staged release could not be verified")
        await self._commit(prefix, frontier, generation, stage="done", finalize_receipt_ref=receipt.finished_ref)
        receipt.stage_committed = True
        return {"success": True, "scan_id": job["scan_id"], "pages_crawled": frontier["pages_crawled"],
                "fix_list_id": scan["fix_list_id"]}

    async def process(self, client: Any, stage: str, job: dict, *, batch: int = 0, limited: bool = False, recovery_generation: int = 0) -> dict:
        if type(recovery_generation) is not int or recovery_generation not in (0, 1) or (recovery_generation and stage != "finalize"):
            raise ValueError("Invalid finalize recovery generation")
        delivery_deadline = time.monotonic() + STAGE_DELIVERY_SECONDS
        scan, skipped = await self._fence(client, job, allow_saved_result=stage == "finalize")
        if skipped:
            return skipped
        saved_result = already_terminal(scan)
        if saved_result and not (
            staged_completion.exact_job(scan, job) and staged_completion.terminal_seal(scan)
            and isinstance(scan.get("staged_writer_request_proof"), str)
            and staged_completion.HEX_PROOF.fullmatch(scan["staged_writer_request_proof"])
        ):
            return {"success": True, "skipped": "already_terminal", "status": scan.get("status")}
        job = self._canonical_job(scan, job)
        prefix = self._prefix(job)
        frontier = None
        receipt = None
        receipt_context = None
        cooldown = None
        try:
            leased = await self._lease(prefix, stage, batch, recovery_generation)
            if leased is None:
                if saved_result:
                    return {"success": True, "skipped": "already_terminal", "status": scan.get("status")}
                stored = await self.store.read(prefix + "frontier.json")
                if not stored:
                    raise StageRetry("The plan has not committed")
                if stage == "finalize" and recovery_generation != int("finalize_recovery_until" in stored.value):
                    return {"success": True, "skipped": "superseded_finalize_delivery"}
                return await self._replay(client, scan, job, stored.value)
            frontier, generation, allow_optional_probes = leased
            if saved_result:
                receipt = DeliveryReceipt(self.store, prefix, job, stage, batch, frontier["lease_owner"], generation)
                receipt_context = active_delivery.set(receipt)
                receipt.start()
                return await self._recover_acknowledgement(client, scan, job, prefix, frontier, generation, receipt)
            result_snapshot = await self.store.read(prefix + "result.json.gz") if stage == "finalize" else None
            cooldown = self._target_cooldown(client, scan, job, prefix, stage)
            cooldown_pending = False
            if cooldown is not None:
                try:
                    await cooldown.resume()
                except TargetCooldownPending:
                    cooldown_pending = True
            cooldown_result = (
                cooldown is not None and cooldown.record is not None
                and self._verified_cooldown_result(frontier, result_snapshot, job)
            )
            if (
                recovery_generation and cooldown_result
                and self.clock() >= frontier["finalize_recovery_until"]
                and "target_cooldown_publication" not in frontier
            ):
                # No authority write has started on this blocked path. Give
                # the verified report one bounded lease to save without waiting
                # forever for this auxiliary service. Never renew this window.
                if not await self.store.read(prefix + "completion.json"):
                    if self.clock() >= float(frontier["lease_until"]):
                        raise StageRetry("The stage lease expired")
                    expired = cooldown.remaining_hold() == 0
                    frontier = {**frontier,
                        "finalize_cooldown_fallback_until": self.clock() + STAGE_LEASE_SECONDS,
                        "target_cooldown_publication": {
                            "state": "unconfirmed" if cooldown_pending else "expired" if expired else "acknowledged",
                            "reason": "publication_unavailable" if cooldown_pending else "observation_expired" if expired else "publication_recovered",
                            "observation": cooldown.record["observation"],
                        },
                    }
                    generation = await self.store.write(prefix + "frontier.json", frontier, generation=generation)
            if recovery_generation and self.clock() >= self._finalize_deadline(frontier):
                # A timed-out persist can outlive its worker's HTTP request.
                # Fence new finalizers and leave a full lease interval for
                # previously started writes before attempting terminal failure.
                safe_after = self._finalize_deadline(frontier) + FINALIZE_PERSIST_DRAIN_SECONDS
                if self.clock() < safe_after:
                    raise StageRetry("The last finalize delivery is still draining")
                _, stopped = await self._fence(client, job)
                if stopped:
                    return stopped
                failure_code = "staged_finalize_timeout"
                closed = await self.dep.fail(
                    client, job["scan_id"], failure_code,
                    "The scan could not save its result after retrying. Please start a new scan.",
                    attempt_count=job.get("attempt_count"),
                )
                if closed is False:
                    return {"success": True, "skipped": "superseded_attempt"}
                persisted = await self.dep.read_scan(client, job["scan_id"])
                if not isinstance(persisted, dict):
                    raise StageRetry("The finalization timeout could not be verified")
                if not identity_matches(persisted, job):
                    return {"success": True, "skipped": "identity_mismatch"}
                if current_attempt(persisted) != current_attempt(scan):
                    return {"success": True, "skipped": "superseded_attempt"}
                status = str(persisted.get("status") or "").lower()
                if status == "failed" and persisted.get("error_code") == failure_code:
                    return {"success": False, "error_code": failure_code}
                if already_terminal(persisted):
                    return {"success": True, "skipped": "already_terminal", "status": status}
                raise StageRetry("The finalization timeout was not persisted")
            if cooldown_pending and not (
                recovery_generation and cooldown_result and "target_cooldown_publication" in frontier
            ):
                raise TargetCooldownPending("The target cooldown publication is pending")
            receipt = DeliveryReceipt(self.store, prefix, job, stage, batch, frontier["lease_owner"], generation)
            receipt_context = active_delivery.set(receipt)
            receipt.start()
            if stage == "plan":
                await self.dep.start(client, scan)
                planned = await self.store.read(prefix + "plan.json")
                if planned:
                    plan = planned.value
                    receipt.observe_artifact("plan", planned.generation, produced=False)
                else:
                    remaining = float(frontier["wall_deadline"]) - self.clock()
                    if remaining < 20:
                        await self.dep.fail(client, job["scan_id"], "scanner_wall_timeout", "The scan exhausted its time budget before collecting page evidence. Please try again.", attempt_count=job.get("attempt_count"))
                        return {"success": False, "error_code": "scanner_wall_timeout"}
                    self._require_contact_ready(cooldown)
                    state = await self._run_site_stage(
                        self.dep.plan, client, scan, job, frontier, cooldown,
                        contact_deadline=frontier["wall_deadline"],
                        website_url=job["website_url"], path_prefix=job.get("path_prefix"),
                        scan_mode=job["scan_mode"], timeout_seconds=remaining, job_mode=True, staged=True,
                    )
                    if cooldown is not None:
                        await cooldown.require_acknowledged()
                    plan = {"job": job, "state": state.to_dict(), "wall_deadline": frontier["wall_deadline"]}
                    # Recheck cancellation immediately before evidence enters storage.
                    _, stopped = await self._fence(client, job)
                    if stopped:
                        return stopped
                    plan_generation = await self.store.write(prefix + "plan.json", plan)
                    receipt.observe_artifact("plan", plan_generation, produced=True)
                state = self.dep.state_type.from_dict(plan["state"])
                planned_count = min(int(job["page_cap"]), max(len(state.queue), len(state.pages)))
                frontier = await self._commit(
                    prefix, frontier, generation, stage="finalize" if state.finished else "batch",
                    batch=0, state_ref="plan.json", wall_deadline=plan["wall_deadline"],
                    pages_crawled=len(state.pages), pages_planned=planned_count, plan_receipt_ref=receipt.finished_ref,
                )
                receipt.stage_committed = True
                return await self._replay(client, scan, job, frontier)

            snapshot = await self.store.read(prefix + str(frontier["state_ref"]))
            if not snapshot:
                raise StageRetry("The committed state snapshot is unavailable")
            receipt.observe_artifact("input_state", snapshot.generation, produced=False)
            state = self.dep.state_type.from_dict(snapshot.value["state"])
            deadline_hit = self.clock() >= float(frontier["wall_deadline"])
            if stage == "batch":
                if not deadline_hit:
                    self._require_contact_ready(cooldown)
                    await self._run_site_stage(
                        self.dep.crawl, client, scan, job, frontier, cooldown,
                        contact_deadline=frontier["wall_deadline"], state=state, max_pages=BATCH_SIZE,
                    )
                    if cooldown is not None:
                        await cooldown.require_acknowledged()
                _, stopped = await self._fence(client, job)
                if stopped:
                    return stopped
                execution = uuid.uuid4().hex
                ref = f"batches/{batch}-{execution}.state.json.gz"
                checkpoint = state.to_dict()
                state_generation = await self.store.write(prefix + ref, {"state": checkpoint})
                receipt.observe_artifact("output_state", state_generation, produced=True)
                # Full state includes cross-batch identity merges and evidence;
                # immutable manifests avoid a non-atomic shared append object.
                evidence_ref = f"batches/{batch}-{execution}.pages.json.gz"
                pages_generation = await self.store.write(prefix + evidence_ref, {"pages": state.pages})
                receipt.observe_artifact("batch_pages", pages_generation, produced=True)
                cutoff = deadline_hit or self.clock() >= float(frontier["wall_deadline"]) or bool(getattr(state, "limited", False))
                limit_reason = str(getattr(state, "completion_reason", "")) if cutoff else ""
                done = state.finished or cutoff
                frontier = await self._commit(prefix, frontier, generation,
                    stage="finalize" if done else "batch", batch=batch + 1,
                    state_ref=ref, pages_crawled=len(state.pages),
                    pages_planned=min(int(job["page_cap"]), max(int(frontier.get("pages_planned") or 0), len(state.pages))),
                    committed_batches=[*frontier.get("committed_batches", []), {
                        "batch": batch, "state": ref, "pages": evidence_ref, "receipt_ref": receipt.finished_ref,
                    }],
                    limited=bool(frontier.get("limited")) or cutoff,
                    limit_reason=limit_reason or ("wall_budget" if cutoff else ""),
                    dispatch_after=float(checkpoint.get("rate_limit_pacer", {}).get("next_request_at") or 0),
                )
                receipt.stage_committed = True
                return await self._replay(client, scan, job, frontier)

            if stage != "finalize":
                raise ValueError("Invalid staged operation")
            # An authorized watchdog may finalize committed partial evidence.
            limited = limited or bool(frontier.get("limited")) or bool(getattr(state, "limited", False)) or not state.finished
            if result_snapshot:
                result = result_snapshot.value
                receipt.observe_artifact("result", result_snapshot.generation, produced=False)
            else:
                if cooldown is not None and cooldown.remaining_hold():
                    allow_optional_probes = False
                result = await self._run_site_stage(
                    self.dep.finalize, client, scan, job, frontier, cooldown, state=state,
                    allow_contact=allow_optional_probes, allow_optional_probes=allow_optional_probes,
                )
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
                result_generation = await self.store.write(prefix + "result.json.gz", result)
                receipt.observe_artifact("result", result_generation, produced=True)
                # Persist the valid final report before a failed relay asks
                # Cloud Tasks to retry. Replacement never repeats its probes.
                if cooldown is not None:
                    try:
                        await cooldown.require_acknowledged()
                    except TargetCooldownPending:
                        # Bind the cache to the still-owned frontier generation.
                        # A result left by a lost lease cannot become fallback
                        # authority merely because its filename exists.
                        if self.clock() >= float(frontier["lease_until"]):
                            raise StageRetry("The stage lease expired")
                        frontier = {**frontier, "target_cooldown_result_generation": result_generation}
                        generation = await self.store.write(prefix + "frontier.json", frontier, generation=generation)
                        raise
            if "target_cooldown_publication" in frontier:
                # Terminal persistence releases the claim, so this pending
                # outbox is retained evidence, not a promised post-terminal
                # replay. Include its unconfirmed state in the signed report.
                result = {**result, "crawl_timing": {
                    **(result.get("crawl_timing") or {}),
                    "target_cooldown_publication": frontier["target_cooldown_publication"],
                }}
            fresh, stopped = await self._fence(client, job)
            if stopped:
                return stopped
            signing_key = str(os.getenv("SCAN_EVIDENCE_SIGNING_KEY") or "")
            if not signing_key:
                raise StageRetry("Authority signing is not configured")
            reviewed = None
            # Completion can already close a definitively blocked crawl from
            # its evidence. A reviewer outage must not mask that outcome.
            crawl_limitation = terminal_crawl_limitation(result)
            if self.dep.review is not None and crawl_limitation is None:
                review_snapshot = await self.store.read(prefix + "review.json.gz")
                if review_snapshot:
                    reviewed = review_snapshot.value
                    receipt.observe_artifact("review", review_snapshot.generation, produced=False)
                else:
                    reviewed = await asyncio.wait_for(self.dep.review(result), timeout=25)
                    _, stopped = await self._fence(client, job)
                    if stopped:
                        return stopped
                    review_generation = await self.store.write(prefix + "review.json.gz", reviewed)
                    receipt.observe_artifact("review", review_generation, produced=True)
                fresh, stopped = await self._fence(client, job)
                if stopped:
                    return stopped
            if crawl_limitation is None:
                # Write the timestamp before the first persistence request.
                # Later deliveries keep it even if the response is lost.
                stamp_key = prefix + "completion.json"
                stamp = await self.store.read(stamp_key)
                if stamp:
                    ready_at = stamp.value["result_ready_at"]
                else:
                    ready_at = datetime.fromtimestamp(self.clock(), timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
                    await self.store.write(stamp_key, {"result_ready_at": ready_at})
                result = {**result, "result_ready_at": ready_at}
            if recovery_generation and self.clock() >= self._finalize_deadline(frontier):
                raise StageRetry("The recovery window closed before the result could be saved")
            async def retain(writer, envelope):
                generations = {name: receipt.artifacts[name]["generation"] for name in ("input_state", "review", "result")}
                binding = staged_completion.binding_for(job, fresh, frontier, batch, generations, ready_at, writer)
                return await staged_completion.retain_packet(self.store, prefix, binding, envelope, signing_key)

            can_retain = reviewed is not None and staged_completion.exact_job(fresh, job)
            token = staged_completion.prepare_staged_completion.set(retain if can_retain else None)
            try:
                completion = self.dep.complete(client, fresh, result, signing_key, review=reviewed) if reviewed is not None else self.dep.complete(client, fresh, result, signing_key)
                outcome = await asyncio.wait_for(completion, timeout=90)
            finally:
                staged_completion.prepare_staged_completion.reset(token)
            if outcome.get("transient"):
                raise StageRetry("Authority persistence is unavailable")
            if outcome.get("superseded"):
                return {"success": True, "skipped": "superseded_attempt"}
            if not outcome.get("ok"):
                await self.dep.fail(client, job["scan_id"], str(outcome.get("failure_code") or "staged_completion_failed"), str(outcome.get("customer_message") or "The scan result could not be saved."), attempt_count=job.get("attempt_count"))
                return {"success": False, "error_code": outcome.get("failure_code")}
            frontier = await self._commit(
                prefix, frontier, generation, stage="done", batch=batch,
                pages_crawled=len(state.pages), finalize_receipt_ref=receipt.finished_ref,
            )
            receipt.stage_committed = True
            return {"success": True, "scan_id": job["scan_id"], "pages_crawled": len(state.pages), "fix_list_id": outcome.get("fix_list_id"),
                    **({"target_cooldown_publication": frontier["target_cooldown_publication"]["state"]} if "target_cooldown_publication" in frontier else {})}
        except TargetCooldownPending as exc:
            raise StageRetry(str(exc)) from exc
        except TargetContactRetry as exc:
            # Cloud Tasks may retry before that window ends. Each delivery must
            # acquire again, so retries cannot contact a protected origin.
            raise StageRetry(str(exc), retry_after=exc.retry_after) from exc
        except (WorkspaceConflict, WorkspaceUnavailable, asyncio.TimeoutError) as exc:
            raise StageRetry("The stage did not finish its durable commit") from exc
        finally:
            if receipt is not None:
                receipt.stop_sampling()
            if receipt_context is not None:
                active_delivery.reset(receipt_context)
            if cooldown is not None:
                await cooldown.drain()
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
            if receipt is not None:
                # Leave room for the existing HTTP timeout and response.
                await receipt.finish(deadline=delivery_deadline - 1)

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
        if frontier.get("stage") == "done":
            return {"success": True, "scan_id": job["scan_id"], "already_completed": True}
        if frontier.get("stage") not in {"batch", "finalize"}:
            raise StageRetry("The committed frontier cannot be finalized")
        if "finalize_recovery_until" not in frontier:
            # Only an interrupted crawl produces new partial evidence.
            # A completed crawl can reuse its original result and review.
            if frontier["stage"] == "batch":
                frontier.update(stage="finalize", limited=True)
            frontier.update(
                finalize_recovery_until=self.clock() + FINALIZE_RECOVERY_SECONDS,
                lease_owner="", lease_until=0,
            )
            await self.store.write(prefix + "frontier.json", frontier, generation=stored.generation)
        batch = int(frontier["batch"])
        recovery_until = self._finalize_deadline(frontier)
        if self.clock() >= recovery_until:
            if self.clock() < recovery_until + FINALIZE_PERSIST_DRAIN_SECONDS:
                raise StageRetry("The last finalize delivery is still draining")
            return await self.process(client, "finalize", job, batch=batch, recovery_generation=1)
        _, stopped = await self._fence(client, job)
        if stopped:
            return stopped
        await self.dispatcher.enqueue(job, "finalize", batch, limited=bool(frontier.get("limited")), recovery_generation=1)
        return {"success": True, "scan_id": job["scan_id"], "finalize_recovery_pending": True}

    async def delete_workspace(self, client: Any, job: dict) -> dict:
        scan = await self.dep.read_scan(client, job["scan_id"])
        if not isinstance(scan, dict):
            raise StageRetry("The scan record is unavailable")
        if not identity_matches(scan, job) or current_attempt(scan) != int(job.get("attempt_count") or 1):
            return {"success": True, "skipped": "identity_mismatch"}
        if not task_matches_scan_contract(scan, job):
            return {"success": True, "skipped": "scan_contract_mismatch"}
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
