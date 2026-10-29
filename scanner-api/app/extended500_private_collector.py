"""Private, bounded Extended 500 page collectors -- NOT a product tier.

Two complementary private paths live here (both off, unwired, unreviewed):
1. ``run_private_extended500_collection``: a bounded frontier with injectable
   clock/sleeper, per-host pacing, budgets and reconciled counters (below).
2. ``run_isolated_extended500_collection``: the earlier lane-C candidate that
   runs ``scanner.run_scan`` in a spawned child holding a child-only 500
   budget (section at the end of this module), plus
   ``validate_extended500_collection_result``.

Lane C (issue #384). This module has no HTTP route, queue, worker, Base44
write, entitlement, billing or review. ``main.py`` does not import it. It
produces an *unreviewed* private collection that a future, separately reviewed
persistence protocol may sign through the existing
``build_extended500_evidence_handoff`` (still ``not_reviewed``).

Why this does not call ``scanner.run_scan`` with a 500 budget
-------------------------------------------------------------
``scanner.resolve_scan_budget`` reads the module-global ``SCAN_BUDGETS`` and
falls back to Standard 150 for any unknown mode, and the public ``/scan``
request model forwards a free-form ``scan_mode`` string to ``run_scan``. The
only way to make ``run_scan`` retain 500 pages without editing ``scanner.py``
is to mutate that shared dict (the existing proof test does it with
``monkeypatch``), which concurrent public requests could observe. ``run_scan``
also has no injectable clock, no per-host pacing before a 429, no cross-origin
redirect refusal, no retained-memory budget, and it silently slices ``pages`` to
the budget. This module therefore drives its own bounded frontier through the
production per-page path (``scanner.fetch_and_extract`` ->
``fetch_with_redirect_evidence`` -> ``security.safe_get_once`` ->
``extract_page``), and ``admit_run_scan_result`` passes a run_scan-shaped 500
result (today: the fixture proof) through the same fail-closed gate.

Hard failures vs counted exclusions
-----------------------------------
Hard failure (``success: False``, structured ``error_code``, NO page arrays):
``invalid_request``, ``invalid_limits`` (e.g. capacity 501, deadline above the
120 s job ceiling), ``entry_robots_denied``, ``deadline_before_minimum_evidence``,
``insufficient_evidence``, ``capacity_exceeded`` (an attempt to retain beyond
the authorised capacity, or a >500 run_scan result), ``retained_bytes_budget_exceeded``
(aggregate retained evidence would exceed the memory budget -- fail, never
truncate, like the handoff's 8 MiB signing budget), ``accounting_mismatch``
(counters do not reconcile, e.g. a truncated run_scan result),
``run_scan_result_rejected``.

Counted exclusions (never retained, never followed, run continues): every
bucket in ``EXCLUSION_BUCKETS``. Reconciliation identity, checked before
returning success::

    urls_discovered == pages_retained + sum(excluded) + sum(not_attempted)
    urls_attempted  == pages_retained + sum(excluded) - excluded["robots_denied"]
"""
from __future__ import annotations

import asyncio
import contextlib
import copy
import json
import math
import multiprocessing as mp
import re
import time
from collections import Counter, deque
from dataclasses import asdict, dataclass
from typing import Any, Awaitable, Callable, Mapping
from urllib.parse import urlparse, urlsplit

import httpx

from . import scanner, security
from .artifact_filter import is_artifact_url
from .extended500_evidence_handoff import (
    EXTENDED500_MAX_PAGES,
    EXTENDED500_MODE,
    build_extended500_evidence_handoff,
)
from .extract import classify_template
from .market_scope import market_pair_prefix, path_within_scope
from .page_evidence_gate import page_evidence_class
from .page_output_privacy import project_scan_result_for_external_boundary
from .redirect_validation import DEFAULT_MAX_REDIRECTS
from .robots_policy import (
    SCANNER_USER_AGENT,
    RobotsPolicy,
    annotate_robots_evidence,
    load_robots_policy,
    owner_robots_override,
)
from .sampling import select_balanced_urls
from .scan_timing import allocate_scan_time_budget
from .sitemap import MAX_SITEMAP_FETCHES, load_sitemap_urls
from .stage2_reachability_provenance import (
    MAX_EXTENDED_ASSESSED_PAGES,
    enrich_pages_from_retained_link_evidence,
)
from .url_frontier_policy import classify_frontier_url

EXTENDED500_PRIVATE_COLLECTOR_VERSION = "extended500_private_collector_v1_bounded_unreviewed"
AUTHORISED_CAPACITY = EXTENDED500_MAX_PAGES
if AUTHORISED_CAPACITY != MAX_EXTENDED_ASSESSED_PAGES:  # pragma: no cover - import contract
    raise RuntimeError("Extended 500 capacity constants disagree")

MAX_DEADLINE_SECONDS = float(scanner.ASYNC_JOB_TIMEOUT_CEILING)
MAX_RESPONSE_BYTES_CEILING = int(scanner.MAX_DECODED_RESPONSE_BYTES)
MAX_DISCOVERED_URLS_CEILING = int(scanner.SITEMAP_DISCOVERY_LIMIT)
MAX_REQUESTS_CEILING = AUTHORISED_CAPACITY * 8  # run_scan's shared frontier ceiling
MAX_TOTAL_RETAINED_BYTES_CEILING = 256 * 1024 * 1024
MIN_HOST_INTERVAL_FLOOR_SECONDS = 0.05
MAX_HOST_INTERVAL_SECONDS = float(scanner.RATE_LIMIT_MAX_INTERVAL_SECONDS)
MAX_SEED_URL_CHARS = 2048
MAX_SOURCE_PAGES_PER_URL = 50
MAX_LINK_TEXT_SAMPLES = 8
MAX_EXCLUSION_EXAMPLES = 5
USER_AGENT = "Mozilla/5.0 (compatible; FixListPythonScanner/1.0)"

HARD_FAILURE_CODES = frozenset({
    "invalid_request",
    "invalid_limits",
    "entry_robots_denied",
    "deadline_before_minimum_evidence",
    "insufficient_evidence",
    "capacity_exceeded",
    "retained_bytes_budget_exceeded",
    "accounting_mismatch",
    "run_scan_result_rejected",
    "collector_internal_error",
})

EXCLUSION_BUCKETS = (
    "robots_denied",               # explicit Disallow: never fetched
    "non_html",
    "http_error",                  # >= 400 except 429
    "rate_limited",                # 429: never retried, host backed off
    "access_blocked",              # vendor challenge / block
    "fetch_failed",                # no status / transport error / timeout
    "oversized_response",          # decoded body above max_response_bytes
    "cross_origin_redirect",       # redirect hop refused before the request
    "unsafe_destination",          # non-public host, loop, chain limit, bad/missing Location, robots-blocked hop
    "incomplete_html",             # truncated or empty body
    "missing_page_evidence",       # fetcher produced no usable page record
    "duplicate_final_destination",  # final URL identity already retained
    "fetch_cut_by_budget",         # attempt started, cut by deadline/request budget
)
STOP_REASONS = (
    "inventory_exhausted",
    "capacity_reached",
    "deadline_reached",
    "request_budget_exhausted",
    "host_rate_limited",
)
DISCOVERY_FILTERS = (
    "duplicate_discoveries",
    "offsite_urls_ignored",
    "out_of_scope_ignored",
    "frontier_traps_ignored",
    "artifact_urls_ignored",
    "invalid_urls_ignored",
    "candidates_over_discovery_cap",
)
_COLLECTION_STATES = {
    "inventory_exhausted": "complete_inventory",
    "capacity_reached": "capacity_reached",
    "deadline_reached": "partial_deadline",
    "request_budget_exhausted": "partial_request_budget",
    "host_rate_limited": "partial_host_rate_limited",
}
_UNSAFE_FETCH_ERRORS = frozenset({
    "blocked_non_public_host",
    "blocked_non_public_redirect",
    "redirect_loop",
    "redirect_chain_limit_exceeded",
    "redirect_location_invalid",
    "redirect_response_missing_location",
    "redirect_destination_blocked_by_robots",
    "redirect_validation_failed",
})
_UNSAFE_REDIRECT_STATES = frozenset({
    "blocked_non_public_redirect",
    "redirect_loop",
    "redirect_chain_limit_exceeded",
    "redirect_invalid_location",
    "redirect_missing_location",
    "redirect_destination_blocked_by_robots",
})
_PRIVATE_PAGE_KEYS = ("_links", "_retry_after", "_redirect_alias_identity_keys", "_html")


