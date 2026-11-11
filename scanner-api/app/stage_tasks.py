"""Worker-owned, pinned Cloud Tasks dispatch for a sequential scan chain."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from typing import Any
from urllib.parse import urlparse


STAGE_ROUTES = {"batch": "/scan-batch", "finalize": "/scan-finalize"}


def stage_task_id(job: dict[str, Any], stage: str, batch: int) -> str:
    if stage not in STAGE_ROUTES or isinstance(batch, bool) or int(batch) < 0:
        raise ValueError("Invalid scan stage")
    identity = f"{job['scan_id']}:{int(job.get('attempt_count') or 1)}:{stage}:{int(batch)}"
    return "scan-" + hashlib.sha256(identity.encode()).hexdigest()


class StageTaskDispatcher:
    def __init__(self, queue_path: str, worker_url: str, invoker: str, *, client: Any = None):
        if not re.fullmatch(r"projects/[A-Za-z0-9:._-]+/locations/[a-z0-9-]+/queues/[A-Za-z0-9_-]+", queue_path):
            raise RuntimeError("A stage queue path is required")
        parsed = urlparse(worker_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.path not in {"", "/"} or parsed.query or parsed.fragment or parsed.username:
            raise RuntimeError("A pinned HTTPS worker origin is required")
        if not invoker or "@" not in invoker:
            raise RuntimeError("The task invoker service account is required")
        self.queue_path, self.worker_url, self.invoker = queue_path, worker_url.rstrip("/"), invoker
        self.client = client

    async def enqueue(self, job: dict[str, Any], stage: str, batch: int, *, limited: bool = False, not_before: float | None = None) -> None:
        task_id = stage_task_id(job, stage, batch)
        task = {
            "name": f"{self.queue_path}/tasks/{task_id}",
            "dispatch_deadline": {"seconds": 480},
            "http_request": {
                "http_method": 1,
                "url": self.worker_url + STAGE_ROUTES[stage],
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({**job, "batch": int(batch), "limited": bool(limited)}, sort_keys=True).encode(),
                "oidc_token": {"service_account_email": self.invoker, "audience": self.worker_url},
            },
        }
        if not_before is not None:
            task["schedule_time"] = {"seconds": int(not_before), "nanos": int((not_before % 1) * 1_000_000_000)}
        def create():
            from google.api_core.exceptions import AlreadyExists
            from google.cloud import tasks_v2
            client = self.client or tasks_v2.CloudTasksClient()
            try:
                client.create_task(request={"parent": self.queue_path, "task": task}, timeout=20, retry=None)
            except AlreadyExists:
                pass
        await asyncio.to_thread(create)


def configured_dispatcher() -> StageTaskDispatcher:
    queue_path = str(os.getenv("SCAN_STAGE_TASKS_QUEUE_PATH") or os.getenv("SCAN_STAGE_QUEUE_PATH") or "")
    if not queue_path and all(os.getenv(name) for name in ("SCAN_TASKS_PROJECT", "SCAN_TASKS_LOCATION", "SCAN_STAGE_QUEUE")):
        queue_path = f"projects/{os.environ['SCAN_TASKS_PROJECT']}/locations/{os.environ['SCAN_TASKS_LOCATION']}/queues/{os.environ['SCAN_STAGE_QUEUE']}"
    return StageTaskDispatcher(
        queue_path,
        str(os.getenv("SCAN_STAGE_TARGET_URL") or os.getenv("SCAN_STAGE_WORKER_URL") or ""),
        str(os.getenv("TASKS_INVOKER_SERVICE_ACCOUNT") or ""),
    )
