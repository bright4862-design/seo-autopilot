import pytest

from app import scanner


def _html(body: str = "") -> str:
    return f"<html><head><title>Page</title><meta name='description' content='Useful page'></head><body><h1>Page</h1>{body}</body></html>"


@pytest.mark.asyncio
async def test_sitemap_and_internal_links_request_the_published_trailing_slash(monkeypatch, mock_network):
    origin = "https://example.com"
    monkeypatch.setitem(scanner.SCAN_BUDGETS, "basic", {"max_pages": 6, "timeout": 20, "fetch_timeout": 3, "max_sitemap_fetches": 2})
    requests = mock_network({
        f"{origin}/robots.txt": {"body": "User-agent: *\nAllow: /", "content_type": "text/plain"},
        f"{origin}/sitemap.xml": {"body": (
            "<urlset>"
            f"<url><loc>{origin}/From-Sitemap/?Q=1#fragment</loc></url>"
            "<url><loc>https://www.example.com/alias/</loc></url>"
            "<url><loc>http://example.com/scheme/</loc></url>"
            "<url><loc>https://other.example.com/foreign/</loc></url>"
            "</urlset>"
        ), "content_type": "application/xml"},
        f"{origin}/": {"body": _html('<a href="/From-Link/">Link</a>')},
        f"{origin}/From-Sitemap/?Q=1": {"body": _html()},
        f"{origin}/From-Link/": {"body": _html()},
        f"{origin}/From-Sitemap?Q=1": {"status": 410, "body": "wrong route"},
        f"{origin}/From-Link": {"status": 410, "body": "wrong route"},
    })

    result = await scanner.run_scan(f"{origin}/", scan_mode="basic", concurrency=1)
    requested = [request.headers.get("host", "") + request.url.raw_path.decode("ascii") for request in requests]

    assert "example.com/From-Sitemap/?Q=1" in requested
    assert "example.com/From-Link/" in requested
    assert "example.com/From-Sitemap?Q=1" not in requested
    assert "example.com/From-Link" not in requested
    assert not any(value.startswith(("www.example.com/alias", "other.example.com/foreign")) for value in requested)
    assert result["crawl_scope"]["sitemap_urls_excluded_outside_scope"] == 3
    assert result["pages_found"] == 3
    assert not [finding for finding in result["findings"] if finding.get("rule") in {"sitemap_redirect", "internal_link_redirect"}]


@pytest.mark.asyncio
async def test_distinct_published_slash_variants_returning_200_are_not_collapsed(monkeypatch, mock_network):
    origin = "https://example.com"
    monkeypatch.setitem(scanner.SCAN_BUDGETS, "basic", {"max_pages": 4, "timeout": 20, "fetch_timeout": 3, "max_sitemap_fetches": 2})
    mock_network({
        f"{origin}/robots.txt": {"body": "User-agent: *\nAllow: /", "content_type": "text/plain"},
        f"{origin}/sitemap.xml": {"body": f"<urlset><url><loc>{origin}/x</loc></url><url><loc>{origin}/x/</loc></url></urlset>", "content_type": "application/xml"},
        f"{origin}/": {"body": _html()},
        f"{origin}/x": {"body": _html("slashless")},
        f"{origin}/x/": {"body": _html("slash")},
    })
    result = await scanner.run_scan(f"{origin}/", scan_mode="basic", concurrency=1)
    urls = {page["url"] for page in result["pages"]}
    assert {f"{origin}/x", f"{origin}/x/"}.issubset(urls)
    assert result["technical_audit_summary"]["final_url_duplicates_deduped"] == 0


@pytest.mark.asyncio
async def test_real_redirecting_aliases_merge_at_the_observed_final_url(monkeypatch, mock_network):
    origin = "https://example.com"
    monkeypatch.setitem(scanner.SCAN_BUDGETS, "basic", {"max_pages": 4, "timeout": 20, "fetch_timeout": 3, "max_sitemap_fetches": 2})
    requests = mock_network({
        f"{origin}/robots.txt": {"body": "User-agent: *\nAllow: /", "content_type": "text/plain"},
        f"{origin}/sitemap.xml": {"body": f"<urlset><url><loc>{origin}/one</loc></url><url><loc>{origin}/two</loc></url></urlset>", "content_type": "application/xml"},
        f"{origin}/": {"body": _html()},
        f"{origin}/one": {"status": 301, "headers": {"location": "/final/"}},
        f"{origin}/two": {"status": 302, "headers": {"location": "/final/"}},
        f"{origin}/final/": {"body": _html()},
    })
    result = await scanner.run_scan(f"{origin}/", scan_mode="basic", concurrency=1)
    requested_paths = [request.url.raw_path.decode("ascii") for request in requests]

    assert "/one" in requested_paths and "/two" in requested_paths
    assert requested_paths.count("/final/") == 2
    assert result["technical_audit_summary"]["final_url_duplicates_deduped"] == 1
    redirected = next(page for page in result["pages"] if page.get("final_url") == f"{origin}/final/")
    assert redirected["url"] == f"{origin}/one"
    assert redirected["redirect_alias_total"] == 1
    assert redirected["redirect_aliases"][0]["url"] == f"{origin}/two"
    assert redirected["redirect_aliases"][0]["redirect_destination_url"] == f"{origin}/final/"
