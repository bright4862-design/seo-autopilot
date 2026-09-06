from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Any
from urllib.parse import urlparse

from .coverage_authority import assess_coverage, coverage_inputs_from_payload
from .repair_coverage import REPAIR_COVERAGE_VERSION, evidence_url_key, normalize_repair_scope
from .repair_dedup import (  # re-exported: callers and tests import these from review
    FAILURE_EVIDENCE_DEDUP_VERSION,
    GENERATOR_GROUP_SOURCES,
    GROUP_CARD_MIN_AFFECTED,
    failure_remediation_family,
    fix_dedup_class,
    suppress_duplicate_group_cards,
    suppress_group_covered_singletons,
)
from .review_primitives import clean_path, dedupe_strings, has_any, int_or_zero
from .page_evidence_gate import (
    PAGE_EVIDENCE_GATE_VERSION,
    page_evidence_class,
    page_has_usable_html,
)
from .market_scope import strip_market_locale_prefix
from .location_template_content import build_location_template_raw_fixes

REVIEW_VERSION = "python_review_v2_structural_marketplace"
SCORING_MODEL = "python_review_v2_group_dedup"
ZERO_FIX_CONFIDENCE_VERSION = "python_review_v3_zero_fix_confidence"
ZERO_FIX_HEALTH_GRADE = "No issues found in sample"
QUALITY_GATE_VERSION = "review_quality_gate_v3_shared_coverage_decision"
GROUPED_RECOMMENDATION_EVIDENCE_VERSION = "grouped_recommendation_evidence_v1_metadata_states"
ORPHAN_ASSET_EVIDENCE_VERSION = "orphan_asset_evidence_v1"

INCOMPLETE_REVIEW_WARNING = "Review received scan metadata, but no page evidence was passed into AI Review."
SUPPORT_RECLASS_FAMILIES = {"loan_program", "conversion", "standard", "guide", "category_listing", "qa", "product_detail", ""}

LOW_VALUE_PATTERNS = [
    "/actualites/", "/news/", "/archive/", "/archives/", "/tag/", "/tags/",
    "/author/", "/feed/", "/rss/", "?tag=", "&tag=",
]
TRUST_PATHS = [
    "/about", "/about-us", "/contact", "/privacy", "/privacy-policy", "/terms",
    "/terms-of-service", "/security", "/legal", "/mentions-legales", "/cgv", "/conditions",
]
INTERNAL_ROUTE_PATTERNS = [
    "/admin", "/developer", "/assistant", "/billing", "/login", "/register",
    "/forgot-password", "/reset-password", "/dashboard", "/issues", "/reports",
    "/crawl-status", "/metadata", "/canonicals", "/redirects", "/js-rendering",
    "/competitors", "/account", "/my-account", "/cart", "/checkout",
]

CATEGORY_MAP = {
    "broken_page": "404_error",
    "404_error": "404_error",
    "410_error": "404_error",
    "server_error": "web_dev",
    "blocked_page": "web_dev",
    "blocked_page_429": "web_dev",
    "scanner_blocked": "web_dev",
    "rate_limited_page": "web_dev",
    "site_access_limited": "web_dev",
    "canonical_missing": "canonical",
    "missing_canonical": "canonical",
    "canonical_to_other_domain": "canonical",
    "canonical_to_other_url": "canonical",
    "duplicate_route_casing": "canonical",
    "route_boundary_candidate_indexable": "indexability",
    "internal_route_indexable": "indexability",
    "missing_trust_pages": "schema",
    "trust_signal_gap": "schema",
    "schema": "schema",
    "structured_data": "schema",
    "image_alt_text": "image_alt_text",
    "missing_image_alt": "image_alt_text",
    "missing_h1": "thin_content",
    "multiple_h1": "thin_content",
    "missing_meta_description": "meta_description",
    "empty_meta_description": "meta_description",
    "malformed_meta_description": "meta_description",
    "meta_description_unusable": "meta_description",
    "title_over_pixel_limit": "meta_title",
    "generic_fallback_title": "meta_title",
    "duplicate_title_localized": "duplicate_content",
    "duplicate_title_query_variants": "duplicate_content",
    "duplicate_title_template": "duplicate_content",
    "missing_title": "meta_title",
    "duplicate_title": "duplicate_content",
    "duplicate_meta_description": "duplicate_content",
}

ARCHETYPE_CLASSIFIER_VERSION = "archetype_classifier_v12_locale_normalized_structural_routes"

# Frequency cap for archetype keyword/pattern counting: template volume
# (hundreds of /blog/ URLs) must not out-vote company-level evidence.
KEYWORD_COUNT_CAP = 5
# Ceiling applied to content_blog when strong structural SaaS/ecommerce
# evidence exists — big blogs stay secondary, not primary.
CONTENT_BLOG_STRUCTURAL_CAP = 8.0

# Route patterns that only exist when a business actually operates the model.
SAAS_STRUCTURAL_PATTERNS = (
    "/pricing", "/free-trial", "/trial", "/contact-sales", "/enterprise",
    "/features", "/integrations", "/use-cases", "/solutions",
    "/customers", "/customer-stories", "/case-studies", "/login", "/signin",
    "/signup", "/register", "/demo", "/docs", "/api", "/developers",
    "/platform", "/apps", "/download", "/payments", "/billing",
    "/connect", "/radar", "/terminal", "/issuing", "/treasury",
    "/tax", "/identity", "/atlas", "/financial-connections",
)
ECOMMERCE_STRUCTURAL_PATTERNS = (
    "/products/", "/product/", "/produit/", "/collections/", "/collection/",
    "/categorie/", "/cat/", "/p/", "/cart", "/checkout",
    "/basket", "/shop/", "/boutique/", "/store/", "/wines/", "/wine/",
    "/membership", "/members/", "/subscription",
)
PRODUCT_DETAIL_PATTERNS = (
    "/products/", "/product/", "/produit/", "/p/", "/itm/", "/buy/",
    "/wine/", "/wines/",
)
ARTICLE_ROUTE_PATTERNS = (
    "/blog/", "/travel-blog/", "/travel-blogs/", "/article/", "/articles/",
    "/news/", "/stories/", "/story/", "/guides/", "/guide/",
    "/travel-guides/", "/destinations/", "/ideas/", "/inspiration/",
    "/resources/", "/category/", "/glossary/", "/beginners-guide/",
    "/tutorial/", "/tutorials/", "/how-to/",
)
SAAS_CORE_IDENTITY_PATTERNS = (
    "/pricing", "/free-trial", "/trial", "/contact-sales", "/enterprise",
    "/features", "/integrations", "/use-cases", "/solutions", "/customers",
    "/customer-stories", "/case-studies", "/login", "/signin", "/signup",
    "/register", "/demo", "/api", "/developers", "/platform", "/apps",
    "/download", "/payments", "/billing", "/connect", "/radar",
    "/terminal", "/issuing", "/treasury", "/tax", "/identity",
    "/atlas", "/financial-connections",
)
SAAS_BUSINESS_FAMILY_PATTERNS = (
    ("product", ("/features", "/platform", "/apps", "/download", "/payments",
                 "/billing", "/connect", "/radar", "/terminal", "/issuing",
                 "/treasury", "/tax", "/identity", "/atlas",
                 "/financial-connections")),
    ("commercial", ("/pricing", "/free-trial", "/trial", "/demo", "/contact-sales", "/enterprise")),
    ("adoption", ("/integrations", "/use-cases", "/solutions", "/customers", "/customer-stories", "/case-studies")),
    ("access", ("/login", "/signin", "/signup", "/register")),
    ("developer", ("/docs", "/api", "/developers")),
)
APP_DISTRIBUTION_PLATFORM_PATTERNS = (
    "/download/android", "/download/ios", "/download/windows",
    "/download/macos", "/download/linux",
)
PLATFORM_PRODUCT_PATTERNS = (
    "/payments", "/billing", "/connect", "/radar", "/terminal",
    "/issuing", "/treasury", "/tax", "/identity", "/atlas",
    "/financial-connections",
)
NONPROFIT_STRUCTURAL_PATTERNS = (
    "/donate", "/donation", "/give", "/fundraise", "/fundraiser",
    "/fundraising", "/campaign", "/projects/", "/our-projects/", "/impact",
    "/where-we-work", "/world-changers", "/tiny-heroes", "/the-spring-series/",
)
NON_HTML_ASSET_EXTENSIONS = (
    ".avif", ".bmp", ".css", ".csv", ".doc", ".docx", ".eot", ".gif",
    ".ico", ".jpeg", ".jpg", ".js", ".json", ".map", ".md", ".markdown", ".mp3", ".mp4",
    ".pdf", ".png", ".ppt", ".pptx", ".svg", ".tif", ".tiff", ".ttf",
    ".txt", ".wav", ".webm", ".webp", ".woff", ".woff2", ".xls", ".xlsx",
    ".xml", ".zip",
)
FINANCE_STRUCTURAL_PATTERNS = (
    "/loan", "/loans", "/mortgage", "/credit", "/pret", "/assurance",
    "/insurance", "/quote", "/devis", "/calculator", "/simulation",
    "/apply", "/dscr", "/bridge", "/fix-and-flip", "/rental",
    "/request-a-payoff", "/document-exchange", "/bank-account", "/bank-accounts",
    "/banking", "/debit-card", "/business-account",
)
# Listing-detail routes (owned inventory) — the marketplace tell.
BOOKING_LISTING_PATTERNS = (
    "/annonce", "/activites/", "/activite/", "/activities/", "/activity/",
    "/listings/", "/listing/", "/experiences/", "/workshops/", "/workshop/",
    "/ateliers/", "/atelier/", "/tours/", "/attractions/", "/venues/",
    "/rooms/", "/stays/", "/homes/",
)
BOOKING_STRUCTURAL_PATTERNS = BOOKING_LISTING_PATTERNS + (
    "/booking", "/book/", "/reservation", "/availability", "/tickets", "/billetterie",
)
LOCAL_BUSINESS_ROUTE_PATTERNS = (
    "/menu", "/menus", "/visit", "/tasting", "/tastings",
    "/vineyard", "/hours", "/directions", "/catering",
    "/private-events", "/order-online", "/reservations", "/reserve-a-table",
    "/find-us", "/locations",
)
LOCAL_HOMEPAGE_IDENTITY_PATTERNS = (
    r"\bbakery\b", r"\brestaurant\b", r"\bwinery\b", r"\bvineyard\b",
    r"\btasting room\b", r"\bdairy\b", r"\bcreamery\b",
    r"\bcaf[eé]\b", r"\bcoffee shop\b", r"\bbistro\b", r"\bpizzeria\b",
)
LOCAL_PUBLISHER_IDENTITY_TERMS = (
    "industry news", "trade publication", "magazine", "journal", "media company",
    "editorial publication", "industry insights",
)

PLAYBOOKS = {
    "finance_insurance_lead_gen": {
        "label": "finance / insurance / lead generation",
        "keywords": [
            "assurance", "insurance", "pret", "prêt", "credit", "crédit", "loan",
            "loans", "lending", "lender", "mortgage", "finance", "banque", "bank",
            "taux", "emprunteur", "mutuelle", "devis", "simulation", "comparateur",
            "courtier", "broker", "hard money", "bridge loan", "fix and flip",
            "fix-and-flip", "rental", "dscr", "real estate investor", "private lending",
            "payoff", "document exchange", "apply now", "loan overview",
            "money transfer", "international transfer", "multi-currency account",
            "currency converter",
        ],
        "money_patterns": [
            "/devis", "/quote", "/simulation", "/simulateur", "/calcul",
            "/calculator", "/comparateur", "/compare", "/tarif", "/contact",
            "/souscription", "/assurance", "/credit", "/pret", "/loan", "/loans",
            "/loan-overview", "/apply", "/apply-now", "/request-a-payoff",
            "/document-exchange", "/locations", "/fix-and-flip", "/bridge", "/rental", "/dscr",
        ],
        "priority_pages": [
            "loan program pages", "application pages", "quote/contact forms",
            "calculator or rate pages", "location pages", "legal/trust pages",
            "methodology/review pages",
        ],
        "priority_issues": [
            "indexability", "canonicalization", "trust pages", "schema",
            "broken lead paths", "form/application flow reliability",
            "template-level loan page issues",
        ],
        "demote": ["old news", "tag archives", "blog pagination", "generic metadata on low-value articles"],
        "owner_rule": "Trust, indexability, canonical, schema, route-boundary, and form/lead-flow issues often need your_web_person.",
    },
    "booking_experiences_marketplace": {
        "label": "booking / experiences marketplace",
        "keywords": [
            "booking", "reservation", "réservation", "activity", "activities",
            "activite", "activité", "activités", "experience", "expérience",
            "experiences", "event", "tour", "destination", "billet", "ticket",
            "travel", "voyage", "stage", "pilotage", "pass", "atelier", "cadeau",
            "coffret", "loisir", "annonce", "voir", "funbooker", "domaine",
            "hotel", "chateau",
        ],
        "money_patterns": [
            "/booking", "/reservation", "/activity", "/activities", "/activite",
            "/activité", "/event", "/tour", "/destination", "/billet", "/ticket",
            "/stage", "/pilotage", "/pass", "/show", "/checkout", "/annonce",
            "/annonces", "/voir", "/cadeau", "/coffret", "/loisir",
        ],
        "priority_pages": [
            "listing/category pages", "activity/detail pages", "location pages",
            "booking and checkout paths", "gift/ticket pages", "review/trust pages",
        ],
        "priority_issues": [
            "JavaScript rendering", "crawlable listing content", "booking route boundaries",
            "schema", "blocked listings", "duplicate templates", "missing trust signals",
            "template image-alt gaps on activity cards",
        ],
        "demote": ["old editorial posts", "tag archives", "low-value pagination", "one-off metadata on inactive listings"],
        "owner_rule": "Rendering, schema, canonical, booking-flow, marketplace templates, and repeated listing-card fixes usually need your_web_person.",
    },
    "ecommerce_specialty_retail": {
        "label": "ecommerce / specialty retail",
        "keywords": [
            "product", "produit", "shop", "boutique", "cart", "panier", "checkout",
            "price", "prix", "sku", "collection", "category", "marque", "brand",
            "variant", "shipping", "livraison", "shopify", "add to cart",
            "add to bag", "in stock", "delivery", "pickup", "store locator",
        ],
        "money_patterns": [
            "/products/", "/product/", "/produit/", "/collections/", "/collection/",
            "/category/", "/categorie/", "/cat/", "/p/", "/shop", "/boutique",
            "/cart", "/checkout", "/basket", "/store/", "/marque",
        ],
        "priority_pages": [
            "product pages", "collection/category pages", "brand pages",
            "cart/checkout route boundaries", "shipping/returns/trust pages",
        ],
        "priority_issues": [
            "product/category indexability", "product schema", "canonicalization",
            "blocked product pages", "template image-alt issues", "checkout/account route boundaries",
        ],
        "demote": ["old blog posts", "tag archives", "generic metadata on inactive products"],
        "owner_rule": "Product schema, canonical, template, cart/checkout, and blocked-product issues usually need your_web_person.",
    },
    "saas_app_membership": {
        "label": "SaaS / app / membership",
        "keywords": [
            "dashboard", "login", "register", "app", "billing", "admin",
            "workspace", "account", "subscription", "developer", "pricing",
            "demo", "trial", "api", "report", "software", "features",
            "integrations", "platform", "install", "download",
            "customer stories", "case studies",
        ],
        "money_patterns": ["/pricing", "/register", "/signup", "/demo", "/contact", "/features", "/use-cases", "/solutions"],
        "priority_pages": ["homepage", "pricing", "demo/signup", "features/use cases", "docs/help pages", "public trust/security pages"],
        "priority_issues": ["internal/auth route exposure", "custom domain trust", "duplicate casing", "thin app snapshots", "noindex boundaries", "canonicalization"],
        "demote": ["metadata on internal routes", "duplicate app snapshots that should be noindexed", "low-value docs pagination"],
        "owner_rule": "Route boundaries, auth, canonical, app rendering, and noindex rules need your_web_person.",
    },
    "nonprofit_fundraising": {
        "label": "nonprofit / fundraising organization",
        "keywords": [
            "nonprofit", "non-profit", "charity", "donate", "donation", "giving",
            "fundraise", "fundraiser", "fundraising", "campaign", "impact",
            "clean water", "monthly giving", "support our work", "our projects",
        ],
        "money_patterns": [
            "/donate", "/donation", "/give", "/fundraise", "/fundraiser",
            "/fundraising", "/campaign", "/projects/", "/our-projects/",
        ],
        "priority_pages": [
            "donation and giving pages", "fundraising campaign pages",
            "project and impact pages", "about and financial-transparency pages",
            "stories and supporter trust pages",
        ],
        "priority_issues": [
            "donation-flow reliability", "campaign indexability", "trust and transparency",
            "project-page templates", "schema", "canonicalization",
        ],
        "demote": ["old campaign archives", "supporter utility pages", "account routes", "thank-you pages"],
        "owner_rule": "Donation flows, campaign templates, redirects, canonicals, schema, and account boundaries usually need your_web_person.",
    },
    "local_business_hospitality": {
        "label": "local business / food / hospitality",
        "keywords": [
            "bakery", "restaurant", "winery", "vineyard", "tasting room", "wine club",
            "dairy", "creamery", "cafe", "café", "coffee shop", "bistro", "pizzeria",
            "family owned", "locally owned", "estate wines", "farmstead", "artisan bread",
            "pastry", "menu", "catering", "private events", "visit us", "opening hours",
        ],
        "money_patterns": [
            "/menu", "/visit", "/tasting", "/wine-club", "/our-club", "/hours",
            "/directions", "/catering", "/private-events", "/order-online",
            "/reservations", "/reserve-a-table", "/find-us", "/locations",
        ],
        "priority_pages": [
            "homepage", "menu or product overview", "visit, hours, and location pages",
            "reservation or tasting pages", "about/our-story pages", "contact and trust pages",
        ],
        "priority_issues": [
            "local discoverability", "location and opening-hours accuracy", "menu/product indexability",
            "reservation or visit-path reliability", "LocalBusiness schema", "metadata on key conversion pages",
        ],
        "demote": ["default WordPress archives", "old news posts", "tag pages", "utility account routes"],
        "owner_rule": "Local schema, redirects, canonicals, reservation paths, and repeated template issues usually need your_web_person.",
    },
    "content_blog": {
        "label": "content / blog-heavy site",
        "keywords": ["blog", "news", "article", "guide", "resources", "insights", "author", "newsletter", "subscribe"],
        "money_patterns": ["/newsletter", "/subscribe", "/contact", "/resources", "/guide", "/pricing"],
        "priority_pages": ["pillar guides", "category hubs", "newsletter/subscription pages", "author/trust pages", "contact/conversion pages"],
        "priority_issues": ["duplicate/thin content", "author/reviewer trust", "internal linking", "canonicalization", "index bloat", "schema"],
        "demote": ["tag pages", "date archives", "pagination", "old low-traffic news unless strategically important"],
        "owner_rule": "Editorial changes can be you; indexation, canonical, templates, and schema often need your_web_person.",
    },
    "general": {
        "label": "general website",
        "keywords": [],
        "money_patterns": ["/contact", "/services", "/products", "/pricing"],
        "priority_pages": ["homepage", "contact", "services/products", "pricing/quote", "trust pages"],
        "priority_issues": ["crawlability", "indexability", "trust", "broken pages", "schema", "metadata on key pages"],
        "demote": ["archives", "tags", "pagination"],
        "owner_rule": "Simple content edits can be you; crawl, schema, redirects, canonicals, and rendering need your_web_person.",
    },
}


