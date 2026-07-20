"""Production-derived regressions for classifier v7 route evidence."""

from app.review import ARCHETYPE_CLASSIFIER_VERSION, build_site_fingerprint


def page(
    path: str,
    *,
    title: str = "",
    h1: str = "",
    description: str = "",
    schema_types=None,
    content_type: str = "text/html",
):
    return {
        "url": f"https://site.example{path}",
        "final_url": f"https://site.example{path}",
        "path": path,
        "status_code": 200,
        "content_type": content_type,
        "title": title,
        "h1": h1,
        "meta_description": description,
        "schema_types": schema_types or [],
    }


def fingerprint(pages):
    return build_site_fingerprint(
        {"website_url": "https://site.example", "pages_found": len(pages)},
        pages,
        "https://site.example",
    )


def publisher_pages(count: int = 40):
    return [
        page(
            f"/glossary/wordpress-term-{index}/",
            title=f"What is WordPress term {index}?",
            h1=f"WordPress term {index}",
            description="A beginner-friendly WordPress tutorial and glossary explanation.",
            schema_types=["Article"],
        )
        for index in range(count)
    ]


def test_signal_shaped_app_distribution_is_saas_without_homepage_software_words():
    pages = [
        page("/", title="Signal >> Home", h1="Speak Freely"),
        page("/download/", title="Download Signal"),
        page("/docs/", title="Documentation", h1="Technical information"),
        page("/download/android/", title="Download for Android"),
        page("/download/ios/", title="Download for iOS"),
        page("/download/windows/", title="Download for Windows"),
        page("/download/macos/", title="Download for Mac"),
        page("/download/linux/", title="Download for Linux"),
    ] + [
        page(f"/locale-{index}/download/", title="Download Signal")
        for index in range(80)
    ]

    result = fingerprint(pages)
    signals = result["classification"]["structural_signals"]

    assert ARCHETYPE_CLASSIFIER_VERSION == "archetype_classifier_v9_local_business_hospitality"
    assert result["primary_archetype"] == "saas_app_membership", result["classification"]["winning_reason"]
    assert signals["saas_homepage_identity"] is False
    assert signals["saas_app_distribution_identity"] is True
    assert len(signals["app_distribution_platforms"]) == 5


def test_wpbeginner_asset_filenames_cannot_create_saas_route_families():
    pages = [
        page(
            "/",
            title="WPBeginner - Beginner's Guide for WordPress",
            h1="Learn WordPress from the real WordPress experts",
            description="The largest WordPress resource site with tutorials for beginners.",
            schema_types=["WebSite", "Organization"],
        ),
        page("/solutions/", title="Premium WordPress Solutions", h1="Solutions"),
        page(
            "/wp-content/uploads/2024/01/signup-forms-leads.png",
            content_type="image/png",
        ),
        page(
            "/wp-content/uploads/2025/04/demo-site-design.png",
            content_type="image/png",
        ),
        page(
            "/wp-content/uploads/2025/04/demo-site-woocommerce.png",
            content_type="image/png",
        ),
    ] + publisher_pages(55)

    result = fingerprint(pages)
    signals = result["classification"]["structural_signals"]

    assert result["primary_archetype"] == "content_blog", result["classification"]["winning_reason"]
    assert signals["publisher_dominant"] is True
    assert signals["saas_dominant"] is False
    assert signals["saas_business_families"] == ["adoption"]
    assert "/signup" not in signals["saas"]
    assert "/demo" not in signals["saas"]
    assert signals["classifier_html_route_pages"] == len(pages) - 3


def test_download_and_docs_without_platform_distribution_do_not_override_publisher():
    pages = [
        page(
            "/",
            title="Open source publishing resources",
            h1="Guides and tutorials",
            description="Articles, resources, and educational guides.",
        ),
        page("/download/", title="Download the annual guide"),
        page("/docs/", title="Documentation archive"),
    ] + publisher_pages(50)

    result = fingerprint(pages)
    signals = result["classification"]["structural_signals"]

    assert result["primary_archetype"] == "content_blog", result["classification"]["winning_reason"]
    assert signals["saas_app_distribution_identity"] is False
    assert signals["app_distribution_platforms"] == []
