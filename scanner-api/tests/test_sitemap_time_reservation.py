import asyncio
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

    async def fake_safe_get(client, url, **kwargs):
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


def test_sitemap_discovery_can_pace_request_starts(monkeypatch):
    origin = "https://paced.example"
    index_url = f"{origin}/index.xml"
    child_url = f"{origin}/products.xml"
    starts = []

    async def fake_safe_get(client, url, **kwargs):
        starts.append((url, time.monotonic()))
        if url == f"{origin}/robots.txt":
            return FakeResponse(f"Sitemap: {index_url}")
        if url == index_url:
            return FakeResponse(sitemap_xml([child_url], index=True))
        if url == f"{origin}/sitemap.xml":
            return FakeResponse(status_code=404)
        if url == child_url:
            return FakeResponse(sitemap_xml([f"{origin}/products/1"]))
        return FakeResponse(status_code=404)

    monkeypatch.setattr(sitemap, "safe_get", fake_safe_get)
    diagnostics = {}
    urls = asyncio.run(load_sitemap_urls(
        object(),
        origin,
        "/",
        20,
        [],
        deadline=time.monotonic() + 1.0,
        max_fetches=10,
        diagnostics=diagnostics,
        min_request_interval_seconds=0.01,
    ))

    assert f"{origin}/products/1" in urls
    gaps = [later[1] - earlier[1] for earlier, later in zip(starts, starts[1:])]
    assert len(gaps) >= 3
    assert min(gaps) >= 0.008
    assert diagnostics["sitemap_request_interval_seconds"] == 0.01


def test_run_scan_continues_to_page_workers_after_sitemap_budget(monkeypatch):
    captured = {}

    async def fake_load_robots_policy(client, origin):
        return Policy()

    async def fake_safe_get(client, url, **kwargs):
        return FakeResponse(url=url)

    async def fake_load_sitemap_urls(client, origin, prefix, limit, artifacts, scope_evidence=None, *, deadline=None, max_fetches=None, diagnostics=None, min_request_interval_seconds=0.0):
        captured["sitemap_deadline"] = deadline
        captured["sitemap_request_interval_seconds"] = min_request_interval_seconds
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
    monkeypatch.setattr(scanner, "is_public_http_url", lambda _url: True)
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
    assert captured["sitemap_deadline"] > 0
    assert result["crawl_timing"]["crawl_started_at"]
