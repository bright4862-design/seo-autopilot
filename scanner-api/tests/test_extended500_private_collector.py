"""Offline tests for the private, bounded Extended 500 collector (issue #384).

Only DNS and the HTTP transport are replaced (httpx.MockTransport plus one
public DNS snapshot); real sockets are forbidden. Everything else runs the
production per-page path: safe_get_once's bounded reader, redirect evidence,
robots policy, sitemap parsing, extract_page and the positive projector.
Fixture results are NOT real-site benchmarks.
"""
from __future__ import annotations

import asyncio
import copy
import json
import socket
from pathlib import Path

import httpx
import pytest

from app import scanner
from app.authority_seal import create_authority_seal
from app.extended500_private_collector import (
    AUTHORISED_CAPACITY,
    COLLECTOR_VERSION,
    Extended500CollectionRefused,
    _collector_child,
    run_isolated_extended500_collection,
    validate_extended500_collection_request,
    validate_extended500_collection_result,
    EXCLUSION_BUCKETS,
    CollectorLimits,
    Extended500CollectorFailure,
    RetainedPageLedger,
    admit_run_scan_result,
    build_private_collection_handoff,
    project_private_collection_for_external_boundary,
    run_private_extended500_collection,
)
from app.extract import extract_page
from app.robots_policy import owner_robots_override
from app.stage2_reachability_provenance import EXTENDED_REACHABILITY_SCOPE

ORIGIN = "https://example.com"
KEY = "fixture-secret-not-for-production"
IDENTITY = {"scan_id": "scan-500", "request_id": "req-500", "idempotency_key": "idem-500"}
SCAN_RUN = {
    "scan_mode": "extended_500", "owner_user_id": "owner-500", "id": "scan-500",
    "project_id": "project-500", "request_id": "req-500", "idempotency_key": "idem-500",
    "normalized_domain": "example.com", "attempt_count": 1,
}


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds
        await asyncio.sleep(0)


def html(title: str, links: list[str] = (), extra: str = "") -> str:
    anchors = "".join(f'<a href="{href}">link {i}</a>' for i, href in enumerate(links))
    return (
        f"<html><head><title>{title}</title></head><body><h1>{title}</h1>"
        f"<p>Synthetic fixture page; no real website was scanned.</p>{anchors}{extra}</body></html>"
    )


def sitemap(paths: list[str], origin: str = ORIGIN) -> dict:
    body = "<urlset>" + "".join(f"<url><loc>{origin}{p}</loc></url>" for p in paths) + "</urlset>"
    return {"body": body, "content_type": "application/xml"}


class Network:
    """Route map + request log; optional fake latency on page requests."""

    def __init__(self, routes: dict, clock: FakeClock | None = None, latency: float = 0.0) -> None:
        self.routes = routes
        self.clock = clock
        self.latency = latency
        self.log: list[tuple[str, float]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = f"{request.url.scheme}://{request.headers.get('host', '')}{request.url.raw_path.decode('ascii')}"
        now = self.clock() if self.clock else 0.0
        self.log.append((url, now))
        if self.clock and self.latency and not url.endswith((".txt", ".xml")):
            self.clock.advance(self.latency)
        entry = self.routes.get(url)
        if entry is None:
            return httpx.Response(404, text="", request=request)
        headers = {"content-type": entry.get("content_type", "text/html")}
        headers.update(entry.get("headers", {}))
        body = entry.get("body", "")
        raw = body if isinstance(body, bytes) else str(body).encode("utf-8")
        return httpx.Response(entry.get("status", 200), headers=headers,
                              stream=httpx.ByteStream(raw), request=request)

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler), follow_redirects=False)

    @property
    def urls(self) -> list[str]:
        return [url for url, _ in self.log]


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbid(*_args, **_kwargs):
        raise AssertionError("test attempted a real outbound socket")

    def resolve(host, port, **_kwargs):
        address = "10.0.0.7" if str(host).startswith("internal.") else "93.184.216.34"
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, port))]

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    monkeypatch.setattr(socket.socket, "connect", forbid)
    monkeypatch.setattr(socket, "create_connection", forbid)


def base_routes(*, robots: str = "User-agent: *\nAllow: /", seed_html: str | None = None) -> dict:
    return {
        f"{ORIGIN}/robots.txt": {"body": robots, "content_type": "text/plain"},
        f"{ORIGIN}/": {"body": seed_html if seed_html is not None else html("Home")},
    }


async def collect(network: Network, *, clock: FakeClock | None = None, **kwargs):
    clock = clock or FakeClock()
    network.clock = network.clock or clock
    limits = kwargs.pop("limits", CollectorLimits(min_host_interval_seconds=0.05))
    url = kwargs.pop("url", f"{ORIGIN}/")
    async with network.client() as client:
        return await run_private_extended500_collection(
            url, limits=limits, http_client=client, clock=clock, sleeper=clock.sleep, **kwargs,
        )


