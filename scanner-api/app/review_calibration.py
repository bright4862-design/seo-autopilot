from __future__ import annotations

from copy import deepcopy
import re
from typing import Any
from urllib.parse import urlparse

from .health_score_explanation import apply_score_ceiling, build_health_score_explanation
from .review import compute_health_score_breakdown, group_page_recommendations, unwrap_scan_payload

CALIBRATION_VERSION = "review_evidence_calibration_v6_health_score_v2"
IMAGE_ALT_EVIDENCE_VERSION = "material_image_alt_v1"
IMAGE_ALT_RULES = {"image_alt_text", "missing_image_alt"}
VERIFICATION_ONLY_RULES = {"potential_orphan_pages", "indexable_faceted_navigation"}
VERIFICATION_ONLY_LIMITATION_CODES = {
    "sampled_crawl_cannot_prove_orphan",
    "faceted_navigation_requires_strategy_review",
}
CANONICAL_MISSING_RULES = {"canonical_missing", "missing_canonical"}
SITEMAP_REDIRECT_RULES = {"sitemap_redirect"}
TRAILING_SLASH_REDIRECT_RULES = {"sitemap_redirect", "internal_link_redirect"}
MISSING_META_DESCRIPTION_RULES = {"missing_meta_description"}
PAGE_SEMANTIC_RULES = {
    "canonical_missing",
    "missing_canonical",
    "missing_h1",
    "multiple_h1",
    "missing_meta_description",
    "missing_title",
    "image_alt_text",
    "missing_image_alt",
}
PAGE_SEMANTIC_CATEGORIES = {"canonical", "thin_content", "meta_description", "meta_title", "image_alt_text"}
UTILITY_PATH_MARKERS = ("/cdn-cgi/",)
NON_HTML_SUFFIXES = (
    ".pdf", ".xml", ".json", ".csv", ".txt", ".zip",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
)
PRIORITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}
LEGAL_TEMPLATE_FAMILIES = {"legal_info", "legal", "terms", "privacy"}
LEGAL_PATH_MARKERS = (
    "/mentions-legales",
    "/mentions_legales",
    "/cgu",
    "/cgv",
    "/conditions-generales",
    "/conditions_generales",
    "/legal",
    "/terms",
    "/privacy",
    "/politique-de-confidentialite",
)


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _path(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
        path = parsed.path or "/"
    except Exception:
        path = raw
    if not path.startswith("/"):
        path = f"/{path}"
    if path != "/":
        path = path.rstrip("/")
    return path


def _pages_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    body = unwrap_scan_payload(payload)
    for key in ("crawled_pages", "pages", "scanned_pages", "crawl_pages"):
        value = body.get(key)
        if isinstance(value, list):
            return [page for page in value if isinstance(page, dict)]
    technical = body.get("technical_audit_summary")
    if isinstance(technical, dict) and isinstance(technical.get("pages"), list):
        return [page for page in technical["pages"] if isinstance(page, dict)]
    return []


def image_alt_evidence(page: dict[str, Any]) -> dict[str, Any]:
    image_count = _int(page.get("image_count"))
    missing_alt = _int(page.get("image_missing_alt_count") or page.get("missing_alt_image_count"))
    ratio = missing_alt / image_count if image_count > 0 else 0.0
    material = bool(
        missing_alt > 0
        and image_count > 0
        and (
            missing_alt >= 8
            or (missing_alt >= 3 and ratio >= 0.10)
            or (missing_alt >= 2 and ratio >= 0.20)
            or (missing_alt == 1 and image_count <= 3)
        )
    )
    return {
        "image_count": image_count,
        "missing_alt": missing_alt,
        "missing_alt_ratio": round(ratio, 3),
        "material": material,
    }


def _content_type(page: dict[str, Any]) -> str:
    headers = page.get("headers") if isinstance(page.get("headers"), dict) else {}
    return str(
        page.get("content_type")
        or page.get("mime_type")
        or headers.get("content-type")
        or headers.get("Content-Type")
        or ""
    ).split(";", 1)[0].strip().lower()


def _is_non_html_or_utility_path(value: Any) -> bool:
    path = _path(value).lower()
    return bool(
        path
        and (
            any(marker in path for marker in UTILITY_PATH_MARKERS)
            or path.endswith(NON_HTML_SUFFIXES)
        )
    )


def _is_non_html_or_utility_page(page: dict[str, Any]) -> bool:
    values = (page.get("url"), page.get("final_url"), page.get("path"), page.get("page_url"))
    if any(_is_non_html_or_utility_path(value) for value in values if value):
        return True
    content_type = _content_type(page)
    return bool(content_type and content_type not in {"text/html", "application/xhtml+xml"})


def _page_evidence_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    evidence: dict[str, dict[str, Any]] = {}
    for page in _pages_from_payload(payload):
        stats = {
            **image_alt_evidence(page),
            "content_type": _content_type(page),
            "non_html_or_utility": _is_non_html_or_utility_page(page),
        }
        for value in (page.get("url"), page.get("final_url"), page.get("path"), page.get("page_url")):
            key = _path(value)
            if key:
                evidence[key] = stats
    return evidence


def _is_page_semantic_fix(fix: dict[str, Any]) -> bool:
    rule = str(fix.get("rule") or "")
    category = str(fix.get("category") or "")
    return rule in PAGE_SEMANTIC_RULES or category in PAGE_SEMANTIC_CATEGORIES


def _calibrate_page_semantic_fix(
    fix: dict[str, Any],
    evidence: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    affected = fix.get("affected_pages") if isinstance(fix.get("affected_pages"), list) else []
    if not affected:
        affected = [fix.get("page_url") or "/"]

    retained: list[str] = []
    suppressed: list[str] = []
    for value in affected:
        key = _path(value)
        if not key:
            continue
        stats = evidence.get(key, {})
        unsupported = bool(stats.get("non_html_or_utility")) or _is_non_html_or_utility_path(key)
        if unsupported:
            suppressed.append(key)
        else:
            retained.append(key)

    if not retained:
        return None
    if not suppressed:
        return fix

    source_pages = fix.get("source_pages") if isinstance(fix.get("source_pages"), list) else []
    retained_set = set(retained)
    filtered_sources = [value for value in source_pages if _path(value) in retained_set]
    return {
        **fix,
        "affected_pages": retained,
        "page_url": retained[0],
        "page_count": len(retained),
        "source_pages": filtered_sources[:30] or retained[:30],
        "non_html_or_utility_pages_suppressed": len(suppressed),
        "page_semantic_calibration_version": CALIBRATION_VERSION,
    }


def _calibrate_image_alt_fix(fix: dict[str, Any], evidence: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    affected = fix.get("affected_pages") if isinstance(fix.get("affected_pages"), list) else []
    if not affected:
        affected = [fix.get("page_url") or "/"]

    matched: list[tuple[str, dict[str, Any]]] = []
    unmatched: list[str] = []
    for value in affected:
        key = _path(value)
        if key in evidence:
            matched.append((key, evidence[key]))
        elif key:
            unmatched.append(key)

    # Preserve findings when the review payload did not include matching page
    # evidence. The calibration gate only suppresses weak evidence it can prove.
    if not matched:
        return fix

    material = [(path, stats) for path, stats in matched if stats["material"]]
    if not material:
        return None

    retained = [path for path, _ in material]
    missing_alt_total = sum(stats["missing_alt"] for _, stats in material)
    image_total = sum(stats["image_count"] for _, stats in material)
    aggregate_ratio = round(missing_alt_total / max(1, image_total), 3)
    max_missing = max(stats["missing_alt"] for _, stats in material)
    max_ratio = max(stats["missing_alt_ratio"] for _, stats in material)

    priority = str(fix.get("priority") or "medium").lower()
    if priority == "critical":
        priority = "high"

    calibrated = {
        **fix,
        "affected_pages": retained,
        "page_url": retained[0],
        "page_count": len(retained),
        "priority": priority,
        "primary_defect_class": "metadata",
        "overall_priority_score": min(79, _int(fix.get("overall_priority_score")) or 79),
        "current_value": (
            f"{len(retained)} materially affected page{'s' if len(retained) != 1 else ''}: "
            f"{missing_alt_total} missing descriptions across {image_total} images "
            f"({round(aggregate_ratio * 100, 1)}%)."
        ),
        "image_alt_evidence_version": IMAGE_ALT_EVIDENCE_VERSION,
        "material_affected_page_count": len(retained),
        "weak_signal_page_count_suppressed": len(matched) - len(material),
        "missing_alt_total": missing_alt_total,
        "image_total": image_total,
        "missing_alt_ratio": aggregate_ratio,
        "max_missing_alt_per_page": max_missing,
        "max_missing_alt_ratio_per_page": max_ratio,
    }

    source_pages = fix.get("source_pages") if isinstance(fix.get("source_pages"), list) else []
    filtered_sources = [value for value in source_pages if _path(value) in set(retained)]
    calibrated["source_pages"] = filtered_sources[:30] or retained[:30]
    return calibrated


def _is_verification_only_fix(fix: dict[str, Any]) -> bool:
    rule = str(fix.get("rule") or "")
    limitation_code = str(fix.get("limitation_code") or "")
    return bool(
        fix.get("non_scoring") is True
        or rule in VERIFICATION_ONLY_RULES
        or limitation_code in VERIFICATION_ONLY_LIMITATION_CODES
    )


def _calibrate_verification_only_fix(fix: dict[str, Any]) -> dict[str, Any]:
    return {
        **fix,
        "priority": "low",
        "overall_priority_score": min(39, _int(fix.get("overall_priority_score")) or 39),
        "score_impact": 0,
        "non_scoring": True,
        "evidence_status": fix.get("evidence_status") or "needs_verification",
        "verification_state": fix.get("verification_state") or "needs_verification",
    }


def _affected_page_count(fix: dict[str, Any]) -> int:
    affected = fix.get("affected_pages") if isinstance(fix.get("affected_pages"), list) else []
    explicit = _int(fix.get("page_count"))
    fallback = 1 if fix.get("page_url") else 0
    return max(explicit, len(affected), fallback)


def _cap_priority(
    fix: dict[str, Any],
    cap: str,
    max_overall_score: int,
    reason: str,
) -> dict[str, Any]:
    current = str(fix.get("priority") or "low").lower()
    if PRIORITY_RANK.get(current, 0) <= PRIORITY_RANK[cap]:
        return fix
    return {
        **fix,
        "priority": cap,
        "overall_priority_score": min(max_overall_score, _int(fix.get("overall_priority_score")) or max_overall_score),
        "severity_calibration_reason": reason,
        "severity_calibration_version": CALIBRATION_VERSION,
    }


def _redirect_endpoint_urls(fix: dict[str, Any]) -> tuple[str, str]:
    source = str(fix.get("redirect_source_url") or fix.get("source_url") or "").strip()
    destination = str(fix.get("redirect_destination_url") or fix.get("destination_url") or "").strip()
    chain = fix.get("redirect_chain") if isinstance(fix.get("redirect_chain"), list) else []
    if not source and chain:
        source = str(chain[0] or "").strip()
    if not destination and len(chain) >= 2:
        destination = str(chain[-1] or "").strip()
    if not source or not destination:
        text = str(fix.get("current_value") or "")
        urls = [value.rstrip(".,;)") for value in re.findall(r"https?://[^\s→—]+", text)]
        if not source and urls:
            source = urls[0]
        if not destination and len(urls) >= 2:
            destination = urls[1]
    return source, destination


def _url_identity_without_trailing_slash(value: str) -> tuple[str, str, str, str] | None:
    try:
        parsed = urlparse(value)
    except Exception:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    path = parsed.path or "/"
    normalized_path = path.rstrip("/") or "/"
    return parsed.scheme.lower(), parsed.netloc.lower(), normalized_path, parsed.query


def _is_trailing_slash_only_healthy_redirect(fix: dict[str, Any]) -> bool:
    if str(fix.get("rule") or "") not in TRAILING_SLASH_REDIRECT_RULES:
        return False
    state = str(fix.get("redirect_state") or "").lower()
    if state and state not in {"single_redirect", "redirect", "redirected"}:
        return False
    if _int(fix.get("redirect_hop_count")) > 1:
        return False
    chain = fix.get("redirect_chain") if isinstance(fix.get("redirect_chain"), list) else []
    if chain and len(chain) != 2:
        return False

    text = " ".join(
        str(fix.get(key) or "")
        for key in (
            "current_value",
            "redirect_destination_status",
            "redirect_destination_indexability",
            "redirect_destination_state",
        )
    ).lower()
    if any(marker in text for marker in (
        "loop", "chain", "failed", "failure", "blocked", "noindex",
        "non-public", "invalid location", "missing location", "too many redirects",
    )):
        return False
    status_is_healthy = (
        "destination http 200" in text
        or _int(fix.get("redirect_destination_status")) == 200
        or _int(fix.get("destination_status_code")) == 200
    )
    destination_is_indexable = (
        "destination: indexable" in text
        or str(fix.get("redirect_destination_indexability") or "").lower() == "indexable"
        or fix.get("redirect_destination_indexable") is True
    )
    if not status_is_healthy or not destination_is_indexable:
        return False

    source, destination = _redirect_endpoint_urls(fix)
    source_identity = _url_identity_without_trailing_slash(source)
    destination_identity = _url_identity_without_trailing_slash(destination)
    if not source_identity or source_identity != destination_identity:
        return False
    source_path = urlparse(source).path or "/"
    destination_path = urlparse(destination).path or "/"
    return source_path != destination_path and source_path.rstrip("/") == destination_path.rstrip("/")


def _is_single_healthy_sitemap_redirect(fix: dict[str, Any]) -> bool:
    if str(fix.get("rule") or "") not in SITEMAP_REDIRECT_RULES:
        return False
    if _affected_page_count(fix) != 1:
        return False

    state = str(fix.get("redirect_state") or "").lower()
    if state and state not in {"single_redirect", "redirect", "redirected"}:
        return False

    chain = fix.get("redirect_chain") if isinstance(fix.get("redirect_chain"), list) else []
    if chain and len(chain) != 2:
        return False
    if _int(fix.get("redirect_hop_count")) > 1:
        return False

    text = " ".join(
        str(fix.get(key) or "")
        for key in (
            "current_value",
            "redirect_destination_status",
            "redirect_destination_indexability",
            "redirect_destination_state",
        )
    ).lower()
    unhealthy_markers = (
        "loop",
        "chain",
        "failed",
        "failure",
        "blocked",
        "noindex",
        "non-public",
        "invalid location",
        "missing location",
        "too many redirects",
    )
    if any(marker in text for marker in unhealthy_markers):
        return False

    status_is_healthy = (
        "destination http 200" in text
        or _int(fix.get("redirect_destination_status")) == 200
        or _int(fix.get("destination_status_code")) == 200
    )
    destination_is_indexable = (
        "destination: indexable" in text
        or str(fix.get("redirect_destination_indexability") or "").lower() == "indexable"
        or fix.get("redirect_destination_indexable") is True
    )
    return status_is_healthy and destination_is_indexable


def _is_legal_page_path(value: Any) -> bool:
    path = _path(value).lower()
    return bool(path and any(marker in path for marker in LEGAL_PATH_MARKERS))


def _is_narrow_legal_canonical_fix(fix: dict[str, Any]) -> bool:
    if str(fix.get("rule") or "") not in CANONICAL_MISSING_RULES:
        return False
    if _affected_page_count(fix) > 5:
        return False
    if str(fix.get("page_scope") or "").lower() == "sitewide":
        return False

    family = str(fix.get("page_template_family") or fix.get("page_type") or "").lower()
    if family in LEGAL_TEMPLATE_FAMILIES:
        return True

    affected = fix.get("affected_pages") if isinstance(fix.get("affected_pages"), list) else []
    if not affected and fix.get("page_url"):
        affected = [fix.get("page_url")]
    return bool(affected and all(_is_legal_page_path(value) for value in affected))


def _calibrate_scope_sensitive_fix(fix: dict[str, Any]) -> dict[str, Any]:
    rule = str(fix.get("rule") or "")
    affected_count = _affected_page_count(fix)
    page_scope = str(fix.get("page_scope") or "").lower()

    if _is_narrow_legal_canonical_fix(fix):
        return _cap_priority(
            fix,
            "medium",
            67,
            "legal_page_missing_canonical_scope",
        )

    if rule in CANONICAL_MISSING_RULES and affected_count <= 2 and page_scope != "sitewide":
        return _cap_priority(
            fix,
            "high",
            81,
            "narrow_missing_canonical_scope",
        )

    if _is_trailing_slash_only_healthy_redirect(fix):
        return _cap_priority(
            fix,
            "medium",
            67,
            "trailing_slash_only_healthy_redirect",
        )

    if _is_single_healthy_sitemap_redirect(fix):
        return _cap_priority(
            fix,
            "medium",
            67,
            "single_healthy_sitemap_redirect",
        )

    if rule in MISSING_META_DESCRIPTION_RULES and affected_count == 1:
        return _cap_priority(
            fix,
            "medium",
            67,
            "single_page_missing_meta_description",
        )

    return fix


def _fix_sort_key(fix: dict[str, Any]) -> tuple[int, int]:
    priority_score = PRIORITY_RANK.get(str(fix.get("priority") or ""), 0)
    return (priority_score, _int(fix.get("overall_priority_score")))


def _health_grade(score: int, scan_status: str) -> str:
    if scan_status == "blocked_or_incomplete":
        return "Blocked / incomplete"
    if scan_status == "incomplete_evidence":
        return "Scan incomplete"
    if scan_status == "inconclusive_insufficient_evidence":
        return "Insufficient evidence"
    if score >= 85:
        return "Strong"
    if score >= 70:
        return "Good"
    if score >= 50:
        return "Needs work"
    return "Major issues"


def apply_review_evidence_calibration(result: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict):
        return result

    calibrated_result = deepcopy(result)
    evidence = _page_evidence_map(payload)
    source_fixes = calibrated_result.get("recommendations")
    if not isinstance(source_fixes, list):
        source_fixes = calibrated_result.get("fixes") if isinstance(calibrated_result.get("fixes"), list) else []

    fixes: list[dict[str, Any]] = []
    for item in source_fixes:
        if not isinstance(item, dict):
            continue
        rule = str(item.get("rule") or item.get("category") or "")
        if _is_page_semantic_fix(item):
            item = _calibrate_page_semantic_fix(item, evidence)
            if item is None:
                continue
        if rule in IMAGE_ALT_RULES or str(item.get("category") or "") == "image_alt_text":
            item = _calibrate_image_alt_fix(item, evidence)
            if item is None:
                continue
        if _is_verification_only_fix(item):
            item = _calibrate_verification_only_fix(item)
        else:
            item = _calibrate_scope_sensitive_fix(item)
        fixes.append(item)

    fixes = sorted(fixes, key=_fix_sort_key, reverse=True)
    scoring_fixes = [item for item in fixes if not _is_verification_only_fix(item)]

    fingerprint = calibrated_result.get("site_fingerprint")
    if not isinstance(fingerprint, dict):
        fingerprint = {}
    # One breakdown, used for both the score and its explanation. Computing the
    # score here and the explanation from a second call would let the two drift
    # the moment either input changed.
    breakdown = compute_health_score_breakdown(scoring_fixes, fingerprint) if fingerprint else None
    score = _int(breakdown["score"]) if breakdown else _int(calibrated_result.get("health_score"))
    score = max(0, min(100, score))
    explanation = build_health_score_explanation(
        breakdown,
        verification_findings_excluded=len(scoring_fixes) != len(fixes),
    )

    for key in ("recommended_actions", "cleaned_fixes", "raw_fixes", "fixes", "findings", "recommendations"):
        calibrated_result[key] = fixes
    calibrated_result["top_recommended_actions"] = fixes[:5]
    calibrated_result["grouped_page_recommendations"] = group_page_recommendations(fixes)
    calibrated_result["health_score"] = score
    calibrated_result["seo_score"] = score
    calibrated_result["review_evidence_calibration_version"] = CALIBRATION_VERSION

    scan_status = str(calibrated_result.get("scan_status") or "complete")
    if scan_status == "inconclusive_insufficient_evidence":
        score = min(score, 55)
        calibrated_result["health_score"] = score
        calibrated_result["seo_score"] = score
        explanation = apply_score_ceiling(explanation, score, "incomplete_evidence")

    # Written after every ceiling this function applies, so `final_score` is the
    # score the record actually carries.
    if explanation:
        calibrated_result["health_score_explanation"] = explanation
    else:
        calibrated_result.pop("health_score_explanation", None)
    report = calibrated_result.get("website_health_report")
    if not isinstance(report, dict):
        report = {}
    report = {
        **report,
        "health_score": score,
        "score": score,
        "health_grade": _health_grade(score, scan_status),
        "top_concerns": [fix.get("issue_title") or fix.get("title") for fix in fixes[:3]],
        "next_best_step": (
            report.get("next_best_step")
            if scan_status in {"blocked_or_incomplete", "incomplete_evidence", "inconclusive_insufficient_evidence"}
            else ((fixes[0].get("issue_title") or fixes[0].get("title")) if fixes else "No high-confidence fixes were found in the reviewed sample.")
        ),
    }
    calibrated_result["website_health_report"] = report
    calibrated_result["health_grade"] = report["health_grade"]
    calibrated_result["next_best_step"] = report["next_best_step"]

    scan_summary = calibrated_result.get("scan_summary")
    if not isinstance(scan_summary, dict):
        scan_summary = {}
    scan_summary = {
        **scan_summary,
        "health_score": score,
        "score": score,
        "scoring_model": calibrated_result.get("scoring_model") or "python_review_v2_group_dedup",
    }
    calibrated_result["scan_summary"] = scan_summary

    site_summary = calibrated_result.get("site_summary")
    if not isinstance(site_summary, dict):
        site_summary = {}
    site_summary = {
        **scan_summary,
        **site_summary,
        "health_score": score,
        "score": score,
        "pages_scanned": site_summary.get("pages_scanned") or scan_summary.get("pages_scanned") or fingerprint.get("pages_crawled") or 0,
        "pages_crawled": site_summary.get("pages_crawled") or fingerprint.get("pages_crawled") or 0,
        "pages_found": site_summary.get("pages_found") or fingerprint.get("pages_found") or 0,
        "scan_status": scan_status,
        "review_confidence_state": calibrated_result.get("review_confidence_state") or "complete",
        "score_is_provisional": bool(calibrated_result.get("score_is_provisional")),
        "access_evidence_state": calibrated_result.get("access_evidence_state") or "complete",
        "scoring_model": calibrated_result.get("scoring_model") or "python_review_v2_group_dedup",
    }
    calibrated_result["site_summary"] = site_summary

    technical = calibrated_result.get("technical_audit_summary")
    if not isinstance(technical, dict):
        technical = {}
    calibrated_result["technical_audit_summary"] = {
        **technical,
        "health_score": score,
        "score": score,
        "scoring_model": calibrated_result.get("scoring_model") or "python_review_v2_group_dedup",
    }
    return calibrated_result
