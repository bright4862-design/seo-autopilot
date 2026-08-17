import asyncio
import hashlib
import re
import time
from urllib.parse import urldefrag, urlparse

import httpx

from .artifact_filter import MAX_ARTIFACT_EVIDENCE, is_artifact_url, record_artifact
from .canonical_validation import validate_canonical_targets
from .redirect_validation import apply_redirect_evidence, fetch_with_redirect_evidence, summarize_redirect_evidence
from .extract import classify_template, extract_links, extract_page
from .market_scope import market_pair_prefix, path_within_scope
from .page_evidence_gate import (
    PAGE_EVIDENCE_GATE_VERSION,
    page_evidence_class,
    page_has_usable_html,
)
from .metadata_title_evidence import (
    METADATA_EVIDENCE_VERSION,
    TITLE_EVIDENCE_VERSION,
    classify_duplicate_title_context,
    is_generic_fallback_title,
    is_html_page_evidence,
    normalize_title_key,
    relative_evidence_url,
)
from .sampling import SAMPLING_VERSION, sampling_report, select_balanced_urls
from .scan_timing import (
    SITEMAP_TIME_RESERVATION_VERSION,
    allocate_scan_time_budget,
    build_crawl_failure_buckets,
    utc_now_iso,
)
from .render_followup import RENDER_FOLLOWUP_VERSION, run_render_followup
from .robots_policy import SCANNER_USER_AGENT, annotate_robots_evidence, load_robots_policy
from .security import is_public_http_url, safe_get
from .sitemap import load_sitemap_urls
from .url_frontier_policy import FRONTIER_POLICY_VERSION, classify_frontier_url

VERSION = "python_scanner_v3_bounded_request"
RENDER_EVIDENCE_VERSION = "render_evidence_v1"
FINAL_URL_DEDUP_VERSION = "final_url_dedup_v1_normalized_identity"

# The Python crawler does not derive an AI crawl policy (no InvokeLLM here), but it
# still emits the policy contract so AI Review keeps provenance. source="disabled"
# mirrors the Deno path when policy derivation is off.
DEFAULT_POLICY = {
    "rendering_mode": "unknown",
    "platform_guess": "",
    "priority_boost_patterns": [],
    "priority_deprioritize_patterns": [],
    "skip_patterns": [],
    "source": "disabled",
    "error": "",
}

SCAN_BUDGETS = {
    # timeout covers robots, sitemap discovery, crawling and post-processing.
    "basic": {"max_pages": 25, "timeout": 28, "fetch_timeout": 5, "max_sitemap_fetches": 4},
    "quick": {"max_pages": 40, "timeout": 40, "fetch_timeout": 6, "max_sitemap_fetches": 10},
    "deep": {"max_pages": 85, "timeout": 58, "fetch_timeout": 8, "max_sitemap_fetches": 24},
    "advanced": {"max_pages": 150, "timeout": 75, "fetch_timeout": 10, "max_sitemap_fetches": 40},
}

SITEMAP_DISCOVERY_LIMIT = 5000

# Durable scans can adapt when a site explicitly rate-limits a burst. Normal
# sites keep the existing concurrent crawler behavior. Once HTTP 429 is seen,
# request starts are paced for the rest of that crawl and the blocked URL gets
# one bounded retry. This is rate-limit cooperation, not a bot-protection bypass.
RATE_LIMIT_COOLDOWN_SECONDS = 3.0
RATE_LIMIT_REQUEST_INTERVAL_SECONDS = 0.5
RATE_LIMIT_PROACTIVE_REQUEST_INTERVAL_SECONDS = 1.0
RATE_LIMIT_BACKOFF_INTERVAL_SECONDS = 2.5
RATE_LIMIT_MAX_INTERVAL_SECONDS = 4.0
RATE_LIMIT_MAX_RETRIES = 8


def detect_rate_limit_profile(response) -> str:
    if response is None or int(getattr(response, "status_code", 0) or 0) >= 400:
        return ""
    server = str(response.headers.get("server", "")).lower()
    content_type = str(response.headers.get("content-type", "")).lower()
    if "cloudflare" not in server or (content_type and "html" not in content_type):
        return ""
    try:
        source = str(response.text or "")[:500_000].lower()
    except Exception:
        return ""
    shopify_markers = ("cdn.shopify.com", "shopify.theme", "myshopify.com", "shopify-section")
    if sum(1 for marker in shopify_markers if marker in source) >= 2:
        return "cloudflare_shopify"
    return ""


class _AdaptiveRateLimitPacer:
    def __init__(
        self,
        *,
        deadline: float,
        enabled: bool,
        start_active: bool = False,
        request_interval_seconds: float | None = None,
    ):
        self.deadline = float(deadline)
        self.enabled = bool(enabled)
        self.active = bool(self.enabled and start_active)
        interval = RATE_LIMIT_REQUEST_INTERVAL_SECONDS if request_interval_seconds is None else request_interval_seconds
        self.request_interval_seconds = max(0.0, float(interval))
        self.next_request_at = 0.0
        self.retry_count = 0
        self.recovered_count = 0
        self.saw_429 = False
        self._lock = asyncio.Lock()

    async def activate(self) -> None:
        if not self.enabled:
            return
        async with self._lock:
            now = time.monotonic()
            first_429 = not self.saw_429
            self.saw_429 = True
            self.active = True
            if first_429:
                self.request_interval_seconds = max(
                    self.request_interval_seconds,
                    float(RATE_LIMIT_BACKOFF_INTERVAL_SECONDS),
                )
            else:
                self.request_interval_seconds = min(
                    float(RATE_LIMIT_MAX_INTERVAL_SECONDS),
                    max(
                        float(RATE_LIMIT_BACKOFF_INTERVAL_SECONDS),
                        self.request_interval_seconds * 1.5,
                    ),
                )
            delay = RATE_LIMIT_COOLDOWN_SECONDS if first_429 else self.request_interval_seconds
            self.next_request_at = max(self.next_request_at, now + max(0.0, float(delay)))

    async def wait_for_slot(self) -> bool:
        if not self.enabled or not self.active:
            return True
        async with self._lock:
            now = time.monotonic()
            wait_seconds = max(0.0, self.next_request_at - now)
            if now + wait_seconds >= self.deadline:
                return False
            if wait_seconds:
                await asyncio.sleep(wait_seconds)
            now = time.monotonic()
            if now >= self.deadline:
                return False
            self.next_request_at = now + self.request_interval_seconds
            return True


TRUST_PATHS = ["/about", "/contact", "/privacy", "/terms", "/security", "/legal", "/mentions-legales", "/cgv"]


def compute_pages_found(
    pages: list[dict],
    queue: list[str],
    seen: set[str],
    sitemap_urls: list[str],
) -> int:
    """Report the broad discovery inventory independently of the crawl sample.

    Standard 150 caps fetched/analyzed pages, not URL discovery. A large sitemap
    may expose thousands of valid URLs even though only 150 representative pages
    enter the crawl and review pipeline.
    """
    return max(
        len(pages),
        len(sitemap_urls),
        len(pages) + len(queue),
        len(seen) + len(queue),
    )


# Asynchronous durable jobs are not bounded by the Base44 gateway's
# synchronous response window, so a trusted gateway may authorise a longer
# crawl. Page caps and robots enforcement are never affected by this ceiling.
ASYNC_JOB_TIMEOUT_CEILING = 120.0


