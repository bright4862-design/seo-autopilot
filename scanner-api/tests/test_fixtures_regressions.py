"""Offline regression tests. Each locks a known scanner failure pattern using
synthetic fixtures. No live network, no stored third-party HTML."""
import pytest

from app.scanner import run_scan
from tests import fixtures as fx


def _paths(result):
    return [p.get("path") for p in result["pages"]]


def _rules(result):
    return [f.get("rule") for f in result["recommendations"]]


@pytest.mark.asyncio
async def test_pretto_crawls_section_and_invents_no_trust_page(mock_network):
    mock_network(fx.PRETTO_ROUTES)
    result = await run_scan(fx.PRETTO_START, path_prefix=fx.PRETTO_PREFIX, scan_mode="advanced")

    assert result["success"] is True
    # More than the seed: the section's article pages get crawled.
    assert result["pages_crawled"] >= 4
    # Off-prefix URL from the sitemap is excluded.
    assert "/blog/actualites" not in _paths(result)
    # Every crawled page stays inside the section.
    assert all((p or "/").startswith(fx.PRETTO_PREFIX) for p in _paths(result))
    # No fabricated trust-page recommendation.
    assert "missing_trust_pages" not in _rules(result)
    # But a real, evidence-based card IS produced (these pages lack a canonical).
    assert "canonical_missing" in _rules(result)


@pytest.mark.asyncio
async def test_meilleurtaux_separates_encoded_artifacts(mock_network):
    mock_network(fx.MT_ROUTES)
    result = await run_scan(fx.MT_START, path_prefix=fx.MT_PREFIX, scan_mode="advanced")

    assert result["success"] is True
    # Encoded/base64 links are captured as artifact evidence...
    assert result["suspicious_url_artifact_count"] >= 1
    assert result["suspicious_url_artifact_count"] <= 50
    # ...and never crawled or surfaced as pages.
    crawled = _paths(result)
    assert not any("aHR0" in (p or "") or "L2V0" in (p or "") for p in crawled)
    # Real section pages are crawled.
    assert "/assurance/auto" in crawled
    assert "/assurance/habitation" in crawled


@pytest.mark.asyncio
async def test_funbooker_deduplicates_pages_and_examples(mock_network):
    mock_network(fx.FB_ROUTES)
    result = await run_scan(fx.FB_START, path_prefix=fx.FB_PREFIX, scan_mode="advanced")

    assert result["success"] is True
    paths = _paths(result)
    # /activites/paris is listed in the sitemap and linked twice: crawl once.
    assert paths.count("/activites/paris") == 1
    # No duplicate page entries at all.
    assert len(paths) == len(set(paths))
    # No finding lists a duplicated affected page.
    for finding in result["recommendations"]:
        affected = finding.get("affected_pages", [])
        assert len(affected) == len(set(affected))


@pytest.mark.asyncio
async def test_centerstreet_429_yields_coverage_cards_only(mock_network):
    mock_network(fx.CS_ROUTES)
    result = await run_scan(fx.CS_START, path_prefix=fx.CS_PREFIX, scan_mode="advanced")

    assert result["success"] is True
    rules = _rules(result)
    # 429s become rate-limiting/coverage cards, not "broken page" findings.
    assert "rate_limited_page" in rules
    assert "failed_page" not in rules
    rate_findings = [f for f in result["recommendations"] if f.get("rule") == "rate_limited_page"]
    assert rate_findings, "expected at least one rate-limited coverage card"
    for finding in rate_findings:
        assert finding["priority"] == "high"
        assert "rate limiting" in finding["title"].lower()
