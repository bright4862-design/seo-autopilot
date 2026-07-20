"""Production-shaped local business and hospitality classifier regressions."""

from app.review import ARCHETYPE_CLASSIFIER_VERSION, build_site_fingerprint, detect_business_model


def page(host, path, title="", h1="", meta="", schema=None, family=""):
    url = f"https://{host}{path}"
    return {
        "url": url,
        "final_url": url,
        "path": path,
        "status_code": 200,
        "content_type": "text/html; charset=utf-8",
        "title": title,
        "h1": h1,
        "meta_description": meta,
        "schema_types": schema or [],
        "page_template_family": family,
    }


def classify(host, pages):
    result = build_site_fingerprint(
        {"website_url": f"https://{host}", "pages_found": len(pages), "pages_crawled": len(pages)},
        pages,
        f"https://{host}",
    )
    assert result["classification"]["classifier_version"] == ARCHETYPE_CLASSIFIER_VERSION
    return result


def test_hartzler_dairy_is_local_business_not_content_publisher():
    host = "hartzlerdairy.com"
    pages = [
        page(host, "/", "Hartzler Family Dairy", "Farm-fresh dairy from our family", "Local creamery and family dairy in Ohio.", ["LocalBusiness", "Organization"]),
        page(host, "/our-story", "Our family dairy story"),
        page(host, "/find-us", "Find Hartzler dairy near you"),
        page(host, "/products/chocolate-milk", "Chocolate Milk"),
        page(host, "/products/whole-milk", "Whole Milk"),
    ]
    pages += [page(host, f"/news/farm-update-{index}", f"Farm update {index}", schema=["Article"]) for index in range(8)]
    result = classify(host, pages)
    assert result["primary_archetype"] == "local_business_hospitality", result["classification"]["winning_reason"]
    assert result["classification"]["structural_signals"]["local_dominant"] is True
    assert result["business_model"] == "local_service_or_hospitality"


def test_lamanna_bakery_identity_survives_default_wordpress_routes():
    host = "lamannabakery.com"
    pages = [
        page(host, "/", "LaManna's Bakery", "Toronto bakery and Italian food", "Family bakery, pastries, pizza and catering.", ["Bakery", "LocalBusiness"]),
        page(host, "/merch", "Bakery merch"),
        page(host, "/hello-world", "Hello world", schema=["BlogPosting"]),
        page(host, "/author/admin", "Admin archive"),
        page(host, "/category/uncategorized", "Uncategorized"),
    ]
    result = classify(host, pages)
    assert result["primary_archetype"] == "local_business_hospitality", result["classification"]["winning_reason"]
    assert result["classification"]["structural_signals"]["local_schema_pages"] >= 1


def test_norris_wines_is_winery_not_booking_marketplace():
    host = "norriswines.com"
    pages = [
        page(host, "/", "Norris Wines | Ribbon Ridge Winery", "Estate wines from Ribbon Ridge", "Visit our Oregon winery and tasting room.", ["Winery", "LocalBusiness"]),
        page(host, "/visit", "Visit the tasting room"),
        page(host, "/our-story", "Our winery story"),
        page(host, "/our-club", "Join the wine club"),
        page(host, "/reservations", "Reserve a tasting"),
        page(host, "/wine/new-releases", "New release wines"),
        page(host, "/wine/pinot-noir", "Pinot Noir"),
    ]
    result = classify(host, pages)
    assert result["primary_archetype"] == "local_business_hospitality", result["classification"]["winning_reason"]
    assert result["classification"]["structural_signals"]["booking_listing_pages"] == 0


def test_red_bamboo_is_restaurant_not_ecommerce():
    host = "redbamboo-nyc.com"
    pages = [
        page(host, "/", "Red Bamboo NYC", "Vegan comfort food restaurant", "Neighborhood restaurant in New York City.", ["Restaurant", "LocalBusiness"]),
        page(host, "/menu", "Restaurant menu"),
        page(host, "/reservations", "Reserve a table"),
        page(host, "/order-online", "Order food online"),
        page(host, "/catering", "Catering and private events"),
        page(host, "/shop", "Gift cards and merchandise"),
    ]
    result = classify(host, pages)
    assert result["primary_archetype"] == "local_business_hospitality", result["classification"]["winning_reason"]
    assert result["classification"]["structural_signals"]["retail_dominant"] is False


def test_restaurant_trade_publication_remains_content_blog():
    host = "restauranttrade.example"
    pages = [
        page(host, "/", "Restaurant Industry News", "Restaurant trade publication", "Industry news, analysis and editorial insights.", ["WebSite", "NewsMediaOrganization"]),
    ]
    pages += [
        page(host, f"/articles/restaurant-trends-{index}", f"Restaurant trends {index}", schema=["NewsArticle"])
        for index in range(16)
    ]
    result = classify(host, pages)
    assert result["primary_archetype"] == "content_blog", result["classification"]["winning_reason"]
    assert result["classification"]["structural_signals"]["local_dominant"] is False


def test_bakery_supply_catalog_remains_ecommerce_without_local_schema_or_routes():
    host = "bakerysupplies.example"
    pages = [
        page(host, "/", "Bakery Equipment Store", "Shop bakery supplies online", "Commercial bakery equipment, products and shipping."),
    ]
    pages += [
        page(host, f"/products/mixer-{index}", f"Commercial mixer {index}", schema=["Product", "Offer"])
        for index in range(8)
    ]
    pages += [page(host, "/collections/mixers", "Mixer collection")]
    result = classify(host, pages)
    assert result["primary_archetype"] == "ecommerce_specialty_retail", result["classification"]["winning_reason"]
    assert result["classification"]["structural_signals"]["local_dominant"] is False
