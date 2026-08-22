from app.review import ARCHETYPE_CLASSIFIER_VERSION, run_review


def page(path, title, description=""):
    return {
        "url": f"https://example.com{path}",
        "final_url": f"https://example.com{path}",
        "status_code": 200,
        "title": title,
        "h1": title,
        "meta_description": description or title,
        "word_count": 250,
        "indexable": True,
        "page_template_family": "homepage" if path == "/" else "standard",
    }


def classify(pages):
    # Four unique HTML pages are sufficient for classification without making
    # any claim about crawl authority in this focused classifier fixture.
    result = run_review({
        "website_url": "https://example.com",
        "pages_found": len(pages),
        "pages_crawled": len(pages),
        "pages": pages,
    })
    return result["site_fingerprint"]


def test_member_led_wine_store_is_retail_not_local_hospitality():
    fingerprint = classify([
        page("/", "Buy wine online", "Member prices, wine cases, delivery and subscriptions"),
        page("/wines/red", "Red wines"),
        page("/wine/case-one", "Mixed wine case"),
        page("/membership", "Wine membership"),
    ])
    assert fingerprint["primary_archetype"] == "ecommerce_specialty_retail"
    assert fingerprint["classification"]["classifier_version"] == ARCHETYPE_CLASSIFIER_VERSION


def test_digital_bank_with_large_guides_surface_is_finance_not_publisher():
    fingerprint = classify([
        page("/", "The mobile bank", "Open a bank account and get a debit card"),
        page("/bank-account", "Bank account"),
        page("/cards", "Debit cards"),
        page("/guides/saving", "Guide to saving"),
        page("/guides/budgeting", "Budgeting guide"),
    ])
    assert fingerprint["primary_archetype"] == "finance_insurance_lead_gen"


def test_physical_winery_control_remains_local_hospitality():
    fingerprint = classify([
        page("/", "Family winery and vineyard", "Visit our tasting room"),
        page("/visit", "Visit the winery"),
        page("/tastings", "Book a tasting"),
        page("/vineyard", "Our vineyard"),
    ])
    assert fingerprint["primary_archetype"] == "local_business_hospitality"


def test_workshop_marketplace_routes_outrank_incidental_local_vocabulary():
    fingerprint = classify([
        page("/", "Book workshops with local artisans", "Choose an experience and reserve online"),
        page("/ateliers/ceramique-paris", "Ceramics workshop in Paris"),
        page("/workshops/leather-bag", "Make a leather bag"),
        page("/experiences/food-tasting", "Food tasting experience"),
    ])
    assert fingerprint["primary_archetype"] == "booking_experiences_marketplace"


def test_ticket_attraction_marketplace_is_booking_not_generic_retail():
    fingerprint = classify([
        page("/", "Tickets for museums and attractions", "Book tickets for your trip"),
        page("/attractions/louvre", "Louvre Museum tickets"),
        page("/tickets/colosseum", "Colosseum tickets"),
        page("/venues/sagrada-familia", "Sagrada Familia"),
    ])
    assert fingerprint["primary_archetype"] == "booking_experiences_marketplace"


def test_accounting_saas_with_guides_remains_saas():
    fingerprint = classify([
        page("/", "Accounting software for growing companies", "Automate bookkeeping on one platform"),
        page("/features/invoicing", "Automated invoicing"),
        page("/integrations/banks", "Bank integrations"),
        page("/pricing", "Plans and pricing"),
        page("/guides/vat", "VAT guide"),
        page("/guides/payroll", "Payroll guide"),
    ])
    assert fingerprint["primary_archetype"] == "saas_app_membership"


def test_greeting_card_store_is_not_finance_from_generic_card_routes():
    fingerprint = classify([
        page("/", "Greeting cards for every occasion", "Shop birthday and wedding cards"),
        page("/products/birthday-card", "Birthday card"),
        page("/products/wedding-card", "Wedding card"),
        page("/collections/cards", "All greeting cards"),
    ])
    assert fingerprint["primary_archetype"] == "ecommerce_specialty_retail"