def assert_reconciles(result: dict) -> None:
    assert result["success"] is True, result
    counters = result["collector_counters"]
    excluded = counters["excluded"]
    assert set(excluded) == set(EXCLUSION_BUCKETS)
    assert counters["urls_discovered"] == (
        counters["pages_retained"] + sum(excluded.values()) + sum(counters["not_attempted"].values())
    )
    assert counters["urls_attempted"] == counters["pages_retained"] + sum(excluded.values()) - excluded["robots_denied"]
    assert result["pages_found"] == counters["urls_discovered"]
    assert result["pages_crawled"] == len(result["pages"]) == counters["pages_retained"]
    assert result["pages"] is result["crawled_pages"]
    assert result["scan_coverage"]["urls_attempted"] == counters["urls_attempted"]
    assert result["scan_coverage"]["unique_retained_destinations"] == counters["pages_retained"]
    assert all(result["reconciliation"]["checks"].values())
    assert len({p["final_url"] for p in result["pages"]}) == len(result["pages"])
    assert all(p["page_evidence_class"] == "usable_html" for p in result["pages"])
    assert result["review_status"] == "not_reviewed" and result["release_gate_eligible"] is False
    assert result["customer_visible"] is False


def catalog_routes(count: int, *, include_seed_in_sitemap: bool = False) -> dict:
    paths = [f"/catalog/item-{n:04d}" for n in range(count)]
    routes = base_routes()
    routes[f"{ORIGIN}/sitemap.xml"] = sitemap((["/"] if include_seed_in_sitemap else []) + paths)
    for path in paths:
        routes[f"{ORIGIN}{path}"] = {"body": html(f"Item {path}")}
    return routes


# --- baseline: 510 discovered -> exactly 500 retained -----------------------

@pytest.mark.asyncio
async def test_synthetic_510_discovered_exactly_500_retained_through_private_frontier():
    network = Network(catalog_routes(509, include_seed_in_sitemap=True))
    result = await collect(network, identity=IDENTITY)

    assert_reconciles(result)
    counters = result["collector_counters"]
    assert counters["urls_discovered"] == result["pages_found"] == 510
    assert counters["pages_retained"] == result["pages_crawled"] == 500 == AUTHORISED_CAPACITY
    assert counters["not_attempted"]["capacity_reached"] == 10
    assert sum(counters["excluded"].values()) == 0
    assert counters["discovery_filtered"]["duplicate_discoveries"] == 1  # seed listed in sitemap
    assert result["stop_reason"] == "capacity_reached"
    page_requests = [u for u in network.urls if not u.endswith((".txt", ".xml"))]
    assert len(page_requests) == len(set(page_requests)) == 500  # the 501st is never fetched
    assert result["resource_usage"]["requests_made"] == len(network.log)
    assert all(p["reachability_scope"] == EXTENDED_REACHABILITY_SCOPE for p in result["pages"])
    assert all("_reachability_links" not in p and "_links" not in p for p in result["pages"])

    # Public Standard 150 contract is untouched by the private run.
    assert scanner.resolve_scan_budget("advanced")["max_pages"] == 150
    assert scanner.resolve_scan_budget("extended_500")["max_pages"] == 150
    assert "extended_500" not in scanner.SCAN_BUDGETS

    # External boundary: positive projector strips internal page fields.
    for page in result["pages"]:
        page["main_text"] = "private main text"
        page["future_internal_debug_field"] = "must not escape"
    projected = project_private_collection_for_external_boundary(result)
    assert len(projected["pages"]) == len(projected["crawled_pages"]) == 500
    assert all("main_text" not in p and "future_internal_debug_field" not in p for p in projected["pages"])
    assert result["pages"][0]["main_text"] == "private main text"  # input not mutated
    for page in result["pages"]:
        page.pop("main_text")
        page.pop("future_internal_debug_field")

    envelope = build_private_collection_handoff(
        SCAN_RUN, result, KEY, scanner_source_sha="a" * 40, beta_revision_fingerprint="b" * 16,
    )
    assert envelope["scan"]["pages_crawled"] == 500 and envelope["scan"]["pages_found"] == 510
    assert envelope["review"] == {"review_status": "not_reviewed", "pages_reviewed": 0, "release_gate_eligible": False}
    signed = {k: envelope[k] for k in ("version", "identity", "scan", "review")}
    assert create_authority_seal(signed, KEY) == envelope["proof"]
    with pytest.raises(ValueError, match="domain identity"):
        build_private_collection_handoff(
            {**SCAN_RUN, "normalized_domain": "other.example"}, result, KEY,
            scanner_source_sha="a" * 40, beta_revision_fingerprint="b" * 16,
        )


