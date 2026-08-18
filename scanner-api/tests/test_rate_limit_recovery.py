import time

import httpx
import pytest

import app.scanner as scanner
from app.extract import extract_page
from tests import fixtures as fx


@pytest.mark.asyncio
async def test_single_429_activates_pacing_and_retries_once(mock_network, monkeypatch):
    origin = "https://rate-limit.example"
    routes = {
        f"{origin}/sitemap.xml": fx._xml(fx._sitemap([
            f"{origin}/section",
            f"{origin}/section/p1",
            f"{origin}/section/p2",
        ])),
        f"{origin}/section": fx._html(fx._page("Hub")),
        f"{origin}/section/p1": fx._html(fx._page("Recovered page")),
        f"{origin}/section/p2": fx._html(fx._page("Other page")),
    }
    mock_network(routes)

    original_fetch = scanner.fetch_and_extract
    attempts = {}

    async def one_time_429(client, url, discovery, robots_policy=None):
        attempts[url] = attempts.get(url, 0) + 1
        if url.endswith("/section/p1") and attempts[url] == 1:
            return extract_page("", url, url, 429, "text/html", discovery)
        return await original_fetch(client, url, discovery, robots_policy=robots_policy)

    monkeypatch.setattr(scanner, "fetch_and_extract", one_time_429)
    monkeypatch.setattr(scanner, "RATE_LIMIT_COOLDOWN_SECONDS", 0.001, raising=False)
    monkeypatch.setattr(scanner, "RATE_LIMIT_REQUEST_INTERVAL_SECONDS", 0.001, raising=False)
    monkeypatch.setattr(scanner, "RATE_LIMIT_BACKOFF_INTERVAL_SECONDS", 0.001, raising=False)
    monkeypatch.setattr(scanner, "RATE_LIMIT_MAX_INTERVAL_SECONDS", 0.005, raising=False)

    result = await scanner.run_scan(
        f"{origin}/section",
        path_prefix="/section",
        scan_mode="advanced",
        concurrency=4,
        timeout_seconds=120,
        job_mode=True,
    )

    p1 = next(page for page in result["pages"] if page["path"] == "/section/p1")
    assert p1["status_code"] == 200
    assert attempts[f"{origin}/section/p1"] == 2
    assert result["crawl_timing"]["rate_limit_throttle_activated"] is True
    assert result["crawl_timing"]["rate_limit_retry_count"] == 1
    assert result["crawl_timing"]["rate_limit_recovered_count"] == 1


@pytest.mark.asyncio
async def test_cloudflare_shopify_profile_paces_before_first_429(mock_network, monkeypatch):
    origin = "https://paced-shop.example"
    urls = [f"{origin}/p{i}" for i in range(6)]
    routes = {
        f"{origin}/sitemap.xml": fx._xml(fx._sitemap([f"{origin}/", *urls])),
        f"{origin}/": fx._html(fx._page("Shop")),
        **{url: fx._html(fx._page(f"Product {index}")) for index, url in enumerate(urls)},
    }
    mock_network(routes)

    original_fetch = scanner.fetch_and_extract
    original_load_sitemap_urls = scanner.load_sitemap_urls
    captured_sitemap_interval = {}
    last_started_at = 0.0
    blocked_attempts = 0

    async def capture_sitemap_interval(*args, **kwargs):
        captured_sitemap_interval["seconds"] = kwargs.get("min_request_interval_seconds")
        return await original_load_sitemap_urls(*args, **kwargs)

    async def burst_sensitive(client, url, discovery, robots_policy=None):
        nonlocal last_started_at, blocked_attempts
        now = time.monotonic()
        too_fast = last_started_at > 0 and now - last_started_at < 0.003
        last_started_at = now
        if too_fast:
            blocked_attempts += 1
            return extract_page("", url, url, 429, "text/html", discovery)
        return await original_fetch(client, url, discovery, robots_policy=robots_policy)

    monkeypatch.setattr(scanner, "fetch_and_extract", burst_sensitive)
    monkeypatch.setattr(scanner, "load_sitemap_urls", capture_sitemap_interval)
    monkeypatch.setattr(scanner, "detect_rate_limit_profile", lambda _response: "cloudflare_shopify", raising=False)
    monkeypatch.setattr(scanner, "RATE_LIMIT_COOLDOWN_SECONDS", 0.005, raising=False)
    monkeypatch.setattr(scanner, "RATE_LIMIT_PROACTIVE_REQUEST_INTERVAL_SECONDS", 0.005, raising=False)

    result = await scanner.run_scan(
        f"{origin}/",
        path_prefix=None,
        scan_mode="advanced",
        concurrency=8,
        timeout_seconds=120,
        job_mode=True,
    )

    assert blocked_attempts == 0
    assert captured_sitemap_interval["seconds"] == 0.005
    assert result["crawl_timing"]["rate_limit_proactive_profile"] == "cloudflare_shopify"
    assert result["crawl_timing"]["rate_limit_throttle_activated"] is True
    assert result["crawl_timing"]["rate_limit_retry_count"] == 0
    assert all(page["status_code"] == 200 for page in result["pages"])


