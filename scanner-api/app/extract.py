import json
import re
from html import unescape
from typing import Any, Mapping
from urllib.parse import urljoin, urldefrag, urlparse

from bs4 import BeautifulSoup

from .market_scope import strip_market_locale_prefix
from .page_evidence_gate import PAGE_EVIDENCE_GATE_VERSION, classify_page_evidence
from .metadata_title_evidence import (
    METADATA_EVIDENCE_VERSION,
    TITLE_EVIDENCE_VERSION,
    describe_meta_description,
    estimate_title_pixel_width,
    is_generic_fallback_title,
    title_width_state,
)


CANONICAL_HREF_RESOLUTION_VERSION = "canonical_href_resolution_v2_absolute_single_label_same_path"


def _canonical_path_key(value: str) -> str:
    path = str(value or "/").split("?", 1)[0].split("#", 1)[0]
    return path.rstrip("/") or "/"


def _repair_single_label_same_path(base_url: str, raw: str) -> str:
    """Return the final page URL for a malformed single-label same-page href."""
    candidate = urlparse(raw)
    base = urlparse(str(base_url or ""))
    hostname = (candidate.hostname or "").lower().strip(".")
    if not hostname or "." in hostname:
        return ""
    if candidate.username or candidate.password or candidate.port is not None:
        return ""
    if candidate.netloc.lower().strip(".") != hostname:
        return ""
    if candidate.scheme and candidate.scheme.lower() not in {"http", "https"}:
        return ""
    if candidate.scheme and candidate.path not in {"", "/"}:
        return ""
    reconstructed_path = f"/{hostname}{candidate.path or ''}"
    if candidate.query != base.query:
        return ""
    if _canonical_path_key(reconstructed_path) != _canonical_path_key(base.path or "/"):
        return ""
    return base._replace(
        path=base.path or "/",
        query=base.query,
        fragment=candidate.fragment,
    ).geturl()


def resolve_canonical_href(base_url: str, href: str) -> str:
    """Resolve canonicals while repairing only exact same-page malformed hosts.

    Two malformed forms have appeared in production: ``//slug/`` and
    ``http://slug``. Both normally parse as a host. They are repaired only when
    the host is a plain single label and rebuilding it as a path exactly matches
    the final page path. Dotted or different-path external domains retain normal
    URL semantics and remain eligible for cross-domain validation.
    """
    raw = str(href or "").strip()
    if not raw:
        return ""
    candidate = urlparse(raw)
    is_scheme_relative = raw.startswith("//")
    is_absolute_http = candidate.scheme.lower() in {"http", "https"} and bool(candidate.netloc)
    if is_scheme_relative or is_absolute_http:
        repaired = _repair_single_label_same_path(base_url, raw)
        if repaired:
            return repaired
    return urljoin(base_url, raw)


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(str(value or ""))).strip()


APP_SHELL_MARKERS = (
    ("react_root", re.compile(r"<[^>]+\bid\s*=\s*(['\"])root\1", re.I)),
    ("generic_app_root", re.compile(r"<[^>]+\bid\s*=\s*(['\"])app\1", re.I)),
    ("next_root", re.compile(r"<[^>]+\bid\s*=\s*(['\"])__next\1", re.I)),
    ("nuxt_root", re.compile(r"<[^>]+\bid\s*=\s*(['\"])__nuxt\1", re.I)),
)

CRAWLER_ROBOTS_NAMES = {
    "googlebot",
    "googlebot-news",
    "googlebot-image",
    "bingbot",
    "slurp",
    "yandex",
    "baiduspider",
    "duckduckbot",
}


def client_rendering_signals(html: str, status_code: int, word_count: int) -> list[str]:
    """Return bounded structural evidence that a successful page is a thin app shell."""
    if not (200 <= int(status_code or 0) < 400) or int(word_count or 0) >= 80:
        return []
    source = str(html or "")
    return [label for label, pattern in APP_SHELL_MARKERS if pattern.search(source)][:4]


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


