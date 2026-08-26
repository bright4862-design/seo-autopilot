import asyncio
import gzip

from app import sitemap
from app.sitemap import (
    fetch_sitemap_locs,
    load_sitemap_urls,
    normalize_sitemap_page_url,
    rank_child_sitemaps,
)


class FakeResponse:
    def __init__(self, text="", *, content=None, status_code=200):
        self.status_code = status_code
        self.content = content if content is not None else text.encode("utf-8")
        self.encoding = "utf-8"

    @property
    def text(self):
        try:
            return self.content.decode("utf-8")
        except UnicodeDecodeError:
            return ""


def sitemap_xml(urls, *, index=False):
    outer = "sitemapindex" if index else "urlset"
    item = "sitemap" if index else "url"
    body = "".join(f"<{item}><loc>{url}</loc></{item}>" for url in urls)
    return f'<?xml version="1.0" encoding="UTF-8"?><{outer}>{body}</{outer}>'


def test_parse_sitemap_locs_ignores_commented_out_entries():
    body = """<?xml version="1.0"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <!-- <url><loc>https://example.com/commented-out</loc></url> -->
      <url><loc>https://example.com/kept</loc></url>
      <url><loc><![CDATA[https://example.com/cdata?x=1&y=2]]></loc></url>
    </urlset>
    """

    assert sitemap.parse_sitemap_locs(body) == [
        "https://example.com/kept",
        "https://example.com/cdata?x=1&y=2",
    ]


def test_parse_sitemap_locs_uses_xml_entities_and_preserves_cdata():
    body = """<urlset>
      <url><loc>https://example.com/p?a=1&amp;b=2</loc></url>
      <url><loc>https://example.com/p?a=1&amp;copy=2</loc></url>
      <url><loc>https://example.com/p?literal=&copy;2</loc></url>
      <url><loc>https://example.com/p?decimal=&#65;&amp;hex=&#x42;</loc></url>
      <url><loc><![CDATA[https://example.com/p?literal=&amp;&copy;]]></loc></url>
    </urlset>"""

    assert sitemap.parse_sitemap_locs(body) == [
        "https://example.com/p?a=1&b=2",
        "https://example.com/p?a=1&copy=2",
        "https://example.com/p?literal=&copy;2",
        "https://example.com/p?decimal=A&hex=B",
        "https://example.com/p?literal=&amp;&copy;",
    ]


def test_sitemap_page_urls_normalize_www_to_origin_host():
    assert normalize_sitemap_page_url(
        "https://www.centerstreetlending.com/blog/benefits-of-using-bridge-loans-for-real-estate-transactions",
        "https://centerstreetlending.com",
    ) == "https://centerstreetlending.com/blog/benefits-of-using-bridge-loans-for-real-estate-transactions"


def test_sitemap_page_urls_normalize_apex_to_www_origin_host():
    assert normalize_sitemap_page_url(
        "https://centerstreetlending.com/loans/fix-and-flip",
        "https://www.centerstreetlending.com",
    ) == "https://www.centerstreetlending.com/loans/fix-and-flip"


def test_sitemap_page_urls_do_not_cross_unrelated_hosts():
    assert normalize_sitemap_page_url(
        "https://example.com/loans/fix-and-flip",
        "https://centerstreetlending.com",
    ) == "https://example.com/loans/fix-and-flip"


def test_page_sitemaps_rank_before_blog_sitemaps():
    ranked = rank_child_sitemaps([
        "https://www.centerstreetlending.com/post-sitemap.xml",
        "https://www.centerstreetlending.com/page-sitemap.xml",
        "https://www.centerstreetlending.com/category-sitemap.xml",
        "https://www.centerstreetlending.com/author-sitemap.xml",
    ], "/")
    assert ranked[:2] == [
        "https://www.centerstreetlending.com/page-sitemap.xml",
        "https://www.centerstreetlending.com/category-sitemap.xml",
    ]
    assert ranked[-1] == "https://www.centerstreetlending.com/author-sitemap.xml"


def test_fetch_sitemap_locs_decodes_raw_xml_gzip(monkeypatch):
    sitemap_url = "https://example.com/product-sitemap.xml.gz"
    expected = [
        "https://example.com/products/one",
        "https://example.com/products/two",
    ]
    compressed = gzip.compress(sitemap_xml(expected).encode("utf-8"))

    async def fake_safe_get(client, url, **kwargs):
        assert url == sitemap_url
        return FakeResponse(content=compressed)

    monkeypatch.setattr(sitemap, "safe_get", fake_safe_get)
    actual = asyncio.run(fetch_sitemap_locs(object(), sitemap_url, set(), []))

    assert actual == expected


def test_fetch_sitemap_locs_applies_decoded_body_limit(monkeypatch):
    sitemap_url = "https://example.com/sitemap.xml"
    seen = {}

    async def fake_safe_get(client, url, **kwargs):
        seen["limit"] = kwargs.get("max_decoded_bytes")
        return FakeResponse(sitemap_xml(["https://example.com/page"]))

    monkeypatch.setattr(sitemap, "safe_get", fake_safe_get)
    actual = asyncio.run(fetch_sitemap_locs(object(), sitemap_url, set(), []))

    assert actual == ["https://example.com/page"]
    assert seen["limit"] == sitemap.MAX_SITEMAP_DECODED_BYTES


