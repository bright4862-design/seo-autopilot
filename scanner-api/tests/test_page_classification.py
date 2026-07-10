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


def test_blog_slugs_with_money_words_are_guide_article():
    for path in [
        "/blog/bridge-loans-vs-traditional-loans-what-is-the-difference",
        "/blog/fix-and-flip-loans-vs-traditional-mortgages",
        "/blog/credit-card-use-strategies-for-real-estate-investing",
        "/fr/blog/simulation-de-pret-immobilier",
    ]:
        assert classify_template(path) == "guide_article"


def test_money_paths_outside_blog_prefix_are_unaffected():
    assert classify_template("/pret-immobilier/guide-achat") == "loan_program"
    assert classify_template("/loans/fix-and-flip") == "loan_program"
    assert classify_template("/apply-now") == "conversion"



def test_pretto_editorial_routes_override_finance_keywords():
    paths = [
        "/tendance-marche-immobilier/marche-immobilier-2026/taux-immobiliers-hausse-2026",
        "/bien-immobilier/maison-ou-appartement/acheter-un-souplex-conseils",
        "/acheteur-immobilier/gestion-patrimoine/patrimoine-immobilier-joueurs-psg",
        "/proprietaire/taxes-proprietaire/taxe-abri-de-jardin-baisse",
        "/investissement-locatif/location-immobiliere/faux-dossiers-location-marche-locatif",
        "/investissement-locatif/loi-immobilier/loi-boutin",
        "/recherche-immobiliere/ou-acheter/ou-acheter-maison-1-euro-sardaigne-avis",
        "/taux-immobilier/historique-taux-immobilier/2026/prevision-taux-immobilier-2027",
        "/pret-immobilier/conditions-credit-immobilier/comprendre-le-scoring-bancaire",
        "/pret-immobilier/remboursement-pret-immobilier/capital-restant-du",
    ]
    for path in paths:
        assert classify_template(path) == "guide_article"
        assert estimate_intent(path, "", "", 200) == "support_content"


def test_pretto_money_routes_remain_money_templates():
    paths = [
        "/pret-immobilier/comparateur-credit-immobilier/pret-immobilier-bnp-paribas",
        "/courtier-credit/nos-expertises/pret-medecin",
        "/courtier-credit/courtier-autour-de-moi/ile-de-france/paris",
    ]
    for path in paths:
        assert classify_template(path) == "loan_program"
        assert estimate_intent(path, "", "", 200) == "money_or_conversion"