def extract_page(
    html: str,
    url: str,
    final_url: str,
    status_code: int,
    content_type: str,
    discovery: dict,
    fetch_error: str = "",
    response_headers: Mapping[str, Any] | None = None,
) -> dict:
    soup = BeautifulSoup(html or "", "lxml")
    title = clean_text(soup.title.string if soup.title else "")
    metadata_evidence = describe_meta_description(
        soup, html, status_code, content_type, fetch_error
    )
    meta_description = clean_text(metadata_evidence.get("selected_value", ""))
    robots = ""
    canonical = ""

    meta_directives: dict[str, list[str]] = {}
    for meta in soup.find_all("meta", attrs={"name": True}):
        name = clean_text(meta.get("name", "")).lower()
        if name != "robots" and name not in CRAWLER_ROBOTS_NAMES:
            continue
        directives = parse_robots_directives(meta.get("content", ""))
        if directives:
            meta_directives[name] = merge_directives(meta_directives.get(name, []), directives)
    robots = ", ".join(meta_directives.get("robots", []))

    x_robots_values = header_values(response_headers, "x-robots-tag")
    x_robots_directives = parse_x_robots_tag(x_robots_values)

    canonical_tag = soup.find("link", attrs={"rel": lambda value: value and "canonical" in str(value).lower()})
    if canonical_tag:
        canonical = resolve_canonical_href(final_url, canonical_tag.get("href", ""))

    h1s = [clean_text(h.get_text(" ")) for h in soup.find_all("h1") if clean_text(h.get_text(" "))]
    images = soup.find_all("img")
    missing_alt = sum(1 for img in images if not clean_text(img.get("alt", "")))
    schema_types = extract_schema_types(soup)
    visible_text = clean_text(soup.get_text(" "))
    word_count = len([w for w in visible_text.split(" ") if w])
    parsed = urlparse(final_url or url)
    path = parsed.path or "/"

    effective_search_directives = merge_directives(
        meta_directives.get("robots", []),
        meta_directives.get("googlebot", []),
        x_robots_directives.get("robots", []),
        x_robots_directives.get("googlebot", []),
    )
    noindexed = "noindex" in effective_search_directives or "none" in effective_search_directives
    indexable = 200 <= status_code < 300 and not fetch_error and not noindexed
    indexability_state = classify_indexability_state(status_code, fetch_error, noindexed)
    page_template_family = classify_template(path, title, h1s[0] if h1s else "", schema_types)

    rendering_signals = client_rendering_signals(html, status_code, word_count)
    page_evidence_class = classify_page_evidence(
        status_code=status_code,
        content_type=content_type,
        fetch_error=fetch_error,
        html=html,
    )

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
        "page_evidence_class": page_evidence_class,
        "evidence_gate_version": PAGE_EVIDENCE_GATE_VERSION,
        "title": title,
        "title_pixel_width_estimate": estimate_title_pixel_width(title),
        "title_width_state": title_width_state(title),
        "title_is_generic_fallback": is_generic_fallback_title(title),
        "title_evidence_version": TITLE_EVIDENCE_VERSION,
        "meta_description": meta_description,
        "meta_description_state": metadata_evidence.get("state"),
        "meta_description_element_count": metadata_evidence.get("element_count", 0),
        "meta_description_values": metadata_evidence.get("values", []),
        "meta_description_duplicate": metadata_evidence.get("duplicate", False),
        "metadata_evidence_version": METADATA_EVIDENCE_VERSION,
        "h1": h1s[0] if h1s else "",
        "h1_count": len(h1s),
        "canonical": canonical,
        "canonical_url": canonical,
        "canonical_href_resolution_version": CANONICAL_HREF_RESOLUTION_VERSION,
        "canonical_status": "self_or_equivalent" if canonical and same_path(final_url or url, canonical) else ("missing" if not canonical else "canonical_to_different_url"),
        "robots": robots,
        "robots_meta": robots,
        "robots_meta_directives": meta_directives,
        "googlebot_robots": ", ".join(meta_directives.get("googlebot", [])),
        "crawler_specific_robots": {
            name: directives for name, directives in meta_directives.items() if name != "robots"
        },
        "x_robots_tag": ", ".join(x_robots_values),
        "x_robots_tag_directives": x_robots_directives,
        "effective_search_robots_directives": effective_search_directives,
        "robots_indexability_status": indexability_state.lower().replace(" ", "_"),
        "indexability_state": indexability_state,
        "word_count": word_count,
        "html_size": len(html or ""),
        "image_count": len(images),
        "image_missing_alt_count": missing_alt,
        "missing_alt_image_count": missing_alt,
        "schema_types": schema_types,
        "has_schema": bool(schema_types),
        "indexable": indexable,
        "client_rendering_suspected": bool(rendering_signals),
        "client_rendering_signals": rendering_signals,
        "page_template_family": page_template_family,
        "estimated_page_intent": estimate_intent(
            path, title, h1s[0] if h1s else "", status_code, page_template_family, schema_types
        ),
    }


