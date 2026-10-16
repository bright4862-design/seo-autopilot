from app.content_evidence_findings import content_evidence_findings
from app.extract import extract_page
from app.stage2_reachability_provenance import (
    REACHABILITY_PROVENANCE_VERSION,
    REACHABILITY_SCOPE,
)


def _page(html: str, url: str, discovered_from: list[str], *, status: int = 200, fetch_error: str = ""):
    return extract_page(
        html,
        url,
        url,
        status,
        "text/html",
        {
            "discovered_from": discovered_from,
            "source_pages": [],
            "link_text_samples": [],
        },
        fetch_error=fetch_error,
        include_links=True,
    )


def test_content_finding_seam_projects_b11_after_retained_page_set_and_strips_private_links():
    seed = "https://example.com/"
    pricing = "https://example.com/Pricing?plan=Pro%2FAnnual"
    pages = [
        _page(
            '<html><body><nav><a href="/Pricing?plan=Pro%2FAnnual">Pricing</a></nav></body></html>',
            seed,
            ["seed"],
        ),
        _page("<html><body><main>Pricing details</main></body></html>", pricing, ["internal_link"]),
    ]

    assert pages[0]["_reachability_links"] == [
        {"href": pricing, "navigation_presence": True}
    ]
    original_urls = [page["url"] for page in pages]

    content_evidence_findings(pages)

    assert [page["url"] for page in pages] == original_urls
    assert all("_reachability_links" not in page for page in pages)
    target = pages[1]
    assert target["reachability_provenance_version"] == REACHABILITY_PROVENANCE_VERSION
    assert target["reachability_scope"] == REACHABILITY_SCOPE
    assert target["observed_internal_inlink_count"] == 1
    assert target["internal_source_pages"] == [seed]
    assert target["navigation_presence"] is True
    assert target["navigation_source_pages"] == [seed]
    assert target["crawl_depth"] == 1
    assert target["sitewide_orphan_claim"] is False
    assert target["url"] == pricing


def test_unsampled_outgoing_target_never_expands_assessed_page_set_or_invents_population():
    seed = "https://example.com/"
    retained = "https://example.com/pricing"
    outside_sample = "https://example.com/pricing/enterprise"
    pages = [
        _page(
            '<html><body><main><a href="/pricing">Pricing</a>'
            '<a href="/pricing/enterprise">Enterprise</a></main></body></html>',
            seed,
            ["seed"],
        ),
        _page("<html><body><main>Pricing</main></body></html>", retained, ["internal_link"]),
    ]

    content_evidence_findings(pages)

    assert len(pages) == 2
    assert [page["url"] for page in pages] == [seed, retained]
    assert pages[1]["observed_internal_inlink_count"] == 1
    assert pages[1]["internal_source_pages"] == [seed]
    assert outside_sample not in [page["url"] for page in pages]
    assert all("_reachability_links" not in page for page in pages)


def test_unusable_source_cannot_contribute_even_if_private_link_cache_is_malformed():
    seed = "https://example.com/"
    challenged = "https://example.com/challenge"
    pricing = "https://example.com/pricing"
    pages = [
        _page("<html><body><main>Home</main></body></html>", seed, ["seed"]),
        _page("<html><body>challenge</body></html>", challenged, ["internal_link"], status=429),
        _page("<html><body><main>Pricing</main></body></html>", pricing, ["sitemap"]),
    ]
    pages[1]["_reachability_links"] = [
        {"href": pricing, "navigation_presence": True}
    ]

    content_evidence_findings(pages)

    target = pages[2]
    assert target["observed_internal_inlink_count"] == 0
    assert target["internal_source_pages"] == []
    assert target["navigation_presence"] is None
    assert target["crawl_depth"] is None
    assert target["sitewide_orphan_claim"] is False
    assert all("_reachability_links" not in page for page in pages)