def run_review(payload: dict[str, Any]) -> dict[str, Any]:
    body = unwrap_scan_payload(payload)
    website_url = clean_str(
        body.get("website_url")
        or body.get("normalized_url")
        or body.get("url")
        or deep_get(body, "technical_audit_summary", "website_url")
        or ""
    )
    pages = first_array(
        body.get("crawled_pages"),
        body.get("pages"),
        body.get("scanned_pages"),
        body.get("crawl_pages"),
        deep_get(body, "technical_audit_summary", "pages"),
    )
    raw_fixes = collect_arrays(
        body.get("raw_fixes"),
        body.get("grouped_findings"),
        body.get("raw_findings"),
        body.get("findings"),
        body.get("fixes"),
        body.get("recommendations"),
        body.get("issues"),
    )

    site_fingerprint = build_site_fingerprint(body, pages, website_url)
    site_fingerprint["scoring_model"] = SCORING_MODEL
    playbook = get_playbook(site_fingerprint["primary_archetype"])
    playbook = apply_finance_sub_playbook(playbook, site_fingerprint.get("finance_sub_playbook", ""))
    evidence_fixes = build_scanner_evidence_findings(body, pages, site_fingerprint)
    page_pattern_fixes = build_page_pattern_findings(pages)
    location_template_fixes = build_location_template_raw_fixes(pages)
    strategic_fixes = build_strategic_findings(body, pages, website_url, site_fingerprint, playbook)
    canonical_fixes = prepare_fixes(raw_fixes + evidence_fixes + page_pattern_fixes + location_template_fixes + strategic_fixes, site_fingerprint, body, playbook, pages)
    no_page_evidence = (
        int_or_zero(site_fingerprint.get("pages_received")) <= 0
        or int_or_zero(site_fingerprint.get("pages_crawled")) <= 0
    )
    evidence_incomplete = evidence_is_incomplete(site_fingerprint) or no_page_evidence
    classification_insufficient = (
        site_fingerprint.get("classification_state") == "inconclusive_insufficient_evidence"
    )
    no_high_confidence_findings = (
        not canonical_fixes
        and not evidence_incomplete
        and not classification_insufficient
        and not crawl_is_blocked(site_fingerprint)
    )

    warning = ""
    if evidence_incomplete:
        warning = INCOMPLETE_REVIEW_WARNING
        if not canonical_fixes:
            canonical_fixes = [make_missing_evidence_fix()]
    elif classification_insufficient and not crawl_is_blocked(site_fingerprint):
        warning = "The crawl returned too few usable pages for a reliable site classification or health grade."
    elif not website_url:
        warning = "AI review ran, but website_url was missing. Scanner recommendations are shown."
    elif not canonical_fixes and not no_high_confidence_findings:
        warning = "AI review ran, but no scanner recommendations were provided."

    review_payload = build_review_payload(body, pages, canonical_fixes, site_fingerprint, playbook, website_url)
    if no_page_evidence and not crawl_is_blocked(site_fingerprint):
        apply_incomplete_evidence_state(review_payload)
    elif no_high_confidence_findings:
        apply_zero_fix_confidence_state(review_payload)
    result = {
        "success": True,
        "ai_provider": "python_review_api",
        "review_version": REVIEW_VERSION,
        "ai_review_version": REVIEW_VERSION,
        "ai_review_warning": warning,
        "review_evidence_contract_version": "review_evidence_contract_v1",
        **review_payload,
    }
    result["review_polish_version"] = SCORING_MODEL
    result["group_dedup_version"] = SCORING_MODEL
    result["scoring_model"] = SCORING_MODEL
    if isinstance(result.get("site_fingerprint"), dict):
        result["site_fingerprint"]["scoring_model"] = SCORING_MODEL
    if isinstance(result.get("scan_summary"), dict):
        result["scan_summary"]["scoring_model"] = SCORING_MODEL
    return result

def unwrap_scan_payload(value: Any) -> dict[str, Any]:
    current = value or {}
    for _ in range(5):
        if isinstance(current, str):
            current = parse_json_object(current)
        if looks_like_scan_payload(current):
            return current
        if looks_like_scan_payload(current.get("scan") if isinstance(current, dict) else None):
            current = current["scan"]
            continue
        if looks_like_scan_payload(current.get("data") if isinstance(current, dict) else None):
            current = current["data"]
            continue
        if looks_like_scan_payload(deep_get(current, "data", "data")):
            current = current["data"]["data"]
            continue
        if looks_like_scan_payload(current.get("payload") if isinstance(current, dict) else None):
            current = current["payload"]
            continue
        if looks_like_scan_payload(current.get("body") if isinstance(current, dict) else None):
            current = current["body"]
            continue
        if looks_like_scan_payload(current.get("result") if isinstance(current, dict) else None):
            current = current["result"]
            continue
        break
    return current if isinstance(current, dict) else {}


