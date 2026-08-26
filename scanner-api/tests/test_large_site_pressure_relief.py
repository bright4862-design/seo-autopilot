import pytest

import app.extract as extract
import app.scanner as scanner
from app.sitemap import parse_sitemap_locs
from tests import fixtures as fx


def test_sitemap_loc_parser_preserves_large_inventory_order_and_entities():
    urls = [f"https://example.com/catalog/item-{index}?a=1&b=2" for index in range(5000)]
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(
            f"<url><loc>{url.replace('&', '&amp;')}</loc></url>"
            for url in urls
        )
        + "</urlset>"
    )

    parsed = parse_sitemap_locs(xml)

    assert parsed == urls
    assert len(parsed) == 5000


def test_sitemap_loc_parser_accepts_namespace_prefix_and_cdata():
    xml = (
        "<sm:urlset xmlns:sm='http://www.sitemaps.org/schemas/sitemap/0.9'>"
        "<sm:url><sm:loc><![CDATA[https://example.com/a?x=1&y=2]]></sm:loc></sm:url>"
        "</sm:urlset>"
    )
    assert parse_sitemap_locs(xml) == ["https://example.com/a?x=1&y=2"]


def test_extract_page_can_collect_links_from_the_same_parse(monkeypatch):
    real = extract.BeautifulSoup
    parse_calls = 0

    def counting_parser(*args, **kwargs):
        nonlocal parse_calls
        parse_calls += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(extract, "BeautifulSoup", counting_parser)
    html = (
        "<html><head><title>Hub</title></head><body>"
        "<h1>Hub</h1>"
        "<a href='/one'>One</a><a href='/two'>Two</a>"
        "</body></html>"
    )
    page = extract.extract_page(
        html,
        "https://example.com/",
        "https://example.com/",
        200,
        "text/html",
        {"discovered_from": ["seed"]},
        include_links=True,
    )

    assert parse_calls == 1
    assert [item["href"] for item in page["_links"]] == [
        "https://example.com/one",
        "https://example.com/two",
    ]


@pytest.mark.asyncio
async def test_scan_does_not_need_second_link_parse(mock_network, monkeypatch):
    origin = "https://single-parse.example"
    routes = {
        f"{origin}/sitemap.xml": fx._xml(fx._sitemap([
            f"{origin}/",
            f"{origin}/one",
            f"{origin}/two",
        ])),
        f"{origin}/": fx._html(fx._page("Hub", links=["/one", "/two"])),
        f"{origin}/one": fx._html(fx._page("One")),
        f"{origin}/two": fx._html(fx._page("Two")),
    }
    mock_network(routes)

    def second_parse_must_not_run(*args, **kwargs):
        raise AssertionError("scanner worker reparsed raw HTML for link extraction")

    # Kept with raising=False so this regression remains valid if the now-unused
    # compatibility import is removed in a later cleanup.
    monkeypatch.setattr(scanner, "extract_links", second_parse_must_not_run, raising=False)

    result = await scanner.run_scan(
        f"{origin}/",
        scan_mode="advanced",
        concurrency=4,
    )

    assert result["pages_crawled"] >= 3
    assert {page["path"] for page in result["pages"]} >= {"/", "/one", "/two"}
    assert all("_html" not in page and "_links" not in page for page in result["pages"])


@pytest.mark.asyncio
async def test_oversized_ordinary_html_fails_only_that_page_without_prefix_evidence(
    mock_network,
    monkeypatch,
):
    origin = "https://oversized.example"
    marker = "SHOULD-NOT-BECOME-SEO-EVIDENCE"
    oversized = (
        f"<html><head><title>{marker}</title></head>"
        f"<body><h1>{marker}</h1>"
        + ("x" * 4096)
        + "</body></html>"
    )
    routes = {
        f"{origin}/sitemap.xml": fx._xml(fx._sitemap([
            f"{origin}/",
            f"{origin}/oversized",
            f"{origin}/healthy",
        ])),
        f"{origin}/": fx._html(fx._page("Home", links=["/oversized", "/healthy"])),
        f"{origin}/oversized": fx._html(oversized),
        f"{origin}/healthy": fx._html(fx._page("Healthy")),
    }
    mock_network(routes)
    monkeypatch.setattr(scanner, "MAX_DECODED_RESPONSE_BYTES", 512)

    result = await scanner.run_scan(
        f"{origin}/",
        scan_mode="advanced",
        concurrency=2,
    )

    assert result["success"] is True
    healthy = next(page for page in result["pages"] if page["path"] == "/healthy")
    oversized_page = next(page for page in result["pages"] if page["path"] == "/oversized")
    assert healthy["status_code"] == 200
    assert oversized_page["status_code"] == 0
    assert "decoded_response_body_exceeded_512_bytes" in str(
        oversized_page.get("fetch_error") or ""
    )
    assert not oversized_page.get("title")
    assert int(oversized_page.get("h1_count") or 0) == 0
    assert all(marker not in str(finding) for finding in result["raw_findings"])
    assert all(marker not in str(finding) for finding in result["grouped_findings"])
