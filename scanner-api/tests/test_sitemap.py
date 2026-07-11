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

    async def fake_safe_get(client, url):
        assert url == sitemap_url
        return FakeResponse(content=compressed)

    monkeypatch.setattr(sitemap, "safe_get", fake_safe_get)
    actual = asyncio.run(fetch_sitemap_locs(object(), sitemap_url, set(), []))

    assert actual == expected


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

    async def fake_safe_get(client, url):
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
