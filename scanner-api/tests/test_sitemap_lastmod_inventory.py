import asyncio

from app import sitemap


class Response:
    status_code = 200
    encoding = "utf-8"

    def __init__(self, text):
        self.content = text.encode()
        self.text = text


def test_lastmod_parser_retains_exact_published_urls_and_ignores_comments():
    body = """<urlset xmlns:s='https://www.sitemaps.org/schemas/sitemap/0.9'>
      <!-- <url><loc>https://example.com/ignored</loc><lastmod>2020-01-01</lastmod></url> -->
      <s:url><s:loc>https://example.com/A?x=1&amp;y=2</s:loc><s:lastmod>2026-11-10</s:lastmod></s:url>
      <url><loc><![CDATA[https://example.com/B?a=1&b=2]]></loc><lastmod>2026-10-01T00:00:00Z</lastmod></url>
      <url><loc>https://example.com/no-date</loc></url>
    </urlset>"""
    assert sitemap.parse_sitemap_lastmod(body) == {
        "https://example.com/A?x=1&y=2": "2026-11-10",
        "https://example.com/B?a=1&b=2": "2026-10-01T00:00:00Z",
    }


def test_inventory_cap_and_lastmod_are_reported_without_changing_url_return(monkeypatch):
    origin = "https://example.com"
    body = "<urlset>" + "".join(f"<url><loc>{origin}/products/{i}</loc><lastmod>2026-11-{i + 1:02d}</lastmod></url>" for i in range(5)) + "</urlset>"

    async def get(client, url, **kwargs):
        return Response(body if url.endswith("sitemap.xml") else "")

    monkeypatch.setattr(sitemap, "safe_get", get)
    diagnostics = {}
    urls = asyncio.run(sitemap.load_sitemap_urls(object(), origin, "/", 3, [], diagnostics=diagnostics))
    assert len(urls) == 3
    assert diagnostics["inventory_capped"] is True
    assert diagnostics["sitemap_lastmod"] == {url: f"2026-11-{int(url.rsplit('/', 1)[1]) + 1:02d}" for url in urls}


def test_complete_small_inventory_is_not_reported_capped(monkeypatch):
    async def get(client, url, **kwargs):
        return Response("<urlset><url><loc>https://example.com/product</loc><lastmod>2026-11-01</lastmod></url></urlset>" if url.endswith("sitemap.xml") else "")

    monkeypatch.setattr(sitemap, "safe_get", get)
    diagnostics = {}
    urls = asyncio.run(sitemap.load_sitemap_urls(object(), "https://example.com", "/", 100, [], diagnostics=diagnostics))
    assert urls == ["https://example.com/product"]
    assert diagnostics["inventory_capped"] is False