def test_compressed_sitemap_expansion_is_bounded_and_isolated(monkeypatch):
    sitemap_url = "https://example.com/product-sitemap.xml.gz"
    expanded = sitemap_xml(["https://example.com/" + ("x" * 2048)]).encode("utf-8")
    compressed = gzip.compress(expanded)
    diagnostics = {}

    async def fake_safe_get(client, url, **kwargs):
        assert kwargs.get("max_decoded_bytes") == 128
        return FakeResponse(content=compressed)

    monkeypatch.setattr(sitemap, "MAX_SITEMAP_DECODED_BYTES", 128)
    monkeypatch.setattr(sitemap, "safe_get", fake_safe_get)
    actual = asyncio.run(
        fetch_sitemap_locs(object(), sitemap_url, set(), [], diagnostics=diagnostics)
    )

    assert actual == []
    assert diagnostics["sitemap_failure_reason_buckets"]["sitemap_body_too_large"] == 1


def test_root_urlset_cannot_starve_later_compressed_child_families(monkeypatch):
    origin = "https://example.com"
    direct_root = f"{origin}/direct.xml"
    sitemap_index = f"{origin}/index.xml"
    product_child = f"{origin}/product-sitemap.xml.gz"
    booking_child = f"{origin}/booking-sitemap.xml"

    direct_pages = [f"{origin}/root-{index}" for index in range(12)]
    product_pages = [f"{origin}/products/product-{index}" for index in range(3)]
    booking_pages = [f"{origin}/booking/experience-{index}" for index in range(3)]
    responses = {
        f"{origin}/robots.txt": FakeResponse(
            f"Sitemap: {direct_root}\nSitemap: {sitemap_index}\n"
        ),
        direct_root: FakeResponse(sitemap_xml(direct_pages)),
        sitemap_index: FakeResponse(sitemap_xml([product_child, booking_child], index=True)),
        f"{origin}/sitemap.xml": FakeResponse(status_code=404),
        product_child: FakeResponse(
            content=gzip.compress(sitemap_xml(product_pages).encode("utf-8"))
        ),
        booking_child: FakeResponse(sitemap_xml(booking_pages)),
    }

    async def fake_safe_get(client, url, **kwargs):
        return responses.get(url, FakeResponse(status_code=404))

    monkeypatch.setattr(sitemap, "safe_get", fake_safe_get)
    urls = asyncio.run(load_sitemap_urls(object(), origin, "/", 6, []))

    assert urls == [
        direct_pages[0],
        product_pages[0],
        booking_pages[0],
        direct_pages[1],
        product_pages[1],
        booking_pages[1],
    ]
    assert any("/products/" in url for url in urls)
    assert any("/booking/" in url for url in urls)


def test_market_scoped_sitemap_excludes_other_country_language_pairs(monkeypatch):
    origin = "https://www.ikea.com"
    pages = [
        f"{origin}/fr/fr/cat/canapes-10661",
        f"{origin}/de/de/cat/sofas-fu003",
        f"{origin}/us/en/p/billy-bookcase-00263850",
    ]
    responses = {
        f"{origin}/robots.txt": FakeResponse(status_code=404),
        f"{origin}/sitemap.xml": FakeResponse(sitemap_xml(pages)),
    }

    async def fake_safe_get(client, url, **kwargs):
        return responses.get(url, FakeResponse(status_code=404))

    monkeypatch.setattr(sitemap, "safe_get", fake_safe_get)
    scope = {}
    urls = asyncio.run(load_sitemap_urls(object(), origin, "/fr/fr", 20, [], scope_evidence=scope))

    assert urls == [pages[0]]
    assert scope["sitemap_urls_excluded_outside_scope"] == 2
    assert scope["multimarket_detected"] is True
    assert set(scope["market_prefixes_detected"]) == {"/fr/fr", "/de/de", "/us/en"}


def test_global_multimarket_root_requires_an_explicit_market(monkeypatch):
    origin = "https://www.ikea.com"
    pages = [
        f"{origin}/fr/fr/cat/canapes-10661",
        f"{origin}/de/de/cat/sofas-fu003",
        f"{origin}/us/en/p/billy-bookcase-00263850",
    ]
    responses = {
        f"{origin}/robots.txt": FakeResponse(status_code=404),
        f"{origin}/sitemap.xml": FakeResponse(sitemap_xml(pages)),
    }

    async def fake_safe_get(client, url, **kwargs):
        return responses.get(url, FakeResponse(status_code=404))

    monkeypatch.setattr(sitemap, "safe_get", fake_safe_get)
    scope = {}
    urls = asyncio.run(load_sitemap_urls(object(), origin, "/", 20, [], scope_evidence=scope))

    assert urls == []
    assert scope["multimarket_detected"] is True
    assert scope["market_scope_required"] is True
    assert scope["sitemap_urls_excluded_outside_scope"] == 3
