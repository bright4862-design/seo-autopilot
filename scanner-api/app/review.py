from __future__ import annotations

from typing import Any

from . import review_base as base
from .review_base import *  # noqa: F401,F403 - preserve the existing public review helpers

REVIEW_VERSION = base.REVIEW_VERSION
SCORING_MODEL = "python_review_v2_group_dedup"
QUALITY_GATE_VERSION = base.QUALITY_GATE_VERSION
INCOMPLETE_REVIEW_WARNING = base.INCOMPLETE_REVIEW_WARNING


def run_review(payload: dict[str, Any]) -> dict[str, Any]:
    body = base.unwrap_scan_payload(payload)
    website_url = base.clean_str(
        body.get("website_url")
        or body.get("normalized_url")
        or body.get("url")
        or base.deep_get(body, "technical_audit_summary", "website_url")
        or ""
    )
    pages = base.first_array(
        body.get("crawled_pages"),
        body.get("pages"),
        body.get("scanned_pages"),
        body.get("crawl_pages"),
        base.deep_get(body, "technical_audit_summary", "pages"),
    )
    raw_fixes = base.collect_arrays(
        body.get("raw_fixes"),
        body.get("grouped_findings"),
        body.get("raw_findings"),
        body.get("findings"),
        body.get("fixes"),
        body.get("recommendations"),
        body.get("issues"),
    )

    site_fingerprint = base.build_site_fingerprint(body, pages, website_url)
    site_fingerprint["scoring_model"] = SCORING_MODEL
    playbook = base.get_playbook(site_fingerprint["primary_archetype"])
    evidence_fixes = base.build_scanner_evidence_findings(body, pages, site_fingerprint)
    page_pattern_fixes = build_page_pattern_findings(pages)
    strategic_fixes = base.build_strategic_findings(body, pages, website_url, site_fingerprint, playbook)
    canonical_fixes = prepare_fixes(raw_fixes + evidence_fixes + page_pattern_fixes + strategic_fixes, site_fingerprint, body, playbook)

    warning = ""
    if base.evidence_is_incomplete(site_fingerprint):
        warning = INCOMPLETE_REVIEW_WARNING
        if not canonical_fixes:
            canonical_fixes = [base.make_missing_evidence_fix()]
    elif not website_url:
        warning = "AI review ran, but website_url was missing. Scanner recommendations are shown."
    elif not canonical_fixes:
        warning = "AI review ran, but no scanner recommendations were provided."

    review_payload = base.build_review_payload(body, pages, canonical_fixes, site_fingerprint, playbook, website_url)
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


