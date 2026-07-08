"""Locks Deno-parity behaviors on the Python scanner: crawl_policy provenance,
template-level grouping, clean group wording, and preserved discovery evidence."""
import pytest

from app.scanner import run_scan
from tests import fixtures as fx


@pytest.mark.asyncio
async def test_crawl_policy_provenance_present(mock_network):
    mock_network(fx.PRETTO_ROUTES)
    result = await run_scan(fx.PRETTO_START, path_prefix=fx.PRETTO_PREFIX, scan_mode="advanced")

    assert "crawl_policy" in result
    assert result["crawl_policy_source"] == result["crawl_policy"]["source"]
    tas = result["technical_audit_summary"]
    assert "crawl_policy" in tas and "crawl_policy_source" in tas
    assert "duplicate_casing_routes" in tas


@pytest.mark.asyncio
async def test_repeated_template_issues_are_grouped(mock_network):
    # Pretto: 4 in-section pages, each missing meta + canonical -> should collapse
    # into single template cards, not 8 per-page findings.
    mock_network(fx.PRETTO_ROUTES)
    result = await run_scan(fx.PRETTO_START, path_prefix=fx.PRETTO_PREFIX, scan_mode="advanced")

    grouped = [f for f in result["recommendations"] if f.get("page_count")]
    rules = {g["rule"] for g in grouped}
    assert "canonical_missing" in rules
    assert "missing_meta_description" in rules

    for g in grouped:
        assert g["page_count"] >= 3
        assert g["affected_pages"] == list(dict.fromkeys(g["affected_pages"]))  # deduped
        # Clean wording: no doubled noun like "page pages".
        assert "page pages" not in g["title"].lower()
        assert g["page_url"] == ""  # group card is not tied to a single page


@pytest.mark.asyncio
async def test_single_page_issue_not_grouped(mock_network):
    # Center Street: one 200 page + two 429s. The single non-failure issues must
    # NOT be inflated into a "repeated template" card (< 3 affected).
    mock_network(fx.CS_ROUTES)
    result = await run_scan(fx.CS_START, path_prefix=fx.CS_PREFIX, scan_mode="advanced")

    for f in result["recommendations"]:
        if f.get("rule") in {"missing_meta_description", "canonical_missing"} and f.get("page_count"):
            assert f["page_count"] >= 3, "single/low-count issue wrongly grouped as template"


@pytest.mark.asyncio
async def test_duplicate_casing_becomes_actionable_finding(mock_network):
    origin = "https://casing.example"
    routes = {
        f"{origin}/sitemap.xml": fx._xml(fx._sitemap([
            f"{origin}/account", f"{origin}/Account", f"{origin}/about",
        ])),
        f"{origin}/account": fx._html(fx._page("Account", meta="a", canonical=f"{origin}/account")),
        f"{origin}/Account": fx._html(fx._page("Account caps", meta="a", canonical=f"{origin}/Account")),
        f"{origin}/about": fx._html(fx._page("About", meta="a", canonical=f"{origin}/about")),
    }
    mock_network(routes)
    result = await run_scan(f"{origin}/", path_prefix="/", scan_mode="advanced")

    casing = [f for f in result["recommendations"] if f.get("rule") == "duplicate_route_casing"]
    assert casing, "duplicate casing must surface as an actionable finding, not just summary data"
    f = casing[0]
    assert f["priority"] == "high"                 # /account is a high-risk app route
    assert set(f["affected_pages"]) == {"/account", "/Account"}
    assert f["requires_developer"] is True
    assert f["who_can_do_this"] == "your_web_person"
    # Contract-consistent (routed through create_finding):
    assert f["status"] == "needs_developer"
    assert "customer_category" in f
