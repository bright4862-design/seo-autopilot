#!/usr/bin/env python3
"""Read the private receipts of one already completed staged canary.

The input is the authenticated canary report handed to this operator by the
500-page runner or the published Standard 150 readback. This tool neither
runs a scan nor observes a browser.
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import hashlib
import io
import json
import os
import re
import stat
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

SCANNER_ROOT = Path(__file__).resolve().parents[1]
if __name__ == "__main__":
    sys.path.insert(0, str(SCANNER_ROOT))

from app.staged_telemetry import MAX_RECORDED_DELIVERIES, RECEIPT_VERSION
from app.workspace import WorkspaceObject, attempt_prefix
from scripts.export_staged_500_fixture import HTTPS_ORIGIN, PAGES_PER_SECTION, SECTIONS

BUCKET = "fixlist-scan-workspaces-seo-autopilot-501517"
WORKER_SERVICE = "fixlist-standard150-worker"
CANARY_REPORT_VERSION = "staged_500_canary_v1"
EVIDENCE_VERSION = "staged_500_receipt_evidence_v1"
PUBLISHED_150_CANARY_VERSION = "staged_150_published_canary_v1"
PUBLISHED_150_EVIDENCE_VERSION = "staged_150_published_receipt_evidence_v1"
MEMORY_LIMIT_BYTES = 1_073_741_824
MAX_RECEIPT_BYTES = 64 * 1024
MAX_PUBLISHED_150_EVIDENCE_BYTES = 16 * 1024 * 1024
MAX_CANARY_BYTES = 1024 * 1024
READ_TIMEOUT_SECONDS = 10
COLLECTION_TIMEOUT_SECONDS = 120
PARALLEL_READS = 12
RECEIPT_GRACE_SECONDS = 12
SHA256 = re.compile(r"[a-f0-9]{64}")
SOURCE_SHA = re.compile(r"[a-f0-9]{40}")
FINGERPRINT = re.compile(r"[a-f0-9]{16}")
ID = re.compile(r"[A-Za-z0-9_-]{6,160}")
OWNER_ID = re.compile(r"[A-Za-z0-9_-]{6,64}")
WORKER_REVISION = re.compile(WORKER_SERVICE + r"-[a-z0-9-]{1,32}")
DELIVERY_ID = re.compile(r"[a-f0-9]{32}")
GENERATION = re.compile(r"[1-9][0-9]{0,23}")
FINISHED_REF = re.compile(r"receipts/([a-f0-9]{32})\.finished\.json\.gz")
STATE_REF = re.compile(r"batches/([0-9]{1,3})-([a-f0-9]{32})\.state\.json\.gz")
STAGES = {"plan", "batch", "finalize"}
COMPLETION = {"complete": "persistDurableScanAuthorityV9", "limited": "persistLimitedScanResultV9"}
IDENTITY_FIELDS = (
    "schema_version", "delivery_id", "lease_generation", "scan_id", "attempt",
    "request_id_sha256", "scan_mode", "page_cap", "stage", "batch",
    "started_at_unix_ms", "runtime",
)


class EvidenceError(ValueError):
    """A stable error code safe to report instead of cloud SDK output."""


def require(ok: Any, code: str) -> None:
    if not ok:
        raise EvidenceError(code)


def mapping(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def matches(pattern: re.Pattern, value: Any) -> bool:
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def positive(value: Any) -> bool:
    return type(value) is int and value > 0


def parse_timestamp(value: Any) -> int:
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.utcoffset() is not None:
            return int(parsed.timestamp() * 1000)
    except (OverflowError, OSError, TypeError, ValueError):
        pass
    raise EvidenceError("canary_timestamps_invalid")


@dataclass(frozen=True)
class Canary:
    scan_id: str
    attempt: int
    request_digest: str
    terminal_status: str
    pages: int
    planned: int
    batches: int
    observed_ms: int
    started_ms: int
    completed_ms: int
    runtime: dict
    page_cap: int
    owner_user_id: str
    project_id: str | None
    target_url: str | None


def canary_identity(report: dict) -> Canary:
    require(isinstance(report, dict), "canary_report_invalid")
    version = report.get("schema_version")
    require(version in (CANARY_REPORT_VERSION, PUBLISHED_150_CANARY_VERSION), "terminal_canary_identity_missing")
    page_cap = 150 if version == PUBLISHED_150_CANARY_VERSION else 500
    provenance = mapping(report.get("provenance"))
    if "ordinary_task_observation" in provenance:
        task_digest = provenance.get("ordinary_stage_task_observation_sha256")
        require(report.get("execution_mode") == "ordinary_user_readback"
                and provenance["ordinary_task_observation"] == "deferred"
                and (matches(SHA256, task_digest) or (page_cap == 150 and task_digest is None)),
                "ordinary_stage_task_observation_unverified")
    scan_id, request_id = report.get("scan_id"), report.get("request_id")
    attempt, pages, planned, batches = (report.get(name) for name in (
        "attempt_count", "pages_crawled", "pages_planned", "committed_batch_count",
    ))
    status = report.get("terminal_status")
    require(report.get("production_freeze") is False
            and report.get("terminal_outcome_verified") is True
            and (report.get("durable_worker_owned") is True
                 or (status == "limited" and report.get("durable_worker_receipt_required") is True))
            and isinstance(status, str) and status in COMPLETION and report.get("page_cap") == page_cap
            and matches(ID, scan_id) and matches(ID, request_id)
            and positive(attempt) and attempt < 2**31, "terminal_canary_identity_missing")
    require(positive(pages) and positive(planned) and 0 < pages <= planned <= page_cap
            and positive(batches) and batches <= MAX_RECORDED_DELIVERIES - 2
            and pages <= batches * 50, "terminal_canary_progress_invalid")
    project_id, target_url = None, None
    if page_cap == 150:
        project_id, target_url = report.get("project_id"), report.get("target_url")
        require(report.get("execution_mode") == "ordinary_user_readback"
                and report.get("authority_verified") is True and status == "complete"
                and type(report.get("page_cap")) is int and pages == planned == 150 and batches == 3
                and matches(ID, project_id) and matches(HTTPS_ORIGIN, target_url),
                "published_150_fixture_identity_missing")
        target_url = target_url.rstrip("/") + "/"
    source, fingerprint = report.get("source_sha"), report.get("release_fingerprint")
    revision = provenance.get("worker_revision")
    staged_digest = provenance.get("worker_config_sha256")
    owner = report.get("expected_owner_user_id")
    require(matches(OWNER_ID, owner), "prerequisite_worker_identity_missing")
    cohort = hashlib.sha256(json.dumps([owner], separators=(",", ":")).encode()).hexdigest()
    require(matches(SOURCE_SHA, source) and matches(FINGERPRINT, fingerprint)
            and source == provenance.get("source_sha") and fingerprint == provenance.get("release_fingerprint")
            and matches(WORKER_REVISION, revision)
            and matches(SHA256, staged_digest) and provenance.get("staged_owner_cohort_sha256") == cohort
            and matches(SHA256, provenance.get("prerequisite_sha256")), "prerequisite_worker_identity_missing")
    observed = parse_timestamp(report.get("observed_at"))
    started = parse_timestamp(report.get("scan_started_at"))
    completed = parse_timestamp(report.get("scan_completed_at"))
    require(observed - 30_000 <= started < completed <= time.time_ns() // 1_000_000 + 30_000
            and completed - started <= 1_800_000,
            "canary_timestamps_invalid")
    runtime = {
        "source_sha": source, "revision": revision, "service": WORKER_SERVICE,
        "staged_config_sha256": staged_digest, "release_fingerprint": fingerprint,
        "pipeline_mode": "staged", "staged_owner_cohort_sha256": cohort,
    }
    return Canary(scan_id, attempt, hashlib.sha256(request_id.encode()).hexdigest(), status,
                  pages, planned, batches, observed, started, completed, runtime, page_cap, owner, project_id, target_url)


def finished_id(ref: Any) -> str:
    require(matches(FINISHED_REF, ref), "committed_receipt_reference_invalid")
    return FINISHED_REF.fullmatch(ref)[1]


def frontier_layout(canary: Canary, frontier: dict) -> tuple[list[str], list[tuple[str, int, str]], list[tuple[str, str]]]:
    require(frontier.get("stage") == "done" and frontier.get("lease_owner") == ""
            and frontier.get("lease_until") == 0, "frontier_not_done")
    require(frontier.get("batch") == canary.batches and frontier.get("pages_crawled") == canary.pages
            and frontier.get("pages_planned") == canary.planned, "frontier_terminal_progress_mismatch")
    require(frontier.get("telemetry_history_complete") is True, "delivery_history_incomplete")
    ids = frontier.get("telemetry_delivery_ids")
    require(isinstance(ids, list) and canary.batches + 2 <= len(ids) <= MAX_RECORDED_DELIVERIES
            and all(matches(DELIVERY_ID, item) for item in ids)
            and len(set(ids)) == len(ids), "delivery_history_invalid")
    entries = frontier.get("committed_batches")
    require(isinstance(entries, list) and len(entries) == canary.batches, "committed_batches_mismatch")
    committed = [("plan", 0, finished_id(frontier.get("plan_receipt_ref")))]
    artifacts = []
    for batch, entry in enumerate(entries):
        entry = mapping(entry)
        state_path = entry.get("state")
        require(matches(STATE_REF, state_path) and STATE_REF.fullmatch(state_path)[1] == str(batch)
                and entry.get("batch") == batch, "committed_state_reference_invalid")
        pages_path = state_path.removesuffix(".state.json.gz") + ".pages.json.gz"
        require(entry.get("pages") == pages_path, "committed_pages_reference_invalid")
        artifacts.append((state_path, pages_path))
        committed.append(("batch", batch, finished_id(entry.get("receipt_ref"))))
    committed.append(("finalize", canary.batches, finished_id(frontier.get("finalize_receipt_ref"))))
    positions = {delivery: index for index, delivery in enumerate(ids)}
    sequence = [positions.get(delivery, -1) for _, _, delivery in committed]
    require(frontier.get("state_ref") == artifacts[-1][0] and -1 not in sequence
            and sequence == sorted(set(sequence)) and sequence[-1] == len(ids) - 1,
            "committed_receipt_order_invalid")
    return ids, committed, artifacts


def verify_receipt_pairs(canary: Canary, ids: list[str], pairs: dict) -> dict[str, dict]:
    result = {}
    lease_generations = set()
    previous_start = 0
    previous_stage = (0, 0)
    stage_order = {"plan": 0, "batch": 1, "finalize": 2}
    for delivery in ids:
        start, finish = pairs.get(delivery, (None, None))
        require(isinstance(start, WorkspaceObject) and isinstance(finish, WorkspaceObject), "delivery_receipt_missing")
        left, right = mapping(start.value), mapping(finish.value)
        require(all(field in left and field in right and left[field] == right[field] for field in IDENTITY_FIELDS)
                and right["schema_version"] == RECEIPT_VERSION and right["delivery_id"] == delivery
                and right["scan_id"] == canary.scan_id
                and positive(right["attempt"]) and right["attempt"] == canary.attempt
                and right["scan_mode"] == f"standard_{canary.page_cap}" and right["page_cap"] == canary.page_cap
                and right["request_id_sha256"] == canary.request_digest, "delivery_receipt_identity_mismatch")
        require(right["runtime"] == canary.runtime, "delivery_runtime_mismatch")
        lease, stage, batch = right["lease_generation"], right["stage"], right["batch"]
        require(matches(GENERATION, lease) and lease not in lease_generations, "delivery_lease_generation_invalid")
        lease_generations.add(lease)
        require(isinstance(stage, str) and stage in STAGES and type(batch) is int
                and ((stage == "plan" and batch == 0)
                     or (stage == "batch" and 0 <= batch < canary.batches)
                     or (stage == "finalize" and batch == canary.batches))
                and (stage_order[stage], batch) >= previous_stage, "delivery_stage_order_invalid")
        previous_stage = stage_order[stage], batch
        started, finished = right["started_at_unix_ms"], right.get("finished_at_unix_ms")
        elapsed = right.get("elapsed_ms")
        require(positive(started) and positive(finished) and finished >= started
                and max(canary.observed_ms, canary.started_ms - 120_000) - 30_000 <= started <= canary.completed_ms + 30_000
                and previous_start - 30_000 <= started <= finished <= canary.completed_ms + 450_000
                and type(elapsed) is int and 0 <= elapsed <= 450_000
                and abs((finished - started) - elapsed) <= 30_000,
                "delivery_receipt_time_invalid")
        previous_start = started
        require(type(right.get("stage_committed")) is bool and isinstance(right.get("artifacts"), dict),
                "delivery_receipt_commit_state_invalid")
        result[delivery] = right
    return result


def artifact_value(receipt: dict, name: str) -> tuple[str, bool]:
    record = mapping(receipt["artifacts"].get(name))
    generation, produced = record.get("generation"), record.get("produced")
    require(matches(GENERATION, generation) and type(produced) is bool, "receipt_artifact_generation_missing")
    return generation, produced


def verify_artifact_lineage(
    receipts: dict[str, dict], committed: list[tuple[str, int, str]],
    artifacts: list[tuple[str, str]], object_generations: dict[str, str | None],
) -> dict:
    marks = {delivery for _, _, delivery in committed}
    require({delivery for delivery, row in receipts.items() if row["stage_committed"]} == marks,
            "receipt_commit_history_mismatch")
    for stage, batch, delivery in committed:
        row = receipts[delivery]
        require((row["stage"], row["batch"]) == (stage, batch), "committed_receipt_stage_mismatch")
    plan, final = receipts[committed[0][2]], receipts[committed[-1][2]]
    delivery_order = {delivery: index for index, delivery in enumerate(receipts)}

    def verify_producer(current: dict, name: str, path: str) -> dict:
        generation, produced = artifact_value(current, name)
        require(object_generations.get(path) == generation, "workspace_artifact_generation_mismatch")
        producers = [row for row in receipts.values()
                     if row["stage"] == current["stage"] and row["batch"] == current["batch"]
                     and row["artifacts"].get(name) == {"generation": generation, "produced": True}]
        require(len(producers) == 1 and (producers[0] is current) == produced
                and delivery_order[producers[0]["delivery_id"]] <= delivery_order[current["delivery_id"]],
                "workspace_artifact_producer_unverified")
        return producers[0]

    verify_producer(plan, "plan", "plan.json")
    input_generation = object_generations.get("plan.json")
    for (_, _, delivery), (state_path, pages_path) in zip(committed[1:-1], artifacts, strict=True):
        batch = receipts[delivery]
        require(artifact_value(batch, "input_state") == (input_generation, False)
                and artifact_value(batch, "output_state") == (object_generations.get(state_path), True)
                and artifact_value(batch, "batch_pages") == (object_generations.get(pages_path), True),
                "batch_checkpoint_lineage_mismatch")
        input_generation = object_generations.get(state_path)
    require(artifact_value(final, "input_state") == (input_generation, False),
            "finalize_checkpoint_lineage_mismatch")
    result_producer = verify_producer(final, "result", "result.json.gz")
    review_producer = verify_producer(final, "review", "review.json.gz")
    for producer in (result_producer, review_producer):
        require(artifact_value(producer, "input_state") == (input_generation, False)
                and artifact_value(producer, "result")[0] == object_generations.get("result.json.gz"),
                "finalize_review_lineage_mismatch")
    return review_producer


def memory_evidence(receipts: dict[str, dict], review_producer: dict) -> tuple[dict, list[str]]:
    failures = []
    parent_samples, review_samples, peaks = [], [], []
    for row in receipts.values():
        memory = mapping(row.get("memory"))
        parent = memory.get("parent_rss_peak_bytes")
        if positive(parent) and positive(memory.get("parent_rss_samples")):
            parent_samples.append(parent)
        child = memory.get("parent_and_review_child_rss_peak_bytes")
        if positive(child) and positive(memory.get("parent_and_review_child_rss_samples")):
            review_samples.append(child)
        memory_group = mapping(memory.get("cgroup"))
        peak = memory_group.get("peak_bytes")
        if (memory_group.get("scope") == "cgroup_lifetime" and positive(peak)
                and memory_group.get("limit_bytes") == MEMORY_LIMIT_BYTES
                and peak < MEMORY_LIMIT_BYTES):
            peaks.append(peak)
    if len(parent_samples) != len(receipts):
        failures.append("parent_rss_sampling_incomplete")
    review_memory = mapping(review_producer.get("memory"))
    if not (positive(review_memory.get("parent_and_review_child_rss_peak_bytes"))
            and positive(review_memory.get("parent_and_review_child_rss_samples"))):
        failures.append("review_child_rss_sampling_unverified")
    if len(peaks) != len(receipts):
        failures.append("cgroup_lifetime_bound_unverified")
    sampled_peak = max([*parent_samples, *review_samples], default=None)
    if sampled_peak is not None and sampled_peak >= MEMORY_LIMIT_BYTES:
        failures.append("sampled_rss_budget_exceeded")
    return {
        "sampled_aggregate_rss_peak_bytes": sampled_peak,
        "parent_sampled_delivery_count": len(parent_samples),
        "review_sampled_delivery_count": len(review_samples),
        "cgroup_lifetime_peak_upper_bound_bytes": max(peaks, default=None),
        "cgroup_measured_delivery_count": len(peaks),
        "reviewed_worker_memory_limit_bytes": MEMORY_LIMIT_BYTES,
        "all_stages_verified": not failures,
    }, failures


def verify_evidence(canary: Canary, frontier: WorkspaceObject, pairs: dict, generations: dict[str, str | None]) -> dict:
    ids, committed, artifacts = frontier_layout(canary, mapping(frontier.value))
    receipts = verify_receipt_pairs(canary, ids, pairs)
    review_producer = verify_artifact_lineage(receipts, committed, artifacts, generations)
    final = receipts[committed[-1][2]]
    require(final["finished_at_unix_ms"] >= canary.completed_ms - 30_000, "finalize_receipt_time_invalid")
    memory, failures = memory_evidence(receipts, review_producer)
    request = mapping(final.get("completion_request"))
    exact_request = (
        request.get("function") == COMPLETION[canary.terminal_status]
        and positive(request.get("body_bytes")) and matches(SHA256, request.get("body_sha256"))
        and type(request.get("status_code")) is int and 200 <= request["status_code"] < 300
    )
    if not exact_request:
        failures.append("terminal_completion_request_unverified")
    return {
        "worker_runtime_verified": True,
        "receipt_evidence_verified": not failures,
        "delivery_count": len(ids),
        "committed_delivery_count": len(committed),
        "frontier_generation": str(frontier.generation),
        "receipt_snapshot_sha256": hashlib.sha256(json.dumps({
            "frontier": str(frontier.generation),
            "deliveries": [[delivery, *(str(obj.generation) for obj in pairs[delivery])] for delivery in ids],
            "artifacts": generations,
        }, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "completion_request": {key: request[key] for key in ("function", "body_bytes", "body_sha256", "status_code")} if exact_request else None,
        "memory": memory,
        "unverified": failures,
    }


async def verify_published_150_pages(
    canary: Canary, storage: Any, prefix: str, artifacts: list[tuple[str, str]], generations: dict[str, str | None],
) -> dict:
    from app.scanner import final_url_identity

    async def read_artifact(path: str) -> dict:
        observed = await storage.read_evidence(prefix + path)
        require(isinstance(observed, WorkspaceObject) and str(observed.generation) == generations[path],
                "published_150_artifact_generation_mismatch")
        return mapping(observed.value)

    allowed_urls = {canary.target_url} | {
        f"{canary.target_url}{section}/{number}.html"
        for section in SECTIONS for number in range(PAGES_PER_SECTION)
    }

    def checked_urls(document: dict, count: int) -> set[str]:
        pages = document.get("pages")
        require(isinstance(pages, list) and len(pages) == count, "published_150_page_count_mismatch")
        urls = set()
        for raw_page in pages:
            page = mapping(raw_page)
            url = final_url_identity(page.get("final_url") or page.get("url"))
            require(url in allowed_urls and page.get("status_code") == 200
                    and final_url_identity(page.get("canonical")) == url, "published_150_fixture_page_unverified")
            require(url not in urls, "published_150_duplicate_page")
            urls.add(url)
        return urls

    plan = await read_artifact("plan.json")
    job = mapping(plan.get("job"))
    request_id = job.get("request_id")
    require(matches(ID, request_id) and hashlib.sha256(request_id.encode()).hexdigest() == canary.request_digest
            and job.get("idempotency_key") == request_id and job.get("scan_id") == canary.scan_id
            and job.get("attempt_count") == canary.attempt and job.get("owner_user_id") == canary.owner_user_id
            and job.get("project_id") == canary.project_id and job.get("scan_mode") == "standard_150"
            and job.get("page_cap") == 150 and job.get("pipeline_mode") == "staged"
            and isinstance(job.get("website_url"), str) and job["website_url"].rstrip("/") + "/" == canary.target_url
            and mapping(plan.get("state")).get("pages") == [], "published_150_plan_identity_mismatch")
    previous: set[str] = set()
    for batch, (_, pages_path) in enumerate(artifacts, start=1):
        current = checked_urls(await read_artifact(pages_path), batch * 50)
        require(previous < current, "published_150_batch_pages_changed")
        previous = current
    result = await read_artifact("result.json.gz")
    require(result.get("success") is True and result.get("scan_id") == canary.scan_id
            and result.get("request_id") == request_id and result.get("idempotency_key") == request_id
            and result.get("submitted_url") == job["website_url"] and result.get("scan_mode") == "standard_150"
            and result.get("pipeline_mode") == "staged" and result.get("pipeline_limited") is False
            and result.get("page_cap") == 150 and result.get("pages_crawled") == 150
            and result.get("beta_revision_fingerprint") == canary.runtime["release_fingerprint"],
            "published_150_result_identity_mismatch")
    require(checked_urls(result, canary.pages) == previous, "published_150_result_pages_mismatch")
    return {
        "checked_distinct_page_count": len(previous),
        "checked_page_set_sha256": hashlib.sha256(json.dumps(sorted(previous), separators=(",", ":")).encode()).hexdigest(),
    }


class ReceiptStorage:
    """Read bounded objects and generation-only metadata through ADC."""

    def __init__(self, bucket: Any):
        self.bucket = bucket
        self.requests = asyncio.Semaphore(PARALLEL_READS)

    def _read(self, key: str, metadata_only: bool, limit: int = MAX_RECEIPT_BYTES) -> WorkspaceObject | str | None:
        from google.api_core.exceptions import NotFound, PreconditionFailed

        blob = self.bucket.blob(key)
        try:
            blob.reload(timeout=READ_TIMEOUT_SECONDS, retry=None)
            generation = str(blob.generation)
            require(matches(GENERATION, generation), "workspace_generation_invalid")
            if metadata_only:
                return generation
            too_large = "workspace_control_object_too_large" if limit == MAX_RECEIPT_BYTES else "workspace_evidence_object_too_large"
            require(positive(blob.size) and blob.size <= limit, too_large)
            raw = blob.download_as_bytes(if_generation_match=int(generation), timeout=READ_TIMEOUT_SECONDS,
                                         retry=None, raw_download=True)
            require(len(raw) <= limit, too_large)
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as compressed:
                document = compressed.read(limit + 1)
            require(len(document) <= limit, too_large)
            value = json.loads(document)
            require(isinstance(value, dict), "workspace_control_document_invalid")
            return WorkspaceObject(value, int(generation))
        except NotFound:
            return None
        except PreconditionFailed as exc:
            raise EvidenceError("workspace_changed_during_collection") from exc
        except EvidenceError:
            raise
        except Exception as exc:
            raise EvidenceError("workspace_read_unavailable") from exc

    async def read(self, key: str) -> WorkspaceObject | None:
        async with self.requests:
            return await asyncio.to_thread(self._read, key, False)

    async def read_evidence(self, key: str) -> WorkspaceObject | None:
        async with self.requests:
            return await asyncio.to_thread(self._read, key, False, MAX_PUBLISHED_150_EVIDENCE_BYTES)

    async def generation(self, key: str) -> str | None:
        async with self.requests:
            return await asyncio.to_thread(self._read, key, True)


async def collect(canary: Canary, storage: Any, *, verify_pages=None) -> dict:
    prefix = attempt_prefix(canary.scan_id, canary.attempt)
    key = prefix + "frontier.json"
    tombstone = "deleted/" + "/".join(prefix.split("/")[:2]) + "/"
    require(await storage.read(tombstone) is None, "workspace_deleted")
    grace = time.monotonic() + RECEIPT_GRACE_SECONDS
    while True:
        frontier = await storage.read(key)
        if frontier and frontier.value.get("stage") == "done":
            break
        require(time.monotonic() < grace, "frontier_not_done")
        await asyncio.sleep(0.5)
    ids, _, artifacts = frontier_layout(canary, frontier.value)

    async def read_pair(delivery: str) -> tuple[WorkspaceObject | None, WorkspaceObject | None]:
        stem = prefix + "receipts/" + delivery
        started, finished = await asyncio.gather(storage.read(stem + ".started.json.gz"),
                                                 storage.read(stem + ".finished.json.gz"))
        return started, finished

    paths = ["plan.json", "result.json.gz", "review.json.gz", *(path for pair in artifacts for path in pair)]
    values, metadata = await asyncio.gather(
        asyncio.gather(*(read_pair(delivery) for delivery in ids)),
        asyncio.gather(*(storage.generation(prefix + path) for path in paths)),
    )
    pairs = dict(zip(ids, values, strict=True))
    pending = [delivery for delivery in ids if None in pairs[delivery]]
    while pending and time.monotonic() < grace:
        await asyncio.sleep(0.5)
        pairs.update(zip(pending, await asyncio.gather(*(read_pair(delivery) for delivery in pending)), strict=True))
        pending = [delivery for delivery in pending if None in pairs[delivery]]
    generations = dict(zip(paths, metadata, strict=True))
    page_evidence = {}
    if verify_pages is not None:
        page_evidence = await verify_pages(canary, storage, prefix, artifacts, generations)
    elif canary.page_cap == 150:
        page_evidence = await verify_published_150_pages(canary, storage, prefix, artifacts, generations)
    final_frontier, deletion = await asyncio.gather(storage.read(key), storage.read(tombstone))
    require(deletion is None, "workspace_deleted")
    require(final_frontier is not None and final_frontier.generation == frontier.generation,
            "workspace_changed_during_collection")
    return {**verify_evidence(canary, frontier, pairs, generations), **page_evidence}


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canary-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    page_cap = 500
    try:
        report_path, output = args.canary_report, args.output
        require(report_path.is_absolute() and report_path.resolve(strict=True) == report_path,
                "canary_report_path_invalid")
        require(output.is_absolute() and output.parent.is_dir() and output.parent.resolve(strict=True) == output.parent
                and not output.is_relative_to(SCANNER_ROOT.parent), "output_path_invalid")
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        with os.fdopen(os.open(report_path, flags), "rb") as source:
            require(stat.S_ISREG(os.fstat(source.fileno()).st_mode), "canary_report_path_invalid")
            raw_report = source.read(MAX_CANARY_BYTES + 1)
        require(len(raw_report) <= MAX_CANARY_BYTES, "canary_report_too_large")
        report = json.loads(raw_report)
        require(isinstance(report, dict), "canary_report_invalid")
        if report.get("schema_version") == PUBLISHED_150_CANARY_VERSION:
            page_cap = 150
        canary = canary_identity(report)
        evidence_version = PUBLISHED_150_EVIDENCE_VERSION if canary.page_cap == 150 else EVIDENCE_VERSION
        with os.fdopen(os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "w") as report_file:
            evidence = {
                "schema_version": evidence_version, "production_freeze": False,
                "canary_report_sha256": hashlib.sha256(raw_report).hexdigest(),
                "scan_id": canary.scan_id, "attempt_count": canary.attempt,
                "source_sha": canary.runtime["source_sha"], "release_fingerprint": canary.runtime["release_fingerprint"],
                "worker_revision": canary.runtime["revision"], "workspace_bucket": BUCKET,
                "prerequisite_sha256": report["provenance"]["prerequisite_sha256"],
                "terminal_status": canary.terminal_status, "worker_runtime_verified": False,
                "receipt_evidence_verified": False, "completion_request": None, "memory": None,
            }
            if canary.page_cap == 150:
                evidence.update(page_cap=canary.page_cap, committed_batch_count=canary.batches)
            try:
                require(not os.getenv("STORAGE_EMULATOR_HOST"), "workspace_emulator_refused")
                from google.cloud import storage

                reader = ReceiptStorage(storage.Client().bucket(BUCKET))
                evidence.update(asyncio.run(asyncio.wait_for(collect(canary, reader), COLLECTION_TIMEOUT_SECONDS)))
            except EvidenceError as exc:
                evidence["unverified"] = [str(exc)]
            except (OSError, TimeoutError, ImportError):
                evidence["unverified"] = ["workspace_read_unavailable"]
            except Exception:
                evidence["unverified"] = ["receipt_collection_failed"]
            json.dump(evidence, report_file, indent=2, allow_nan=False)
            report_file.write("\n")
        print(f"STAGED_{page_cap}_RECEIPT_EVIDENCE_SAVED verified={str(evidence['receipt_evidence_verified']).lower()}")
        return 0 if evidence["receipt_evidence_verified"] else 1
    except EvidenceError as exc:
        print(f"STAGED_{page_cap}_RECEIPT_EVIDENCE_BLOCKED: {exc}", file=sys.stderr)
    except (OSError, TypeError, ValueError):
        print(f"STAGED_{page_cap}_RECEIPT_EVIDENCE_BLOCKED: input_or_output_unavailable", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_main())
