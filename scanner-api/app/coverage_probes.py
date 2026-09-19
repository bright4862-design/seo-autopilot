from __future__ import annotations

import asyncio
import hashlib
import time
from collections import defaultdict
from typing import Any

from .security import safe_get_once


COVERAGE_PROBE_SCHEDULER_VERSION = "coverage_probe_scheduler_v1_shared_request_budget"
LINK_INTEGRITY_PROBE_VERSION = "link_integrity_probe_v1_unsampled_same_site"
MAX_PROBE_OBSERVATION_SAMPLES = 40

_REQUEST_LIMITS = {
    "basic": 4,
    "quick": 6,
    "deep": 12,
    "advanced": 18,
}


def coverage_probe_request_limit(scan_mode: str) -> int:
    return int(_REQUEST_LIMITS.get(str(scan_mode or "advanced").lower(), _REQUEST_LIMITS["advanced"]))


def _bounded_text_list(values: Any, limit: int = 8, width: int = 500) -> list[str]:
    out: list[str] = []
    for value in values if isinstance(values, (list, tuple)) else []:
        clean = str(value or "").strip()[:width]
        if clean and clean not in out:
            out.append(clean)
        if len(out) >= limit:
            break
    return out


def _evidence_ref(purpose: str, url: str, state: str, status_code: int) -> str:
    digest = hashlib.sha256(
        f"{purpose}\x1f{url}\x1f{state}\x1f{int(status_code or 0)}".encode("utf-8")
    ).hexdigest()[:24]
    return f"{COVERAGE_PROBE_SCHEDULER_VERSION}:{digest}"


