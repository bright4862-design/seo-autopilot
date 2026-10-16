import httpx
import pytest

import app.sitemap as sitemap


ORIGIN = "https://example.com"
ROOT = ORIGIN + "/declared.xml"
CHILD = ORIGIN + "/products.xml"
DEFAULT = ORIGIN + "/sitemap.xml"


def response(status: int, body: str = "") -> httpx.Response:
    return httpx.Response(status, text=body)


@pytest.mark.asyncio
async def test_discovery_retains_exact_target_and_child_source_provenance(monkeypatch):
    responses = {
        ORIGIN + "/robots.txt": response(200, f"User-agent: *\nSitemap: {ROOT}\n"),
        ROOT: response(
            200,
            f"""<sitemapindex>
                <sitemap><loc>{CHILD}</loc></sitemap>
                <url><loc>{ORIGIN}/root-page</loc></url>
                <url><loc>{ORIGIN}/shared</loc></url>
            </sitemapindex>""",
        ),
        DEFAULT: response(404, "missing"),
        CHILD: response(
            200,
            f"""<urlset>
                <url><loc>{ORIGIN}/child-page</loc></url>
                <url><loc>{ORIGIN}/shared</loc></url>
            </urlset>""",
        ),
    }

    async def fake_get(_client, url, _deadline, *, pacer=None):
        return responses[url]

    monkeypatch.setattr(sitemap, "_safe_get_before_deadline", fake_get)
    diagnostics = {}
    urls = await sitemap.load_sitemap_urls(
        object(),
        ORIGIN,
        "/",
        20,
        [],
        diagnostics=diagnostics,
    )

    assert urls == [
        ORIGIN + "/root-page",
        ORIGIN + "/child-page",
        ORIGIN + "/shared",
    ]
    target_rows = diagnostics["sitemap_target_sources"]
    assert {
        (row["url"], row["sitemap_url"], row["source_kind"])
        for row in target_rows
    } == {
        (ORIGIN + "/root-page", ROOT, "robots_declared"),
        (ORIGIN + "/shared", ROOT, "robots_declared"),
        (ORIGIN + "/child-page", CHILD, "child_discovered"),
        (ORIGIN + "/shared", CHILD, "child_discovered"),
    }

    source_rows = {row["url"]: row for row in diagnostics["sitemap_sources"]}
    assert source_rows[ROOT]["source"] == "robots_declared"
    assert source_rows[ROOT]["outcome"] == "urls"
    assert source_rows[CHILD]["source"] == "child_discovered"
    assert source_rows[CHILD]["outcome"] == "urls"
    assert source_rows[DEFAULT]["outcome"] == "failed"
    assert source_rows[DEFAULT]["reason"] == "http_404"
    assert diagnostics["sitemap_source_failures"][DEFAULT] == "http_404"


@pytest.mark.asyncio
async def test_child_failure_reason_is_attached_to_exact_child_source(monkeypatch):
    responses = {
        ORIGIN + "/robots.txt": response(200, f"Sitemap: {ROOT}\n"),
        ROOT: response(200, f"<sitemapindex><sitemap><loc>{CHILD}</loc></sitemap></sitemapindex>"),
        DEFAULT: response(404, "missing"),
        CHILD: response(429, "slow down"),
    }

    async def fake_get(_client, url, _deadline, *, pacer=None):
        return responses[url]

    monkeypatch.setattr(sitemap, "_safe_get_before_deadline", fake_get)
    diagnostics = {}
    urls = await sitemap.load_sitemap_urls(
        object(),
        ORIGIN,
        "/",
        20,
        [],
        diagnostics=diagnostics,
    )

    assert urls == []
    source_rows = {row["url"]: row for row in diagnostics["sitemap_sources"]}
    assert source_rows[CHILD]["outcome"] == "failed"
    assert source_rows[CHILD]["reason"] == "http_429"
    assert diagnostics["sitemap_source_failures"][CHILD] == "http_429"
    assert diagnostics["sitemap_failure_reason_buckets"]["http_429"] == 1


@pytest.mark.asyncio
async def test_target_provenance_is_filtered_to_final_bounded_output(monkeypatch):
    pages = "".join(
        f"<url><loc>{ORIGIN}/page-{index}</loc></url>"
        for index in range(5)
    )
    responses = {
        ORIGIN + "/robots.txt": response(200, f"Sitemap: {ROOT}\n"),
        ROOT: response(200, f"<urlset>{pages}</urlset>"),
        DEFAULT: response(404, "missing"),
    }

    async def fake_get(_client, url, _deadline, *, pacer=None):
        return responses[url]

    monkeypatch.setattr(sitemap, "_safe_get_before_deadline", fake_get)
    diagnostics = {}
    urls = await sitemap.load_sitemap_urls(
        object(),
        ORIGIN,
        "/",
        2,
        [],
        diagnostics=diagnostics,
    )

    assert urls == [ORIGIN + "/page-0", ORIGIN + "/page-1"]
    assert [row["url"] for row in diagnostics["sitemap_target_sources"]] == urls