@pytest.mark.asyncio
async def test_existing_run_scan_baseline_is_admitted_through_the_same_gate(monkeypatch):
    """The existing proof path (fixture-only 500 budget) through admit_run_scan_result."""
    sitemap_urls = [f"{ORIGIN}/catalog/item-{n:04d}" for n in range(510)]

    class Policy:
        def directive_allowed(self, _agent, _url):
            return True

        allowed = directive_allowed

        def evidence(self):
            return {}

    class Landing:
        def __init__(self, url):
            self.url = url

    async def robots(*_a):
        return Policy()

    async def landing(_client, url, **_k):
        return Landing(url)

    async def sitemap_loader(*_a, **_k):
        return list(sitemap_urls)

    async def fetch(_client, url, discovery, robots_policy=None):
        await asyncio.sleep(0)
        return extract_page(html("Catalog"), url, url, 200, "text/html", discovery, include_links=True)

    async def nothing(*_a, **_k):
        return {"attempted": 0}

    monkeypatch.setattr(scanner, "is_public_http_url", lambda _u: True)
    monkeypatch.setitem(scanner.SCAN_BUDGETS, "advanced",
                        {"max_pages": 500, "timeout": 120, "fetch_timeout": 10, "max_sitemap_fetches": 40})
    monkeypatch.setattr(scanner, "load_robots_policy", robots)
    monkeypatch.setattr(scanner, "safe_get", landing)
    monkeypatch.setattr(scanner, "load_sitemap_urls", sitemap_loader)
    monkeypatch.setattr(scanner, "fetch_and_extract", fetch)
    monkeypatch.setattr(scanner, "validate_canonical_targets", nothing)
    monkeypatch.setattr(scanner, "run_render_followup", nothing)
    raw = await scanner.run_scan(f"{ORIGIN}/", scan_mode="advanced", job_mode=True,
                                 timeout_seconds=120, concurrency=8)
    monkeypatch.undo()
    before = copy.deepcopy(raw["pages"][0])

    admitted = admit_run_scan_result(raw, identity=IDENTITY)
    assert admitted["success"] is True, admitted
    assert admitted["collector_path"] == "run_scan_admission"
    assert admitted["pages_crawled"] == len(admitted["pages"]) == 500
    assert admitted["pages_found"] >= 510
    assert all(admitted["reconciliation"]["checks"].values())
    assert raw["pages"][0] == before  # input not mutated
    envelope = build_private_collection_handoff(
        SCAN_RUN, admitted, KEY, scanner_source_sha="c" * 40, beta_revision_fingerprint="d" * 16,
    )
    assert envelope["scan"]["pages_crawled"] == 500

    # 501 page records (forged/oversized budget) fail closed; never truncated.
    forged = copy.deepcopy(raw)
    extra = copy.deepcopy(forged["pages"][-1])
    extra["url"] = extra["final_url"] = f"{ORIGIN}/catalog/extra"
    forged["pages"].append(extra)
    forged["crawled_pages"] = forged["pages"]
    forged["pages_crawled"] = 501
    forged["scan_coverage"]["urls_attempted"] += 1
    failed = admit_run_scan_result(forged)
    assert failed["success"] is False and failed["error_code"] == "capacity_exceeded"
    assert "pages" not in failed and "crawled_pages" not in failed

    # run_scan's silent pages[:max_pages] slice is detected, not accepted.
    truncated = copy.deepcopy(raw)
    truncated["scan_coverage"]["urls_attempted"] += 7
    assert admit_run_scan_result(truncated)["error_code"] == "accounting_mismatch"
    misaligned = copy.deepcopy(raw)
    misaligned["crawled_pages"] = misaligned["pages"][:-1]
    assert admit_run_scan_result(misaligned)["error_code"] == "run_scan_result_rejected"


# --- 150 / 500 / 501 --------------------------------------------------------

@pytest.mark.asyncio
async def test_capacity_150_retains_exactly_150():
    network = Network(catalog_routes(510))
    result = await collect(network, limits=CollectorLimits(max_retained_pages=150, min_host_interval_seconds=0.05))
    assert_reconciles(result)
    assert result["pages_crawled"] == 150
    assert result["collector_counters"]["urls_discovered"] == 511
    assert result["collector_counters"]["not_attempted"]["capacity_reached"] == 361
    assert len([u for u in network.urls if "/catalog/" in u]) == 149


@pytest.mark.asyncio
async def test_exactly_500_available_and_501_available():
    exact = await collect(Network(catalog_routes(499)))
    assert_reconciles(exact)
    assert exact["pages_crawled"] == 500 and exact["collector_counters"]["urls_discovered"] == 500
    assert sum(exact["collector_counters"]["not_attempted"].values()) == 0

    network = Network(catalog_routes(500))
    over = await collect(network)
    assert_reconciles(over)
    assert over["pages_crawled"] == 500 and over["collector_counters"]["urls_discovered"] == 501
    assert over["collector_counters"]["not_attempted"]["capacity_reached"] == 1
    fetched = {u for u in network.urls if "/catalog/" in u}
    assert len(fetched) == 499  # the 501st usable page was never requested


@pytest.mark.asyncio
async def test_501_capacity_and_ledger_overflow_fail_closed():
    network = Network(catalog_routes(10))
    failed = await collect(network, limits=CollectorLimits(max_retained_pages=501))
    assert failed["success"] is False and failed["error_code"] == "invalid_limits"
    assert "pages" not in failed and network.log == []

    for bad in (CollectorLimits(deadline_seconds=121), CollectorLimits(max_response_bytes=5_000_001),
                CollectorLimits(min_host_interval_seconds=0.0), CollectorLimits(max_retained_pages=True)):
        assert (await collect(Network({}), limits=bad))["error_code"] == "invalid_limits"

    ledger = RetainedPageLedger(500, 64 * 1024 * 1024)
    for index in range(500):
        ledger.retain({"url": f"{ORIGIN}/p{index}"})
    with pytest.raises(Extended500CollectorFailure) as excinfo:
        ledger.retain({"url": f"{ORIGIN}/p500"})
    assert excinfo.value.code == "capacity_exceeded" and len(ledger) == 500
    with pytest.raises(Extended500CollectorFailure):
        RetainedPageLedger(501, 1024 * 1024)


