"""Production-derived classifier and representative-page regressions."""

from app.review import (
    build_page_pattern_findings,
    build_site_fingerprint,
    get_playbook,
    prepare_fixes,
    run_review,
    score_page_value,
)


def page(url, title="", h1="", meta="", schema=None, status=200, family="", content_type="text/html"):
    return {
        "url": url,
        "status_code": status,
        "title": title,
        "h1": h1,
        "meta_description": meta,
        "schema_types": schema or [],
        "page_template_family": family,
        "content_type": content_type,
        "indexable": status == 200,
    }


def nomadic_matt_production_mix():
    pages = [page("https://travel.example/", "Travel Better", "Travel Better", "Independent travel guides")]
    for index in range(42):
        pages.append(page(
            f"https://travel.example/travel-blogs/story-{index}/",
            f"Travel story {index}",
            "Travel story",
            "Independent travel advice",
            ["BlogPosting"],
            family="guide_article",
        ))
    for index in range(18):
        pages.append(page(
            f"https://travel.example/travel-guides/country-{index}/",
            f"Country guide {index}",
            "Travel guide",
            "Practical destination guide",
            ["Article"],
            family="guide_article",
        ))
    for index in range(6):
        pages.append(page(
            f"https://travel.example/product/guidebook-{index}/",
            f"Guidebook {index}",
            "Guidebook",
            "Buy the guidebook",
            ["Product", "Offer"],
            family="product_page",
        ))
    pages.append(page("https://travel.example/cart/", "Cart", family="route_boundary"))
    return pages


def wpbeginner_production_mix():
    pages = [page("https://publisher.example/", "WordPress tutorials", "WPBeginner", "Beginner WordPress guides")]
    for index in range(35):
        pages.append(page(
            f"https://publisher.example/glossary/term-{index}/",
            f"WordPress term {index}",
            "WordPress glossary",
            "Beginner definition and tutorial",
            ["Article"],
            family="guide_article",
        ))
    for index in range(30):
        pages.append(page(
            f"https://publisher.example/beginners-guide/tutorial-{index}/",
            f"Beginner tutorial {index}",
            "WordPress tutorial",
            "Step-by-step guide",
            ["Article"],
            family="guide_article",
        ))
    for index in range(8):
        pages.append(page(
            f"https://publisher.example/category/wp-tutorials/page-{index}/",
            f"Tutorial category {index}",
            "Tutorials",
            "WordPress tutorials",
            ["CollectionPage"],
            family="collection_page",
        ))
    for index in range(10):
        pages.append(page(
            f"https://publisher.example/solutions/vendor-{index}/",
            f"Solution review {index}",
            "Solution center",
            "Independent product review",
            ["Review"],
        ))
    pages.append(page("https://publisher.example/glossary/dashboard/", "Dashboard definition", family="route_boundary"))
    return pages


def charity_water_production_mix():
    pages = [
        page(
            "https://charity.example/",
            "Bring clean water to everyone",
            "Clean water charity",
            "Donate and support our nonprofit work",
        )
    ]
    for index in range(35):
        pages.append(page(
            f"https://charity.example/projects/{index}/",
            f"Water project {index}",
            "Water project",
            "See the impact of donor-funded clean water projects",
        ))
    for index in range(25):
        pages.append(page(
            f"https://charity.example/stories/community-{index}/",
            f"Community story {index}",
            "A clean water story",
            "Stories from communities and supporters",
            ["Article"],
            family="guide_article",
        ))
    for index in range(15):
        pages.append(page(
            f"https://charity.example/fundraise/campaign-{index}/",
            f"Fundraising campaign {index}",
            "Fundraise for clean water",
            "Start a fundraiser or donate",
        ))
    pages.extend([
        page("https://charity.example/donate/", "Donate", "Give clean water", "Make a donation", family="conversion"),
        page("https://charity.example/account/login", "Account login", family="route_boundary"),
    ])
    return pages


def test_nomadic_matt_mix_stays_publisher_despite_small_shop():
    fingerprint = build_site_fingerprint({}, nomadic_matt_production_mix(), "https://travel.example")
    assert fingerprint["primary_archetype"] == "content_blog", fingerprint["classification"]["winning_reason"]
    assert fingerprint["classification"]["structural_signals"]["retail_dominant"] is False


