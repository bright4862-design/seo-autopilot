import pytest

from app.scanner import run_scan
from tests import fixtures as fx


@pytest.mark.asyncio
async def test_apex_start_redirect_rebases_crawl_to_verified_www_origin(mock_network):
    apex = "https://meilleurtaux-regression.example"
    www = "https://www.meilleurtaux-regression.example"
    routes = {
        f"{apex}/robots.txt": {"body": "", "status": 404, "content_type": "text/plain"},
        f"{apex}/sitemap.xml": {"body": "", "status": 404, "content_type": "text/plain"},
        f"{apex}/": {
            "body": "",
            "status": 301,
            "content_type": "text/html",
            "headers": {"location": f"{www}/"},
        },
        f"{www}/robots.txt": fx._text(f"User-agent: *\nSitemap: {www}/sitemap.xml\n"),
        f"{www}/sitemap.xml": fx._xml(fx._sitemap([
            f"{www}/",
            f"{www}/credit-immobilier/",
            f"{www}/assurance-de-pret/",
            f"{www}/credit-consommation/",
        ])),
        f"{www}/": fx._html(fx._page(
            "Meilleurtaux",
            links=["/credit-immobilier/", "/assurance-de-pret/", "/credit-consommation/"],
        )),
        f"{www}/credit-immobilier/": fx._html(fx._page("Crédit immobilier")),
        f"{www}/assurance-de-pret/": fx._html(fx._page("Assurance de prêt")),
        f"{www}/credit-consommation/": fx._html(fx._page("Crédit consommation")),
    }
    mock_network(routes)

    result = await run_scan(apex, scan_mode="advanced", concurrency=2)

    assert result["pages_found"] >= 4
    assert result["pages_crawled"] == 4
    assert result["crawl_timing"]["sitemap_urls_discovered"] == 4
    assert result["sampling_evidence"]["crawl_scope"]["effective_origin"] == www
    assert result["sampling_evidence"]["crawl_scope"]["origin_scope_source"] == "verified_www_alias_redirect"
