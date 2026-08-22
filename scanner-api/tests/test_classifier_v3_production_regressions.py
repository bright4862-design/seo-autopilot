"""Classifier regressions reproduced from focused production retests."""

from app.review import build_site_fingerprint, run_review


def page(url, title="", h1="", meta="", schema=None, status=200, family=""):
    return {
        "url": url,
        "status_code": status,
        "title": title,
        "h1": h1,
        "meta_description": meta,
        "schema_types": schema or [],
        "page_template_family": family,
    }


def shopify_like_pages():
    """SaaS platform with heavy finance vocabulary but no finance routes."""
    pages = [
        page("https://saasplatform.example/", "Start your online business", "The commerce platform", "Sell online with our software platform"),
        page("https://saasplatform.example/pricing", "Pricing plans"),
        page("https://saasplatform.example/features", "Platform features"),
        page("https://saasplatform.example/solutions/enterprise", "Enterprise solutions"),
        page("https://saasplatform.example/login", "Log in"),
        page("https://saasplatform.example/signup", "Start free trial"),
        page("https://saasplatform.example/developers", "Developer docs"),
        page("https://saasplatform.example/apps", "App marketplace"),
        page("https://saasplatform.example/platform", "Platform overview"),
    ]
    finance_topics = [
        ("capital", "Business loans and funding", "Get business lending, capital, and loans with flexible payments"),
        ("payments", "Accept payments and credit card processing", "Payments, credit card rates, money transfers"),
        ("balance", "Money management and banking", "Banking, money, business account, interest rate"),
    ]
    for slug, title, meta in finance_topics:
        for i in range(12):
            pages.append(page(
                f"https://saasplatform.example/{slug}/guide-{i}",
                f"{title} {i}",
                title,
                f"{meta}. Lending and private lending explained. Bridge loan basics for real estate investor stores.",
            ))
    return pages


def nomadicmatt_like_pages():
    """Travel publisher with archives, affiliate vocabulary, and a small shop."""
    pages = [
        page("https://travelblog.example/", "Travel Better, Cheaper, Longer", "Travel blog", "Travel tips, guides and articles from a travel writer", schema=["WebSite"]),
        page("https://travelblog.example/shop/", "Merch shop", "Shop"),
        page("https://travelblog.example/category/travel-tips/", "Travel tips archive"),
        page("https://travelblog.example/category/destinations/", "Destinations archive"),
        page("https://travelblog.example/category/hotels/", "Hotel reviews archive"),
    ]
    for i in range(45):
        pages.append(page(
            f"https://travelblog.example/travel-blogs/how-to-book-cheap-hotels-{i}/",
            f"How to book cheap hotels and deals {i}",
            "How to find hotel deals",
            "Book hotels, buy travel insurance, best booking sites, seller deals and discounts",
            schema=["BlogPosting"],
        ))
    for i in range(10):
        pages.append(page(
            f"https://travelblog.example/2026/0{(i % 9) + 1}/backpacking-guide-{i}/",
            f"Backpacking guide {i}",
            "Backpacking guide",
            "A complete guide with itineraries, bookings, and hotel picks",
            schema=["Article"],
        ))
    return pages


def ikea_global_editorial_pages():
    """The global corporate portal is editorial, unlike a country retail storefront."""
    pages = [
        page(
            "https://furniture.example/global/en/",
            "Welcome to the global brand site",
            "Welcome to our global site",
            "Stories, newsroom, jobs, our business, design and home inspiration",
        ),
    ]
    for i in range(30):
        pages.append(page(
            f"https://furniture.example/global/en/stories/design/story-{i}/",
            f"Designer story {i}",
            "Meet the designer",
            "A story about design, ideas, inspiration and life at home",
            schema=["Article"],
        ))
    for i in range(10):
        pages.append(page(
            f"https://furniture.example/global/en/newsroom/article-{i}/",
            f"Newsroom article {i}",
            "Company news",
            "News and information about the business",
            schema=["NewsArticle"],
        ))
    return pages


