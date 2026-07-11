from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Anchor not found in {path}: {old[:180]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


extract = ROOT / "scanner-api/app/extract.py"
text = extract.read_text(encoding="utf-8")
replace_once(
    extract,
    '    indexable = 200 <= status_code < 400 and "noindex" not in robots.lower()\n\n    return {\n',
    '    indexable = 200 <= status_code < 400 and "noindex" not in robots.lower()\n    page_template_family = classify_template(path, title, h1s[0] if h1s else "", schema_types)\n\n    return {\n',
)
replace_once(
    extract,
    '        "page_template_family": classify_template(path),\n        "estimated_page_intent": estimate_intent(path, title, h1s[0] if h1s else "", status_code),\n',
    '        "page_template_family": page_template_family,\n        "estimated_page_intent": estimate_intent(\n            path, title, h1s[0] if h1s else "", status_code, page_template_family, schema_types\n        ),\n',
)

text = extract.read_text(encoding="utf-8")
start = text.index("def classify_template(path: str) -> str:\n")
end = text.index("\n\ndef same_path(left: str, right: str) -> bool:\n", start)
new_block = r'''ARTICLE_SCHEMA_TYPES = {
    "article",
    "newsarticle",
    "blogposting",
    "report",
    "scholarlyarticle",
}

STRONG_LOAN_PATH_RE = re.compile(
    r"^(/[a-z]{2}(-[a-z]{2})?)?/(?:"
    r"loans?(?:/|$)|loan-overview(?:/|$)|fix-and-flip(?:/|$)|bridge(?:/|$)|dscr(?:/|$)|hard-money(?:/|$)|"
    r"pret-immobilier/comparateur-credit-immobilier(?:/|$)|"
    r"courtier-credit/(?:nos-expertises|courtier-autour-de-moi)(?:/|$)|"
    r"taux-immobilier/cout-credit-immobilier(?:/|$)"
    r")"
)
BROAD_LOAN_SEGMENT_RE = re.compile(
    r"(^|/)(pret|prêt|credit|crédit|immobilier|mortgage|hypotheque|hypothèque|rachat)([-_/]|$)"
)
BOOKING_SEGMENT_RE = re.compile(
    r"(^|/)(booking|reservation|réservation|ticket|pass|cadeau|coffret|billet)(/|$)"
)
SERVICE_PATH_RE = re.compile(
    r"^(/[a-z]{2}(-[a-z]{2})?)?/(notre-service|our-service|our-services|services)(/|$)"
)


def has_article_schema(schema_types: list[str] | tuple[str, ...] | set[str] | None) -> bool:
    return any(str(value or "").lower() in ARTICLE_SCHEMA_TYPES for value in (schema_types or []))


def classify_template(
    path: str,
    title: str = "",
    h1: str = "",
    schema_types: list[str] | tuple[str, ...] | set[str] | None = None,
) -> str:
    """Classify structural templates first, then use article schema to break broad keyword ties."""
    p = str(path or "").lower()
    clean = p.split("?")[0].split("#")[0].rstrip("/") or "/"
    if clean in ("", "/") or clean.count("/") == 0:
        return "homepage"
    if is_route_boundary(p):
        return "route_boundary"
    if any(x in p for x in ["/tag/", "/author/", "/archive/"]) or re.search(r"/page/\d+(/|$)", p):
        return "archive"
    if is_support_content_path(clean):
        return "guide_article"
    if re.search(r"^(/[a-z]{2}(-[a-z]{2})?)?/(category|categorie|catégorie|categories|theme|thème|collection|collections|marque|brand|univers)(/|$)", clean):
        return "collection_page"
    if re.search(r"/annonce/.*?/voir|/annonce/|/activite|/activité|/activity|/experience|/expérience|/atelier|/stage/|/pilotage", p):
        return "activity_detail"
    if is_legal_page_path(clean):
        return "legal_info"

    # Strong structural routes win even when their pages also publish Article schema.
    if STRONG_LOAN_PATH_RE.search(clean):
        return "loan_program"
    if re.search(r"/apply-now|/apply(?:/|$)|/request-a-payoff|/document-exchange|/souscription|/devis|/quote|/signup|/demo|/contact-sales", p):
        return "conversion"
    if re.search(r"/calcul|/calculator|/simulateur|/simulation", p):
        return "calculator"
    if re.search(r"/comparateur|/compare|/comparer|/versus|/vs-", p):
        return "comparison_page"
    if re.search(r"/products?/|/produit/|/p/", p):
        return "product_page"
    if re.search(r"/collections?/|/category/|/categorie/|/catégorie/|/marque/|/brand/|listing", p):
        return "collection_page"
    if re.search(r"/locations?/|/agence|/ville/|/region/|/store-locator", p):
        return "location_landing"
    if re.search(r"(^|/)(contact|nous-contacter|contactez-nous)(/|$)", clean):
        return "contact"

    # Article/NewsArticle is stronger evidence than incidental commercial words in a long editorial slug.
    if has_article_schema(schema_types):
        return "guide_article"
    if BROAD_LOAN_SEGMENT_RE.search(clean):
        return "loan_program"
    if BOOKING_SEGMENT_RE.search(clean) or re.search(r"ticket[_-]order|gift[_-]voucher", clean):
        return "booking_or_checkout"
    if any(x in p for x in ["guide", "blog", "article", "conseils", "actualites", "/faq", "question"]):
        return "guide_article"
    return "standard"


MONEY_TEMPLATE_FAMILIES = {
    "homepage",
    "activity_detail",
    "booking_or_checkout",
    "conversion",
    "contact",
    "loan_program",
    "calculator",
    "comparison_page",
    "product_page",
    "collection_page",
    "location_landing",
}


def estimate_intent(
    path: str,
    title: str,
    h1: str,
    status_code: int,
    page_template_family: str = "",
    schema_types: list[str] | tuple[str, ...] | set[str] | None = None,
) -> str:
    if status_code >= 400:
        return "blocked_access" if status_code == 429 else "failed"
    if is_route_boundary(path):
        return "internal_or_auth"

    family = page_template_family or classify_template(path, title, h1, schema_types)
    if family in {"guide_article", "archive"}:
        return "support_content"
    if family == "legal_info":
        return "trust_or_legal"
    if family in MONEY_TEMPLATE_FAMILIES or SERVICE_PATH_RE.search(str(path or "").lower()):
        return "money_or_conversion"
    if has_article_schema(schema_types):
        return "support_content"

    text = f"{path} {title} {h1}".lower()
    if is_legal_page_path(path) or re.search(r"\b(privacy|terms|legal|about|security|mentions|cgu|cgv|impressum)\b", text):
        return "trust_or_legal"
    if is_support_content_path(path) or re.search(r"\b(faq|guide|blog|article|question|conseils|news)\b", text):
        return "support_content"
    if re.search(
        r"\b(devis|quote|pricing|tarif|contact|booking|reservation|checkout|product|produit|simulation|simulateur|calcul|calculator|comparateur|demo|signup|prêt|pret|crédit|credit|loan|loans|apply|bridge|dscr|rental)\b",
        text,
    ):
        return "money_or_conversion"
    return "standard"
'''
extract.write_text(text[:start] + new_block + text[end:], encoding="utf-8")

review = ROOT / "scanner-api/app/review.py"
replace_once(
    review,
    '        "business_importance": page_value["classification"],\n        "evidence_confidence": evidence_confidence,\n',
    '        "business_importance": page_value["classification"],\n        "is_low_value_page": is_low_value_page(page_url),\n        "is_important_business_page": fix.get("is_important_business_page") if isinstance(fix.get("is_important_business_page"), bool) else False,\n        "evidence_confidence": evidence_confidence,\n',
)

classification_tests = ROOT / "scanner-api/tests/test_page_classification.py"
text = classification_tests.read_text(encoding="utf-8")
text = text.replace(
    "from app.extract import classify_template, estimate_intent\n",
    "from app.extract import classify_template, estimate_intent, extract_page\n",
    1,
)
addition = r'''


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
'''
if "test_pretto_service_page_is_not_legal_because_slug_contains_conditions" not in text:
    classification_tests.write_text(text.rstrip() + addition + "\n", encoding="utf-8")

presentation_tests = ROOT / "scanner-api/tests/test_review_presentation_contract.py"
text = presentation_tests.read_text(encoding="utf-8")
addition = r'''


def test_authoritative_guide_group_explicitly_stamps_not_low_value():
    pages = [
        _page(f"/blog/article-{index}", "guide_article", meta_description="")
        for index in range(3)
    ]
    card = _fix(_run(pages), "missing_meta_description")

    assert card["page_template_family"] == "guide_article"
    assert card["is_low_value_page"] is False
    assert card["business_importance"] == "standard"
'''
if "test_authoritative_guide_group_explicitly_stamps_not_low_value" not in text:
    presentation_tests.write_text(text.rstrip() + addition + "\n", encoding="utf-8")
