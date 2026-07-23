"""Regression tests for canonical page template classification."""

from app.extract import classify_template, estimate_intent, extract_page


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


# --- Scanner/review split-brain + unbounded-token leaks (Funbooker live scan) ---

def test_locguenole_activity_page_is_not_legal():
    """Unbounded 'cgu' matched the letters inside 'domaine-de-lo(cgu)enole', demoting a public
    activity page to legal_info and spawning a 'Batch image descriptions on legal info pages' card."""
    path = "/fr/annonce/domaine-de-locguenole-a-kervignac-56/voir"
    assert classify_template(path) == "activity_detail"


def test_legal_tokens_must_be_bounded_segments():
    from app.extract import is_legal_page_path
    assert is_legal_page_path("/fr/page/cgu")
    assert is_legal_page_path("/cgv")
    assert is_legal_page_path("/mentions-legales")
    assert not is_legal_page_path("/fr/annonce/domaine-de-locguenole-a-kervignac-56/voir")
    assert not is_legal_page_path("/fr/annonce/legumes-du-terroir/voir")


def test_review_route_matcher_delegates_to_canonical_classifier():
    """review.py kept a second, weaker substring matcher that re-matched /cart inside /carte
    even after the scanner had correctly classified the page. One classifier, not two."""
    from app.review import is_route_boundary_candidate
    assert not is_route_boundary_candidate("/fr/carte-invitation-anniversaire")
    assert is_route_boundary_candidate("/cart")
    assert is_route_boundary_candidate("/checkout")
    assert is_route_boundary_candidate("/login")


def test_legal_pages_are_not_low_value_archives():
    """Generic '/page/' in LOW_VALUE_PATTERNS demoted /fr/page/cgu to a pagination archive."""
    from app.review import is_low_value_page
    assert not is_low_value_page("/fr/page/cgu")
    assert not is_low_value_page("/fr/page/mentions-legales")
    assert is_low_value_page("/blog/page/3")
    assert is_low_value_page("/tag/x")


def test_scanner_route_boundary_boolean_is_authoritative():
    """When the scanner supplies route_boundary_candidate, review must not recompute it."""
    from app.review import run_review
    pages = [{"final_url": "https://f.com/fr/carte-invitation-anniversaire", "status_code": 200,
              "h1_count": 1, "meta_description": "d",
              "canonical": "https://f.com/fr/carte-invitation-anniversaire",
              "route_boundary_candidate": False, "page_template_family": "standard"}]
    r = run_review({"website_url": "https://f.com", "pages": pages,
                    "scan_coverage": {"pages_found": 50, "pages_crawled": 1, "sampled_pages_sent_to_ai": 1}})
    titles = " ".join(str(f.get("issue_title", "")) for f in r["cleaned_fixes"]).lower()
    assert "route-boundary" not in titles


def _extract_for_classification(path, *, title, h1, schema_type=None):
    schema = (
        f'<script type="application/ld+json">{{"@type":"{schema_type}"}}</script>'
        if schema_type
        else ""
    )
    html = f"<html><head><title>{title}</title>{schema}</head><body><h1>{h1}</h1></body></html>"
    return extract_page(
        html,
        f"https://example.com{path}",
        f"https://example.com{path}",
        200,
        "text/html",
        {"discovered_from": ["sitemap"], "source_pages": ["/sitemap.xml"]},
    )


def test_pretto_service_page_is_not_legal_because_slug_contains_conditions():
    page = _extract_for_classification(
        "/notre-service/garantie-zero-conditions-suspensives",
        title="La Garantie Zéro Conditions Suspensives de Pretto",
        h1="La Garantie Zéro Conditions Suspensives, votre alliée pour négocier",
        schema_type="FAQPage",
    )
    assert page["page_template_family"] == "standard"
    assert page["estimated_page_intent"] == "money_or_conversion"


def test_editorial_gift_article_is_not_checkout():
    page = _extract_for_classification(
        "/proprietaire/demenagement/cadeaux-noel-proprietaire",
        title="Les meilleurs cadeaux de Noël pour un futur propriétaire",
        h1="Les meilleurs cadeaux de Noël pour un futur propriétaire",
        schema_type="Article",
    )
    assert page["page_template_family"] == "guide_article"
    assert page["estimated_page_intent"] == "support_content"


def test_editorial_real_estate_article_schema_beats_broad_immobilier_keyword():
    page = _extract_for_classification(
        "/acheteur-immobilier/pourquoi-moins-30-ans-achetent-immobilier",
        title="Immobilier : pourquoi les moins de 30 ans achètent encore ?",
        h1="Pourquoi les moins de 30 ans n'ont jamais autant acheté ?",
        schema_type="Article",
    )
    assert page["page_template_family"] == "guide_article"
    assert page["estimated_page_intent"] == "support_content"


def test_strong_finance_route_still_beats_article_schema():
    page = _extract_for_classification(
        "/courtier-credit/nos-expertises/pret-sci",
        title="Comment acheter en SCI en 2026 ?",
        h1="Comment obtenir un prêt immobilier avec une SCI ?",
        schema_type="Article",
    )
    assert page["page_template_family"] == "loan_program"
    assert page["estimated_page_intent"] == "money_or_conversion"


def test_pretto_brand_name_does_not_make_a_standard_page_money_intent():
    assert estimate_intent("/equipe", "L'équipe Pretto", "Nos experts", 200) == "standard"



def test_wordpress_author_admin_archive_is_public_archive_not_route_boundary():
    from app.extract import is_route_boundary, is_wordpress_author_archive
    from app.review import is_internal_app_route, is_route_boundary_candidate

    for path in ["/author/admin", "/author/admin/", "/author/admin/page/2/"]:
        assert is_wordpress_author_archive(path)
        assert not is_route_boundary(path)
        assert not is_route_boundary_candidate(path)
        assert not is_internal_app_route(path)
        assert classify_template(path) == "archive"
        assert estimate_intent(path, "Admin archive", "", 200) == "support_content"

    for path in ["/admin", "/wp-admin", "/account/admin", "/author/admin/settings"]:
        assert is_route_boundary(path)
