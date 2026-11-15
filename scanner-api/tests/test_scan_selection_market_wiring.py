"""Observed market hints rank discovery and selection without narrowing scope."""

import asyncio
from datetime import datetime, timezone

import httpx
import pytest

from app import scanner
from app.extract import extract_page
from app.robots_policy import RobotsPolicy


@pytest.mark.parametrize(
    "final_url,status,expected",
    [
        ("https://example.com/fr/", 200, "/fr"),
        ("https://example.com/us/", 200, "/us"),
        ("https://example.com/us/en/", 200, "/us/en"),
        ("https://example.com/france/", 200, ""),
        ("https://example.com/fr/", 404, ""),
        ("https://elsewhere.example/fr/", 200, ""),
    ],
)
def test_only_successful_same_origin_landing_market_ranks_both_stages(
    monkeypatch, final_url, status, expected,
):
    captured = {}
    real_select = scanner.select_balanced_urls

    async def robots(*args, **kwargs):
        return RobotsPolicy("https://example.com/robots.txt", "missing", 404)

    async def landing(*args, **kwargs):
        return httpx.Response(status, text="<html></html>", request=httpx.Request("GET", final_url))

    async def discovery(*args, **kwargs):
        captured["discovery_hint"] = kwargs.get("primary_market_hint", "")
        return []

    def select(*args, **kwargs):
        captured["selection_hint"] = kwargs.get("preferred_market", "")
        captured["selection_time"] = kwargs.get("now")
        return real_select(*args, **kwargs)

    async def fetch(client, url, discovery, robots_policy=None):
        return extract_page(
            "<html><head><title>Example business</title></head>"
            "<body><h1>Example business</h1><p>Useful public business information.</p></body></html>",
            url, url, 200, "text/html", discovery,
        )

    async def validate(*args, **kwargs):
        return {}

    async def render(*args, **kwargs):
        return {"attempted": 0}

    monkeypatch.setattr(scanner, "load_robots_policy", robots)
    monkeypatch.setattr(scanner, "is_public_http_url", lambda _url: True)
    monkeypatch.setattr(scanner, "safe_get", landing)
    monkeypatch.setattr(scanner, "load_sitemap_urls", discovery)
    monkeypatch.setattr(scanner, "select_balanced_urls", select)
    monkeypatch.setattr(scanner, "fetch_and_extract", fetch)
    monkeypatch.setattr(scanner, "validate_canonical_targets", validate)
    monkeypatch.setattr(scanner, "run_render_followup", render)

    async def run():
        state = await scanner.plan_scan("https://example.com/", scan_mode="basic", concurrency=1, staged=True)
        snapshot = state.to_dict()
        await scanner.crawl_batch(state)
        return snapshot, await scanner.finalize_scan(state)

    snapshot, result = asyncio.run(run())

    assert captured["discovery_hint"] == captured["selection_hint"] == expected
    assert snapshot["selection_preferred_market"] == expected
    captured_at = datetime.fromisoformat(snapshot["selection_captured_at"])
    assert captured_at.tzinfo == timezone.utc and captured_at == captured["selection_time"]
    assert "selection_preferred_market" not in result["crawl_timing"]
    assert "selection_captured_at" not in result["crawl_timing"]
    assert scanner.ScanState.from_dict(snapshot).selection_captured_at == snapshot["selection_captured_at"]
    snapshot.pop("selection_preferred_market")
    snapshot.pop("selection_captured_at")
    assert scanner.ScanState.from_dict(snapshot).selection_captured_at == ""
    # The pre-existing two-segment market redirect scopes this case already.
    # A single language hint must not introduce a new scope restriction.
    assert result["crawl_scope"]["effective_path_prefix"] == ("/us/en" if expected == "/us/en" else "/")
    assert result["pages_crawled"] == 1
    assert result["sampling_evidence"]["pages_checked"] == 1


def test_selector_replays_sitemap_recency_with_captured_clock(monkeypatch):
    from app import page_importance

    captured_at = datetime(2026, 11, 14, 21, 55, 0, 4567, tzinfo=timezone.utc)
    observed = []
    real_importance = page_importance.build_page_importance

    def score(*args, **kwargs):
        observed.append(kwargs.get("now"))
        return real_importance(*args, **kwargs)

    monkeypatch.setattr(page_importance, "build_page_importance", score)
    paths = ["/products/prod-one", "/products/prod-two", "/solutions"]
    selected = scanner.select_balanced_urls(paths, lambda _: "general", lambda path: path, 2, now=captured_at)
    assert len(selected) == 2
    assert observed == [captured_at]
