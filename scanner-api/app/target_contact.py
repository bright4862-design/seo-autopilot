"""Bound each staged worker's target HTTP requests to a coordinator grant."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Callable

import httpx

from .finalize_probe_guard import FINALIZE_OPTIONAL_PROBES_UNAVAILABLE, FINALIZE_RATE_LIMITED, FinalizeProbeSuppressed
from .target_cooldown import TargetCooldownActive, explicit_http_origin, explicit_retry_after


DEFAULT_RETRY_AFTER_SECONDS = 30


class TargetContactRetry(RuntimeError):
    """A site was not contacted because access could not be granted."""

    def __init__(self, reason: str, retry_after: int = 10):
        super().__init__(reason)
        self.reason = reason
        self.retry_after = max(1, retry_after)


@dataclass
class OriginContact:
    stop_at: float = 0
    in_flight: int = 0
    drained_at: int = 0
    observation: dict[str, Any] | None = None


class TargetContacts:
    def __init__(self, *, delivery_id: str, cutoff: int, send: Callable | None, clock: Callable[[], float]):
        self.delivery_id, self.cutoff, self.send, self.clock = delivery_id, cutoff, send, clock
        self.contacts: dict[str, OriginContact] = {}
        self.failure: TargetContactRetry | None = None
        self.closed = False
        self.lock = asyncio.Lock()

    def require_contact_enabled(self):
        if self.send is None:
            raise FinalizeProbeSuppressed(FINALIZE_OPTIONAL_PROBES_UNAVAILABLE)
        if self.failure:
            raise self.failure
        if self.closed:
            raise TargetContactRetry("target_contact_closed")

    def _retry(self, reason: str, retry_after: int = 10):
        self.failure = TargetContactRetry(reason, retry_after)
        raise self.failure

    async def _control(self, action: str, origin: str, **fields):
        return await self.send(action, {"delivery_id": self.delivery_id, "target_origin": origin, **fields})

    async def _acquire(self, origin: str):
        # A second caller in the same delivery can reuse the first grant.
        async with self.lock:
            self.require_contact_enabled()
            existing = self.contacts.get(origin)
            if existing is not None:
                return existing
            if self.clock() >= self.cutoff:
                self._retry("target_contact_cutoff")
            contact = self.contacts[origin] = OriginContact()
            started = asyncio.get_running_loop().time()
            reply = await self._control("acquire_target_contact", origin, delivery_cutoff=self.cutoff)
            body = reply["body"]
            seconds = body.get("seconds_remaining")
            if (reply["status_code"] == 200 and body.get("success") is True and body.get("outcome") == "acquired"
                    and type(seconds) is int and 0 < seconds <= 420):
                # Anchor at the request start and subtract one second for
                # second-resolution clocks. Transit time never extends access.
                contact.stop_at = started + seconds - 1
                return contact
            if 400 <= reply["status_code"] < 500:
                # A definitive refusal did not create a grant. Keep unknown
                # outcomes so a lost acknowledgement can still be settled.
                del self.contacts[origin]
            code = body.get("error_code")
            if reply["status_code"] == 429 and code == "target_cooldown_active":
                raise TargetCooldownActive(FINALIZE_RATE_LIMITED)
            delay = body.get("retry_after_seconds")
            self._retry(code if code in {"target_contact_busy", "target_contact_unconfirmed"} else "target_contact_unavailable",
                        delay if type(delay) is int and delay > 0 else 10)

    @asynccontextmanager
    async def request(self, logical_url: httpx.URL):
        self.require_contact_enabled()
        origin = explicit_http_origin(logical_url)
        if not origin:
            self._retry("target_contact_unavailable")
        contact = self.contacts.get(origin)
        if contact is None or not contact.stop_at:
            contact = await self._acquire(origin)
        self.require_contact_enabled()
        observation = contact.observation
        if observation and observation["observed_at"] + observation["retry_after_seconds"] > self.clock():
            raise TargetCooldownActive(FINALIZE_RATE_LIMITED)
        if asyncio.get_running_loop().time() >= contact.stop_at:
            self._retry("target_contact_cutoff")
        contact.in_flight += 1
        try:
            async with asyncio.timeout_at(contact.stop_at):
                yield
        finally:
            contact.in_flight -= 1
            if not contact.in_flight:
                contact.drained_at = int(self.clock())

    def observe_response(self, logical_url: httpx.URL, response: httpx.Response) -> bool:
        if response.status_code != 429:
            return False
        contact = self.contacts[explicit_http_origin(logical_url)]
        now = int(self.clock())
        values = response.headers.get_list("retry-after")
        delay = explicit_retry_after(values[0], now) if len(values) == 1 else 0
        observation = {
            "status_code": 429, "observed_at": now, "retry_after_seconds": delay or DEFAULT_RETRY_AFTER_SECONDS,
            "expires_source": "retry_after" if delay else "default",
        }
        old = contact.observation
        if old is None or now + observation["retry_after_seconds"] > old["observed_at"] + old["retry_after_seconds"]:
            contact.observation = observation
        return True

    async def _settle(self, origin: str, contact: OriginContact, drained_at: int):
        receipt = {"drained_at": drained_at, "observation": contact.observation}
        for _ in range(2):
            reply = await self._control("settle_target_contact", origin, receipt=receipt)
            if reply["status_code"] < 500:
                return

    async def close(self):
        self.closed = True
        if not self.contacts:
            return
        drained_at = int(self.clock())
        # Never claim that an outliving request has drained. Its durable gate
        # protects the origin even if this worker or its receipt is lost.
        limit = asyncio.Semaphore(8)

        async def settle(origin, contact):
            async with limit:
                await self._settle(origin, contact, contact.drained_at or drained_at)

        await asyncio.gather(*(
            settle(origin, contact) for origin, contact in self.contacts.items() if not contact.in_flight
        ))


active_target_contacts: ContextVar[TargetContacts | None] = ContextVar("active_target_contacts", default=None)


@asynccontextmanager
async def target_contact_scope(contacts: TargetContacts | None):
    token = active_target_contacts.set(contacts)
    try:
        yield
    finally:
        active_target_contacts.reset(token)
        if contacts is not None:
            await contacts.close()
