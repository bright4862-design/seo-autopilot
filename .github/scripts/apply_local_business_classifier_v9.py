from __future__ import annotations

import hashlib
import json
from pathlib import Path

OLD_VERSION = "archetype_classifier_v8_platform_product_routes"
NEW_VERSION = "archetype_classifier_v9_local_business_hospitality"


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one replacement, found {count}: {old!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_expected(path: str, old: str, new: str, expected: int = 1) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != expected:
        raise SystemExit(f"{path}: expected {expected} replacements, found {count}: {old!r}")
    target.write_text(text.replace(old, new), encoding="utf-8")


review_path = "scanner-api/app/review.py"
replace_once(review_path, f'ARCHETYPE_CLASSIFIER_VERSION = "{OLD_VERSION}"', f'ARCHETYPE_CLASSIFIER_VERSION = "{NEW_VERSION}"')

replace_once(
    review_path,
    '''BOOKING_STRUCTURAL_PATTERNS = BOOKING_LISTING_PATTERNS + (
    "/booking", "/book/", "/reservation", "/availability", "/tickets", "/billetterie",
)

PLAYBOOKS = {''',
    '''BOOKING_STRUCTURAL_PATTERNS = BOOKING_LISTING_PATTERNS + (
    "/booking", "/book/", "/reservation", "/availability", "/tickets", "/billetterie",
)
LOCAL_BUSINESS_ROUTE_PATTERNS = (
    "/menu", "/menus", "/visit", "/tasting", "/tastings", "/wine-club",
    "/our-club", "/vineyard", "/hours", "/directions", "/catering",
    "/private-events", "/order-online", "/reservations", "/reserve-a-table",
    "/find-us", "/locations",
)
LOCAL_HOMEPAGE_IDENTITY_PATTERNS = (
    r"\\bbakery\\b", r"\\brestaurant\\b", r"\\bwinery\\b", r"\\bvineyard\\b",
    r"\\btasting room\\b", r"\\bwine club\\b", r"\\bdairy\\b", r"\\bcreamery\\b",
    r"\\bcaf[eé]\\b", r"\\bcoffee shop\\b", r"\\bbistro\\b", r"\\bpizzeria\\b",
)
LOCAL_PUBLISHER_IDENTITY_TERMS = (
    "industry news", "trade publication", "magazine", "journal", "media company",
    "editorial publication", "industry insights",
)

PLAYBOOKS = {''',
)

replace_once(
    review_path,
    '''    "content_blog": {
        "label": "content / blog-heavy site",''',
    '''    "local_business_hospitality": {
        "label": "local business / food / hospitality",
        "keywords": [
            "bakery", "restaurant", "winery", "vineyard", "tasting room", "wine club",
            "dairy", "creamery", "cafe", "café", "coffee shop", "bistro", "pizzeria",
            "family owned", "locally owned", "estate wines", "farmstead", "artisan bread",
            "pastry", "menu", "catering", "private events", "visit us", "opening hours",
        ],
        "money_patterns": [
            "/menu", "/visit", "/tasting", "/wine-club", "/our-club", "/hours",
            "/directions", "/catering", "/private-events", "/order-online",
            "/reservations", "/reserve-a-table", "/find-us", "/locations",
        ],
        "priority_pages": [
            "homepage", "menu or product overview", "visit, hours, and location pages",
            "reservation or tasting pages", "about/our-story pages", "contact and trust pages",
        ],
        "priority_issues": [
            "local discoverability", "location and opening-hours accuracy", "menu/product indexability",
            "reservation or visit-path reliability", "LocalBusiness schema", "metadata on key conversion pages",
        ],
        "demote": ["default WordPress archives", "old news posts", "tag pages", "utility account routes"],
        "owner_rule": "Local schema, redirects, canonicals, reservation paths, and repeated template issues usually need your_web_person.",
    },
    "content_blog": {
        "label": "content / blog-heavy site",''',
)

replace_once(
    review_path,
    '''    software_schema_pages = count_schema_pages(classifier_pages, ("softwareapplication", "mobileapplication", "webapplication"))
    product_route_pages = sum(''',
    '''    software_schema_pages = count_schema_pages(classifier_pages, ("softwareapplication", "mobileapplication", "webapplication"))
    local_schema_pages = count_schema_pages(
        classifier_pages,
        ("localbusiness", "restaurant", "winery", "bakery", "foodestablishment", "cafeorcoffeeshop"),
    )
    product_route_pages = sum(''',
)

replace_once(
    review_path,
    '''    nonprofit_route_pages = sum(
        1 for path in page_paths if any(pattern in path for pattern in NONPROFIT_STRUCTURAL_PATTERNS)
    )
    booking_listing_pages = sum(''',
    '''    nonprofit_route_pages = sum(
        1 for path in page_paths if any(pattern in path for pattern in NONPROFIT_STRUCTURAL_PATTERNS)
    )
    local_route_pages = sum(
        1 for path in page_paths if any(pattern in path for pattern in LOCAL_BUSINESS_ROUTE_PATTERNS)
    )
    booking_listing_pages = sum(''',
)

replace_once(
    review_path,
    '''    nonprofit_homepage_identity = has_any(homepage_text, [
        "nonprofit", "non-profit", "charity", "donate", "donation", "fundraising",
        "support our work", "monthly giving", "clean water", "our impact",
    ])
    publisher_dominant = bool(''',
    '''    nonprofit_homepage_identity = has_any(homepage_text, [
        "nonprofit", "non-profit", "charity", "donate", "donation", "fundraising",
        "support our work", "monthly giving", "clean water", "our impact",
    ])
    local_publisher_identity = has_any(homepage_text, LOCAL_PUBLISHER_IDENTITY_TERMS)
    local_homepage_identity = bool(
        any(re.search(pattern, homepage_text, re.I) for pattern in LOCAL_HOMEPAGE_IDENTITY_PATTERNS)
        and not local_publisher_identity
    )
    publisher_dominant = bool(''',
)

replace_once(
    review_path,
    '''    retail_dominant = bool(
        (
            product_route_pages >= 3
            and product_route_pages >= max(3, round(article_route_pages * 0.45))
        )
        or (
            product_schema_pages >= 3
            and product_schema_pages >= max(3, round(article_schema_pages * 0.75))
        )
        or (
            len(ecommerce_structural) >= 3
            and product_route_pages > 0
            and product_route_pages >= max(2, round(article_route_pages * 0.35))
        )
    )
    saas_business_identity = bool(''',
    '''    retail_dominant = bool(
        (
            product_route_pages >= 3
            and product_route_pages >= max(3, round(article_route_pages * 0.45))
        )
        or (
            product_schema_pages >= 3
            and product_schema_pages >= max(3, round(article_schema_pages * 0.75))
        )
        or (
            len(ecommerce_structural) >= 3
            and product_route_pages > 0
            and product_route_pages >= max(2, round(article_route_pages * 0.35))
        )
    )
    local_dominant = bool(
        local_schema_pages >= 1
        or local_route_pages >= 3
        or (local_homepage_identity and not publisher_dominant)
    )
    if retail_dominant and local_schema_pages == 0 and local_route_pages == 0:
        local_dominant = False
    saas_business_identity = bool(''',
)

replace_once(
    review_path,
    '''        if key == "nonprofit_fundraising":
            if not nonprofit_dominant:
                score = min(score, 4.0)
            else:
                score += 10.0 * len(nonprofit_structural)
                score += 2.0 * min(nonprofit_route_pages, 25)
                if nonprofit_homepage_identity:
                    score += 20.0
        if key == "content_blog" and publisher_dominant:''',
    '''        if key == "nonprofit_fundraising":
            if not nonprofit_dominant:
                score = min(score, 4.0)
            else:
                score += 10.0 * len(nonprofit_structural)
                score += 2.0 * min(nonprofit_route_pages, 25)
                if nonprofit_homepage_identity:
                    score += 20.0
        if key == "local_business_hospitality":
            if not local_dominant:
                score = min(score, 3.0)
            else:
                score += 24.0
                score += 5.0 * min(local_schema_pages, 4)
                score += 3.0 * min(local_route_pages, 10)
                if local_homepage_identity:
                    score += 24.0
        if key == "content_blog" and publisher_dominant:''',
)

replace_once(
    review_path,
    '''    structural_competitor = saas_dominant or retail_dominant or nonprofit_dominant''',
    '''    structural_competitor = saas_dominant or retail_dominant or nonprofit_dominant or local_dominant''',
)

replace_once(
    review_path,
    '''            "software_schema_pages": software_schema_pages,
            "product_route_pages": product_route_pages,''',
    '''            "software_schema_pages": software_schema_pages,
            "local_schema_pages": local_schema_pages,
            "local_route_pages": local_route_pages,
            "local_homepage_identity": local_homepage_identity,
            "local_publisher_identity": local_publisher_identity,
            "local_dominant": local_dominant,
            "product_route_pages": product_route_pages,''',
)

replace_once(
    review_path,
    '''            f"ecommerce={len(ecommerce_structural)}, booking={len(booking_structural)}, "
            f"finance={len(finance_structural)}, nonprofit={len(nonprofit_structural)}; "
            f"dominance publisher={publisher_dominant}, retail={retail_dominant}, "
            f"saas={saas_dominant}, app_distribution={saas_app_distribution_identity}, "''',
    '''            f"ecommerce={len(ecommerce_structural)}, booking={len(booking_structural)}, "
            f"finance={len(finance_structural)}, nonprofit={len(nonprofit_structural)}, "
            f"local_routes={local_route_pages}, local_schema={local_schema_pages}; "
            f"dominance publisher={publisher_dominant}, retail={retail_dominant}, local={local_dominant}, "
            f"saas={saas_dominant}, app_distribution={saas_app_distribution_identity}, "''',
)

replace_once(
    review_path,
    '''        "nonprofit_fundraising": "nonprofit_or_fundraising",
        "content_blog": "content_or_general_business",''',
    '''        "nonprofit_fundraising": "nonprofit_or_fundraising",
        "local_business_hospitality": "local_service_or_hospitality",
        "content_blog": "content_or_general_business",''',
)

Path("scanner-api/tests/test_classifier_v9_local_business.py").write_text('''"""Production-shaped local business and hospitality classifier regressions."""

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
''', encoding="utf-8")

version_files = [
    "scanner-api/tests/test_classifier_v7_html_route_evidence.py",
    "scanner-api/tests/test_observability.py",
    "scanner-api/tests/test_representative_evidence_v8.py",
    "src/lib/scanStorageRecovery.js",
    "src/lib/scanRunModel.js",
    "tests/frontend/scanRunPersistence.test.mjs",
    "tests/frontend/releaseAuthorityGate.test.mjs",
]
for path in version_files:
    replace_expected(path, OLD_VERSION, NEW_VERSION, 1)

release_doc = "docs/releases/local-business-classifier-v9.md"
Path(release_doc).write_text('''# Local business and hospitality classifier v9

This candidate adds a first-class local-business/hospitality archetype for bakeries, restaurants, wineries, tasting rooms, dairies, creameries, cafes, and related owner-operated businesses.

The classifier uses homepage identity, LocalBusiness-family structured data, and operating routes such as menu, visit, tasting, hours, catering, and reservations. Publisher dominance and catalog dominance remain counter-signals, so restaurant trade publications and bakery-supply ecommerce sites keep their existing archetypes.

Production acceptance controls: Hartzler Dairy, Lamanna Bakery, Norris Wines, Red Bamboo, Funbooker, and a retail control.
''', encoding="utf-8")

revision_path = Path("data/beta-crawler-revision.json")
revision = json.loads(revision_path.read_text(encoding="utf-8"))
revision["component_versions"]["archetype_classifier_version"] = NEW_VERSION
payload = json.dumps(revision["component_versions"], sort_keys=True, separators=(",", ":"))
fingerprint = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
revision["fingerprint"] = fingerprint
revision["acceptance_report"] = release_doc
revision["note"] = "Local-business classifier candidate: homepage identity, LocalBusiness-family schema and operating routes override incidental blog, booking and shop vocabulary while preserving publisher and catalog controls."
revision_path.write_text(json.dumps(revision, indent=2, sort_keys=True) + "\n", encoding="utf-8")

for path in [
    "src/lib/scanRunModel.js",
    "tests/frontend/scanRunPersistence.test.mjs",
    "tests/frontend/releaseAuthorityGate.test.mjs",
]:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    old_fingerprint = "664cceb4873e81a1"
    count = text.count(old_fingerprint)
    if count != 1:
        raise SystemExit(f"{path}: expected one old fingerprint, found {count}")
    target.write_text(text.replace(old_fingerprint, fingerprint, 1), encoding="utf-8")

print(f"classifier_version={NEW_VERSION}")
print(f"fingerprint={fingerprint}")