class Extended500CollectorFailure(Exception):
    """Structured fail-closed outcome; never carries partial page evidence."""

    def __init__(self, code: str, detail: str = "") -> None:
        if code not in HARD_FAILURE_CODES:
            detail = f"{code}: {detail}"
            code = "collector_internal_error"
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class CollectorLimits:
    max_retained_pages: int = AUTHORISED_CAPACITY
    min_retained_pages: int = 1
    deadline_seconds: float = MAX_DEADLINE_SECONDS
    fetch_timeout_seconds: float = 10.0  # Standard 150 "advanced" fetch timeout
    max_response_bytes: int = MAX_RESPONSE_BYTES_CEILING
    max_total_retained_bytes: int = 64 * 1024 * 1024
    max_discovered_urls: int = MAX_DISCOVERED_URLS_CEILING
    max_requests: int = MAX_REQUESTS_CEILING
    min_host_interval_seconds: float = 0.2
    max_sitemap_fetches: int = 40
    concurrency: int = 4
    max_consecutive_rate_limited: int = 3


def _is_int(value: Any) -> bool:
    return type(value) is int


def _is_number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(float(value))


def _validate_limits(limits: Any) -> None:
    if not isinstance(limits, CollectorLimits):
        raise Extended500CollectorFailure("invalid_limits", "expected CollectorLimits")
    int_bounds = {
        "max_retained_pages": (1, AUTHORISED_CAPACITY),
        "min_retained_pages": (1, AUTHORISED_CAPACITY),
        "max_response_bytes": (1024, MAX_RESPONSE_BYTES_CEILING),
        "max_total_retained_bytes": (64 * 1024, MAX_TOTAL_RETAINED_BYTES_CEILING),
        "max_discovered_urls": (1, MAX_DISCOVERED_URLS_CEILING),
        "max_requests": (1, MAX_REQUESTS_CEILING),
        "max_sitemap_fetches": (1, MAX_SITEMAP_FETCHES),
        "concurrency": (1, 8),
        "max_consecutive_rate_limited": (1, 20),
    }
    for name, (low, high) in int_bounds.items():
        value = getattr(limits, name)
        if not _is_int(value) or not low <= value <= high:
            raise Extended500CollectorFailure(
                "invalid_limits", f"{name} must be an integer in [{low}, {high}]",
            )
    if limits.min_retained_pages > limits.max_retained_pages:
        raise Extended500CollectorFailure("invalid_limits", "min_retained_pages exceeds max_retained_pages")
    float_bounds = {
        "deadline_seconds": (1.0, MAX_DEADLINE_SECONDS),
        "fetch_timeout_seconds": (0.5, MAX_DEADLINE_SECONDS),
        "min_host_interval_seconds": (MIN_HOST_INTERVAL_FLOOR_SECONDS, MAX_HOST_INTERVAL_SECONDS),
    }
    for name, (low, high) in float_bounds.items():
        value = getattr(limits, name)
        if not _is_number(value) or not low <= float(value) <= high:
            raise Extended500CollectorFailure(
                "invalid_limits", f"{name} must be a finite number in [{low}, {high}]",
            )


def _validate_identity(identity: Any) -> dict[str, str]:
    if identity is None:
        return {}
    keys = ("scan_id", "request_id", "idempotency_key")
    if not isinstance(identity, Mapping) or set(identity) != set(keys):
        raise Extended500CollectorFailure("invalid_request", f"identity must contain exactly {keys}")
    out = {}
    for key in keys:
        value = identity[key]
        if not isinstance(value, str) or not value.strip() or len(value) > 256:
            raise Extended500CollectorFailure("invalid_request", f"invalid identity {key}")
        out[key] = value.strip()
    return out


