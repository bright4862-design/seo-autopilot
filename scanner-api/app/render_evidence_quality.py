from __future__ import annotations

from typing import Any

from .page_output_privacy import project_scan_result_for_external_boundary


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
    attempted = crawled if crawled else found

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


def _project_private_page_evidence(result: dict[str, Any]) -> dict[str, Any]:
    """Project producer-only page evidence after all Stage-2 aggregation.

    ``apply_indexability_quality_to_result`` runs immediately before this pass on
    every successful scanner boundary and has already consumed B13/B14 raw page
    observations into the bounded scan-level aggregate. B10/B15 are currently
    evidence-only and have no authenticated customer contract. Keeping those
    intermediate page fields after this common post-crawl pass would leak them
    through the synchronous HTTP result and the durable signed scan envelope.

    The projection is deliberately fail-closed even when renderer evidence is
    absent or inconclusive. Scan-level aggregates and ordinary page evidence are
    preserved; only fields explicitly denied by ``page_output_privacy`` leave the
    producer/review-preparation phase.
    """
    return project_scan_result_for_external_boundary(result)


def apply_render_evidence_quality(result: dict[str, Any]) -> dict[str, Any]:
    """Prevent weak access coverage from being presented as negative renderer evidence.

    Material signals remain material even when coverage is limited. Only negative or
    isolated conclusions are replaced with an explicit insufficient-evidence state.
    This pass is idempotent and does not alter findings or health scoring.

    This is also the final common post-crawl pass before both synchronous output
    and durable authority handling, so producer-only Stage-2 page evidence is
    projected out here after scan-level aggregation has consumed it.
    """
    if not isinstance(result, dict):
        return result
    if not result.get("success"):
        return _project_private_page_evidence(result)

    evidence = result.get("render_evidence")
    if not isinstance(evidence, dict):
        return _project_private_page_evidence(result)

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

    return _project_private_page_evidence(result)
