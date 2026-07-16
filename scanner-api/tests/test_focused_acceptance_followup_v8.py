"""Production-shaped regressions from the focused representative-evidence acceptance."""

from app.review import build_site_fingerprint, get_playbook, prepare_fixes


def page(url, title="", h1="", meta="", schema=None, status=200, family="standard", content_type="text/html"):
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


def test_platform_product_routes_keep_docs_heavy_infrastructure_site_saas():
    pages = [page("https://platform.example/", "Financial infrastructure for the internet", "Build financial products", "APIs and infrastructure for businesses")]
    for index in range(45):
        pages.append(page(
            f"https://platform.example/docs/guide-{index}",
            f"Developer guide {index}",
            "Developer documentation",
            "API integration guide",
            ["TechArticle"],
            family="guide_article",
        ))
    for route in ("payments", "billing", "connect", "radar", "terminal", "issuing"):
        pages.append(page(
            f"https://platform.example/{route}",
            route.title(),
            f"{route.title()} platform",
            "Build and operate financial products",
            family="product_page",
        ))
    pages.extend([
        page("https://platform.example/docs/api", "API reference", "Developer API", family="guide_article"),
        page("https://platform.example/developers", "Developers", "Developer platform", family="guide_article"),
    ])
    fingerprint = build_site_fingerprint(
        {"pages_found": len(pages), "pages_crawled": len(pages)},
        pages,
        "https://platform.example",
    )
    assert fingerprint["primary_archetype"] == "saas_app_membership", fingerprint["classification"]["winning_reason"]
    signals = fingerprint["classification"]["structural_signals"]
    assert signals["saas_platform_infrastructure_identity"] is True
    assert len(signals["platform_product_routes"]) >= 3


def test_markdown_failed_page_is_removed_from_page_level_broken_evidence():
    pages = [
        page("https://shop.example/llms/pages/measure-your-pd.md", status=404, content_type="text/markdown"),
        page("https://shop.example/sunglasses/metallic", "Metallic sunglasses", status=404, family="collection_page"),
        page("https://shop.example/", "Eyewear", "Shop eyewear", "Glasses and sunglasses"),
    ]
    fingerprint = build_site_fingerprint(
        {"pages_found": len(pages), "pages_crawled": len(pages)},
        pages,
        "https://shop.example",
    )
    fixes = prepare_fixes(
        [{
            "rule": "broken_page",
            "category": "404_error",
            "source": "scanner_verified_failed_pages:404",
            "affected_pages": ["/llms/pages/measure-your-pd.md", "/sunglasses/metallic"],
            "page_url": "/llms/pages/measure-your-pd.md",
        }],
        fingerprint,
        {},
        get_playbook(fingerprint["primary_archetype"]),
        pages,
    )
    assert len(fixes) == 1
    assert fixes[0]["page_url"] == "/sunglasses/metallic"
    assert fixes[0]["affected_pages"] == ["/sunglasses/metallic"]
    assert fixes[0]["page_level_asset_evidence_version"] == "page_level_asset_evidence_v3_markdown"


def test_sitewide_canonical_uses_finance_business_page_not_contact():
    pages = [
        page("https://lender.example/", "Private lending", "Real estate loans", "Bridge and investor lending", family="homepage"),
        page("https://lender.example/contact", "Contact", "Contact us", family="contact"),
        page("https://lender.example/apply-now", "Apply now", "Apply for financing", family="conversion"),
        page("https://lender.example/loan-overview", "Loan overview", "Loan programs", family="loan_program"),
        page("https://lender.example/bridge-loans", "Bridge loans", "Bridge financing", family="loan_program"),
        page("https://lender.example/dscr-loans", "DSCR loans", "DSCR financing", family="loan_program"),
        page("https://lender.example/fix-and-flip", "Fix and flip", "Fix and flip loans", family="loan_program"),
        page("https://lender.example/blog/bridge-loan-guide", "Bridge loan guide", "Bridge loan guide", family="guide_article"),
        page("https://lender.example/blog/dscr-guide", "DSCR guide", "DSCR guide", family="guide_article"),
        page("https://lender.example/locations/california", "California loans", "California lending", family="location_landing"),
        page("https://lender.example/locations/texas", "Texas loans", "Texas lending", family="location_landing"),
        page("https://lender.example/about", "About", "About the lender", family="standard"),
    ]
    body = {"pages_found": len(pages), "pages_crawled": len(pages)}
    fingerprint = build_site_fingerprint(body, pages, "https://lender.example")
    playbook = get_playbook(fingerprint["primary_archetype"])
    raw_fixes = [
        {
            "rule": "canonical_missing",
            "category": "canonical",
            "source": "page_pattern:canonical_missing",
            "page_template_family": family,
            "affected_pages": urls,
            "issue_title": "Add canonical URLs",
        }
        for family, urls in (
            ("contact", ["/contact", "/about", "/"]),
            ("conversion", ["/apply-now", "/locations/california", "/locations/texas"]),
            ("loan_program", ["/loan-overview", "/bridge-loans", "/dscr-loans", "/fix-and-flip"]),
            ("guide_article", ["/blog/bridge-loan-guide", "/blog/dscr-guide"]),
        )
    ]
    fixes = prepare_fixes(raw_fixes, fingerprint, body, playbook, pages)
    sitewide = next(fix for fix in fixes if fix.get("page_scope") == "sitewide")
    assert sitewide["page_url"] in {"/apply-now", "/loan-overview", "/bridge-loans", "/dscr-loans", "/fix-and-flip"}
    assert sitewide["page_url"] != "/contact"
    assert sitewide["representative_page_version"] == "business_representative_page_v3_sitewide_archetype_ranking"
