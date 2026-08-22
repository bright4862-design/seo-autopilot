"""Production regressions for structural, multilingual page-family inference."""

from app.extract import classify_template


def test_experience_simulator_is_not_a_financial_calculator():
    assert (
        classify_template(
            "/fr/coffrets-cadeaux/simulateur-chute-libre",
            "Simulateur de chute libre",
            "Vivez une expérience de chute libre",
        )
        == "activity_detail"
    )


def test_marketplace_listing_show_route_is_an_activity_detail():
    assert classify_template("/fr/listing/escape-game-paris/show") == "activity_detail"


def test_incidental_listing_text_is_not_a_collection_route():
    assert classify_template("/guides/blacklisting-and-email-delivery") == "guide_article"


def test_employment_guidance_with_activite_is_editorial():
    assert (
        classify_template(
            "/fr/ressources/activite-partielle-employeur",
            "Activité partielle : guide employeur",
            "Comprendre l'activité partielle",
            ["Article"],
        )
        == "guide_article"
    )


def test_glossary_slug_with_activite_is_editorial():
    assert classify_template("/fr/glossaire/activite-professionnelle") == "guide_article"


def test_credit_card_insurance_is_not_a_loan_program():
    assert classify_template("/travel-insurance/credit-card-insurance") == "standard"


def test_garden_project_with_location_word_is_not_a_location_landing():
    assert classify_template("/idees-conseils/jardin/location-materiel-jardin") != "location_landing"


def test_marketplace_product_route_is_a_product_page():
    for path in (
        "/marketplace/product/perceuse-sans-fil",
        "/marketplace/produit/tondeuse-electrique",
    ):
        assert classify_template(path) == "product_page"


def test_real_calculator_and_location_routes_remain_structural():
    assert classify_template("/calculator/mortgage") == "calculator"
    assert classify_template("/fr/simulateur") == "calculator"
    assert classify_template("/locations/paris") == "location_landing"
    assert classify_template("/fr/agence/lyon") == "location_landing"