# --- discovery shapes -------------------------------------------------------

@pytest.mark.asyncio
async def test_all_sitemap_discovery():
    network = Network(catalog_routes(40))
    result = await collect(network)
    assert_reconciles(result)
    assert result["stop_reason"] == "inventory_exhausted"
    assert result["collector_state"] == "complete_inventory"
    assert result["pages_crawled"] == 41
    assert result["collector_counters"]["discovered_by_source"] == {"seed": 1, "sitemap": 40}
    assert result["sitemap_evidence"]["sitemap_urls_admitted"] == 40


@pytest.mark.asyncio
async def test_no_sitemap_discovers_through_internal_links_only():
    routes = base_routes(seed_html=html("Home", ["/a", "/b", "https://other.example.org/x"]))
    routes[f"{ORIGIN}/a"] = {"body": html("A", ["/c", "/"])}
    routes[f"{ORIGIN}/b"] = {"body": html("B", ["/c"])}
    routes[f"{ORIGIN}/c"] = {"body": html("C")}
    result = await collect(Network(routes))
    assert_reconciles(result)
    assert result["pages_crawled"] == 4
    assert result["sitemap_evidence"]["sitemap_urls_returned"] == 0
    assert result["collector_counters"]["discovered_by_source"] == {"seed": 1, "internal_link": 3}
    filtered = result["collector_counters"]["discovery_filtered"]
    assert filtered["offsite_urls_ignored"] == 1
    assert filtered["duplicate_discoveries"] >= 2


@pytest.mark.asyncio
async def test_scope_limited_run_excludes_and_counts_out_of_scope_urls():
    routes = {
        f"{ORIGIN}/robots.txt": {"body": "User-agent: *\nAllow: /", "content_type": "text/plain"},
        f"{ORIGIN}/blog": {"body": html("Blog", ["/blog/one", "/shop/hat"])},
        f"{ORIGIN}/sitemap.xml": sitemap(["/blog/one", "/blog/two", "/shop/a", "/shop/b"]),
        f"{ORIGIN}/blog/one": {"body": html("One")},
        f"{ORIGIN}/blog/two": {"body": html("Two")},
        f"{ORIGIN}/shop/a": {"body": html("Shop")},
    }
    network = Network(routes)
    result = await collect(network, url=f"{ORIGIN}/blog", path_prefix="/blog")
    assert_reconciles(result)
    assert result["path_prefix"] == "/blog"
    assert {p["path"] for p in result["pages"]} == {"/blog", "/blog/one", "/blog/two"}
    assert result["crawl_scope"]["sitemap_urls_excluded_outside_scope"] == 2
    assert result["collector_counters"]["discovery_filtered"]["out_of_scope_ignored"] == 1
    assert not any("/shop/" in u for u in network.urls)
    outside = await collect(Network(routes), url=f"{ORIGIN}/shop/a", path_prefix="/blog")
    assert outside["error_code"] == "invalid_request"


# --- robots -----------------------------------------------------------------

@pytest.mark.asyncio
async def test_robots_denied_urls_are_counted_and_never_fetched_even_with_ambient_override():
    routes = catalog_routes(6)
    routes[f"{ORIGIN}/robots.txt"]["body"] = "User-agent: *\nDisallow: /catalog/item-000"
    network = Network(routes)
    with owner_robots_override(True):
        result = await collect(network)
    assert_reconciles(result)
    assert result["collector_counters"]["excluded"]["robots_denied"] == 6
    assert result["pages_crawled"] == 1
    assert not any("/catalog/" in u for u in network.urls)


@pytest.mark.asyncio
async def test_entry_robots_denial_is_a_hard_failure():
    network = Network(base_routes(robots="User-agent: *\nDisallow: /"))
    result = await collect(network)
    assert result["success"] is False and result["error_code"] == "entry_robots_denied"
    assert "pages" not in result
    assert network.urls == [f"{ORIGIN}/robots.txt"]


# --- duplicates, non-HTML, redirects, oversize --------------------------------

@pytest.mark.asyncio
async def test_duplicates_collapse_by_normalised_and_final_identity():
    routes = base_routes(seed_html=html("Home", ["/a", "/a#frag", "/a?utm_source=x", "/A", "/old"]))
    routes[f"{ORIGIN}/sitemap.xml"] = sitemap(["/a", "/a?gclid=1"])
    routes[f"{ORIGIN}/a"] = {"body": html("A")}
    routes[f"{ORIGIN}/A"] = {"body": html("Upper A")}
    routes[f"{ORIGIN}/old"] = {"status": 301, "headers": {"location": f"{ORIGIN}/a"}, "body": ""}
    network = Network(routes)
    result = await collect(network)
    assert_reconciles(result)
    assert {p["final_url"] for p in result["pages"]} == {f"{ORIGIN}/", f"{ORIGIN}/a", f"{ORIGIN}/A"}
    assert result["collector_counters"]["excluded"]["duplicate_final_destination"] == 1
    assert result["collector_counters"]["discovery_filtered"]["duplicate_discoveries"] >= 4
    assert network.urls.count(f"{ORIGIN}/a") == 2  # direct + via /old redirect


