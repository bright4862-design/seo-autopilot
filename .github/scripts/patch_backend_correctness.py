from pathlib import Path
import re


def sub1(text, pattern, replacement, label, flags=0):
    updated, count = re.subn(pattern, replacement, text, count=1, flags=flags)
    if count != 1:
        raise SystemExit(f"{label}: expected one match, found {count}")
    return updated


review_path = Path("scanner-api/app/review.py")
review = review_path.read_text(encoding="utf-8")
new_model = '''def detect_business_model(text: str, archetype: str) -> str:
    # Decisive archetypes must not be overridden by incidental page text.
    decisive = {
        "finance_insurance_lead_gen": "regulated_or_trust_lead_generation",
        "utilities_comparison_lead_gen": "regulated_or_trust_lead_generation",
        "booking_experiences_marketplace": "booking_or_reservation",
        "ecommerce_specialty_retail": "catalog_or_ecommerce",
    }
    if archetype in decisive:
        return decisive[archetype]
    if has_any(text, ["/annonce", "/voir", "booking", "reservation", "réservation", "availability", "calendar", "book now", "ticket", "stage", "pass", "cadeau", "loisir"]):
        return "booking_or_reservation"
    if has_any(text, ["/loans", "/loan", "apply-now", "fix-and-flip", "hard money", "bridge loan", "lending", "request-a-payoff"]):
        return "regulated_or_trust_lead_generation"
    if has_any(text, ["devis", "quote", "simulation", "simulateur", "calcul", "calculator", "comparateur", "compare"]):
        return "quote_or_comparison_lead_gen"
    if has_any(text, ["cart", "panier", "checkout", "sku", "product", "produit", "add to cart", "shopify"]):
        return "catalog_or_ecommerce"
    if has_any(text, ["login", "dashboard", "subscription", "billing", "admin"]):
        return "saas_or_member_app"
    return "content_or_general_business"


def detect_localization'''
review = sub1(review, r"def detect_business_model\(text: str, archetype: str\) -> str:\n.*?\n\ndef detect_localization", new_model, "business model", re.S)
review_path.write_text(review, encoding="utf-8")

Path("scanner-api/tests/test_business_model.py").write_text('''"""Regression tests for decisive business-model routing."""
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
''', encoding="utf-8")

extract_path = Path("scanner-api/app/extract.py")
extract = extract_path.read_text(encoding="utf-8")
helper = '''SUPPORT_CONTENT_PREFIX_RE = re.compile(
    r"^(/[a-z]{2}(-[a-z]{2})?)?/(blog|guide|guides|article|articles|faq|resources|ressources|news|actualites|conseils|help|support|learn|academy|glossary|glossaire)(/|$)"
)
SUPPORT_CONTENT_NESTED_RE = re.compile(
    r"^(/[a-z]{2}(-[a-z]{2})?)?/(?:"
    r"tendance-marche-immobilier(?:/|$)|"
    r"bien-immobilier/maison-ou-appartement(?:/|$)|"
    r"acheteur-immobilier/gestion-patrimoine(?:/|$)|"
    r"proprietaire/taxes-proprietaire(?:/|$)|"
    r"investissement-locatif/(?:location-immobiliere|loi-immobilier)(?:/|$)|"
    r"recherche-immobiliere/ou-acheter(?:/|$)|"
    r"taux-immobilier/historique-taux-immobilier/20\\d{2}(?:/|$)|"
    r"pret-immobilier/(?:conditions-credit-immobilier|remboursement-pret-immobilier)(?:/|$)"
    r")"
)


def is_support_content_path(path: str) -> bool:
    clean = str(path or "").lower().split("?")[0].split("#")[0].rstrip("/") or "/"
    return bool(SUPPORT_CONTENT_PREFIX_RE.match(clean) or SUPPORT_CONTENT_NESTED_RE.match(clean))


'''
if "SUPPORT_CONTENT_NESTED_RE" not in extract:
    extract = extract.replace("def classify_template(path: str) -> str:\n", helper + "def classify_template(path: str) -> str:\n", 1)
extract = sub1(extract, r'    if re\.match\(r"\^\(\/\[a-z\]\{2\}.*?\n        return "guide_article"', '    if is_support_content_path(clean):\n        return "guide_article"', "support route")
extract = extract.replace('    if is_route_boundary(text):\n        return "internal_or_auth"\n    if re.search(', '    if is_route_boundary(text):\n        return "internal_or_auth"\n    if is_support_content_path(path):\n        return "support_content"\n    if re.search(', 1)
extract_path.write_text(extract, encoding="utf-8")

test_path = Path("scanner-api/tests/test_page_classification.py")
tests = test_path.read_text(encoding="utf-8")
if "test_pretto_editorial_routes_override_finance_keywords" not in tests:
    tests += '''


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
'''
test_path.write_text(tests, encoding="utf-8")
