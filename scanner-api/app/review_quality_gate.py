from __future__ import annotations

from typing import Any

from .review import REVIEW_VERSION, deep_get, first_array, int_or_zero, unwrap_scan_payload

QUALITY_GATE_VERSION = "review_quality_gate_v1_evidence_complete"
INCOMPLETE_REVIEW_WARNING = "Review received scan metadata, but no page evidence was passed into AI Review."
INCOMPLETE_REVIEW_FIX_ID = "review_input_quality_missing_pages"


def run_review_with_quality_gate(payload: dict[str, Any]) -> dict[str, Any]:
    """Run Python review and enforce evidence-quality gates on the result.

    This intentionally preserves REVIEW_VERSION because the Base44 wrapper currently
    requires python_review_v1_archetype_templates. The gate adds explicit debug
    fields and prevents metadata-only reviews from looking like strong completed
    audits.
    """
    from .review import run_review

    result = run_review(payload)
    return apply_review_quality_gate(payload, result)


def apply_review_quality_gate(payload: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    body = unwrap_scan_payload(payload)
    pages = first_array(
        body.get("crawled_pages"),
        body.get("pages"),
        body.get("scanned_pages"),
        body.get("crawl_pages"),
        deep_get(body, "technical_audit_summary", "pages"),
    )
    pages_received = len(pages or [])
    grouped_findings_received = len(body.get("grouped_findings") or []) if isinstance(body.get("grouped_findings"), list) else 0
    verified_failed_pages_received = _count_all_lists(
        body.get("verified_failed_pages"),
        deep_get(body, "technical_audit_summary", "verified_failed_pages"),
        deep_get(body, "url_evidence_summary", "verified_failed_pages"),
    )
    suspicious_artifacts_received = _count_all_lists(
        body.get("suspicious_url_artifacts"),
        deep_get(body, "technical_audit_summary", "suspicious_url_artifacts"),
        deep_get(body, "url_evidence_summary", "suspicious_url_artifacts"),
    )
    pages_crawled_reported = _first_positive_int(
        deep_get(body, "scan_coverage", "pages_crawled"),
        body.get("pages_crawled"),
        deep_get(body, "technical_audit_summary", "pages_crawled"),
        deep_get(result, "site_fingerprint", "pages_crawled"),
        deep_get(result, "scan_summary", "pages_scanned"),
    )
    sampled_pages_sent = _first_non_negative_int(
        deep_get(body, "scan_coverage", "sampled_pages_sent_to_ai"),
        deep_get(result, "site_fingerprint", "sampled_pages_sent_to_ai"),
        pages_received,
    )

    evidence_complete = pages_received > 0
    metadata_without_pages = pages_crawled_reported > 0 and pages_received == 0 and sampled_pages_sent == 0
    quality = {
        "version": QUALITY_GATE_VERSION,
        "pages_received": pages_received,
        "pages_crawled_reported": pages_crawled_reported,
        "sampled_pages_sent_to_ai": sampled_pages_sent,
        "grouped_findings_received": grouped_findings_received,
        "verified_failed_pages_received": verified_failed_pages_received,
        "suspicious_artifacts_received": suspicious_artifacts_received,
        "has_technical_summary": bool(body.get("technical_audit_summary")),
        "evidence_complete": evidence_complete,
        "metadata_without_pages": metadata_without_pages,
    }

    result["review_input_quality"] = quality
    result["review_quality_gate_version"] = QUALITY_GATE_VERSION

    if isinstance(result.get("site_fingerprint"), dict):
        result["site_fingerprint"]["review_input_quality"] = quality
    if isinstance(result.get("scan_summary"), dict):
        result["scan_summary"]["review_input_quality"] = quality

    if metadata_without_pages:
        _mark_incomplete_review(result)

    return result


def _mark_incomplete_review(result: dict[str, Any]) -> None:
    result["ai_review_warning"] = INCOMPLETE_REVIEW_WARNING
    result["review_evidence_complete"] = False
    result["health_score"] = min(int_or_zero(result.get("health_score")) or 70, 70)
    result["seo_score"] = min(int_or_zero(result.get("seo_score")) or 70, 70)

    report = result.get("website_health_report")
    if not isinstance(report, dict):
        report = {}
        result["website_health_report"] = report
    capped_score = min(int_or_zero(report.get("health_score") or result.get("health_score")) or 70, 70)
    report["health_score"] = capped_score
    report["score"] = capped_score
    report["health_grade"] = "Scan incomplete"
    report["overall_explanation"] = INCOMPLETE_REVIEW_WARNING
    report["next_best_step"] = "Pass the full page evidence from runAdvancedScan into aiReviewScan."
    report["top_concerns"] = _prepend_unique(report.get("top_concerns"), "Scan evidence was not passed into AI Review")
    report["bigger_projects"] = _prepend_unique(report.get("bigger_projects"), "Fix the scan-to-review evidence handoff")

    debug_fix = _make_missing_evidence_fix()
    for key in [
        "cleaned_fixes",
        "recommended_actions",
        "raw_fixes",
        "fixes",
        "findings",
        "recommendations",
    ]:
        result[key] = _prepend_fix(result.get(key), debug_fix)
    result["top_recommended_actions"] = _prepend_fix(result.get("top_recommended_actions"), debug_fix)[:5]

    summary = INCOMPLETE_REVIEW_WARNING
    result["plain_english_summary"] = summary
    result["health_explanation"] = summary
    result["customer_summary"] = summary
    result["simple_summary"] = summary

    if isinstance(result.get("scan_summary"), dict):
        result["scan_summary"]["health_score"] = capped_score
        result["scan_summary"]["score"] = capped_score
        result["scan_summary"]["plain_english_summary"] = summary


def _make_missing_evidence_fix() -> dict[str, Any]:
    return {
        "id": INCOMPLETE_REVIEW_FIX_ID,
        "fix_id": INCOMPLETE_REVIEW_FIX_ID,
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


def _prepend_fix(value: Any, fix: dict[str, Any]) -> list[dict[str, Any]]:
    items = value if isinstance(value, list) else []
    return [fix] + [item for item in items if not isinstance(item, dict) or item.get("fix_id") != INCOMPLETE_REVIEW_FIX_ID]


def _prepend_unique(value: Any, item: str) -> list[str]:
    items = value if isinstance(value, list) else []
    return [item] + [str(existing) for existing in items if str(existing) != item]


def _count_all_lists(*values: Any) -> int:
    return sum(len(value) for value in values if isinstance(value, list))


def _first_positive_int(*values: Any) -> int:
    for value in values:
        number = int_or_zero(value)
        if number > 0:
            return number
    return 0


def _first_non_negative_int(*values: Any) -> int:
    for value in values:
        if value is None:
            continue
        number = int_or_zero(value)
        if number >= 0:
            return number
    return 0