def parse_robots_directives(value: Any) -> list[str]:
    directives: list[str] = []
    for item in re.split(r"[,;]", clean_text(value).lower()):
        directive = clean_text(item)
        if directive and directive not in directives:
            directives.append(directive)
    return directives


def merge_directives(*groups: list[str]) -> list[str]:
    merged: list[str] = []
    for group in groups:
        for directive in group:
            if directive not in merged:
                merged.append(directive)
    return merged


def header_values(headers: Mapping[str, Any] | None, name: str) -> list[str]:
    if not headers:
        return []
    wanted = name.lower()
    value = next((value for key, value in headers.items() if str(key).lower() == wanted), None)
    if value is None:
        return []
    values = value if isinstance(value, (list, tuple)) else [value]
    return [clean_text(item) for item in values if clean_text(item)]


def parse_x_robots_tag(values: list[str]) -> dict[str, list[str]]:
    parsed: dict[str, list[str]] = {}
    for value in values:
        current_agent = "robots"
        for item in re.split(r"[,;]", clean_text(value)):
            token = clean_text(item).lower()
            if not token:
                continue
            agent_match = re.match(r"^([a-z][a-z0-9_-]*):\s*(.+)$", token)
            if agent_match and agent_match.group(1) in CRAWLER_ROBOTS_NAMES | {"robots"}:
                current_agent = agent_match.group(1)
                token = clean_text(agent_match.group(2))
            if token:
                parsed[current_agent] = merge_directives(parsed.get(current_agent, []), [token])
    return parsed


def classify_indexability_state(status_code: int, fetch_error: str, noindexed: bool) -> str:
    if fetch_error or status_code <= 0:
        return "Unknown because of access or rendering limitations"
    if 300 <= status_code < 400:
        return "Redirected"
    if status_code >= 400:
        return "Failed"
    if noindexed:
        return "Noindexed"
    if 200 <= status_code < 300:
        return "Indexable"
    return "Unknown because of access or rendering limitations"


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


ROUTE_BOUNDARY_CLASSIFIER_VERSION = "route_boundary_classifier_v2_wordpress_author_archives"
ROUTE_BOUNDARY_RE = re.compile(
    # Token-bounded: a segment must BE the keyword, not merely start with it.
    # Unbounded "/cart" matched the French word "carte" (/fr/annonce/carte-all-inclusive.../voir),
    # flagging public activity pages as private internal routes.
    r"/(login|signin|sign-in|register|signup|sign-up|account|mon-compte|dashboard|cart|panier|checkout|billing|admin|wp-admin)(?=[/?#\s]|$)"
)
WORDPRESS_AUTHOR_ARCHIVE_RE = re.compile(r"^/author/[^/?#]+(?:/page/\d+)?/?$")


