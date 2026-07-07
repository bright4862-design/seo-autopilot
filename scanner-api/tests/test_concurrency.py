"""Parity tests: the concurrent worker pool must produce the same results as a
single-worker (sequential) crawl on every synthetic fixture. This is what makes
the concurrency change safe to ship."""
import pytest

from app.scanner import run_scan
from tests import fixtures as fx

CASES = [
    ("pretto", fx.PRETTO_ROUTES, fx.PRETTO_START, fx.PRETTO_PREFIX),
    ("meilleurtaux", fx.MT_ROUTES, fx.MT_START, fx.MT_PREFIX),
    ("funbooker", fx.FB_ROUTES, fx.FB_START, fx.FB_PREFIX),
    ("centerstreet", fx.CS_ROUTES, fx.CS_START, fx.CS_PREFIX),
]


@pytest.mark.parametrize("name,routes,start,prefix", CASES)
@pytest.mark.asyncio
async def test_sequential_and_concurrent_parity(mock_network, name, routes, start, prefix):
    mock_network(routes)

    sequential = await run_scan(start, path_prefix=prefix, scan_mode="advanced", concurrency=1)
    concurrent = await run_scan(start, path_prefix=prefix, scan_mode="advanced", concurrency=8)

    seq_paths = sorted(p["path"] for p in sequential["pages"])
    con_paths = sorted(p["path"] for p in concurrent["pages"])
    assert seq_paths == con_paths, f"{name}: crawled path set differs"

    seq_rules = sorted(f["rule"] for f in sequential["recommendations"])
    con_rules = sorted(f["rule"] for f in concurrent["recommendations"])
    assert seq_rules == con_rules, f"{name}: recommendation rules differ"

    assert sequential["suspicious_url_artifact_count"] == concurrent["suspicious_url_artifact_count"]
    assert concurrent["suspicious_url_artifact_count"] <= 50


@pytest.mark.asyncio
async def test_concurrency_respects_max_pages(mock_network, monkeypatch):
    # Build a wide fixture: one hub linking to many same-prefix pages.
    origin = "https://wide.example"
    links = [f"/section/p{i}" for i in range(40)]
    routes = {
        f"{origin}/sitemap.xml": fx._xml(fx._sitemap([f"{origin}/section"] + [f"{origin}{p}" for p in links])),
        f"{origin}/section": fx._html(fx._page("Hub", links=links)),
    }
    for p in links:
        routes[f"{origin}{p}"] = fx._html(fx._page(f"Page {p}"))
    mock_network(routes)

    # Force a tiny budget via a patched budget table.
    monkeypatch.setitem(__import__("app.scanner", fromlist=["SCAN_BUDGETS"]).SCAN_BUDGETS, "advanced", {"max_pages": 10, "timeout": 30})

    result = await run_scan(f"{origin}/section", path_prefix="/section", scan_mode="advanced", concurrency=8)
    # 8 workers must not overshoot the page budget.
    assert result["pages_crawled"] <= 10
