"""Relay a verified target's Retry-After from the existing staged attempt."""

from __future__ import annotations

import asyncio
import ipaddress
import re
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable

import httpx

from .finalize_probe_guard import FINALIZE_RATE_LIMITED, FinalizeProbeSuppressed
from .workspace import WorkspaceConflict, WorkspaceUnavailable


MAX_RETRY_AFTER_SECONDS = 86_400
OUTBOX_VERSION = "staged_target_cooldown_v1"
_HTTP_DATE = re.compile(
    r"(?:[A-Z][a-z]{2}, [0-9]{2} [A-Z][a-z]{2} [0-9]{4} [0-9]{2}:[0-9]{2}:[0-9]{2} GMT"
    r"|[A-Z][a-z]+, [0-9]{2}-[A-Z][a-z]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2} GMT"
    r"|[A-Z][a-z]{2} [A-Z][a-z]{2} (?:[0-9]{2}| [0-9]) [0-9]{2}:[0-9]{2}:[0-9]{2} [0-9]{4})"
)


def explicit_http_origin(value: str | httpx.URL) -> str:
    """Use the ASCII logical hostname and its exact scheme and effective port."""
    try:
        url = value if isinstance(value, httpx.URL) else httpx.URL(value)
        if url.scheme not in {"http", "https"} or url.username or url.password:
            return ""
        host = url.raw_host.decode("ascii").lower()
        port = url.port if url.port is not None else (443 if url.scheme == "https" else 80)
        if not host or not 1 <= port <= 65_535:
            return ""
        if ":" in host:
            host = f"[{ipaddress.IPv6Address(host).compressed}]"
        return f"{url.scheme}://{host}:{port}"
    except (httpx.InvalidURL, TypeError, ValueError, UnicodeError):
        return ""


def explicit_retry_after(raw: str, observed_at: int) -> int:
    value = raw.strip(" \t")
    if re.fullmatch(r"[0-9]+", value):
        digits = value.lstrip("0")
        if not digits:
            return 0
        if len(digits) > len(str(MAX_RETRY_AFTER_SECONDS)):
            return MAX_RETRY_AFTER_SECONDS
        return min(int(digits), MAX_RETRY_AFTER_SECONDS)
    if not _HTTP_DATE.fullmatch(value):
        return 0
    try:
        date = parsedate_to_datetime(value)
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        return max(0, min(int(date.timestamp()) - observed_at, MAX_RETRY_AFTER_SECONDS))
    except (OverflowError, OSError, TypeError, ValueError):
        return 0


class TargetCooldownPending(RuntimeError):
    """The exact observation must be replayed before the stage can progress."""


class TargetCooldownActive(FinalizeProbeSuppressed):
    """A request was not sent because this exact origin is still paused."""


