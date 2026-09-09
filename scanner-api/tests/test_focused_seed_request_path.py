import pytest

from app.scanner import run_scan


@pytest.mark.asyncio
async def test_focused_en_seed_preserves_published_trailing_slash_without_broadening_scope(mock_network):
    origin = "https://example.com"
    mock_network({
        f"{origin}/robots.txt": {
            "body": "User-agent: *\nAllow: /\n",
            "status": 200,
            "content_type": "text/plain",
        },
        f"{origin}/sitemap.xml": {
            "body": (
                '<?xml version="1.0"?><urlset>'
                f"<url><loc>{origin}/en/</loc></url>"
                f"<url><loc>{origin}/en/about/</loc></url>"
                f"<url><loc>{origin}/fr/</loc></url>"
                "</urlset>"
            ),
            "status": 200,
            "content_type": "application/xml",
        },
        f"{origin}/en/": {
            "body": (
                '<html><head><title>English</title></head><body><h1>English</h1>'
                '<a href="/en/about/">About</a><a href="/fr/">French</a>'
                '<a href="https://other.example.com/en/">Other host</a>'
                '</body></html>'
            ),
            "status": 200,
            "content_type": "text/html",
        },
        f"{origin}/en": {
            "body": "wrong route",
            "status": 410,
            "content_type": "text/html",
        },
        f"{origin}/en/about/": {
            "body": '<html><head><title>About</title></head><body><h1>About</h1></body></html>',
            "status": 200,
            "content_type": "text/html",
        },
        f"{origin}/fr/": {
            "body": '<html><head><title>French</title></head><body><h1>French</h1></body></html>',
            "status": 200,
            "content_type": "text/html",
        },
    })

    result = await run_scan(
        f"{origin}/en/",
        path_prefix="/en/",
        scan_mode="basic",
        concurrency=1,
    )

    assert result["success"] is True
    assert result["website_url"] == f"{origin}/en/"
    assert result["crawl_scope"]["requested_seed_path"] == "/en"
    assert result["crawl_scope"]["requested_path_prefix"] == "/en"
    assert result["crawl_scope"]["effective_path_prefix"] == "/en"
    assert any(page["url"] == f"{origin}/en/" and page["status_code"] == 200 for page in result["pages"])
    assert not any(page["url"] == f"{origin}/en" for page in result["pages"])
    assert not any(page["path"].startswith("/fr") for page in result["pages"])
    assert not any("other.example.com" in page["url"] for page in result["pages"])
