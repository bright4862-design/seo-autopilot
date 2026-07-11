import json
import re
from html import unescape
from urllib.parse import urljoin, urldefrag, urlparse

from bs4 import BeautifulSoup


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(str(value or ""))).strip()


def extract_links(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html or "", "lxml")
    links: list[dict] = []
    for anchor in soup.find_all("a", href=True):
        try:
            href, _ = urldefrag(urljoin(base_url, anchor.get("href", "")))
        except Exception:
            continue
        if not href:
            continue
        links.append({"href": href, "text": clean_text(anchor.get_text(" "))[:180]})
        if len(links) >= 2000:
            break
    return links


def extract_schema_types(soup: BeautifulSoup) -> list[str]:
    types: set[str] = set()

    def collect(value):
        if isinstance(value, list):
            for item in value:
                collect(item)
        elif isinstance(value, dict):
            item_type = value.get("@type")
            if isinstance(item_type, list):
                for entry in item_type:
                    types.add(str(entry))
            elif item_type:
                types.add(str(item_type))
            collect(value.get("@graph"))

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            collect(json.loads(script.string or ""))
        except Exception:
            continue
    return sorted(types)[:25]


def extract_page(html: str, url: str, final_url: str, status_code: int, content_type: str, discovery: dict, fetch_error: str = "") -> dict:
    soup = BeautifulSoup(html or "", "lxml")
    title = clean_text(soup.title.string if soup.title else "")
    meta_description = ""
    robots = ""
    canonical = ""

    meta_desc = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    if meta_desc:
        meta_description = clean_text(meta_desc.get("content", ""))

    meta_robots = soup.find("meta", attrs={"name": re.compile("^robots$", re.I)})
    if meta_robots:
        robots = clean_text(meta_robots.get("content", ""))

    canonical_tag = soup.find("link", attrs={"rel": lambda value: value and "canonical" in str(value).lower()})
    if canonical_tag:
        canonical = urljoin(final_url, canonical_tag.get("href", ""))

    h1s = [clean_text(h.get_text(" ")) for h in soup.find_all("h1") if clean_text(h.get_text(" "))]
    images = soup.find_all("img")
    missing_alt = sum(1 for img in images if not clean_text(img.get("alt", "")))
    schema_types = extract_schema_types(soup)
    visible_text = clean_text(soup.get_text(" "))
    word_count = len([w for w in visible_text.split(" ") if w])
    parsed = urlparse(final_url or url)
    path = parsed.path or "/"

    indexable = 200 <= status_code < 400 and "noindex" not in robots.lower()

    return {
        "url": url,
        "final_url": final_url or url,
        "path": path,
        "discovered_from": list(dict.fromkeys(discovery.get("discovered_from", []))),
        "source_pages": list(dict.fromkeys(discovery.get("source_pages", []))),
        "link_text_samples": list(dict.fromkeys(discovery.get("link_text_samples", [])))[:8],
        "url_confidence": classify_confidence(discovery, status_code),
        "url_suspicion_reasons": [],
        "route_boundary_candidate": is_route_boundary(path),
        "route_boundary_type": "route_boundary" if is_route_boundary(path) else "",
        "status_code": status_code,
        "fetch_error": fetch_error,
        "content_type": content_type,
        "title": title,
        "meta_description": meta_description,
        "h1": h1s[0] if h1s else "",
        "h1_count": len(h1s),
        "canonical": canonical,
        "canonical_url": canonical,
        "canonical_status": "self_or_equivalent" if canonical and same_path(final_url or url, canonical) else ("missing" if not canonical else "canonical_to_different_url"),
        "robots": robots,
        "robots_meta": robots,
        "robots_indexability_status": "indexable" if indexable else "not_indexable",
        "word_count": word_count,
        "html_size": len(html or ""),
        "image_count": len(images),
        "image_missing_alt_count": missing_alt,
        "missing_alt_image_count": missing_alt,
        "schema_types": schema_types,
        "has_schema": bool(schema_types),
        "indexable": indexable,
        "client_rendering_suspected": 200 <= status_code < 400 and word_count < 80 and ("id=\"root\"" in html or "id=\"app\"" in html),
        "page_template_family": classify_template(path),
        "estimated_page_intent": estimate_intent(path, title, h1s[0] if h1s else "", status_code),
    }


def classify_confidence(discovery: dict, status_code: int) -> str:
    sources = set(discovery.get("discovered_from", []))
    if "seed" in sources:
        return "confirmed_seed"
    if "sitemap" in sources and "internal_link" in sources:
        return "confirmed_sitemap_and_linked"
    if "sitemap" in sources:
        return "sitemap_listed"
    if "internal_link" in sources:
        return "linked_but_failed" if status_code >= 400 else "internally_linked"
    return "unknown_discovery"


ROUTE_BOUNDARY_RE = re.compile(
    # Token-bounded: a segment must BE the keyword, not merely start with it.
    # Unbounded "/cart" matched the French word "carte" (/fr/annonce/carte-all-inclusive.../voir),
    # flagging public activity pages as private internal routes.
    r"/(login|signin|sign-in|register|signup|sign-up|account|mon-compte|dashboard|cart|panier|checkout|billing|admin|wp-admin)(?=[/?#\s]|$)"
)