class TargetCooldownRelay:
    """A generation-fenced outbox in the existing staged attempt workspace."""

    def __init__(self, store: Any, prefix: str, origin: str, publish: Callable, clock: Callable[[], float], *, optional: bool = False):
        self.store = store
        self.key = prefix + "target-cooldown.json"
        self.origin = origin
        self.publish = publish
        self.clock = clock
        self.optional = optional
        self.lock = asyncio.Lock()
        self.tasks: set[asyncio.Task[None]] = set()
        self.generation = 0
        self.record: dict | None = None
        self.unsaved: dict | None = None
        self.failed = False

    @staticmethod
    def _expires(observation: dict) -> int:
        return observation["observed_at"] + observation["retry_after_seconds"]

    def _valid_record(self, value: Any) -> bool:
        if not isinstance(value, dict) or value.get("version") != OUTBOX_VERSION:
            return False
        observation = value.get("observation")
        return (
            isinstance(observation, dict)
            and set(observation) == {"status_code", "target_origin", "observed_at", "retry_after_seconds"}
            and type(observation["status_code"]) is int and observation["status_code"] == 429
            and observation["target_origin"] == self.origin
            and type(observation["observed_at"]) is int and observation["observed_at"] > 0
            and type(observation["retry_after_seconds"]) is int
            and 0 < observation["retry_after_seconds"] <= MAX_RETRY_AFTER_SECONDS
            and type(value.get("pending")) is bool
            and type(value.get("hold_until")) is int
            and 0 <= value["hold_until"] <= self._expires(observation)
        )

    async def _write(self, record: dict) -> None:
        # Retain the strongest observed signal even if the first checkpoint
        # write failed. A later delivery reuses only generation-fenced evidence.
        self.unsaved = record
        self.generation = await self.store.write(self.key, record, generation=self.generation)
        self.record, self.unsaved = record, None

    async def _acknowledge(self) -> None:
        record = self.record
        if record is None or not record["pending"]:
            return
        observation = record["observation"]
        expiry = self._expires(observation)
        if expiry > self.clock() and await self.publish(observation) is not True:
            raise TargetCooldownPending("The target cooldown publication is pending")
        hold_until = expiry
        await self._write({**record, "pending": False, "hold_until": hold_until})

    async def resume(self) -> None:
        stored = await self.store.read(self.key)
        if stored is None:
            return
        if not self._valid_record(stored.value):
            raise TargetCooldownPending("The target cooldown checkpoint could not be verified")
        self.generation, self.record = stored.generation, stored.value
        await self._acknowledge()

    def remaining_hold(self) -> int:
        # Earlier acknowledged checkpoints used hold_until=0. The validated
        # target's original expiry remains binding across those restarts too.
        return max(0, self._expires(self.record["observation"]) - int(self.clock())) if self.record else 0

    async def before_request(self, logical_url: str | httpx.URL) -> None:
        if explicit_http_origin(logical_url) != self.origin:
            return
        # Queue new contacts behind the header observer. In-flight requests
        # might already have been admitted before the 429 reached the worker.
        if self.failed or (self.optional and self.tasks):
            raise TargetCooldownActive(FINALIZE_RATE_LIMITED)
        await self.drain()
        if self.failed:
            raise TargetCooldownActive(FINALIZE_RATE_LIMITED)
        if self.remaining_hold():
            raise TargetCooldownActive(FINALIZE_RATE_LIMITED)

    def observe_response(self, logical_url: httpx.URL, response: httpx.Response) -> asyncio.Event | None:
        if response.status_code != 429 or explicit_http_origin(logical_url) != self.origin:
            return None
        observed_at = int(self.clock())
        values = response.headers.get_list("retry-after")
        delay = explicit_retry_after(values[0], observed_at) if len(values) == 1 else 0
        if not delay or observed_at <= 0:
            return None
        observation = {
            "status_code": 429, "target_origin": self.origin, "observed_at": observed_at,
            "retry_after_seconds": delay,
        }
        # The stage owns publication, outside the target HTTP deadline. The
        # scanner can use the real response headers while the relay is pending.
        closed = asyncio.Event()
        task = asyncio.create_task(self._record_and_publish(observation, closed))
        self.tasks.add(task)
        task.add_done_callback(self._finished)
        return closed

    def _finished(self, task: asyncio.Task[None]) -> None:
        self.tasks.discard(task)
        if task.cancelled() or task.exception() is not None:
            self.failed = True

    async def _record_and_publish(self, observation: dict, closed: asyncio.Event) -> None:
        async with self.lock:
            prior = self.unsaved or self.record
            if prior is None or self._expires(observation) > self._expires(prior["observation"]):
                pending = {
                    "version": OUTBOX_VERSION, "observation": observation, "pending": True,
                    "hold_until": self._expires(observation),
                }
                try:
                    await self._write(pending)
                except (WorkspaceConflict, WorkspaceUnavailable):
                    self.failed = True
            await closed.wait()
            if not self.failed:
                try:
                    await self._acknowledge()
                except (TargetCooldownPending, WorkspaceConflict, WorkspaceUnavailable):
                    self.failed = True

    async def drain(self) -> None:
        while self.tasks:
            # A target GET timeout cannot cancel an already scheduled relay.
            await asyncio.shield(asyncio.gather(*self.tasks, return_exceptions=True))

    async def require_acknowledged(self) -> None:
        await self.drain()
        if self.unsaved is not None:
            # Acknowledge writes may fail after the coordinator committed. Keep
            # pending evidence and replay the same observation on redelivery.
            pending = {**self.unsaved, "pending": True}
            await self._write(pending)
        if self.failed or (self.record and self.record["pending"]):
            raise TargetCooldownPending("The target cooldown publication is pending")


active_target_cooldown: ContextVar[TargetCooldownRelay | None] = ContextVar(
    "active_target_cooldown", default=None,
)


@contextmanager
def target_cooldown_scope(relay: TargetCooldownRelay | None):
    token = active_target_cooldown.set(relay)
    try:
        yield
    finally:
        active_target_cooldown.reset(token)
