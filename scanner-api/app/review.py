from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Any
from urllib.parse import urlparse

REVIEW_VERSION = "python_review_v1_archetype_templates"
SCORING_MODEL = "python_review_v1_archetype_templates"
QUALITY_GATE_VERSION = "review_quality_gate_v1_evidence_complete"
INCOMPLETE_REVIEW_WARNING = "Review received scan metadata, but no page evidence was passed into AI Review."

LOW_VALUE_PATTERNS = [
    "/actualites/", "/news/", "/archive/", "/archives/", "/tag/", "/tags/",
    "/author/", "/feed/", "/rss/", "/page/", "?page=", "&page=", "?tag=", "&tag=",
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
    "missing_title": "meta_title",
    "duplicate_title": "duplicate_content",
    "duplicate_meta_description": "duplicate_content",
}

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
            "variant", "shipping", "livraison", "shopify",
        ],
        "money_patterns": [
            "/products/", "/product/", "/produit/", "/collections/", "/collection/",
            "/category/", "/categorie/", "/shop", "/boutique", "/cart", "/checkout", "/marque",
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
            "demo", "trial", "api", "report",
        ],
        "money_patterns": ["/pricing", "/register", "/signup", "/demo", "/contact", "/features", "/use-cases", "/solutions"],
        "priority_pages": ["homepage", "pricing", "demo/signup", "features/use cases", "docs/help pages", "public trust/security pages"],
        "priority_issues": ["internal/auth route exposure", "custom domain trust", "duplicate casing", "thin app snapshots", "noindex boundaries", "canonicalization"],
        "demote": ["metadata on internal routes", "duplicate app snapshots that should be noindexed", "low-value docs pagination"],
        "owner_rule": "Route boundaries, auth, canonical, app rendering, and noindex rules need your_web_person.",
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
    playbook = get_playbook(site_fingerprint["primary_archetype"])
    evidence_fixes = build_scanner_evidence_findings(body, pages, site_fingerprint)
    page_pattern_fixes = build_page_pattern_findings(pages)
    strategic_fixes = build_strategic_findings(body, pages, website_url, site_fingerprint, playbook)
    canonical_fixes = prepare_fixes(raw_fixes + evidence_fixes + page_pattern_fixes + strategic_fixes, site_fingerprint, body, playbook)

    warning = ""
    if evidence_is_incomplete(site_fingerprint):
        warning = INCOMPLETE_REVIEW_WARNING
        if not canonical_fixes:
            canonical_fixes = [make_missing_evidence_fix()]
    elif not website_url:
        warning = "AI review ran, but website_url was missing. Scanner recommendations are shown."
    elif not canonical_fixes:
        warning = "AI review ran, but no scanner recommendations were provided."

    review_payload = build_review_payload(body, pages, canonical_fixes, site_fingerprint, playbook, website_url)
    return {
        "success": True,
        "ai_provider": "python_review_api",
        "review_version": REVIEW_VERSION,
        "ai_review_version": REVIEW_VERSION,
        "ai_review_warning": warning,
        "review_evidence_contract_version": "review_evidence_contract_v1",
        **review_payload,
    }


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


