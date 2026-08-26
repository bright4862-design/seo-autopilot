from datetime import datetime, timezone

import pytest

import app.scanner as scanner
from app.extract import extract_page
from tests import fixtures as fx


def test_retry_after_accepts_seconds_and_http_date():
    now = datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc)
    assert scanner.parse_retry_after_seconds("3", now=now) == 3.0
    assert scanner.parse_retry_after_seconds(
        "Tue, 25 Aug 2026 12:00:07 GMT",
        now=now,
    ) == 7.0
    assert scanner.parse_retry_after_seconds("garbage", now=now) == 0.0
    assert scanner.parse_retry_after_seconds("inf", now=now) == 0.0
    assert scanner.parse_retry_after_seconds("-inf", now=now) == 0.0
    assert scanner.parse_retry_after_seconds("nan", now=now) == 0.0


def test_transient_pressure_classification_is_narrow():
    assert scanner.transient_pressure_kind({"status_code": 429}) == "429"
    assert scanner.transient_pressure_kind({"status_code": 503}) == "5xx"
    assert scanner.transient_pressure_kind({"status_code": 404}) == ""
    assert scanner.transient_pressure_kind({
        "status_code": 0,
        "fetch_error": "ReadTimeout while waiting for origin",
    }) == "network"
    assert scanner.transient_pressure_kind({
        "status_code": 0,
        "fetch_error": "blocked_non_public_redirect",
    }) == ""


@pytest.mark.asyncio
async def test_transient_503_backs_off_and_recovers(mock_network, monkeypatch):
    origin = "https://pressure.example"
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

    async def one_time_503(client, url, discovery, robots_policy=None):
        attempts[url] = attempts.get(url, 0) + 1
        if url.endswith("/section/p1") and attempts[url] == 1:
            return extract_page("", url, url, 503, "text/html", discovery)
        return await original_fetch(client, url, discovery, robots_policy=robots_policy)

    monkeypatch.setattr(scanner, "fetch_and_extract", one_time_503)
    monkeypatch.setattr(scanner, "RATE_LIMIT_COOLDOWN_SECONDS", 0.001, raising=False)
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
    assert result["crawl_timing"]["crawl_pressure_5xx_count"] >= 1
    assert result["crawl_timing"]["rate_limit_retry_count"] >= 1
    assert result["crawl_timing"]["rate_limit_recovered_count"] >= 1


@pytest.mark.asyncio
async def test_healthy_responses_reduce_backoff_gradually(monkeypatch):
    monkeypatch.setattr(scanner, "RATE_LIMIT_BACKOFF_INTERVAL_SECONDS", 4.0, raising=False)
    monkeypatch.setattr(scanner, "PRESSURE_RECOVERY_HEALTHY_RESPONSES", 3, raising=False)
    pacer = scanner._AdaptiveRateLimitPacer(
        deadline=10_000_000_000.0,
        enabled=True,
        start_active=False,
        request_interval_seconds=0.5,
    )
    await pacer.activate("503")
    pressured_interval = pacer.request_interval_seconds
    assert pressured_interval >= 4.0

    await pacer.note_success()
    await pacer.note_success()
    assert pacer.request_interval_seconds == pressured_interval
    await pacer.note_success()

    assert 0.5 <= pacer.request_interval_seconds < pressured_interval


@pytest.mark.asyncio
async def test_retry_after_can_consume_remaining_deadline_without_hammering(monkeypatch):
    # Unit-level proof: a server-specified delay later than the crawl deadline
    # makes the pacer stop rather than immediately retry.
    now = scanner.time.monotonic()
    pacer = scanner._AdaptiveRateLimitPacer(
        deadline=now + 0.01,
        enabled=True,
        start_active=False,
        request_interval_seconds=0.001,
    )
    monkeypatch.setattr(scanner, "RATE_LIMIT_COOLDOWN_SECONDS", 0.001, raising=False)
    monkeypatch.setattr(scanner, "RATE_LIMIT_BACKOFF_INTERVAL_SECONDS", 0.001, raising=False)
    await pacer.activate("429", retry_after_seconds=30.0)
    assert await pacer.wait_for_slot() is False
    assert pacer.retry_after_max_seconds == 30.0
