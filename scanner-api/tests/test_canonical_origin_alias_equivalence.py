import pytest

from app.canonical_validation import validate_canonical_targets
from app.extract import extract_page
from app.robots_policy import RobotsPolicy
from app.scanner import build_findings


DISCOVERY = {"discovered_from": ["sitemap"], "source_pages": ["/sitemap.xml"], "link_text_samples": []}


def _page(url: str, *, canonical: str = "", robots: str = ""):
    canonical_tag = f'<link rel="canonical" href="{canonical}">' if canonical else ""
    robots_tag = f'<meta name="robots" content="{robots}">' if robots else ""
    return extract_page(
        f"<html><head><title>Page</title>{canonical_tag}{robots_tag}</head><body><h1>Page</h1></body></html>",
        url,
        url,
        200,
        "text/html",
        DISCOVERY,
    )


class FakeClient:
    def __init__(self, responses=None):
        self.responses = responses or {}
        self.calls = []

    async def get(self, url):
        self.calls.append(url)
        return self.responses[url]


@pytest.mark.asyncio
async def test_apex_to_www_canonical_is_valid_origin_alias_not_cross_domain():
    source = _page(
        "https://hartzlerdairy.com/chocolate-milk",
        canonical="https://www.hartzlerdairy.com/chocolate-milk",
    )
    target = _page(
        "https://www.hartzlerdairy.com/chocolate-milk",
        canonical="https://www.hartzlerdairy.com/chocolate-milk",
    )
    client = FakeClient()

    summary = await validate_canonical_targets(
        client,
        [source, target],
        RobotsPolicy("https://hartzlerdairy.com/robots.txt", "missing", 404),
    )

    assert client.calls == []
    assert source["canonical_target_state"] == "valid"
    assert source["canonical_origin_alias"] is True
    assert source["canonical_origin_alias_source_url"] == "https://hartzlerdairy.com/chocolate-milk"
    assert source["canonical_origin_alias_target_url"] == "https://www.hartzlerdairy.com/chocolate-milk"
    assert summary["origin_alias_declarations"] == 1
    assert not any(item["rule"] == "canonical_cross_domain" for item in build_findings([source, target]))


@pytest.mark.asyncio
async def test_origin_alias_does_not_suppress_noindex_target_warning():
    source = _page(
        "https://example.com/source",
        canonical="https://www.example.com/preferred",
    )
    target = _page(
        "https://www.example.com/preferred",
        canonical="https://www.example.com/preferred",
        robots="noindex",
    )

    await validate_canonical_targets(
        FakeClient(),
        [source, target],
        RobotsPolicy("https://example.com/robots.txt", "missing", 404),
    )

    assert source["canonical_origin_alias"] is True
    assert source["canonical_target_state"] == "target_noindexed"
    assert any(item["rule"] == "canonical_target_noindex" for item in build_findings([source, target]))


@pytest.mark.asyncio
async def test_http_to_https_www_change_is_not_treated_as_origin_alias():
    source = _page(
        "http://example.com/source",
        canonical="https://www.example.com/source",
    )
    client = FakeClient()

    await validate_canonical_targets(
        client,
        [source],
        RobotsPolicy("http://example.com/robots.txt", "missing", 404),
    )

    assert client.calls == []
    assert source.get("canonical_origin_alias") is not True
    assert source["canonical_target_state"] == "cross_domain_needs_verification"
    assert any(item["rule"] == "canonical_cross_domain" for item in build_findings([source]))
