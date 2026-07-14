from app.review import run_review
from app.scanner import SCAN_BUDGETS, VERSION


def test_quick_budget_leaves_time_for_base44_response_reserve():
    assert VERSION == "python_scanner_v3_bounded_request"
    assert SCAN_BUDGETS["quick"]["timeout"] <= 40
    assert SCAN_BUDGETS["quick"]["fetch_timeout"] <= 6
    assert SCAN_BUDGETS["quick"]["max_sitemap_fetches"] <= 10


def test_ebay_marketplace_structure_is_not_classified_as_saas():
    pages = [
        {"url": "https://www.ebay.com/itm/123456", "status_code": 200, "title": "Buy it now", "h1": "Vintage camera", "meta_description": "Seller listing", "canonical": "https://www.ebay.com/itm/123456", "h1_count": 1},
        {"url": "https://www.ebay.com/sch/i.html?_nkw=camera", "status_code": 200, "title": "Shop by category", "h1": "Camera auctions", "meta_description": "Items from sellers", "canonical": "https://www.ebay.com/sch/i.html?_nkw=camera", "h1_count": 1},
        {"url": "https://www.ebay.com/b/Electronics/293", "status_code": 200, "title": "Electronics", "h1": "Electronics", "meta_description": "Buy products", "canonical": "https://www.ebay.com/b/Electronics/293", "h1_count": 1},
    ]
    result = run_review({"website_url": "https://www.ebay.com/", "pages_found": 900, "pages_crawled": 3, "pages": pages})
    fingerprint = result["site_fingerprint"]
    assert fingerprint["primary_archetype"] == "ecommerce_specialty_retail"
    assert fingerprint["business_model"] == "catalog_or_ecommerce"
