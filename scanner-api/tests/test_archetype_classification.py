"""Regression tests for the 18-site production audit's classification failures.

Each test reconstructs one audited failure mode with synthetic page evidence:
SaaS sites with large blogs must not become content/blog; retailers with
appointment language must not become booking marketplaces; travel publishers
must not become marketplaces; and thin or blocked crawls must be marked
inconclusive instead of counting as validation.
"""

from app.review import ARCHETYPE_CLASSIFIER_VERSION, build_site_fingerprint


def page(path, title="", description="", schema_types=None, status=200, h1=""):
    return {
        "url": f"https://site.example.com{path}",
        "final_url": f"https://site.example.com{path}",
        "path": path,
        "title": title or path.strip("/").replace("-", " ").title() or "Home",
        "h1": h1 or title,
        "meta_description": description,
        "schema_types": schema_types or [],
        "status_code": status,
    }


def blog_pages(count, topic="productivity"):
    return [
        page(
            f"/blog/{topic}-guide-{i}",
            title=f"The complete {topic} guide part {i}",
            description=f"Article with insights, resources and a newsletter for {topic} readers.",
        )
        for i in range(count)
    ]


def fingerprint(pages, url="https://site.example.com", body=None):
    return build_site_fingerprint(body or {"website_url": url}, pages, url)


# --- 1. SaaS vs dominant crawled template (Basecamp/Buffer/Intercom/Webflow) --


def test_saas_with_large_blog_is_saas_not_content_blog():
    pages = [
        page("/", title="Acme — Project management software", description="The all-in-one platform for teams.", h1="Project management software"),
        page("/pricing", title="Pricing — Acme"),
        page("/features", title="Features — Acme"),
        page("/integrations", title="Integrations — Acme"),
        page("/customers", title="Customer stories — Acme"),
        page("/login", title="Log in"),
        page("/signup", title="Start your free trial"),
    ] + blog_pages(40)
    result = fingerprint(pages)
    assert result["primary_archetype"] == "saas_app_membership", result["classification"]["winning_reason"]
    assert result["classification"]["state"] == "classified"


def test_saas_with_docs_and_help_center_is_saas():
    pages = [
        page("/", title="Helpdesk software for support teams", h1="Customer support platform"),
        page("/pricing"),
        page("/demo", title="Book a demo"),
        page("/api", title="API reference"),
        page("/docs/getting-started"),
        page("/docs/webhooks"),
        page("/login"),
    ] + blog_pages(30, topic="support")
    result = fingerprint(pages)
    assert result["primary_archetype"] == "saas_app_membership"


# --- Signal-shaped: app site without pricing must not be content/blog --------


def test_app_site_without_pricing_is_not_content_blog():
    pages = [
        page("/", title="Private messenger app", description="Fast, simple, secure messaging software.", h1="Speak freely"),
        page("/download", title="Download the app", schema_types=["SoftwareApplication"]),
        page("/apps/android", title="Android app", schema_types=["SoftwareApplication"]),
        page("/apps/desktop", title="Desktop app", schema_types=["SoftwareApplication"]),
    ] + blog_pages(25, topic="privacy")
    result = fingerprint(pages)
    assert result["primary_archetype"] != "content_blog", result["classification"]["winning_reason"]
    assert result["primary_archetype"] in {"saas_app_membership", "general"}


# --- Shopify-shaped: SaaS whose copy is full of commerce vocabulary ----------


def test_saas_selling_ecommerce_software_is_saas_not_store_or_blog():
    pages = [
        page("/", title="Start your online store — Commerce platform", description="Software to sell products, manage checkout, cart and shipping."),
        page("/pricing", title="Plans and pricing"),
        page("/features/checkout", title="Checkout features", description="Sell with our cart and checkout software."),
        page("/solutions/retail", title="Retail solutions"),
        page("/login"),
        page("/signup", title="Start free trial"),
    ] + blog_pages(35, topic="selling")
    result = fingerprint(pages)
    assert result["primary_archetype"] == "saas_app_membership", result["classification"]["winning_reason"]


# --- 2. IKEA-shaped: retailer with appointment/planning language -------------


def test_retailer_with_planning_appointments_is_ecommerce_not_booking():
    pages = [
        page("/", title="Furniture and home goods", description="Shop furniture with delivery and in-store pickup."),
        page("/cat/sofas", title="Sofas", description="Browse sofas in stock."),
        page("/cat/beds", title="Beds"),
        page("/p/billy-bookcase-white", title="BILLY bookcase", schema_types=["Product"], description="Add to bag. In stock for delivery."),
        page("/p/malm-bed-frame", title="MALM bed frame", schema_types=["Product"]),
        page("/p/poang-armchair", title="POÄNG armchair", schema_types=["Product"]),
        page("/planning/kitchen-appointment", title="Book a kitchen planning appointment", description="Reserve a planning session with our experts."),
        page("/services/delivery", title="Delivery services"),
    ]
    result = fingerprint(pages)
    assert result["primary_archetype"] == "ecommerce_specialty_retail", result["classification"]["winning_reason"]
    assert result["primary_archetype"] != "booking_experiences_marketplace"


