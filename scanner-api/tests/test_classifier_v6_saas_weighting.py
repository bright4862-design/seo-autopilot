"""Focused regression matrix for SaaS sites with large content libraries."""

from app.review import ARCHETYPE_CLASSIFIER_VERSION, build_site_fingerprint


def page(path, *, title="", description="", h1="", schema_types=None):
    return {
        "url": f"https://site.example.com{path}",
        "final_url": f"https://site.example.com{path}",
        "path": path,
        "title": title or path.strip("/").replace("-", " ").title() or "Home",
        "h1": h1 or title,
        "meta_description": description,
        "schema_types": schema_types or [],
        "status_code": 200,
    }


def content_pages(prefix, count, topic):
    return [
        page(
            f"/{prefix}/{topic}-{index}",
            title=f"{topic.title()} guide {index}",
            description=f"Articles, resources, tutorials and insights about {topic}.",
            schema_types=["Article"],
        )
        for index in range(count)
    ]


def classify(pages):
    result = build_site_fingerprint(
        {"website_url": "https://site.example.com", "pages_found": len(pages), "pages_crawled": len(pages)},
        pages,
        "https://site.example.com",
    )
    assert result["classification"]["classifier_version"] == ARCHETYPE_CLASSIFIER_VERSION
    assert result["classification"]["state"] == "classified"
    return result


def assert_saas(pages):
    result = classify(pages)
    assert result["primary_archetype"] == "saas_app_membership", result["classification"]["winning_reason"]
    assert result["classification"]["structural_signals"]["saas_dominant"] is True
    return result


def assert_publisher(pages):
    result = classify(pages)
    assert result["primary_archetype"] == "content_blog", result["classification"]["winning_reason"]
    assert result["classification"]["structural_signals"]["saas_dominant"] is False
    return result


def test_signal_shaped_app_beats_large_content_library():
    result = assert_saas([
        page(
            "/",
            title="Private messenger app",
            h1="Speak freely",
            description="Fast, simple and secure messaging app for private conversations.",
        ),
        page("/download", title="Download the app"),
        page("/apps/android", title="Android app"),
        page("/apps/desktop", title="Desktop app"),
    ] + content_pages("blog", 80, "privacy"))
    assert "product" in result["classification"]["structural_signals"]["saas_business_families"]


def test_buffer_shaped_platform_beats_large_resource_library():
    assert_saas([
        page(
            "/",
            title="Social media management platform",
            h1="Grow your audience",
            description="Social media management software for publishing, analytics and engagement.",
        ),
        page("/features/publishing"),
        page("/pricing"),
        page("/free-trial"),
    ] + content_pages("resources", 100, "social-media"))


def test_webflow_shaped_builder_beats_large_content_library():
    assert_saas([
        page(
            "/",
            title="Website builder and visual development platform",
            h1="Build extraordinary websites",
            description="A visual development and web experience platform for professional teams.",
        ),
        page("/features"),
        page("/enterprise"),
        page("/contact-sales"),
    ] + content_pages("resources", 100, "web-design"))


def test_nomadic_matt_shaped_publisher_with_small_shop_stays_publisher():
    assert_publisher([
        page(
            "/",
            title="Travel better, cheaper, longer",
            h1="Travel guides from an independent author",
            description="Destination guides, practical travel advice and stories.",
        ),
        page("/product/travel-book", title="Travel book"),
        page("/checkout", title="Checkout"),
    ] + content_pages("blog", 80, "travel"))


def test_wpbeginner_shaped_knowledge_publisher_stays_publisher():
    assert_publisher([
        page(
            "/",
            title="WordPress tutorials for beginners",
            h1="Beginner-friendly WordPress guides",
            description="Free tutorials, glossary articles and practical WordPress resources.",
        ),
        page("/solutions/hosting"),
        page("/glossary/dashboard"),
    ] + content_pages("beginners-guide", 80, "wordpress"))


def test_existing_saas_controls_remain_saas():
    controls = [
        [
            page("/", title="Project management software", description="A platform for teams."),
            page("/features"), page("/pricing"), page("/login"),
        ],
        [
            page("/", title="Issue tracking software", description="A product platform for modern teams."),
            page("/features"), page("/integrations"), page("/signup"),
        ],
        [
            page("/", title="Customer support platform", description="Helpdesk software for support teams."),
            page("/features"), page("/pricing"), page("/demo"),
        ],
        [
            page("/", title="Commerce platform", description="Software to build and run an online store."),
            page("/features/checkout"), page("/pricing"), page("/signup"),
        ],
    ]
    for pages in controls:
        assert_saas(pages + content_pages("blog", 50, "productivity"))