class SharedCoverageProbeScheduler:
    """One finite request pool for Stage-2 follow-up checks.

    Assessed-page crawling owns its existing page cap. Follow-up probes are
    separate evidence and can only spend the smaller of the declared probe
    allowance and the crawler's remaining finite frontier-request ceiling.
    Actual HTTP identities are cached so two purposes (or two redirect chains)
    do not spend the budget twice for the same request URL.
    """

    def __init__(
        self,
        *,
        max_probe_requests: int,
        shared_request_limit: int,
        initial_request_count: int,
        deadline: float,
    ) -> None:
        self.max_probe_requests = max(0, int(max_probe_requests or 0))
        self.shared_request_limit = max(0, int(shared_request_limit or 0))
        self.initial_request_count = max(0, int(initial_request_count or 0))
        self.deadline = float(deadline or 0.0)
        self.started_at = time.monotonic()
        self.requests_consumed = 0
        self.reused_requests = 0
        self.deadline_exhausted = False
        self.budget_exhausted = False
        self._response_cache: dict[str, Any] = {}
        self._candidates: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        self._stats: dict[str, dict[str, int]] = defaultdict(
            lambda: {
                "eligible": 0,
                "selected": 0,
                "attempted": 0,
                "completed": 0,
                "passed": 0,
                "failed": 0,
                "not_verified": 0,
                "skipped": 0,
                "exhausted": 0,
            }
        )
        self._observations: list[dict[str, Any]] = []

    def register(
        self,
        *,
        purpose: str,
        url: str,
        source_pages: Any = None,
        link_text_samples: Any = None,
    ) -> None:
        purpose = str(purpose or "").strip()
        url = str(url or "").strip()
        if not purpose or not url:
            return
        existing = self._candidates[purpose].get(url)
        if existing is None:
            self._candidates[purpose][url] = {
                "url": url,
                "source_pages": _bounded_text_list(source_pages),
                "link_text_samples": _bounded_text_list(link_text_samples),
            }
            self._stats[purpose]["eligible"] += 1
            return
        existing["source_pages"] = _bounded_text_list(
            [*existing.get("source_pages", []), *_bounded_text_list(source_pages)]
        )
        existing["link_text_samples"] = _bounded_text_list(
            [*existing.get("link_text_samples", []), *_bounded_text_list(link_text_samples)]
        )

    def candidates(self, purpose: str) -> list[dict[str, Any]]:
        rows = self._candidates.get(str(purpose or ""), {})
        return [dict(rows[url]) for url in sorted(rows)]

    def _request_capacity_available(self) -> bool:
        if self.deadline and time.monotonic() >= self.deadline:
            self.deadline_exhausted = True
            return False
        if self.requests_consumed >= self.max_probe_requests:
            self.budget_exhausted = True
            return False
        if self.initial_request_count + self.requests_consumed >= self.shared_request_limit:
            self.budget_exhausted = True
            return False
        return True

    def can_start_candidate(self, purpose: str, url: str) -> bool:
        del purpose
        if str(url or "") in self._response_cache:
            return True
        return self._request_capacity_available()

    def begin_candidate(self, purpose: str) -> None:
        stats = self._stats[str(purpose or "")]
        stats["selected"] += 1
        stats["attempted"] += 1

    async def fetch_once(self, client, url: str, *, max_decoded_bytes: int | None = None):
        request_url = str(url or "").strip()
        if request_url in self._response_cache:
            self.reused_requests += 1
            return self._response_cache[request_url]
        if not self._request_capacity_available():
            raise RuntimeError(
                "coverage_probe_deadline_exhausted"
                if self.deadline_exhausted
                else "coverage_probe_request_budget_exhausted"
            )
        # Spend the permit before I/O. A timeout/transport failure still consumed
        # a real outbound request and therefore still counts against the bound.
        self.requests_consumed += 1
        remaining = None if not self.deadline else self.deadline - time.monotonic()
        if remaining is not None and remaining <= 0:
            self.deadline_exhausted = True
            raise RuntimeError("coverage_probe_deadline_exhausted")
        try:
            request = safe_get_once(
                client,
                request_url,
                max_decoded_bytes=max_decoded_bytes,
            )
            response = (
                await request
                if remaining is None
                else await asyncio.wait_for(request, timeout=max(0.1, remaining))
            )
        except asyncio.TimeoutError as exc:
            self.deadline_exhausted = True
            raise RuntimeError("coverage_probe_deadline_exhausted") from exc
        if response is not None:
            self._response_cache[request_url] = response
        return response

    def record_exhausted(self, purpose: str, url: str, *, source_pages: Any = None, link_text_samples: Any = None) -> None:
        purpose = str(purpose or "")
        self._stats[purpose]["exhausted"] += 1
        self._observations_append({
            "purpose": purpose,
            "version": LINK_INTEGRITY_PROBE_VERSION if purpose == "internal_link" else COVERAGE_PROBE_SCHEDULER_VERSION,
            "state": "not_verified",
            "reason": "deadline_exhausted" if self.deadline_exhausted else "request_budget_exhausted",
            "observed_url": str(url or ""),
            "status_code": 0,
            "final_url": "",
            "source_pages": _bounded_text_list(source_pages),
            "link_text_samples": _bounded_text_list(link_text_samples),
        })

    def record_skipped(
        self,
        purpose: str,
        url: str,
        *,
        reason: str,
        source_pages: Any = None,
        link_text_samples: Any = None,
    ) -> None:
        purpose = str(purpose or "")
        self._stats[purpose]["skipped"] += 1
        self._observations_append({
            "purpose": purpose,
            "version": LINK_INTEGRITY_PROBE_VERSION if purpose == "internal_link" else COVERAGE_PROBE_SCHEDULER_VERSION,
            "state": "not_verified",
            "reason": str(reason or "")[:220],
            "observed_url": str(url or "")[:2_000],
            "status_code": 0,
            "final_url": "",
            "source_pages": _bounded_text_list(source_pages),
            "link_text_samples": _bounded_text_list(link_text_samples),
        })

    def record_result(
        self,
        purpose: str,
        url: str,
        *,
        state: str,
        reason: str,
        status_code: int = 0,
        final_url: str = "",
        source_pages: Any = None,
        link_text_samples: Any = None,
    ) -> None:
        purpose = str(purpose or "")
        state = str(state or "not_verified")
        stats = self._stats[purpose]
        stats["completed"] += 1
        if state == "pass":
            stats["passed"] += 1
        elif state == "fail":
            stats["failed"] += 1
        elif state == "not_verified":
            stats["not_verified"] += 1
        else:
            stats["skipped"] += 1
        self._observations_append({
            "purpose": purpose,
            "version": LINK_INTEGRITY_PROBE_VERSION if purpose == "internal_link" else COVERAGE_PROBE_SCHEDULER_VERSION,
            "state": state,
            "reason": str(reason or "")[:220],
            "observed_url": str(url or "")[:2_000],
            "status_code": max(0, int(status_code or 0)),
            "final_url": str(final_url or "")[:2_000],
            "source_pages": _bounded_text_list(source_pages),
            "link_text_samples": _bounded_text_list(link_text_samples),
        })

    def _observations_append(self, observation: dict[str, Any]) -> None:
        if len(self._observations) >= MAX_PROBE_OBSERVATION_SAMPLES:
            return
        observation = dict(observation)
        observation["evidence_ref"] = _evidence_ref(
            observation.get("purpose", ""),
            observation.get("observed_url", ""),
            observation.get("state", ""),
            int(observation.get("status_code") or 0),
        )
        self._observations.append(observation)

    def summary(self) -> dict[str, Any]:
        remaining_probe = max(0, self.max_probe_requests - self.requests_consumed)
        remaining_shared = max(
            0,
            self.shared_request_limit - self.initial_request_count - self.requests_consumed,
        )
        return {
            "version": COVERAGE_PROBE_SCHEDULER_VERSION,
            "request_budget": {
                "configured_probe_requests": self.max_probe_requests,
                "shared_request_limit": self.shared_request_limit,
                "crawl_requests_consumed": self.initial_request_count,
                "requests_consumed": self.requests_consumed,
                "requests_reused": self.reused_requests,
                "requests_remaining": min(remaining_probe, remaining_shared),
                "budget_exhausted": self.budget_exhausted,
                "deadline_exhausted": self.deadline_exhausted,
                "time_budget_seconds": round(max(0.0, self.deadline - self.started_at), 3) if self.deadline else None,
            },
            "purposes": {
                purpose: dict(stats)
                for purpose, stats in sorted(self._stats.items())
            },
            "observations": list(self._observations),
            "observation_samples_truncated": sum(
                int(stats.get("completed") or 0) + int(stats.get("exhausted") or 0)
                for stats in self._stats.values()
            ) > len(self._observations),
        }
