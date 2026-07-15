"""Regression coverage for orphan/sitemap-only asset URL filtering."""

from app.review import (
    ORPHAN_ASSET_EVIDENCE_VERSION,
    filter_orphan_asset_evidence,
    get_playbook,
    select_representative_page,
)


def page(url: str, content_type: str = "text/html") -> dict:
    return {
        "url": f"https://www.nomadicmatt.com{url}",
        "final_url": f"https://www.nomadicmatt.com{url}",
        "status_code": 200,
        "content_type": content_type,
        "title": "Useful page" if content_type == "text/html" else "",
    }


def orphan_fix(urls, *, rule="sitemap_only_page", title="Sitemap-only/orphan pages"):
    return {
        "rule": rule,
        "issue_title": title,
        "page_url": urls[0],
        "representative_page_url": urls[0],
        "affected_pages": list(urls),
        "source_pages": list(urls),
        "supporting_evidence_pages": list(urls),
    }


def test_asset_only_orphan_group_is_suppressed():
    urls = [
        "/wp-content/themes/nomadicmatt/images/blog_divider.png",
        "/wp-content/uploads/hero.jpg",
        "/wp-content/uploads/photo.jpeg",
    ]
    assets = [page(url, "image/png") for url in urls]
    assert filter_orphan_asset_evidence(orphan_fix(urls), assets) is None


def test_mixed_orphan_group_retains_only_html_pages():
    urls = ["/travel-planning-services", "/wp-content/uploads/photo.jpg", "/about"]
    filtered = filter_orphan_asset_evidence(
        orphan_fix(urls),
        [page("/travel-planning-services"), page("/about"), page("/wp-content/uploads/photo.jpg", "image/jpeg")],
    )
    assert filtered is not None
    assert filtered["affected_pages"] == ["/travel-planning-services", "/about"]
    assert filtered["page_url"] == "/travel-planning-services"
    assert filtered["source_pages"] == ["/travel-planning-services", "/about"]
    assert filtered["asset_urls_excluded"] == 1
    assert filtered["orphan_asset_evidence_version"] == ORPHAN_ASSET_EVIDENCE_VERSION


def test_representative_target_never_selects_an_asset_after_filtering():
    urls = ["/wp-content/uploads/photo.png", "/product/guide-to-points-and-miles"]
    pages = [page(urls[0], "image/png"), page(urls[1])]
    filtered = filter_orphan_asset_evidence(orphan_fix(urls), pages)
    assert filtered is not None
    selected = select_representative_page(filtered, pages, {}, get_playbook("content_blog"))
    assert selected["page_url"] == "/product/guide-to-points-and-miles"
    assert selected["representative_page_url"] == "/product/guide-to-points-and-miles"
    assert not selected["page_url"].endswith(".png")


def test_uppercase_extensions_and_query_strings_are_filtered():
    urls = ["/wp-content/uploads/HERO.JPG?ver=4", "/wp-content/uploads/ICON.PNG#asset", "/contact"]
    filtered = filter_orphan_asset_evidence(orphan_fix(urls), [page("/contact")])
    assert filtered is not None
    assert filtered["affected_pages"] == ["/contact"]
    assert filtered["asset_urls_excluded"] == 2


def test_genuine_orphan_html_page_is_retained():
    fix = orphan_fix(["/forgotten-travel-guide"], rule="orphan_page")
    filtered = filter_orphan_asset_evidence(fix, [page("/forgotten-travel-guide")])
    assert filtered is not None
    assert filtered["affected_pages"] == ["/forgotten-travel-guide"]
    assert filtered["page_url"] == "/forgotten-travel-guide"


def test_nomadic_matt_wp_content_image_group_is_suppressed_by_title_hint():
    urls = [
        "/wp-content/themes/nomadicmatt/images/blog_divider_735x40_@2x.png",
        "/wp-content/uploads/2024/guide-cover.jpg",
        "/wp-content/uploads/2025/map.jpeg",
    ]
    fix = orphan_fix(
        urls,
        rule="indexability_review",
        title="Sitemap-only/orphan URLs need internal links",
    )
    assets = [page(url, "image/jpeg") for url in urls]
    assert filter_orphan_asset_evidence(fix, assets) is None
