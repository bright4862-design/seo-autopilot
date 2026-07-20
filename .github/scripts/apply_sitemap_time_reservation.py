from __future__ import annotations

import hashlib
import json
from pathlib import Path

VERSION = "sitemap_time_reservation_v1_crawl_first"


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one replacement, found {count}: {old!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


Path("scanner-api/app/scan_timing.py").write_text('''from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

SITEMAP_TIME_RESERVATION_VERSION = "sitemap_time_reservation_v1_crawl_first"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def allocate_scan_time_budget(
    scan_started_at: float,
    total_timeout_seconds: float,
    fetch_timeout_seconds: float,
    *,
    now: float,
) -> dict[str, float]:
    total = max(1.0, float(total_timeout_seconds or 0))
    fetch_timeout = max(0.1, float(fetch_timeout_seconds or 0.1))
    response_reserve = min(6.0, max(2.0, total * 0.08))
    maximum_crawl_reserve = max(0.5, total - response_reserve - 0.5)
    crawl_reserve = min(maximum_crawl_reserve, max(fetch_timeout * 2.0, total * 0.65))
    overall_deadline = scan_started_at + total
    crawl_deadline = overall_deadline - response_reserve
    sitemap_deadline = overall_deadline - response_reserve - crawl_reserve
    return {
        "overall_deadline": overall_deadline,
        "crawl_deadline": crawl_deadline,
        "sitemap_deadline": sitemap_deadline,
        "sitemap_budget_seconds": max(0.0, sitemap_deadline - now),
        "crawl_reserved_seconds": max(0.0, crawl_deadline - sitemap_deadline),
        "response_reserved_seconds": response_reserve,
    }


def build_crawl_failure_buckets(pages: list[dict[str, Any]]) -> dict[str, int]:
    buckets: dict[str, int] = {}
    for page in pages:
        status = int(page.get("status_code") or page.get("status") or 0)
        error = str(page.get("fetch_error") or "").strip().lower()
        reason = ""
        if error:
            if "robots" in error:
                reason = "robots_blocked"
            elif "timeout" in error or "timed_out" in error:
                reason = "timeout"
            elif "non_public" in error:
                reason = "security_blocked"
            else:
                reason = f"fetch_error:{error}"
        elif status == 429:
            reason = "access_limited_429"
        elif 400 <= status < 500:
            reason = "client_error_4xx"
        elif status >= 500:
            reason = "server_error_5xx"
        elif status == 0:
            reason = "no_response"
        if reason:
            buckets[reason] = buckets.get(reason, 0) + 1
    return dict(sorted(buckets.items()))
''', encoding="utf-8")

# Sitemap diagnostics and partial-return behavior.
sitemap_path = "scanner-api/app/sitemap.py"
replace_once(
    sitemap_path,
    '''async def load_sitemap_urls(client: httpx.AsyncClient, origin: str, path_prefix: str, limit: int, artifacts: list[dict], scope_evidence: dict | None = None, *, deadline: float | None = None, max_fetches: int | None = None) -> list[str]:
    scope_evidence = scope_evidence if scope_evidence is not None else {}''',
    '''async def load_sitemap_urls(client: httpx.AsyncClient, origin: str, path_prefix: str, limit: int, artifacts: list[dict], scope_evidence: dict | None = None, *, deadline: float | None = None, max_fetches: int | None = None, diagnostics: dict | None = None) -> list[str]:
    scope_evidence = scope_evidence if scope_evidence is not None else {}
    diagnostics = diagnostics if diagnostics is not None else {}
    diagnostics.setdefault("sitemap_fetch_count", 0)
    diagnostics.setdefault("sitemap_fetch_limit_reached", False)
    diagnostics.setdefault("sitemap_budget_exhausted", False)
    diagnostics.setdefault("sitemap_failure_reason_buckets", {})''',
)
replace_once(
    sitemap_path,
    '''    for root in dedupe(roots):
        if len(fetched) >= fetch_limit or _deadline_reached(deadline):
            break
        locs = await fetch_sitemap_locs(client, root, fetched, artifacts, deadline=deadline)''',
    '''    for root in dedupe(roots):
        if _stop_sitemap_discovery(fetched, fetch_limit, deadline, diagnostics):
            break
        locs = await fetch_sitemap_locs(client, root, fetched, artifacts, deadline=deadline, diagnostics=diagnostics)''',
)
replace_once(
    sitemap_path,
    '''    for child in rank_child_sitemaps(child_sitemaps, path_prefix):
        if len(fetched) >= fetch_limit or _deadline_reached(deadline):
            break
        bucket = family_urls.setdefault(f"child:{sitemap_family_key(child)}", [])
        locs = await fetch_sitemap_locs(client, child, fetched, artifacts, deadline=deadline)''',
    '''    for child in rank_child_sitemaps(child_sitemaps, path_prefix):
        if _stop_sitemap_discovery(fetched, fetch_limit, deadline, diagnostics):
            break
        bucket = family_urls.setdefault(f"child:{sitemap_family_key(child)}", [])
        locs = await fetch_sitemap_locs(client, child, fetched, artifacts, deadline=deadline, diagnostics=diagnostics)''',
)
replace_once(
    sitemap_path,
    '''    elif len(detected) > 1:
        scope_evidence["multimarket_detected"] = True
    return output[:limit]


def interleave_url_families''',
    '''    elif len(detected) > 1:
        scope_evidence["multimarket_detected"] = True
    output = output[:limit]
    diagnostics["sitemap_fetch_count"] = len(fetched)
    diagnostics["sitemap_urls_discovered"] = len(output)
    diagnostics["sitemap_child_url_count"] = len(dedupe(child_sitemaps))
    return output


def interleave_url_families''',
)

old_fetch = '''async def fetch_sitemap_locs(client: httpx.AsyncClient, sitemap_url: str, fetched: set[str], artifacts: list[dict], *, deadline: float | None = None) -> list[str]:
    if not sitemap_url or sitemap_url in fetched:
        return []
    fetched.add(sitemap_url)
    try:
        response = await _safe_get_before_deadline(client, sitemap_url, deadline)
        if response is None or response.status_code >= 400:
            return []
    except Exception:
        return []

    body = decode_sitemap_body(response, sitemap_url)
    if not body:
        return []
    soup = BeautifulSoup(body, "xml")
    locs: list[str] = []
    for tag in soup.find_all("loc"):
        loc = (tag.get_text() or "").strip()
        if not loc:
            continue
        if is_artifact_url(loc):
            record_artifact(artifacts, loc, "sitemap", sitemap_url, "")
            continue
        locs.append(loc)
    return locs
'''
new_fetch = '''def _record_sitemap_failure(diagnostics: dict | None, reason: str) -> None:
    if diagnostics is None:
        return
    buckets = diagnostics.setdefault("sitemap_failure_reason_buckets", {})
    buckets[reason] = int(buckets.get(reason, 0)) + 1


def _stop_sitemap_discovery(fetched: set[str], fetch_limit: int, deadline: float | None, diagnostics: dict | None) -> bool:
    if len(fetched) >= fetch_limit:
        if diagnostics is not None:
            diagnostics["sitemap_fetch_limit_reached"] = True
        return True
    if _deadline_reached(deadline):
        if diagnostics is not None:
            diagnostics["sitemap_budget_exhausted"] = True
        _record_sitemap_failure(diagnostics, "sitemap_deadline_reached")
        return True
    return False


async def fetch_sitemap_locs(client: httpx.AsyncClient, sitemap_url: str, fetched: set[str], artifacts: list[dict], *, deadline: float | None = None, diagnostics: dict | None = None) -> list[str]:
    if not sitemap_url or sitemap_url in fetched:
        return []
    if _deadline_reached(deadline):
        if diagnostics is not None:
            diagnostics["sitemap_budget_exhausted"] = True
        _record_sitemap_failure(diagnostics, "sitemap_deadline_reached")
        return []
    fetched.add(sitemap_url)
    if diagnostics is not None:
        diagnostics["sitemap_fetch_count"] = len(fetched)
    try:
        response = await _safe_get_before_deadline(client, sitemap_url, deadline)
        if response is None:
            if _deadline_reached(deadline) and diagnostics is not None:
                diagnostics["sitemap_budget_exhausted"] = True
                _record_sitemap_failure(diagnostics, "sitemap_deadline_reached")
            else:
                _record_sitemap_failure(diagnostics, "no_response")
            return []
        if response.status_code >= 400:
            _record_sitemap_failure(diagnostics, f"http_{response.status_code}")
            return []
    except asyncio.TimeoutError:
        if diagnostics is not None:
            diagnostics["sitemap_budget_exhausted"] = True
        _record_sitemap_failure(diagnostics, "sitemap_timeout")
        return []
    except Exception:
        _record_sitemap_failure(diagnostics, "sitemap_fetch_exception")
        return []

    body = decode_sitemap_body(response, sitemap_url)
    if not body:
        _record_sitemap_failure(diagnostics, "empty_sitemap_body")
        return []
    soup = BeautifulSoup(body, "xml")
    locs: list[str] = []
    for tag in soup.find_all("loc"):
        loc = (tag.get_text() or "").strip()
        if not loc:
            continue
        if is_artifact_url(loc):
            record_artifact(artifacts, loc, "sitemap", sitemap_url, "")
            continue
        locs.append(loc)
    return locs
'''
replace_once(sitemap_path, old_fetch, new_fetch)

# Scanner time reservation and diagnostics.
scanner_path = "scanner-api/app/scanner.py"
replace_once(
    scanner_path,
    '''from .sampling import SAMPLING_VERSION, sampling_report, select_balanced_urls
from .render_followup import RENDER_FOLLOWUP_VERSION, run_render_followup''',
    '''from .sampling import SAMPLING_VERSION, sampling_report, select_balanced_urls
from .scan_timing import (
    SITEMAP_TIME_RESERVATION_VERSION,
    allocate_scan_time_budget,
    build_crawl_failure_buckets,
    utc_now_iso,
)
from .render_followup import RENDER_FOLLOWUP_VERSION, run_render_followup''',
)
replace_once(
    scanner_path,
    '''    scan_started_at = time.monotonic()
    deadline = scan_started_at + budget["timeout"]''',
    '''    scan_started_at = time.monotonic()
    scan_started_wall_clock = utc_now_iso()
    deadline = scan_started_at + budget["timeout"]''',
)
replace_once(
    scanner_path,
    '''        max_pages = budget["max_pages"]
        sitemap_urls = await load_sitemap_urls(
            client, origin, prefix, SITEMAP_DISCOVERY_LIMIT, artifacts,
            scope_evidence=scope_evidence, deadline=deadline,
            max_fetches=max_sitemap_fetches,
        )''',
    '''        max_pages = budget["max_pages"]
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
        sitemap_diagnostics["sitemap_urls_discovered"] = len(sitemap_urls)''',
)
replace_once(
    scanner_path,
    '''        for url in sampled_sitemap_urls:
            enqueue(url, "sitemap", "/sitemap.xml", "")

        state_lock = asyncio.Lock()''',
    '''        for url in sampled_sitemap_urls:
            enqueue(url, "sitemap", "/sitemap.xml", "")

        crawl_started_at = utc_now_iso()
        crawl_started_monotonic = time.monotonic()
        initial_queue_size = len(queue)
        state_lock = asyncio.Lock()''',
)
replace_once(
    scanner_path,
    '''                    if time.monotonic() >= deadline or crawl_state["claimed"] >= max_pages:''',
    '''                    if time.monotonic() >= timing_budget["crawl_deadline"] or crawl_state["claimed"] >= max_pages:''',
)
replace_once(
    scanner_path,
    '''        await asyncio.gather(*workers)
        # Enforce the selected scan budget again after all concurrent sources finish.''',
    '''        await asyncio.gather(*workers)
        crawl_elapsed_ms = round((time.monotonic() - crawl_started_monotonic) * 1000)
        final_queue_size = len(queue)
        # Enforce the selected scan budget again after all concurrent sources finish.''',
)
replace_once(
    scanner_path,
    '''            robots_policy,
            deadline=deadline,
        )''',
    '''            robots_policy,
            deadline=timing_budget["crawl_deadline"],
        )''',
)
replace_once(
    scanner_path,
    '''    elapsed_ms = round((time.monotonic() - scan_started_at) * 1000)
    deadline_reached = time.monotonic() >= deadline
    crawl_warnings = []''',
    '''    elapsed_ms = round((time.monotonic() - scan_started_at) * 1000)
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
    }
    crawl_warnings = []''',
)
replace_once(
    scanner_path,
    '''    if deadline_reached:
        crawl_warnings.append(f"The {scan_mode} scan reached its bounded {budget['timeout']}-second backend budget and returned collected evidence.")''',
    '''    if deadline_reached:
        crawl_warnings.append(f"The {scan_mode} scan reached its bounded {budget['timeout']}-second backend budget and returned collected evidence.")
    if sitemap_diagnostics.get("sitemap_budget_exhausted"):
        crawl_warnings.append(
            f"Sitemap discovery reached its reserved {sitemap_diagnostics.get('sitemap_budget_seconds', 0)}-second budget; "
            f"page crawling continued with {len(sitemap_urls)} discovered sitemap URLs."
        )''',
)
replace_once(
    scanner_path,
    '''        "sampling_version": SAMPLING_VERSION,
        "sampling_evidence": sampling_evidence,''',
    '''        "sampling_version": SAMPLING_VERSION,
        "sampling_evidence": sampling_evidence,
        "sitemap_time_reservation_version": SITEMAP_TIME_RESERVATION_VERSION,
        "crawl_timing": crawl_timing,''',
)
replace_once(
    scanner_path,
    '''            "page_evidence_gate_version": PAGE_EVIDENCE_GATE_VERSION,
            "scanner_elapsed_ms": elapsed_ms,''',
    '''            "page_evidence_gate_version": PAGE_EVIDENCE_GATE_VERSION,
            "sitemap_time_reservation_version": SITEMAP_TIME_RESERVATION_VERSION,
            "crawl_timing": crawl_timing,
            "scanner_elapsed_ms": elapsed_ms,''',
)

# Health and frozen revision component.
main_path = "scanner-api/app/main.py"
replace_once(
    main_path,
    '''from .review import REVIEW_VERSION, run_review
from .review_calibration import CALIBRATION_VERSION, apply_review_evidence_calibration''',
    '''from .review import REVIEW_VERSION, run_review
from .review_calibration import CALIBRATION_VERSION, apply_review_evidence_calibration
from .scan_timing import SITEMAP_TIME_RESERVATION_VERSION''',
)
replace_once(
    main_path,
    '''        "evidence_quality_gate_version": EVIDENCE_QUALITY_GATE_VERSION,
        "beta_revision_fingerprint": live_revision()["fingerprint"],''',
    '''        "evidence_quality_gate_version": EVIDENCE_QUALITY_GATE_VERSION,
        "sitemap_time_reservation_version": SITEMAP_TIME_RESERVATION_VERSION,
        "beta_revision_fingerprint": live_revision()["fingerprint"],''',
)

beta_path = "scanner-api/app/beta_revision.py"
replace_once(
    beta_path,
    '''    from .robots_policy import ROBOTS_POLICY_VERSION
    from .sampling import SAMPLING_VERSION''',
    '''    from .robots_policy import ROBOTS_POLICY_VERSION
    from .sampling import SAMPLING_VERSION
    from .scan_timing import SITEMAP_TIME_RESERVATION_VERSION''',
)
replace_once(
    beta_path,
    '''        "sampling_version": SAMPLING_VERSION,
        "render_evidence_version": RENDER_EVIDENCE_VERSION,''',
    '''        "sampling_version": SAMPLING_VERSION,
        "sitemap_time_reservation_version": SITEMAP_TIME_RESERVATION_VERSION,
        "render_evidence_version": RENDER_EVIDENCE_VERSION,''',
)

# Durable ScanRun and browser debug mapping.
schema_path = "base44/entities/ScanRun.jsonc"
replace_once(
    schema_path,
    '''    "sampling_evidence": { "type": "object", "additionalProperties": true, "default": {} },
    "scan_status": { "type": "string" },''',
    '''    "sampling_evidence": { "type": "object", "additionalProperties": true, "default": {} },
    "crawl_timing": { "type": "object", "additionalProperties": true, "default": {} },
    "scan_status": { "type": "string" },''',
)

model_path = "src/lib/scanRunModel.js"
replace_once(
    model_path,
    '''    sampling_evidence: record.sampling_evidence || {},
    scan_status: toStr(record.scan_status),''',
    '''    sampling_evidence: record.sampling_evidence || {},
    crawl_timing: record.crawl_timing || record.technical_audit_summary?.crawl_timing || {},
    scan_status: toStr(record.scan_status),''',
)

form_path = "src/components/scan/ScanWebsiteForm.jsx"
replace_once(
    form_path,
    '''    sampling_version: record.sampling_version || "",
    sampling_evidence: record.sampling_evidence || {},
    id: record.id || "",''',
    '''    sampling_version: record.sampling_version || "",
    sampling_evidence: record.sampling_evidence || {},
    crawl_timing: record.crawl_timing || record.technical_audit_summary?.crawl_timing || {},
    id: record.id || "",''',
)
replace_once(
    form_path,
    '''      route_boundary_candidates_crawled: record.technical_audit_summary.route_boundary_candidates_crawled || 0,
      crawl_policy_source: record.technical_audit_summary.crawl_policy_source || record.technical_audit_summary.crawl_policy?.source || "",''',
    '''      route_boundary_candidates_crawled: record.technical_audit_summary.route_boundary_candidates_crawled || 0,
      crawl_timing: record.technical_audit_summary.crawl_timing || record.crawl_timing || {},
      crawl_policy_source: record.technical_audit_summary.crawl_policy_source || record.technical_audit_summary.crawl_policy?.source || "",''',
)

Path("scanner-api/tests/test_sitemap_time_reservation.py").write_text('''import asyncio
import time

from app import scanner, sitemap
from app.extract import extract_page
from app.scan_timing import allocate_scan_time_budget
from app.sitemap import load_sitemap_urls


class FakeResponse:
    def __init__(self, text="", *, status_code=200, url="https://example.com/"):
        self.status_code = status_code
        self.content = text.encode("utf-8")
        self.encoding = "utf-8"
        self.url = url

    @property
    def text(self):
        return self.content.decode("utf-8")


def sitemap_xml(urls, *, index=False):
    outer = "sitemapindex" if index else "urlset"
    item = "sitemap" if index else "url"
    body = "".join(f"<{item}><loc>{url}</loc></{item}>" for url in urls)
    return f"<{outer}>{body}</{outer}>"


class Policy:
    def allowed(self, user_agent, url):
        return True

    def evidence(self):
        return {"state": "allowed"}


def test_time_allocation_reserves_most_of_advanced_budget_for_crawling():
    allocation = allocate_scan_time_budget(100.0, 75.0, 10.0, now=102.0)
    assert allocation["crawl_reserved_seconds"] >= 48.0
    assert allocation["sitemap_deadline"] < allocation["crawl_deadline"]
    assert allocation["crawl_deadline"] < allocation["overall_deadline"]
    assert allocation["response_reserved_seconds"] >= 2.0


def test_sitemap_deadline_returns_partial_urls_and_records_budget(monkeypatch):
    origin = "https://example.com"
    index_url = f"{origin}/index.xml"
    fast_child = f"{origin}/product-sitemap.xml"
    slow_child = f"{origin}/blog-sitemap.xml"
    fast_pages = [f"{origin}/products/{index}" for index in range(3)]

    async def fake_safe_get(client, url):
        if url == f"{origin}/robots.txt":
            return FakeResponse(f"Sitemap: {index_url}")
        if url == index_url:
            return FakeResponse(sitemap_xml([fast_child, slow_child], index=True))
        if url == f"{origin}/sitemap.xml":
            return FakeResponse(status_code=404)
        if url == fast_child:
            return FakeResponse(sitemap_xml(fast_pages))
        if url == slow_child:
            await asyncio.sleep(0.2)
            return FakeResponse(sitemap_xml([f"{origin}/blog/late"]))
        return FakeResponse(status_code=404)

    monkeypatch.setattr(sitemap, "safe_get", fake_safe_get)
    diagnostics = {}
    urls = asyncio.run(load_sitemap_urls(
        object(),
        origin,
        "/",
        20,
        [],
        deadline=time.monotonic() + 0.08,
        max_fetches=10,
        diagnostics=diagnostics,
    ))

    assert fast_pages[0] in urls
    assert f"{origin}/blog/late" not in urls
    assert diagnostics["sitemap_budget_exhausted"] is True
    assert diagnostics["sitemap_urls_discovered"] >= 1
    assert diagnostics["sitemap_fetch_count"] >= 2
    assert diagnostics["sitemap_failure_reason_buckets"]


def test_run_scan_continues_to_page_workers_after_sitemap_budget(monkeypatch):
    captured = {}

    async def fake_load_robots_policy(client, origin):
        return Policy()

    async def fake_safe_get(client, url):
        return FakeResponse(url=url)

    async def fake_load_sitemap_urls(client, origin, prefix, limit, artifacts, scope_evidence=None, *, deadline=None, max_fetches=None, diagnostics=None):
        captured["sitemap_deadline"] = deadline
        diagnostics.update({
            "sitemap_budget_exhausted": True,
            "sitemap_fetch_count": 2,
            "sitemap_failure_reason_buckets": {"sitemap_deadline_reached": 1},
        })
        return [f"{origin}/a", f"{origin}/b", f"{origin}/c"]

    async def fake_fetch_and_extract(client, url, discovery, robots_policy=None):
        return extract_page(
            "<html><head><title>Page</title></head><body><h1>Page</h1><p>Useful content for this page.</p></body></html>",
            url,
            url,
            200,
            "text/html",
            discovery,
        )

    async def fake_validate(*args, **kwargs):
        return {}

    async def fake_render_followup(*args, **kwargs):
        return {"attempted": 0}

    monkeypatch.setattr(scanner, "load_robots_policy", fake_load_robots_policy)
    monkeypatch.setattr(scanner, "safe_get", fake_safe_get)
    monkeypatch.setattr(scanner, "load_sitemap_urls", fake_load_sitemap_urls)
    monkeypatch.setattr(scanner, "fetch_and_extract", fake_fetch_and_extract)
    monkeypatch.setattr(scanner, "validate_canonical_targets", fake_validate)
    monkeypatch.setattr(scanner, "run_render_followup", fake_render_followup)

    result = asyncio.run(scanner.run_scan("https://example.com/", scan_mode="basic", concurrency=2))

    assert result["pages_crawled"] == 4
    assert result["crawl_timing"]["initial_queue_size"] == 4
    assert result["crawl_timing"]["sitemap_budget_exhausted"] is True
    assert result["crawl_timing"]["crawl_reserved_seconds"] > 0
    assert result["crawl_timing"]["crawl_started_at"]
    assert captured["sitemap_deadline"] < result["crawl_timing"]["crawl_started_at"] or captured["sitemap_deadline"] > 0
''', encoding="utf-8")

Path("tests/frontend/sitemapTimingDiagnostics.test.mjs").write_text('''import assert from "node:assert/strict";\nimport { readFileSync } from "node:fs";\nimport test from "node:test";\n\nimport { buildScanRunFields } from "../../src/lib/scanRunModel.js";\n\nconst scanRunEntity = JSON.parse(readFileSync(new URL("../../base44/entities/ScanRun.jsonc", import.meta.url), "utf8"));\n\ntest("ScanRun stores crawl timing diagnostics", () => {\n  assert.ok(scanRunEntity.properties.crawl_timing);\n  const crawlTiming = { sitemap_budget_exhausted: true, sitemap_elapsed_ms: 1200, crawl_elapsed_ms: 23000 };\n  const fields = buildScanRunFields({ crawl_timing: crawlTiming });\n  assert.deepEqual(fields.crawl_timing, crawlTiming);\n});\n''', encoding="utf-8")

Path("docs/releases/sitemap-time-reservation-v1.md").write_text('''# Sitemap time reservation v1

## Scope

- Sitemap discovery receives a bounded sub-deadline.
- At least 65% of the backend request budget remains reserved for page crawling.
- A final response reserve remains after worker crawling.
- Partial sitemap discoveries still seed the crawl queue.
- Timing, queue and failure diagnostics are persisted and included in debug exports.

## Production acceptance

1. IKEA France must crawl pages instead of returning 149 discovered and 0 crawled solely from sitemap time exhaustion.
2. Nordic Nest must progress beyond the previous five-page result when access permits.
3. Funbooker must remain complete at the 150-page cap.
''', encoding="utf-8")

revision_path = Path("data/beta-crawler-revision.json")
revision = json.loads(revision_path.read_text(encoding="utf-8"))
old_fingerprint = str(revision["fingerprint"])
components = dict(revision["component_versions"])
components["sitemap_time_reservation_version"] = VERSION
payload = json.dumps(components, sort_keys=True, separators=(",", ":"))
new_fingerprint = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
revision.update({
    "acceptance_report": "docs/releases/sitemap-time-reservation-v1.md",
    "component_versions": dict(sorted(components.items())),
    "fingerprint": new_fingerprint,
    "git_commit": "",
    "note": "Sitemap timing candidate: bounded sitemap expansion preserves a majority crawl reserve and returns partial discovery with durable diagnostics.",
    "recorded_at": "2026-07-20T00:00:00Z",
    "status": "candidate",
})
revision_path.write_text(json.dumps(revision, indent=2, sort_keys=True) + "\n", encoding="utf-8")

for file_name in [
    "src/lib/scanRunModel.js",
    "tests/frontend/releaseAuthorityGate.test.mjs",
    "tests/frontend/scanRunPersistence.test.mjs",
    "scanner-api/tests/test_observability.py",
]:
    target = Path(file_name)
    text = target.read_text(encoding="utf-8")
    if old_fingerprint not in text:
        raise SystemExit(f"{file_name}: old fingerprint {old_fingerprint} not found")
    target.write_text(text.replace(old_fingerprint, new_fingerprint), encoding="utf-8")

print(f"old fingerprint: {old_fingerprint}")
print(f"new fingerprint: {new_fingerprint}")
