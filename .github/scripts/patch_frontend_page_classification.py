from pathlib import Path

path = Path("src/components/scan/ScanWebsiteForm.jsx")
text = path.read_text(encoding="utf-8")


def replace_once(old: str, new: str, label: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    text = text.replace(old, new, 1)


replace_once(
    'const LOW_VALUE_PAGE_PATTERNS = ["/actualites", "/news", "/blog", "/archive", "/archives", "/tag/", "/tags/", "/author/", "/feed", "/rss", "/page/", "?page=", "&page=", "?p=", "&p=", "?tag=", "&tag="];\nconst MONEY_PAGE_PATTERNS =',
    '''const LOW_VALUE_PAGE_PATTERNS = ["/actualites", "/news", "/blog", "/archive", "/archives", "/tag/", "/tags/", "/author/", "/feed", "/rss", "?tag=", "&tag="];
const LEGAL_PAGE_RE = /(mentions-legales|mentions_legales|politique-de-confidentialite|privacy-policy|privacy_policy|conditions-generales|conditions-generales-de-vente|legal-notice|terms-of-service|terms-and-conditions|terms-of-use|privacy|impressum)|(?:^|\\/)(?:cgu|cgv|legal|terms|mentions|privacite)(?:\\/|$)/i;
const ROUTE_BOUNDARY_RE = /\\/(?:login|signin|sign-in|register|signup|sign-up|account|mon-compte|dashboard|cart|panier|checkout|billing|admin|wp-admin)(?=[/?#\\s]|$)/i;
const MONEY_PAGE_PATTERNS =''',
    "low-value constants",
)

replace_once(
    '  const lowValue = isLowValuePage(url);\n  const important = isImportantBusinessPage(url, options);',
    '  const lowValue = typeof fix.is_low_value_page === "boolean" ? fix.is_low_value_page : isLowValuePage(url);\n  const important = typeof fix.is_important_business_page === "boolean" ? fix.is_important_business_page : isImportantBusinessPage(url, options);',
    "authoritative priority booleans",
)

replace_once(
    'business_importance: important ? "important" : lowValue ? "low_value_archive" : fix.business_importance || "standard", is_low_value_page: lowValue, is_important_business_page: important',
    'business_importance: fix.business_importance || (important ? "important" : lowValue ? "low_value_archive" : "standard"), is_low_value_page: typeof fix.is_low_value_page === "boolean" ? fix.is_low_value_page : lowValue, is_important_business_page: typeof fix.is_important_business_page === "boolean" ? fix.is_important_business_page : important',
    "priority output fields",
)

replace_once(
    'is_low_value_page: Boolean(fix.is_low_value_page) || isLowValuePage(fallbackPage), is_important_business_page: Boolean(fix.is_important_business_page) || isImportantBusinessPage(fallbackPage)',
    'is_low_value_page: typeof fix.is_low_value_page === "boolean" ? fix.is_low_value_page : isLowValuePage(fallbackPage), is_important_business_page: typeof fix.is_important_business_page === "boolean" ? fix.is_important_business_page : isImportantBusinessPage(fallbackPage)',
    "slim fix booleans",
)

replace_once(
    'function isLowValuePage(url = "") { const path = String(url || "").toLowerCase(); if (/\\/(20\\d{2})([-/]\\d{1,2}|\\/|$)/.test(path)) return true; return LOW_VALUE_PAGE_PATTERNS.some((pattern) => path.includes(pattern)); }',
    '''function isLegalPagePath(url = "") { const path = String(url || "").toLowerCase().split("?")[0].split("#")[0]; return LEGAL_PAGE_RE.test(path); }
function isLowValuePage(url = "") { const value = String(url || "").toLowerCase(); const path = value.split("#")[0]; if (isLegalPagePath(path)) return false; if (/\\/(20\\d{2})([-/]\\d{1,2}|\\/|$)/.test(path)) return true; if (/\\/page\\/\\d+(?:\\/|$)/.test(path.split("?")[0])) return true; if (/[?&]page=\\d+/.test(path)) return true; return LOW_VALUE_PAGE_PATTERNS.some((pattern) => path.includes(pattern)); }''',
    "bounded low-value matcher",
)

replace_once(
    'function classifyTemplateFamily(url = "") { const path = String(url || "").toLowerCase(); if (isLowValuePage(path)) return "archive"; if (/checkout|booking|reservation|ticket_order|gift_voucher/.test(path)) return "booking_or_checkout"; if (/listing|show|category|categorie|collection|pass|ticket|stage|pilotage/.test(path)) return "category_listing"; if (/product|produit|\\/p\\//.test(path)) return "product_detail"; if (/simulation|simulateur|calcul|calculator|comparateur|devis|quote|pricing|demo|tarif|fournisseur|energie|electricite|gaz/.test(path)) return "conversion"; if (/contact/.test(path)) return "contact"; if (/faq|question/.test(path)) return "qa"; if (/guide|blog/.test(path)) return "guide"; if (/privacy|terms|legal|mentions-legales|security|cgv/.test(path)) return "legal_info"; if (/login|register|account|dashboard|admin|billing|cart|checkout/.test(path)) return "route_boundary"; return "standard"; }',
    'function classifyTemplateFamily(url = "") { const path = String(url || "").toLowerCase(); if (isLegalPagePath(path)) return "legal_info"; if (ROUTE_BOUNDARY_RE.test(path)) return "route_boundary"; if (isLowValuePage(path)) return "archive"; if (/checkout|booking|reservation|ticket_order|gift_voucher/.test(path)) return "booking_or_checkout"; if (/listing|show|category|categorie|collection|pass|ticket|stage|pilotage/.test(path)) return "category_listing"; if (/product|produit|\\/p\\//.test(path)) return "product_detail"; if (/simulation|simulateur|calcul|calculator|comparateur|devis|quote|pricing|demo|tarif|fournisseur|energie|electricite|gaz/.test(path)) return "conversion"; if (/contact/.test(path)) return "contact"; if (/faq|question/.test(path)) return "qa"; if (/guide|blog/.test(path)) return "guide"; return "standard"; }',
    "template family precedence",
)

path.write_text(text, encoding="utf-8")
print("Patched frontend page classification and backend-authoritative booleans.")