@pytest.mark.asyncio
async def test_real_429_escalates_spacing_before_following_requests(mock_network, monkeypatch):
    origin = "https://adaptive-shop.example"
    urls = [f"{origin}/p{i}" for i in range(5)]
    routes = {
        f"{origin}/sitemap.xml": fx._xml(fx._sitemap([f"{origin}/", *urls])),
        f"{origin}/": fx._html(fx._page("Shop")),
        **{url: fx._html(fx._page(f"Product {index}")) for index, url in enumerate(urls)},
    }
    mock_network(routes)

    original_fetch = scanner.fetch_and_extract
    last_started_at = 0.0
    blocked_attempts = 0

    async def burst_sensitive(client, url, discovery, robots_policy=None):
        nonlocal last_started_at, blocked_attempts
        now = time.monotonic()
        too_fast = last_started_at > 0 and now - last_started_at < 0.003
        last_started_at = now
        if too_fast:
            blocked_attempts += 1
            return extract_page("", url, url, 429, "text/html", discovery)
        return await original_fetch(client, url, discovery, robots_policy=robots_policy)

    monkeypatch.setattr(scanner, "fetch_and_extract", burst_sensitive)
    monkeypatch.setattr(scanner, "detect_rate_limit_profile", lambda _response: "cloudflare_shopify", raising=False)
    monkeypatch.setattr(scanner, "RATE_LIMIT_PROACTIVE_REQUEST_INTERVAL_SECONDS", 0.001, raising=False)
    monkeypatch.setattr(scanner, "RATE_LIMIT_COOLDOWN_SECONDS", 0.001, raising=False)
    monkeypatch.setattr(scanner, "RATE_LIMIT_BACKOFF_INTERVAL_SECONDS", 0.005, raising=False)
    monkeypatch.setattr(scanner, "RATE_LIMIT_MAX_INTERVAL_SECONDS", 0.008, raising=False)

    result = await scanner.run_scan(
        f"{origin}/",
        scan_mode="advanced",
        concurrency=8,
        timeout_seconds=120,
        job_mode=True,
    )

    assert blocked_attempts >= 1
    assert result["crawl_timing"]["rate_limit_recovered_count"] >= 1
    assert result["crawl_timing"]["rate_limit_final_interval_seconds"] >= 0.005
    assert all(page["status_code"] == 200 for page in result["pages"])


