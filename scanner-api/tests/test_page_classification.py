"""Regression tests for canonical page template classification."""

from app.extract import classify_template, estimate_intent


def test_no_funbooker_voir_is_standard():
    for path in ["/fr/annonce/a/voir", "/fr/annonce/b-c-1/voir", "/annonce/x/voir"]:
        assert classify_template(path) == "activity_detail"


def test_finance_and_lending_paths_stay_cohesive():
    for path in [
        "/pret-immobilier/garantie/voir-tout",
        "/credit-immobilier/calculatrice",
        "/loans/fix-and-flip",
        "/loan-overview",
        "/request-a-payoff",
        "/document-exchange",
    ]:
        assert classify_template(path) in {"loan_program", "conversion"}
        assert estimate_intent(path, "", "", 200) == "money_or_conversion"


def test_ecommerce_catalog_paths_are_canonical_families():
    assert classify_template("/products/surfboard") == "product_page"
    assert classify_template("/product/surfboard") == "product_page"
    assert classify_template("/produit/planche") == "product_page"
    assert classify_template("/collections/surfboards") == "collection_page"
    assert classify_template("/collection/surfboards") == "collection_page"
    assert classify_template("/category/surfboards") == "collection_page"


def test_route_boundaries_are_preserved():
    for path in ["/login", "/account", "/dashboard", "/Dashboard", "/cart", "/checkout", "/admin"]:
        assert classify_template(path) == "route_boundary"
        assert estimate_intent(path, "", "", 200) == "internal_or_auth"


def test_marketplace_and_local_page_families():
    assert classify_template("/fr/activite/paris") == "activity_detail"
    assert classify_template("/booking/checkout") == "route_boundary"
    assert classify_template("/agence/paris") == "location_landing"
    assert classify_template("/locations/austin") == "location_landing"
    assert classify_template("/privacy-policy") == "legal_info"
    assert classify_template("/contact") == "contact"
