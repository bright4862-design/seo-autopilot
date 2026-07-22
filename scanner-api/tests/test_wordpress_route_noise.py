import httpx
import pytest

from app.sitemap import fetch_sitemap_locs


@pytest.mark.asyncio
async def test_wordpress_route_noise_is_removed_during_sitemap_ingestion(monkeypatch):
    sitemap_url = "https://example.com/wp-sitemap-posts-page-1.xml"
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://example.com/about/</loc></url>
      <url><loc>https://example.com/category/bread/</loc></url>
      <url><loc>https://example.com/wp-login.php</loc></url>
      <url><loc>https://example.com/wp-login.php?action=lostpassword</loc></url>
      <url><loc>https://example.com/feed/</loc></url>
      <url><loc>https://example.com/comments/feed/</loc></url>
      <url><loc>https://example.com/hello-world/</loc></url>
      <url><loc>https://example.com/category/uncategorized/</loc></url>
    </urlset>
    """

    async def fake_get(_client, _url, _deadline):
        return httpx.Response(200, content=xml.encode("utf-8"))

    monkeypatch.setattr("app.sitemap._safe_get_before_deadline", fake_get)
    artifacts = []
    locs = await fetch_sitemap_locs(
        object(),
        sitemap_url,
        set(),
        artifacts,
    )

    assert locs == [
        "https://example.com/about/",
        "https://example.com/category/bread/",
    ]
    assert {item["url"] for item in artifacts} == {
        "https://example.com/wp-login.php",
        "https://example.com/wp-login.php?action=lostpassword",
        "https://example.com/feed/",
        "https://example.com/comments/feed/",
        "https://example.com/hello-world/",
        "https://example.com/category/uncategorized/",
    }
    assert all(item["url_suspicion_reasons"] == ["wordpress_route_noise"] for item in artifacts)


def test_wordpress_noise_filter_is_shared_by_scanner_queue_and_sitemap():
    from app.artifact_filter import is_artifact_url
    from app import scanner, sitemap

    assert scanner.is_artifact_url is is_artifact_url
    assert sitemap.is_artifact_url is is_artifact_url
