from __future__ import annotations

from copy import deepcopy
from typing import Any

from . import review as review_engine
from .extract import classify_template

REVIEW_VERSION = review_engine.REVIEW_VERSION
REVIEW_EVIDENCE_CONTRACT_VERSION = "review_evidence_contract_v1"

LEGACY_TEMPLATE_FAMILIES = {"", "standard", "category_listing", "guide", "qa", "product_detail"}
TEMPLATE_OWNED_FAMILIES = {
    "activity_detail",
    "booking_or_checkout",
    "product_page",
    "collection_page",
    "conversion",
    "loan_program",
    "calculator",
    "comparison_page",
    "location_landing",
    "route_boundary",
}
TEMPLATE_RULES = {
    "canonical_missing",
    "missing_canonical",
    "missing_h1",
    "multiple_h1",
    "image_alt_text",
    "missing_image_alt",
    "missing_meta_description",
}


def run_review(payload: dict[str, Any]) -> dict[str, Any]:
    """Run AI Review with stricter evidence normalization at the API boundary."""
    body = review_engine.unwrap_scan_payload(payload)
    guarded_body = normalize_review_input(body)
    result = review_engine.run_review(guarded_body)
    return normalize_review_output(result)


def normalize_review_input(body: dict[str, Any]) -> dict[str, Any]:
    guarded = deepcopy(body if isinstance(body, dict) else {})
    pages = first_page_array(guarded)
    if not pages:
        return guarded
    guarded_pages = [normalize_page_for_review(page) for page in pages]
    write_page_arrays(guarded, guarded_pages)
    guarded["review_evidence_contract_version"] = REVIEW_EVIDENCE_CONTRACT_VERSION
    return guarded


def normalize_page_for_review(page: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(page if isinstance(page, dict) else {})
    url = page_url(normalized)
    normalized["page_template_family"] = normalize_template_family(normalized.get("page_template_family"), url)
    if is_failed_or_limited_page(normalized):
        normalized["canonical"] = normalized.get("canonical") or normalized.get("canonical_url") or url or "/"
        normalized["canonical_url"] = normalized.get("canonical_url") or normalized.get("canonical") or url or "/"
        normalized["h1_count"] = max(1, int_or_zero(normalized.get("h1_count")))
        normalized["meta_description"] = normalized.get("meta_description") or "Skipped content checks because this page did not return usable crawl content."
        normalized["image_missing_alt_count"] = 0
        normalized["missing_alt_image_count"] = 0
    return normalized


def normalize_review_output(result: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict):
        return result
    output = deepcopy(result)
    for key in [
        "cleaned_fixes",
        "raw_fixes",
        "fixes",
        "findings",
        "recommendations",
        "recommended_actions",
        "top_recommended_actions",
    ]:
        if isinstance(output.get(key), list):
            output[key] = [normalize_fix_evidence(item) if isinstance(item, dict) else item for item in output[key]]
    if isinstance(output.get("cleaned_fixes"), list):
        output["grouped_page_recommendations"] = review_engine.group_page_recommendations(output["cleaned_fixes"])
    output["review_evidence_contract_version"] = REVIEW_EVIDENCE_CONTRACT_VERSION
    return output


def normalize_fix_evidence(fix: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(fix)
    affected = dedupe_paths(normalized.get("affected_pages") or normalized.get("pages") or normalized.get("page_urls") or [])
    fallback = clean_path(normalized.get("page_url") or normalized.get("url") or "")
    if fallback and fallback not in affected:
        affected.append(fallback)
    if not affected:
        affected = ["/"]
    normalized["affected_pages"] = affected[:150]
    normalized["page_url"] = clean_path(normalized.get("page_url") or affected[0]) or "/"
    source_pages = normalized.get("source_pages") if isinstance(normalized.get("source_pages"), list) else []
    normalized["source_pages"] = dedupe_paths(source_pages or affected)[:30]
    family = normalize_template_family(normalized.get("page_template_family"), normalized.get("page_url"))
    normalized["page_template_family"] = family
    rule = str(normalized.get("rule") or "")
    source = str(normalized.get("source") or "")
    if source.startswith("page_pattern:") or rule in TEMPLATE_RULES:
        normalized["current_value"] = template_current_value(affected)
    if not str(normalized.get("current_value") or "").strip():
        normalized["current_value"] = template_current_value(affected)
    if family in TEMPLATE_OWNED_FAMILIES and len(set(affected)) >= 2 and (source.startswith("page_pattern:") or rule in TEMPLATE_RULES):
        normalized["difficulty"] = "developer"
        normalized["status"] = "needs_developer"
        normalized["requires_developer"] = True
        normalized["requires_approval"] = False
        normalized["can_auto_fix"] = False
        normalized["who_can_do_this"] = "your_web_person"
    return normalized


def normalize_template_family(stamped: Any, url: Any = "") -> str:
    value = str(stamped or "").strip()
    if value and value not in LEGACY_TEMPLATE_FAMILIES:
        return value
    return classify_template(clean_path(url) or "/")


def template_current_value(affected_paths: list[Any]) -> str:
    paths = dedupe_paths(affected_paths)
    if not paths:
        return "No affected pages recorded."
    count = len(paths)
    sample = ", ".join(paths[:3])
    more = f" (+{count - 3} more)" if count > 3 else ""
    noun = "page" if count == 1 else "pages"
    return f"{count} affected {noun}: {sample}{more}"


def first_page_array(body: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ["crawled_pages", "pages", "scanned_pages", "crawl_pages"]:
        value = body.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    technical = body.get("technical_audit_summary")
    technical_pages = technical.get("pages") if isinstance(technical, dict) else None
    if isinstance(technical_pages, list):
        return [item for item in technical_pages if isinstance(item, dict)]
    return []


def write_page_arrays(body: dict[str, Any], pages: list[dict[str, Any]]) -> None:
    wrote = False
    for key in ["crawled_pages", "pages", "scanned_pages", "crawl_pages"]:
        if isinstance(body.get(key), list):
            body[key] = pages
            wrote = True
    if not wrote:
        body["pages"] = pages
    technical = body.get("technical_audit_summary")
    if isinstance(technical, dict) and isinstance(technical.get("pages"), list):
        technical["pages"] = pages


def is_failed_or_limited_page(page: dict[str, Any]) -> bool:
    status = int_or_zero(page.get("status_code") or page.get("status"))
    if status >= 400:
        return True
    text = f"{page.get('fetch_error', '')} {page.get('error', '')} {page.get('title', '')} {page.get('content_type', '')}".lower()
    return any(token in text for token in ["not found", "server error", "rate limit", "too many requests", "verification", "limited"])


def page_url(page: dict[str, Any]) -> str:
    return str(page.get("url") or page.get("final_url") or page.get("path") or page.get("page_url") or "/")


def clean_path(value: Any) -> str:
    return review_engine.clean_path(value)


def dedupe_paths(values: list[Any]) -> list[str]:
    return review_engine.dedupe_strings([clean_path(value) for value in values if clean_path(value)])


def int_or_zero(value: Any) -> int:
    return review_engine.int_or_zero(value)