def resolve_scan_budget(scan_mode: str, timeout_seconds: float | None = None, *, job_mode: bool = False) -> dict:
    """Return a per-request copy of the mode budget.

    Standard 150 normally owns a 75-second backend ceiling. A trusted gateway may
    request a shorter ceiling so the scanner can return collected evidence before
    the gateway platform kills the request. The override can only reduce runtime;
    it never raises the mode limit or page cap.
    """
    base = SCAN_BUDGETS.get(str(scan_mode or "advanced").lower(), SCAN_BUDGETS["advanced"])
    budget = dict(base)
    if timeout_seconds is None:
        return budget
    try:
        requested = float(timeout_seconds)
    except (TypeError, ValueError):
        return budget
    if job_mode:
        bounded = max(20.0, min(ASYNC_JOB_TIMEOUT_CEILING, requested))
    else:
        bounded = max(20.0, min(float(base["timeout"]), requested))
    budget["timeout"] = bounded
    budget["fetch_timeout"] = min(
        float(base.get("fetch_timeout", 10)),
        max(3.0, min(6.0, bounded / 8.0)),
    )
    budget["max_sitemap_fetches"] = min(
        int(base.get("max_sitemap_fetches", 10)),
        max(6, int(bounded // 2)),
    )
    return budget


async def run_scan(
    website_url: str,
    path_prefix: str | None = None,
    scan_mode: str = "advanced",
    concurrency: int = 8,
    timeout_seconds: float | None = None,
    job_mode: bool = False,
    **kwargs,
) -> dict:
    budget = resolve_scan_budget(scan_mode, timeout_seconds, job_mode=job_mode)
    fetch_timeout = float(budget.get("fetch_timeout", min(10, max(3, budget["timeout"] / 5))))
    max_sitemap_fetches = int(budget.get("max_sitemap_fetches", 10))
    scan_started_at = time.monotonic()
    scan_started_wall_clock = utc_now_iso()
    deadline = scan_started_at + budget["timeout"]
    start_url = normalize_url(website_url)
    if not start_url:
        return {"success": False, "version": VERSION, "error": "Missing or invalid website_url."}
    if not is_public_http_url(start_url):
        return {"success": False, "version": VERSION, "error": "website_url must resolve to a public host."}

    parsed_start = urlparse(start_url)
    origin = f"{parsed_start.scheme}://{parsed_start.netloc}"
    prefix, prefix_source, requested_seed_path = resolve_crawl_scope(path_prefix, parsed_start.path)
    scope_evidence = {
        "requested_path_prefix": prefix,
        "requested_seed_path": requested_seed_path,
        "effective_path_prefix": prefix,
        "scope_source": prefix_source,
        "requested_origin": origin,
        "effective_origin": origin,
        "origin_scope_source": "requested_origin",
        "multimarket_detected": False,
        "market_scope_required": False,
        "market_prefixes_detected": [],
        "sitemap_urls_excluded_outside_scope": 0,
        "internal_urls_excluded_outside_scope": 0,
        "frontier_policy_version": FRONTIER_POLICY_VERSION,
        "crawler_trap_urls_skipped": 0,
        "crawler_trap_reason_counts": {},
        "frontier_tracking_params_removed": 0,
    }

    pages: list[dict] = []
    queue: list[str] = []
    queued: set[str] = set()
    seen: set[str] = set()
    final_pages: dict[str, dict] = {}
    discovery: dict[str, dict] = {}
    artifacts: list[dict] = []

    def enqueue(url: str, source: str, source_page: str = "", link_text: str = "") -> None:
        clean = normalize_url(url)
        if not clean:
            if is_artifact_url(url):
                record_artifact(artifacts, url, source, source_page, link_text)
            return
        frontier = classify_frontier_url(clean)
        if not frontier.allowed:
            scope_evidence["crawler_trap_urls_skipped"] += 1
            reason = frontier.reason or "frontier_rejected"
            counts = scope_evidence["crawler_trap_reason_counts"]
            counts[reason] = int(counts.get(reason, 0)) + 1
            return
        clean = frontier.url
        if frontier.removed_params:
            scope_evidence["frontier_tracking_params_removed"] += len(frontier.removed_params)
        if is_artifact_url(clean):
            record_artifact(artifacts, clean, source, source_page, link_text)
            return
        if not same_origin(clean, origin):
            return
        clean_path = urlparse(clean).path or "/"
        if not path_within_scope(clean_path, prefix):
            if source == "internal_link":
                scope_evidence["internal_urls_excluded_outside_scope"] += 1
            return
        if prefix == "/" and scope_evidence.get("market_scope_required") and market_pair_prefix(clean_path):
            if source == "internal_link":
                scope_evidence["internal_urls_excluded_outside_scope"] += 1
            return
        if clean in queued or clean in seen:
            merge_discovery(discovery.setdefault(clean, empty_discovery()), source, source_page, link_text)
            return
        queued.add(clean)
        queue.append(clean)
        merge_discovery(discovery.setdefault(clean, empty_discovery()), source, source_page, link_text)

    enqueue(start_url, "seed")

    async with httpx.AsyncClient(
        timeout=fetch_timeout,
        follow_redirects=False,
        headers={"User-Agent": "Mozilla/5.0 (compatible; FixListPythonScanner/1.0)"},
    ) as client:
        robots_policy = await load_robots_policy(client, origin)
        rate_limit_profile = ""
        if not path_prefix and prefix == "/":
            try:
                landing = await safe_get(client, start_url)
                rate_limit_profile = detect_rate_limit_profile(landing) if job_mode else ""
                final_landing_url = str(getattr(landing, "url", start_url) or start_url) if landing is not None else start_url
                landing_status = int(getattr(landing, "status_code", 0) or 0) if landing is not None else 0
                landing_origin = url_origin(final_landing_url)
                if (
                    200 <= landing_status < 300
                    and landing_origin
                    and is_www_origin_alias(start_url, final_landing_url)
                ):
                    origin = landing_origin
                    scope_evidence["effective_origin"] = origin
                    scope_evidence["origin_scope_source"] = "verified_www_alias_redirect"
                    robots_policy = await load_robots_policy(client, origin)
                redirected_market = market_pair_prefix(final_landing_url)
                if redirected_market:
                    prefix = redirected_market
                    scope_evidence["effective_path_prefix"] = prefix
                    scope_evidence["scope_source"] = "redirect_market_path"
            except Exception:
                pass

        max_pages = budget["max_pages"]
        timing_budget = allocate_scan_time_budget(
            scan_started_at,
            budget["timeout"],
            fetch_timeout,
            now=time.monotonic(),
        )
        sitemap_diagnostics = {
            "version": SITEMAP_TIME_RESERVATION_VERSION,
            "sitemap_started_at": utc_now_iso(),
            "sitemap_budget_seconds": round(timing_budget["sitemap_budget_seconds"], 3),
            "crawl_reserved_seconds": round(timing_budget["crawl_reserved_seconds"], 3),
            "response_reserved_seconds": round(timing_budget["response_reserved_seconds"], 3),
        }
        sitemap_started_monotonic = time.monotonic()
        sitemap_urls = await load_sitemap_urls(
            client, origin, prefix, SITEMAP_DISCOVERY_LIMIT, artifacts,
            scope_evidence=scope_evidence, deadline=timing_budget["sitemap_deadline"],
            max_fetches=max_sitemap_fetches, diagnostics=sitemap_diagnostics,
        )
        sitemap_diagnostics["sitemap_elapsed_ms"] = round((time.monotonic() - sitemap_started_monotonic) * 1000)
        sitemap_diagnostics["sitemap_urls_discovered"] = len(sitemap_urls)
        family_of = lambda url: classify_template(urlparse(url).path or "/")
        path_of = lambda url: urlparse(url).path or "/"
        sampled_sitemap_urls = select_balanced_urls(sitemap_urls, family_of, path_of, max(0, max_pages - 1))
        sampling_evidence = sampling_report(sitemap_urls, sampled_sitemap_urls, family_of, path_of)
        scope_evidence["effective_path_prefix"] = prefix
        sampling_evidence["crawl_scope"] = dict(scope_evidence)
        for url in sampled_sitemap_urls:
            enqueue(url, "sitemap", "/sitemap.xml", "")

        crawl_started_at = utc_now_iso()
        crawl_started_monotonic = time.monotonic()
        initial_queue_size = len(queue)
        state_lock = asyncio.Lock()
        crawl_state = {
            "claimed": 0,
            "in_flight": 0,
            "final_url_duplicates_deduped": 0,
            "final_url_duplicate_examples": [],
        }
        rate_limit_pacer = _AdaptiveRateLimitPacer(
            deadline=timing_budget["crawl_deadline"],
            enabled=job_mode,
            start_active=bool(rate_limit_profile),
            request_interval_seconds=(
                RATE_LIMIT_PROACTIVE_REQUEST_INTERVAL_SECONDS
                if rate_limit_profile
                else RATE_LIMIT_REQUEST_INTERVAL_SECONDS
            ),
        )

        async def worker() -> None:
            while True:
                target = None
                snapshot = None
                async with state_lock:
                    if (
                        time.monotonic() >= timing_budget["crawl_deadline"]
                        or len(pages) + crawl_state["in_flight"] >= max_pages
                        or crawl_state["claimed"] >= max_pages * 8
                    ):
                        return
                    while queue:
                        candidate = queue.pop(0)
                        queued.discard(candidate)
                        if candidate in seen:
                            continue
                        target = candidate
                        break
                    if target is None:
                        # Nothing queued: stop only when no other worker might enqueue more.
                        if crawl_state["in_flight"] == 0:
                            return
                    else:
                        seen.add(target)
                        crawl_state["claimed"] += 1
                        crawl_state["in_flight"] += 1
                        # Snapshot discovery lists so a concurrent merge can't mutate mid-read.
                        record = discovery.get(target, empty_discovery())
                        snapshot = {key: list(value) for key, value in record.items()}
                if target is None:
                    await asyncio.sleep(0.01)
                    continue

                page = None
                discovered = []
                try:
                    if robots_policy.allowed(SCANNER_USER_AGENT, target) is False:
                        page = extract_page(
                            "",
                            target,
                            target,
                            0,
                            "",
                            snapshot,
                            fetch_error="blocked_by_robots_txt",
                        )
                    else:
                        if not await rate_limit_pacer.wait_for_slot():
                            return
                        page = await fetch_and_extract(client, target, snapshot, robots_policy=robots_policy)
                        if rate_limit_pacer.enabled and int(page.get("status_code") or 0) == 429:
                            await rate_limit_pacer.activate()
                            if rate_limit_pacer.retry_count < RATE_LIMIT_MAX_RETRIES and await rate_limit_pacer.wait_for_slot():
                                rate_limit_pacer.retry_count += 1
                                retry_page = await fetch_and_extract(client, target, snapshot, robots_policy=robots_policy)
                                page = retry_page
                                retry_status = int(page.get("status_code") or 0)
                                if 200 <= retry_status < 400:
                                    rate_limit_pacer.recovered_count += 1
                                elif retry_status == 429:
                                    await rate_limit_pacer.activate()
                    annotate_robots_evidence(page, robots_policy, target)
                    html = page.pop("_html", "")
                    # Parse links OUTSIDE the lock (CPU-bound) so workers don't block each other.
                    discovered = extract_links(html, page.get("final_url") or target) if (page.get("status_code") == 200 and html) else []
                except Exception:
                    page = extract_page("", target, target, 0, "", snapshot, fetch_error="worker_processing_failed")
                    discovered = []
                finally:
                    async with state_lock:
                        if page is not None:
                            identity = final_url_identity(page.get("final_url") or page.get("url") or "")
                            retained = final_pages.get(identity) if identity else None
                            if retained is not None:
                                merge_duplicate_page_evidence(retained, page)
                                crawl_state["final_url_duplicates_deduped"] += 1
                                if len(crawl_state["final_url_duplicate_examples"]) < 10:
                                    crawl_state["final_url_duplicate_examples"].append({
                                        "requested_url": page.get("url") or "",
                                        "final_url": page.get("final_url") or page.get("url") or "",
                                        "retained_url": retained.get("url") or "",
                                    })
                            else:
                                pages.append(page)
                                if identity:
                                    final_pages[identity] = page
                        crawl_state["in_flight"] -= 1
                        for link in discovered:
                            if len(queue) + len(seen) >= max_pages * 8:
                                break
                            enqueue(link["href"], "internal_link", page.get("path") or "", link.get("text") or "")

        workers = [asyncio.create_task(worker()) for _ in range(max(1, concurrency))]
        await asyncio.gather(*workers)
        crawl_elapsed_ms = round((time.monotonic() - crawl_started_monotonic) * 1000)
        final_queue_size = len(queue)
        # Enforce the selected scan budget again after all concurrent sources finish.
        # Downstream validation and review must never receive more pages than the mode allows.
        if len(pages) > max_pages:
            pages = pages[:max_pages]
        canonical_target_evidence = await validate_canonical_targets(
            client,
            pages,
            robots_policy,
            deadline=timing_budget["crawl_deadline"],
        )
        redirect_evidence = summarize_redirect_evidence(pages)

    findings = build_findings(pages)
    findings.extend(duplicate_title_findings(pages))
    findings.extend(duplicate_casing_findings(pages))
    grouped = group_findings(findings)
    verified_failed = [page_evidence(page) for page in pages if is_verified_failed(page)]
    artifacts = dedupe_artifacts(artifacts)[:MAX_ARTIFACT_EVIDENCE]
    health_score = calculate_health_score(pages, grouped)
    pages_found = compute_pages_found(pages, queue, seen, sitemap_urls)
    render_evidence = build_render_evidence(pages)
    material_render_risk = render_evidence["evidence_state"] == "material_client_rendering_risk"
    render_followup = await run_render_followup(
        pages if material_render_risk else [],
        render_page=kwargs.get("_render_page") if material_render_risk else None,
    )
    render_evidence["browser_followup_version"] = RENDER_FOLLOWUP_VERSION
    render_evidence["browser_followup"] = render_followup
    elapsed_ms = round((time.monotonic() - scan_started_at) * 1000)
    deadline_reached = time.monotonic() >= deadline
    crawl_deadline_reached = time.monotonic() >= timing_budget["crawl_deadline"]
    failure_reason_buckets = build_crawl_failure_buckets(pages)
    failed_fetch_count = sum(failure_reason_buckets.values())
    crawl_timing = {
        **sitemap_diagnostics,
        "version": SITEMAP_TIME_RESERVATION_VERSION,
        "scan_started_at": scan_started_wall_clock,
        "crawl_started_at": crawl_started_at,
        "crawl_elapsed_ms": crawl_elapsed_ms,
        "initial_queue_size": initial_queue_size,
        "final_queue_size": final_queue_size,
        "crawl_deadline_reached": crawl_deadline_reached,
        "queue_exhausted": final_queue_size == 0 and len(pages) < max_pages and not crawl_deadline_reached,
        "failed_fetch_count": failed_fetch_count,
        "failure_reason_buckets": failure_reason_buckets,
        "rate_limit_throttle_activated": rate_limit_pacer.active,
        "rate_limit_proactive_profile": rate_limit_profile,
        "rate_limit_retry_count": rate_limit_pacer.retry_count,
        "rate_limit_recovered_count": rate_limit_pacer.recovered_count,
        "rate_limit_final_interval_seconds": round(rate_limit_pacer.request_interval_seconds, 3),
        "final_url_dedup_version": FINAL_URL_DEDUP_VERSION,
        "final_url_duplicates_deduped": crawl_state["final_url_duplicates_deduped"],
        "final_url_duplicate_examples": crawl_state["final_url_duplicate_examples"],
    }
    crawl_warnings = []
    if deadline_reached:
        crawl_warnings.append(f"The {scan_mode} scan reached its bounded {budget['timeout']}-second backend budget and returned collected evidence.")
    if sitemap_diagnostics.get("sitemap_budget_exhausted"):
        crawl_warnings.append(
            f"Sitemap discovery reached its reserved {sitemap_diagnostics.get('sitemap_budget_seconds', 0)}-second budget; "
            f"page crawling continued with {len(sitemap_urls)} discovered sitemap URLs."
        )
    if scope_evidence.get("market_scope_required"):
        crawl_warnings.append(
            "Multiple country/language markets were detected on the global root. Submit one market URL, such as /fr/fr/, for a coherent audit."
        )
    if render_evidence["evidence_state"] == "material_client_rendering_risk":
        crawl_warnings.append(
            f'{render_evidence["client_rendering_suspected_pages"]} successful pages returned thin app-shell HTML; '
            "rendered content may need a browser-based follow-up."
        )

    return {
        "success": True,
        "version": VERSION,
        "scanner_version": VERSION,
        "scanner_profile": "python_screaming_frog_lite_v1",
        "metadata_evidence_version": METADATA_EVIDENCE_VERSION,
        "title_evidence_version": TITLE_EVIDENCE_VERSION,
        "page_evidence_gate_version": PAGE_EVIDENCE_GATE_VERSION,
        "sampling_version": SAMPLING_VERSION,
        "sampling_evidence": sampling_evidence,
        "sitemap_time_reservation_version": SITEMAP_TIME_RESERVATION_VERSION,
        "crawl_timing": crawl_timing,
        "render_evidence_version": RENDER_EVIDENCE_VERSION,
        "render_evidence": render_evidence,
        "screaming_frog_lite_enabled": True,
        "website_url": start_url,
        "normalized_url": start_url,
        "requested_path_prefix": scope_evidence.get("requested_path_prefix", "/"),
        "crawl_scope": dict(scope_evidence),
        "robots_txt_evidence": robots_policy.evidence(),
        "canonical_target_evidence": canonical_target_evidence,
        "redirect_evidence": redirect_evidence,
        "scan_mode": scan_mode,
        "scanner_elapsed_ms": elapsed_ms,
        "scanner_total_budget_seconds": budget["timeout"],
        "scan_deadline_reached": deadline_reached,
        "pages_crawled": len(pages),
        "pages_found": pages_found,
        "queued_remaining": len(queue),
        "pages": pages,
        "crawled_pages": pages,
        "raw_findings": findings,
        "grouped_findings": grouped,
        "findings": grouped,
        "recommendations": grouped,
        "crawl_policy": DEFAULT_POLICY,
        "crawl_policy_source": DEFAULT_POLICY["source"],
        "health_score": health_score,
        "scan_summary": build_scan_summary(pages, grouped, health_score, pages_found, len(artifacts)),
        "verified_failed_pages": verified_failed,
        "suspicious_url_artifacts": artifacts,
        "verified_failed_page_count": len(verified_failed),
        "suspicious_url_artifact_count": len(artifacts),
        "url_evidence_summary": build_evidence_summary(pages, len(artifacts)),
        "technical_audit_summary": {
            "scanner_version": VERSION,
            "metadata_evidence_version": METADATA_EVIDENCE_VERSION,
            "title_evidence_version": TITLE_EVIDENCE_VERSION,
            "page_evidence_gate_version": PAGE_EVIDENCE_GATE_VERSION,
            "sitemap_time_reservation_version": SITEMAP_TIME_RESERVATION_VERSION,
            "final_url_dedup_version": FINAL_URL_DEDUP_VERSION,
            "final_url_duplicates_deduped": crawl_state["final_url_duplicates_deduped"],
            "final_url_duplicate_examples": crawl_state["final_url_duplicate_examples"],
            "crawl_timing": crawl_timing,
            "scanner_elapsed_ms": elapsed_ms,
            "scanner_total_budget_seconds": budget["timeout"],
            "scan_deadline_reached": deadline_reached,
            "pages_crawled": len(pages),
            "pages_found": pages_found,
            "failed_pages": sum(1 for page in pages if is_verified_failed(page)),
            "verified_failed_pages": len(verified_failed),
            "suspicious_url_artifacts": len(artifacts),
            "url_evidence_summary": build_evidence_summary(pages, len(artifacts)),
            "crawl_policy": DEFAULT_POLICY,
            "crawl_policy_source": DEFAULT_POLICY["source"],
            "crawl_scope": dict(scope_evidence),
            "canonical_target_evidence": canonical_target_evidence,
            "redirect_evidence": redirect_evidence,
            "render_evidence_version": RENDER_EVIDENCE_VERSION,
            "render_evidence": render_evidence,
            "duplicate_casing_routes": detect_duplicate_casing_routes(pages),
            "screaming_frog_lite_enabled": True,
        },
        "crawl_warnings": crawl_warnings,
    }


def build_render_evidence(pages: list[dict]) -> dict:
    successful = [
        page for page in pages
        if 200 <= int(page.get("status_code") or 0) < 400
        and not page.get("fetch_error")
        and not page_is_redirect_source(page)
    ]
    suspected = [page for page in successful if page.get("client_rendering_suspected") is True]
    evaluated = len(successful)
    ratio = round(len(suspected) / evaluated, 4) if evaluated else 0.0
    material = len(suspected) >= 2 and ratio >= 0.2
    return {
        "version": RENDER_EVIDENCE_VERSION,
        "pages_evaluated": evaluated,
        "client_rendering_suspected_pages": len(suspected),
        "suspected_ratio": ratio,
        "evidence_state": "material_client_rendering_risk" if material else (
            "isolated_client_rendering_signal" if suspected else "raw_html_sufficient"
        ),
        "rendering_mode": "browser_follow_up_recommended" if material else "raw_html_first",
        "representative_pages": [
            page.get("path") or page.get("final_url") or page.get("url") or "/"
            for page in suspected[:10]
        ],
    }


async def fetch_and_extract(
    client: httpx.AsyncClient,
    url: str,
    discovery: dict,
    robots_policy=None,
) -> dict:
    if not is_public_http_url(url):
        return extract_page("", url, url, 0, "", discovery, fetch_error="blocked_non_public_host")
    try:
        redirect_evidence = None
        if robots_policy is None:
            response = await safe_get(client, url)
            if response is None:
                return extract_page("", url, url, 0, "", discovery, fetch_error="blocked_non_public_redirect")
        else:
            response, redirect_evidence = await fetch_with_redirect_evidence(
                client,
                url,
                robots_policy,
            )
            if response is None:
                page = extract_page(
                    "",
                    url,
                    str(redirect_evidence.get("destination_url") or url),
                    0,
                    "",
                    discovery,
                    fetch_error=str(redirect_evidence.get("fetch_error") or "redirect_validation_failed"),
                )
                apply_redirect_evidence(page, redirect_evidence)
                return page

        content_type = response.headers.get("content-type", "")
        html = response.text if "html" in content_type or "xml" in content_type or not content_type else ""
        page = extract_page(
            html,
            url,
            str(response.url),
            response.status_code,
            content_type,
            discovery,
            response_headers={"x-robots-tag": response.headers.get_list("x-robots-tag")},
        )
        if redirect_evidence is not None:
            apply_redirect_evidence(page, redirect_evidence)
        page["_html"] = html
        return page
    except Exception as exc:
        return extract_page("", url, url, 0, "", discovery, fetch_error=str(exc)[:220])


def build_findings(pages: list[dict]) -> list[dict]:
    findings: list[dict] = []
    for page in pages:
        path = page.get("path") or "/"
        if page.get("url_confidence") == "crawler_artifact":
            continue
        redirect_finding = redirect_finding_for_page(page)
        if redirect_finding is not None:
            findings.append(redirect_finding)
        if page_is_redirect_source(page):
            continue
        if sitemap_indexability_conflict(page):
            findings.append(create_finding(
                rule="sitemap_indexability_conflict",
                category="indexability",
                priority="medium",
                title="Remove non-indexable URLs from the sitemap",
                page_url=path,
                current_value=str(page.get("indexability_state") or "Not indexable"),
                explanation=(
                    "This URL was explicitly listed in a sitemap but the scanner found a "
                    "noindex directive or a Googlebot robots.txt block."
                ),
                recommendation=(
                    "Remove the URL from the sitemap unless it should be indexable. If it should "
                    "be indexed, resolve the noindex or Googlebot block first."
                ),
                difficulty="developer",
                source_pages=page.get("source_pages", []),
                link_text_samples=page.get("link_text_samples", []),
            ))
        canonical_finding = canonical_target_finding(page)
        if canonical_finding is not None:
            findings.append(canonical_finding)
        if str(page.get("fetch_error") or "").startswith("blocked_"):
            continue
        status_code = int(page.get("status_code") or 0)
        evidence_class = page_evidence_class(page)
        if evidence_class == "failed_access":
            is_seed = "seed" in set(page.get("discovered_from") or [])
            rule = "site_access_limited" if is_seed else ("rate_limited_page" if status_code == 429 else "failed_page")
            title = "We could not fully check your site this time" if is_seed else ("Check pages blocked by rate limiting" if status_code == 429 else "Verify a page that did not load during the scan")
            explanation = ("Your site redirected or responded in a way the scanner could not safely verify. This does not necessarily mean anything is wrong for visitors or Google." if is_seed else "The scanner could not retrieve usable HTML for this URL. This is access evidence, not proof that page elements are missing.")
            recommendation = ("Try again later. If it keeps happening, ask your web person to check hosting, CDN, firewall, bot-protection, DNS, and redirect logs." if is_seed else "Check server, CDN, firewall, bot-protection, and redirect logs before changing page content.")
            finding = create_finding(
                rule=rule,
                category="web_dev",
                priority="medium" if is_seed or status_code == 0 else "high" if status_code == 429 or status_code >= 500 else "medium",
                title=title,
                page_url=path,
                current_value=page.get("fetch_error") or f"HTTP {status_code}",
                explanation=explanation,
                recommendation=recommendation,
                difficulty="developer",
                source_pages=page.get("source_pages", []),
                link_text_samples=page.get("link_text_samples", []),
            )
            finding.update({
                "evidence_status": "needs_verification" if status_code in {0, 429} or is_seed else "confirmed",
                "verification_state": "needs_verification",
                "non_scoring": True,
                "score_impact": 0,
                "page_evidence_class": evidence_class,
                "evidence_gate_version": PAGE_EVIDENCE_GATE_VERSION,
                "confidence_score": 70 if status_code in {0, 429} or is_seed else 92,
            })
            findings.append(finding)
            continue
        if not page_has_usable_html(page):
            continue
        if not page.get("title"):
            findings.append(create_finding("missing_title", "meta_title", "medium", "Add a clear search title", path, explanation="This page is missing a title.", recommendation="Add a short, specific page title."))
        else:
            if page.get("title_is_generic_fallback") or is_generic_fallback_title(page.get("title")):
                finding = create_finding(
                    "generic_fallback_title",
                    "meta_title",
                    "medium",
                    "Replace a generic fallback search title",
                    path,
                    current_value=str(page.get("title") or ""),
                    explanation="This page uses a generic CMS or fallback title instead of describing the page.",
                    recommendation="Replace the fallback with a specific title generated from the page or shared template.",
                )
                finding.update({"title_evidence_version": TITLE_EVIDENCE_VERSION, "non_scoring": True, "score_impact": 0})
                findings.append(finding)
            if page.get("title_width_state") == "over_pixel_limit":
                finding = create_finding(
                    "title_over_pixel_limit",
                    "meta_title",
                    "low",
                    "Shorten a search title likely to truncate",
                    path,
                    current_value=f"{page.get('title_pixel_width_estimate', 0)} estimated pixels: {page.get('title', '')}",
                    explanation="The title is likely wider than the common search-result display area.",
                    recommendation="Shorten the title while preserving the main topic and commercial intent.",
                )
                finding.update({"title_evidence_version": TITLE_EVIDENCE_VERSION, "non_scoring": True, "score_impact": 0})
                findings.append(finding)
        metadata_state = str(page.get("meta_description_state") or "")
        if not metadata_state:
            metadata_state = "present_valid" if page.get("meta_description") else "missing"
        if page.get("estimated_page_intent") != "internal_or_auth":
            if metadata_state == "missing":
                finding = create_finding("missing_meta_description", "meta_description", "medium", "Add a clear search description", path, explanation="This page has no standard meta-description element.", recommendation="Add a short description that explains the page and why someone should click.")
                finding.update({"metadata_evidence_version": METADATA_EVIDENCE_VERSION, "meta_description_state": metadata_state})
                findings.append(finding)
            elif metadata_state == "present_empty":
                finding = create_finding("empty_meta_description", "meta_description", "medium", "Fill an empty search description", path, explanation="A meta-description element exists, but its content value is empty.", recommendation="Populate the existing description field with a concise, page-specific summary.")
                finding.update({"metadata_evidence_version": METADATA_EVIDENCE_VERSION, "meta_description_state": metadata_state})
                findings.append(finding)
            elif metadata_state == "malformed":
                finding = create_finding("malformed_meta_description", "meta_description", "medium", "Fix malformed meta-description markup", path, explanation="A meta-description element exists without a usable content attribute.", recommendation="Output one valid meta name=\"description\" element with a non-empty content value.")
                finding.update({"metadata_evidence_version": METADATA_EVIDENCE_VERSION, "meta_description_state": metadata_state})
                findings.append(finding)
        if page.get("h1_count", 0) == 0 and page.get("estimated_page_intent") != "internal_or_auth":
            findings.append(create_finding("missing_h1", "thin_content", "medium", "Add one clear page heading", path, explanation="The page does not have a clear H1 heading.", recommendation="Add one main heading that matches the page purpose."))
        if page.get("h1_count", 0) > 1:
            findings.append(create_finding("multiple_h1", "thin_content", "low", "Use one main page heading", path, explanation="The page has more than one H1 heading.", recommendation="Keep one H1 as the main page heading and make the rest H2/H3 headings."))
        if not page.get("canonical") and page.get("indexable"):
            findings.append(create_finding("canonical_missing", "canonical", "medium", "Add a canonical URL", path, explanation="The page does not expose a canonical URL.", recommendation="Add a self-referencing canonical or point to the preferred version.", difficulty="developer"))
        missing_alt = int(page.get("image_missing_alt_count") or 0)
        if missing_alt > 0:
            findings.append(create_finding("image_alt_text", "image_alt_text", "medium" if missing_alt >= 10 else "low", "Add useful image descriptions", path, current_value=f"{missing_alt} images missing alt text", explanation="Some meaningful images may not have text descriptions.", recommendation="Add short, specific alt text to meaningful images."))
    return findings




def page_is_redirect_source(page: dict) -> bool:
    state = str(page.get("redirect_state") or "")
    return int(page.get("redirect_hop_count") or 0) > 0 or state in {
        "redirect_loop",
        "redirect_missing_location",
        "redirect_invalid_location",
        "redirect_chain_limit_exceeded",
        "redirect_destination_blocked_by_robots",
        "redirect_destination_failed",
        "blocked_non_public_redirect",
    }


def redirect_finding_for_page(page: dict) -> dict | None:
    if not page_is_redirect_source(page):
        return None

    state = str(page.get("redirect_state") or "")
    sources = set(page.get("discovered_from") or [])
    source_path = str(page.get("redirect_source_path") or urlparse(str(page.get("url") or "")).path or "/")
    destination = str(page.get("redirect_destination_url") or page.get("final_url") or "")
    destination_status = int(page.get("redirect_destination_status_code") or 0)
    destination_indexability = str(page.get("redirect_destination_indexability_state") or "")
    chain = [str(item) for item in (page.get("redirect_chain") or []) if str(item)]
    hop_count = int(page.get("redirect_hop_count") or 0)

    if state == "redirect_loop":
        details = (
            "redirect_loop", "high", "Remove a redirect loop",
            "This URL redirects back to a URL already visited in the same redirect path, so crawlers and visitors cannot reach a final page.",
            "Choose one final destination and update each redirect so the path ends there without returning to an earlier URL.",
        )
    elif state in {"redirect_missing_location", "redirect_invalid_location"}:
        details = (
            "redirect_invalid_response", "high", "Fix a redirect with no valid destination",
            "This URL returned a redirect response without a usable destination URL.",
            "Add a valid absolute or relative Location header that points directly to the intended final page.",
        )
    elif state == "redirect_chain_limit_exceeded":
        details = (
            "redirect_chain_limit", "high", "Fix an unresolved redirect chain",
            "The redirect path exceeded the scanner's bounded hop limit before reaching a final page.",
            "Replace the chain with one direct redirect to the final live destination.",
        )
    elif state in {"redirect_destination_failed", "blocked_non_public_redirect"} or destination_status >= 400 or destination_indexability == "Failed":
        details = (
            "redirect_destination_failed", "high", "Fix a redirect that ends on an unavailable page",
            "The redirect destination failed to load, returned an error, or could not be safely reached.",
            "Point the source URL directly to a live 200-status destination or restore the intended destination page.",
        )
    elif state == "redirect_destination_blocked_by_robots" or destination_indexability == "Blocked by robots.txt":
        details = (
            "redirect_destination_blocked", "medium", "Review a redirect to a robots-blocked destination",
            "The redirect ends on a URL that Googlebot or the scanner is blocked from crawling.",
            "Confirm the destination is intentional and allow search crawlers to access it when the page should appear in search.",
        )
    elif destination_indexability == "Noindexed":
        details = (
            "redirect_destination_noindex", "high", "Fix a redirect to a noindexed destination",
            "The redirect ends on a page that explicitly tells search engines not to index it.",
            "Use an indexable final destination or remove the noindex directive when the destination should rank.",
        )
    elif state == "redirect_chain" or hop_count >= 2:
        details = (
            "redirect_chain", "medium", "Shorten a redirect chain",
            "This URL passes through multiple redirects before reaching the final page.",
            "Update the first redirect and any links or sitemap entries to point directly to the final destination.",
        )
    elif "sitemap" in sources:
        details = (
            "sitemap_redirect", "medium", "Replace a redirecting URL in the sitemap",
            "The sitemap lists a URL that redirects instead of the final indexable destination.",
            "Replace the sitemap entry with the final 200-status canonical URL.",
        )
    elif "internal_link" in sources:
        details = (
            "internal_link_redirect", "low", "Update an internal link that passes through a redirect",
            "An internal link points to an old URL and makes crawlers and visitors take an unnecessary redirect.",
            "Update the internal link to point directly to the final destination.",
        )
    else:
        return None

    rule, priority, title, explanation, recommendation = details
    current_parts = []
    if chain:
        current_parts.append(" → ".join(chain[:8]))
    elif destination:
        current_parts.append(destination)
    if destination_status:
        current_parts.append(f"destination HTTP {destination_status}")
    if destination_indexability:
        current_parts.append(f"destination: {destination_indexability}")

    finding = create_finding(
        rule=rule,
        category="indexability",
        priority=priority,
        title=title,
        page_url=source_path,
        current_value=" — ".join(current_parts),
        explanation=explanation,
        recommendation=recommendation,
        difficulty="developer",
        source_pages=page.get("source_pages", []),
        link_text_samples=page.get("link_text_samples", []),
    )
    finding.update({
        "redirect_state": state,
        "redirect_hop_count": hop_count,
        "redirect_chain": chain,
        "redirect_destination_url": destination,
        "redirect_destination_status_code": destination_status,
        "redirect_destination_indexability_state": destination_indexability,
        "redirect_evidence_version": page.get("redirect_evidence_version"),
        "evidence_status": "confirmed",
        "verification_state": "verified",
        "confidence_score": 94,
    })
    return finding

def canonical_target_finding(page: dict) -> dict | None:
    state = str(page.get("canonical_target_state") or "")
    target = str(page.get("canonical_target_url") or page.get("canonical") or "")
    status_code = int(page.get("canonical_target_status_code") or 0)
    redirect_location = str(page.get("canonical_target_redirect_location") or "")
    target_canonical = str(page.get("canonical_target_declared_canonical") or "")
    mapping = {
        "target_redirected": (
            "canonical_target_redirect",
            "medium",
            "Update a canonical URL that points to a redirect",
            "The declared canonical URL redirects instead of resolving directly.",
            "Point the canonical directly to the final 200-status preferred URL.",
        ),
        "target_failed": (
            "canonical_target_failed",
            "high",
            "Fix a canonical URL that points to an unavailable page",
            "The declared canonical target failed to load or returned an error.",
            "Choose a live, indexable preferred URL and update the canonical reference.",
        ),
        "target_noindexed": (
            "canonical_target_noindex",
            "high",
            "Fix a canonical URL that points to a noindexed page",
            "The page asks search engines to consolidate signals into a target that is explicitly noindexed.",
            "Use an indexable preferred URL or remove the conflicting noindex directive from the intended target.",
        ),
        "target_blocked_by_robots": (
            "canonical_target_blocked",
            "medium",
            "Review a canonical URL that points to a robots-blocked page",
            "Googlebot is blocked from crawling the declared canonical target, so the consolidation signal may be hard to verify.",
            "Confirm the intended preferred URL and allow Googlebot to crawl it when appropriate.",
        ),
        "canonical_chain": (
            "canonical_chain",
            "medium",
            "Replace a canonical chain with the final preferred URL",
            "The declared canonical target itself points to another canonical URL.",
            "Point the source page directly to the final preferred canonical destination.",
        ),
        "canonical_loop": (
            "canonical_loop",
            "high",
            "Remove a canonical loop",
            "The source and target canonical declarations point back to each other.",
            "Choose one preferred URL and make every duplicate point directly to it without a loop.",
        ),
        "cross_domain_needs_verification": (
            "canonical_cross_domain",
            "low",
            "Verify a cross-domain canonical URL",
            "This page declares a preferred URL on another domain. That can be intentional, but ownership and matching content require confirmation.",
            "Confirm both domains are controlled by the same organization and that the external URL is the intended equivalent page.",
        ),
        "invalid_target": (
            "canonical_target_failed",
            "high",
            "Fix an invalid canonical target",
            "The declared canonical target is invalid or does not resolve to a public HTTP URL.",
            "Replace it with a valid absolute HTTPS URL for the preferred page.",
        ),
    }
    details = mapping.get(state)
    if details is None:
        return None
    rule, priority, title, explanation, recommendation = details
    current_parts = [target]
    if status_code:
        current_parts.append(f"HTTP {status_code}")
    if redirect_location:
        current_parts.append(f"redirects to {redirect_location}")
    if target_canonical:
        current_parts.append(f"target canonical: {target_canonical}")
    finding = create_finding(
        rule=rule,
        category="canonical",
        priority=priority,
        title=title,
        page_url=page.get("path") or "/",
        current_value=" — ".join(part for part in current_parts if part),
        explanation=explanation,
        recommendation=recommendation,
        difficulty="developer",
        source_pages=page.get("source_pages", []),
        link_text_samples=page.get("link_text_samples", []),
    )
    finding.update({
        "canonical_target_url": target,
        "canonical_target_state": state,
        "canonical_target_status_code": status_code,
        "canonical_target_redirect_location": redirect_location,
        "canonical_target_declared_canonical": target_canonical,
        "canonical_target_evidence_source": page.get("canonical_target_evidence_source"),
        "evidence_status": "needs_verification" if state == "cross_domain_needs_verification" else "confirmed",
        "verification_state": "needs_verification" if state == "cross_domain_needs_verification" else "verified",
        "limitation_code": "cross_domain_canonical_requires_confirmation" if state == "cross_domain_needs_verification" else "",
        "confidence_score": 70 if state == "cross_domain_needs_verification" else 94,
    })
    return finding


def sitemap_indexability_conflict(page: dict) -> bool:
    if "sitemap" not in set(page.get("discovered_from") or []):
        return False
    return str(page.get("indexability_state") or "") in {
        "Noindexed",
        "Blocked by robots.txt",
    }


def create_finding(rule: str, category: str, priority: str, title: str, page_url: str, current_value: str = "", explanation: str = "", recommendation: str = "", difficulty: str = "easy", source_pages: list[str] | None = None, link_text_samples: list[str] | None = None) -> dict:
    developer = difficulty == "developer" or any(token in f"{rule} {category} {title}" for token in ["429", "schema", "canonical", "web_dev"])
    finding_id = stable_id(f"{rule}|{page_url}|{title}")
    return {
        "id": finding_id,
        "fix_id": finding_id,
        "rule": rule,
        "category": category,
        "customer_category": friendly_category(category),
        "priority": priority,
        "difficulty": "developer" if developer else difficulty,
        "status": "needs_developer" if developer else "needs_approval",
        "title": title,
        "issue_title": title,
        "plain_english_explanation": explanation,
        "plain_english_summary": explanation,
        "why_it_matters": explanation,
        "current_value": current_value,
        "recommended_value": recommendation,
        "recommendation": recommendation,
        "ai_recommendation": recommendation,
        "page_url": page_url,
        "affected_pages": [page_url],
        "page_template_family": classify_template(page_url),
        "primary_defect_class": "blocked_access" if ("429" in rule or "blocked" in rule) else ("structural" if developer else "content"),
        "source_pages": list(dict.fromkeys(source_pages or [])),
        "link_text_samples": list(dict.fromkeys(link_text_samples or [])),
        "requires_developer": developer,
        "requires_approval": not developer,
        "can_auto_fix": False,
        "who_can_do_this": "your_web_person" if developer else "you",
        "confidence_score": 88,
    }


FAILURE_RULES = {"rate_limited_page", "failed_page", "server_error", "404_error", "410_error"}
TEMPLATE_RULES = {"client_rendering", "canonical_missing", "canonical_target_redirect", "canonical_target_failed", "canonical_target_noindex", "canonical_target_blocked", "canonical_chain", "canonical_loop", "canonical_cross_domain", "redirect_loop", "redirect_invalid_response", "redirect_chain_limit", "redirect_destination_failed", "redirect_destination_blocked", "redirect_destination_noindex", "redirect_chain", "sitemap_redirect", "internal_link_redirect", "schema", "missing_h1", "multiple_h1", "image_alt_text", "missing_meta_description", "empty_meta_description", "malformed_meta_description", "title_over_pixel_limit", "generic_fallback_title", "sitemap_indexability_conflict"}
GROUP_MIN_AFFECTED = 3


def humanize(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[_-]+", " ", str(value or "template"))).strip()


def grouping_key(finding: dict) -> str:
    family = classify_template(finding.get("page_url") or (finding.get("affected_pages") or [""])[0] or "")
    rule = finding.get("rule", "")
    if rule in FAILURE_RULES:
        return f"failure|{rule}|{family}"
    if rule in TEMPLATE_RULES:
        return f"template|{rule}|{family}"
    return ""


def group_template_title(rule: str, family: str) -> str:
    fam = humanize(family)
    if rule == "schema":
        return f"Add structured data to {fam} templates"
    if rule == "image_alt_text":
        return f"Batch image descriptions on {fam} pages"
    if rule == "missing_meta_description":
        return f"Add missing meta descriptions on {fam} pages"
    if rule == "empty_meta_description":
        return f"Fill empty meta descriptions on {fam} pages"
    if rule == "malformed_meta_description":
        return f"Fix malformed meta descriptions on {fam} pages"
    if rule == "title_over_pixel_limit":
        return f"Shorten overwide search titles on {fam} pages"
    if rule == "missing_h1":
        return f"Batch page headings on {fam} pages"
    if rule == "canonical_missing":
        return f"Add canonical URLs across {fam} templates"
    if rule == "canonical_target_redirect":
        return "Update canonicals that point to redirects"
    if rule == "canonical_target_failed":
        return "Fix canonicals that point to unavailable pages"
    if rule == "canonical_target_noindex":
        return "Fix canonicals that point to noindexed pages"
    if rule == "canonical_target_blocked":
        return "Review canonicals that point to robots-blocked pages"
    if rule == "canonical_chain":
        return "Replace canonical chains with the final preferred URL"
    if rule == "canonical_loop":
        return "Remove canonical loops"
    if rule == "canonical_cross_domain":
        return "Verify cross-domain canonical URLs"
    if rule == "redirect_loop":
        return "Remove redirect loops"
    if rule in {"redirect_invalid_response", "redirect_chain_limit"}:
        return "Fix unresolved redirect paths"
    if rule == "redirect_destination_failed":
        return "Fix redirects that end on unavailable pages"
    if rule == "redirect_destination_blocked":
        return "Review redirects to robots-blocked pages"
    if rule == "redirect_destination_noindex":
        return "Fix redirects to noindexed pages"
    if rule == "redirect_chain":
        return "Shorten repeated redirect chains"
    if rule == "sitemap_redirect":
        return "Replace redirecting URLs in the sitemap"
    if rule == "internal_link_redirect":
        return "Update internal links that pass through redirects"
    if rule == "sitemap_indexability_conflict":
        return "Remove non-indexable URLs from the sitemap"
    return f"Fix repeated {fam} template issue"


def group_findings(findings: list[dict]) -> list[dict]:
    direct: list[dict] = []
    groups: dict[str, list[dict]] = {}
    for finding in findings:
        key = grouping_key(finding)
        if not key:
            direct.append(finding)
            continue
        groups.setdefault(key, []).append(finding)

    for key, members in groups.items():
        affected = _unique_nonempty([p for f in members for p in (f.get("affected_pages") or [f.get("page_url")])])[:150]
        # Only collapse into a template card when multiple pages share the issue.
        if len(affected) < GROUP_MIN_AFFECTED:
            direct.extend(members)
            continue
        sample = members[0]
        family = classify_template(sample.get("page_url") or "")
        blocked = key.startswith("failure|rate_limited_page") or sample.get("rule") == "rate_limited_page"
        if blocked:
            title = "Check pages blocked by rate limiting"
            explanation = "Several similar pages returned HTTP 429 or rate limiting. Treat this as one crawler-access problem."
            recommendation = "Ask your web person to check server, CDN, firewall, and rate-limit logs. Confirm Googlebot and normal users can access the affected URLs."
        else:
            title = group_template_title(sample.get("rule", ""), family)
            explanation = "Several similar pages have the same template-level issue. Fix the shared template or pattern instead of creating one task per page."
            recommendation = "Fix one representative page/template first, then roll out the same rule across the affected group."
        group_id = stable_id(f"group|{key}")
        grouped = dict(sample)
        grouped.update({
            "id": group_id,
            "fix_id": group_id,
            "page_url": "",
            "title": title,
            "issue_title": title,
            "plain_english_explanation": explanation,
            "plain_english_summary": explanation,
            "why_it_matters": explanation,
            "recommended_value": recommendation,
            "recommendation": recommendation,
            "ai_recommendation": recommendation,
            "priority": "high" if blocked else ("medium" if sample.get("priority") == "high" else sample.get("priority")),
            "difficulty": "developer" if blocked else sample.get("difficulty"),
            "requires_developer": blocked or sample.get("requires_developer", False),
            "who_can_do_this": "your_web_person" if (blocked or sample.get("requires_developer")) else sample.get("who_can_do_this"),
            "affected_pages": affected,
            "page_count": len(affected),
            "source_pages": _unique_nonempty([p for f in members for p in (f.get("source_pages") or [])]),
            "link_text_samples": _unique_nonempty([t for f in members for t in (f.get("link_text_samples") or [])]),
        })
        direct.append(grouped)
    return direct


def _unique_nonempty(values: list) -> list:
    seen: set = set()
    out: list = []
    for value in values:
        cleaned = str(value or "").strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            out.append(cleaned)
    return out



def duplicate_title_findings(pages: list[dict]) -> list[dict]:
    buckets: dict[str, list[dict]] = {}
    for page in pages:
        status = int(page.get("status_code") or 0)
        title = str(page.get("title") or "").strip()
        if not title or page.get("indexable") is False or not page_has_usable_html(page):
            continue
        if not is_html_page_evidence(page):
            continue
        buckets.setdefault(normalize_title_key(title), []).append(page)

    findings: list[dict] = []
    for title_key in sorted(buckets):
        members = buckets[title_key]
        urls = sorted(_unique_nonempty([relative_evidence_url(page) for page in members]))
        if len(urls) < 2:
            continue
        title = str(members[0].get("title") or "").strip()
        context = classify_duplicate_title_context(title, urls)
        # Generic fallback titles are owned by build_findings so one affected page
        # still produces evidence and repeated pages do not create a second bucket card.
        if context == "generic_fallback":
            continue
        details = {
            "localized_pages": (
                "duplicate_title_localized",
                "low",
                "Review repeated titles across localized pages",
                "The same title appears across multiple locale or country paths.",
                "Verify each market has the intended language, a self-referencing canonical, and correct hreflang relationships before deciding whether titles need localization.",
            ),
            "query_parameter_variants": (
                "duplicate_title_query_variants",
                "medium",
                "Consolidate duplicate titles on parameter variants",
                "The same title appears on clean and query-parameter versions of one path.",
                "Confirm the preferred URL is canonical and non-preferred parameter variants do not create separate indexable pages.",
            ),
            "generic_fallback": (
                "generic_fallback_title",
                "medium",
                "Replace a repeated generic fallback title",
                "Multiple unrelated pages use the same generic CMS fallback title.",
                "Fix the shared title template so each public page receives a specific descriptive title.",
            ),
            "true_template_duplicates": (
                "duplicate_title_template",
                "medium",
                "Differentiate repeated titles across templates",
                "Multiple distinct pages use the same title without a locale or parameter relationship.",
                "Update the shared title template or page fields so each indexable page has a distinct, useful title.",
            ),
        }[context]
        rule, priority, issue_title, explanation, recommendation = details
        finding = create_finding(
            rule,
            "meta_title" if context == "generic_fallback" else "duplicate_content",
            priority,
            issue_title,
            urls[0],
            current_value=f"{len(urls)} pages share: {title}",
            explanation=explanation,
            recommendation=recommendation,
            difficulty="developer" if context in {"query_parameter_variants", "generic_fallback"} else "moderate",
        )
        finding.update({
            "affected_pages": urls,
            "duplicate_title_urls": urls,
            "page_count": len(urls),
            "duplicate_title_context": context,
            "title_value": title,
            "title_evidence_version": TITLE_EVIDENCE_VERSION,
            "non_scoring": True,
            "score_impact": 0,
            "evidence_status": "confirmed",
            "verification_state": "needs_verification" if context == "localized_pages" else "verified",
        })
        findings.append(finding)
    return findings


def detect_duplicate_casing_routes(pages: list[dict]) -> list[dict]:
    by_lower: dict[str, list[str]] = {}
    for page in pages:
        path = str(page.get("path") or "")
        if not path:
            continue
        by_lower.setdefault(path.lower(), [])
        if path not in by_lower[path.lower()]:
            by_lower[path.lower()].append(path)
    return [{"path": lower, "variants": variants} for lower, variants in by_lower.items() if len(variants) > 1][:20]


_CASING_HIGH_RISK = ("/dashboard", "/account", "/login", "/cart", "/checkout", "/admin")


def duplicate_casing_findings(pages: list[dict]) -> list[dict]:
    findings: list[dict] = []
    for item in detect_duplicate_casing_routes(pages):
        variants = item["variants"]
        high_risk = any(part in path.lower() for path in variants for part in _CASING_HIGH_RISK)
        finding = create_finding(
            rule="duplicate_route_casing",
            category="indexability",
            priority="high" if high_risk else "medium",
            title="Fix duplicate URL casing variants",
            page_url="",
            current_value=", ".join(variants[:6]),
            explanation="The crawler found URLs that differ only by uppercase/lowercase letters. These can create duplicate crawlable pages or expose app-route variants.",
            recommendation="Ask your web person to choose one canonical casing, redirect the other variants, and make sure internal links use the preferred version.",
            difficulty="developer",
        )
        finding_id = stable_id("duplicate_route_casing|" + "|".join(variants))
        finding.update({
            "id": finding_id,
            "fix_id": finding_id,
            "why_it_matters": "Search engines may treat these as separate URLs, which can split ranking signals and create duplicate or indexable app routes.",
            "affected_pages": variants,
            "page_count": len(variants),
            "page_template_family": "route_boundary" if high_risk else "standard",
            "primary_defect_class": "structural",
        })
        findings.append(finding)
    return findings


def build_scan_summary(pages: list[dict], findings: list[dict], health_score: int | None, pages_found: int, artifact_count: int) -> dict:
    return {
        "health_score": health_score,
        "score": health_score,
        "pages_scanned": len(pages),
        "pages_crawled": len(pages),
        "pages_found": pages_found,
        "verified_failed_pages": sum(1 for page in pages if is_verified_failed(page)),
        "suspicious_url_artifacts": artifact_count,
        "high_priority_count": sum(1 for item in findings if item.get("priority") in ["critical", "high"]),
        "technical_issue_count": len(findings),
        "duplicate_casing_routes": detect_duplicate_casing_routes(pages),
        "status_label": "Score unavailable" if health_score is None else "Good" if health_score >= 75 else "Fair" if health_score >= 55 else "Needs work",
        "health_score_status": "available" if health_score is not None else "insufficient_evidence",
        "usable_page_count": sum(1 for page in pages if page_has_usable_html(page)),
        "plain_english_summary": f"The Python scanner reviewed {len(pages)} pages and found {len(findings)} evidence-based issues.",
    }


def build_evidence_summary(pages: list[dict], artifact_count: int) -> dict:
    summary = {"confirmed_seed": 0, "confirmed_sitemap_and_linked": 0, "sitemap_listed": 0, "internally_linked": 0, "linked_but_failed": 0, "crawler_artifact": artifact_count, "unknown_discovery": 0}
    for page in pages:
        key = page.get("url_confidence") or "unknown_discovery"
        summary[key] = summary.get(key, 0) + 1
    return summary


def page_evidence(page: dict) -> dict:
    keys = ["url", "final_url", "path", "status_code", "fetch_error", "page_evidence_class", "evidence_gate_version", "url_confidence", "url_suspicion_reasons", "discovered_from", "source_pages", "link_text_samples", "page_template_family", "estimated_page_intent", "title", "title_pixel_width_estimate", "title_width_state", "title_is_generic_fallback", "title_evidence_version", "meta_description", "meta_description_state", "meta_description_element_count", "meta_description_values", "meta_description_duplicate", "metadata_evidence_version", "h1", "redirect_state", "redirect_hop_count", "redirect_chain", "redirect_destination_url", "redirect_destination_status_code", "redirect_destination_indexability_state"]
    return {key: page.get(key) for key in keys}


def is_verified_failed(page: dict) -> bool:
    if page_is_redirect_source(page):
        return False
    if str(page.get("fetch_error") or "").startswith("blocked_"):
        return False
    return bool((int(page.get("status_code") or 0) >= 400 or page.get("fetch_error")) and page.get("url_confidence") != "crawler_artifact")


def calculate_health_score(pages: list[dict], findings: list[dict]) -> int | None:
    if sum(1 for page in pages if page_has_usable_html(page)) < 4:
        return None
    score = 92
    score -= min(35, sum(1 for page in pages if is_verified_failed(page)) * 8)
    metadata_penalties: dict[str, int] = {}
    for finding in findings:
        if finding.get("non_scoring") is True or finding.get("score_impact") == 0:
            continue
        penalty = {"critical": 10, "high": 6, "medium": 2}.get(finding.get("priority"), 0)
        rule = str(finding.get("rule") or "")
        if rule in {"missing_meta_description", "empty_meta_description", "malformed_meta_description"}:
            family = str(finding.get("page_template_family") or "standard")
            metadata_penalties[family] = max(metadata_penalties.get(family, 0), penalty)
        else:
            score -= penalty
    score -= sum(metadata_penalties.values())
    return max(20, min(98, round(score)))



def final_url_identity(value: str) -> str:
    """Stable identity for a fetched final URL without collapsing distinct path variants."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return ""
        scheme = parsed.scheme.lower()
        host = parsed.hostname.lower()
        port = parsed.port
        if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
            host = f"{host}:{port}"
        path = parsed.path or "/"
        query = f"?{parsed.query}" if parsed.query else ""
        return f"{scheme}://{host}{path}{query}"
    except Exception:
        return ""


def merge_duplicate_page_evidence(retained: dict, duplicate: dict) -> None:
    for key, limit in (("discovered_from", None), ("source_pages", None), ("link_text_samples", 8)):
        merged = list(dict.fromkeys([*(retained.get(key) or []), *(duplicate.get(key) or [])]))
        retained[key] = merged[:limit] if limit else merged
    sources = set(retained.get("discovered_from") or [])
    status_code = int(retained.get("status_code") or 0)
    if "seed" in sources:
        retained["url_confidence"] = "confirmed_seed"
    elif "sitemap" in sources and "internal_link" in sources:
        retained["url_confidence"] = "confirmed_sitemap_and_linked"
    elif "sitemap" in sources:
        retained["url_confidence"] = "sitemap_listed"
    elif "internal_link" in sources:
        retained["url_confidence"] = "linked_but_failed" if status_code >= 400 else "internally_linked"

def resolve_crawl_scope(path_prefix: str | None, requested_path: str) -> tuple[str, str, str]:
    """Resolve the crawl boundary without treating a leaf seed URL as a subtree.

    An explicit API path_prefix remains authoritative. Without one, a recognized
    country/language pair such as /fr/fr/ stays market-scoped; every other seed
    crawls from the origin root so /section/page.html can discover the site.
    """
    requested_seed_path = normalize_prefix(requested_path or "/")
    explicit_prefix = str(path_prefix or "").strip()
    if explicit_prefix:
        return normalize_prefix(explicit_prefix), "explicit_path_prefix", requested_seed_path
    requested_market = market_pair_prefix(requested_seed_path)
    if requested_market:
        return requested_market, "requested_market_path", requested_seed_path
    return "/", "origin_root", requested_seed_path


def normalize_url(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if not raw.startswith(("http://", "https://")):
        raw = f"https://{raw}"
    try:
        parsed = urlparse(raw)
        if parsed.scheme not in ["http", "https"] or not parsed.netloc:
            return ""
        host = parsed.hostname or ""
        if any(ch.isspace() for ch in parsed.netloc):
            return ""
        if "." not in host and host != "localhost":
            return ""
        clean, _ = urldefrag(raw)
        return clean.rstrip("/") if parsed.path != "/" else clean
    except Exception:
        return ""


def normalize_prefix(value: str) -> str:
    path = urlparse(value).path if value.startswith(("http://", "https://")) else value
    path = f"/{path.strip('/')}" if path and path != "/" else "/"
    return path.rstrip("/") if path != "/" else "/"


def url_origin(url: str) -> str:
    parsed = urlparse(str(url or ""))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def is_www_origin_alias(source: str, target: str) -> bool:
    source_parsed = urlparse(str(source or ""))
    target_parsed = urlparse(str(target or ""))
    if source_parsed.scheme.lower() != target_parsed.scheme.lower():
        return False
    source_host = (source_parsed.hostname or "").lower().strip(".")
    target_host = (target_parsed.hostname or "").lower().strip(".")
    if not source_host or not target_host or source_host == target_host:
        return False
    if source_parsed.port != target_parsed.port:
        return False
    source_base = source_host[4:] if source_host.startswith("www.") else source_host
    target_base = target_host[4:] if target_host.startswith("www.") else target_host
    return source_base == target_base and (
        source_host.startswith("www.") or target_host.startswith("www.")
    )


def same_origin(url: str, origin: str) -> bool:
    return url_origin(url) == origin


def empty_discovery() -> dict:
    return {"discovered_from": [], "source_pages": [], "link_text_samples": []}


def merge_discovery(record: dict, source: str, source_page: str, link_text: str) -> None:
    if source and source not in record["discovered_from"]:
        record["discovered_from"].append(source)
    if source_page and source_page not in record["source_pages"]:
        record["source_pages"].append(source_page)
    if link_text and link_text not in record["link_text_samples"]:
        record["link_text_samples"].append(link_text[:180])


def dedupe_artifacts(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    output: list[dict] = []
    for item in items:
        key = f"{item.get('url')}|{item.get('source_pages')}"
        if key not in seen:
            seen.add(key)
            output.append(item)
    return output


def friendly_category(category: str) -> str:
    return {
        "meta_title": "Search appearance",
        "meta_description": "Search appearance",
        "duplicate_content": "Search appearance",
        "canonical": "Website setup",
        "schema": "Trust signals",
        "thin_content": "Page content",
        "404_error": "Broken page",
        "web_dev": "Website setup",
        "image_alt_text": "Images",
        "indexability": "Indexability",
    }.get(category, "Website improvement")


def stable_id(value: str) -> str:
    return "finding_" + hashlib.sha1(str(value).encode("utf-8")).hexdigest()[:12]