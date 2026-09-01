"""Locale variants must not multiply structural classifier votes.

The route examples below come from the Standard 150 handoff, the 35-site audit
records, and the production-shaped controls already frozen elsewhere in this
suite. They are route fixtures, not claimed page captures: titles/descriptions
only state the business identity the fixture is testing.
"""

from app.review import build_site_fingerprint


def page(path: str, title: str = "", description: str = "", schema_types=None, host: str = "https://example.com") -> dict:
    return {
        "url": f"{host}{path}",
        "final_url": f"{host}{path}",
        "path": path,
        "status_code": 200,
        "content_type": "text/html",
        "title": title or path,
        "h1": title or path,
        "meta_description": description or title,
        "schema_types": schema_types or [],
        "word_count": 250,
        "indexable": True,
    }


def fingerprint(pages: list[dict], host: str = "https://example.com") -> dict:
    return build_site_fingerprint(
        {"website_url": host, "pages_found": len(pages), "pages_crawled": len(pages)},
        pages,
        host,
    )


def test_translated_copies_of_one_article_cast_one_structural_vote():
    # Exact failure shape from the A1 handoff: one ETF article published in
    # multiple markets was counted once per locale by review.py.
    pages = [
        page("/", "Business home"),
        page("/de-at/blog/etfs", "ETF article"),
        page("/en-at/blog/etfs", "ETF article"),
        page("/fr-be/blog/etfs", "ETF article"),
    ]

    signals = fingerprint(pages)["classification"]["structural_signals"]

    assert signals["article_route_pages"] == 1
    assert signals["classifier_html_route_pages"] == 4
    assert signals["normalized_structural_route_pages"] == 2


def test_twelve_genuinely_different_articles_still_cast_twelve_votes():
    pages = [page("/", "Publisher home")]
    pages += [page(f"/fr/blog/article-{index}", f"Article {index}") for index in range(12)]

    signals = fingerprint(pages)["classification"]["structural_signals"]

    assert signals["article_route_pages"] == 12
    assert signals["normalized_structural_route_pages"] == 13


def test_musement_shaped_marketplace_stays_booking_after_locale_collapse():
    pages = [
        page("/", "Things to do", "Book activities and tours"),
        page("/uk/gift", "Experience gifts"),  # observed in scan 6a959c18287e8b8c5b595ad1
        page("/us/barcelona", "Barcelona experiences"),  # observed in that scan
        page("/en/tickets/louvre", "Louvre tickets"),
        page("/fr/tickets/louvre", "Billets Louvre"),
        page("/en/attractions/eiffel-tower", "Eiffel Tower attraction"),
    ]
    assert fingerprint(pages)["primary_archetype"] == "booking_experiences_marketplace"


def test_tiqets_shaped_marketplace_stays_booking_after_locale_collapse():
    pages = [
        page("/", "Museum tickets and attractions", "Book museum tickets"),
        page("/cs/holiday-specials-pc199", "Holiday specials"),  # scan 6a959ca488c45275b250e19f
        page("/blog/landmarks-in-london", "London landmarks guide"),
        page("/en/tickets/colosseum", "Colosseum tickets"),
        page("/fr/tickets/colosseum", "Billets Colisée"),
        page("/en/attractions/prado", "Prado attraction"),
    ]
    assert fingerprint(pages)["primary_archetype"] == "booking_experiences_marketplace"


def test_pennylane_shaped_accounting_platform_is_not_outvoted_by_localized_guides():
    pages = [
        page("/", "Accounting software for growing companies", "Automate bookkeeping on one platform"),
        page("/fr/pricing-micro-entreprise-sans-tva", "Pricing"),  # scan 6a95a17e7e60e660ad7a9ccc
        page("/features/invoicing", "Automated invoicing"),
        page("/integrations/banks", "Bank integrations"),
    ]
    pages += [page(f"/{locale}/blog/accounting", "Accounting guide") for locale in ("fr", "de", "it", "es", "nl", "be")]

    result = fingerprint(pages)
    assert result["primary_archetype"] == "saas_app_membership"
    assert result["classification"]["structural_signals"]["article_route_pages"] == 1


def test_ikea_shaped_retailer_is_not_outvoted_by_localized_editorial_routes():
    pages = [
        page("/", "Furniture and home goods", "Shop furniture for delivery"),
        page("/cat/sofas", "Sofas"),
        page("/p/billy-bookcase", "BILLY bookcase", schema_types=["Product"]),
        page("/p/malm-bed", "MALM bed", schema_types=["Product"]),
        page("/global/en/newsroom/subscription", "Newsroom subscription"),  # scan 6a95a2634663773b7144c372
    ]
    pages += [page(f"/{locale}/blog/small-space-living", "Small-space guide") for locale in ("fr", "de", "it", "es")]

    assert fingerprint(pages)["primary_archetype"] == "ecommerce_specialty_retail"


def test_wise_shaped_money_transfer_business_uses_finance_identity_not_generic_saas():
    pages = [
        page("/", "Money transfer app", "International transfers and a multi-currency account"),
        page("/au/about/our-story", "Our story"),  # scan 6a95a093017e7cf9cc5bff11
        page("/br/about/our-story", "Nossa história"),
        page("/gb/import-duty/calculator", "Import duty calculator"),
        page("/au/features/auto-conversion", "Auto conversion"),
    ]

    result = fingerprint(pages)
    assert result["primary_archetype"] == "finance_insurance_lead_gen"
    assert result["finance_sub_playbook"] == "digital_bank"


def test_n26_shaped_digital_bank_keeps_its_specific_finance_playbook():
    pages = [
        page("/", "The mobile bank you'll love", "Open a bank account with a debit card"),
        page("/en-at/contact", "Contact"),  # scan 6a95a589c1d5cc150837c976
        page("/en-at/legal-documents/credit", "Credit legal documents"),
        page("/bank-account", "Bank account"),
        page("/cards", "Debit cards"),
    ]
    result = fingerprint(pages)
    assert result["primary_archetype"] == "finance_insurance_lead_gen"
    assert result["finance_sub_playbook"] == "digital_bank"


def test_alan_shaped_insurer_keeps_its_specific_finance_playbook():
    pages = [
        page("/", "Health insurance for your team", "Assurance santé for companies"),
        page("/coverage/v253437", "Coverage"),  # scan 6a95a5f1d928f084de6643f3
        page("/coverage/v23720-nc", "Coverage"),
        page("/fr-fr/assurance-sante/fonction-publique", "Assurance santé"),
    ]
    result = fingerprint(pages)
    assert result["primary_archetype"] == "finance_insurance_lead_gen"
    assert result["finance_sub_playbook"] == "insurance"
