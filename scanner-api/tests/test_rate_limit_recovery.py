import time

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