def build_page_pattern_findings(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for page in pages:
        url = base.page_evidence_url(page)
        if not url:
            continue
        if base.int_or_zero(page.get("status_code") or page.get("status")) >= 400 or base.is_blocked_access_page(page):
            continue
        family = base.normalize_template_family(page.get("page_template_family"), url)
        canonical = base.clean_str(page.get("canonical") or page.get("canonical_url") or "")
        if not canonical:
            base.add_bucket(buckets, "canonical_missing", "canonical", family, page, "Add canonical URLs across templates", "The page does not expose a canonical URL.", "Canonical URLs help search engines consolidate duplicate and near-duplicate versions of a page.", "Ask your web person to add self-referencing canonicals to the shared template or affected pages.", "developer")
        h1_count = base.int_or_zero(page.get("h1_count"))
        if h1_count == 0:
            base.add_bucket(buckets, "missing_h1", "thin_content", family, page, "Fix missing H1 headings on templates", "The page has no main H1 heading.", "A clear H1 helps users and search engines understand the page topic.", "Add one clear H1 to the affected template or page.", "moderate")
        elif h1_count > 1:
            base.add_bucket(buckets, "multiple_h1", "thin_content", family, page, "Use one main page heading", "The page has more than one H1 heading.", "Multiple H1s can make the page structure less clear.", "Keep one H1 as the main page heading and make the rest H2/H3 headings.", "easy")
        missing_alt = base.int_or_zero(page.get("image_missing_alt_count") or page.get("missing_alt_image_count"))
        if missing_alt > 0:
            base.add_bucket(buckets, "image_alt_text", "image_alt_text", family, page, "Batch image descriptions on templates", f"{missing_alt} images missing alt text", "Repeated image-alt gaps are usually a shared template or CMS pattern, especially on listing or detail pages.", "Fix one representative page/template first, then roll out the same rule across the affected group.", "developer" if missing_alt >= 8 else "easy")
        if not base.clean_str(page.get("meta_description")):
            base.add_bucket(buckets, "missing_meta_description", "meta_description", family, page, "Batch meta descriptions on templates", "The page is missing a meta description.", "Search descriptions can improve how pages appear in search results.", "Add a short description that explains the page and why someone should click.", "easy")

    fixes = []
    for bucket in buckets.values():
        affected = [base.page_evidence_url(page) for page in bucket["pages"]]
        is_group = len(set(map(base.clean_path, affected))) > 1
        title = bucket["title"].replace("templates", f"{family_label(bucket['family'])} templates") if is_group else bucket["title"].replace("templates", "the affected page")
        fixes.append(base.make_fix(
            rule=bucket["rule"],
            category=bucket["category"],
            priority="critical" if bucket["category"] == "canonical" else "high" if len(bucket["pages"]) >= 8 else "medium",
            title=title,
            explanation="Several similar pages have the same template-level issue. Fix the shared template or pattern instead of creating one task per page." if is_group else bucket["explanation"],
            why="Large sites usually have template problems. Grouping keeps the FixList focused on the highest-impact patterns." if is_group else bucket["why"],
            recommendation=bucket["recommendation"],
            affected_pages=affected,
            difficulty="developer" if len(set(map(base.clean_path, affected))) >= 5 else bucket["difficulty"],
            source=f"page_pattern:{bucket['rule']}:{bucket['family']}",
            extra={
                "current_value": base.template_current_value(affected),
                "defect_summary": bucket["explanation"],
                "source_pages": base.dedupe_strings([base.clean_path(u) for u in affected if base.clean_path(u)])[:30],
                "page_template_family": bucket["family"],
            },
        ))
    return fixes


def fix_dedup_class(fix: dict[str, Any]) -> str:
    text = " ".join(str(fix.get(k, "")) for k in ["rule", "category", "issue_title", "title"]).lower()
    if "canonical" in text:
        return "canonical"
    if base.has_any(text, ["h1", "heading"]):
        return "h1"
    if base.has_any(text, ["meta description", "meta_description", "description"]):
        return "meta_description"
    if base.has_any(text, ["alt text", "image_alt", "alt_text", "image description"]):
        return "image_alt"
    if base.has_any(text, ["schema", "structured data"]):
        return "schema"
    if base.has_any(text, ["429", "blocked", "rate limit"]):
        return "blocked_access"
    if base.has_any(text, ["404", "410", "500", "503", "5xx", "broken", "server error", "not found"]):
        return "broken_page"
    return str(fix.get("rule") or fix.get("category") or "general")


GENERATOR_GROUP_SOURCES = ("page_pattern:", "scanner_verified_failed_pages:", "archetype_")


def suppress_group_covered_singletons(fixes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop per-page fixes already covered by one of our grouped template/evidence cards of the same defect class."""

    def pages_of(fix: dict[str, Any]) -> list[str]:
        return base.dedupe_strings([base.clean_path(u) for u in (fix.get("affected_pages") or []) if base.clean_path(u)])

    def is_generator_group(fix: dict[str, Any]) -> bool:
        return str(fix.get("source", "")).startswith(GENERATOR_GROUP_SOURCES)

    covered: set[tuple[str, str]] = set()
    for fix in fixes:
        pages = pages_of(fix)
        if len(pages) > 1 and is_generator_group(fix):
            cls = fix_dedup_class(fix)
            for page in pages:
                covered.add((cls, page))
    if not covered:
        return fixes

    output = []
    for fix in fixes:
        pages = pages_of(fix)
        if len(pages) <= 1:
            page = pages[0] if pages else base.clean_path(fix.get("page_url") or "")
            if page and (fix_dedup_class(fix), page) in covered:
                continue
        output.append(fix)
    return output


def prepare_fixes(raw_fixes: list[dict[str, Any]], site_fingerprint: dict[str, Any], body: dict[str, Any], playbook: dict[str, Any]) -> list[dict[str, Any]]:
    normalized = base.dedupe_fixes([base.normalize_fix(fix, index) for index, fix in enumerate(raw_fixes or []) if isinstance(fix, dict)])
    scored = [base.score_fix(fix, site_fingerprint, body, playbook) for fix in normalized]
    scored = suppress_group_covered_singletons(scored)
    return sorted(scored, key=base.fix_sort_key, reverse=True)[:36]


def family_label(family: str) -> str:
    return {
        "activity_detail": "activity/detail",
        "booking_or_checkout": "booking",
        "conversion": "conversion",
        "contact": "contact",
        "guide": "guide",
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
