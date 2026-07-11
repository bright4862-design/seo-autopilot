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


# Funbooker live classifier false positives exposed once balanced sampling worked.
def test_french_carte_is_not_a_cart_route_boundary():
    """The French word 'carte' must not match the /cart route segment."""
    for path in [
        "/fr/annonce/carte-all-inclusive-lyon-city-card-69/voir",
        "/fr/annonce/carte-1-an-descapades-lyon-city-card-365-69/voir",
    ]:
        assert classify_template(path) == "activity_detail"
        assert estimate_intent(path, "", "", 200) != "internal_or_auth"


def test_public_invitation_page_is_not_internal():
    path = "/fr/carte-invitation-anniversaire"
    assert classify_template(path) != "route_boundary"
    assert estimate_intent(path, "", "", 200) != "internal_or_auth"


def test_real_cart_and_checkout_routes_still_detected():
    for path in ["/cart", "/fr/panier", "/checkout", "/login", "/account", "/dashboard", "/admin", "/en/cart/"]:
        assert classify_template(path) == "route_boundary"
        assert estimate_intent(path, "", "", 200) == "internal_or_auth"


def test_category_landing_pages_are_collections_not_calculators():
    """Simulator experience categories are listings, not calculator tools."""
    for path in [
        "/fr/category/simulateur",
        "/fr/category/simulateur-de-pilotage",
        "/fr/category/simulateur-de-vol/lyon",
    ]:
        assert classify_template(path) == "collection_page"


def test_theme_landing_page_is_a_collection_not_checkout():
    assert classify_template("/fr/theme/cadeau") == "collection_page"


def test_cms_legal_pages_are_legal_info_not_archive():
    """CMS page slugs must not be swallowed by the numbered pagination rule."""
    for path in ["/fr/page/mentions-legales", "/fr/page/cgu", "/mentions-legales", "/cgv"]:
        assert classify_template(path) == "legal_info"
        assert estimate_intent(path, "", "", 200) == "trust_or_legal"


def test_numbered_pagination_is_still_archive():
    for path in ["/page/2", "/blog/page/3", "/tag/x", "/author/y"]:
        assert classify_template(path) == "archive"
