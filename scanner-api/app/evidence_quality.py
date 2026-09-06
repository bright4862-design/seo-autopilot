from __future__ import annotations

from copy import deepcopy

from .coverage_authority import assess_coverage, coverage_inputs_from_payload
from typing import Any
from urllib.parse import urlparse

from .health_score_explanation import apply_score_ceiling
from .review import unwrap_scan_payload

EVIDENCE_QUALITY_GATE_VERSION = "evidence_quality_gate_v2_shared_coverage_decision"

LIMITED_SCAN_STATUSES = {
    "complete_with_access_limitations",
    "incomplete_evidence",
    "inconclusive_insufficient_evidence",
    "blocked_or_incomplete",
}
DEFAULT_ROUTE_EXACT = {
    "/hello-world",
    "/sample-page",
    "/category/uncategorized",
    "/tag/uncategorized",
    "/uncategorized",
    "/wp-login",
    "/wp-admin",
    "/feed",
}
DEFAULT_ROUTE_PREFIXES = (
    "/author/",
    "/wp-admin/",
    "/wp-json/",
)
NON_HTML_SUFFIXES = (
    ".pdf", ".xml", ".json", ".csv", ".txt", ".zip",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
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
    return path.lower()


def _content_type(page: dict[str, Any]) -> str:
    headers = page.get("headers") if isinstance(page.get("headers"), dict) else {}
    return str(
        page.get("content_type")
        or page.get("mime_type")
        or headers.get("content-type")
        or headers.get("Content-Type")
        or ""
    ).split(";", 1)[0].strip().lower()


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


def _is_usable_html(page: dict[str, Any]) -> bool:
    status = _int(page.get("status_code") or page.get("status"))
    if status != 200 or str(page.get("fetch_error") or "").strip():
        return False
    path = _path(page.get("final_url") or page.get("url") or page.get("path"))
    if path.endswith(NON_HTML_SUFFIXES):
        return False
    content_type = _content_type(page)
    if content_type and content_type not in {"text/html", "application/xhtml+xml"}:
        return False
    return bool(
        str(page.get("title") or "").strip()
        or str(page.get("h1") or "").strip()
        or _int(page.get("word_count")) >= 20
        or path == "/"
    )


def _is_default_route(page: dict[str, Any]) -> bool:
    path = _path(page.get("final_url") or page.get("url") or page.get("path"))
    family = str(page.get("page_template_family") or "").strip().lower()
    intent = str(page.get("estimated_page_intent") or "").strip().lower()
    return bool(
        path in DEFAULT_ROUTE_EXACT
        or any(path.startswith(prefix) for prefix in DEFAULT_ROUTE_PREFIXES)
        or family == "route_boundary"
        or intent == "internal_or_auth"
    )


def _meaningful_root(page: dict[str, Any]) -> bool:
    path = _path(page.get("final_url") or page.get("url") or page.get("path"))
    return bool(
        path == "/"
        and _is_usable_html(page)
        and (
            _int(page.get("word_count")) >= 50
            or (str(page.get("title") or "").strip() and str(page.get("h1") or "").strip())
        )
    )


def _blocked_page_count(payload: dict[str, Any], pages: list[dict[str, Any]]) -> int:
    """Challenged/rate-limited pages, from the crawl or counted from evidence."""
    crawl_timing = payload.get("crawl_timing") if isinstance(payload.get("crawl_timing"), dict) else {}
    reported = max(
        _int(payload.get("blocked_or_429_pages")),
        _int(payload.get("blocked_access_pages")),
        _int(crawl_timing.get("blocked_or_429_pages")),
    )
    if reported:
        return reported
    return sum(1 for page in pages if _int(page.get("status_code")) in (401, 403, 429))


def evaluate_evidence_quality(payload: dict[str, Any]) -> dict[str, Any]:
    pages = _pages_from_payload(payload)
    usable = [page for page in pages if _is_usable_html(page)]
    default_routes = [page for page in usable if _is_default_route(page)]
    representative = [page for page in usable if not _is_default_route(page)]
    usable_count = len(usable)
    default_count = len(default_routes)
    representative_count = len(representative)
    default_ratio = default_count / usable_count if usable_count else 0.0
    reasons: list[str] = []
    blocking = False

    # One shared coverage decision. This module does not form its own opinion
    # about whether the crawl saw enough of the site; it reads the verdict and
    # applies it. The previous local rule only guarded the one-page case when
    # the single page was a "meaningful root", so a single page that was not
    # fell straight through to the representative branch and scored 81,
    # non-blocking. That is the path Habito took in production.
    coverage = assess_coverage(coverage_inputs_from_payload(
        payload,
        retained_usable_html=usable_count,
        blocked_or_429_pages=_blocked_page_count(payload, pages),
    ))

    if usable_count == 0:
        state = "no_usable_html"
        discovery_state = "no_usable_html"
        score = 0
        blocking = True
        reasons.append("no_usable_html_pages")
    elif coverage["state"] != "sufficient":
        state = "access_limited" if coverage["state"] == "access_limited" else "insufficient_discovery"
        # Keep the more specific published label where it applies; the coverage
        # state is the general case, not a replacement vocabulary.
        discovery_state = (
            "single_page_inventory_unproven"
            if coverage["state"] == "inventory_unproven" and usable_count == 1
            else coverage["state"]
        )
        score = 35
        blocking = True
        reasons.extend(coverage["reasons"])
    elif usable_count == 1:
        state = "small_site_supported"
        discovery_state = "small_site_supported"
        score = 85
        reasons.append("proven_single_page_inventory")
    elif (
        2 <= usable_count <= 6
        and default_count >= 2
        and default_ratio >= 0.5
        and representative_count <= 2
    ):
        state = "insufficient_discovery"
        discovery_state = "default_route_dominated"
        score = 35
        blocking = True
        reasons.extend(["default_route_dominance", "representative_html_pages_below_minimum"])
    else:
        state = "representative"
        discovery_state = "representative"
        score = min(100, 80 + min(20, representative_count))
        reasons.append("representative_html_evidence")

    return {
        "evidence_quality_state": state,
        "evidence_quality_score": score,
        "evidence_quality_reasons": reasons,
        "discovery_quality_state": discovery_state,
        "representative_html_page_count": representative_count,
        "usable_html_page_count": usable_count,
        "default_route_page_count": default_count,
        "default_route_ratio": round(default_ratio, 3),
        "default_route_paths": [
            _path(page.get("final_url") or page.get("url") or page.get("path"))
            for page in default_routes[:12]
        ],
        "evidence_quality_blocking": blocking,
        "evidence_quality_gate_version": EVIDENCE_QUALITY_GATE_VERSION,
        "coverage_authority_version": coverage["coverage_authority_version"],
        "coverage_state": coverage["state"],
        "coverage_reasons": list(coverage["reasons"]),
    }


def _copy_quality_fields(target: dict[str, Any], quality: dict[str, Any]) -> dict[str, Any]:
    return {
        **target,
        **quality,
    }


def apply_evidence_quality_gate(result: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict):
        return result

    calibrated = deepcopy(result)
    quality = evaluate_evidence_quality(payload)
    calibrated.update(quality)

    existing_status = str(calibrated.get("scan_status") or "complete")
    existing_provisional = calibrated.get("score_is_provisional") is True
    existing_limited = existing_provisional or existing_status in LIMITED_SCAN_STATUSES
    should_block = quality["evidence_quality_blocking"] and not existing_limited

    if should_block:
        usable = quality["usable_html_page_count"]
        representative = quality["representative_html_page_count"]
        defaults = quality["default_route_page_count"]
        limitation = (
            f"FixList reviewed {usable} usable HTML pages, but only {representative} were representative business pages "
            f"and {defaults} were default, archive, or internal routes. Discovery was too narrow to support a full authoritative audit."
        )
        next_step = "Verify sitemap and internal navigation coverage"
        score = min(55, _int(calibrated.get("health_score") or calibrated.get("seo_score")))
        # This gate runs after calibration sealed the explanation. Clamping the
        # score without moving the explanation with it would put a breakdown on
        # the page that adds up to a different number than the score above it.
        explanation = apply_score_ceiling(
            calibrated.get("health_score_explanation"),
            score,
            "incomplete_evidence",
        )
        if explanation:
            calibrated["health_score_explanation"] = explanation
        calibrated.update({
            "scan_status": "inconclusive_insufficient_evidence",
            "review_confidence_state": "insufficient_discovery_quality",
            "score_is_provisional": True,
            "release_gate_eligible": False,
            "limitation": limitation,
            "next_best_step": next_step,
            "health_score": score,
            "seo_score": score,
            "health_grade": "Insufficient evidence",
        })
        summary = str(calibrated.get("customer_summary") or calibrated.get("plain_english_summary") or "").strip()
        if limitation not in summary:
            summary = f"{summary} {limitation}".strip()
        calibrated["customer_summary"] = summary
        calibrated["plain_english_summary"] = summary
    else:
        score = _int(calibrated.get("health_score") or calibrated.get("seo_score"))
        limitation = str(calibrated.get("limitation") or "")
        next_step = str(calibrated.get("next_best_step") or "")

    report = calibrated.get("website_health_report") if isinstance(calibrated.get("website_health_report"), dict) else {}
    report = _copy_quality_fields(report, quality)
    if should_block:
        report.update({
            "scan_status": calibrated["scan_status"],
            "review_confidence_state": calibrated["review_confidence_state"],
            "score_is_provisional": True,
            "health_score": score,
            "score": score,
            "health_grade": "Insufficient evidence",
            "limitations": [limitation],
            "next_best_step": next_step,
        })
    calibrated["website_health_report"] = report

    for key in ("scan_summary", "site_summary", "technical_audit_summary"):
        nested = calibrated.get(key) if isinstance(calibrated.get(key), dict) else {}
        nested = _copy_quality_fields(nested, quality)
        if should_block:
            nested.update({
                "scan_status": calibrated["scan_status"],
                "review_confidence_state": calibrated["review_confidence_state"],
                "score_is_provisional": True,
                "health_score": score,
                "score": score,
                "limitation": limitation,
                "next_best_step": next_step,
            })
        calibrated[key] = nested

    return calibrated