def test_wpbeginner_mix_stays_knowledge_publisher_despite_solution_routes():
    fingerprint = build_site_fingerprint({}, wpbeginner_production_mix(), "https://publisher.example")
    assert fingerprint["primary_archetype"] == "content_blog", fingerprint["classification"]["winning_reason"]
    assert fingerprint["classification"]["structural_signals"]["saas_dominant"] is False


def test_charity_water_mix_uses_nonprofit_playbook():
    fingerprint = build_site_fingerprint({}, charity_water_production_mix(), "https://charity.example")
    assert fingerprint["primary_archetype"] == "nonprofit_fundraising", fingerprint["classification"]["winning_reason"]
    assert fingerprint["classification"]["structural_signals"]["nonprofit_dominant"] is True


def test_representative_page_demotes_auth_archive_and_asset_urls():
    pages = [
        page("https://publisher.example/account/login", "Log in", family="route_boundary"),
        page("https://publisher.example/blog/important-guide", "Important guide", "Guide", "Helpful guide", ["Article"], family="guide_article"),
        page("https://publisher.example/wp-content/uploads/image.png", content_type="image/png"),
    ]
    fingerprint = build_site_fingerprint({}, pages + [
        page("https://publisher.example/blog/second-guide", "Second guide", "Guide", "Helpful"),
    ], "https://publisher.example")
    fixes = prepare_fixes(
        [{
            "rule": "image_alt_text",
            "category": "image_alt_text",
            "issue_title": "Add image descriptions",
            "affected_pages": [
                "/account/login",
                "/wp-content/uploads/image.png",
                "/blog/important-guide",
            ],
            "page_template_family": "mixed",
        }],
        fingerprint,
        {},
        get_playbook(fingerprint["primary_archetype"]),
        pages,
    )
    assert fixes[0]["page_url"] == "/blog/important-guide"
    assert fixes[0]["affected_pages"][0] == "/blog/important-guide"
    assert "/account/login" in fixes[0]["supporting_evidence_pages"]
    assert fixes[0]["representative_page_version"] == "business_representative_page_v1"


def test_non_html_assets_do_not_generate_template_findings():
    findings = build_page_pattern_findings([
        page("https://example.com/wp-content/uploads/photo.png", content_type="image/png"),
        page("https://example.com/guide", "Guide", "", "", family="guide_article"),
    ])
    urls = [url for finding in findings for url in finding.get("affected_pages", [])]
    assert not any(url.endswith(".png") for url in urls)
    assert "/guide" in urls


def test_route_boundary_is_not_scored_as_business_page():
    pages = wpbeginner_production_mix()
    fingerprint = build_site_fingerprint({}, pages, "https://publisher.example")
    value = score_page_value(
        "/account/login",
        fingerprint,
        {},
        get_playbook(fingerprint["primary_archetype"]),
    )
    assert value["classification"] == "internal_or_auth_route"
    assert value["score"] < 70


def test_incidental_rate_limit_is_verification_evidence_not_provisional_score():
    pages = [
        page(f"https://publisher.example/blog/article-{index}", f"Article {index}", "Article", "Guide", ["Article"])
        for index in range(20)
    ]
    pages.append(page("https://publisher.example/blog/rate-limited", "Too Many Requests", status=429))
    result = run_review({
        "website_url": "https://publisher.example",
        "pages_found": len(pages),
        "pages_crawled": len(pages),
        "crawled_pages": pages,
    })
    assert result["scan_status"] == "complete"
    assert result["score_is_provisional"] is False
    assert result["access_evidence_state"] == "incidental_access_limited"
    rate_fix = next(fix for fix in result["fixes"] if fix["rule"] == "rate_limited_page")
    assert rate_fix["verification_state"] == "needs_verification"


def test_material_rate_limit_share_remains_provisional():
    pages = [
        page(f"https://publisher.example/blog/article-{index}", f"Article {index}", "Article", "Guide", ["Article"])
        for index in range(20)
    ]
    pages.extend(
        page(f"https://publisher.example/blog/rate-limited-{index}", "Too Many Requests", status=429)
        for index in range(5)
    )
    result = run_review({
        "website_url": "https://publisher.example",
        "pages_found": len(pages),
        "pages_crawled": len(pages),
        "crawled_pages": pages,
    })
    assert result["scan_status"] == "complete_with_access_limitations"
    assert result["score_is_provisional"] is True
    assert result["access_evidence_state"] == "partial_access_limited"
