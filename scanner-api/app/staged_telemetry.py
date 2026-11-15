"""Private observations of leased scan stages, independent of the signed result."""

from __future__ import annotations

import asyncio
import json
import os
import re
import threading
import time
from contextvars import ContextVar
from hashlib import sha256
from pathlib import Path
from typing import Any

from .acceptance_evidence import measure_worker_peak_memory_bytes
from .beta_revision import live_revision
from .workspace import WorkspaceConflict, WorkspaceUnavailable


RECEIPT_VERSION = "staged_delivery_receipt_v1"
RECEIPT_WRITE_SECONDS = 2.0
RSS_SAMPLE_SECONDS = 0.2
# Covers ten Cloud Tasks attempts for plan, ten batches and finalize with
# room for short rate-limited batches. Scan work continues on overflow.
MAX_RECORDED_DELIVERIES = 256
COMPLETION_FUNCTIONS = frozenset({"persistDurableScanAuthorityV9", "persistLimitedScanResultV9"})


def _valid_env(name: str, pattern: str) -> str | None:
    value = os.getenv(name, "")
    return value if re.fullmatch(pattern, value) else None


def _runtime_identity() -> dict:
    try:
        fingerprint = live_revision()["fingerprint"]
    except (OSError, ValueError, RuntimeError):
        fingerprint = None
    mode = os.getenv("SCAN_PIPELINE_MODE") or "monolith"
    raw_cohort = os.getenv("SCAN_STAGED_OWNER_IDS") or os.getenv("SCAN_PIPELINE_OWNER_IDS") or ""
    owners = sorted({owner.strip() for owner in raw_cohort.split(",") if owner.strip()})
    cohort_hash = None
    if len(owners) <= 5 and all(re.fullmatch(r"[A-Za-z0-9_-]{6,64}", owner) for owner in owners):
        cohort_hash = sha256(json.dumps(owners, separators=(",", ":")).encode()).hexdigest()
    return {
        "source_sha": _valid_env("FIXLIST_WORKER_SOURCE_SHA", r"[a-f0-9]{40}"),
        "revision": _valid_env("K_REVISION", r"[a-z0-9-]{1,63}"),
        "service": _valid_env("K_SERVICE", r"[a-z0-9-]{1,63}"),
        "staged_config_sha256": _valid_env("FIXLIST_STAGED_CONFIG_SHA256", r"[a-f0-9]{64}"),
        "release_fingerprint": fingerprint,
        "pipeline_mode": mode.lower() if mode.lower() in {"monolith", "staged"} else None,
        "staged_owner_cohort_sha256": cohort_hash,
    }


def _kernel_memory_bound() -> dict | None:
    """The cgroup lifetime peak includes other work on the same instance."""
    try:
        memberships = Path("/proc/self/cgroup").read_text().splitlines()
    except OSError:
        return None
    # Only claim a value when the process belongs to the exposed mount root.
    # A different layout remains unmeasured instead of reading a sibling's peak.
    if "0::/" in memberships:
        directory, peak_name, limit_name = Path("/sys/fs/cgroup"), "memory.peak", "memory.max"
    elif any(line.split(":")[1:] == ["memory", "/"] for line in memberships):
        directory = Path("/sys/fs/cgroup/memory")
        peak_name, limit_name = "memory.max_usage_in_bytes", "memory.limit_in_bytes"
    else:
        return None
    members_file = directory / "cgroup.procs"
    try:
        if str(os.getpid()) not in members_file.read_text().splitlines():
            return None
    except OSError:
        return None

    def read_positive(name: str) -> int | None:
        try:
            value = int((directory / name).read_text().strip())
        except (OSError, ValueError):
            return None
        return value if 0 < value < 2**60 else None

    peak = read_positive(peak_name)
    if peak is None:
        return None
    return {"scope": "cgroup_lifetime", "peak_bytes": peak, "limit_bytes": read_positive(limit_name)}


