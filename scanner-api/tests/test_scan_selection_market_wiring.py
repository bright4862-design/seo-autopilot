"""Observed market hints rank discovery and selection without narrowing scope."""

import asyncio

import httpx
import pytest

from app import scanner
from app.extract import extract_page


@pytest.mark.parametrize(
    "final_url,status,expected",
    [
        ("https://example.com/fr/", 200, "/fr"),
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

    class Policy:
        def allowed(self, user_agent, url):
            return True

        def evidence(self):
            return {"state": "allowed"}

    async def robots(*args, **kwargs):
        return Policy()

    async def landing(*args, **kwargs):
        return httpx.Response(status, text="<html></html>", request=httpx.Request("GET", final_url))

    async def discovery(*args, **kwargs):
        captured["discovery_hint"] = kwargs.get("primary_market_hint", "")
        return []

    def select(*args, **kwargs):
        captured["selection_hint"] = kwargs.get("preferred_market", "")
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

    result = asyncio.run(scanner.run_scan("https://example.com/", scan_mode="basic", concurrency=1))

    assert captured == {"discovery_hint": expected, "selection_hint": expected}
    # The pre-existing two-segment market redirect scopes this case already.
    # A single language hint must not introduce a new scope restriction.
    assert result["crawl_scope"]["effective_path_prefix"] == ("/us/en" if expected == "/us/en" else "/")
    assert result["pages_crawled"] == 1
    assert result["sampling_evidence"]["pages_checked"] == 1