@pytest.mark.asyncio
async def test_initial_cloudflare_429_cools_down_once_then_recovers_before_sitemap(mock_network, monkeypatch):
    origin = "https://initial-throttle.example"
    shopify_home = fx._page("Shop") + '<script src="https://cdn.shopify.com/theme.js"></script><script>Shopify.theme = {};</script>'
    routes = {
        f"{origin}/robots.txt": {"body": "", "status": 404, "content_type": "text/plain"},
        f"{origin}/sitemap.xml": fx._xml(fx._sitemap([f"{origin}/", f"{origin}/p1", f"{origin}/p2"])),
        f"{origin}/": {"body": shopify_home, "status": 200, "content_type": "text/html", "headers": {"server": "cloudflare"}},
        f"{origin}/p1": fx._html(fx._page("Product 1")),
        f"{origin}/p2": fx._html(fx._page("Product 2")),
    }
    mock_network(routes)

    original_safe_get = scanner.safe_get
    landing_calls = 0

    async def first_landing_is_429(client, url, *args, **kwargs):
        nonlocal landing_calls
        if url == f"{origin}/":
            landing_calls += 1
            if landing_calls == 1:
                return httpx.Response(
                    429,
                    headers={"server": "cloudflare", "content-type": "text/html"},
                    text="<html><title>Verifying your connection...</title></html>",
                    request=httpx.Request("GET", url),
                )
        return await original_safe_get(client, url, *args, **kwargs)

    monkeypatch.setattr(scanner, "safe_get", first_landing_is_429)
    monkeypatch.setattr(scanner, "RATE_LIMIT_INITIAL_COOLDOWN_SECONDS", 0.001, raising=False)
    monkeypatch.setattr(scanner, "RATE_LIMIT_PROACTIVE_REQUEST_INTERVAL_SECONDS", 0.001, raising=False)

    result = await scanner.run_scan(
        f"{origin}/",
        scan_mode="advanced",
        concurrency=4,
        timeout_seconds=120,
        job_mode=True,
    )

    assert landing_calls >= 2
    assert result["crawl_timing"]["rate_limit_initial_retry_count"] == 1
    assert result["crawl_timing"]["rate_limit_initial_recovered"] is True
    assert result["crawl_timing"]["rate_limit_initial_blocked"] is False
    assert result["crawl_timing"]["rate_limit_proactive_profile"] == "cloudflare_shopify"
    assert result["pages_found"] >= 3
    assert all(page["status_code"] == 200 for page in result["pages"])


@pytest.mark.asyncio
async def test_persistent_initial_cloudflare_429_stops_before_sitemap_fanout(mock_network, monkeypatch):
    origin = "https://persistently-throttled.example"
    routes = {
        f"{origin}/robots.txt": {"body": "", "status": 404, "content_type": "text/plain"},
        f"{origin}/": fx._html(fx._page("Normally reachable")),
    }
    mock_network(routes)

    original_safe_get = scanner.safe_get
    landing_calls = 0

    async def always_throttled_landing(client, url, *args, **kwargs):
        nonlocal landing_calls
        if url == f"{origin}/":
            landing_calls += 1
            return httpx.Response(
                429,
                headers={"server": "cloudflare", "content-type": "text/html"},
                text="<html><title>Verifying your connection...</title><body><h1>Your connection needs to be verified before you can proceed</h1></body></html>",
                request=httpx.Request("GET", url),
            )
        return await original_safe_get(client, url, *args, **kwargs)

    async def sitemap_must_not_run(*args, **kwargs):
        raise AssertionError("sitemap discovery must not fan out while the landing page remains Cloudflare-throttled")

    monkeypatch.setattr(scanner, "safe_get", always_throttled_landing)
    monkeypatch.setattr(scanner, "load_sitemap_urls", sitemap_must_not_run)
    monkeypatch.setattr(scanner, "RATE_LIMIT_INITIAL_COOLDOWN_SECONDS", 0.001, raising=False)

    result = await scanner.run_scan(
        f"{origin}/",
        scan_mode="advanced",
        concurrency=8,
        timeout_seconds=120,
        job_mode=True,
    )

    assert landing_calls == 2
    assert result["crawl_timing"]["rate_limit_initial_retry_count"] == 1
    assert result["crawl_timing"]["rate_limit_initial_recovered"] is False
    assert result["crawl_timing"]["rate_limit_initial_blocked"] is True
    assert result["crawl_timing"]["sitemap_fetch_count"] == 0
    assert result["pages_crawled"] == 1
    assert result["pages"][0]["status_code"] == 429
