from __future__ import annotations

from typing import Any

from . import review as base

# Keep the public contract version accepted by Base44 while exposing the polish
# version separately in the review payload. Base44 currently gates on the
# python_review_v1_archetype_templates contract string.
REVIEW_VERSION = base.REVIEW_VERSION
SCORING_MODEL = "python_review_v2_group_dedup"
POLISH_VERSION = "python_review_v2_group_dedup"


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


# Grouped cards produced by our deterministic generators. Raw scanner-provided
# groupings are intentionally excluded so they cannot suppress a more specific
# single-page fix.
GENERATOR_GROUP_SOURCES = ("page_pattern:", "scanner_verified_failed_pages:", "archetype_")


def suppress_group_covered_singletons(fixes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop single-page fixes already covered by one of our grouped cards of the same defect class."""

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

    output: list[dict[str, Any]] = []
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


# Monkey-patch the base review module so existing generator code uses the polish.
base.family_label = family_label
base.prepare_fixes = prepare_fixes
base.fix_dedup_class = fix_dedup_class
base.suppress_group_covered_singletons = suppress_group_covered_singletons
base.SCORING_MODEL = SCORING_MODEL


def run_review(payload: dict[str, Any]) -> dict[str, Any]:
    result = base.run_review(payload)
    result["review_polish_version"] = POLISH_VERSION
    result["group_dedup_version"] = POLISH_VERSION
    result["scoring_model"] = SCORING_MODEL
    if isinstance(result.get("scan_summary"), dict):
        result["scan_summary"]["scoring_model"] = SCORING_MODEL
    return result