# --- 3. Publisher vs booking marketplace (Nomadic Matt) -----------------------


def test_travel_publisher_with_booking_ctas_is_content_not_marketplace():
    pages = [
        page("/", title="Travel better, cheaper, longer", description="Travel tips, guides and hotel recommendations from a travel blogger."),
        page("/about", title="About the author"),
    ] + [
        page(
            f"/blog/where-to-stay-{city}",
            title=f"Where to stay in {city}: best hotels and hostels",
            description=f"My favorite hotels in {city}. Book your reservation through these links. Travel guide with destination tips and tours.",
        )
        for city in ["paris", "tokyo", "rome", "bangkok", "lisbon", "cusco", "hanoi", "oslo"]
    ]
    result = fingerprint(pages)
    assert result["primary_archetype"] != "booking_experiences_marketplace", result["classification"]["winning_reason"]
    assert result["primary_archetype"] in {"content_blog", "general"}


def test_real_marketplace_with_listings_stays_booking():
    pages = [
        page("/", title="Réservez des activités uniques", description="Réservation d'activités et loisirs."),
        page("/activites/paris", title="Activités à Paris"),
        page("/activites/lyon", title="Activités à Lyon"),
        page("/annonce/degustation-vin-paris", title="Dégustation de vin — réservation"),
        page("/annonce/atelier-cuisine", title="Atelier cuisine — réservez"),
        page("/booking/checkout", title="Réservation"),
    ]
    result = fingerprint(pages, url="https://www.funbooker.com")
    assert result["primary_archetype"] == "booking_experiences_marketplace", result["classification"]["winning_reason"]


# --- Pure blogs must remain content/blog (WPBeginner control) -----------------


def test_pure_blog_remains_content_blog():
    pages = [
        page("/", title="WordPress tutorials for beginners", description="Free guides, articles and resources."),
    ] + blog_pages(45, topic="wordpress")
    result = fingerprint(pages)
    assert result["primary_archetype"] == "content_blog"


# --- 4. Evidence sufficiency ---------------------------------------------------


def test_single_page_crawl_is_inconclusive():
    result = fingerprint([page("/", title="Electronics, cars, fashion — online marketplace")])
    assert result["classification"]["state"] == "inconclusive_insufficient_evidence"
    assert result["classification"]["evidence_sufficiency"] == "insufficient_pages"
    assert result["vertical_confidence"] <= 0.35


def test_mostly_rate_limited_crawl_is_access_limited():
    ok_pages = [page(f"/p/lipstick-{i}", schema_types=["Product"]) for i in range(6)] + [page("/", title="Beauty store")]
    blocked = [page(f"/blocked-{i}", status=429) for i in range(60)]
    body = {"website_url": "https://site.example.com", "scan_coverage": {"rate_limited_pages": 60}}
    result = fingerprint(ok_pages + blocked, body=body)
    assert result["classification"]["evidence_sufficiency"] == "access_limited"
    assert result["classification"]["state"] == "inconclusive_insufficient_evidence"
    assert result["vertical_confidence"] <= 0.35


def test_access_limited_but_well_sampled_stays_classified():
    ok_pages = [
        page("/", title="Sustainable shoes", description="Shop our wool runners."),
        page("/collections/mens", title="Mens shoes"),
        page("/collections/womens", title="Womens shoes"),
    ] + [page(f"/products/wool-runner-{i}", schema_types=["Product"]) for i in range(12)]
    blocked = [page(f"/blocked-{i}", status=429) for i in range(4)]
    result = fingerprint(ok_pages + blocked)
    assert result["classification"]["state"] == "classified"
    assert result["primary_archetype"] == "ecommerce_specialty_retail"


# --- 5. Output and auditability -----------------------------------------------


def test_classification_output_is_auditable():
    pages = [
        page("/", title="Acme — Project management software"),
        page("/pricing"),
        page("/features"),
        page("/login"),
        page("/signup"),
    ] + blog_pages(20)
    result = fingerprint(pages)
    classification = result["classification"]
    assert classification["classifier_version"] == ARCHETYPE_CLASSIFIER_VERSION
    assert classification["scores"] and classification["scores"][0]["archetype"] == result["primary_archetype"]
    assert "saas" in classification["structural_signals"]
    assert classification["winning_reason"]
    assert result["classification_state"] == classification["state"]