class DeliveryReceipt:
    """Collect bounded observations for one acquired frontier lease."""

    def __init__(
        self, store: Any, prefix: str, job: dict, stage: str, batch: int, lease_owner: str, lease_generation: int,
    ):
        self.store, self.prefix = store, prefix
        self.started_ref = f"receipts/{lease_owner}.started.json.gz"
        self.finished_ref = f"receipts/{lease_owner}.finished.json.gz"
        self.started_at = time.monotonic()
        request_id = job.get("request_id")
        self.identity = {
            "schema_version": RECEIPT_VERSION,
            "delivery_id": lease_owner,
            "lease_generation": str(lease_generation),
            "scan_id": job["scan_id"],
            "attempt": int(job.get("attempt_count") or 1),
            "request_id_sha256": sha256(request_id.encode()).hexdigest() if isinstance(request_id, str) and request_id else None,
            "scan_mode": job["scan_mode"],
            "page_cap": job["page_cap"],
            "stage": stage,
            "batch": batch,
            "started_at_unix_ms": time.time_ns() // 1_000_000,
            "runtime": _runtime_identity(),
        }
        self.artifacts: dict[str, dict] = {}
        self.stage_committed = False
        self.completion_request: dict | None = None
        self.parent_peak: int | None = None
        self.parent_samples = 0
        self.review_peak: int | None = None
        self.review_samples = 0
        self.sample_lock = threading.Lock()
        self.stopped = threading.Event()
        self.sampling_thread = threading.Thread(target=self._sample_parent, daemon=True)
        self.started_write: asyncio.Task | None = None

    async def _write(self, reference: str, value: dict) -> None:
        try:
            await asyncio.wait_for(
                self.store.write(self.prefix + reference, value, generation=0),
                timeout=RECEIPT_WRITE_SECONDS,
            )
        except (WorkspaceConflict, WorkspaceUnavailable, TimeoutError):
            # The scan's existing durable writes remain the recovery authority.
            pass

    def _read_parent(self) -> None:
        value = measure_worker_peak_memory_bytes()
        if value is not None:
            with self.sample_lock:
                self.parent_peak = max(self.parent_peak or 0, value)
                self.parent_samples += 1

    def _sample_parent(self) -> None:
        while not self.stopped.wait(RSS_SAMPLE_SECONDS):
            self._read_parent()

    def stop_sampling(self) -> None:
        self.stopped.set()

    def start(self) -> None:
        self._read_parent()
        try:
            self.sampling_thread.start()
        except RuntimeError:
            # Leave sample counts truthful if a worker cannot start the sampler.
            pass
        self.started_write = asyncio.create_task(self._write(self.started_ref, self.identity))

    def observe_artifact(self, name: str, generation: int, *, produced: bool) -> None:
        # GCS generations may exceed the integer precision of a JS consumer.
        self.artifacts[name] = {"generation": str(generation), "produced": produced}

    def observe_review_memory(self, value: int | None) -> None:
        if value is not None:
            with self.sample_lock:
                self.review_peak = max(self.review_peak or 0, value)
                self.review_samples += 1

    def observe_completion_request(self, function: str, content: bytes) -> None:
        self.completion_request = {
            "function": function,
            "body_bytes": len(content),
            "body_sha256": sha256(content).hexdigest(),
            "status_code": None,
        }

    def observe_completion_response(self, status_code: int) -> None:
        if self.completion_request is not None:
            self.completion_request["status_code"] = status_code

    async def finish(self, *, deadline: float = float("inf")) -> None:
        if deadline - time.monotonic() <= RECEIPT_WRITE_SECONDS:
            if self.started_write is not None:
                self.started_write.cancel()
            return
        self._read_parent()
        with self.sample_lock:
            memory = {
                "parent_rss_peak_bytes": self.parent_peak,
                "parent_rss_samples": self.parent_samples,
                "parent_and_review_child_rss_peak_bytes": self.review_peak,
                "parent_and_review_child_rss_samples": self.review_samples,
            }
        memory["cgroup"] = _kernel_memory_bound()
        receipt = {
            **self.identity,
            "finished_at_unix_ms": time.time_ns() // 1_000_000,
            "elapsed_ms": int((time.monotonic() - self.started_at) * 1000),
            "stage_committed": self.stage_committed,
            "artifacts": self.artifacts.copy(),
            "memory": memory,
            "completion_request": self.completion_request,
        }
        if self.started_write is not None:
            await self.started_write
        if deadline - time.monotonic() > RECEIPT_WRITE_SECONDS:
            await self._write(self.finished_ref, receipt)


active_delivery: ContextVar[DeliveryReceipt | None] = ContextVar("active_staged_delivery", default=None)