@pytest.mark.asyncio
async def test_non_html_excluded_and_artifacts_never_enter_inventory():
    routes = base_routes(seed_html=html("Home", ["/data", "/brochure.pdf", "/page"]))
    routes[f"{ORIGIN}/data"] = {"body": '{"a": 1}', "content_type": "application/json"}
    routes[f"{ORIGIN}/page"] = {"body": html("Page")}
    network = Network(routes)
    result = await collect(network)
    assert_reconciles(result)
    assert result["collector_counters"]["excluded"]["non_html"] == 1
    assert result["collector_counters"]["discovery_filtered"]["artifact_urls_ignored"] == 1
    assert f"{ORIGIN}/brochure.pdf" not in network.urls
    assert {p["path"] for p in result["pages"]} == {"/", "/page"}


@pytest.mark.asyncio
async def test_cross_origin_and_unsafe_redirects_rejected_before_request():
    routes = base_routes(seed_html=html("Home", ["/go", "/internal", "/loop", "/ok"]))
    routes[f"{ORIGIN}/go"] = {"status": 302, "headers": {"location": "https://evil.example.net/landing"}}
    routes["https://evil.example.net/landing"] = {"body": html("Evil")}
    routes[f"{ORIGIN}/internal"] = {"status": 302, "headers": {"location": "https://internal.example.com/"}}
    routes[f"{ORIGIN}/loop"] = {"status": 302, "headers": {"location": f"{ORIGIN}/loop"}}
    routes[f"{ORIGIN}/ok"] = {"body": html("OK")}
    network = Network(routes)
    result = await collect(network)
    assert_reconciles(result)
    excluded = result["collector_counters"]["excluded"]
    assert excluded["cross_origin_redirect"] == 2  # evil + internal host both off-origin
    assert excluded["unsafe_destination"] == 1  # loop
    assert not any("evil.example.net" in u or "internal.example.com" in u for u in network.urls)
    assert {p["path"] for p in result["pages"]} == {"/", "/ok"}


@pytest.mark.asyncio
async def test_www_alias_entry_redirect_is_adopted_like_run_scan():
    www = "https://www.example.com"
    routes = {
        f"{ORIGIN}/robots.txt": {"body": "User-agent: *\nAllow: /", "content_type": "text/plain"},
        f"{ORIGIN}/": {"status": 301, "headers": {"location": f"{www}/"}},
        f"{www}/robots.txt": {"body": "User-agent: *\nDisallow: /private", "content_type": "text/plain"},
        f"{www}/": {"body": html("Home", [f"{www}/a", f"{www}/private"])},
        f"{www}/a": {"body": html("A")},
    }
    network = Network(routes)
    result = await collect(network)
    assert_reconciles(result)
    assert result["effective_origin"] == www
    assert {p["final_url"] for p in result["pages"]} == {f"{www}/", f"{www}/a"}
    assert result["collector_counters"]["excluded"]["robots_denied"] == 1
    assert f"{www}/private" not in network.urls


@pytest.mark.asyncio
async def test_oversized_response_excluded_and_retained_bytes_budget_fails_closed():
    routes = base_routes(seed_html=html("Home", ["/huge", "/ok"]))
    routes[f"{ORIGIN}/huge"] = {"body": html("Huge", extra="x" * 80_000)}
    routes[f"{ORIGIN}/ok"] = {"body": html("OK")}
    result = await collect(Network(routes), limits=CollectorLimits(
        max_response_bytes=50_000, min_host_interval_seconds=0.05))
    assert_reconciles(result)
    assert result["collector_counters"]["excluded"]["oversized_response"] == 1
    assert {p["path"] for p in result["pages"]} == {"/", "/ok"}

    budget = await collect(Network(catalog_routes(100)), limits=CollectorLimits(
        max_total_retained_bytes=64 * 1024, min_host_interval_seconds=0.05))
    assert budget["success"] is False and budget["error_code"] == "retained_bytes_budget_exceeded"
    assert "pages" not in budget


@pytest.mark.asyncio
async def test_missing_page_evidence_counted_and_all_missing_fails_closed():
    calls = []

    async def flaky(client, url, discovery, *, robots_policy, request_provider):
        calls.append(url)
        if url.endswith("/item-0001"):
            return None
        return await scanner.fetch_and_extract(client, url, discovery,
                                               robots_policy=robots_policy, request_provider=request_provider)

    result = await collect(Network(catalog_routes(3)), page_fetcher=flaky)
    assert_reconciles(result)
    assert result["collector_counters"]["excluded"]["missing_page_evidence"] == 1

    async def nothing(*_a, **_k):
        return "not a page"

    failed = await collect(Network(catalog_routes(3)), page_fetcher=nothing)
    assert failed["success"] is False and failed["error_code"] == "insufficient_evidence"
    assert failed["diagnostics"]["excluded"]["missing_page_evidence"] == 4


