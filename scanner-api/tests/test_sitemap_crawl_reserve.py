import time

import pytest

from app import sitemap


class FakeResponse:
    def __init__(self, text: str, status_code: int = 200, content_type: str = "application/xml"):
        self.text = text
        self.content = text.encode("utf-8")
        self.status_code = status_code
        self.encoding = "utf-8"
        self.headers = {"content-type": content_type}


def test_sitemap_deadline_reserves_part_of_the_global_budget(monkeypatch):
    monkeypatch.setattr(sitemap.time, "monotonic", lambda: 100.0)

    discovery_deadline, reserve = sitemap._sitemap_deadline(175.0, None)

    assert reserve == 30.0
    assert discovery_deadline == 145.0
    assert discovery_deadline < 175.0


def test_explicit_crawl_reserve_is_honored(monkeypatch):
    monkeypatch.setattr(sitemap.time, "monotonic", lambda: 100.0)

    discovery_deadline, reserve = sitemap._sitemap_deadline(140.0, 12.0)

    assert reserve == 12.0
    assert discovery_deadline == 128.0


@pytest.mark.asyncio
async def test_sitemap_diagnostics_are_written_to_existing_scope_evidence(monkeypatch):
    async def fake_safe_get(client, url):
        if url.endswith("/robots.txt"):
            return FakeResponse("Sitemap: https://example.com/sitemap.xml", content_type="text/plain")
        return FakeResponse(
            "<?xml version='1.0'?><urlset>"
            "<url><loc>https://example.com/products/widget</loc></url>"
            "<url><loc>https://example.com/about</loc></url>"
            "</urlset>"
        )

    monkeypatch.setattr(sitemap, "safe_get", fake_safe_get)
    scope = {}
    artifacts = []

    urls = await sitemap.load_sitemap_urls(
        object(),
        "https://example.com",
        "/",
        100,
        artifacts,
        scope,
        deadline=time.monotonic() + 60,
        max_fetches=10,
        crawl_reserve_seconds=20,
    )

    assert urls == [
        "https://example.com/products/widget",
        "https://example.com/about",
    ]
    assert scope["sitemap_discovery_version"] == sitemap.SITEMAP_DISCOVERY_VERSION
    assert scope["sitemap_crawl_reserve_seconds"] == 20.0
    assert scope["sitemap_fetch_limit"] == 10
    assert scope["sitemap_fetches_attempted"] == 1
    assert scope["sitemap_urls_discovered"] == 2
    assert scope["sitemap_root_count"] == 1
    assert scope["sitemap_child_count"] == 0
    assert scope["sitemap_deadline_reached"] is False
    assert scope["sitemap_stopped_for_crawl_reserve"] is False
    assert scope["sitemap_discovery_elapsed_ms"] >= 0
