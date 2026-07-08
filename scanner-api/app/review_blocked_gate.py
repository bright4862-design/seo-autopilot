from __future__ import annotations

from typing import Any, Callable


def install(review_module: Any) -> None:
    """Install a lightweight blocked-crawl gate around app.review.run_review.

    The gate is intentionally applied at package import time so both the FastAPI
    /review route and tests that do `from app.review import run_review` see the
    same canonical behavior.
    """
    if getattr(review_module, "_blocked_crawl_gate_installed", False):
        return

    original_run_review = review_module.run_review

    def run_review_with_blocked_gate(payload: dict[str, Any]) -> dict[str, Any]:
        result = original_run_review(payload)
        body = review_module.unwrap_scan_payload(payload)
        pages = review_module.first_array(
            body.get("crawled_pages"),
            body.get("pages"),
            body.get("scanned_pages"),
            body.get("crawl_pages"),
            review_module.deep_get(body, "technical_audit_summary", "pages"),
        )
        blocked_or_429_pages = max(
            sum(1 for page in pages if review_module.is_blocked_access_page(page)),
            _first_number(
                review_module.deep_get(body, "scan_coverage", "rate_limited_pages"),
                review_module.deep_get(body, "scan_coverage", "blocked_pages"),
                review_module.deep_get(body, "technical_audit_summary", "blocked_pages"),
                0,
            ),
        )

        site_fingerprint = result.get("site_fingerprint") if isinstance(result.get("site_fingerprint"), dict) else {}
        site_fingerprint["blocked_or_429_pages"] = blocked_or_429_pages
        result["site_fingerprint"] = site_fingerprint

        quality = result.get("review_input_quality") if isinstance(result.get("review_input_quality"), dict) else {}
        quality["blocked_or_429_pages"] = blocked_or_429_pages
        result["review_input_quality"] = quality
        if isinstance(site_fingerprint.get("review_input_quality"), dict):
            site_fingerprint["review_input_quality"]["blocked_or_429_pages"] = blocked_or_429_pages

        blocked = crawl_is_blocked_from_result(result, blocked_or_429_pages)
        incomplete = not bool(result.get("evidence_complete", True))
        if blocked:
            _mark_blocked(result)
        else:
            result["scan_status"] = "incomplete_evidence" if incomplete else "complete"

        return result

    run_review_with_blocked_gate.__name__ = original_run_review.__name__
    run_review_with_blocked_gate.__doc__ = original_run_review.__doc__
    review_module._run_review_before_blocked_crawl_gate = original_run_review
    review_module.run_review = run_review_with_blocked_gate
    review_module.crawl_is_blocked = crawl_is_blocked_from_result
    review_module._blocked_crawl_gate_installed = True


def crawl_is_blocked_from_result(result: dict[str, Any], blocked_or_429_pages: int | None = None) -> bool:
    site_fingerprint = result.get("site_fingerprint") if isinstance(result.get("site_fingerprint"), dict) else {}
    crawled = _int_or_zero(site_fingerprint.get("pages_crawled"))
    received = _int_or_zero(site_fingerprint.get("pages_received"))
    blocked = max(
        _int_or_zero(site_fingerprint.get("blocked_access_pages")),
        _int_or_zero(blocked_or_429_pages if blocked_or_429_pages is not None else site_fingerprint.get("blocked_or_429_pages")),
    )
    if blocked == 0:
        return False
    if crawled <= 1:
        return True
    usable = max(received, crawled)
    return usable > 0 and (blocked / usable) >= 0.5


def _mark_blocked(result: dict[str, Any]) -> None:
    capped = min(_int_or_zero(result.get("health_score")) or 45, 45)
    result["health_score"] = capped
    result["seo_score"] = min(_int_or_zero(result.get("seo_score")) or capped, capped)
    result["scan_status"] = "blocked_or_incomplete"

    report = result.get("website_health_report")
    if not isinstance(report, dict):
        report = {}
        result["website_health_report"] = report
    report["health_score"] = min(_int_or_zero(report.get("health_score")) or capped, capped)
    report["score"] = report["health_score"]
    report["health_grade"] = "Blocked / incomplete"

    summary = result.get("plain_english_summary") or result.get("customer_summary") or "FixList could not complete a reliable crawl because crawler access was blocked or rate-limited."
    report.setdefault("overall_explanation", summary)
    report["next_best_step"] = "Ask your web person to verify crawler access, rate limits, CDN, firewall, and bot-protection settings."

    scan_summary = result.get("scan_summary")
    if isinstance(scan_summary, dict):
        scan_summary["health_score"] = capped
        scan_summary["score"] = capped
        scan_summary["scan_status"] = "blocked_or_incomplete"


def _first_number(*values: Any) -> int:
    for value in values:
        number = _int_or_zero(value)
        if number >= 0:
            return number
    return 0


def _int_or_zero(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
