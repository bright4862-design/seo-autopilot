"""Production-derived representative URL and generic asset evidence regressions."""

from app.review import ARCHETYPE_CLASSIFIER_VERSION, build_site_fingerprint, get_playbook, prepare_fixes


def page(url, *, family="standard", status=200, title="Page", h1="Page", content_type="text/html"):
    return {
        "url": url,
        "status_code": status,
        "title": title,
        "h1": h1,
        "meta_description": "Description",
        "page_template_family": family,
        "content_type": content_type,
        "indexable": status == 200,
    }


def ranked_url(archetype_pages, affected, rule="missing_canonical"):
    fingerprint = build_site_fingerprint({}, archetype_pages, archetype_pages[0]["url"])
    fixes = prepare_fixes(
        [{
            "rule": rule,
            "category": "technical_seo",
            "issue_title": "Representative evidence test",
            "affected_pages": affected,
            "page_template_family": "mixed",
        }],
        fingerprint,
        {},
        get_playbook(fingerprint["primary_archetype"]),
        archetype_pages,
    )
    assert fixes
    return fixes[0]


def test_saas_product_route_beats_contact_and_signup():
    pages = [
        page("https://saas.example/", title="Software platform", h1="Software platform"),
        page("https://saas.example/contact", family="contact"),
        page("https://saas.example/signup", family="route_boundary"),
        page("https://saas.example/payments", family="product_page"),
        page("https://saas.example/billing", family="product_page"),
        page("https://saas.example/pricing", family="conversion"),
    ]
    fix = ranked_url(pages, ["/contact", "/signup", "/payments", "/billing", "/pricing"])
    assert fix["page_url"] in {"/payments", "/billing", "/pricing"}
    assert fix["page_url"] not in {"/contact", "/signup"}


def test_ecommerce_category_beats_cart_checkout_reservation_and_ccpa():
    pages = [
        page("https://shop.example/", title="Eyewear store", h1="Shop eyewear"),
        page("https://shop.example/cart", family="route_boundary"),
        page("https://shop.example/checkout", family="route_boundary"),
        page("https://shop.example/reservation/edit", family="route_boundary"),
        page("https://shop.example/ccpa", family="legal"),
        page("https://shop.example/eyeglasses", family="collection_page"),
        page("https://shop.example/sunglasses", family="collection_page"),
        page("https://shop.example/products/frame-a", family="product_page"),
    ]
    fix = ranked_url(pages, ["/cart", "/checkout", "/reservation/edit", "/ccpa", "/eyeglasses", "/sunglasses", "/products/frame-a"])
    assert fix["page_url"] in {"/eyeglasses", "/sunglasses", "/products/frame-a"}


def test_publisher_topic_hub_beats_contact_and_random_article_for_group_issue():
    pages = [
        page("https://news.example/", title="Technology news", h1="Technology news"),
        page("https://news.example/contact", family="contact"),
        page("https://news.example/topics/ai", family="collection_page"),
        page("https://news.example/category/startups", family="collection_page"),
        page("https://news.example/news/random-story", family="guide_article"),
        page("https://news.example/news/another-story", family="guide_article"),
    ]
    fix = ranked_url(pages, ["/contact", "/topics/ai", "/category/startups", "/news/random-story"])
    assert fix["page_url"] in {"/topics/ai", "/category/startups"}


def test_finance_hub_beats_contact_and_disclosure():
    pages = [
        page("https://finance.example/", title="Loans and banking", h1="Loans and banking"),
        page("https://finance.example/contact", family="contact"),
        page("https://finance.example/disclosures/cash-account", family="legal"),
        page("https://finance.example/mortgages", family="collection_page"),
        page("https://finance.example/credit-cards", family="collection_page"),
        page("https://finance.example/loans/personal", family="loan_program"),
    ]
    fix = ranked_url(pages, ["/contact", "/disclosures/cash-account", "/mortgages", "/credit-cards", "/loans/personal"])
    assert fix["page_url"] in {"/mortgages", "/credit-cards", "/loans/personal"}


def test_asset_only_generic_broken_page_is_suppressed():
    pages = [
        page("https://publisher.example/", title="Publisher", h1="Publisher"),
        page("https://publisher.example/wp-content/uploads/2026/07/equity.png", status=404, content_type="image/png"),
    ]
    fingerprint = build_site_fingerprint({}, pages, "https://publisher.example")
    fixes = prepare_fixes(
        [{
            "rule": "broken_page",
            "category": "web_dev",
            "issue_title": "Fix broken page",
            "affected_pages": ["/wp-content/uploads/2026/07/equity.png"],
            "status_code": 404,
        }],
        fingerprint,
        {},
        get_playbook(fingerprint["primary_archetype"]),
        pages,
    )
    assert fixes == []


def test_mixed_generic_broken_page_keeps_html_only():
    pages = [
        page("https://publisher.example/", title="Publisher", h1="Publisher"),
        page("https://publisher.example/news/missing-story", status=404, family="guide_article"),
        page("https://publisher.example/wp-content/uploads/missing.png", status=404, content_type="image/png"),
    ]
    fix = ranked_url(
        pages,
        ["/wp-content/uploads/missing.png", "/news/missing-story"],
        rule="broken_page",
    )
    assert fix["page_url"] == "/news/missing-story"
    assert fix["affected_pages"] == ["/news/missing-story"]
    assert fix["page_level_asset_evidence_version"] == "page_level_asset_evidence_v3_markdown"


def test_classifier_marker_is_unchanged_by_evidence_patch():
    pages = [
        page("https://saas.example/", title="Software platform", h1="Software platform"),
        page("https://saas.example/features", family="product_page"),
        page("https://saas.example/pricing", family="conversion"),
        page("https://saas.example/integrations", family="collection_page"),
    ]
    fingerprint = build_site_fingerprint({}, pages, "https://saas.example")
    assert fingerprint["classification"]["classifier_version"] == ARCHETYPE_CLASSIFIER_VERSION