# --- deadline and rate limiting (injected clock, no real sleeping) -----------

@pytest.mark.asyncio
async def test_deadline_produces_truthful_partial_and_fails_before_minimum_evidence():
    clock = FakeClock()
    network = Network(catalog_routes(200), clock=clock, latency=1.0)
    limits = CollectorLimits(deadline_seconds=30, fetch_timeout_seconds=1, min_host_interval_seconds=0.05,
                             concurrency=1)
    result = await collect(network, clock=clock, limits=limits)
    assert_reconciles(result)
    assert result["stop_reason"] == "deadline_reached" and result["collector_state"] == "partial_deadline"
    assert 10 < result["pages_crawled"] < 40
    assert result["collector_counters"]["not_attempted"]["deadline_reached"] > 150
    assert clock.now - 1000.0 <= 30

    clock = FakeClock()
    network = Network(catalog_routes(200), clock=clock, latency=1.0)
    failed = await collect(network, clock=clock, limits=CollectorLimits(
        deadline_seconds=30, fetch_timeout_seconds=1, min_host_interval_seconds=0.05,
        concurrency=1, min_retained_pages=100))
    assert failed["success"] is False and failed["error_code"] == "deadline_before_minimum_evidence"
    assert "pages" not in failed


@pytest.mark.asyncio
async def test_per_host_rate_limit_spacing_uses_injected_clock():
    clock = FakeClock()
    network = Network(catalog_routes(20), clock=clock)
    result = await collect(network, clock=clock, limits=CollectorLimits(
        min_host_interval_seconds=1.0, concurrency=4))
    assert_reconciles(result)
    times = [t for _, t in network.log]
    gaps = [b - a for a, b in zip(times, times[1:])]
    assert len(times) == result["resource_usage"]["requests_made"]
    assert min(gaps) >= 1.0 - 1e-9
    assert result["resource_usage"]["min_observed_host_start_gap_seconds"]["example.com"] >= 1.0 - 1e-9
    assert sum(clock.slept) >= len(times) - 2


@pytest.mark.asyncio
async def test_429_is_not_retried_backs_off_and_trips_host_rate_limit():
    clock = FakeClock()
    routes = catalog_routes(12)
    for n in (0, 1, 2):
        routes[f"{ORIGIN}/catalog/item-{n:04d}"] = {"status": 429, "headers": {"retry-after": "7"}}
    network = Network(routes, clock=clock)
    result = await collect(network, clock=clock, limits=CollectorLimits(
        min_host_interval_seconds=0.1, concurrency=1, max_consecutive_rate_limited=2))
    assert_reconciles(result)
    assert result["collector_counters"]["excluded"]["rate_limited"] == 2
    assert result["stop_reason"] == "host_rate_limited"
    log = network.log
    first_429 = next(i for i, (u, _) in enumerate(log) if u.endswith("item-0000"))
    assert log[first_429 + 1][1] - log[first_429][1] >= 7.0  # Retry-After honoured
    assert [u for u, _ in log].count(f"{ORIGIN}/catalog/item-0000") == 1  # never retried


@pytest.mark.asyncio
async def test_request_budget_is_a_counted_stop():
    result = await collect(Network(catalog_routes(50)), limits=CollectorLimits(
        max_requests=13, min_host_interval_seconds=0.05))
    assert_reconciles(result)
    assert result["stop_reason"] == "request_budget_exhausted"
    assert result["resource_usage"]["requests_made"] == 13


@pytest.mark.asyncio
async def test_invalid_requests_fail_closed_without_network():
    network = Network({})
    for url in ("ftp://example.com/", "https://internal.example.com/", "https://u:p@example.com/", "x" * 3000):
        result = await collect(network, url=url)
        assert result["error_code"] == "invalid_request", url
    bad_identity = await collect(network, identity={"scan_id": "only"})
    assert bad_identity["error_code"] == "invalid_request"
    assert network.log == []


def test_collector_is_not_wired_into_any_route():
    source = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text()
    assert "extended500_private_collector" not in source


# --- spawn-isolated run_scan candidate (tests kept from bb703cf04) ---


def frozen():
    return {
        "id": "scan_one", "owner_user_id": "owner_one",
        "project_id": "project_one", "request_id": "request_one",
        "idempotency_key": "request_one", "scan_mode": "extended_500",
        "status": "queued", "attempt_count": 1,
        "website_url": f"{ORIGIN}/", "normalized_domain": "example.com",
        "respect_robots_txt": True, "owner_attested_robots_override": False,
        "path_prefix": None,
    }


def raw_result(n=2):
    pages = [
        {"url": f"{ORIGIN}/p-{i}", "final_url": f"{ORIGIN}/p-{i}",
         "status_code": 200, "content_type": "text/html",
         "title": "Fixture", "main_text": "private main text",
         "_reachability_links": [{"href": f"{ORIGIN}/"}],
         "future_secret_field": "do not leak"}
        for i in range(n)
    ]
    return {
        "success": True, "scan_mode": "extended_500",
        "pages": pages, "crawled_pages": [dict(p) for p in pages],
        "pages_crawled": n, "pages_found": n + 10,
        "scan_coverage": {"urls_attempted": n, "usable_html_pages": n,
                          "unique_retained_destinations": n},
        "release_gate_eligible": False,
    }


