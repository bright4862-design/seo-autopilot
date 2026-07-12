from __future__ import annotations

from typing import Any


RENDER_EVIDENCE_QUALITY_VERSION = "render_evidence_quality_v1"
INSUFFICIENT_RENDER_EVIDENCE_STATE = "insufficient_raw_html_evidence"
MIN_EVALUATED_PAGES_FOR_LARGE_CRAWL = 3
MIN_EVALUATED_RATIO_FOR_LARGE_CRAWL = 0.10
LARGE_CRAWL_PAGE_THRESHOLD = 10
RATIO_CHECK_PAGE_THRESHOLD = 20


def _nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def assess_render_evidence_coverage(
    evidence: dict[str, Any] | None,
    *,
    pages_crawled: int = 0,
    pages_found: int = 0,
) -> dict[str, Any]:
    evidence = evidence if isinstance(evidence, dict) else {}
    evaluated = _nonnegative_int(evidence.get("pages_evaluated"))
    crawled = _nonnegative_int(pages_crawled)
    found = _nonnegative_int(pages_found)
    attempted = max(crawled, min(found, crawled) if crawled else 0)
    if attempted <= 0:
        attempted = max(crawled, found)

    ratio = round(evaluated / attempted, 4) if attempted else 0.0
    reason = ""
    if evaluated == 0:
        reason = "no_evaluable_html_pages"
    elif attempted >= LARGE_CRAWL_PAGE_THRESHOLD and evaluated < MIN_EVALUATED_PAGES_FOR_LARGE_CRAWL:
        reason = "too_few_evaluable_html_pages"
    elif attempted >= RATIO_CHECK_PAGE_THRESHOLD and ratio < MIN_EVALUATED_RATIO_FOR_LARGE_CRAWL:
        reason = "evaluable_html_coverage_below_10_percent"

    return {
        "version": RENDER_EVIDENCE_QUALITY_VERSION,
        "sufficient": not bool(reason),
        "state": "sufficient" if not reason else "insufficient",
        "reason": reason,
        "pages_evaluated": evaluated,
        "pages_attempted": attempted,
        "evaluated_ratio": ratio,
        "minimum_pages_for_large_crawl": MIN_EVALUATED_PAGES_FOR_LARGE_CRAWL,
        "minimum_ratio_for_large_crawl": MIN_EVALUATED_RATIO_FOR_LARGE_CRAWL,
    }


def apply_render_evidence_quality(result: dict[str, Any]) -> dict[str, Any]:
    """Prevent weak access coverage from being presented as negative renderer evidence.

    Material signals remain material even when coverage is limited. Only negative or
    isolated conclusions are replaced with an explicit insufficient-evidence state.
    This pass is idempotent and does not alter findings or health scoring.
    """
    if not isinstance(result, dict) or not result.get("success"):
        return result

    evidence = result.get("render_evidence")
    if not isinstance(evidence, dict):
        return result

    coverage = assess_render_evidence_coverage(
        evidence,
        pages_crawled=_nonnegative_int(result.get("pages_crawled")),
        pages_found=_nonnegative_int(result.get("pages_found")),
    )
    prior_state = str(
        evidence.get("pre_coverage_evidence_state")
        or evidence.get("evidence_state")
        or ""
    )

    evidence["coverage"] = coverage
    evidence["coverage_version"] = RENDER_EVIDENCE_QUALITY_VERSION
    if not coverage["sufficient"] and prior_state != "material_client_rendering_risk":
        evidence["pre_coverage_evidence_state"] = prior_state
        evidence["evidence_state"] = INSUFFICIENT_RENDER_EVIDENCE_STATE
        evidence["rendering_mode"] = "raw_html_evidence_insufficient"

        warning = (
            "Renderer-risk evidence is inconclusive because too few successful HTML pages "
            "were available for evaluation. Do not treat this scan as proof that raw HTML is sufficient."
        )
        warnings = list(result.get("crawl_warnings") or [])
        if warning not in warnings:
            warnings.append(warning)
        result["crawl_warnings"] = warnings

    result["render_evidence"] = evidence
    result["render_evidence_quality"] = coverage

    summary = result.get("scan_summary")
    if isinstance(summary, dict):
        summary["render_evidence"] = evidence
        summary["render_evidence_quality"] = coverage

    technical = result.get("technical_audit_summary")
    if isinstance(technical, dict):
        technical["render_evidence"] = evidence
        technical["render_evidence_quality"] = coverage

    return result