def is_wordpress_author_archive(path: str) -> bool:
    clean = str(path or "").lower().split("?")[0].split("#")[0]
    return bool(WORDPRESS_AUTHOR_ARCHIVE_RE.fullmatch(clean))


def is_route_boundary(path: str) -> bool:
    clean = str(path or "").lower().split("?")[0].split("#")[0]
    if is_wordpress_author_archive(clean):
        return False
    return bool(ROUTE_BOUNDARY_RE.search(clean))


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


LEGAL_PAGE_RE = re.compile(
    # Bounded: multi-word legal slugs match anywhere, but short tokens (cgu/cgv/legal/terms)
    # must be a complete path segment. Unbounded "cgu" matched "domaine-de-lo(cgu)enole".
    r"(mentions-legales|mentions_legales|politique-de-confidentialite|privacy-policy|privacy_policy"
    r"|conditions-generales|conditions-generales-de-vente|legal-notice|terms-of-service|terms-and-conditions"
    r"|terms-of-use|privacy|impressum)"
    r"|(^|/)(cgu|cgv|legal|terms|mentions|privacite)(/|$)"
)


def is_legal_page_path(path: str) -> bool:
    return bool(LEGAL_PAGE_RE.search(str(path or "").lower().split("?")[0]))


ARTICLE_SCHEMA_TYPES = {
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
    localized = strip_market_locale_prefix(clean).rstrip("/") or "/"
    if localized in ("", "/") or localized.count("/") == 0:
        return "homepage"
    if is_route_boundary(p):
        return "route_boundary"
    if any(x in p for x in ["/tag/", "/author/", "/archive/"]) or re.search(r"/page/\d+(/|$)", p):
        return "archive"
    if is_support_content_path(localized):
        return "guide_article"
    if re.search(r"^/(category|categorie|catégorie|categories|cat|theme|thème|collection|collections|marque|brand|univers)(/|$)", localized):
        return "collection_page"
    if re.search(r"/annonce/.*?/voir|/annonce/|/activite|/activité|/activity|/experience|/expérience|/atelier|/stage/|/pilotage", localized):
        return "activity_detail"
    if is_legal_page_path(localized):
        return "legal_info"

    # Strong structural routes win even when their pages also publish Article schema.
    if STRONG_LOAN_PATH_RE.search(localized):
        return "loan_program"
    if re.search(r"/apply-now|/apply(?:/|$)|/request-a-payoff|/document-exchange|/souscription|/devis|/quote|/signup|/demo|/contact-sales", localized):
        return "conversion"
    if re.search(r"/comparateur|/compare|/comparer|/versus|/vs-", localized):
        return "comparison_page"
    if re.search(r"/products?/|/produit/|/p/", localized):
        return "product_page"
    if re.search(r"/collections?/|/category/|/categorie/|/catégorie/|/cat/|/marque/|/brand/|listing", localized):
        return "collection_page"
    if re.search(r"/locations?/|/agence|/ville/|/region/|/store-locator", localized):
        return "location_landing"
    if re.search(r"(^|/)(contact|contact-us|nous-contacter|contactez-nous)(/|$)", localized):
        return "contact"

    # Article/NewsArticle is stronger evidence than incidental commercial words in a long editorial slug.
    if has_article_schema(schema_types):
        return "guide_article"
    if BROAD_LOAN_SEGMENT_RE.search(localized):
        return "loan_program"
    if re.search(r"/calcul|/calculator|/simulateur|/simulation", localized):
        return "calculator"
    if BOOKING_SEGMENT_RE.search(localized) or re.search(r"ticket[_-]order|gift[_-]voucher", localized):
        return "booking_or_checkout"
    if any(x in localized for x in ["guide", "blog", "article", "conseils", "actualites", "/faq", "question"]):
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


def same_path(left: str, right: str) -> bool:
    try:
        l = urlparse(left)
        r = urlparse(right)
        return l.netloc == r.netloc and l.path.rstrip("/") == r.path.rstrip("/")
    except Exception:
        return False