def looks_like_scan_payload(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if value.get("ai_provider") and not value.get("scanner_version") and not value.get("pages_crawled"):
        return False
    return bool(
        value.get("website_url")
        or value.get("normalized_url")
        or value.get("scanner_version")
        or value.get("pages_crawled")
        or value.get("pages_found")
        or isinstance(value.get("pages"), list)
        or isinstance(value.get("crawled_pages"), list)
        or isinstance(value.get("verified_failed_pages"), list)
    )


def normalized_structural_route_paths(pages: list[dict[str, Any]]) -> list[str]:
    """Return one structural route vote per locale-equivalent HTML path.

    Raw page copy remains available to the keyword classifier. Only structural
    route counts use this identity, so twelve translations of `/blog/etfs`
    contribute one route while twelve different article slugs remain twelve.
    """
    paths: list[str] = []
    seen: set[str] = set()
    for page in pages[:220]:
        # Structural identity ignores query/fragment variants. Tracking
        # parameters are crawl/discovery detail, not distinct business routes.
        raw_path = clean_path(page_evidence_url(page)).split("?", 1)[0].split("#", 1)[0].lower()
        normalized = strip_market_locale_prefix(raw_path).rstrip("/") or "/"
        if normalized and normalized not in seen:
            seen.add(normalized)
            paths.append(normalized)
    return paths


def build_site_fingerprint(body: dict[str, Any], pages: list[dict[str, Any]], website_url: str) -> dict[str, Any]:
    # Only HTML evidence may define a business route family. Asset filenames such
    # as signup-form.png or demo-site.png are crawl evidence, not product routes.
    classifier_pages = [
        page for page in pages[:220]
        if not is_non_html_page_evidence(page)
    ]
    text_parts: list[str] = [
        website_url,
        str(body.get("business_name", "")),
        str(body.get("business_type", "")),
        str(body.get("cms_name", "")),
        str(body.get("cms_platform", "")),
        str(body.get("scan_mode", "")),
    ]
    for page in classifier_pages:
        text_parts.extend([
            str(page.get("url", "")),
            str(page.get("final_url", "")),
            str(page.get("path", "")),
            str(page.get("title", "")),
            str(page.get("h1", "")),
            str(page.get("meta_description", "")),
            str(page.get("page_template_family", "")),
            str(page.get("estimated_page_intent", "")),
            " ".join(map(str, page.get("schema_types") or [])),
        ])
    text = " ".join(text_parts).lower()
    # Homepage (shortest-path page) text is company-level evidence: what the
    # business says it IS, as opposed to what it publishes the most of.
    homepage_text = ""
    if classifier_pages:
        homepage = min(classifier_pages, key=lambda page: len(clean_path(page_evidence_url(page)) or "/"))
        homepage_text = " ".join([
            str(homepage.get("title", "")),
            str(homepage.get("h1", "")),
            str(homepage.get("meta_description", "")),
        ]).lower()

    scores = []
    for key, playbook in PLAYBOOKS.items():
        if key == "general":
            continue
        score = float(sum(min(count_includes(text, keyword), KEYWORD_COUNT_CAP) for keyword in playbook["keywords"]))
        score += sum(min(count_includes(text, pattern), KEYWORD_COUNT_CAP) for pattern in playbook["money_patterns"]) * 1.8
        score += sum(min(count_includes(homepage_text, keyword), 3) for keyword in playbook["keywords"]) * 2.0
        score += archetype_boost(key, text, pages)
        scores.append((key, score))

    structural_page_paths = normalized_structural_route_paths(classifier_pages)
    path_text = " ".join(structural_page_paths)
    saas_structural = [pattern for pattern in SAAS_STRUCTURAL_PATTERNS if pattern in path_text]
    ecommerce_structural = [pattern for pattern in ECOMMERCE_STRUCTURAL_PATTERNS if pattern in path_text]
    booking_structural = [pattern for pattern in BOOKING_STRUCTURAL_PATTERNS if pattern in path_text]
    finance_structural = [pattern for pattern in FINANCE_STRUCTURAL_PATTERNS if pattern in path_text]
    nonprofit_structural = [pattern for pattern in NONPROFIT_STRUCTURAL_PATTERNS if pattern in path_text]
    saas_core_structural = [pattern for pattern in SAAS_CORE_IDENTITY_PATTERNS if pattern in path_text]
    saas_business_families = [
        family
        for family, patterns in SAAS_BUSINESS_FAMILY_PATTERNS
        if any(pattern in path_text for pattern in patterns)
    ]
    app_distribution_platforms = [
        pattern
        for pattern in APP_DISTRIBUTION_PLATFORM_PATTERNS
        if any(pattern in path for path in structural_page_paths)
    ]
    platform_product_routes = [
        pattern
        for pattern in PLATFORM_PRODUCT_PATTERNS
        if any(path == pattern or path.startswith(pattern + "/") for path in structural_page_paths)
    ]
    ecommerce_marketplace_patterns = ("/itm/", "/sch/", "/b/", "/buy/", "/seller/", "/listing/")
    ecommerce_structural.extend(
        pattern for pattern in ecommerce_marketplace_patterns
        if pattern in path_text and pattern not in ecommerce_structural
    )
    marketplace_signals = sum(
        min(count_includes(text, signal), KEYWORD_COUNT_CAP)
        for signal in ("ebay", "buy it now", "auction", "seller", "item number", "shop by category")
    )
    product_schema_pages = count_schema_pages(classifier_pages, ("product", "offer"))
    article_schema_pages = count_schema_pages(classifier_pages, ("article", "blogposting", "newsarticle"))
    software_schema_pages = count_schema_pages(classifier_pages, ("softwareapplication", "mobileapplication", "webapplication"))
    local_schema_pages = count_schema_pages(
        classifier_pages,
        ("localbusiness", "restaurant", "winery", "bakery", "foodestablishment", "cafeorcoffeeshop"),
    )
    product_route_pages = sum(
        1 for path in structural_page_paths if any(pattern in path for pattern in PRODUCT_DETAIL_PATTERNS)
    )
    article_route_pages = sum(
        1 for path in structural_page_paths
        if any(pattern in path for pattern in ARTICLE_ROUTE_PATTERNS)
        or bool(re.search(r"/20\d{2}/(?:0?[1-9]|1[0-2])/", path))
    )
    saas_route_pages = sum(
        1 for path in structural_page_paths if any(pattern in path for pattern in SAAS_STRUCTURAL_PATTERNS)
    )
    finance_route_pages = sum(
        1 for path in structural_page_paths if any(pattern in path for pattern in FINANCE_STRUCTURAL_PATTERNS)
    )
    nonprofit_route_pages = sum(
        1 for path in structural_page_paths if any(pattern in path for pattern in NONPROFIT_STRUCTURAL_PATTERNS)
    )
    local_route_pages = sum(
        1 for path in structural_page_paths if any(pattern in path for pattern in LOCAL_BUSINESS_ROUTE_PATTERNS)
    )
    booking_listing_pages = sum(
        1 for path in structural_page_paths
        if any(pattern in path for pattern in BOOKING_LISTING_PATTERNS)
    )
    if product_schema_pages >= 3:
        ecommerce_structural = ecommerce_structural + ["schema:Product"]
    if marketplace_signals >= 2:
        ecommerce_structural = ecommerce_structural + ["marketplace:ecommerce"]
    if software_schema_pages >= 2:
        saas_structural = saas_structural + ["schema:SoftwareApplication"]

    saas_homepage_identity = has_any(homepage_text, [
        "software", "saas", "platform", "app", "application", "workspace",
        "project management", "customer support", "helpdesk",
        "social media management", "messaging app", "private messenger",
        "secure messaging", "website builder", "visual development",
        "web experience platform", "design platform", "commerce platform",
        "free trial", "start your trial",
    ])
    finance_homepage_identity = has_any(homepage_text, [
        "lending", "lender", "mortgage", "insurance", "assurance", "loan provider",
        "bridge loan", "hard money", "private lending", "credit broker",
        "digital bank", "mobile bank", "bank account", "business account", "debit card",
        "money transfer", "international transfer", "multi-currency account", "currency converter",
    ])
    finance_operations_homepage_identity = has_any(homepage_text, [
        "money transfer", "international transfer", "multi-currency account", "currency converter",
    ])
    booking_homepage_identity = has_any(homepage_text, [
        "things to do", "book tickets", "buy tickets", "museum tickets",
        "skip the line", "skip-the-line", "guided tour", "guided tours",
        "day trips", "excursions", "book an experience", "book your experience",
        "activities and tours", "tours and activities", "book activities",
    ])
    nonprofit_homepage_identity = has_any(homepage_text, [
        "nonprofit", "non-profit", "charity", "donate", "donation", "fundraising",
        "support our work", "monthly giving", "clean water", "our impact",
    ])
    local_publisher_identity = has_any(homepage_text, LOCAL_PUBLISHER_IDENTITY_TERMS)
    local_homepage_identity = bool(
        any(re.search(pattern, homepage_text, re.I) for pattern in LOCAL_HOMEPAGE_IDENTITY_PATTERNS)
        and not local_publisher_identity
    )
    publisher_dominant = bool(
        article_route_pages >= max(8, product_route_pages * 2)
        and (article_schema_pages >= 3 or article_route_pages >= 12)
    )
    retail_dominant = bool(
        (
            product_route_pages >= 3
            and product_route_pages >= max(3, round(article_route_pages * 0.45))
        )
        or (
            product_schema_pages >= 3
            and product_schema_pages >= max(3, round(article_schema_pages * 0.75))
        )
        or (
            len(ecommerce_structural) >= 3
            and product_route_pages > 0
            and product_route_pages >= max(2, round(article_route_pages * 0.35))
        )
    )
    local_dominant = bool(
        local_schema_pages >= 1
        or local_route_pages >= 3
        or (local_homepage_identity and not publisher_dominant)
    )
    if retail_dominant and local_schema_pages == 0 and local_route_pages == 0:
        local_dominant = False
    saas_business_identity = bool(
        saas_homepage_identity
        and saas_route_pages >= 1
        and any(family in {"product", "commercial"} for family in saas_business_families)
    )
    saas_diverse_structure = bool(
        len(saas_core_structural) >= 3
        and len(saas_business_families) >= 2
        and saas_route_pages >= 3
    )
    saas_app_distribution_identity = bool(
        "/download" in saas_core_structural
        and "developer" in saas_business_families
        and len(app_distribution_platforms) >= 3
    )
    saas_platform_infrastructure_identity = bool(
        len(platform_product_routes) >= 3
        and "developer" in saas_business_families
        and saas_route_pages >= 4
    )
    saas_dominant = bool(
        saas_business_identity
        or saas_diverse_structure
        or saas_app_distribution_identity
        or saas_platform_infrastructure_identity
        or software_schema_pages >= 2
    )
    nonprofit_dominant = bool(
        nonprofit_route_pages >= 3
        and (nonprofit_homepage_identity or nonprofit_route_pages >= 8)
    )
    finance_dominant = bool(
        finance_route_pages >= 3
        or len(finance_structural) >= 2
        or (finance_homepage_identity and finance_route_pages >= 1)
    )
    # A booking marketplace operates listing and reservation routes that only
    # exist when the business actually sells the experience. This mirrors the
    # threshold the booking score itself already trusts, so a site that scores
    # as booking also counts as a structural competitor rather than ceding the
    # result to whichever archetype sampled the most editorial pages.
    booking_dominant = bool(
        len(booking_structural) >= 2
        or booking_listing_pages >= 2
        or (booking_homepage_identity and booking_listing_pages >= 1)
    )

    adjusted_scores = []
    for key, score in scores:
        if key == "ecommerce_specialty_retail":
            if publisher_dominant and not retail_dominant and marketplace_signals < 2:
                score = min(score, 2.0)
            elif not retail_dominant and len(ecommerce_structural) < 2 and marketplace_signals < 2:
                score = min(score, 1.0)
            else:
                score += 10.0 * len(ecommerce_structural)
                score += 2.0 * min(product_route_pages, 20)
                score += 2.0 * min(product_schema_pages, 20)
        if key == "booking_experiences_marketplace":
            if len(booking_structural) < 2 and booking_listing_pages < 2:
                score = min(score, 1.0)
            else:
                score += 8.0 * max(len(booking_structural), 1)
        if key == "saas_app_membership":
            if not saas_dominant:
                score = min(score, 1.0)
            else:
                score += 12.0 * len(saas_core_structural)
                score += 8.0 * len(saas_business_families)
                score += 2.0 * min(saas_route_pages, 15)
                if saas_homepage_identity:
                    score += 20.0
                if saas_app_distribution_identity:
                    score += 20.0
                if saas_platform_infrastructure_identity:
                    score += 24.0
        if key == "finance_insurance_lead_gen":
            if not finance_dominant:
                score = min(score, 6.0)
            else:
                score += 10.0 * len(finance_structural)
                score += 2.0 * min(finance_route_pages, 20)
                if finance_homepage_identity:
                    score += 20.0
                if finance_operations_homepage_identity:
                    score += 12.0
        if key == "nonprofit_fundraising":
            if not nonprofit_dominant:
                score = min(score, 4.0)
            else:
                score += 10.0 * len(nonprofit_structural)
                score += 2.0 * min(nonprofit_route_pages, 25)
                if nonprofit_homepage_identity:
                    score += 20.0
        if key == "local_business_hospitality":
            if not local_dominant:
                score = min(score, 3.0)
            else:
                score += 24.0
                score += 5.0 * min(local_schema_pages, 4)
                score += 3.0 * min(local_route_pages, 10)
                if local_homepage_identity:
                    score += 24.0
        if key == "content_blog" and publisher_dominant:
            score += 2.0 * min(article_route_pages, 25)
            score += 1.5 * min(article_schema_pages, 20)
        adjusted_scores.append((key, score))

    # Booking belonged here from the start and was the one structural archetype
    # missing: a marketplace whose sampled pages skewed editorial lost to
    # content_blog on article volume alone, which is how the 35-site production
    # audit saw Musement and Tiqets reported as publishers.
    structural_competitor = (
        saas_dominant
        or retail_dominant
        or booking_dominant
        or finance_dominant
        or nonprofit_dominant
        or local_dominant
    )
    if structural_competitor:
        adjusted_scores = [
            (key, min(score, CONTENT_BLOG_STRUCTURAL_CAP) if key == "content_blog" else score)
            for key, score in adjusted_scores
        ]

    scores = sorted(adjusted_scores, key=lambda item: item[1], reverse=True)
    primary = scores[0][0] if scores and scores[0][1] > 0 else "general"
    secondary = scores[1][0] if len(scores) > 1 and scores[1][1] > max(3, scores[0][1] * 0.6) else ""
    confidence = min(0.96, 0.45 + (scores[0][1] / max(12, scores[0][1] + (scores[1][1] if len(scores) > 1 else 0)))) if scores and scores[0][1] > 0 else 0.35
    playbook = get_playbook(primary)
    if primary == "finance_insurance_lead_gen":
        playbook = resolve_finance_playbook(playbook, homepage_text, path_text)
    pages_found = first_number(
        deep_get(body, "scan_coverage", "pages_found"),
        body.get("pages_found"),
        deep_get(body, "technical_audit_summary", "pages_found"),
        len(pages),
    )
    pages_crawled = first_number(
        deep_get(body, "scan_coverage", "pages_crawled"),
        body.get("pages_crawled"),
        deep_get(body, "technical_audit_summary", "pages_crawled"),
        len(pages),
    )
    pages_received = len(pages or [])
    sampled_pages_sent = first_number(deep_get(body, "scan_coverage", "sampled_pages_sent_to_ai"), pages_received)
    route_boundary_count = sum(1 for p in pages if is_route_boundary_candidate(page_evidence_url(p)) or is_internal_app_route(page_evidence_url(p)))
    blocked_access_pages = sum(1 for p in pages if is_blocked_access_page(p))
    blocked_or_429_pages = max(
        blocked_access_pages,
        int_or_zero(deep_get(body, "scan_coverage", "rate_limited_pages")),
        int_or_zero(deep_get(body, "scan_coverage", "blocked_pages")),
        int_or_zero(deep_get(body, "technical_audit_summary", "blocked_pages")),
    )
    host = safe_hostname(website_url)

    # Classification confidence is separate from scan completion. Fewer than
    # four usable pages normally stays inconclusive, unless the crawler proves
    # that it exhausted a genuinely small inventory with every discovered URL
    # accounted for by a retained page or a normalized final-URL duplicate.
    usable_pages = sum(1 for page in pages if page_has_usable_html(page))
    crawl_timing = body.get("crawl_timing") if isinstance(body.get("crawl_timing"), dict) else {}
    if not crawl_timing:
        nested_timing = deep_get(body, "technical_audit_summary", "crawl_timing")
        crawl_timing = nested_timing if isinstance(nested_timing, dict) else {}
    final_url_duplicates_deduped = max(
        int_or_zero(crawl_timing.get("final_url_duplicates_deduped")),
        int_or_zero(deep_get(body, "technical_audit_summary", "final_url_duplicates_deduped")),
    )
    complete_small_site_inventory = bool(
        1 <= usable_pages < 4
        and pages_crawled == usable_pages
        and pages_found <= pages_crawled + final_url_duplicates_deduped
        and crawl_timing.get("queue_exhausted") is True
        and crawl_timing.get("crawl_deadline_reached") is not True
        and int_or_zero(crawl_timing.get("failed_fetch_count")) == 0
        and int_or_zero(body.get("queued_remaining")) == 0
    )
    if blocked_or_429_pages and blocked_or_429_pages / max(usable_pages + blocked_or_429_pages, 1) >= 0.6:
        evidence_sufficiency = "access_limited"
    elif usable_pages < 4 and not complete_small_site_inventory:
        evidence_sufficiency = "insufficient_pages"
    else:
        evidence_sufficiency = "complete_small_site_inventory" if complete_small_site_inventory else "sufficient"
    classification_state = "classified" if evidence_sufficiency in {"sufficient", "complete_small_site_inventory"} else "inconclusive_insufficient_evidence"
    if classification_state != "classified":
        confidence = min(confidence, 0.35)
    elif complete_small_site_inventory:
        confidence = min(confidence, 0.65)

    score_map = dict(scores)
    runner_up = scores[1] if len(scores) > 1 else ("", 0.0)
    classification = {
        "classifier_version": ARCHETYPE_CLASSIFIER_VERSION,
        "state": classification_state,
        "evidence_sufficiency": evidence_sufficiency,
        "usable_pages": usable_pages,
        "blocked_or_429_pages": blocked_or_429_pages,
        "complete_small_site_inventory": complete_small_site_inventory,
        "small_site_inventory_accounting": {
            "pages_found": pages_found,
            "pages_crawled": pages_crawled,
            "usable_pages": usable_pages,
            "final_url_duplicates_deduped": final_url_duplicates_deduped,
            "queue_exhausted": crawl_timing.get("queue_exhausted") is True,
            "failed_fetch_count": int_or_zero(crawl_timing.get("failed_fetch_count")),
        },
        "scores": [{"archetype": key, "score": round(value, 1)} for key, value in scores[:3]],
        "structural_signals": {
            "saas": saas_structural,
            "ecommerce": ecommerce_structural,
            "booking": booking_structural,
            "booking_listing_pages": booking_listing_pages,
            "product_schema_pages": product_schema_pages,
            "article_schema_pages": article_schema_pages,
            "software_schema_pages": software_schema_pages,
            "local_schema_pages": local_schema_pages,
            "local_route_pages": local_route_pages,
            "local_homepage_identity": local_homepage_identity,
            "local_publisher_identity": local_publisher_identity,
            "local_dominant": local_dominant,
            "product_route_pages": product_route_pages,
            "article_route_pages": article_route_pages,
            "classifier_html_route_pages": len(classifier_pages),
            "normalized_structural_route_pages": len(structural_page_paths),
            "saas_route_pages": saas_route_pages,
            "saas_business_families": saas_business_families,
            "app_distribution_platforms": app_distribution_platforms,
            "platform_product_routes": platform_product_routes,
            "saas_platform_infrastructure_identity": saas_platform_infrastructure_identity,
            "saas_homepage_identity": saas_homepage_identity,
            "saas_business_identity": saas_business_identity,
            "saas_diverse_structure": saas_diverse_structure,
            "saas_app_distribution_identity": saas_app_distribution_identity,
            "finance_route_pages": finance_route_pages,
            "finance_operations_homepage_identity": finance_operations_homepage_identity,
            "nonprofit_route_pages": nonprofit_route_pages,
            "publisher_dominant": publisher_dominant,
            "retail_dominant": retail_dominant,
            "booking_dominant": booking_dominant,
            "booking_homepage_identity": booking_homepage_identity,
            "saas_dominant": saas_dominant,
            "nonprofit_dominant": nonprofit_dominant,
            "saas_core": saas_core_structural,
            "finance": finance_structural,
            "nonprofit": nonprofit_structural,
        },
        "winning_reason": (
            f"{primary} scored {round(score_map.get(primary, 0.0), 1)} vs {runner_up[0] or 'none'} "
            f"{round(runner_up[1], 1)}; structural signals saas={len(saas_structural)}, "
            f"ecommerce={len(ecommerce_structural)}, booking={len(booking_structural)}, "
            f"finance={len(finance_structural)}, nonprofit={len(nonprofit_structural)}, "
            f"local_routes={local_route_pages}, local_schema={local_schema_pages}; "
            f"dominance publisher={publisher_dominant}, retail={retail_dominant}, booking={booking_dominant}, local={local_dominant}, "
            f"saas={saas_dominant}, app_distribution={saas_app_distribution_identity}, "
            f"platform_infrastructure={saas_platform_infrastructure_identity}, "
            f"nonprofit={nonprofit_dominant}; "
            f"content_blog cap {'applied' if structural_competitor else 'not applied'}."
        ) if primary != "general" else "No archetype scored above zero; defaulted to general.",
        "strongest_conflicting_signal": (
            f"{runner_up[0]} scored {round(runner_up[1], 1)}" if runner_up[0] and runner_up[1] > 0 else ""
        ),
        "access_limitation_impact": (
            f"{blocked_or_429_pages} blocked/rate-limited pages against {usable_pages} usable pages"
            if blocked_or_429_pages else ""
        ),
    }

    return {
        "primary_archetype": primary,
        "secondary_archetype": secondary,
        "archetype_label": playbook["label"],
        "finance_sub_playbook": playbook.get("finance_sub_playbook", ""),
        "vertical": primary,
        "vertical_label": playbook["label"],
        "vertical_confidence": round(confidence, 2),
        "classification": classification,
        "classification_state": classification["state"],
        # One coverage decision per crawl, taken here because this is where the
        # full crawl body is available. Everything downstream reads this rather
        # than re-deriving it from a summary that has already lost the sitemap
        # and timing evidence the decision depends on.
        "coverage_assessment": assess_coverage(coverage_inputs_from_payload(
            {
                "pages_found": pages_found,
                "pages_crawled": pages_crawled,
                "queued_remaining": int_or_zero(body.get("queued_remaining")),
                "crawl_timing": crawl_timing,
            },
            retained_usable_html=usable_pages,
            blocked_or_429_pages=blocked_or_429_pages,
        )),
        "classification_evidence_sufficiency": classification["evidence_sufficiency"],
        "business_model": detect_business_model(text, primary),
        "size_band": "enterprise" if max(pages_found, pages_crawled, pages_received) >= 1000 else "mid_market" if max(pages_found, pages_crawled, pages_received) >= 150 else "smb" if max(pages_found, pages_crawled, pages_received) >= 30 else "micro",
        "pages_found": pages_found,
        "pages_crawled": pages_crawled,
        "pages_received": pages_received,
        "sampled_pages_sent_to_ai": sampled_pages_sent,
        "localization": detect_localization(pages, website_url),
        "render_mode": "rendered_browser_checked" if deep_get(body, "browser_rendering", "enabled") else "js_heavy_suspected" if sum(1 for page in pages if page.get("client_rendering_suspected")) >= 3 else "raw_html_first",
        "regulatory_sensitivity": "trust_or_regulated" if primary in {"finance_insurance_lead_gen", "utilities_comparison_lead_gen", "nonprofit_fundraising"} else "standard",
        "likely_money_page_patterns": playbook["money_patterns"],
        "archetype_priority_pages": playbook["priority_pages"],
        "archetype_priority_issues": playbook["priority_issues"],
        "archetype_demotions": playbook["demote"],
        "route_boundary_count": route_boundary_count,
        "route_boundary_risk": "high" if route_boundary_count >= 4 else "medium" if route_boundary_count else "low",
        "blocked_access_pages": blocked_access_pages,
        "blocked_or_429_pages": blocked_or_429_pages,
        "free_base44_subdomain": host.endswith(".base44.app"),
        "scoring_model": SCORING_MODEL,
        "grouped_recommendation_evidence_version": GROUPED_RECOMMENDATION_EVIDENCE_VERSION,
    }


def review_input_quality(body: dict[str, Any], site_fingerprint: dict[str, Any]) -> dict[str, Any]:
    incomplete = evidence_is_incomplete(site_fingerprint)
    insufficient = site_fingerprint.get("classification_state") == "inconclusive_insufficient_evidence"
    return {
        "version": QUALITY_GATE_VERSION,
        "pages_received": int_or_zero(site_fingerprint.get("pages_received")),
        "pages_crawled_reported": int_or_zero(site_fingerprint.get("pages_crawled")),
        "pages_found_reported": int_or_zero(site_fingerprint.get("pages_found")),
        "sampled_pages_sent_to_ai": int_or_zero(site_fingerprint.get("sampled_pages_sent_to_ai")),
        "grouped_findings_received": len(body.get("grouped_findings") or []) if isinstance(body.get("grouped_findings"), list) else 0,
        "verified_failed_pages_received": count_lists(body.get("verified_failed_pages"), deep_get(body, "technical_audit_summary", "verified_failed_pages"), deep_get(body, "url_evidence_summary", "verified_failed_pages")),
        "suspicious_artifacts_received": count_lists(body.get("suspicious_url_artifacts"), deep_get(body, "technical_audit_summary", "suspicious_url_artifacts"), deep_get(body, "url_evidence_summary", "suspicious_url_artifacts")),
        "has_technical_summary": bool(body.get("technical_audit_summary")),
        "evidence_complete": not (incomplete or insufficient),
        "metadata_without_pages": incomplete,
        "blocked_or_429_pages": int_or_zero(site_fingerprint.get("blocked_or_429_pages")),
    }


def evidence_is_incomplete(site_fingerprint: dict[str, Any]) -> bool:
    """Incomplete means no usable page evidence arrived at all.

    Deliberately narrow. A thin-but-real crawl is *insufficient*, not
    incomplete, and the two are different customer states: incomplete_evidence
    says the review never saw pages, inconclusive_insufficient_evidence says it
    saw some and could not conclude from them. Coverage is judged once, by
    coverage_authority.assess_coverage, and reaches the result through
    `insufficient` -- which is also what makes evidence_complete false.

    The old thin-crawl clause here (fewer than 20 received pages) is what let
    38/3,689 and 40/1,374 seal as complete; the shared assessment replaces it.
    """
    received = int_or_zero(site_fingerprint.get("pages_received"))
    crawled = int_or_zero(site_fingerprint.get("pages_crawled"))
    found = int_or_zero(site_fingerprint.get("pages_found"))
    reported = max(crawled, found)
    sampled = int_or_zero(site_fingerprint.get("sampled_pages_sent_to_ai"))
    if reported > 0 and (received == 0 or sampled == 0):
        return True
    # The original clause, kept exactly. It only ever caught the most extreme
    # cases (7/900), and those already read as incomplete_evidence to customers;
    # widening it would relabel them. The crawls it missed -- 38/3,689,
    # 40/1,374 -- are caught by the shared coverage decision as *insufficient*,
    # which is the honest state for a thin-but-real sample.
    if found >= 100 and received < 20 and received / max(found, 1) < 0.10:
        return True
    return False


def coverage_limitation_text(site_fingerprint: dict[str, Any]) -> str:
    """Plain-English reason a scan is not authoritative, from the shared verdict."""
    assessment = site_fingerprint.get("coverage_assessment")
    assessment = assessment if isinstance(assessment, dict) else {}
    state = str(assessment.get("state") or "")
    if not state or state == "sufficient":
        return ""
    inventory = assessment.get("inventory") if isinstance(assessment.get("inventory"), dict) else {}
    retained = int_or_zero(inventory.get("retained_usable_html"))
    discovered = int_or_zero(inventory.get("discovered_target"))
    if state == "limited_coverage":
        return (
            f"FixList reviewed {retained:,} of {discovered:,} discovered pages, which is too small a share "
            "of this site to support an authoritative result. The findings below are real for the pages "
            "checked; they are not a complete picture of the site."
        )
    if state == "inventory_unproven":
        return (
            f"FixList reviewed {retained:,} page(s) and could not confirm how many pages this site actually "
            "has, because no sitemap or inventory source answered. The findings below are real for the pages "
            "checked, but the rest of the site was never established."
        )
    if state == "access_limited":
        return (
            "The site rate-limited or challenged the scanner for most requests, so FixList could not collect "
            "enough verified HTML to support an authoritative result. The findings below cover only the pages "
            "that did respond."
        )
    return ""


def coverage_state_for_fingerprint(site_fingerprint: dict[str, Any]) -> str:
    """The shared coverage verdict recorded on the fingerprint.

    Read, never recomputed. A summary has already lost the sitemap-source and
    timing evidence the decision rests on, so re-deriving from it would quietly
    produce a second, worse opinion -- exactly the split this patch removes.
    """
    assessment = site_fingerprint.get("coverage_assessment")
    if isinstance(assessment, dict) and assessment.get("state"):
        return str(assessment["state"])
    return "sufficient"


def crawl_is_blocked(site_fingerprint: dict[str, Any]) -> bool:
    crawled = int_or_zero(site_fingerprint.get("pages_crawled"))
    received = int_or_zero(site_fingerprint.get("pages_received"))
    blocked = max(
        int_or_zero(site_fingerprint.get("blocked_access_pages")),
        int_or_zero(site_fingerprint.get("blocked_or_429_pages")),
    )
    if blocked == 0:
        return False
    if crawled <= 1:
        return True
    usable = max(received, crawled)
    return usable > 0 and (blocked / usable) >= 0.5


def make_missing_evidence_fix() -> dict[str, Any]:
    return {
        "id": "review_input_quality_missing_pages",
        "fix_id": "review_input_quality_missing_pages",
        "type": "debug_quality_gate",
        "rule": "review_evidence_missing",
        "category": "web_dev",
        "customer_category": "Website setup",
        "issue_title": "Scan evidence was not passed into AI Review",
        "title": "Scan evidence was not passed into AI Review",
        "plain_english_explanation": INCOMPLETE_REVIEW_WARNING,
        "plain_english_summary": INCOMPLETE_REVIEW_WARNING,
        "why_it_matters": "Without page evidence, FixList can identify the site type but cannot safely score the website or produce trustworthy fixes.",
        "current_value": "Scan metadata reported crawled pages, but the review payload contained zero page records.",
        "recommended_value": "Send the full runAdvancedScan.data object into aiReviewScan, including pages, grouped findings, failed-page evidence, and technical_audit_summary.",
        "ai_recommendation": "Pass the complete advanced scan response into AI Review before showing a score.",
        "recommendation": "Pass the complete advanced scan response into AI Review before showing a score.",
        "priority": "high",
        "difficulty": "developer",
        "status": "needs_developer",
        "can_auto_fix": False,
        "requires_approval": False,
        "requires_developer": True,
        "affected_pages": ["/"],
        "page_url": "/",
        "page_template_family": "site",
        "primary_defect_class": "crawl_index",
        "meta_rewrite_allowed": False,
        "meta_regeneration_gate": "review_input_incomplete",
        "business_importance": "site_level",
        "confidence_score": 100,
        "evidence_confidence": 100,
        "reach_score": 100,
        "overall_priority_score": 70,
        "what_to_do": [
            "Call runAdvancedScan and keep the full response data object.",
            "Pass that full object directly into aiReviewScan.",
            "Confirm review_input_quality.pages_received is greater than zero before showing a health score.",
        ],
        "what_to_do_steps": [
            "Call runAdvancedScan and keep the full response data object.",
            "Pass that full object directly into aiReviewScan.",
            "Confirm review_input_quality.pages_received is greater than zero before showing a health score.",
        ],
        "fix_steps": [
            "Call runAdvancedScan and keep the full response data object.",
            "Pass that full object directly into aiReviewScan.",
            "Confirm review_input_quality.pages_received is greater than zero before showing a health score.",
        ],
        "who_can_do_this": "your_web_person",
        "estimated_time": "about 15–30 minutes",
        "time_estimate": "about 15–30 minutes",
        "source": "review_input_quality_gate",
        "internal_debug": True,
    }


def count_schema_pages(pages: list[dict[str, Any]], schema_needles: tuple[str, ...]) -> int:
    """Pages whose structured data includes one of the given schema types."""
    count = 0
    for page in pages[:220]:
        types = " ".join(map(str, page.get("schema_types") or [])).lower()
        if any(needle in types for needle in schema_needles):
            count += 1
    return count


def archetype_boost(key: str, text: str, pages: list[dict[str, Any]]) -> float:
    path_text = " ".join(normalized_structural_route_paths([
        page for page in pages[:220] if not is_non_html_page_evidence(page)
    ]))
    if key == "booking_experiences_marketplace":
        score = min(count_includes(path_text, "/annonce/"), KEYWORD_COUNT_CAP) * 8
        score += min(count_includes(path_text, "/voir"), KEYWORD_COUNT_CAP) * 5
        # Marketplace vocabulary only counts when the site actually has
        # listing/booking routes — writing ABOUT reservations is publishing.
        has_marketplace_routes = any(pattern in path_text for pattern in BOOKING_STRUCTURAL_PATTERNS)
        if has_marketplace_routes and has_any(text, ["funbooker", "activité", "activite", "cadeau", "coffret", "loisir", "reservation", "réservation"]):
            score += 35
        return score
    if key == "finance_insurance_lead_gen":
        # Repeated editorial vocabulary is not proof of a finance business.
        # Structural routes and homepage identity are applied centrally in
        # build_site_fingerprint so mixed-template sites cannot self-amplify.
        return 0
    return 0


def build_scanner_evidence_findings(body: dict[str, Any], pages: list[dict[str, Any]], site_fingerprint: dict[str, Any]) -> list[dict[str, Any]]:
    evidence_pages = dedupe_pages(
        collect_arrays(
            body.get("verified_failed_pages"),
            deep_get(body, "technical_audit_summary", "verified_failed_pages"),
            deep_get(body, "url_evidence_summary", "verified_failed_pages"),
        )
        + [page for page in pages if is_failed_page(page) or is_blocked_access_page(page) or page_evidence_class(page) == "failed_access"]
    )
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for page in evidence_pages:
        grouped[status_bucket_from_page(page)].append(page)

    fixes = []
    for bucket, group in grouped.items():
        if bucket == "access":
            fixes.append(make_fix(
                rule="site_access_limited",
                category="web_dev",
                priority="medium",
                title="We could not fully check your site this time",
                explanation="The site redirected or responded in a way the scanner could not safely verify. This is a scan limitation, not proof of an SEO defect.",
                why="Without usable HTML, FixList cannot confirm titles, headings, canonical tags, metadata, schema, content, or image descriptions.",
                recommendation="Try again later. If it keeps happening, ask your web person to check hosting, CDN, firewall, bot-protection, DNS, and redirect logs.",
                affected_pages=[page_evidence_url(page) for page in group],
                difficulty="developer",
                source="scanner_access_evidence",
                extra={
                    **evidence_extra(group),
                    "evidence_status": "needs_verification",
                    "verification_state": "needs_verification",
                    "limitation_code": "site_access_requires_retry_or_log_confirmation",
                    "non_scoring": True,
                    "score_impact": 0,
                    "page_evidence_class": "failed_access",
                    "evidence_gate_version": PAGE_EVIDENCE_GATE_VERSION,
                    "confidence_score": 70,
                },
            ))
            continue
        if bucket == "429":
            fixes.append(make_fix(
                rule="rate_limited_page",
                category="web_dev",
                priority="high" if len(group) >= 3 else "medium",
                title="Check pages blocked by rate limiting" if len(group) >= 3 else "Verify crawler access for a rate-limited page",
                explanation="The scanner saw HTTP 429, bot protection, or a connection-verification response. This is crawler-access evidence, not proof that customers see a broken page.",
                why="If legitimate crawlers cannot access important pages, search engines may miss them. Verify this in server, CDN, firewall, or bot-protection logs before changing page content.",
                recommendation="Ask your web person to check server, CDN, firewall, and bot-protection logs for these URLs. Confirm whether Googlebot and normal users can access them, then adjust rate-limit rules only if legitimate access is blocked.",
                affected_pages=[page_evidence_url(page) for page in group],
                difficulty="developer",
                source="scanner_verified_failed_pages:429",
                extra={
                    **evidence_extra(group),
                    "evidence_status": "needs_verification",
                    "verification_state": "needs_verification",
                    "limitation_code": "rate_limit_requires_log_confirmation",
                },
            ))
            continue
        is_server = bucket == "5xx"
        repeated_observation = any(
            int_or_zero(
                page.get("failure_observation_count")
                or page.get("terminal_observation_count")
                or page.get("same_status_observation_count")
            ) >= 2
            for page in group
        )
        fixes.append(make_fix(
            rule="server_error" if is_server else "410_error" if bucket == "410" else "broken_page",
            category="web_dev" if is_server else "404_error",
            priority="high" if important_failed_pages(group, site_fingerprint) else "medium",
            title="Fix server errors found during the crawl" if is_server else "Fix confirmed broken URLs found during the crawl",
            explanation="The scanner found URLs that returned server errors during the crawl. These are technical availability problems, not copywriting tasks." if is_server else "The scanner found URLs that returned 404 or 410 during the crawl and included source evidence such as internal links, sitemap discovery, or linked failed URLs.",
            why="Server errors can prevent search engines and users from reaching important pages and can waste crawl budget." if is_server else "Broken internal links and confirmed failed URLs waste crawl budget and can send users or search engines into dead ends, especially when they are discovered from important pages.",
            recommendation="Ask your web person to inspect the failing URLs, server logs, and routing rules, then restore the page or redirect to the closest relevant live page." if is_server else "Ask your web person to either restore the missing URL, update the internal link that points to it, or add a 301 redirect to the closest relevant live page. Do not treat this as a meta title or content rewrite.",
            affected_pages=[page_evidence_url(page) for page in group],
            difficulty="developer",
            source=f"scanner_verified_failed_pages:{bucket}",
            extra={
                **evidence_extra(group),
                **({
                    "evidence_status": "needs_verification",
                    "verification_state": "needs_verification",
                    "limitation_code": "single_server_error_requires_confirmation",
                    "non_scoring": True,
                    "score_impact": 0,
                    "confidence_score": 68,
                } if is_server and not repeated_observation else {}),
                "failure_evidence_dedup_version": FAILURE_EVIDENCE_DEDUP_VERSION,
            },
        ))
    return fixes


def page_pattern_title(rule: str, family: str, is_group: bool) -> str:
    label = family_label(family)
    if rule == "canonical_missing":
        return f"Add canonical URLs to {label} pages" if is_group else "Add a canonical URL to the affected page"
    if rule == "image_alt_text":
        return f"Add missing image descriptions to {label} pages" if is_group else "Add missing image descriptions to the affected page"
    if rule == "missing_meta_description":
        return f"Add missing meta descriptions to {label} pages" if is_group else "Add a meta description to the affected page"
    if rule == "empty_meta_description":
        return f"Fill empty meta descriptions on {label} pages" if is_group else "Fill the empty meta description on the affected page"
    if rule == "malformed_meta_description":
        return f"Fix malformed meta descriptions on {label} pages" if is_group else "Fix malformed meta-description markup"
    if rule == "missing_h1":
        return f"Add H1 headings to {label} pages" if is_group else "Add an H1 to the affected page"
    if rule == "multiple_h1":
        return f"Use one main heading on {label} pages" if is_group else "Use one main heading on the affected page"
    return f"Fix the repeated {label} page issue" if is_group else "Fix the affected page issue"


META_DESCRIPTION_STATE_CONFIG = {
    "missing": {
        "rule": "missing_meta_description",
        "count_key": "missing",
        "count_label": "missing tags",
        "explanation": "The page has no standard meta-description element.",
        "why": "Search descriptions can improve how pages appear in search results.",
        "recommendation": "Add a short description that explains the page and why someone should click.",
    },
    "present_empty": {
        "rule": "empty_meta_description",
        "count_key": "empty",
        "count_label": "empty values",
        "explanation": "A meta-description element exists, but its content value is empty.",
        "why": "An empty description gives search engines no page-specific summary to use.",
        "recommendation": "Populate the existing description field with a concise, page-specific summary.",
    },
    "malformed": {
        "rule": "malformed_meta_description",
        "count_key": "malformed",
        "count_label": "malformed elements",
        "explanation": "A meta-description element exists without a usable content attribute.",
        "why": "Malformed metadata may be ignored by search engines and auditing tools.",
        "recommendation": 'Output one valid meta name="description" element with a non-empty content value.',
    },
}
META_DESCRIPTION_RULE_ORDER = (
    "missing_meta_description",
    "empty_meta_description",
    "malformed_meta_description",
)


def add_metadata_bucket(buckets: dict[tuple[str, str], dict[str, Any]], family: str, page: dict[str, Any], state: str) -> None:
    config = META_DESCRIPTION_STATE_CONFIG[state]
    key = ("meta_description_unusable", family)
    if key not in buckets:
        buckets[key] = {
            "rule": "meta_description_unusable",
            "category": "meta_description",
            "family": family,
            "pages": [],
            "difficulty": "easy",
            "metadata_state_counts": {"missing": 0, "empty": 0, "malformed": 0},
            "metadata_rules": [],
        }
    bucket = buckets[key]
    bucket["pages"].append(page)
    bucket["metadata_state_counts"][config["count_key"]] += 1
    if config["rule"] not in bucket["metadata_rules"]:
        bucket["metadata_rules"].append(config["rule"])


def metadata_state_summary(counts: dict[str, Any]) -> str:
    labels = {"missing": "missing tags", "empty": "empty values", "malformed": "malformed elements"}
    return ", ".join(
        f"{int_or_zero(counts.get(key))} {label}"
        for key, label in labels.items()
        if int_or_zero(counts.get(key)) > 0
    )


def metadata_bucket_copy(bucket: dict[str, Any], is_group: bool) -> dict[str, Any]:
    family = bucket["family"]
    label = family_label(family)
    counts = dict(bucket.get("metadata_state_counts") or {})
    total = sum(int_or_zero(counts.get(key)) for key in ("missing", "empty", "malformed"))
    rules = [rule for rule in META_DESCRIPTION_RULE_ORDER if rule in set(bucket.get("metadata_rules") or [])]
    output_rule = "meta_description_unusable" if len(rules) > 1 else (rules[0] if rules else "missing_meta_description")
    if not is_group:
        state_config = next((item for item in META_DESCRIPTION_STATE_CONFIG.values() if item["rule"] == output_rule), META_DESCRIPTION_STATE_CONFIG["missing"])
        return {
            "rule": output_rule,
            "title": page_pattern_title(output_rule, family, False),
            "explanation": state_config["explanation"],
            "why": state_config["why"],
            "recommendation": state_config["recommendation"],
            "grouping_explanation": "",
            "combined_rules": [],
        }

    state_summary = metadata_state_summary(counts)
    title = f"Add usable meta descriptions to {label} pages" if len(rules) > 1 else page_pattern_title(output_rule, family, True)
    return {
        "rule": output_rule,
        "title": title,
        "explanation": f"FixList found {state_summary} across {total} {label} pages. These URLs use the same page pattern, so repair the shared metadata output instead of editing every URL separately.",
        "why": "Meta descriptions can appear beneath page titles in search results. Missing, empty, or malformed output leaves search engines to create their own snippet, which can be less specific or persuasive. Fixing the shared template improves the whole affected group.",
        "recommendation": "Repair the shared metadata template so every affected page outputs exactly one non-empty, page-specific, plain-text meta description, with a reliable fallback when the dedicated SEO field is blank.",
        "grouping_explanation": f"These {total} URLs use the {label} page pattern. One shared template correction can resolve the reported metadata states across the group.",
        "combined_rules": rules if len(rules) > 1 else [],
    }


def build_page_pattern_findings(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for page in pages:
        url = page_evidence_url(page)
        if not url or is_non_html_page_evidence(page) or not page_has_usable_html(page):
            continue
        family = normalize_template_family(page.get("page_template_family"), url)
        canonical = clean_str(page.get("canonical") or page.get("canonical_url") or "")
        if not canonical:
            add_bucket(buckets, "canonical_missing", "canonical", family, page, "Add canonical URLs across templates", "The page does not expose a canonical URL.", "Canonical URLs help search engines consolidate duplicate and near-duplicate versions of a page.", "Ask your web person to add self-referencing canonicals to the shared template or affected pages.", "developer")
        h1_count = int_or_zero(page.get("h1_count"))
        if h1_count == 0:
            add_bucket(buckets, "missing_h1", "thin_content", family, page, "Fix missing H1 headings on templates", "The page has no main H1 heading.", "A clear H1 helps users and search engines understand the page topic.", "Add one clear H1 to the affected template or page.", "moderate")
        elif h1_count > 1:
            add_bucket(buckets, "multiple_h1", "thin_content", family, page, "Use one main page heading", "The page has more than one H1 heading.", "Multiple H1s can make the page structure less clear.", "Keep one H1 as the main page heading and make the rest H2/H3 headings.", "easy")
        missing_alt = int_or_zero(page.get("image_missing_alt_count") or page.get("missing_alt_image_count"))
        if missing_alt > 0:
            add_bucket(buckets, "image_alt_text", "image_alt_text", family, page, "Batch image descriptions on templates", f"{missing_alt} images missing alt text", "Repeated image-alt gaps are usually a shared template or CMS pattern, especially on listing or detail pages.", "Fix one representative page/template first, then roll out the same rule across the affected group.", "developer" if missing_alt >= 8 else "easy")
        metadata_state = clean_str(page.get("meta_description_state"))
        if not metadata_state:
            metadata_state = "present_valid" if clean_str(page.get("meta_description")) else "missing"
        if metadata_state in META_DESCRIPTION_STATE_CONFIG:
            add_metadata_bucket(buckets, family, page, metadata_state)

    fixes = []
    for bucket in buckets.values():
        affected = [page_evidence_url(page) for page in bucket["pages"]]
        affected_count = len(set(map(clean_path, affected)))
        is_group = affected_count > 1
        metadata_counts = bucket.get("metadata_state_counts")
        if isinstance(metadata_counts, dict):
            copy = metadata_bucket_copy(bucket, is_group)
            output_rule = copy["rule"]
            title = copy["title"]
            explanation = copy["explanation"]
            why = copy["why"]
            recommendation = copy["recommendation"]
            grouping_explanation = copy["grouping_explanation"]
            combined_rules = copy["combined_rules"]
        else:
            output_rule = bucket["rule"]
            title = page_pattern_title(output_rule, bucket["family"], is_group)
            explanation = (
                f"FixList found the same issue on {affected_count} {family_label(bucket['family'])} pages: {bucket['explanation']} Fix the shared template or pattern instead of editing each URL separately."
                if is_group else bucket["explanation"]
            )
            why = (
                f"{bucket['why']} Because the issue repeats across one page pattern, a shared correction has broader impact than isolated page edits."
                if is_group else bucket["why"]
            )
            recommendation = bucket["recommendation"]
            grouping_explanation = (
                f"These {affected_count} URLs use the {family_label(bucket['family'])} page pattern. One shared template correction may resolve the issue across the group."
                if is_group else ""
            )
            combined_rules = []
            metadata_counts = {"missing": 0, "empty": 0, "malformed": 0}

        fixes.append(make_fix(
            rule=output_rule,
            category=bucket["category"],
            priority="critical" if bucket["category"] == "canonical" else "high" if len(bucket["pages"]) >= 8 else "medium",
            title=title,
            explanation=explanation,
            why=why,
            recommendation=recommendation,
            affected_pages=affected,
            difficulty="developer" if (is_group and output_rule == "image_alt_text") or affected_count >= 5 else bucket["difficulty"],
            source=f"page_pattern:{output_rule}:{bucket['family']}",
            extra={
                "current_value": metadata_state_summary(metadata_counts) if any(int_or_zero(metadata_counts.get(key)) for key in ("missing", "empty", "malformed")) else template_current_value(affected),
                "defect_summary": explanation,
                "source_pages": dedupe_strings([clean_path(u) for u in affected if clean_path(u)])[:30],
                "page_template_family": bucket["family"],
                "page_count": affected_count,
                "metadata_state_counts": metadata_counts,
                "combined_rules": combined_rules,
                "grouping_explanation": grouping_explanation,
                "grouped_recommendation_evidence_version": GROUPED_RECOMMENDATION_EVIDENCE_VERSION,
            },
        ))
    return fixes


def add_bucket(buckets: dict[tuple[str, str], dict[str, Any]], rule: str, category: str, family: str, page: dict[str, Any], title: str, explanation: str, why: str, recommendation: str, difficulty: str) -> None:
    key = (rule, family)
    if key not in buckets:
        buckets[key] = {"rule": rule, "category": category, "family": family, "pages": [], "title": title, "explanation": explanation, "why": why, "recommendation": recommendation, "difficulty": difficulty, "current_value": explanation}
    buckets[key]["pages"].append(page)

def build_strategic_findings(body: dict[str, Any], pages: list[dict[str, Any]], website_url: str, site_fingerprint: dict[str, Any], playbook: dict[str, Any]) -> list[dict[str, Any]]:
    fixes = []
    if safe_hostname(website_url).endswith(".base44.app"):
        fixes.append(make_fix("free_base44_subdomain", "indexability", "high", "Move production SEO to a custom domain", "The site is on a free Base44 subdomain. That can be crawled, but it is not the strongest production SEO or trust setup.", "A custom domain improves brand trust, shareability, Search Console ownership, and company-specific search signals.", "Connect a branded custom domain before treating this as the long-term production SEO home.", ["/"], "developer", "archetype_strategy_layer", extra={"current_value": f"Production site served from {safe_hostname(website_url)} (free Base44 subdomain).", "source_pages": ["/"]}))
    def is_route_page(page: dict[str, Any]) -> bool:
        # Trust the scanner's authoritative classification when it supplied one.
        stamped = page.get("route_boundary_candidate")
        if isinstance(stamped, bool):
            return stamped
        url = page_evidence_url(page)
        return is_route_boundary_candidate(url) or is_internal_app_route(url)

    route_pages = [page for page in pages if is_route_page(page) and page_is_indexable(page)]
    if route_pages:
        fixes.append(make_fix("route_boundary_candidate_indexable", "indexability", "critical", "Keep checkout, login, account, and app routes out of search", "FixList found checkout, login, account, dashboard, billing, cart, admin, or app-like routes that appear crawlable and indexable.", "These pages are usually not useful SEO landing pages. Letting them appear in search can dilute the site, confuse prospects, or expose private product structure.", "Ask your web person to require login, add noindex, or keep these routes out of public search while preserving true public landing, category, product, booking, and help pages.", [page_evidence_url(page) for page in route_pages], "developer", "archetype_route_boundary_layer", extra={"current_value": "Indexable app/checkout/account routes: " + ", ".join(dedupe_strings([clean_path(page_evidence_url(page)) for page in route_pages])[:6]), "source_pages": dedupe_strings([clean_path(page_evidence_url(page)) for page in route_pages])[:30]}))
    trust_sensitive = site_fingerprint["regulatory_sensitivity"] != "standard" or site_fingerprint["primary_archetype"] == "saas_app_membership"
    has_trust = any(clean_path(page_evidence_url(page)).lower().startswith(tuple(TRUST_PATHS)) for page in pages)
    if trust_sensitive and pages and not has_trust:
        fixes.append(make_fix("missing_trust_pages", "schema", "high" if site_fingerprint["regulatory_sensitivity"] != "standard" else "medium", "Add public trust pages", f"For a {playbook['label']} site, visitors and crawlers need clear trust, legal, contact, and ownership signals.", "Trust pages help buyers, search engines, and AI systems understand who runs the site and whether it is credible.", "Add or expose clear About, Contact, Privacy, Terms, and Security/Trust pages, then link them from the footer.", ["/"], "moderate", "archetype_trust_layer", extra={"current_value": f"No public trust pages (About/Contact/Privacy/Terms) found among {len(pages)} crawled pages.", "source_pages": ["/"]}))
    return fixes


SITEWIDE_COLLAPSE_RULES = {"canonical_missing"}
SITEWIDE_MIN_FAMILIES = 3
SITEWIDE_MIN_PAGES = 10
SITEWIDE_MIN_AFFECTED_RATIO = 0.80
SITEWIDE_MIN_DISCOVERY_COVERAGE = 0.50


def sitewide_collapse_evidence_is_sufficient(site_fingerprint: dict[str, Any]) -> bool:
    """Require a healthy, materially complete crawl before making a site-wide claim."""
    if evidence_is_incomplete(site_fingerprint) or crawl_is_blocked(site_fingerprint):
        return False
    received = int_or_zero(site_fingerprint.get("pages_received"))
    crawled = int_or_zero(site_fingerprint.get("pages_crawled"))
    found = int_or_zero(site_fingerprint.get("pages_found"))
    if received < SITEWIDE_MIN_PAGES:
        return False
    if crawled > 0 and (received / crawled) < 0.80:
        return False
    if found > 0 and crawled > 0 and (crawled / found) < SITEWIDE_MIN_DISCOVERY_COVERAGE:
        return False
    return True


def collapse_sitewide_template_findings(
    fixes: list[dict[str, Any]],
    pages: list[dict[str, Any]],
    site_fingerprint: dict[str, Any],
    body: dict[str, Any],
    playbook: dict[str, Any],
) -> list[dict[str, Any]]:
    """Collapse one global implementation fault without erasing per-family evidence."""
    if not sitewide_collapse_evidence_is_sufficient(site_fingerprint):
        return fixes

    usable_pages = {
        clean_path(page_evidence_url(page))
        for page in pages
        if clean_path(page_evidence_url(page))
        and not is_blocked_access_page(page)
        and int_or_zero(page.get("status_code") or page.get("status")) < 400
        and page_is_indexable(page)
    }
    if len(usable_pages) < SITEWIDE_MIN_PAGES:
        return fixes

    page_lookup = {
        clean_path(page_evidence_url(page)): page
        for page in pages
        if clean_path(page_evidence_url(page))
    }
    output = list(fixes)
    for rule in SITEWIDE_COLLAPSE_RULES:
        candidates = [
            fix
            for fix in output
            if str(fix.get("rule") or "") == rule
            and str(fix.get("source") or "").startswith("page_pattern:")
            and str(fix.get("page_scope") or "") not in {"sitewide", "cross_cutting"}
        ]
        families = {
            str(fix.get("page_template_family") or "")
            for fix in candidates
            if str(fix.get("page_template_family") or "") not in {"", "mixed", "sitewide"}
        }
        affected = dedupe_strings([
            clean_path(url)
            for fix in candidates
            for url in (fix.get("affected_pages") or [])
            if clean_path(url)
        ])
        affected_usable = [url for url in affected if url in usable_pages]
        coverage_ratio = len(affected_usable) / max(1, len(usable_pages))
        if (
            len(families) < SITEWIDE_MIN_FAMILIES
            or len(affected_usable) < SITEWIDE_MIN_PAGES
            or coverage_ratio < SITEWIDE_MIN_AFFECTED_RATIO
        ):
            continue

        family_breakdown: dict[str, int] = {}
        representative_pages_by_family: dict[str, list[str]] = {}
        for fix in candidates:
            family = str(fix.get("page_template_family") or "standard")
            family_pages = dedupe_strings([
                clean_path(url)
                for url in (fix.get("affected_pages") or [])
                if clean_path(url) and clean_path(url) in usable_pages
            ])
            if not family_pages:
                continue
            family_breakdown[family] = family_breakdown.get(family, 0) + len(family_pages)
            representative_pages_by_family[family] = dedupe_strings(
                representative_pages_by_family.get(family, []) + family_pages
            )[:3]

        representative_pages = dedupe_strings([
            pages_for_family[0]
            for _, pages_for_family in sorted(representative_pages_by_family.items())
            if pages_for_family
        ])
        base = max(candidates, key=fix_sort_key)
        original_position = {url: index for index, url in enumerate(affected_usable)}
        ranked_affected = sorted(
            affected_usable,
            key=lambda url: (
                representative_page_score(url, {**base, "rule": rule}, page_lookup, body, playbook),
                -original_position[url],
            ),
            reverse=True,
        )
        ranked_source_pages = sorted(
            representative_pages,
            key=lambda url: representative_page_score(
                url, {**base, "rule": rule}, page_lookup, body, playbook
            ),
            reverse=True,
        )
        collapse_id = stable_id(
            f"sitewide|{rule}|{','.join(sorted(families))}|{len(affected_usable)}|{len(usable_pages)}"
        )
        title = "Add canonical URLs across the site"
        explanation = (
            "Canonical URLs are missing across nearly every indexable page in the scanned evidence. "
            "This points to one global document-head or CMS template implementation issue, not separate page-family problems."
        )
        why = (
            "Without consistent canonical URLs, search engines have a weaker signal for which public URL should represent each page. "
            "Because the same gap spans multiple page families, one global implementation fix should resolve it."
        )
        recommendation = (
            "Ask your web person to add a self-referencing canonical URL in the global document head or shared layout, "
            "then verify representative pages from every affected family."
        )
        steps = [
            "Open the global document head, root layout, or shared CMS template that renders canonical tags.",
            "Add one self-referencing canonical URL based on each page's final public URL.",
            "Verify at least one representative page from every affected family listed in the card.",
            "Publish the global change and run FixList again to confirm the site-wide canonical gap is resolved.",
        ]
        collapsed = {
            **base,
            "id": collapse_id,
            "fix_id": collapse_id,
            "issue_title": title,
            "title": title,
            "plain_english_explanation": explanation,
            "plain_english_summary": explanation,
            "why_it_matters": why,
            "recommendation": recommendation,
            "recommended_value": recommendation,
            "ai_recommendation": recommendation,
            "simple_next_step": recommendation,
            "current_value": (
                f"{len(affected_usable)} of {len(usable_pages)} indexable pages in the crawl are missing canonical URLs "
                f"across {len(family_breakdown)} page families."
            ),
            "page_url": ranked_affected[0],
            "representative_page_url": ranked_affected[0],
            "representative_page_version": REPRESENTATIVE_PAGE_VERSION,
            "representative_page_reason": "Highest archetype-aware business-value page in the site-wide affected evidence.",
            "affected_pages": ranked_affected[:150],
            "source_pages": ranked_source_pages[:30],
            "page_count": len(affected_usable),
            "page_scope": "sitewide",
            "page_template_family": "",
            "family_breakdown": dict(sorted(family_breakdown.items())),
            "representative_pages_by_family": dict(sorted(representative_pages_by_family.items())),
            "sitewide_evidence": {
                "affected_indexable_pages": len(affected_usable),
                "indexable_pages_reviewed": len(usable_pages),
                "coverage_ratio": round(coverage_ratio, 3),
                "family_count": len(family_breakdown),
            },
            "source": f"review_sitewide_collapse:{rule}",
            "priority": "critical",
            "difficulty": "developer",
            "status": "needs_developer",
            "requires_developer": True,
            "requires_approval": False,
            "can_auto_fix": False,
            "who_can_do_this": "your_web_person",
            "what_to_do": steps,
            "what_to_do_steps": steps,
            "fix_steps": steps,
            "page_type": "site_level",
            "business_importance": "site_level",
            "is_low_value_page": False,
            "is_important_business_page": False,
            "page_value_score": 100,
            "page_value_label": "Site-wide setup",
            "primary_defect_class": "structural",
            "reach_score": 100,
            "overall_priority_score": max(96, max(int_or_zero(fix.get("overall_priority_score")) for fix in candidates)),
            "evidence_confidence": max(int_or_zero(fix.get("evidence_confidence")) for fix in candidates),
        }
        candidate_ids = {id(fix) for fix in candidates}
        output = [fix for fix in output if id(fix) not in candidate_ids]
        output.append(collapsed)
    return output


REPRESENTATIVE_PAGE_VERSION = "business_representative_page_v3_sitewide_archetype_ranking"
PAGE_LEVEL_ASSET_EVIDENCE_VERSION = "page_level_asset_evidence_v3_markdown"
DIRECT_EVIDENCE_RULES = {
    "broken_page", "404_error", "410_error", "server_error", "rate_limited_page",
    "blocked_page", "sitemap_redirect", "internal_link_redirect", "redirect_chain",
    "redirect_destination_noindex", "canonical_loop", "sitemap_indexability_conflict",
    "sitemap_canonicalized_url", "canonical_to_other_url", "canonical_to_other_domain",
    "route_boundary_candidate_indexable", "internal_route_indexable",
}
ROUTE_BOUNDARY_RULES = {"route_boundary_candidate_indexable", "internal_route_indexable"}
PAGE_LEVEL_HTML_ONLY_RULES = {
    "broken_page", "404_error", "410_error", "server_error", "rate_limited_page",
    "blocked_page", "missing_canonical", "canonical_to_other_url",
    "canonical_to_other_domain", "canonical_loop", "missing_h1",
    "missing_meta_description", "duplicate_title", "duplicate_meta_description",
}
UTILITY_ROUTE_PATTERNS = (
    "/contact", "/contact-us", "/about", "/privacy", "/terms", "/cookie",
    "/legal", "/ccpa", "/login", "/signin", "/signup", "/register",
    "/account", "/cart", "/checkout", "/basket", "/reservation/edit",
    "/reservation/manage", "/booking/edit", "/booking/manage",
)
ARCHETYPE_REPRESENTATIVE_PATTERNS = {
    "saas": ("/features", "/pricing", "/product", "/platform", "/integrations", "/use-cases", "/solutions", "/enterprise", "/payments", "/billing", "/connect", "/radar", "/terminal"),
    "ecommerce": ("/collections/", "/collection/", "/category/", "/categories/", "/shop/", "/products/", "/product/", "/eyeglasses", "/sunglasses", "/contacts"),
    "publisher": ("/category/", "/categories/", "/topic/", "/topics/", "/guides/", "/reviews/", "/news/", "/resources/"),
    "finance": ("/mortgage", "/loan", "/loans", "/credit-cards", "/banking", "/insurance", "/calculator"),
    "nonprofit": ("/projects", "/impact", "/programs", "/donate", "/fundraise"),
    "education": ("/courses", "/subjects", "/learn", "/math", "/science"),
    "booking": ("/activities", "/activity", "/experiences", "/events", "/category", "/collections"),
}


def is_non_html_page_evidence(page: dict[str, Any]) -> bool:
    raw_url = str(page_evidence_url(page) or "")
    url = (urlparse(raw_url).path or clean_path(raw_url)).lower()
    content_type = str(page.get("content_type") or page.get("mime_type") or "").lower()
    if content_type and "html" not in content_type and "xhtml" not in content_type:
        return True
    return any(url.endswith(extension) for extension in NON_HTML_ASSET_EXTENSIONS)


ORPHAN_FINDING_HINTS = ("orphan", "sitemap_only", "sitemap-only", "sitemap only")


def is_orphan_page_finding(fix: dict[str, Any]) -> bool:
    """Identify orphan/sitemap-only findings without matching every sitemap rule."""
    evidence = " ".join(
        str(fix.get(key) or "")
        for key in (
            "rule", "type", "issue_type", "source", "issue_title", "title",
            "plain_english_explanation", "plain_english_summary",
        )
    ).lower()
    return any(hint in evidence for hint in ORPHAN_FINDING_HINTS)


def filter_orphan_asset_evidence(
    fix: dict[str, Any],
    pages: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Remove non-HTML URLs from orphan findings; suppress asset-only groups."""
    if not is_orphan_page_finding(fix):
        return fix

    page_lookup = {
        clean_path(page_evidence_url(page)): page
        for page in pages
        if clean_path(page_evidence_url(page))
    }
    affected = dedupe_strings([
        clean_path(url)
        for url in (fix.get("affected_pages") or [fix.get("page_url") or "/"])
        if clean_path(url)
    ])
    html_pages = [
        url for url in affected
        if not is_non_html_page_evidence({**page_lookup.get(url, {}), "url": url})
    ]
    if not html_pages:
        return None

    def html_only(values: Any, limit: int) -> list[str]:
        if not isinstance(values, list):
            return []
        normalized = dedupe_strings([
            clean_path(value) for value in values if clean_path(value)
        ])
        return [
            url for url in normalized
            if not is_non_html_page_evidence({**page_lookup.get(url, {}), "url": url})
        ][:limit]

    selected_page = clean_path(fix.get("page_url") or "")
    if selected_page not in html_pages:
        selected_page = html_pages[0]
    representative = clean_path(fix.get("representative_page_url") or "")
    if representative not in html_pages:
        representative = selected_page

    return {
        **fix,
        "page_url": selected_page,
        "representative_page_url": representative,
        "affected_pages": html_pages,
        "source_pages": html_only(fix.get("source_pages"), 30),
        "supporting_evidence_pages": html_only(fix.get("supporting_evidence_pages"), 20),
        "page_count": len(html_pages),
        "asset_urls_excluded": max(0, len(affected) - len(html_pages)),
        "orphan_asset_evidence_version": ORPHAN_ASSET_EVIDENCE_VERSION,
    }

def filter_page_level_asset_evidence(
    fix: dict[str, Any],
    pages: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Keep generic page-level findings on HTML documents only."""
    rule = str(fix.get("rule") or "").lower()
    if rule not in PAGE_LEVEL_HTML_ONLY_RULES:
        return fix
    page_lookup = {
        clean_path(page_evidence_url(page)): page
        for page in pages
        if clean_path(page_evidence_url(page))
    }
    candidates = dedupe_strings([
        clean_path(url)
        for url in (fix.get("affected_pages") or [fix.get("page_url") or "/"])
        if clean_path(url)
    ])
    html_pages = [
        url for url in candidates
        if not is_non_html_page_evidence({**page_lookup.get(url, {}), "url": url})
    ]
    if not html_pages:
        return None
    selected = clean_path(fix.get("page_url") or "")
    if selected not in html_pages:
        selected = html_pages[0]
    return {
        **fix,
        "page_url": selected,
        "representative_page_url": selected,
        "affected_pages": html_pages,
        "page_count": len(html_pages),
        "asset_urls_excluded": int_or_zero(fix.get("asset_urls_excluded")) + max(0, len(candidates) - len(html_pages)),
        "page_level_asset_evidence_version": PAGE_LEVEL_ASSET_EVIDENCE_VERSION,
    }


def representative_archetype_key(playbook: dict[str, Any]) -> str:
    label = str(playbook.get("label") or "").lower()
    if any(token in label for token in ("saas", "software", "app", "platform")):
        return "saas"
    if any(token in label for token in ("ecommerce", "retail", "commerce")):
        return "ecommerce"
    if any(token in label for token in ("publisher", "content", "blog")):
        return "publisher"
    if any(token in label for token in ("finance", "insurance", "lending")):
        return "finance"
    if any(token in label for token in ("nonprofit", "fundraising", "charity")):
        return "nonprofit"
    if any(token in label for token in ("education", "learning")):
        return "education"
    if any(token in label for token in ("booking", "experience", "marketplace")):
        return "booking"
    return ""


def representative_page_score(
    url: str,
    fix: dict[str, Any],
    page_lookup: dict[str, dict[str, Any]],
    body: dict[str, Any],
    playbook: dict[str, Any],
) -> int:
    path = clean_path(url) or "/"
    lower = path.lower()
    page = page_lookup.get(path, {})
    rule = str(fix.get("rule") or "").lower()
    direct_evidence = rule in DIRECT_EVIDENCE_RULES
    requested = clean_path(
        body.get("requested_path_prefix")
        or body.get("crawl_path_prefix")
        or body.get("path_prefix")
        or ""
    )
    family = normalize_template_family(
        page.get("page_template_family") or fix.get("page_template_family"),
        path,
    )
    archetype = representative_archetype_key(playbook)

    score = 20
    if path in {"/", "/index.html"}:
        score += 75
    if requested and path.rstrip("/") == requested.rstrip("/"):
        score += 70
    if any(pattern in lower for pattern in playbook.get("money_patterns", [])):
        score += 35
    if family in {
        "homepage", "loan_program", "conversion", "calculator", "comparison_page",
        "product_page", "collection_page", "activity_detail", "location_landing",
        "guide_article",
    }:
        score += 25
    if family in {"collection_page", "category", "archive"} and archetype in {"ecommerce", "publisher", "booking"}:
        score += 25
    for pattern in ARCHETYPE_REPRESENTATIVE_PATTERNS.get(archetype, ()):
        if pattern in lower:
            score += 55
            break
    if clean_str(page.get("title")) or clean_str(page.get("h1")):
        score += 8
    if page_is_indexable(page):
        score += 5
    if any(pattern in lower for pattern in UTILITY_ROUTE_PATTERNS):
        score -= 95
    if is_low_value_page(path):
        score -= 65
    if is_non_html_page_evidence({**page, "url": path}):
        score -= 250
    if is_route_boundary_candidate(path) or is_internal_app_route(path):
        score += 15 if rule in ROUTE_BOUNDARY_RULES else -100
    status = int_or_zero(page.get("status_code") or page.get("status"))
    if status >= 400 or is_blocked_access_page(page):
        score += 15 if direct_evidence else -60
    elif direct_evidence:
        score += 5
    return score


def select_representative_page(
    fix: dict[str, Any],
    pages: list[dict[str, Any]],
    body: dict[str, Any],
    playbook: dict[str, Any],
) -> dict[str, Any]:
    affected = dedupe_strings([
        clean_path(url)
        for url in (fix.get("affected_pages") or [fix.get("page_url") or "/"])
        if clean_path(url)
    ]) or ["/"]
    page_lookup = {
        clean_path(page_evidence_url(page)): page
        for page in pages
        if clean_path(page_evidence_url(page))
    }
    original_position = {url: index for index, url in enumerate(affected)}
    ranked = sorted(
        affected,
        key=lambda url: (
            representative_page_score(url, fix, page_lookup, body, playbook),
            -original_position[url],
        ),
        reverse=True,
    )
    representative = ranked[0]
    reason = (
        "Direct issue evidence on the highest-value affected URL."
        if str(fix.get("rule") or "").lower() in DIRECT_EVIDENCE_RULES
        else "Highest business-value affected URL; utility, auth, archive, blocked, and asset URLs are retained as supporting evidence."
    )
    return {
        **fix,
        "page_url": representative,
        "affected_pages": ranked,
        "representative_page_url": representative,
        "representative_page_version": REPRESENTATIVE_PAGE_VERSION,
        "representative_page_reason": reason,
        "supporting_evidence_pages": ranked[1:21],
    }


HTML_DEPENDENT_RULES = {
    "canonical_missing", "missing_canonical", "missing_title", "generic_fallback_title",
    "title_over_pixel_limit", "duplicate_title", "duplicate_title_localized",
    "duplicate_title_query_variants", "duplicate_title_template",
    "missing_meta_description", "empty_meta_description", "malformed_meta_description",
    "meta_description_unusable", "duplicate_meta_description", "missing_h1", "multiple_h1", "schema",
    "structured_data", "thin_content", "image_alt_text", "missing_image_alt",
}


def filter_html_dependent_fix_evidence(fix: dict[str, Any], pages: list[dict[str, Any]]) -> dict[str, Any] | None:
    rule = str(fix.get("rule") or "").lower()
    if rule not in HTML_DEPENDENT_RULES:
        return fix
    lookup = {clean_path(page_evidence_url(page)): page for page in pages if clean_path(page_evidence_url(page))}
    affected = dedupe_strings([clean_path(url) for url in (fix.get("affected_pages") or [fix.get("page_url") or "/"]) if clean_path(url)])
    usable = [url for url in affected if page_has_usable_html(lookup.get(url, {}))]
    if not usable:
        return None
    return {**fix, "affected_pages": usable, "page_url": usable[0], "page_count": len(usable), "evidence_gate_version": PAGE_EVIDENCE_GATE_VERSION}


def prepare_fixes(raw_fixes: list[dict[str, Any]], site_fingerprint: dict[str, Any], body: dict[str, Any], playbook: dict[str, Any], pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = dedupe_fixes([normalize_fix(fix, index) for index, fix in enumerate(raw_fixes or []) if isinstance(fix, dict)])
    normalized = [candidate for fix in normalized if (candidate := filter_html_dependent_fix_evidence(fix, pages)) is not None]
    filtered = [filter_orphan_asset_evidence(fix, pages) for fix in normalized]
    normalized = [fix for fix in filtered if fix is not None]
    filtered = [filter_page_level_asset_evidence(fix, pages) for fix in normalized]
    normalized = [fix for fix in filtered if fix is not None]
    normalized = [select_representative_page(fix, pages, body, playbook) for fix in normalized]
    scored = [score_fix(fix, site_fingerprint, body, playbook, pages) for fix in normalized]
    scored = suppress_group_covered_singletons(scored)
    scored = suppress_duplicate_group_cards(scored)
    scored = collapse_sitewide_template_findings(scored, pages, site_fingerprint, body, playbook)
    return sorted(scored, key=fix_sort_key, reverse=True)[:36]

def normalize_fix(fix: dict[str, Any], index: int) -> dict[str, Any]:
    rule = clean_str(fix.get("rule") or fix.get("type") or fix.get("issue_type") or "review")
    category = CATEGORY_MAP.get(str(fix.get("category", ""))) or CATEGORY_MAP.get(rule) or clean_str(fix.get("category")) or infer_category(rule, fix)
    page_url = clean_path(fix.get("page_url") or fix.get("url") or fix.get("final_url") or first_value(fix.get("affected_pages")) or first_value(fix.get("pages")) or "/")
    affected = normalize_affected_pages(fix, page_url)
    difficulty = normalize_difficulty(fix)
    developer_owned = needs_developer_owner({**fix, "rule": rule, "category": category, "difficulty": difficulty, "affected_pages": affected})
    title = clean_str(fix.get("issue_title") or fix.get("title")) or default_title(category, rule)
    explanation = clean_str(fix.get("plain_english_explanation") or fix.get("explanation") or fix.get("summary") or fix.get("description")) or "This recommendation was found during the website scan."
    why = clean_str(fix.get("why_it_matters") or fix.get("why") or fix.get("impact")) or "Improving this helps visitors and search engines understand and access the site more clearly."
    recommendation = clean_str(fix.get("recommended_value") or fix.get("recommendation") or fix.get("ai_recommendation") or fix.get("suggested_fix")) or "Review and improve this item."
    fix_id = clean_str(fix.get("id") or fix.get("fix_id") or fix.get("fingerprint")) or stable_id(f"{rule}|{category}|{page_url}|{index}|{','.join(affected)}")
    steps = normalize_steps(fix) or default_steps(category, rule, "developer" if developer_owned else difficulty, recommendation)
    return {
        **fix,
        "id": fix_id,
        "fix_id": fix_id,
        "rule": rule,
        "category": category,
        "customer_category": fix.get("customer_category") or friendly_category(category),
        "issue_title": title,
        "title": title,
        "plain_english_explanation": explanation,
        "plain_english_summary": clean_str(fix.get("plain_english_summary") or fix.get("plain_english_explanation") or fix.get("explanation")) or explanation,
        "why_it_matters": why,
        "recommended_value": recommendation,
        "ai_recommendation": recommendation,
        "current_value": clean_str(fix.get("current_value") or fix.get("current") or (f"HTTP {fix.get('status_code')}" if fix.get("status_code") else "")),
        "page_url": page_url,
        "affected_pages": affected,
        "source_pages": (fix.get("source_pages") or [])[:20] if isinstance(fix.get("source_pages"), list) else [],
        "link_text_samples": (fix.get("link_text_samples") or [])[:10] if isinstance(fix.get("link_text_samples"), list) else [],
        "url_confidence": fix.get("url_confidence") or "",
        "url_suspicion_reasons": (fix.get("url_suspicion_reasons") or [])[:8] if isinstance(fix.get("url_suspicion_reasons"), list) else [],
        "priority": normalize_priority(fix.get("priority")),
        "difficulty": "developer" if developer_owned else difficulty,
        "status": "needs_developer" if developer_owned else fix.get("status") or ("auto_fixed" if fix.get("can_auto_fix") else "needs_approval"),
        "requires_developer": developer_owned or bool(fix.get("requires_developer")),
        "requires_approval": False if developer_owned else fix.get("requires_approval") is not False,
        "can_auto_fix": bool(fix.get("can_auto_fix")) and not developer_owned,
        "what_to_do": steps,
        "what_to_do_steps": steps,
        "fix_steps": steps,
        "who_can_do_this": "your_web_person" if developer_owned else normalize_owner(fix.get("who_can_do_this")),
        "estimated_time": clean_str(fix.get("estimated_time") or fix.get("time_estimate")) or default_time("developer" if developer_owned else difficulty),
        "time_estimate": clean_str(fix.get("time_estimate") or fix.get("estimated_time")) or default_time("developer" if developer_owned else difficulty),
        "confidence_score": fix.get("confidence_score") if isinstance(fix.get("confidence_score"), (int, float)) else 88,
    }


def is_cross_cutting_evidence(fix: dict[str, Any]) -> bool:
    """HTTP/crawler-access evidence groups by failure mode, not page template."""
    source = str(fix.get("source", ""))
    rule = str(fix.get("rule", ""))
    if source.startswith("scanner_verified_failed_pages:"):
        return True
    return rule in {"rate_limited_page", "broken_page", "server_error", "blocked_page"}


def score_fix(
    fix: dict[str, Any],
    site_fingerprint: dict[str, Any],
    body: dict[str, Any],
    playbook: dict[str, Any],
    pages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    # The caller already holds the authoritative page list; deriving it from
    # body keys here was guessing at the payload shape and silently resolved
    # every affected URL to "unknown".
    scope_evidence = normalize_repair_scope(
        fix,
        pages if pages is not None else (body.get("crawled_pages") or body.get("pages") or []),
        family_resolver=normalize_template_family,
    )
    page_url = clean_path(fix.get("page_url") or first_value(fix.get("affected_pages")) or "/")
    page_value = score_page_value(page_url, site_fingerprint, body, playbook)
    defect_class = classify_defect_class(fix)
    evidence_confidence = score_evidence_confidence(fix)
    reach_score = max(5, min(100, len(fix.get("affected_pages") or [1]) * 10))
    structural_boost = 18 if defect_class in {"structural", "crawl_index", "blocked_access"} else 0
    trust_boost = 12 if site_fingerprint["regulatory_sensitivity"] != "standard" and defect_class in {"content_trust", "semantic_schema", "crawl_index", "structural"} else 0
    overall = round(evidence_confidence * 0.22 + page_value["score"] * 0.26 + reach_score * 0.14 + structural_boost + trust_boost + 24)
    rule = str(fix.get("rule") or "").lower()
    if fix.get("url_confidence") == "crawler_artifact":
        overall = min(overall, 44)
    if page_value["classification"] == "internal_or_auth_route" and rule in ROUTE_BOUNDARY_RULES:
        overall = min(overall, 72)
    if rule in RATE_LIMIT_RULES and fix.get("verification_state") == "needs_verification":
        overall = min(overall, 72 if page_value["score"] >= 70 else 62)
    overall = max(0, min(100, overall))
    priority = "critical" if fix.get("priority") == "critical" or overall >= 82 else "high" if overall >= 68 else "medium" if overall >= 44 else "low"
    if page_value["classification"] == "internal_or_auth_route" and rule in ROUTE_BOUNDARY_RULES and priority == "critical":
        priority = "high"
    if rule in RATE_LIMIT_RULES and page_value["score"] < 70 and priority in {"critical", "high"}:
        priority = "medium"
    developer_owned = needs_developer_owner({**fix, "primary_defect_class": defect_class})
    affected_pages = dedupe_strings([clean_path(u) for u in (fix.get("affected_pages") or [page_url]) if clean_path(u)]) or ["/"]
    source_pages = dedupe_strings([clean_path(u) for u in (fix.get("source_pages") if isinstance(fix.get("source_pages"), list) else []) if clean_path(u)]) or affected_pages
    link_text_samples = [clean_str(x) for x in (fix.get("link_text_samples") if isinstance(fix.get("link_text_samples"), list) else []) if clean_str(x)][:12]
    return {
        **fix,
        "affected_pages": affected_pages[:150],
        "source_pages": source_pages[:30],
        "link_text_samples": link_text_samples,
        "current_value": clean_str(fix.get("current_value")) or template_current_value(affected_pages),
        "priority": priority,
        "page_type": page_value["classification"],
        # Scope and family come from normalize_repair_scope, which reads the
        # family stamped on authoritative page evidence. The previous inline
        # rule fell back to the representative's own family, which is how a
        # mixed group came to be labelled Homepage.
        "page_scope": scope_evidence["page_scope"],
        "page_template_family": scope_evidence["page_template_family"],
        "page_count": scope_evidence["page_count"],
        "family_breakdown": scope_evidence["family_breakdown"],
        "representative_pages_by_family": scope_evidence["representative_pages_by_family"],
        "affected_pages_complete": scope_evidence["affected_pages_complete"],
        "repair_coverage_version": scope_evidence["repair_coverage_version"],
        "page_value_score": page_value["score"],
        "page_value_label": page_value["label"],
        "primary_defect_class": defect_class,
        "meta_rewrite_allowed": False,
        "meta_regeneration_gate": "not_metadata_primary_gap",
        "business_importance": page_value["classification"],
        "is_low_value_page": is_low_value_page(page_url),
        "is_important_business_page": fix.get("is_important_business_page") if isinstance(fix.get("is_important_business_page"), bool) else False,
        "evidence_confidence": evidence_confidence,
        "reach_score": reach_score,
        "overall_priority_score": overall,
        "site_fingerprint_vertical": site_fingerprint["primary_archetype"],
        "archetype_label": site_fingerprint["archetype_label"],
        "requires_developer": developer_owned or bool(fix.get("requires_developer")),
        "difficulty": "developer" if developer_owned else fix.get("difficulty"),
        "status": "needs_developer" if developer_owned else fix.get("status"),
        "who_can_do_this": "your_web_person" if developer_owned else fix.get("who_can_do_this"),
    }


RATE_LIMIT_RULES = {"rate_limited_page", "blocked_page"}


def has_rate_limit_evidence(fixes: list[dict[str, Any]]) -> bool:
    return any(
        str(fix.get("rule") or "") in RATE_LIMIT_RULES
        or str(fix.get("source") or "").startswith("scanner_verified_failed_pages:429")
        for fix in fixes
    )


def build_review_payload(body: dict[str, Any], pages: list[dict[str, Any]], fixes: list[dict[str, Any]], site_fingerprint: dict[str, Any], playbook: dict[str, Any], website_url: str) -> dict[str, Any]:
    incomplete = evidence_is_incomplete(site_fingerprint)
    blocked = crawl_is_blocked(site_fingerprint)
    # Coverage insufficiency IS insufficient evidence, so it must reach the
    # customer-facing state rather than being swallowed by the incompleteness
    # guard -- incompleteness is now largely driven by coverage itself.
    coverage_insufficient = coverage_state_for_fingerprint(site_fingerprint) in {
        "limited_coverage",
        "inventory_unproven",
    }
    insufficient = bool(
        not blocked
        and (
            coverage_insufficient
            or (
                site_fingerprint.get("classification_state") == "inconclusive_insufficient_evidence"
                and not incomplete
            )
        )
    )
    rate_limited = has_rate_limit_evidence(fixes)
    quality = review_input_quality(body, site_fingerprint)
    usable_page_count = int_or_zero(site_fingerprint.get("classification", {}).get("usable_pages"))
    complete_small_site_inventory = bool(site_fingerprint.get("classification", {}).get("complete_small_site_inventory"))
    health_score_status = "available" if usable_page_count >= 4 or complete_small_site_inventory else "insufficient_evidence"
    health_score = compute_health_score(fixes, site_fingerprint) if health_score_status == "available" else None
    if insufficient and health_score is not None:
        health_score = min(55, health_score)
    blocked_count = int_or_zero(site_fingerprint.get("blocked_or_429_pages"))
    reviewed_count = max(
        int_or_zero(site_fingerprint.get("pages_received")),
        int_or_zero(site_fingerprint.get("pages_crawled")),
    )
    blocked_ratio = blocked_count / max(1, reviewed_count)
    material_access_limited = rate_limited and not blocked and blocked_ratio >= 0.10

    crawled_count = int_or_zero(site_fingerprint.get("pages_crawled"))
    crawled_noun = "page" if crawled_count == 1 else "pages"
    summary = f"FixList recognized this as {playbook['label']} and used the {playbook['label']} playbook. The scanner reviewed {site_fingerprint['pages_crawled']} {crawled_noun}"
    if site_fingerprint.get("pages_found"):
        summary += f" out of about {site_fingerprint['pages_found']} discovered URLs"
    summary += f". Start with the highest-impact items on {', '.join(playbook['priority_pages'][:3])}."
    if blocked:
        summary = (
            f"FixList could not complete a reliable page-quality review because {blocked_count} of {reviewed_count or blocked_count} reviewed "
            f"{'page' if (reviewed_count or blocked_count) == 1 else 'pages'} "
            "returned access blocks, rate limiting, bot-protection, or connection-verification responses. The score is provisional until server, CDN, "
            "firewall, or bot-protection logs confirm legitimate crawler access."
        )
    elif incomplete:
        summary = INCOMPLETE_REVIEW_WARNING
    elif insufficient:
        summary = (
            f"FixList received only {site_fingerprint.get('classification', {}).get('usable_pages', 0)} usable pages. "
            "That is not enough evidence to assign a reliable site type or health grade, so this result is provisional."
        )
    elif material_access_limited:
        summary += (
            f" {blocked_count or 1} reviewed page{'s' if (blocked_count or 1) != 1 else ''} returned HTTP 429 or an access-verification response. "
            "The affected share is material, so the score is provisional until those results are checked in access logs."
        )
    elif rate_limited:
        summary += (
            f" {blocked_count or 1} reviewed page{'s' if (blocked_count or 1) != 1 else ''} returned HTTP 429 or an access-verification response. "
            "This records what the scanner encountered and does not by itself prove that normal customers see an error."
        )

    working = [f"FixList detected a {playbook['label']} pattern."] if site_fingerprint["primary_archetype"] != "general" and not insufficient else []
    top_concerns = [fix.get("issue_title") or fix.get("title") for fix in fixes[:3] if fix.get("issue_title") or fix.get("title")]
    quick_wins = [fix.get("issue_title") or fix.get("title") for fix in fixes if fix.get("difficulty") != "developer"][:3]
    bigger_projects = [fix.get("issue_title") or fix.get("title") for fix in fixes if fix.get("difficulty") == "developer" or fix.get("requires_developer")][:3]
    limitations = [
        "This scan is read-only and cannot confirm private analytics, paid search data, conversions, or server logs."
    ]
    # A limited result that does not say why it is limited is not a truthful
    # result. The evidence-quality gate only writes a limitation when it is the
    # thing doing the blocking; when the review has already marked the scan
    # provisional the gate short-circuits, and the customer was left with a
    # provisional score and no stated reason.
    coverage_limitation = coverage_limitation_text(site_fingerprint)
    if coverage_limitation:
        limitations.append(coverage_limitation)
    if rate_limited:
        limitations.append(
            "HTTP 429 and connection-verification results need access-log confirmation before being treated as confirmed broken customer pages."
        )

    access_evidence_state = (
        "blocked"
        if blocked
        else "insufficient_evidence"
        if insufficient
        else "partial_access_limited"
        if material_access_limited
        else "incidental_access_limited"
        if rate_limited
        else "complete"
    )
    review_confidence_state = (
        "blocked_access_needs_verification"
        if blocked
        else "incomplete_evidence"
        if incomplete
        else "insufficient_evidence"
        if insufficient
        else "partial_access_needs_verification"
        if material_access_limited
        else "complete_with_incidental_access_checks"
        if rate_limited
        else "complete"
    )
    scan_status = (
        "blocked_or_incomplete"
        if blocked
        else "incomplete_evidence"
        if incomplete
        else "inconclusive_insufficient_evidence"
        if insufficient
        else "complete_with_access_limitations"
        if material_access_limited
        else "complete"
    )
    score_is_provisional = bool(blocked or incomplete or insufficient or material_access_limited)
    release_gate_eligible = not score_is_provisional

    report = {
        "health_score": health_score,
        "score": health_score,
        "overall_explanation": summary,
        "health_grade": "Blocked / incomplete" if blocked else "Scan incomplete" if incomplete else "Insufficient evidence" if insufficient else "Score unavailable" if health_score is None else "Strong" if health_score >= 85 else "Good" if health_score >= 70 else "Needs work" if health_score >= 50 else "Major issues",
        "health_score_status": health_score_status,
        "usable_page_count": usable_page_count,
        "what_is_working": working,
        "top_concerns": top_concerns,
        "quick_wins": quick_wins,
        "bigger_projects": bigger_projects,
        "limitations": limitations,
        "coverage_limitation": coverage_limitation,
        "next_best_step": "Ask your web person to verify crawler access, rate limits, CDN, firewall, and bot-protection settings." if blocked else "Re-run the scan — page evidence did not reach AI Review." if incomplete else "Run a deeper scan or verify crawler access so FixList can review at least four usable pages." if insufficient else ((fixes[0].get("issue_title") or fixes[0].get("title")) if fixes else "Review the first FixList item."),
        "scan_status": scan_status,
        "review_confidence_state": review_confidence_state,
        "score_is_provisional": score_is_provisional,
        "access_evidence_state": access_evidence_state,
        "release_gate_eligible": release_gate_eligible,
    }
    pages_returned = pages[:80]
    return {
        "limitation": coverage_limitation,
        "plain_english_summary": summary,
        "website_health_report": report,
        "health_explanation": summary,
        "customer_summary": summary,
        "top_recommended_actions": fixes[:5],
        "recommended_actions": fixes,
        "cleaned_fixes": fixes,
        "raw_fixes": fixes,
        "fixes": fixes,
        "findings": fixes,
        "recommendations": fixes,
        "competitor_insights": [],
        "grouped_page_recommendations": group_page_recommendations(fixes),
        "ignored_low_value_pages": [clean_path(page_evidence_url(page)) for page in pages if is_low_value_page(page_evidence_url(page))][:30],
        "positive_findings": working,
        "ai_rewrites_applied": 0,
        "crawled_pages": pages_returned,
        "pages": pages_returned,
        "health_score": health_score,
        "health_score_status": health_score_status,
        "usable_page_count": usable_page_count,
        "page_evidence_gate_version": PAGE_EVIDENCE_GATE_VERSION,
        "site_fingerprint": {**site_fingerprint, "review_input_quality": quality},
        "review_input_quality": {**quality, "access_evidence_state": access_evidence_state, "score_is_provisional": score_is_provisional},
        "review_quality_gate_version": QUALITY_GATE_VERSION,
        "evidence_complete": not (incomplete or insufficient),
        "scan_status": scan_status,
        "review_confidence_state": review_confidence_state,
        "score_is_provisional": score_is_provisional,
        "access_evidence_state": access_evidence_state,
        "release_gate_eligible": release_gate_eligible,
        "archetype_classifier_version": ARCHETYPE_CLASSIFIER_VERSION,
        "archetype_playbook": {
            "label": playbook["label"],
            "priority_pages": playbook["priority_pages"],
            "priority_issues": playbook["priority_issues"],
            "demote": playbook["demote"],
            "owner_rule": playbook["owner_rule"],
        },
        "technical_audit_summary": body.get("technical_audit_summary"),
        "screaming_frog_lite_enabled": bool(body.get("screaming_frog_lite_enabled")),
        "audit_profile": clean_str(body.get("scanner_profile") or body.get("audit_profile") or ""),
        "scanner_version": body.get("scanner_version") or body.get("version") or "",
        "advanced_scan_backend": body.get("advanced_scan_backend") or deep_get(body, "technical_audit_summary", "advanced_scan_backend") or "",
        "deno_fallback_used": bool(body.get("deno_fallback_used") or deep_get(body, "technical_audit_summary", "deno_fallback_used")),
        "website_url": website_url,
        "seo_score": health_score,
        "simple_summary": summary,
        "scanned_pages": pages_returned,
        "scan_summary": {
            "health_score": health_score,
            "score": health_score,
            "health_score_status": health_score_status,
            "usable_page_count": usable_page_count,
            "pages_scanned": site_fingerprint["pages_crawled"],
            "plain_english_summary": summary,
            "site_fingerprint": site_fingerprint,
            "review_input_quality": quality,
            "scan_status": scan_status,
            "review_confidence_state": review_confidence_state,
            "score_is_provisional": score_is_provisional,
            "access_evidence_state": access_evidence_state,
            "release_gate_eligible": release_gate_eligible,
        },
        "scoring_model": SCORING_MODEL,
        "grouped_recommendation_evidence_version": GROUPED_RECOMMENDATION_EVIDENCE_VERSION,
    }


def make_fix(rule: str, category: str, priority: str, title: str, explanation: str, why: str, recommendation: str, affected_pages: list[Any], difficulty: str, source: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    extra = extra or {}
    clean_affected = dedupe_strings([clean_path(url) for url in affected_pages or ["/"] if clean_path(url)])[:150]
    page = clean_affected[0] if clean_affected else "/"
    fix_id = stable_id(f"synthetic|{rule}|{page}|{title}|{','.join(clean_affected)}")
    steps = default_steps(category, rule, difficulty, recommendation)
    return {
        "id": fix_id,
        "fix_id": fix_id,
        "type": "site_level",
        "rule": rule,
        "category": category,
        "customer_category": friendly_category(category),
        "issue_title": title,
        "title": title,
        "plain_english_explanation": explanation,
        "plain_english_summary": explanation,
        "why_it_matters": why,
        "current_value": extra.get("current_value") or ("Confirmed failed URL evidence from scanner" if any(token in rule for token in ["broken", "404", "410"]) else "Detected from crawl evidence and site patterns."),
        "recommended_value": recommendation,
        "ai_recommendation": recommendation,
        "priority": priority,
        "difficulty": difficulty,
        "status": "needs_developer" if difficulty == "developer" else "needs_approval",
        "can_auto_fix": False,
        "requires_approval": difficulty != "developer",
        "requires_developer": difficulty == "developer",
        "affected_pages": clean_affected,
        "source_pages": extra.get("source_pages") or clean_affected,
        "link_text_samples": extra.get("link_text_samples") or [],
        "page_url": page,
        "confidence_score": extra.get("confidence_score", 92),
        "what_to_do": steps,
        "what_to_do_steps": steps,
        "fix_steps": steps,
        "who_can_do_this": "your_web_person" if difficulty == "developer" else "you",
        "estimated_time": default_time(difficulty),
        "time_estimate": default_time(difficulty),
        "source": source,
        **extra,
    }


def evidence_extra(group: list[dict[str, Any]]) -> dict[str, Any]:
    status_codes = dedupe_values([int_or_zero(page.get("status_code") or page.get("status")) for page in group if int_or_zero(page.get("status_code") or page.get("status"))])
    source_pages = dedupe_strings([item for page in group for item in (page.get("source_pages") if isinstance(page.get("source_pages"), list) else [])])[:30]
    link_text_samples = dedupe_strings([item for page in group for item in (page.get("link_text_samples") if isinstance(page.get("link_text_samples"), list) else [])])[:12]
    url_confidence = "linked_but_failed" if any(page.get("url_confidence") == "linked_but_failed" for page in group) else group[0].get("url_confidence") if group else "scanner_evidence"
    current_value = "; ".join(f"{clean_path(page_evidence_url(page))}: HTTP {page.get('status_code') or page.get('status') or 'failed'}" for page in group[:8])
    return {"status_codes": status_codes, "source_pages": source_pages, "link_text_samples": link_text_samples, "url_confidence": url_confidence, "current_value": current_value}


def score_page_value(url: str, site_fingerprint: dict[str, Any], body: dict[str, Any], playbook: dict[str, Any]) -> dict[str, Any]:
    path = clean_path(url).lower()
    requested = clean_path(body.get("requested_path_prefix") or body.get("crawl_path_prefix") or body.get("path_prefix") or "").lower()
    score = 35
    if path in {"/", "/index.html"}:
        score += 35
    if requested and path in {requested, f"{requested}/", f"{requested}/index.html"}:
        score += 35
    if is_route_boundary_candidate(path) or is_internal_app_route(path):
        score -= 20
    if any(pattern in path for pattern in playbook["money_patterns"]):
        score += 24
    if has_any(path, ["contact", "devis", "quote", "simulation", "calculator", "comparateur", "booking", "reservation", "annonce", "voir", "cadeau", "coffret", "loisir", "pricing", "demo", "signup", "product", "products", "collection", "collections", "checkout", "loan", "loans", "apply", "payoff", "document-exchange", "locations", "fix-and-flip"]):
        score += 24
    if is_low_value_page(path):
        score -= 35
    if any(path.endswith(extension) for extension in NON_HTML_ASSET_EXTENSIONS):
        score -= 80
    clamped = max(0, min(100, score))
    classification = "internal_or_auth_route" if is_route_boundary_candidate(path) or is_internal_app_route(path) else "money_page" if clamped >= 70 else "low_value" if clamped <= 30 else "standard"
    label = {"internal_or_auth_route": "Route-boundary candidate", "money_page": "Important business page", "low_value": "Lower-priority archive/tag page", "standard": "Standard page"}[classification]
    return {"score": clamped, "classification": classification, "label": label}


def classify_defect_class(fix: dict[str, Any]) -> str:
    text = " ".join(str(fix.get(key, "")) for key in ["rule", "category", "issue_title", "title", "current_value"]).lower()
    if has_any(text, ["429", "blocked", "rate limit", "bot protection", "connection verification"]):
        return "blocked_access"
    if has_any(text, ["route_boundary", "internal_route", "login", "account", "checkout", "dashboard", "noindex", "indexability"]):
        return "crawl_index"
    if has_any(text, ["javascript", "render", "canonical", "redirect", "500", "503", "404", "410", "server_error", "broken_page", "template", "shared pattern", "similar pages"]):
        return "structural"
    if has_any(text, ["schema", "structured"]):
        return "semantic_schema"
    if has_any(text, ["trust", "privacy", "terms", "legal", "about", "contact", "review", "methodology"]):
        return "content_trust"
    if has_any(text, ["meta", "title", "description", "image_alt_text", "alt text"]):
        return "metadata"
    return "general"


def score_evidence_confidence(fix: dict[str, Any]) -> int:
    score = fix.get("confidence_score") if isinstance(fix.get("confidence_score"), (int, float)) else 72
    source = str(fix.get("source", ""))
    if "scanner" in source or "page_pattern" in source:
        score += 10
    if fix.get("current_value"):
        score += 5
    if len(fix.get("affected_pages") or []) > 1:
        score += 5
    if fix.get("url_confidence") == "crawler_artifact":
        score -= 35
    if not fix.get("page_url") and not fix.get("affected_pages"):
        score -= 15
    return max(0, min(100, round(score)))


HEALTH_SCORE_VERSION = "health_score_v3_cosmetic_capped"
# What a finding costs, and the most any one area can cost in total.
#
# The old table summed to 100 against a floor of 20, so a site whose only
# problems were image descriptions and repeated headings could reach the high
# twenties. A production scan of a working lending site scored 28 on nineteen
# findings, almost all of them alt text and duplicate H1s -- real work, but not
# a site in trouble, and a number that reads as a verdict rather than a to-do
# list. FixList tells owners "a perfect score isn't the goal -- a shorter list
# is", and then hands them a figure that contradicts it.
#
# Search visibility keeps its full weight: a page search engines cannot index
# or that names the wrong canonical is genuine damage, and a site with that
# should still score badly. The cosmetic buckets are capped so that together
# they cannot take a healthy site below the sixties, and the floor rises to 40
# so the worst case still reads as a score rather than a zero.
HEALTH_SCORE_SEVERITY_PENALTIES = {"critical": 12.0, "high": 8.0, "medium": 3.0, "low": 1.0}
HEALTH_SCORE_BUCKET_CAPS = {
    # Raised, not lowered. Under the old table a site whose pages were broadly
    # cosmetically imperfect scored *worse* than one whose pages search engines
    # could not index at all -- nineteen small findings spread over five buckets
    # out-penalized two catastrophic ones confined to a single bucket. Breadth
    # was beating severity. Search visibility has to be able to sink a score on
    # its own for the ordering to mean anything.
    "search_visibility": 45.0,
    "site_structure": 16.0,
    # The three cosmetic buckets together cap at 28, so alt text, headings and
    # descriptions cannot drag a working site out of the sixties no matter how
    # many pages carry them.
    "search_appearance": 12.0,
    "page_content": 8.0,
    "technical_quality": 8.0,
}
HEALTH_SCORE_FLOOR = 40


def _health_score_rule_name(fix: dict[str, Any], index: int) -> str:
    rule = str(fix.get("rule") or "").strip().lower()
    aliases = {
        "missing_canonical": "canonical_missing",
        "empty_meta_description": "meta_description_unusable",
        "malformed_meta_description": "meta_description_unusable",
        "missing_meta_description": "meta_description_unusable",
        "meta_description_unusable": "meta_description_unusable",
        "missing_image_alt": "image_alt_text",
    }
    if rule:
        return aliases.get(rule, rule)

    identity = str(
        fix.get("fix_id")
        or fix.get("id")
        or fix.get("issue_title")
        or fix.get("title")
        or index
    ).strip().lower()
    category = str(fix.get("category") or "uncategorized").strip().lower()
    return f"card:{category}:{identity}"


def _health_score_rule_key(fix: dict[str, Any], index: int) -> str:
    rule = _health_score_rule_name(fix, index)
    scope = str(fix.get("page_scope") or "").strip().lower()
    family = str(fix.get("page_template_family") or "").strip().lower()
    if scope == "sitewide":
        family = "*"
    return f"{rule}|family:{family or 'unclassified'}"


def _health_score_bucket(fix: dict[str, Any], index: int) -> str:
    rule = _health_score_rule_name(fix, index)
    category = str(fix.get("category") or "").strip().lower()

    if rule == "potential_orphan_pages" or "redirect" in rule or "sitemap" in rule or "internal_link" in rule:
        return "site_structure"
    if "canonical" in rule or "noindex" in rule or "robots" in rule or "indexab" in rule or "route_boundary" in rule:
        return "search_visibility"
    if "meta_description" in rule or "title" in rule or "schema" in rule:
        return "search_appearance"
    if "h1" in rule or "heading" in rule or "thin_content" in rule:
        return "page_content"

    if category in {"canonical", "indexability"}:
        return "search_visibility"
    if category in {"internal_link", "sitemap"}:
        return "site_structure"
    if category in {"meta_description", "meta_title", "duplicate_content", "schema", "social_metadata"}:
        return "search_appearance"
    if category in {"thin_content", "image_alt_text", "alt_text"}:
        return "page_content"
    return "technical_quality"


def _health_score_affected_pages(fix: dict[str, Any]) -> set[str]:
    values = fix.get("affected_pages") if isinstance(fix.get("affected_pages"), list) else []
    pages = {str(value).strip() for value in values if str(value or "").strip()}
    page_url = str(fix.get("page_url") or "").strip()
    if page_url:
        pages.add(page_url)
    return pages


def _health_score_evidence_factor(fix: dict[str, Any]) -> float:
    state = " ".join([
        str(fix.get("evidence_status") or ""),
        str(fix.get("verification_state") or ""),
        str(fix.get("review_confidence_state") or ""),
    ]).strip().lower()
    if any(token in state for token in ("needs_verification", "inconclusive", "provisional", "unverified")):
        return 0.5

    confidence = fix.get("confidence_score")
    try:
        confidence_value = float(confidence)
    except (TypeError, ValueError):
        confidence_value = 0.0
    if confidence_value <= 0:
        return 1.0
    return max(0.75, min(1.0, confidence_value / 100.0))


def _health_score_prevalence_factor(page_count: int, pages_crawled: int, scope: str) -> float:
    count = max(1, int(page_count or 0))
    crawled = max(1, int(pages_crawled or 0))
    ratio = count / crawled
    factor = 1.0
    if count >= 50 or ratio >= 0.33:
        factor = 2.0
    elif count >= 15 or ratio >= 0.10:
        factor = 1.7
    elif count >= 5 or ratio >= 0.03:
        factor = 1.4
    elif count >= 2:
        factor = 1.2

    normalized_scope = str(scope or "").strip().lower()
    if normalized_scope == "sitewide":
        factor = max(factor, 2.0)
    elif normalized_scope == "cross_cutting":
        factor = max(factor, 1.7)
    elif normalized_scope == "family":
        factor = max(factor, 1.2)
    return factor


def compute_health_score_breakdown(fixes: list[dict[str, Any]], site_fingerprint: dict[str, Any]) -> dict[str, Any]:
    pages_crawled = int_or_zero(site_fingerprint.get("pages_crawled"))
    pages_found = int_or_zero(site_fingerprint.get("pages_found"))
    grouped: dict[str, dict[str, Any]] = {}

    for index, fix in enumerate(fixes):
        if fix.get("non_scoring") is True or fix.get("score_impact") == 0:
            continue

        priority = str(fix.get("priority") or "low").strip().lower()
        base_penalty = HEALTH_SCORE_SEVERITY_PENALTIES.get(priority, 1.0)
        key = _health_score_rule_key(fix, index)
        bucket = _health_score_bucket(fix, index)
        pages = _health_score_affected_pages(fix)
        reported_count = int_or_zero(fix.get("page_count"))
        evidence_factor = _health_score_evidence_factor(fix)
        scope = str(fix.get("page_scope") or "").strip().lower()

        current = grouped.get(key)
        if current is None:
            grouped[key] = {
                "bucket": bucket,
                "base_penalty": base_penalty,
                "pages": set(pages),
                "reported_count": reported_count,
                "evidence_factor": evidence_factor,
                "scope": scope,
            }
            continue

        current["base_penalty"] = max(float(current["base_penalty"]), base_penalty)
        current["pages"].update(pages)
        current["reported_count"] = max(int(current["reported_count"]), reported_count)
        current["evidence_factor"] = max(float(current["evidence_factor"]), evidence_factor)
        if scope == "sitewide" or (scope == "cross_cutting" and current["scope"] != "sitewide"):
            current["scope"] = scope

    bucket_raw = {name: 0.0 for name in HEALTH_SCORE_BUCKET_CAPS}
    action_penalties: dict[str, float] = {}
    for key, action in grouped.items():
        page_count = max(len(action["pages"]), int(action["reported_count"]), 1)
        prevalence = _health_score_prevalence_factor(page_count, pages_crawled, str(action["scope"]))
        penalty = float(action["base_penalty"]) * prevalence * float(action["evidence_factor"])
        action_penalties[key] = round(penalty, 2)
        bucket_raw[str(action["bucket"])] += penalty

    bucket_penalties = {
        bucket: round(min(HEALTH_SCORE_BUCKET_CAPS[bucket], penalty), 2)
        for bucket, penalty in bucket_raw.items()
    }
    total_penalty = sum(bucket_penalties.values())
    score = max(HEALTH_SCORE_FLOOR, min(100, round(100 - total_penalty)))

    # A small representative sample can show that nothing urgent was found,
    # but it should not claim a perfect whole-site score. Full small-site
    # inventories and 100+ page representative crawls may reach 100.
    coverage_ceiling = 100
    # Which limit actually decided the score, for the customer explanation. The
    # ceilings were applied silently, so a scan whose number came from what the
    # crawl could see was indistinguishable from one whose number came from what
    # the crawl found -- and only the second is a statement about the site.
    applied_ceiling = 100
    ceiling_reason = ""

    def _bind(limit: int, reason: str) -> None:
        nonlocal applied_ceiling, ceiling_reason
        if limit < applied_ceiling:
            applied_ceiling, ceiling_reason = limit, reason

    if pages_found > pages_crawled > 0:
        if pages_crawled >= 100:
            coverage_ceiling = 100
        elif pages_crawled >= 50:
            coverage_ceiling = 98
        elif pages_crawled >= 25:
            coverage_ceiling = 95
        else:
            coverage_ceiling = 92
        if coverage_ceiling < score:
            _bind(coverage_ceiling, "sample_size")
        score = min(score, coverage_ceiling)

    # These ceilings describe how much the scan could see, not how good the site
    # is. Each sits above the floor, so what they actually do is pull a
    # high-looking score down: a blocked crawl finds few problems precisely
    # because it saw few pages, and must not be rewarded for it. They cannot
    # push below the floor, and are not meant to -- the floor is the harshest a
    # findings-based score gets.
    if crawl_is_blocked(site_fingerprint):
        if 45 < score:
            _bind(45, "blocked_access")
        score = min(score, 45)
    if evidence_is_incomplete(site_fingerprint):
        if 55 < score:
            _bind(55, "incomplete_evidence")
        score = min(score, 55)
    if pages_crawled == 0:
        if 86 < score:
            _bind(86, "no_pages_crawled")
        score = min(score, 86)

    return {
        "version": HEALTH_SCORE_VERSION,
        "score": score,
        "coverage_ceiling": coverage_ceiling,
        # The ceiling that actually bound this score, and why. 100/"" when the
        # findings alone decided it.
        "applied_ceiling": applied_ceiling,
        "ceiling_reason": ceiling_reason,
        "total_penalty": round(total_penalty, 2),
        "bucket_penalties": bucket_penalties,
        "action_penalties": action_penalties,
    }


def compute_health_score(fixes: list[dict[str, Any]], site_fingerprint: dict[str, Any]) -> int:
    return int(compute_health_score_breakdown(fixes, site_fingerprint)["score"])


def fix_sort_key(fix: dict[str, Any]) -> tuple[int, int]:
    priority_score = {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(str(fix.get("priority")), 0)
    return (priority_score, int_or_zero(fix.get("overall_priority_score")))


def get_playbook(key: str) -> dict[str, Any]:
    return PLAYBOOKS.get(key) or PLAYBOOKS["general"]


# One finance archetype covers businesses that share none of each other's work.
# The 35-site production audit caught the cost: N26, a digital bank, and Alan, a
# health insurer, were both told to start with "loan program pages" because the
# lending playbook is the only one the archetype had. These refine the advice
# inside the archetype rather than re-partitioning the scoring space, so a
# correctly classified lender is unaffected.
FINANCE_SUB_PLAYBOOKS = {
    "digital_bank": {
        "label": "digital bank / consumer fintech",
        "homepage_terms": (
            "digital bank", "mobile bank", "online bank", "bank account",
            "current account", "checking account", "debit card", "banking app",
            "money transfer", "send money", "international transfer",
            "multi-currency account", "spending account",
        ),
        "route_patterns": (
            "/bank-account", "/bank-accounts", "/current-account", "/checking",
            "/cards", "/card/", "/debit", "/accounts/", "/send-money",
            "/money-transfer", "/currency-converter", "/exchange-rate",
        ),
        "priority_pages": [
            "account and card product pages", "pricing and fee pages",
            "signup and onboarding paths", "supported-country and currency pages",
            "legal, security and regulatory pages",
        ],
    },
    "insurance": {
        "label": "insurance",
        "homepage_terms": (
            "health insurance", "insurance", "assurance", "assurance sante",
            "assurance santé", "mutuelle", "cover your team", "coverage for",
            "insurer", "policyholder", "claims",
        ),
        "route_patterns": (
            "/insurance", "/assurance", "/assurance-sante", "/mutuelle",
            "/coverage/", "/cover/", "/claims", "/policy/", "/policies/",
        ),
        "priority_pages": [
            "coverage and plan pages", "quote and enrolment paths",
            "claims and member-support pages", "employer and team plan pages",
            "legal, regulatory and trust pages",
        ],
    },
}


def apply_finance_sub_playbook(base: dict[str, Any], key: str) -> dict[str, Any]:
    """Re-apply an already-decided finance sub-playbook.

    The review pipeline rebuilds the playbook from the archetype key alone, so
    the decision has to travel on the site fingerprint or the customer summary
    silently reverts to the lending wording the fingerprint no longer claims.
    """
    sub = FINANCE_SUB_PLAYBOOKS.get(key or "")
    if not sub:
        return base
    return {
        **base,
        "label": sub["label"],
        "priority_pages": sub["priority_pages"],
        "finance_sub_playbook": key,
    }


def resolve_finance_playbook(base: dict[str, Any], homepage_text: str, path_text: str) -> dict[str, Any]:
    """Pick the finance playbook the evidence supports, defaulting to lending.

    Evidence must be structural or explicit homepage identity. Where neither
    names a bank or an insurer, the lending/lead-generation playbook stands: it
    is the archetype's historical default and the audit's correctly classified
    lender relies on it.
    """
    homepage = (homepage_text or "").lower()
    paths = (path_text or "").lower()
    best_key = ""
    best_score = 0
    for key, sub in FINANCE_SUB_PLAYBOOKS.items():
        routes = sum(1 for pattern in sub["route_patterns"] if pattern in paths)
        homepage_hit = any(term in homepage for term in sub["homepage_terms"])
        score = routes + (2 if homepage_hit else 0)
        # A single incidental route is not an identity; require either homepage
        # identity or more than one distinct route before overriding the default.
        if not homepage_hit and routes < 2:
            continue
        if score > best_score:
            best_key, best_score = key, score
    if not best_key:
        return base
    sub = FINANCE_SUB_PLAYBOOKS[best_key]
    return {
        **base,
        "label": sub["label"],
        "priority_pages": sub["priority_pages"],
        "finance_sub_playbook": best_key,
    }


def detect_business_model(text: str, archetype: str) -> str:
    # Decisive archetypes must not be overridden by incidental page text.
    decisive = {
        "finance_insurance_lead_gen": "regulated_or_trust_lead_generation",
        "utilities_comparison_lead_gen": "regulated_or_trust_lead_generation",
        "booking_experiences_marketplace": "booking_or_reservation",
        "ecommerce_specialty_retail": "catalog_or_ecommerce",
        "saas_app_membership": "saas_or_member_app",
        "nonprofit_fundraising": "nonprofit_or_fundraising",
        "local_business_hospitality": "local_service_or_hospitality",
        "content_blog": "content_or_general_business",
        "general": "content_or_general_business",
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


def detect_localization(pages: list[dict[str, Any]], website_url: str) -> str:
    text = " ".join([website_url] + [page_evidence_url(page) for page in pages[:100]]).lower()
    hits = len(re.findall(r"/(fr|en|es|de|it|nl|pt|ca|us|uk)([-_/]|$)", text))
    if hits >= 4:
        return "multi_language_or_multi_country"
    if hits > 0:
        return "single_locale_subfolder"
    return "single_language_or_unknown"


def is_failed_page(page: dict[str, Any]) -> bool:
    status = int_or_zero(page.get("status_code") or page.get("status"))
    if status >= 400 and status != 429:
        return True
    error = str(page.get("fetch_error") or page.get("error") or "").lower()
    return has_any(error, ["404", "410", "500", "503", "not found", "server error"])


def is_blocked_access_page(page: dict[str, Any]) -> bool:
    status = int_or_zero(page.get("status_code") or page.get("status"))
    text = f"{page.get('fetch_error', '')} {page.get('title', '')} {page.get('content_type', '')}".lower()
    evidence_class = page_evidence_class(page)
    return (
        status == 429
        or (status in {401, 403} and evidence_class == "failed_access")
        or has_any(text, ["rate limit", "too many requests", "connection verification", "bot protection", "access denied", "cloudflare"])
    )


def status_bucket_from_page(page: dict[str, Any]) -> str:
    status = int_or_zero(page.get("status_code") or page.get("status"))
    if page_evidence_class(page) == "failed_access" and status not in {404, 410, 429} and status < 500:
        return "access"
    if status == 429 or is_blocked_access_page(page):
        return "429"
    if status >= 500:
        return "5xx"
    if status == 410:
        return "410"
    return "404"


def important_failed_pages(group: list[dict[str, Any]], site_fingerprint: dict[str, Any]) -> bool:
    for page in group:
        path = clean_path(page_evidence_url(page)).lower()
        if page.get("url_confidence") in {"linked_but_failed", "confirmed_sitemap_and_linked"}:
            return True
        if any(pattern in path for pattern in site_fingerprint.get("likely_money_page_patterns", [])):
            return True
        if not is_low_value_page(path):
            return True
    return False


def page_evidence_url(page: dict[str, Any]) -> str:
    return str(page.get("url") or page.get("final_url") or page.get("path") or page.get("page_url") or "/")


def page_is_indexable(page: dict[str, Any]) -> bool:
    robots = str(page.get("robots") or page.get("robots_meta") or "").lower()
    return "noindex" not in robots and page.get("indexable") is not False


LEGACY_TEMPLATE_FAMILIES = {"", "standard", "category_listing", "guide", "qa", "product_detail"}


def normalize_template_family(stamped: Any, url: Any = "") -> str:
    """Trust explicit template stamps except when a support URL was promoted by money keywords."""
    path = clean_path(url) or "/"
    derived = get_template_family(path)
    value = str(stamped or "").strip()
    if derived == "guide_article" and value in SUPPORT_RECLASS_FAMILIES:
        return "guide_article"
    if value and value not in LEGACY_TEMPLATE_FAMILIES:
        return value
    return derived


def template_current_value(affected_paths: list[Any]) -> str:
    paths = dedupe_strings([clean_path(u) for u in (affected_paths or []) if clean_path(u)])
    if not paths:
        return "No affected pages recorded."
    count = len(paths)
    sample = ", ".join(paths[:3])
    more = f" (+{count - 3} more)" if count > 3 else ""
    noun = "page" if count == 1 else "pages"
    return f"{count} affected {noun}: {sample}{more}"


def get_template_family(url: str = "") -> str:
    from .extract import classify_template
    return classify_template(clean_path(url))


def family_label(family: str) -> str:
    return {
        "activity_detail": "activity/detail",
        "booking_or_checkout": "booking",
        "conversion": "conversion",
        "contact": "contact",
        "guide": "guide",
        "guide_article": "guide/article",
        "legal_info": "legal info",
        "product_page": "product page",
        "collection_page": "collection page",
        "loan_program": "loan program",
        "location_landing": "location landing",
        "calculator": "calculator",
        "comparison_page": "comparison page",
        "route_boundary": "route-boundary",
        "standard": "standard",
    }.get(family, family.replace("_", " ") if family else "standard")

def is_low_value_page(url: str = "") -> bool:
    path = clean_path(url).lower()
    # Legal/trust documents are never low-value archives, wherever the CMS files them.
    from .extract import is_legal_page_path
    if is_legal_page_path(path) or path.startswith(tuple(TRUST_PATHS)):
        return False
    if re.search(r"/(20\d{2})([-/]\d{1,2}|/|$)", path):
        return True
    # "/page/" alone demoted CMS slugs like /fr/page/mentions-legales; only numbered
    # pagination (/page/3, ?page=2) is genuinely a low-value archive.
    if re.search(r"/page/\d+(/|$)", path) or re.search(r"[?&]page=\d+", path):
        return True
    return any(pattern in path for pattern in LOW_VALUE_PATTERNS)


def is_route_boundary_candidate(url: str = "") -> bool:
    # Delegate to the canonical, token-bounded classifier. The old review-side substring list
    # re-matched "/cart" inside the French word "carte", so public activity pages
    # (/fr/carte-invitation-anniversaire) were flagged as private internal routes even after
    # the scanner had correctly classified them. One classifier, not two.
    from .extract import is_route_boundary
    return is_route_boundary(clean_path(url))


def is_internal_app_route(url: str = "") -> bool:
    from .extract import is_wordpress_author_archive

    path = clean_path(url).lower()
    if is_wordpress_author_archive(path):
        return False
    return any(pattern in path for pattern in INTERNAL_ROUTE_PATTERNS)


def normalize_affected_pages(fix: dict[str, Any], fallback: str) -> list[str]:
    values: list[Any] = []
    for key in ["affected_pages", "pages", "page_urls"]:
        if isinstance(fix.get(key), list):
            values.extend(fix[key])
    values.append(fallback)
    return dedupe_strings([clean_path(value) for value in values if clean_path(value)])[:150]


def normalize_steps(fix: dict[str, Any]) -> list[str] | None:
    for key in ["what_to_do_steps", "what_to_do", "fix_steps", "steps"]:
        value = fix.get(key)
        if isinstance(value, list) and value:
            return [str(item) for item in value if str(item).strip()][:6]
    return None


def default_steps(category: str, rule: str, difficulty: str, recommended_value: str) -> list[str]:
    text = f"{category} {rule}"

    if category == "image_alt_text" or re.search(r"image_alt|missing_alt|alt_text", rule, re.I):
        return [
            "Open one affected page and identify which meaningful images are missing alt text.",
            "Update the shared image component or CMS image field to output short, specific alt text.",
            "Check several affected pages to confirm decorative images remain empty and meaningful images are described.",
            "Publish the change and run FixList again to confirm the missing-alt count has fallen.",
        ]
    if re.search(r"canonical_missing|missing_canonical|canonical_to_other", rule, re.I) or category == "canonical":
        return [
            "Send the affected URLs to your web person.",
            "Add or correct self-referencing canonical tags on the affected page or shared template.",
            "Publish the change and inspect the rendered page source to confirm the canonical URL is correct.",
            "Run FixList again to confirm the canonical issue is resolved.",
        ]
    if re.search(r"missing_h1", rule, re.I):
        return [
            "Open the affected page or shared template.",
            "Add one clear H1 that describes the page's main topic.",
            "Keep supporting section headings as H2 or H3 headings.",
            "Publish the change and run FixList again.",
        ]
    if re.search(r"multiple_h1", rule, re.I):
        return [
            "Open the affected page or shared template.",
            "Keep the primary page heading as the only H1.",
            "Change supporting headings to H2 or H3 without altering their visual style.",
            "Publish the change and run FixList again.",
        ]
    if re.search(r"missing_meta_description", rule, re.I) or category == "meta_description":
        return [
            "Open the affected page in the CMS or page template.",
            "Add a concise meta description that accurately explains the page and gives searchers a reason to click.",
            "Keep the description unique to the page and avoid copying visible boilerplate or HTML markup.",
            "Publish the update and run FixList again.",
        ]
    if re.search(r"429|blocked|rate_limited", rule, re.I):
        return [
            "Send the grouped affected URLs to your web person.",
            "Check CDN, firewall, server, and bot-protection logs for HTTP 429 or verification responses.",
            "Confirm whether Googlebot and normal users can load the pages.",
            "Adjust rate-limit or bot-protection rules only if legitimate crawlers or users are blocked.",
            "Run FixList again to confirm the affected pages load.",
        ]
    if re.search(r"404|410|broken", text, re.I):
        return [
            "Send the affected URLs and source-page evidence to your web person.",
            "Decide whether each URL should be restored, redirected, or removed from internal links.",
            "Update the source links or add 301 redirects to the closest relevant live page.",
            "Run FixList again to confirm the URLs no longer fail.",
        ]
    if re.search(r"server_error|5xx|500|502|503|504", text, re.I):
        return [
            "Send the affected URLs and timestamps to your web person.",
            "Check application, hosting, and reverse-proxy logs for the server error.",
            "Fix the failing route, dependency, timeout, or infrastructure rule.",
            "Recheck the URLs directly, then run FixList again.",
        ]
    if difficulty == "developer" or re.search(r"redirect|route_boundary|indexability|template|schema|javascript|render", text, re.I):
        return [
            "Send this recommendation to your web person.",
            clean_str(recommended_value) or "Apply the recommended technical change.",
            "Publish the change and rerun FixList to verify it.",
        ]
    return [
        "Open the affected page or template.",
        clean_str(recommended_value) or "Apply the recommended change.",
        "Publish the update and run FixList again.",
    ]


def needs_developer_owner(item: dict[str, Any]) -> bool:
    affected = item.get("affected_pages") or []
    affected_count = len(set(map(clean_path, affected))) if isinstance(affected, list) else 0
    page_template_family = str(item.get("page_template_family") or "")
    if str(item.get("source", "")).startswith("page_pattern:image_alt_text:"):
        return True  # a template-level image-alt pattern is a developer task even at one sampled page
    if affected_count >= 5:
        return True
    if page_template_family in {"activity_detail", "booking_or_checkout", "product_page", "collection_page", "conversion", "loan_program", "calculator", "comparison_page", "location_landing", "route_boundary"} and affected_count >= 2:
        return True
    value = " ".join(str(item.get(key, "")) for key in ["rule", "category", "title", "issue_title", "reason", "recommendation", "recommended_value", "who_can_do_this", "primary_defect_class"]).lower()
    if isinstance(item.get("what_to_do_steps"), list):
        value += " " + " ".join(map(str, item["what_to_do_steps"])).lower()
    if item.get("requires_developer") or item.get("difficulty") == "developer" or item.get("status") == "needs_developer" or "your_web_person" in value:
        return True
    return bool(re.search(r"developer|web person|server-side|server side|ssr|pre-render|prerender|javascript|rendering|schema|structured data|canonical|redirect|server|firewall|bot protection|cloudflare|429|500|503|404|410|robots|noindex|crawlable html|view source|indexability|route-boundary|route boundary|checkout|login|account|dashboard|routing", value))


def infer_category(rule: str, fix: dict[str, Any]) -> str:
    text = f"{rule} {fix.get('title', '')} {fix.get('issue_title', '')}".lower()
    if has_any(text, ["429", "blocked", "rate limit", "bot protection", "server", "500", "503"]):
        return "web_dev"
    if "schema" in text or "trust" in text:
        return "schema"
    if "canonical" in text:
        return "canonical"
    if "h1" in text or "heading" in text:
        return "thin_content"
    if "title" in text:
        return "meta_title"
    if "description" in text or "meta" in text:
        return "meta_description"
    if "alt" in text or "image" in text:
        return "image_alt_text"
    if "404" in text or "410" in text or "broken" in text:
        return "404_error"
    if "index" in text or "noindex" in text:
        return "indexability"
    return "web_dev"


def default_title(category: str, rule: str = "") -> str:
    if re.search(r"404|410|broken", f"{category} {rule}", re.I):
        return "Fix confirmed broken URLs"
    return {"meta_title": "Improve search titles", "meta_description": "Improve search descriptions", "duplicate_content": "Review duplicate or repeated pages", "canonical": "Add canonical URLs", "schema": "Improve trust and structured data", "thin_content": "Improve page headings", "404_error": "Fix pages that are not loading", "web_dev": "Review website setup", "image_alt_text": "Add useful image descriptions", "indexability": "Review indexability settings"}.get(category, "Review this recommendation")


def friendly_category(category: str) -> str:
    return {"meta_title": "Search appearance", "meta_description": "Search appearance", "duplicate_content": "Search appearance", "canonical": "Website setup", "schema": "Trust signals", "thin_content": "Page content", "404_error": "Broken page", "redirect": "Page redirect", "internal_link": "Internal links", "performance": "Website performance", "web_dev": "Website setup", "mobile_setup": "Mobile setup", "performance_hint": "Website performance", "social_metadata": "Social sharing", "indexability": "Indexability", "image_alt_text": "Images"}.get(category, "Website improvement")


def normalize_priority(value: Any) -> str:
    priority = str(value or "").lower()
    return priority if priority in {"critical", "high", "medium", "low"} else "medium"


def normalize_difficulty(fix: dict[str, Any]) -> str:
    value = str(fix.get("difficulty") or fix.get("estimated_complexity") or "").lower()
    if "developer" in value or "complex" in value:
        return "developer"
    if "moderate" in value:
        return "moderate"
    return "easy"


def normalize_owner(value: Any) -> str:
    owner = str(value or "").lower()
    return "your_web_person" if "web" in owner or "developer" in owner or owner == "your_web_person" else "you"


def default_time(difficulty: str) -> str:
    if difficulty == "developer":
        return "about 1–2 hours"
    if difficulty == "moderate":
        return "about 30–60 minutes"
    return "about 10–20 minutes"


def group_page_recommendations(fixes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fix in fixes:
        scope = str(fix.get("page_scope") or "")
        key = scope if scope in {"sitewide", "cross_cutting"} else str(fix.get("page_template_family") or "site")
        groups[key].append(fix)
    return [{"template_family": family, "count": len(items), "top_recommendations": items[:5]} for family, items in list(groups.items())[:12]]


def dedupe_fixes(fixes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    output = []
    for fix in fixes:
        key = str(fix.get("fix_id") or fix.get("id") or f"{fix.get('rule')}|{fix.get('category')}|{fix.get('page_template_family', '')}|{fix.get('page_url')}|{','.join(fix.get('affected_pages') or [])}")
        if key in seen:
            continue
        seen.add(key)
        output.append(fix)
    return output


def dedupe_pages(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    output = []
    for page in pages:
        key = clean_path(page_evidence_url(page))
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(page)
    return output


def collect_arrays(*values: Any) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for value in values:
        if isinstance(value, list):
            output.extend(item for item in value if isinstance(item, dict))
    return output


def first_array(*values: Any) -> list[dict[str, Any]]:
    for value in values:
        if isinstance(value, list) and value:
            return [item for item in value if isinstance(item, dict)]
    return []


def first_number(*values: Any) -> int:
    for value in values:
        try:
            number = int(value)
            if number >= 0:
                return number
        except (TypeError, ValueError):
            continue
    return 0


def first_value(value: Any) -> Any:
    return value[0] if isinstance(value, list) and value else None


def parse_json_object(value: str) -> dict[str, Any]:
    try:
        import json
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def clean_str(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def safe_hostname(value: Any) -> str:
    parsed = urlparse(str(value or ""))
    return (parsed.hostname or "").lower()


def deep_get(value: Any, *keys: str) -> Any:
    current = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def count_includes(text: str, keyword: str) -> int:
    needle = str(keyword or "").lower()
    if not needle:
        return 0
    return str(text or "").lower().count(needle)


def count_lists(*values: Any) -> int:
    return sum(len(value) for value in values if isinstance(value, list))


def dedupe_values(values: list[Any]) -> list[Any]:
    seen = set()
    output = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output


def stable_id(value: str) -> str:
    digest = hashlib.sha1(str(value or "").encode("utf-8")).hexdigest()[:10]
    return f"finding_{digest}"


def apply_incomplete_evidence_state(review_payload: dict[str, Any]) -> None:
    """Make an empty scan explicit instead of presenting a misleading health grade."""
    summary = INCOMPLETE_REVIEW_WARNING
    next_step = "Provide page-level scan evidence, then rerun AI Review."
    report = review_payload.get("website_health_report")
    if isinstance(report, dict):
        report["health_grade"] = "Scan incomplete"
        report["overall_explanation"] = summary
        report["next_best_step"] = next_step
    review_payload.update({
        "health_grade": "Scan incomplete",
        "plain_english_summary": summary,
        "health_explanation": summary,
        "customer_summary": summary,
        "next_best_step": next_step,
        "scan_status": "incomplete_evidence",
    })


def apply_zero_fix_confidence_state(review_payload: dict[str, Any]) -> None:
    """Present a complete zero-fix review as a bounded sample result, not a site-wide guarantee."""
    summary = (
        "FixList found no high-confidence, evidence-backed fixes in the scanned sample. "
        "This does not guarantee that every page or SEO signal on the site is issue-free."
    )
    next_step = "No high-confidence issues found in the scanned sample — consider a deeper crawl or manual review of money pages."
    limitation = (
        "No high-confidence fixes were found in the scanned sample; unscanned pages "
        "or signals outside the crawl may still contain issues."
    )
    report = review_payload.get("website_health_report")
    if isinstance(report, dict):
        report["health_grade"] = ZERO_FIX_HEALTH_GRADE
        report["overall_explanation"] = summary
        report["next_best_step"] = next_step
        limitations = report.get("limitations")
        if isinstance(limitations, list) and limitation not in limitations:
            limitations.append(limitation)

    review_payload.update({
        "no_high_confidence_findings": True,
        "review_confidence_state": "no_high_confidence_findings",
        "zero_fix_confidence_version": ZERO_FIX_CONFIDENCE_VERSION,
        "health_grade": ZERO_FIX_HEALTH_GRADE,
        "plain_english_summary": summary,
        "health_explanation": summary,
        "customer_summary": summary,
        "next_best_step": next_step,
        "limitation": limitation,
        "scan_status": "complete_no_high_confidence_findings",
    })
