"""Regression tests for decisive business-model routing."""
from app.review import detect_business_model


def test_finance_archetype_is_regulated_not_booking():
    text = "https://pretto.fr/pret-immobilier reservez un rendez-vous avec un expert credit"
    assert detect_business_model(text, "finance_insurance_lead_gen") == "regulated_or_trust_lead_generation"


def test_booking_archetype_stays_booking():
    assert detect_business_model("/annonce/x/voir booking", "booking_experiences_marketplace") == "booking_or_reservation"


def test_ecommerce_archetype_is_catalog():
    assert detect_business_model("/products cart", "ecommerce_specialty_retail") == "catalog_or_ecommerce"


def test_generic_archetype_still_uses_text_heuristics():
    assert detect_business_model("/annonce/x/voir reservation", "content_site") == "booking_or_reservation"
    assert detect_business_model("/loans apply-now", "content_site") == "regulated_or_trust_lead_generation"