def build_site_fingerprint(body: dict[str, Any], pages: list[dict[str, Any]], website_url: str) -> dict[str, Any]:
    text_parts: list[str] = [
        website_url,
        str(body.get("business_name", "")),
        str(body.get("business_type", "")),
        str(body.get("cms_name", "")),
        str(body.get("cms_platform", "")),
        str(body.get("scan_mode", "")),
    ]
    for page in pages[:220]:
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
    scores = []
    for key, playbook in PLAYBOOKS.items():
        if key == "general":
            continue
        score = 0.0
        score += sum(count_includes(text, keyword) for keyword in playbook["keywords"])
        score += sum(count_includes(text, pattern) for pattern in playbook["money_patterns"]) * 1.8
        score += archetype_boost(key, text, pages)
        scores.append((key, score))
    scores.sort(key=lambda item: item[1], reverse=True)
    primary = scores[0][0] if scores and scores[0][1] > 0 else "general"
    secondary = scores[1][0] if len(scores) > 1 and scores[1][1] > max(3, scores[0][1] * 0.6) else ""
    confidence = min(0.96, 0.45 + (scores[0][1] / max(12, scores[0][1] + (scores[1][1] if len(scores) > 1 else 0)))) if scores and scores[0][1] > 0 else 0.35
    playbook = get_playbook(primary)
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

    return {
        "primary_archetype": primary,
        "secondary_archetype": secondary,
        "archetype_label": playbook["label"],
        "vertical": primary,
        "vertical_label": playbook["label"],
        "vertical_confidence": round(confidence, 2),
        "business_model": detect_business_model(text, primary),
        "size_band": "enterprise" if max(pages_found, pages_crawled, pages_received) >= 1000 else "mid_market" if max(pages_found, pages_crawled, pages_received) >= 150 else "smb" if max(pages_found, pages_crawled, pages_received) >= 30 else "micro",
        "pages_found": pages_found,
        "pages_crawled": pages_crawled,
        "pages_received": pages_received,
        "sampled_pages_sent_to_ai": sampled_pages_sent,
        "localization": detect_localization(pages, website_url),
        "render_mode": "rendered_browser_checked" if deep_get(body, "browser_rendering", "enabled") else "js_heavy_suspected" if sum(1 for page in pages if page.get("client_rendering_suspected")) >= 3 else "raw_html_first",
        "regulatory_sensitivity": "trust_or_regulated" if primary in {"finance_insurance_lead_gen", "utilities_comparison_lead_gen"} else "standard",
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
    }


def review_input_quality(body: dict[str, Any], site_fingerprint: dict[str, Any]) -> dict[str, Any]:
    incomplete = evidence_is_incomplete(site_fingerprint)
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
        "evidence_complete": not incomplete,
        "metadata_without_pages": incomplete,
        "blocked_or_429_pages": int_or_zero(site_fingerprint.get("blocked_or_429_pages")),
    }


def evidence_is_incomplete(site_fingerprint: dict[str, Any]) -> bool:
    received = int_or_zero(site_fingerprint.get("pages_received"))
    reported = max(
        int_or_zero(site_fingerprint.get("pages_crawled")),
        int_or_zero(site_fingerprint.get("pages_found")),
    )
    sampled = int_or_zero(site_fingerprint.get("sampled_pages_sent_to_ai"))
    return reported > 0 and (received == 0 or sampled == 0)


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


def archetype_boost(key: str, text: str, pages: list[dict[str, Any]]) -> float:
    path_text = " ".join(clean_path(page_evidence_url(page)).lower() for page in pages[:220])
    if key == "booking_experiences_marketplace":
        score = count_includes(path_text, "/annonce/") * 8
        score += count_includes(path_text, "/voir") * 5
        if has_any(text, ["funbooker", "activité", "activite", "cadeau", "coffret", "loisir", "reservation", "réservation"]):
            score += 35
        return score
    if key == "finance_insurance_lead_gen":
        score = count_includes(path_text, "/loans") * 10
        score += count_includes(path_text, "/loan") * 6
        score += count_includes(path_text, "/apply-now") * 18
        score += count_includes(path_text, "/request-a-payoff") * 18
        score += count_includes(path_text, "/document-exchange") * 14
        score += count_includes(path_text, "/locations") * 4
        if has_any(text, ["centerstreetlending", "center street lending", "fix-and-flip", "fix and flip", "hard money", "bridge loan", "private lending", "real estate investor", "lending"]):
            score += 55
        return score
    return 0