def ikea_like_pages():
    """Retailer with heavy editorial content plus product routes and schema."""
    pages = [
        page("https://furniture.example/", "Furniture and home ideas", "Affordable furniture", "Shop furniture, decoration and home ideas"),
        page("https://furniture.example/cart", "Shopping cart"),
    ]
    for i in range(35):
        pages.append(page(
            f"https://furniture.example/p/bookcase-model-{i}-9000{i}/",
            f"BOOKCASE {i} — Bookcases",
            f"Bookcase {i}",
            "Buy this bookcase online or in store",
            schema=["Product", "Offer"],
        ))
    for i in range(8):
        pages.append(page(
            f"https://furniture.example/cat/living-room-{i}/",
            f"Living room furniture {i}",
            "Living room",
        ))
    for i in range(40):
        pages.append(page(
            f"https://furniture.example/ideas/home-inspiration-{i}/",
            f"Home ideas and inspiration {i}",
            "Ideas and inspiration",
            "Guides, articles, tips, resources and news about decorating your home. Subscribe to the newsletter.",
            schema=["Article"],
        ))
    return pages


def ebay_like_payload():
    return {
        "website_url": "https://marketplace.example",
        "pages_found": 1,
        "pages_crawled": 1,
        "crawled_pages": [page("https://marketplace.example/", "503 Service Unavailable", status=503)],
    }


def test_saas_structure_outranks_incidental_finance_language():
    fingerprint = build_site_fingerprint({}, shopify_like_pages(), "https://saasplatform.example")
    assert fingerprint["primary_archetype"] == "saas_app_membership", fingerprint["classification"]["winning_reason"]


def test_finance_vocabulary_capped_without_finance_routes():
    fingerprint = build_site_fingerprint({}, shopify_like_pages(), "https://saasplatform.example")
    scores = {item["archetype"]: item["score"] for item in fingerprint["classification"]["scores"]}
    assert scores.get("saas_app_membership", 0) > scores.get("finance_insurance_lead_gen", 0)


def test_publisher_structure_outranks_incidental_shopping_language():
    fingerprint = build_site_fingerprint({}, nomadicmatt_like_pages(), "https://travelblog.example")
    assert fingerprint["primary_archetype"] == "content_blog", fingerprint["classification"]["winning_reason"]


def test_plural_travel_publisher_routes_count_as_article_structure():
    fingerprint = build_site_fingerprint({}, nomadicmatt_like_pages(), "https://travelblog.example")
    signals = fingerprint["classification"]["structural_signals"]
    assert signals["article_route_pages"] >= 45
    assert signals["publisher_dominant"] is True


def test_wordpress_category_archives_are_not_ecommerce_structure():
    pages = [item for item in nomadicmatt_like_pages() if "/shop/" not in item["url"]]
    fingerprint = build_site_fingerprint({}, pages, "https://travelblog.example")
    assert "/category/" not in fingerprint["classification"]["structural_signals"]["ecommerce"]


def test_retail_routes_and_schema_outrank_editorial_content():
    fingerprint = build_site_fingerprint({}, ikea_like_pages(), "https://furniture.example")
    assert fingerprint["primary_archetype"] == "ecommerce_specialty_retail", fingerprint["classification"]["winning_reason"]


def test_global_editorial_portal_is_not_forced_to_retail_by_brand_context():
    fingerprint = build_site_fingerprint({}, ikea_global_editorial_pages(), "https://furniture.example/global/en/")
    assert fingerprint["primary_archetype"] == "content_blog", fingerprint["classification"]["winning_reason"]
    assert fingerprint["classification"]["structural_signals"]["retail_dominant"] is False


def test_classification_debug_signals_are_exposed():
    classification = build_site_fingerprint({}, ikea_like_pages(), "https://furniture.example")["classification"]
    assert classification["classifier_version"].startswith("archetype_classifier_v9")
    signals = classification["structural_signals"]
    for key in ("product_route_pages", "article_route_pages", "publisher_dominant", "retail_dominant", "saas_dominant", "finance"):
        assert key in signals
    assert classification["winning_reason"]


def test_one_page_503_crawl_is_inconclusive_not_good():
    result = run_review(ebay_like_payload())
    assert result["scan_status"] == "inconclusive_insufficient_evidence"
    assert result["score_is_provisional"] is True
    assert result["release_gate_eligible"] is False
    assert result["website_health_report"]["health_grade"] == "Insufficient evidence"
    assert result["review_confidence_state"] == "insufficient_evidence"