def evidence_bytes(page: Any) -> int:
    """Deterministic size estimate of one retained in-memory page record."""
    return len(json.dumps(page, default=str, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


class RetainedPageLedger:
    """The only place a page becomes retained; enforces capacity and bytes."""

    def __init__(self, capacity: int, max_total_bytes: int) -> None:
        if not _is_int(capacity) or not 1 <= capacity <= AUTHORISED_CAPACITY:
            raise Extended500CollectorFailure(
                "invalid_limits", f"capacity must be in [1, {AUTHORISED_CAPACITY}]",
            )
        self.capacity = capacity
        self.max_total_bytes = int(max_total_bytes)
        self.pages: list[dict[str, Any]] = []
        self._sizes: dict[int, int] = {}
        self.total_bytes = 0

    def __len__(self) -> int:
        return len(self.pages)

    def retain(self, page: dict[str, Any]) -> None:
        if len(self.pages) >= self.capacity:
            raise Extended500CollectorFailure(
                "capacity_exceeded",
                f"refused to retain assessed page {len(self.pages) + 1}; authorised capacity is {self.capacity}",
            )
        size = evidence_bytes(page)
        if self.total_bytes + size > self.max_total_bytes:
            raise Extended500CollectorFailure(
                "retained_bytes_budget_exceeded",
                f"retaining page {len(self.pages) + 1} would exceed {self.max_total_bytes} bytes",
            )
        self.pages.append(page)
        self._sizes[id(page)] = size
        self.total_bytes += size

    def remeasure(self, page: dict[str, Any]) -> None:
        size = evidence_bytes(page)
        total = self.total_bytes - self._sizes.get(id(page), 0) + size
        if total > self.max_total_bytes:
            raise Extended500CollectorFailure(
                "retained_bytes_budget_exceeded", f"retained evidence would exceed {self.max_total_bytes} bytes",
            )
        self._sizes[id(page)] = size
        self.total_bytes = total

    def remeasure_all(self) -> None:
        for page in self.pages:
            self.remeasure(page)


class _GuardRefusal(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"extended500_collector_refused:{reason}")
        self.reason = reason


class _HostRequestGuard:
    """Single choke point for every HTTP request the collector causes.

    Enforces the total request budget, the active phase deadline and a minimum
    per-host start interval using the injected clock/sleeper. A 429 widens the
    host interval and honours Retry-After; it is never retried.
    """

    def __init__(self, *, clock, sleeper, max_requests: int, min_interval: float,
                 max_consecutive_rate_limited: int) -> None:
        self._clock = clock
        self._sleeper = sleeper
        self.max_requests = max_requests
        self.base_interval = float(min_interval)
        self.deadline = math.inf
        self.requests_made = 0
        self.refusals = {"deadline": 0, "request_budget": 0}
        self.interval: dict[str, float] = {}
        self._next_at: dict[str, float] = {}
        self._last_start: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self.min_observed_gap: dict[str, float] = {}
        self.total_wait_seconds = 0.0
        self.rate_limited_responses = 0
        self.consecutive_rate_limited = 0
        self.max_consecutive_rate_limited = max_consecutive_rate_limited
        self.rate_limit_tripped = False

    async def admit(self, host: str) -> None:
        if self.requests_made >= self.max_requests:
            self.refusals["request_budget"] += 1
            raise _GuardRefusal("request_budget")
        self.requests_made += 1  # reserve before awaiting; concurrent callers cannot overshoot
        try:
            lock = self._locks.setdefault(host, asyncio.Lock())
            async with lock:
                now = self._clock()
                start = max(now, self._next_at.get(host, now))
                if start >= self.deadline:
                    raise _GuardRefusal("deadline")
                if start > now:
                    self.total_wait_seconds += start - now
                    await self._sleeper(start - now)
                    now = self._clock()
                    if now >= self.deadline:
                        raise _GuardRefusal("deadline")
                previous = self._last_start.get(host)
                if previous is not None:
                    gap = now - previous
                    self.min_observed_gap[host] = min(self.min_observed_gap.get(host, gap), gap)
                self._last_start[host] = now
                self._next_at[host] = now + self.interval.get(host, self.base_interval)
        except _GuardRefusal as refusal:
            self.requests_made -= 1
            self.refusals[refusal.reason] += 1
            raise
        except BaseException:
            self.requests_made -= 1
            raise

    def observe(self, host: str, status: int, retry_after: str) -> None:
        if status == 429:
            self.rate_limited_responses += 1
            self.consecutive_rate_limited += 1
            widened = min(
                MAX_HOST_INTERVAL_SECONDS,
                max(self.interval.get(host, self.base_interval) * 2.0,
                    float(scanner.RATE_LIMIT_BACKOFF_INTERVAL_SECONDS)),
            )
            self.interval[host] = widened
            wait = max(widened, scanner.parse_retry_after_seconds(retry_after))
            now = self._clock()
            self._next_at[host] = max(self._next_at.get(host, now), now + wait)
            if self.consecutive_rate_limited >= self.max_consecutive_rate_limited:
                self.rate_limit_tripped = True
        elif 0 < status < 400:
            self.consecutive_rate_limited = 0


def _request_host(url: Any, headers: Any) -> str:
    if isinstance(headers, Mapping):
        for key, value in headers.items():
            if str(key).lower() == "host" and str(value).strip():
                return str(value).strip().lower()
    try:
        return (httpx.URL(str(url)).host or "").lower()
    except Exception:
        return ""


class _GuardedClient:
    """Per-operation view of the shared client exposing only guarded GETs.

    ``security.safe_get_once`` uses ``stream``/``get``; any other client method
    is deliberately absent so it fails closed instead of bypassing the guard.
    """

    follow_redirects = False

    def __init__(self, inner, guard: _HostRequestGuard) -> None:
        self._inner = inner
        self._guard = guard
        self.requests = 0
        self.refusal = ""

    async def _admit(self, url: Any, headers: Any) -> str:
        host = _request_host(url, headers)
        try:
            await self._guard.admit(host)
        except _GuardRefusal as refusal:
            self.refusal = self.refusal or refusal.reason
            raise
        self.requests += 1
        return host

    @contextlib.asynccontextmanager
    async def stream(self, method: str, url: Any, **kwargs):
        if str(method).upper() != "GET":
            raise _GuardRefusal("method_not_allowed")
        host = await self._admit(url, kwargs.get("headers"))
        async with self._inner.stream(method, url, **kwargs) as response:
            self._guard.observe(host, int(response.status_code or 0), response.headers.get("retry-after", ""))
            yield response

    async def get(self, url: Any, **kwargs):
        host = await self._admit(url, kwargs.get("headers"))
        response = await self._inner.get(url, **kwargs)
        self._guard.observe(host, int(response.status_code or 0), response.headers.get("retry-after", ""))
        return response


@dataclass
class _Attempt:
    view: _GuardedClient
    hops: int = 0
    refusal: str = ""
    timed_out: bool = False
    fetcher_error: bool = False


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _exclusion_bucket(page: Any, refusal: str = "") -> str | None:
    """Map one settled page to an exclusion bucket, or None if retainable."""
    if refusal == "cross_origin_redirect":
        return "cross_origin_redirect"
    if refusal in {"robots_redirect_hop", "method_not_allowed"}:
        return "unsafe_destination"
    if refusal in {"deadline", "request_budget"}:
        return "fetch_cut_by_budget"
    if refusal == "fetch_timeout":
        return "fetch_failed"
    if not isinstance(page, dict):
        return "missing_page_evidence"
    fetch_error = str(page.get("fetch_error") or "").strip()
    if fetch_error == "blocked_by_robots_txt":
        return "robots_denied"
    if fetch_error.startswith("decoded_response_body_exceeded"):
        return "oversized_response"
    if fetch_error in _UNSAFE_FETCH_ERRORS or str(page.get("redirect_state") or "") in _UNSAFE_REDIRECT_STATES:
        return "unsafe_destination"
    status = _int(page.get("status_code"))
    access_kind = str(page.get("access_block_kind") or "").strip().lower()
    if access_kind == "rate_limit" or status == 429:
        return "rate_limited"
    if access_kind in {"challenge", "block"}:
        return "access_blocked"
    if status >= 400:
        return "http_error"
    if fetch_error or status <= 0:
        return "fetch_failed"
    evidence_class = page_evidence_class(page)
    if evidence_class == "usable_html":
        return None
    return {
        "failed_access": "access_blocked",
        "redirected_terminal": "unsafe_destination",
        "non_html": "non_html",
        "incomplete_html": "incomplete_html",
    }.get(evidence_class, "missing_page_evidence")


def _www_alias_origin(origin: str) -> str:
    parsed = urlparse(origin)
    host = parsed.hostname or ""
    if not host:
        return ""
    alias = host[4:] if host.startswith("www.") else f"www.{host}"
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{alias}{port}"


def _empty_counts(keys) -> dict[str, int]:
    return {key: 0 for key in keys}


def _example(page: Any, url: str) -> dict[str, Any]:
    page = page if isinstance(page, dict) else {}
    return {
        "url": url,
        "final_url": str(page.get("final_url") or "")[:2048],
        "status_code": _int(page.get("status_code")),
        "fetch_error": str(page.get("fetch_error") or "")[:180],
    }


def _strip_private_page_fields(page: dict[str, Any]) -> None:
    for key in _PRIVATE_PAGE_KEYS:
        page.pop(key, None)


async def _default_page_fetcher(client, url, discovery, *, robots_policy, request_provider):
    # Looked up at call time so the production per-page path is always used.
    return await scanner.fetch_and_extract(
        client, url, discovery, robots_policy=robots_policy, request_provider=request_provider,
    )


class _PrivateCollector:
    def __init__(self, *, seed_url: str, prefix: str, scope_source: str, explicit_prefix: bool,
                 limits: CollectorLimits, identity: dict[str, str], client, clock, sleeper,
                 page_fetcher, robots_loader, sitemap_loader) -> None:
        self._limits = limits
        self._identity = identity
        self._client = client
        self._clock = clock
        self._page_fetcher = page_fetcher or _default_page_fetcher
        self._robots_loader = robots_loader or load_robots_policy
        self._sitemap_loader = sitemap_loader or load_sitemap_urls
        self._seed_url = seed_url
        self._seed_origin = scanner.url_origin(seed_url)
        self._effective_origin = self._seed_origin
        alias = _www_alias_origin(self._seed_origin)
        self._allowed_origins = {self._seed_origin} | ({alias} if alias else set())
        self._prefix = prefix
        self._explicit_prefix = explicit_prefix
        self._guard = _HostRequestGuard(
            clock=clock, sleeper=sleeper, max_requests=limits.max_requests,
            min_interval=limits.min_host_interval_seconds,
            max_consecutive_rate_limited=limits.max_consecutive_rate_limited,
        )
        self._ledger = RetainedPageLedger(limits.max_retained_pages, limits.max_total_retained_bytes)
        self._inventory: dict[str, dict[str, Any]] = {}
        self._tiers: tuple[deque, deque, deque, deque] = (deque(), deque(), deque(), deque())
        self._final_index: dict[str, dict[str, Any]] = {}
        self._robots: dict[str, Any] = {}
        self._robots_locks: dict[str, asyncio.Lock] = {}
        self._robots_requests = 0
        self._excluded = _empty_counts(EXCLUSION_BUCKETS)
        self._examples: dict[str, list[dict[str, Any]]] = {}
        self._not_attempted: dict[str, int] = _empty_counts(STOP_REASONS)
        self._filters = _empty_counts(DISCOVERY_FILTERS)
        self._discovered_from = Counter()
        self._attempts = 0
        self._coverage = scanner._new_scan_coverage_counters()
        self._stop_reason = ""
        self._in_flight = 0
        self._cond: asyncio.Condition | None = None
        self._max_body_bytes = 0
        self._seed_identity = ""
        self._scope_evidence: dict[str, Any] = {
            "requested_origin": self._seed_origin,
            "effective_origin": self._seed_origin,
            "origin_scope_source": "requested_origin",
            "effective_path_prefix": prefix,
            "scope_source": scope_source,
            "sitemap_urls_excluded_outside_scope": 0,
            "market_prefixes_detected": [],
            "multimarket_detected": False,
            "market_scope_required": False,
        }
        self._sitemap_evidence: dict[str, Any] = {"attempted": False}
        self._started = 0.0
        self._crawl_deadline = math.inf
        self._sitemap_deadline = math.inf

    # -- discovery -----------------------------------------------------
    def _admit(self, raw: Any, source: str, source_page: str = "", link_text: str = "", *, tier: int) -> str:
        clean = scanner.normalize_published_request_url(str(raw or ""))
        if not clean:
            self._filters["artifact_urls_ignored" if is_artifact_url(str(raw or "")) else "invalid_urls_ignored"] += 1
            return ""
        frontier = classify_frontier_url(clean)
        if not frontier.allowed:
            self._filters["frontier_traps_ignored"] += 1
            return ""
        clean = frontier.url
        if is_artifact_url(clean):
            self._filters["artifact_urls_ignored"] += 1
            return ""
        origin = scanner.url_origin(clean)
        if not (origin == self._effective_origin or (tier == 0 and origin == self._seed_origin)):
            self._filters["offsite_urls_ignored"] += 1
            return ""
        path = urlparse(clean).path or "/"
        if not path_within_scope(path, self._prefix) or (
            self._prefix == "/" and self._scope_evidence.get("market_scope_required") and market_pair_prefix(path)
        ):
            self._filters["out_of_scope_ignored"] += 1
            return ""
        identity = scanner.final_url_identity(clean)
        if not identity:
            self._filters["invalid_urls_ignored"] += 1
            return ""
        record = self._inventory.get(identity)
        if record is not None:
            self._filters["duplicate_discoveries"] += 1
            if record["state"] == "queued":
                self._merge_discovery(record["discovery"], source, source_page, link_text)
            return identity
        if len(self._inventory) >= self._limits.max_discovered_urls:
            self._filters["candidates_over_discovery_cap"] += 1
            return ""
        record = {
            "url": clean, "state": "queued", "tier": tier,
            "discovery": {"discovered_from": [], "source_pages": [], "link_text_samples": []},
        }
        self._merge_discovery(record["discovery"], source, source_page, link_text)
        self._inventory[identity] = record
        self._discovered_from[source] += 1
        self._tiers[tier].append(identity)
        return identity

    @staticmethod
    def _merge_discovery(record: dict, source: str, source_page: str, link_text: str) -> None:
        if source and source not in record["discovered_from"]:
            record["discovered_from"].append(source)
        if source_page and source_page not in record["source_pages"] and len(record["source_pages"]) < MAX_SOURCE_PAGES_PER_URL:
            record["source_pages"].append(source_page)
        if link_text and len(record["link_text_samples"]) < MAX_LINK_TEXT_SAMPLES:
            text = link_text[:180]
            if text not in record["link_text_samples"]:
                record["link_text_samples"].append(text)

    def _next_identity(self) -> str | None:
        for tier in self._tiers:
            while tier:
                identity = tier.popleft()
                if self._inventory[identity]["state"] == "queued":
                    self._inventory[identity]["state"] = "claimed"
                    return identity
        return None

    # -- outcomes ------------------------------------------------------
    def _stop(self, reason: str) -> None:
        if not self._stop_reason:
            self._stop_reason = reason

    def _exclude(self, identity: str, bucket: str, page: Any = None) -> None:
        record = self._inventory[identity]
        record["state"] = bucket
        self._excluded[bucket] += 1
        examples = self._examples.setdefault(bucket, [])
        if len(examples) < MAX_EXCLUSION_EXAMPLES:
            examples.append(_example(page, record["url"]))

    def _not_attempted_cut(self, identity: str, refusal: str) -> None:
        reason = "request_budget_exhausted" if refusal == "request_budget" else "deadline_reached"
        self._stop(reason)
        self._inventory[identity]["state"] = f"not_attempted:{reason}"
        self._not_attempted[reason] += 1

    async def _robots_for(self, origin: str) -> tuple[Any, str]:
        if origin in self._robots:
            return self._robots[origin], ""
        lock = self._robots_locks.setdefault(origin, asyncio.Lock())
        async with lock:
            if origin in self._robots:
                return self._robots[origin], ""
            view = _GuardedClient(self._client, self._guard)
            try:
                policy = await self._robots_loader(view, origin)
            except Exception:
                policy = RobotsPolicy(f"{origin}/robots.txt", "unavailable", 0)
            self._robots_requests += view.requests
            if view.refusal:
                # A guard refusal must never be mistaken for "robots unavailable".
                return None, view.refusal
            if not callable(getattr(policy, "allowed", None)):
                raise Extended500CollectorFailure("collector_internal_error", "robots loader returned no policy")
            self._robots[origin] = policy
            return policy, ""

    def _provider(self, attempt: _Attempt):
        async def provider(client, url, *, max_decoded_bytes=None):
            attempt.hops += 1
            if attempt.hops > 1:
                origin = scanner.url_origin(str(url))
                if origin not in self._allowed_origins:
                    attempt.refusal = "cross_origin_redirect"
                    raise _GuardRefusal("cross_origin_redirect")
                hop_policy, refusal = await self._robots_for(origin)
                if hop_policy is None:
                    attempt.refusal = refusal or "deadline"
                    raise _GuardRefusal(attempt.refusal)
                if hop_policy.allowed(SCANNER_USER_AGENT, str(url)) is False:
                    attempt.refusal = "robots_redirect_hop"
                    raise _GuardRefusal("robots_redirect_hop")
            cap = self._limits.max_response_bytes
            if max_decoded_bytes is not None:
                cap = min(cap, int(max_decoded_bytes))
            response = await security.safe_get_once(client, str(url), max_decoded_bytes=cap)
            if response is not None:
                self._max_body_bytes = max(self._max_body_bytes, len(response.content or b""))
            return response
        return provider

    async def _process(self, identity: str) -> None:
        record = self._inventory[identity]
        url = record["url"]
        policy, refusal = await self._robots_for(scanner.url_origin(url))
        if policy is None:
            self._not_attempted_cut(identity, refusal)
            return
        if policy.allowed(SCANNER_USER_AGENT, url) is False:
            self._exclude(identity, "robots_denied", {"fetch_error": "blocked_by_robots_txt"})
            return
        attempt = _Attempt(view=_GuardedClient(self._client, self._guard))
        snapshot = {key: list(value) for key, value in record["discovery"].items()}
        remaining = self._crawl_deadline - self._clock()
        timeout = max(0.05, min(remaining, self._limits.fetch_timeout_seconds * (DEFAULT_MAX_REDIRECTS + 1)))
        page = None
        try:
            page = await asyncio.wait_for(
                self._page_fetcher(
                    attempt.view, url, snapshot,
                    robots_policy=policy, request_provider=self._provider(attempt),
                ),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            attempt.timed_out = True
        except Extended500CollectorFailure:
            raise
        except Exception:
            attempt.fetcher_error = True
        self._settle(identity, record, page, attempt, policy)

    def _settle(self, identity, record, page, attempt: _Attempt, policy) -> None:
        refusal = attempt.refusal or attempt.view.refusal
        if refusal in {"deadline", "request_budget"}:
            self._stop("request_budget_exhausted" if refusal == "request_budget" else "deadline_reached")
            if attempt.view.requests == 0:
                self._not_attempted_cut(identity, refusal)
                return
        if attempt.timed_out:
            refusal = "deadline" if self._clock() >= self._crawl_deadline else "fetch_timeout"
            if refusal == "deadline":
                self._stop("deadline_reached")
        self._attempts += 1
        if not isinstance(page, dict):
            scanner._observe_scan_coverage(self._coverage, {"status_code": 0, "fetch_error": "missing_page_evidence"})
            self._exclude(identity, _exclusion_bucket(None, refusal), None)
            return
        links = page.pop("_links", None) or []
        page.pop("_retry_after", None)
        annotate_robots_evidence(page, policy, record["url"])
        scanner._observe_scan_coverage(self._coverage, page)
        bucket = _exclusion_bucket(page, refusal)
        final = str(page.get("final_url") or page.get("url") or "")
        if bucket is None and scanner.url_origin(final) not in self._allowed_origins:
            bucket = "cross_origin_redirect"
        final_identity = scanner.final_url_identity(final)
        if bucket is None and not final_identity:
            bucket = "missing_page_evidence"
        if bucket is not None:
            self._exclude(identity, bucket, page)
            return
        existing = self._final_index.get(final_identity)
        if existing is not None:
            scanner.merge_duplicate_page_evidence(existing, page)
            self._ledger.remeasure(existing)
            self._exclude(identity, "duplicate_final_destination", page)
            return
        reach = page.get("_reachability_links")
        if isinstance(reach, list):
            # Lossless for B11: only edges to retained (allowed-origin) requests count.
            page["_reachability_links"] = [
                link for link in reach
                if isinstance(link, dict) and scanner.url_origin(str(link.get("href") or "")) in self._allowed_origins
            ]
        self._ledger.retain(page)
        self._final_index[final_identity] = page
        record["state"] = "retained"
        if identity == self._seed_identity:
            self._maybe_adopt_entry_origin(page)
        for link in links:
            if isinstance(link, dict):
                self._admit(link.get("href"), "internal_link", page.get("path") or "",
                            str(link.get("text") or ""), tier=2)

    def _maybe_adopt_entry_origin(self, page: dict[str, Any]) -> None:
        """Mirror run_scan: a verified www/apex alias landing sets the origin."""
        if self._explicit_prefix or self._prefix != "/":
            return
        final = str(page.get("final_url") or "")
        if 200 <= _int(page.get("status_code")) < 300 and scanner.is_www_origin_alias(self._seed_url, final):
            self._effective_origin = scanner.url_origin(final)
            self._scope_evidence["effective_origin"] = self._effective_origin
            self._scope_evidence["origin_scope_source"] = "verified_www_alias_redirect"
        market = market_pair_prefix(final)
        if market:
            self._prefix = market
            self._scope_evidence["effective_path_prefix"] = market
            self._scope_evidence["scope_source"] = "redirect_market_path"

    # -- phases --------------------------------------------------------
    async def _discover_sitemaps(self) -> None:
        if self._stop_reason:
            return
        remaining = self._sitemap_deadline - self._clock()
        self._sitemap_evidence = {"attempted": remaining > 0, "budget_seconds": round(max(0.0, remaining), 3)}
        if remaining <= 0:
            self._sitemap_evidence["skipped_reason"] = "sitemap_budget_exhausted_before_start"
            return
        view = _GuardedClient(self._client, self._guard)
        diagnostics: dict[str, Any] = {}
        artifacts: list[dict] = []
        self._guard.deadline = min(self._crawl_deadline, self._sitemap_deadline)
        urls: Any = []
        try:
            urls = await self._sitemap_loader(
                view, self._effective_origin, self._prefix, self._limits.max_discovered_urls, artifacts,
                scope_evidence=self._scope_evidence,
                deadline=time.monotonic() + remaining,
                max_fetches=self._limits.max_sitemap_fetches,
                diagnostics=diagnostics,
                # The guarded client already paces every request per host.
                min_request_interval_seconds=0.0,
            )
        except Exception:
            urls = []
            diagnostics["loader_exception"] = True
        finally:
            self._guard.deadline = self._crawl_deadline
        candidates = [url for url in (urls if isinstance(urls, list) else []) if isinstance(url, str)]
        budget = max(0, self._limits.max_retained_pages - len(self._ledger))
        sample = select_balanced_urls(
            candidates, lambda u: classify_template(urlparse(u).path or "/"),
            lambda u: urlparse(u).path or "/", budget,
        )
        sample_set = set(sample)
        before = len(self._inventory)
        for url in sample:
            self._admit(url, "sitemap", "/sitemap.xml", tier=1)
        for url in candidates:
            if url not in sample_set:
                self._admit(url, "sitemap", "/sitemap.xml", tier=3)
        self._sitemap_evidence.update({
            "sitemap_requests": view.requests,
            "sitemap_guard_refusal": view.refusal,
            "sitemap_urls_returned": len(candidates),
            "sitemap_urls_admitted": len(self._inventory) - before,
            "sitemap_balanced_sample_size": len(sample),
            "sitemap_artifact_urls": len(artifacts),
            "sitemap_fetch_count": _int(diagnostics.get("sitemap_fetch_count")),
            "sitemap_fetch_limit_reached": bool(diagnostics.get("sitemap_fetch_limit_reached")),
            "sitemap_budget_exhausted": bool(diagnostics.get("sitemap_budget_exhausted")),
            "sitemap_failure_reason_buckets": dict(diagnostics.get("sitemap_failure_reason_buckets") or {}),
            "sitemap_child_url_count": _int(diagnostics.get("sitemap_child_url_count")),
        })

    async def _worker(self) -> None:
        assert self._cond is not None
        capacity = self._limits.max_retained_pages
        while True:
            async with self._cond:
                while True:
                    if not self._stop_reason:
                        if self._clock() >= self._crawl_deadline:
                            self._stop("deadline_reached")
                        elif self._guard.rate_limit_tripped:
                            self._stop("host_rate_limited")
                        elif len(self._ledger) >= capacity:
                            self._stop("capacity_reached")
                        elif self._guard.requests_made >= self._limits.max_requests:
                            self._stop("request_budget_exhausted")
                    if self._stop_reason:
                        self._cond.notify_all()
                        return
                    identity = None
                    if len(self._ledger) + self._in_flight < capacity:
                        identity = self._next_identity()
                        if identity is None and self._in_flight == 0:
                            self._stop("inventory_exhausted")
                            continue
                    if identity is not None:
                        break
                    await self._cond.wait()
                self._in_flight += 1
            try:
                await self._process(identity)
            finally:
                async with self._cond:
                    self._in_flight -= 1
                    self._cond.notify_all()

    async def _crawl(self) -> None:
        if self._stop_reason:
            return
        self._cond = asyncio.Condition()
        workers = [asyncio.create_task(self._worker()) for _ in range(self._limits.concurrency)]
        try:
            await asyncio.gather(*workers)
        except BaseException:
            for worker in workers:
                worker.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
            raise

    async def run(self) -> dict[str, Any]:
        self._started = self._clock()
        timing = allocate_scan_time_budget(
            self._started, self._limits.deadline_seconds, self._limits.fetch_timeout_seconds, now=self._started,
        )
        self._crawl_deadline = timing["crawl_deadline"]
        self._sitemap_deadline = timing["sitemap_deadline"]
        self._guard.deadline = self._crawl_deadline

        policy, refusal = await self._robots_for(self._seed_origin)
        if policy is None:
            raise Extended500CollectorFailure(
                "deadline_before_minimum_evidence", f"robots.txt could not be read ({refusal})",
            )
        if policy.allowed(SCANNER_USER_AGENT, self._seed_url) is False:
            raise Extended500CollectorFailure(
                "entry_robots_denied", "robots.txt disallows the entry URL for the scanner user-agent",
            )
        self._seed_identity = self._admit(self._seed_url, "seed", tier=0)
        if not self._seed_identity:
            raise Extended500CollectorFailure("invalid_request", "entry URL is outside its own crawl frontier")
        self._tiers[0].clear()
        self._inventory[self._seed_identity]["state"] = "claimed"
        await self._process(self._seed_identity)
        await self._discover_sitemaps()
        await self._crawl()
        return self._finish()

    # -- result --------------------------------------------------------
    def _finish(self) -> dict[str, Any]:
        stop = self._stop_reason or "inventory_exhausted"
        for record in self._inventory.values():
            if record["state"] in {"queued", "claimed"}:
                record["state"] = f"not_attempted:{stop}"
                self._not_attempted[stop] += 1
        pages = self._ledger.pages
        retained = len(pages)
        if retained < self._limits.min_retained_pages:
            code = "deadline_before_minimum_evidence" if stop == "deadline_reached" else "insufficient_evidence"
            raise Extended500CollectorFailure(
                code, f"{retained} usable HTML pages retained; minimum {self._limits.min_retained_pages}; stop_reason={stop}",
            )
        enrich_pages_from_retained_link_evidence(pages, max_assessed_pages=MAX_EXTENDED_ASSESSED_PAGES)
        for page in pages:
            _strip_private_page_fields(page)
        self._ledger.remeasure_all()
        coverage = scanner._finalize_scan_coverage(self._coverage, pages)
        discovered = len(self._inventory)
        excluded_total = sum(self._excluded.values())
        not_attempted_total = sum(self._not_attempted.values())
        states = Counter(record["state"] for record in self._inventory.values())
        expected_states = Counter({"retained": retained})
        expected_states.update({k: v for k, v in self._excluded.items() if v})
        expected_states.update({f"not_attempted:{k}": v for k, v in self._not_attempted.items() if v})
        finals = {scanner.final_url_identity(p.get("final_url") or p.get("url") or "") for p in pages}
        checks = {
            "inventory_identity": discovered == retained + excluded_total + not_attempted_total,
            "attempt_identity": self._attempts == retained + excluded_total - self._excluded["robots_denied"],
            "coverage_identity": coverage["urls_attempted"] == self._attempts
            and coverage["unique_retained_destinations"] == retained,
            "per_url_states": states == expected_states,
            "unique_final_destinations": len(finals) == retained and "" not in finals,
            "within_capacity": retained <= self._limits.max_retained_pages <= AUTHORISED_CAPACITY,
        }
        if not all(checks.values()):
            raise Extended500CollectorFailure(
                "accounting_mismatch", "failed: " + ",".join(k for k, v in checks.items() if not v),
            )
        hosts = sorted(self._guard.min_observed_gap)
        robots = self._robots.get(self._effective_origin) or self._robots.get(self._seed_origin)
        return {
            "success": True,
            "version": EXTENDED500_PRIVATE_COLLECTOR_VERSION,
            "collector_path": "bounded_private_frontier",
            "scan_mode": EXTENDED500_MODE,
            "canonical_mode": EXTENDED500_MODE,
            "collector_state": _COLLECTION_STATES[stop],
            "stop_reason": stop,
            "review_status": "not_reviewed",
            "pages_reviewed": 0,
            "release_gate_eligible": False,
            "customer_visible": False,
            "website_url": self._seed_url,
            "requested_origin": self._seed_origin,
            "effective_origin": self._effective_origin,
            "normalized_domain": (urlparse(self._seed_url).hostname or "").lower().removeprefix("www.").rstrip("."),
            "path_prefix": self._prefix,
            "crawl_scope": dict(self._scope_evidence),
            "collection_identity": dict(self._identity),
            "pages": pages,
            "crawled_pages": pages,
            "pages_crawled": retained,
            "pages_found": discovered,
            "scan_coverage": coverage,
            "collector_counters": {
                "urls_discovered": discovered,
                "pages_retained": retained,
                "urls_attempted": self._attempts,
                "excluded": dict(self._excluded),
                "not_attempted": dict(self._not_attempted),
                "discovery_filtered": dict(self._filters),
                "discovered_by_source": dict(self._discovered_from),
                "requests_made": self._guard.requests_made,
                "robots_requests": self._robots_requests,
            },
            "reconciliation": {
                "inventory_identity": "urls_discovered == pages_retained + sum(excluded) + sum(not_attempted)",
                "attempt_identity": "urls_attempted == pages_retained + sum(excluded) - excluded.robots_denied",
                "checks": checks,
                "holds": True,
            },
            "exclusion_examples": {k: list(v) for k, v in self._examples.items()},
            "resource_usage": {
                "elapsed_seconds_injected_clock": round(self._clock() - self._started, 6),
                "requests_made": self._guard.requests_made,
                "guard_refusals": dict(self._guard.refusals),
                "retained_evidence_bytes": self._ledger.total_bytes,
                "max_response_body_bytes_observed": self._max_body_bytes,
                "rate_limited_responses": self._guard.rate_limited_responses,
                "rate_limit_wait_seconds": round(self._guard.total_wait_seconds, 6),
                "min_observed_host_start_gap_seconds": {h: round(self._guard.min_observed_gap[h], 6) for h in hosts},
                "final_host_interval_seconds": {
                    h: self._guard.interval.get(h, self._guard.base_interval) for h in hosts
                },
            },
            "limits": asdict(self._limits),
            "robots_txt_evidence": robots.evidence() if robots is not None and hasattr(robots, "evidence") else {},
            "sitemap_evidence": dict(self._sitemap_evidence),
        }

    def diagnostics(self) -> dict[str, Any]:
        return {
            "stop_reason": self._stop_reason,
            "urls_discovered": len(self._inventory),
            "pages_retained_before_failure": len(self._ledger),
            "urls_attempted": self._attempts,
            "excluded": dict(self._excluded),
            "requests_made": self._guard.requests_made,
        }


def _failure_result(failure: Extended500CollectorFailure, diagnostics: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "success": False,
        "version": EXTENDED500_PRIVATE_COLLECTOR_VERSION,
        "scan_mode": EXTENDED500_MODE,
        "canonical_mode": EXTENDED500_MODE,
        "collector_state": "failed_closed",
        "error_code": failure.code,
        "error": failure.detail,
        "review_status": "not_reviewed",
        "release_gate_eligible": False,
        "customer_visible": False,
        "diagnostics": dict(diagnostics),
    }


def _validate_seed(website_url: Any, path_prefix: Any) -> tuple[str, str, str, bool]:
    if not isinstance(website_url, str) or not website_url.strip() or len(website_url) > MAX_SEED_URL_CHARS:
        raise Extended500CollectorFailure("invalid_request", "missing or oversized website_url")
    seed = scanner.normalize_published_request_url(website_url)
    if not seed:
        raise Extended500CollectorFailure("invalid_request", "invalid website_url")
    parsed = urlparse(seed)
    if parsed.username or parsed.password:
        raise Extended500CollectorFailure("invalid_request", "credentials in website_url")
    if path_prefix is not None and (not isinstance(path_prefix, str) or len(path_prefix) > 2048):
        raise Extended500CollectorFailure("invalid_request", "invalid path_prefix")
    if not security.is_public_http_url(seed):
        raise Extended500CollectorFailure("invalid_request", "website_url must resolve to a public host")
    prefix, scope_source, _ = scanner.resolve_crawl_scope(path_prefix, parsed.path)
    if not path_within_scope(parsed.path or "/", prefix):
        raise Extended500CollectorFailure("invalid_request", "website_url is outside path_prefix")
    return seed, prefix, scope_source, bool(str(path_prefix or "").strip())


async def run_private_extended500_collection(
    website_url: str,
    *,
    path_prefix: str | None = None,
    limits: CollectorLimits | None = None,
    identity: Mapping[str, str] | None = None,
    http_client: Any = None,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    page_fetcher: Callable[..., Awaitable[Any]] | None = None,
    robots_loader: Callable[..., Awaitable[Any]] | None = None,
    sitemap_loader: Callable[..., Awaitable[Any]] | None = None,
) -> dict[str, Any]:
    """Collect at most ``limits.max_retained_pages`` (<= 500) usable HTML pages.

    Returns a private, unreviewed collection or a structured failure. Robots
    Disallow is always honoured: any ambient owner override is reset to False.
    """
    limits = CollectorLimits() if limits is None else limits
    collector: _PrivateCollector | None = None
    try:
        _validate_limits(limits)
        bound_identity = _validate_identity(identity)
        seed, prefix, scope_source, explicit = _validate_seed(website_url, path_prefix)
        if http_client is not None and getattr(http_client, "follow_redirects", True) is not False:
            raise Extended500CollectorFailure("invalid_request", "http_client must not follow redirects")
        with owner_robots_override(False):
            async with contextlib.AsyncExitStack() as stack:
                client = http_client
                if client is None:
                    client = await stack.enter_async_context(httpx.AsyncClient(
                        timeout=float(limits.fetch_timeout_seconds), follow_redirects=False,
                        headers={"User-Agent": USER_AGENT},
                    ))
                collector = _PrivateCollector(
                    seed_url=seed, prefix=prefix, scope_source=scope_source, explicit_prefix=explicit,
                    limits=limits, identity=bound_identity, client=client, clock=clock, sleeper=sleeper,
                    page_fetcher=page_fetcher, robots_loader=robots_loader, sitemap_loader=sitemap_loader,
                )
                return await collector.run()
    except Extended500CollectorFailure as failure:
        return _failure_result(failure, collector.diagnostics() if collector is not None else {})


def admit_run_scan_result(
    result: Any,
    *,
    limits: CollectorLimits | None = None,
    identity: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Pass a run_scan-shaped 500 result through the same fail-closed gate.

    Never truncates: >capacity page records, mismatched aliases or attempts
    that do not reconcile (run_scan's silent ``pages[:max_pages]`` slice)
    fail closed. The input is not mutated.
    """
    limits = CollectorLimits() if limits is None else limits
    try:
        _validate_limits(limits)
        bound_identity = _validate_identity(identity)
        return _admit_run_scan(result, limits, bound_identity)
    except Extended500CollectorFailure as failure:
        return _failure_result(failure, {})


def _admit_run_scan(result: Any, limits: CollectorLimits, identity: dict[str, str]) -> dict[str, Any]:
    if not isinstance(result, dict) or result.get("success") is not True:
        raise Extended500CollectorFailure("run_scan_result_rejected", "run_scan did not succeed")
    pages, mirror = result.get("pages"), result.get("crawled_pages")
    if not isinstance(pages, list) or not isinstance(mirror, list) or pages != mirror:
        raise Extended500CollectorFailure("run_scan_result_rejected", "page aliases must match exactly")
    if not _is_int(result.get("pages_crawled")) or result["pages_crawled"] != len(pages):
        raise Extended500CollectorFailure("accounting_mismatch", "pages_crawled does not equal page records")
    if len(pages) > limits.max_retained_pages:
        raise Extended500CollectorFailure(
            "capacity_exceeded", f"{len(pages)} page records exceed authorised capacity {limits.max_retained_pages}",
        )
    coverage = result.get("scan_coverage") if isinstance(result.get("scan_coverage"), dict) else {}
    attempted, usable = coverage.get("urls_attempted"), coverage.get("usable_html_pages")
    timing = result.get("crawl_timing") if isinstance(result.get("crawl_timing"), dict) else {}
    deduped = timing.get("final_url_duplicates_deduped", 0)
    found = result.get("pages_found")
    if not all(_is_int(v) and v >= 0 for v in (attempted, usable, deduped, found)):
        raise Extended500CollectorFailure("accounting_mismatch", "missing run_scan coverage counters")
    if attempted != len(pages) + deduped:
        raise Extended500CollectorFailure(
            "accounting_mismatch", "run_scan attempts do not reconcile with page records (truncated or forged)",
        )
    if found < len(pages) + deduped or usable > attempted:
        raise Extended500CollectorFailure("accounting_mismatch", "run_scan inventory smaller than attempts")
    scope = result.get("crawl_scope") if isinstance(result.get("crawl_scope"), dict) else {}
    allowed = {scope.get("requested_origin"), scope.get("effective_origin"), scanner.url_origin(result.get("website_url") or "")}
    allowed.discard(None)
    allowed.discard("")
    ledger = RetainedPageLedger(limits.max_retained_pages, limits.max_total_retained_bytes)
    excluded = _empty_counts(EXCLUSION_BUCKETS)
    examples: dict[str, list] = {}
    finals: set[str] = set()
    for page in pages:
        bucket = _exclusion_bucket(page)
        if bucket == "robots_denied" and "seed" in set(page.get("discovered_from") or []):
            raise Extended500CollectorFailure("entry_robots_denied", "run_scan entry URL was blocked by robots.txt")
        final = str(page.get("final_url") or page.get("url") or "") if isinstance(page, dict) else ""
        identity_key = scanner.final_url_identity(final)
        if bucket is None and scanner.url_origin(final) not in allowed:
            bucket = "cross_origin_redirect"
        if bucket is None and (not identity_key or identity_key in finals):
            bucket = "duplicate_final_destination" if identity_key else "missing_page_evidence"
        if bucket is not None:
            excluded[bucket] += 1
            bucket_examples = examples.setdefault(bucket, [])
            if len(bucket_examples) < MAX_EXCLUSION_EXAMPLES:
                bucket_examples.append(_example(page, str((page or {}).get("url") or "") if isinstance(page, dict) else ""))
            continue
        finals.add(identity_key)
        ledger.retain(copy.deepcopy(page))
    excluded["duplicate_final_destination"] += deduped
    retained = len(ledger)
    if retained < limits.min_retained_pages:
        raise Extended500CollectorFailure("insufficient_evidence", f"{retained} usable HTML pages in run_scan result")
    retained_pages = ledger.pages
    if any("_reachability_links" in page for page in retained_pages):
        enrich_pages_from_retained_link_evidence(retained_pages, max_assessed_pages=MAX_EXTENDED_ASSESSED_PAGES)
    for page in retained_pages:
        _strip_private_page_fields(page)
    ledger.remeasure_all()
    remainder = found - len(pages) - deduped
    not_attempted = {"run_scan_inventory_remainder": remainder}
    checks = {
        "inventory_identity": found == retained + sum(excluded.values()) + remainder,
        "record_identity": len(pages) == retained + sum(excluded.values()) - deduped,
        "attempt_identity": attempted == len(pages) + deduped,
        "within_capacity": retained <= limits.max_retained_pages,
    }
    if not all(checks.values()):  # pragma: no cover - defensive
        raise Extended500CollectorFailure("accounting_mismatch", ",".join(k for k, v in checks.items() if not v))
    website = str(result.get("website_url") or "")
    return {
        "success": True,
        "version": EXTENDED500_PRIVATE_COLLECTOR_VERSION,
        "collector_path": "run_scan_admission",
        "scan_mode": EXTENDED500_MODE,
        "canonical_mode": EXTENDED500_MODE,
        "collector_state": "admitted_run_scan_result",
        "stop_reason": "run_scan_completed",
        "review_status": "not_reviewed",
        "pages_reviewed": 0,
        "release_gate_eligible": False,
        "customer_visible": False,
        "website_url": website,
        "requested_origin": scope.get("requested_origin") or scanner.url_origin(website),
        "effective_origin": scope.get("effective_origin") or scanner.url_origin(website),
        "normalized_domain": (urlparse(website).hostname or "").lower().removeprefix("www.").rstrip("."),
        "path_prefix": scope.get("effective_path_prefix") or "/",
        "crawl_scope": dict(scope),
        "collection_identity": dict(identity),
        "pages": retained_pages,
        "crawled_pages": retained_pages,
        "pages_crawled": retained,
        "pages_found": found,
        "scan_coverage": {
            "urls_attempted": attempted,
            "usable_html_pages": usable,
            "unique_retained_destinations": retained,
        },
        "collector_counters": {
            "urls_discovered": found,
            "pages_retained": retained,
            "urls_attempted": attempted,
            "run_scan_page_records": len(pages),
            "excluded": excluded,
            "not_attempted": not_attempted,
        },
        "reconciliation": {
            "inventory_identity": "pages_found == pages_retained + sum(excluded) + run_scan_inventory_remainder",
            "attempt_identity": "run_scan urls_attempted == page_records + final_url_duplicates_deduped",
            "checks": checks,
            "holds": True,
        },
        "exclusion_examples": examples,
        "resource_usage": {"retained_evidence_bytes": ledger.total_bytes},
        "limits": asdict(limits),
        "robots_txt_evidence": dict(result.get("robots_txt_evidence") or {}),
        "sitemap_evidence": {},
    }


_EXTERNAL_COLLECTION_FIELDS = frozenset({
    "success", "version", "collector_path", "scan_mode", "canonical_mode", "collector_state",
    "stop_reason", "review_status", "pages_reviewed", "release_gate_eligible", "customer_visible",
    "website_url", "requested_origin", "effective_origin", "normalized_domain", "path_prefix",
    "collection_identity", "pages", "crawled_pages", "pages_crawled", "pages_found", "scan_coverage",
    "collector_counters", "reconciliation", "exclusion_examples", "resource_usage", "limits",
    "robots_txt_evidence", "sitemap_evidence", "error_code", "error", "diagnostics",
})


def project_private_collection_for_external_boundary(collection: Mapping[str, Any]) -> dict[str, Any]:
    """Positive top-level allowlist plus the existing positive page projector."""
    if not isinstance(collection, Mapping):
        raise ValueError("Expected a collection mapping")
    allowed = {key: copy.deepcopy(value) for key, value in collection.items()
               if key in _EXTERNAL_COLLECTION_FIELDS and key not in ("pages", "crawled_pages")}
    if isinstance(collection.get("pages"), list):
        allowed["pages"] = collection["pages"]
        allowed["crawled_pages"] = collection["pages"]
    return project_scan_result_for_external_boundary(allowed)


def build_private_collection_handoff(
    scan_run: dict[str, Any],
    collection: Mapping[str, Any],
    signing_key: str,
    *,
    scanner_source_sha: str,
    beta_revision_fingerprint: str,
) -> dict[str, Any]:
    """Sign a successful, identity-bound collection via the existing unreviewed handoff."""
    if not isinstance(collection, Mapping) or collection.get("success") is not True:
        raise ValueError("Only a successful private collection can be handed off")
    bound = collection.get("collection_identity") or {}
    if not isinstance(bound, Mapping) or set(bound) != {"scan_id", "request_id", "idempotency_key"}:
        raise ValueError("Collection was not bound to a frozen ScanRun identity")
    result = {
        "scan_mode": EXTENDED500_MODE,
        "canonical_mode": EXTENDED500_MODE,
        "scan_id": bound["scan_id"],
        "request_id": bound["request_id"],
        "idempotency_key": bound["idempotency_key"],
        "normalized_domain": collection.get("normalized_domain"),
        "pages_found": collection.get("pages_found"),
        "pages_crawled": collection.get("pages_crawled"),
        "pages": collection.get("pages"),
        "crawled_pages": collection.get("crawled_pages"),
        "scan_coverage": collection.get("scan_coverage"),
        "scanner_source_sha": scanner_source_sha,
        "beta_revision_fingerprint": beta_revision_fingerprint,
        "release_gate_eligible": False,
    }
    return build_extended500_evidence_handoff(scan_run, result, signing_key)

# ---------------------------------------------------------------------------
# Spawn-isolated run_scan candidate (kept from bb703cf04). Its process-local
# SCAN_BUDGETS insertion never reaches the parent/public process.
# ---------------------------------------------------------------------------

EXTENDED500_MODE = "extended_500"
COLLECTOR_VERSION = "extended500_private_collector_v1_unreviewed"
MAX_RETAINED_PAGES = 500
MAX_RESULT_BYTES = 8 * 1024 * 1024
MIN_TIMEOUT_SECONDS = 20
MAX_TIMEOUT_SECONDS = 120
MAX_CONCURRENCY = 8
_TOKEN = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_HOST = re.compile(r"[a-z0-9.-]{1,253}\Z")


class Extended500CollectionRefused(ValueError):
    """Non-retryable collection-contract refusal. Contains no secrets."""


def _token(value: Any) -> bool:
    return isinstance(value, str) and bool(_TOKEN.fullmatch(value))


def _site_root(value: Any) -> str:
    if not isinstance(value, str) or len(value) > 2048:
        return ""
    try:
        url = urlsplit(value)
        host = (url.hostname or "").lower().rstrip(".")
        if (
            url.scheme not in {"https", "http"}
            or not _HOST.fullmatch(host) or "." not in host
            or url.username is not None or url.password is not None
            or url.port is not None or url.query or url.fragment
            or url.path not in ("", "/") or host.startswith(".")
            or host.endswith((".local", ".localhost", ".test", ".invalid", ".internal", ".example"))
            or host in {"localhost", "0.0.0.0"} or ".." in host
            or all(c in ".0123456789" for c in host)
        ):
            return ""
        return f"{url.scheme}://{host}/"
    except ValueError:
        return ""


def validate_extended500_collection_request(scan: Any, *, timeout_seconds: int = 120,
                                             concurrency: int = 4) -> str:
    """Use only a service-owned frozen ScanRun; this is not pickup authorization."""
    if not isinstance(scan, dict):
        raise Extended500CollectionRefused("frozen_scanrun_required")
    if scan.get("scan_mode") != EXTENDED500_MODE or scan.get("status") != "queued":
        raise Extended500CollectionRefused("frozen_extended500_queue_required")
    if any(not _token(scan.get(k)) for k in (
        "id", "owner_user_id", "project_id", "request_id", "idempotency_key",
    )):
        raise Extended500CollectionRefused("scanrun_identity_invalid")
    if (type(scan.get("attempt_count")) is not int or scan["attempt_count"] < 1
        or scan.get("respect_robots_txt") is not True
        or scan.get("owner_attested_robots_override") is not False
        or scan.get("path_prefix") not in (None, "")):
        raise Extended500CollectionRefused("scanrun_scope_invalid")
    url = _site_root(scan.get("website_url"))
    if not url or url != scan.get("website_url"):
        raise Extended500CollectionRefused("scanrun_root_url_invalid")
    if urlsplit(url).hostname.removeprefix("www.") != scan.get("normalized_domain"):
        raise Extended500CollectionRefused("scanrun_domain_invalid")
    if (type(timeout_seconds) is not int or not MIN_TIMEOUT_SECONDS <= timeout_seconds <= MAX_TIMEOUT_SECONDS
        or type(concurrency) is not int or not 1 <= concurrency <= MAX_CONCURRENCY):
        raise Extended500CollectionRefused("collector_budget_invalid")
    return url


def validate_extended500_collection_result(scan: dict, raw_result: Any) -> dict:
    """Keep one 500-page *unreviewed* collection; reject untruthful counts."""
    from .page_output_privacy import project_scan_result_for_external_boundary

    if not isinstance(raw_result, dict) or raw_result.get("success") is not True:
        raise Extended500CollectionRefused("collection_failed_or_unverified")
    if raw_result.get("scan_mode") != EXTENDED500_MODE:
        raise Extended500CollectionRefused("foreign_collection_mode")
    if raw_result.get("release_gate_eligible") is True or raw_result.get("review_status") in {
        "reviewed", "complete", "passed",
    }:
        raise Extended500CollectionRefused("collector_must_not_assert_review_authority")
    pages = raw_result.get("pages")
    mirrored = raw_result.get("crawled_pages")
    if not isinstance(pages, list) or not isinstance(mirrored, list) or pages != mirrored:
        raise Extended500CollectionRefused("collection_page_mirror_mismatch")
    number = len(pages)
    if number < 1 or number > MAX_RETAINED_PAGES:
        raise Extended500CollectionRefused("collection_page_budget_exceeded_or_empty")
    if type(raw_result.get("pages_crawled")) is not int or raw_result["pages_crawled"] != number:
        raise Extended500CollectionRefused("collection_assessed_count_invalid")
    found = raw_result.get("pages_found")
    if type(found) is not int or found < number:
        raise Extended500CollectionRefused("collection_discovered_count_invalid")
    coverage = raw_result.get("scan_coverage")
    if not isinstance(coverage, dict):
        raise Extended500CollectionRefused("collection_coverage_missing")
    for field in ("urls_attempted", "usable_html_pages", "unique_retained_destinations"):
        if type(coverage.get(field)) is not int or coverage[field] < 0:
            raise Extended500CollectionRefused("collection_coverage_invalid")
    if (coverage["urls_attempted"] < number
        or coverage["usable_html_pages"] > number
        or coverage["unique_retained_destinations"] != number):
        raise Extended500CollectionRefused("collection_denominator_invalid")
    unique = set()
    for page in pages:
        if not isinstance(page, dict):
            raise Extended500CollectionRefused("collection_page_invalid")
        url = page.get("final_url") or page.get("url")
        if not isinstance(url, str) or not url:
            raise Extended500CollectionRefused("collection_page_identity_missing")
        if url in unique:
            raise Extended500CollectionRefused("collection_duplicate_destination")
        unique.add(url)

    projected = project_scan_result_for_external_boundary(raw_result)
    projected["scan_mode"] = EXTENDED500_MODE
    projected["canonical_mode"] = EXTENDED500_MODE
    projected["release_gate_eligible"] = False
    projected["review_status"] = "not_reviewed"
    projected["pages_reviewed"] = 0
    projected["extended500_collector_version"] = COLLECTOR_VERSION
    for field in ("scan_id", "request_id", "idempotency_key"):
        projected[field] = scan["id" if field == "scan_id" else field]
    projected["normalized_domain"] = scan["normalized_domain"]

    # Count parity must survive the privacy boundary.
    if len(projected.get("pages", [])) != number or projected.get("pages") != projected.get("crawled_pages"):
        raise Extended500CollectionRefused("collection_projection_count_mismatch")
    return projected


def _collector_child(conn, scan: dict, timeout_seconds: int, concurrency: int) -> None:
    """Spawn-only process target. No live Standard 150 request can share budget."""
    try:
        from . import scanner
        # The mode is unique and exists ONLY in this child's process memory.
        if EXTENDED500_MODE in scanner.SCAN_BUDGETS:
            raise Extended500CollectionRefused("collector_budget_collision")
        scanner.SCAN_BUDGETS[EXTENDED500_MODE] = {
            "max_pages": MAX_RETAINED_PAGES, "timeout": timeout_seconds,
            "fetch_timeout": 10, "max_sitemap_fetches": 60,
        }
        result = asyncio.run(scanner.run_scan(
            scan["website_url"], scan_mode=EXTENDED500_MODE, path_prefix=None,
            concurrency=concurrency, timeout_seconds=timeout_seconds, job_mode=True,
        ))
        output = validate_extended500_collection_result(scan, result)
        encoded = json.dumps({"ok": True, "result": output}, ensure_ascii=False,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
        if len(encoded) > MAX_RESULT_BYTES:
            raise Extended500CollectionRefused("collection_wire_payload_too_large")
    except Exception as exc:
        error = str(exc) if isinstance(exc, Extended500CollectionRefused) else "collector_child_failure"
        encoded = json.dumps({"ok": False, "error": error}).encode("utf-8")
    try:
        conn.send_bytes(encoded)
    except (BrokenPipeError, OSError):
        pass
    finally:
        conn.close()


def run_isolated_extended500_collection(
    scan: dict, *, enabled: bool = False, timeout_seconds: int = 120,
    concurrency: int = 4,
) -> dict:
    """Run private unreviewed collector in a fresh spawn; never serve as a route.

    The caller MUST additionally perform Agent B's fresh paid entitlement +
    active owner-slot authorization. 'enabled' is a development-only explicit
    permission, not the production flag or an entitlement.
    """
    if enabled is not True:
        raise Extended500CollectionRefused("extended500_collector_disabled")
    validate_extended500_collection_request(
        scan, timeout_seconds=timeout_seconds, concurrency=concurrency,
    )
    ctx = mp.get_context("spawn")
    parent, child = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=_collector_child, args=(child, dict(scan), timeout_seconds, concurrency),
                       daemon=True, name="fixlist-extended500-unreviewed")
    try:
        proc.start()
        child.close()
        if not parent.poll(timeout_seconds + 10):
            raise Extended500CollectionRefused("collector_process_deadline")
        try:
            message = parent.recv_bytes(MAX_RESULT_BYTES + 1024)
        except (EOFError, OSError, ValueError):
            raise Extended500CollectionRefused("collector_process_response_invalid") from None
        try:
            parsed = json.loads(message)
        except (ValueError, UnicodeError):
            raise Extended500CollectionRefused("collector_process_json_invalid") from None
        if not isinstance(parsed, dict) or parsed.get("ok") is not True:
            raise Extended500CollectionRefused(
                parsed.get("error", "collector_process_failed") if isinstance(parsed, dict)
                else "collector_process_failed"
            )
        output = parsed.get("result")
        if not isinstance(output, dict):
            raise Extended500CollectionRefused("collector_response_missing")
        # Re-validate strict count, privacy, ID binding AFTER process transport.
        return validate_extended500_collection_result(scan, output)
    finally:
        parent.close()
        child.close()
        if proc.is_alive():
            proc.terminate()
        if proc.pid is not None:
            proc.join(timeout=2)
            if proc.is_alive():
                proc.kill()
                proc.join(timeout=2)