def test_private_crawl_is_disabled_before_process_creation(monkeypatch):
    def bomb(*args, **kwargs):
        raise AssertionError("must not create any subprocess")
    monkeypatch.setattr("app.extended500_private_collector.mp.get_context", bomb)
    with pytest.raises(Extended500CollectionRefused, match="collector_disabled"):
        run_isolated_extended500_collection(frozen())
    assert scanner.resolve_scan_budget("advanced")["max_pages"] == 150
    assert scanner.resolve_scan_budget("extended_500")["max_pages"] == 150


@pytest.mark.parametrize("change,expected", [
    ({"scan_mode": "standard_150"}, "frozen_extended500"),
    ({"scan_mode": "advanced"}, "frozen_extended500"),
    ({"status": "complete"}, "frozen_extended500"),
    ({"owner_user_id": "bad owner"}, "identity_invalid"),
    ({"request_id": "../request"}, "identity_invalid"),
    ({"attempt_count": True}, "scope_invalid"),
    ({"attempt_count": 0}, "scope_invalid"),
    ({"respect_robots_txt": False}, "scope_invalid"),
    ({"owner_attested_robots_override": True}, "scope_invalid"),
    ({"path_prefix": "/blog/"}, "scope_invalid"),
    ({"website_url": "https://localhost/"}, "root_url_invalid"),
    ({"website_url": "http://127.0.0.1/"}, "root_url_invalid"),
    ({"website_url": "https://example.com/private"}, "root_url_invalid"),
    ({"website_url": "https://example.com/?token=secret"}, "root_url_invalid"),
    ({"website_url": "https://user:pass@example.com/"}, "root_url_invalid"),
    ({"normalized_domain": "another.com"}, "domain_invalid"),
])
def test_request_fails_closed_for_wrong_owner_scope_mode_or_target(change, expected):
    with pytest.raises(Extended500CollectionRefused, match=expected):
        validate_extended500_collection_request({**frozen(), **change})


@pytest.mark.parametrize("timeout,concurrency", [(19, 4), (121, 4), (120, 0), (120, 9), (True, 4), (120, 1.0)])
def test_invalid_runtime_budgets_rejected(timeout, concurrency):
    with pytest.raises(Extended500CollectionRefused, match="budget_invalid"):
        validate_extended500_collection_request(frozen(), timeout_seconds=timeout, concurrency=concurrency)


@pytest.mark.parametrize("n", [1, 150, 500])
def test_valid_boundary_counts_are_unreviewed_and_private(n):
    projected = validate_extended500_collection_result(frozen(), raw_result(n))
    assert len(projected["pages"]) == projected["pages_crawled"] == n
    assert projected["review_status"] == "not_reviewed"
    assert projected["pages_reviewed"] == 0
    assert projected["release_gate_eligible"] is False
    assert projected["extended500_collector_version"] == COLLECTOR_VERSION
    assert projected["canonical_mode"] == "extended_500"
    assert projected["scan_id"] == "scan_one"
    assert projected["request_id"] == "request_one"
    for page in projected["pages"]:
        for hidden in ["main_text", "_reachability_links", "future_secret_field"]:
            assert hidden not in page
    assert "main_text" in raw_result(1)["pages"][0]


@pytest.mark.parametrize("change,expected", [
    ({"success": False}, "collection_failed"),
    ({"scan_mode": "standard_150"}, "foreign_collection_mode"),
    ({"release_gate_eligible": True}, "must_not_assert_review"),
    ({"review_status": "complete"}, "must_not_assert_review"),
    ({"pages_crawled": 3}, "assessed_count_invalid"),
    ({"pages_crawled": True}, "assessed_count_invalid"),
    ({"pages_found": 0}, "discovered_count_invalid"),
    ({"pages_found": True}, "discovered_count_invalid"),
    ({"scan_coverage": {}}, "coverage_invalid"),
    ({"scan_coverage": {"urls_attempted": 0, "usable_html_pages": 2,
                        "unique_retained_destinations": 2}}, "denominator_invalid"),
    ({"scan_coverage": {"urls_attempted": 2, "usable_html_pages": 3,
                        "unique_retained_destinations": 2}}, "denominator_invalid"),
    ({"scan_coverage": {"urls_attempted": 2, "usable_html_pages": 2,
                        "unique_retained_destinations": 1}}, "denominator_invalid"),
])
def test_untruthful_results_rejected(change, expected):
    with pytest.raises(Extended500CollectionRefused, match=expected):
        validate_extended500_collection_result(frozen(), {**raw_result(2), **change})