def build_scanner_evidence_findings(body: dict[str, Any], pages: list[dict[str, Any]], site_fingerprint: dict[str, Any]) -> list[dict[str, Any]]:
    evidence_pages = dedupe_pages(
        collect_arrays(
            body.get("verified_failed_pages"),
            deep_get(body, "technical_audit_summary", "verified_failed_pages"),
            deep_get(body, "url_evidence_summary", "verified_failed_pages"),
        )
        + [page for page in pages if is_failed_page(page) or is_blocked_access_page(page)]
    )
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for page in evidence_pages:
        grouped[status_bucket_from_page(page)].append(page)

    fixes = []
    for bucket, group in grouped.items():
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
                extra=evidence_extra(group),
            ))
            continue
        is_server = bucket == "5xx"
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
            extra=evidence_extra(group),
        ))
    return fixes


def build_page_pattern_findings(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for page in pages:
        url = page_evidence_url(page)
        if not url:
            continue
        if int_or_zero(page.get("status_code") or page.get("status")) >= 400 or is_blocked_access_page(page):
            continue  # failed/blocked pages are owned by the evidence generator; never fabricate content fixes for them
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
        if not clean_str(page.get("meta_description")):
            add_bucket(buckets, "missing_meta_description", "meta_description", family, page, "Batch meta descriptions on templates", "The page is missing a meta description.", "Search descriptions can improve how pages appear in search results.", "Add a short description that explains the page and why someone should click.", "easy")

    fixes = []
    for bucket in buckets.values():
        affected = [page_evidence_url(page) for page in bucket["pages"]]
        is_group = len(set(map(clean_path, affected))) > 1
        title = bucket["title"].replace("templates", f"{family_label(bucket['family'])} templates") if is_group else bucket["title"].replace("templates", "the affected page")
        fixes.append(make_fix(
            rule=bucket["rule"],
            category=bucket["category"],
            priority="critical" if bucket["category"] == "canonical" else "high" if len(bucket["pages"]) >= 8 else "medium",
            title=title,
            explanation="Several similar pages have the same template-level issue. Fix the shared template or pattern instead of creating one task per page." if is_group else bucket["explanation"],
            why="Large sites usually have template problems. Grouping keeps the FixList focused on the highest-impact patterns." if is_group else bucket["why"],
            recommendation=bucket["recommendation"],
            affected_pages=affected,
            difficulty="developer" if len(set(map(clean_path, affected))) >= 5 else bucket["difficulty"],
            source=f"page_pattern:{bucket['rule']}:{bucket['family']}",
            extra={
                "current_value": template_current_value(affected),
                "defect_summary": bucket["explanation"],
                "source_pages": dedupe_strings([clean_path(u) for u in affected if clean_path(u)])[:30],
                "page_template_family": bucket["family"],
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
    route_pages = [page for page in pages if (is_route_boundary_candidate(page_evidence_url(page)) or is_internal_app_route(page_evidence_url(page))) and page_is_indexable(page)]
    if route_pages:
        fixes.append(make_fix("route_boundary_candidate_indexable", "indexability", "critical", "Keep checkout, login, account, and app routes out of search", "FixList found checkout, login, account, dashboard, billing, cart, admin, or app-like routes that appear crawlable and indexable.", "These pages are usually not useful SEO landing pages. Letting them appear in search can dilute the site, confuse prospects, or expose private product structure.", "Ask your web person to require login, add noindex, or keep these routes out of public search while preserving true public landing, category, product, booking, and help pages.", [page_evidence_url(page) for page in route_pages], "developer", "archetype_route_boundary_layer", extra={"current_value": "Indexable app/checkout/account routes: " + ", ".join(dedupe_strings([clean_path(page_evidence_url(page)) for page in route_pages])[:6]), "source_pages": dedupe_strings([clean_path(page_evidence_url(page)) for page in route_pages])[:30]}))
    trust_sensitive = site_fingerprint["regulatory_sensitivity"] != "standard" or site_fingerprint["primary_archetype"] == "saas_app_membership"
    has_trust = any(clean_path(page_evidence_url(page)).lower().startswith(tuple(TRUST_PATHS)) for page in pages)
    if trust_sensitive and pages and not has_trust:
        fixes.append(make_fix("missing_trust_pages", "schema", "high" if site_fingerprint["regulatory_sensitivity"] != "standard" else "medium", "Add public trust pages", f"For a {playbook['label']} site, visitors and crawlers need clear trust, legal, contact, and ownership signals.", "Trust pages help buyers, search engines, and AI systems understand who runs the site and whether it is credible.", "Add or expose clear About, Contact, Privacy, Terms, and Security/Trust pages, then link them from the footer.", ["/"], "moderate", "archetype_trust_layer", extra={"current_value": f"No public trust pages (About/Contact/Privacy/Terms) found among {len(pages)} crawled pages.", "source_pages": ["/"]}))
    return fixes


def prepare_fixes(raw_fixes: list[dict[str, Any]], site_fingerprint: dict[str, Any], body: dict[str, Any], playbook: dict[str, Any]) -> list[dict[str, Any]]:
    normalized = dedupe_fixes([normalize_fix(fix, index) for index, fix in enumerate(raw_fixes or []) if isinstance(fix, dict)])
    scored = [score_fix(fix, site_fingerprint, body, playbook) for fix in normalized]
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


def score_fix(fix: dict[str, Any], site_fingerprint: dict[str, Any], body: dict[str, Any], playbook: dict[str, Any]) -> dict[str, Any]:
    page_url = clean_path(fix.get("page_url") or first_value(fix.get("affected_pages")) or "/")
    page_value = score_page_value(page_url, site_fingerprint, body, playbook)
    defect_class = classify_defect_class(fix)
    evidence_confidence = score_evidence_confidence(fix)
    reach_score = max(5, min(100, len(fix.get("affected_pages") or [1]) * 10))
    structural_boost = 18 if defect_class in {"structural", "crawl_index", "blocked_access"} else 0
    trust_boost = 12 if site_fingerprint["regulatory_sensitivity"] != "standard" and defect_class in {"content_trust", "semantic_schema", "crawl_index", "structural"} else 0
    overall = round(evidence_confidence * 0.22 + page_value["score"] * 0.26 + reach_score * 0.14 + structural_boost + trust_boost + 24)
    if fix.get("url_confidence") == "crawler_artifact":
        overall = min(overall, 44)
    overall = max(0, min(100, overall))
    priority = "critical" if fix.get("priority") == "critical" or overall >= 82 else "high" if overall >= 68 else "medium" if overall >= 44 else "low"
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
        "page_template_family": fix.get("page_template_family") or get_template_family(page_url),
        "page_value_score": page_value["score"],
        "page_value_label": page_value["label"],
        "primary_defect_class": defect_class,
        "meta_rewrite_allowed": False,
        "meta_regeneration_gate": "not_metadata_primary_gap",
        "business_importance": page_value["classification"],
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


def build_review_payload(body: dict[str, Any], pages: list[dict[str, Any]], fixes: list[dict[str, Any]], site_fingerprint: dict[str, Any], playbook: dict[str, Any], website_url: str) -> dict[str, Any]:
    incomplete = evidence_is_incomplete(site_fingerprint)
    blocked = crawl_is_blocked(site_fingerprint)
    quality = review_input_quality(body, site_fingerprint)
    health_score = compute_health_score(fixes, site_fingerprint)
    summary = f"FixList recognized this as {playbook['label']} and used the {playbook['label']} playbook. The scanner reviewed {site_fingerprint['pages_crawled']} pages"
    if site_fingerprint.get("pages_found"):
        summary += f" out of about {site_fingerprint['pages_found']} discovered URLs"
    summary += f". Start with the highest-impact items on {', '.join(playbook['priority_pages'][:3])}."
    if incomplete:
        summary = INCOMPLETE_REVIEW_WARNING
    working = [f"FixList detected a {playbook['label']} pattern."] if site_fingerprint["primary_archetype"] != "general" else []
    top_concerns = [fix.get("issue_title") or fix.get("title") for fix in fixes[:3] if fix.get("issue_title") or fix.get("title")]
    quick_wins = [fix.get("issue_title") or fix.get("title") for fix in fixes if fix.get("difficulty") != "developer"][:3]
    bigger_projects = [fix.get("issue_title") or fix.get("title") for fix in fixes if fix.get("difficulty") == "developer" or fix.get("requires_developer")][:3]
    report = {
        "health_score": health_score,
        "score": health_score,
        "overall_explanation": summary,
        "health_grade": "Blocked / incomplete" if blocked else "Scan incomplete" if incomplete else "Strong" if health_score >= 90 else "Good" if health_score >= 80 else "Needs work" if health_score >= 65 else "Major issues",
        "what_is_working": working,
        "top_concerns": top_concerns,
        "quick_wins": quick_wins,
        "bigger_projects": bigger_projects,
        "limitations": [
            "This scan is read-only and cannot confirm private analytics, paid search data, conversions, or server logs.",
            "HTTP 429 and connection-verification results need access-log confirmation before being treated as confirmed broken customer pages.",
        ],
        "next_best_step": "Ask your web person to verify crawler access, rate limits, CDN, firewall, and bot-protection settings." if blocked else "Re-run the scan — page evidence did not reach AI Review." if incomplete else ((fixes[0].get("issue_title") or fixes[0].get("title")) if fixes else "Review the first FixList item."),
    }
    pages_returned = pages[:80]
    return {
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
        "site_fingerprint": {**site_fingerprint, "review_input_quality": quality},
        "review_input_quality": quality,
        "review_quality_gate_version": QUALITY_GATE_VERSION,
        "evidence_complete": not incomplete,
        "scan_status": "blocked_or_incomplete" if blocked else "incomplete_evidence" if incomplete else "complete",
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
            "pages_scanned": site_fingerprint["pages_crawled"],
            "plain_english_summary": summary,
            "site_fingerprint": site_fingerprint,
            "review_input_quality": quality,
        },
        "scoring_model": SCORING_MODEL,
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
        score += 32
    if any(pattern in path for pattern in playbook["money_patterns"]):
        score += 24
    if has_any(path, ["contact", "devis", "quote", "simulation", "calculator", "comparateur", "booking", "reservation", "annonce", "voir", "cadeau", "coffret", "loisir", "pricing", "demo", "signup", "product", "products", "collection", "collections", "checkout", "loan", "loans", "apply", "payoff", "document-exchange", "locations", "fix-and-flip"]):
        score += 24
    if is_low_value_page(path):
        score -= 35
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


def compute_health_score(fixes: list[dict[str, Any]], site_fingerprint: dict[str, Any]) -> int:
    score = 92
    for fix in fixes:
        priority = fix.get("priority")
        if priority == "critical":
            score -= 12
        elif priority == "high":
            score -= 8
        elif priority == "medium":
            score -= 4
        else:
            score -= 1
    if crawl_is_blocked(site_fingerprint):
        return min(score, 45)
    if evidence_is_incomplete(site_fingerprint):
        return min(score, 55)
    if site_fingerprint.get("pages_crawled") == 0:
        score = min(score, 86)
    return max(35, min(98, score))


def fix_sort_key(fix: dict[str, Any]) -> tuple[int, int]:
    priority_score = {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(str(fix.get("priority")), 0)
    return (priority_score, int_or_zero(fix.get("overall_priority_score")))


def get_playbook(key: str) -> dict[str, Any]:
    return PLAYBOOKS.get(key) or PLAYBOOKS["general"]


def detect_business_model(text: str, archetype: str) -> str:
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
    if archetype in {"finance_insurance_lead_gen", "utilities_comparison_lead_gen"}:
        return "regulated_or_trust_lead_generation"
    if archetype == "booking_experiences_marketplace":
        return "booking_or_reservation"
    if archetype == "ecommerce_specialty_retail":
        return "catalog_or_ecommerce"
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
    return status == 429 or has_any(text, ["rate limit", "too many requests", "connection verification", "bot protection", "access denied", "cloudflare"])


def status_bucket_from_page(page: dict[str, Any]) -> str:
    status = int_or_zero(page.get("status_code") or page.get("status"))
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
    value = str(stamped or "").strip()
    if value and value not in LEGACY_TEMPLATE_FAMILIES:
        return value
    return get_template_family(clean_path(url) or "/")


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
    return {"activity_detail": "activity/detail", "booking_or_checkout": "booking", "conversion": "conversion", "contact": "contact", "guide": "guide", "legal_info": "legal info", "product_page": "product", "collection_page": "collection", "route_boundary": "route-boundary", "standard": "standard"}.get(family, family or "standard")


def is_low_value_page(url: str = "") -> bool:
    path = clean_path(url).lower()
    if re.search(r"/(20\d{2})([-/]\d{1,2}|/|$)", path):
        return True
    return any(pattern in path for pattern in LOW_VALUE_PATTERNS)


def is_route_boundary_candidate(url: str = "") -> bool:
    path = clean_path(url).lower()
    return any(pattern in path for pattern in ["/login", "/register", "/forgot-password", "/reset-password", "/account", "/my-account", "/dashboard", "/admin", "/billing", "/cart", "/checkout"])


def is_internal_app_route(url: str = "") -> bool:
    path = clean_path(url).lower()
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
    if difficulty == "developer" or re.search(r"429|blocked|rate_limited|server_error|404|410|broken|canonical|redirect|route_boundary|indexability|template", text, re.I):
        if re.search(r"429|blocked|rate_limited", rule, re.I):
            return ["Send the grouped affected URLs to your web person.", "Check CDN, firewall, server, and bot-protection logs for HTTP 429 or verification responses.", "Confirm whether Googlebot and normal users can load the pages.", "Adjust rate-limit or bot-protection rules only if legitimate crawlers or users are blocked.", "Run FixList again to confirm the affected pages load."]
        if re.search(r"404|410|broken", text, re.I):
            return ["Send the affected URLs and source-page evidence to your web person.", "Decide whether each URL should be restored, redirected, or removed from internal links.", "Update the source links or add 301 redirects to the closest relevant live page.", "Run FixList again to confirm the URLs no longer fail."]
        return ["Send this recommendation to your web person.", "Update the routing, canonical, schema, indexability, or shared template configuration.", "Publish the change and rerun FixList to verify it."]
    if category == "image_alt_text":
        return ["Open the affected page or template.", "Add short, specific alt text to meaningful images.", "Publish the update and run FixList again."]
    return ["Open the affected page or template.", clean_str(recommended_value) or "Apply the recommended change.", "Publish the update and run FixList again."]


def needs_developer_owner(item: dict[str, Any]) -> bool:
    affected = item.get("affected_pages") or []
    affected_count = len(set(map(clean_path, affected))) if isinstance(affected, list) else 0
    page_template_family = str(item.get("page_template_family") or "")
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
        groups[str(fix.get("page_template_family") or "site")].append(fix)
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


def int_or_zero(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def parse_json_object(value: str) -> dict[str, Any]:
    try:
        import json
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def clean_str(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def clean_path(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.path or '/'}{('?' + parsed.query) if parsed.query else ''}"
    return raw if raw.startswith("/") else f"/{raw}"


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


def has_any(text: str, needles: list[str]) -> bool:
    haystack = str(text or "").lower()
    return any(str(needle or "").lower() in haystack for needle in needles)


def count_includes(text: str, keyword: str) -> int:
    needle = str(keyword or "").lower()
    if not needle:
        return 0
    return str(text or "").lower().count(needle)


def count_lists(*values: Any) -> int:
    return sum(len(value) for value in values if isinstance(value, list))


def dedupe_strings(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        item = str(value)
        if item and item not in seen:
            seen.add(item)
            output.append(item)
    return output


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