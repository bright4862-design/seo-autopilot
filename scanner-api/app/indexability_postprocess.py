from __future__ import annotations

from .indexability_quality import (
    annotate_indexability_quality,
    build_indexability_quality_findings,
    summarize_indexability_quality,
)


QUALITY_RULES = {
    "soft_404",
    "robots_directive_conflict",
    "noindex_canonical_conflict",
    "sitemap_canonicalized_url",
}
SOFT_404_NOISE_RULES = {
    "missing_title",
    "missing_meta_description",
    "missing_h1",
    "multiple_h1",
    "image_alt_text",
    "canonical_missing",
    "schema",
}


def _page_path(page: dict) -> str:
    return str(page.get("path") or "/")


def apply_indexability_quality_to_result(result: dict) -> dict:
    """Apply bounded indexability-quality evidence to a successful scan response.

    This runs at the scanner API boundary after bounded trust-page enrichment. It
    preserves the scanner's existing evidence and only replaces prior quality
    findings, making the operation safe to run more than once.
    """
    if not isinstance(result, dict) or not result.get("success"):
        return result

    pages = list(result.get("crawled_pages") or result.get("pages") or [])
    if not pages:
        return result

    for page in pages:
        annotate_indexability_quality(page)

    # Import lazily so the quality module remains independent of scanner finding
    # construction and does not create an import cycle during app startup.
    from .scanner import calculate_health_score, create_finding, group_findings

    raw_findings = [
        dict(item)
        for item in (result.get("raw_findings") or [])
        if isinstance(item, dict) and str(item.get("rule") or "") not in QUALITY_RULES
    ]

    soft_404_paths = {
        _page_path(page)
        for page in pages
        if page.get("soft_404_suspected") and not page.get("trust_discovery_probe")
    }
    raw_findings = [
        item
        for item in raw_findings
        if not (
            str(item.get("page_url") or "") in soft_404_paths
            and str(item.get("rule") or "") in SOFT_404_NOISE_RULES
        )
    ]

    for page in pages:
        # Trust probes exist to prevent missing-trust false positives; they are not
        # part of the representative SEO sample and should not generate new tasks.
        if page.get("trust_discovery_probe"):
            continue
        raw_findings.extend(build_indexability_quality_findings(page, create_finding))

    grouped = group_findings(raw_findings)
    health_score = calculate_health_score(pages, grouped)
    evidence = summarize_indexability_quality(pages)

    result["pages"] = pages
    result["crawled_pages"] = pages
    result["raw_findings"] = raw_findings
    result["grouped_findings"] = grouped
    result["findings"] = grouped
    result["recommendations"] = grouped
    result["health_score"] = health_score
    result["indexability_quality_evidence"] = evidence

    summary = result.get("scan_summary")
    if not isinstance(summary, dict):
        summary = {}
        result["scan_summary"] = summary
    summary.update({
        "health_score": health_score,
        "score": health_score,
        "high_priority_count": sum(
            1 for item in grouped if item.get("priority") in {"critical", "high"}
        ),
        "technical_issue_count": len(grouped),
        "indexability_quality_evidence": evidence,
    })

    technical = result.get("technical_audit_summary")
    if not isinstance(technical, dict):
        technical = {}
        result["technical_audit_summary"] = technical
    technical.update({
        "indexability_quality_evidence": evidence,
        "soft_404_pages": evidence.get("soft_404_count", 0),
        "canonicalized_pages": evidence.get("canonicalized_count", 0),
        "indexability_conflicts": sum(evidence.get("conflict_counts", {}).values()),
    })

    return result