def test_reject_501_pages_and_empty_collection_and_duplicate_destinations():
    with pytest.raises(Extended500CollectionRefused, match="budget_exceeded"):
        validate_extended500_collection_result(frozen(), raw_result(501))
    with pytest.raises(Extended500CollectionRefused, match="empty"):
        validate_extended500_collection_result(frozen(), raw_result(0))
    result = raw_result(2)
    result["pages"][1]["final_url"] = result["pages"][0]["final_url"]
    result["crawled_pages"][1]["final_url"] = result["pages"][0]["final_url"]
    with pytest.raises(Extended500CollectionRefused, match="duplicate_destination"):
        validate_extended500_collection_result(frozen(), result)


def test_mirror_inconsistency_and_foreign_raw_page_rejected():
    result = raw_result(2)
    result["crawled_pages"].pop()
    with pytest.raises(Extended500CollectionRefused, match="mirror_mismatch"):
        validate_extended500_collection_result(frozen(), result)
    result = raw_result(2)
    result["pages"][1] = {"title": "missing destination"}
    result["crawled_pages"][1] = {"title": "missing destination"}
    with pytest.raises(Extended500CollectionRefused, match="page_identity_missing"):
        validate_extended500_collection_result(frozen(), result)


class FakeConn:
    def __init__(self):
        self.data = None
        self.closed = False

    def send_bytes(self, value):
        self.data = value

    def close(self):
        self.closed = True


def test_child_injects_500_budget_only_for_extended_mode(monkeypatch):
    seen = {}
    async def fake_run_scan(url, **kwargs):
        seen["url"] = url
        seen["mode"] = kwargs["scan_mode"]
        seen["budget"] = scanner.resolve_scan_budget(kwargs["scan_mode"], kwargs["timeout_seconds"], job_mode=True)
        return raw_result(500)

    monkeypatch.setattr(scanner, "run_scan", fake_run_scan)
    assert scanner.resolve_scan_budget("extended_500")["max_pages"] == 150
    conn = FakeConn()
    try:
        _collector_child(conn, frozen(), 120, 4)
        outcome = json.loads(conn.data)
        assert outcome["ok"] is True, outcome
        assert len(outcome["result"]["pages"]) == 500
        assert outcome["result"]["review_status"] == "not_reviewed"
        assert seen["url"] == f"{ORIGIN}/"
        assert seen["mode"] == "extended_500"
        assert seen["budget"]["max_pages"] == 500
        assert scanner.resolve_scan_budget("advanced")["max_pages"] == 150
    finally:
        scanner.SCAN_BUDGETS.pop("extended_500", None)
    assert conn.closed
    assert scanner.resolve_scan_budget("extended_500")["max_pages"] == 150


@pytest.mark.asyncio
async def test_existing_real_scanner_sitemap_510_does_not_exceed_private_500(monkeypatch):
    """Run production scanner code with only network I/O faked; no public tier edits."""
    from app.extract import extract_page

    class Policy:
        def directive_allowed(self, agent, url):
            return True
        def allowed(self, agent, url):
            return True
        def evidence(self):
            return {}

    class Landing:
        def __init__(self, url):
            self.url = url

    sitemap = [f"{ORIGIN}/item-{i:04d}" for i in range(510)]
    seen = []
    async def robots(*args, **kwargs):
        return Policy()
    async def landing(client, url, **kwargs):
        return Landing(url)
    async def sitemap_loader(*args, **kwargs):
        return list(sitemap)
    async def fetch(client, url, discovery, robots_policy=None):
        seen.append(url)
        await asyncio.sleep(0)
        html = "<html><title>Fixture</title><h1>Item</h1><p>Test page.</p></html>"
        return extract_page(html, url, url, 200, "text/html", discovery, include_links=True)
    async def validate(*args, **kwargs):
        return {}
    async def render(*args, **kwargs):
        return {"attempted": 0}

    monkeypatch.setattr(scanner, "is_public_http_url", lambda url: True)
    monkeypatch.setattr(scanner, "load_robots_policy", robots)
    monkeypatch.setattr(scanner, "safe_get", landing)
    monkeypatch.setattr(scanner, "load_sitemap_urls", sitemap_loader)
    monkeypatch.setattr(scanner, "fetch_and_extract", fetch)
    monkeypatch.setattr(scanner, "validate_canonical_targets", validate)
    monkeypatch.setattr(scanner, "run_render_followup", render)
    monkeypatch.setitem(scanner.SCAN_BUDGETS, "extended_500",
                        {"max_pages": 500, "timeout": 120, "fetch_timeout": 10,
                         "max_sitemap_fetches": 60})
    raw = await scanner.run_scan(f"{ORIGIN}/", scan_mode="extended_500",
                                 job_mode=True, timeout_seconds=120, concurrency=8)
    assert raw["success"] is True
    assert raw["scan_mode"] == "extended_500"
    assert raw["pages_crawled"] == len(raw["pages"]) == 500
    assert len(set(seen)) == 500
    assert raw["pages_found"] >= 500
    result = validate_extended500_collection_result(frozen(), raw)
    assert result["review_status"] == "not_reviewed"
    assert result["release_gate_eligible"] is False
    assert result["scan_coverage"]["unique_retained_destinations"] == 500
    # The original Standard150 mode is not raised.
    assert scanner.resolve_scan_budget("advanced")["max_pages"] == 150