def test_few_usable_pages_is_inconclusive_even_with_200s():
    payload = {
        "website_url": "https://tinysite.example",
        "pages_found": 3,
        "pages_crawled": 3,
        "crawled_pages": [
            page("https://tinysite.example/", "Home"),
            page("https://tinysite.example/about", "About"),
            page("https://tinysite.example/contact", "Contact"),
        ],
    }
    result = run_review(payload)
    assert result["scan_status"] == "inconclusive_insufficient_evidence"
    assert result["score_is_provisional"] is True
    assert result["release_gate_eligible"] is False


def test_complete_three_page_inventory_with_final_url_dedup_is_authoritative():
    pages = [
        page("https://tinysite.example/", "Home", h1="Tiny Site"),
        page("https://tinysite.example/merch", "Merch", h1="Merch"),
        page("https://tinysite.example/author/admin", "Author archive", h1="Author archive", family="archive"),
    ]
    result = run_review({
        "website_url": "https://tinysite.example/",
        "pages_found": 4,
        "pages_crawled": 3,
        "queued_remaining": 0,
        "crawl_timing": {
            "queue_exhausted": True,
            "crawl_deadline_reached": False,
            "failed_fetch_count": 0,
            "final_url_duplicates_deduped": 1,
            # A small inventory is only "complete" if something authoritative
            # said how big it is. An exhausted frontier and zero fetch errors
            # look identical whether the site really has three pages or its
            # discovery was blocked.
            "sitemap_sources": [{
                "url": "https://tinysite.example/sitemap.xml",
                "source": "robots_declared",
                "outcome": "urls",
                "loc_count": 4,
            }],
        },
        "crawled_pages": pages,
    })
    classification = result["site_fingerprint"]["classification"]
    assert classification["state"] == "classified"
    assert classification["evidence_sufficiency"] == "complete_small_site_inventory"
    assert classification["complete_small_site_inventory"] is True
    assert classification["small_site_inventory_accounting"]["final_url_duplicates_deduped"] == 1
    assert result["scan_status"] == "complete"
    assert result["score_is_provisional"] is False
    assert result["release_gate_eligible"] is True
    assert result["health_score_status"] == "available"
    assert result["health_score"] is not None


def test_three_pages_without_complete_inventory_accounting_stays_inconclusive():
    pages = [
        page("https://tinysite.example/", "Home"),
        page("https://tinysite.example/about", "About"),
        page("https://tinysite.example/contact", "Contact"),
    ]
    result = run_review({
        "website_url": "https://tinysite.example/",
        "pages_found": 4,
        "pages_crawled": 3,
        "queued_remaining": 0,
        "crawl_timing": {
            "queue_exhausted": True,
            "crawl_deadline_reached": False,
            "failed_fetch_count": 0,
            "final_url_duplicates_deduped": 0,
        },
        "crawled_pages": pages,
    })
    assert result["site_fingerprint"]["classification"]["complete_small_site_inventory"] is False
    assert result["scan_status"] == "inconclusive_insufficient_evidence"
    assert result["score_is_provisional"] is True
    assert result["release_gate_eligible"] is False


def test_healthy_mixed_retail_crawl_stays_complete():
    pages = ikea_like_pages()
    result = run_review({
        "website_url": "https://furniture.example",
        "pages_found": len(pages),
        "pages_crawled": len(pages),
        "crawled_pages": pages,
    })
    assert result["scan_status"] == "complete"
    assert result["website_health_report"]["health_grade"] != "Insufficient evidence"
    assert result["release_gate_eligible"] is True


def test_blocked_crawl_still_wins_over_insufficient():
    pages = [page(f"https://blockedsite.example/page-{i}", "Too Many Requests", status=429) for i in range(101)]
    result = run_review({
        "website_url": "https://blockedsite.example",
        "pages_found": 101,
        "pages_crawled": 101,
        "crawled_pages": pages,
    })
    assert result["scan_status"] == "blocked_or_incomplete"
    assert result["release_gate_eligible"] is False