def is_route_boundary(path: str) -> bool:
    return bool(ROUTE_BOUNDARY_RE.search(str(path or "").lower().split("?")[0]))


SUPPORT_CONTENT_PREFIX_RE = re.compile(
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
    r"taux-immobilier/historique-taux-immobilier/20\d{2}(?:/|$)|"
    r"pret-immobilier/(?:conditions-credit-immobilier|remboursement-pret-immobilier)(?:/|$)"
    r")"
)


def is_support_content_path(path: str) -> bool:
    clean = str(path or "").lower().split("?")[0].split("#")[0].rstrip("/") or "/"
    return bool(SUPPORT_CONTENT_PREFIX_RE.match(clean) or SUPPORT_CONTENT_NESTED_RE.match(clean))


def classify_template(path: str) -> str:
    p = str(path or "").lower()
    clean = p.split("?")[0].split("#")[0].rstrip("/")
    if clean in ("", "/") or clean.count("/") == 0:
        return "homepage"
    if is_route_boundary(p):
        return "route_boundary"
    # /page/2 is pagination; /page/mentions-legales is a CMS page slug, not an archive.
    if any(x in p for x in ["/tag/", "/author/", "/archive/"]) or re.search(r"/page/\d+(/|$)", p):
        return "archive"
    # Support-content paths are guide_article regardless of money keywords in the slug.
    # Prefix-based (optionally locale-prefixed) so /blog/fix-and-flip-loans-... does NOT become loan_program,
    # while /pret-immobilier/guide-achat (not a /blog|/guide prefix) still classifies by its money path.
    if is_support_content_path(clean):
        return "guide_article"
    # Trust/legal documents, wherever the CMS puts them (/fr/page/mentions-legales, /cgu).
    if re.search(r"mentions-legales|mentions_legales|cgu|cgv|privacy|privacite|politique-de-confidentialite|terms|conditions-generales|legal-notice|impressum", clean):
        return "legal_info"
    # Category/theme/collection LANDING pages win over money-keyword rules: /fr/category/simulateur
    # is a listing of simulator experiences, not a calculator tool; /fr/theme/cadeau is a gift-ideas
    # landing page, not a checkout route.
    if re.search(r"^(/[a-z]{2}(-[a-z]{2})?)?/(category|categorie|catégorie|categories|theme|thème|collection|collections|marque|brand|univers)(/|$)", clean):
        return "collection_page"
    if re.search(r"/annonce/.*?/voir|/annonce/|/activite|/activité|/activity|/experience|/expérience|/atelier|/stage/|/pilotage", p):
        return "activity_detail"
    if re.search(r"/loans?/|/loan-overview|/fix-and-flip|/bridge|/rental|/dscr|/hard-money|pret|prêt|credit|crédit|immobilier|mortgage|hypotheque|hypothèque|rachat", p):
        return "loan_program"
    if re.search(r"/apply-now|/apply|/request-a-payoff|/document-exchange|/souscription|/devis|/quote|/signup|/demo|/contact-sales", p):
        return "conversion"
    if re.search(r"/calcul|/calculator|/simulateur|/simulation", p):
        return "calculator"
    if re.search(r"/comparateur|/compare|/versus|/vs-", p):
        return "comparison_page"
    if re.search(r"booking|reservation|réservation|ticket_order|gift_voucher|cadeau|coffret|billet|/ticket|/pass", p):
        return "booking_or_checkout"
    if re.search(r"/products?/|/produit/|/p/", p):
        return "product_page"
    if re.search(r"/collections?/|/category/|/categorie/|/catégorie/|/marque/|/brand/|listing", p):
        return "collection_page"
    if re.search(r"/locations?/|/agence|/ville/|/region/|/store-locator", p):
        return "location_landing"
    if any(x in p for x in ["guide", "blog", "article", "conseils", "actualites", "/faq", "question"]):
        return "guide_article"
    if any(x in p for x in ["privacy", "terms", "legal", "mentions-legales", "cgv", "conditions"]):
        return "legal_info"
    if "contact" in p:
        return "contact"
    return "standard"


def estimate_intent(path: str, title: str, h1: str, status_code: int) -> str:
    text = f"{path} {title} {h1}".lower()
    if status_code >= 400:
        return "blocked_access" if status_code == 429 else "failed"
    if is_route_boundary(path):
        return "internal_or_auth"
    if is_support_content_path(path):
        return "support_content"
    if re.search(r"devis|quote|pricing|tarif|contact|booking|reservation|checkout|product|produit|collection|category|simulation|simulateur|calcul|calculator|comparateur|demo|signup|pret|prêt|credit|crédit|annonce|voir|activite|activité|activity|experience|expérience|billet|ticket|stage|pass|loans?|apply-now|request-a-payoff|document-exchange|fix-and-flip|bridge|dscr|rental", text):
        return "money_or_conversion"
    if re.search(r"privacy|terms|legal|about|contact|security|mentions|cgu|cgv|conditions-generales|politique-de-confidentialite|impressum", text):
        return "trust_or_legal"
    if re.search(r"faq|guide|blog|article|question|conseils", text):
        return "support_content"
    return "standard"


def same_path(left: str, right: str) -> bool:
    try:
        l = urlparse(left)
        r = urlparse(right)
        return l.netloc == r.netloc and l.path.rstrip("/") == r.path.rstrip("/")
    except Exception:
        return False
