"""Private attempt workspaces with explicit optimistic concurrency.

Only frontier references are authoritative. Interrupted writes are immutable
orphans and can never be mistaken for a committed batch by a retry.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import os
import re
import threading
from dataclasses import dataclass
from typing import Any


class WorkspaceConflict(RuntimeError):
    """The expected object generation no longer owns the write."""


class WorkspaceUnavailable(RuntimeError):
    """Workspace storage is not available; the delivery must be retried."""


@dataclass(frozen=True)
class WorkspaceObject:
    value: dict[str, Any]
    generation: int


def attempt_prefix(scan_id: str, attempt: int) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", str(scan_id or "")):
        raise ValueError("Invalid workspace scan identity")
    if isinstance(attempt, bool) or int(attempt) < 1:
        raise ValueError("Invalid workspace attempt")
    return f"scans/{scan_id}/a{int(attempt)}/"


def _encode(value: dict[str, Any]) -> bytes:
    return gzip.compress(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(), mtime=0)


class GCSWorkspace:
    """Storage SDK calls run off the event loop and use bounded RPCs."""

    def __init__(self, bucket_name: str, *, client: Any = None):
        if not bucket_name or "/" in bucket_name:
            raise WorkspaceUnavailable("A private scan workspace bucket is required")
        if client is None:
            from google.cloud import storage
            client = storage.Client()
        self.bucket = client.bucket(bucket_name)

    async def read(self, key: str) -> WorkspaceObject | None:
        def download():
            from google.api_core.exceptions import NotFound, PreconditionFailed
            blob = self.bucket.blob(key)
            try:
                blob.reload(timeout=20, retry=None)
                generation = int(blob.generation)
                raw = blob.download_as_bytes(if_generation_match=generation, timeout=20, retry=None)
            except NotFound:
                return None
            except PreconditionFailed as exc:
                raise WorkspaceConflict("Workspace changed while reading") from exc
            return WorkspaceObject(json.loads(gzip.decompress(raw)), generation)
        try:
            return await asyncio.to_thread(download)
        except (WorkspaceConflict, WorkspaceUnavailable):
            raise
        except Exception as exc:
            raise WorkspaceUnavailable("Workspace read failed") from exc

    async def write(self, key: str, value: dict[str, Any], *, generation: int = 0) -> int:
        raw = _encode(value)
        def upload():
            from google.api_core.exceptions import PreconditionFailed
            blob = self.bucket.blob(key)
            try:
                blob.upload_from_string(raw, content_type="application/gzip", if_generation_match=generation, timeout=20, retry=None)
            except PreconditionFailed as exc:
                raise WorkspaceConflict("Workspace generation was superseded") from exc
            return int(blob.generation)
        try:
            return await asyncio.to_thread(upload)
        except WorkspaceConflict:
            raise
        except Exception as exc:
            raise WorkspaceUnavailable("Workspace write failed") from exc

    async def delete_prefix(self, prefix: str) -> None:
        def delete():
            for blob in self.bucket.list_blobs(prefix=prefix, timeout=20, retry=None):
                blob.delete(if_generation_match=blob.generation, timeout=20, retry=None)
        try:
            await asyncio.to_thread(delete)
        except Exception as exc:
            raise WorkspaceUnavailable("Workspace deletion failed") from exc

    async def keys(self, prefix: str) -> list[str]:
        try:
            return await asyncio.to_thread(lambda: [blob.name for blob in self.bucket.list_blobs(prefix=prefix, timeout=20, retry=None)])
        except Exception as exc:
            raise WorkspaceUnavailable("Workspace listing failed") from exc


class MemoryWorkspace:
    """Generation-accurate test store; production never falls back to memory."""

    def __init__(self):
        self.objects: dict[str, tuple[bytes, int]] = {}
        self.sequence = 0
        self.lock = threading.Lock()

    async def read(self, key: str) -> WorkspaceObject | None:
        with self.lock:
            stored = self.objects.get(key)
            return WorkspaceObject(json.loads(gzip.decompress(stored[0])), stored[1]) if stored else None

    async def write(self, key: str, value: dict[str, Any], *, generation: int = 0) -> int:
        with self.lock:
            current = self.objects.get(key)
            if (current[1] if current else 0) != generation:
                raise WorkspaceConflict("Workspace generation was superseded")
            self.sequence += 1
            self.objects[key] = (_encode(value), self.sequence)
            return self.sequence

    async def delete_prefix(self, prefix: str) -> None:
        with self.lock:
            self.objects = {key: value for key, value in self.objects.items() if not key.startswith(prefix)}

    async def keys(self, prefix: str) -> list[str]:
        with self.lock:
            return sorted(key for key in self.objects if key.startswith(prefix))


def configured_workspace() -> GCSWorkspace:
    return GCSWorkspace(str(os.getenv("SCAN_WORKSPACE_BUCKET") or ""))
