from __future__ import annotations

import hashlib

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
QUALITY_GROUP_TITLES = {
    "soft_404": "Return real 404 or 410 responses for missing pages",
    "robots_directive_conflict": "Resolve conflicting index and noindex directives",
    "noindex_canonical_conflict": "Choose between noindex and canonical consolidation",
    "sitemap_canonicalized_url": "Replace canonicalized URLs in the sitemap",
}
GROUP_MIN_AFFECTED = 3


def _page_path(page: dict) -> str:
    return str(page.get("path") or "/")


def _unique(values) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        cleaned = str(value or "").strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            output.append(cleaned)
    return output


def group_indexability_quality_findings(findings: list[dict]) -> list[dict]:
    groups: dict[tuple[str, str], list[dict]] = {}
    for finding in findings:
        rule = str(finding.get("rule") or "")
        family = str(finding.get("page_template_family") or "standard")
        groups.setdefault((rule, family), []).append(finding)

    output: list[dict] = []
    severity = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    for (rule, family), members in groups.items():
        affected = _unique(
            page
            for member in members
            for page in (member.get("affected_pages") or [member.get("page_url")])
        )[:150]
        if len(affected) < GROUP_MIN_AFFECTED:
            output.extend(members)
            continue

        sample = dict(members[0])
        group_key = f"indexability-quality|{rule}|{family}"
        group_id = "finding_" + hashlib.sha1(group_key.encode("utf-8")).hexdigest()[:12]
        highest_priority = max(
            (str(member.get("priority") or "low") for member in members),
            key=lambda value: severity.get(value, 0),
        )
        title = QUALITY_GROUP_TITLES.get(rule, str(sample.get("title") or "Fix repeated indexability issue"))
        sample.update({
            "id": group_id,
            "fix_id": group_id,
            "page_url": "",
            "title": title,
            "issue_title": title,
            "plain_english_explanation": (
                "Several similar pages share the same indexability problem. Fix the shared template, routing rule, or response behavior instead of treating each URL separately."
            ),
            "plain_english_summary": (
                "Several similar pages share the same indexability problem. Fix the shared template, routing rule, or response behavior instead of treating each URL separately."
            ),
            "why_it_matters": (
                "Repeated indexability defects can waste crawl activity and create inconsistent search-engine signals across a whole page family."
            ),
            "recommended_value": (
                "Fix one representative template or routing rule, verify the result, then apply it across every affected URL."
            ),
            "recommendation": (
                "Fix one representative template or routing rule, verify the result, then apply it across every affected URL."
            ),
            "ai_recommendation": (
                "Fix one representative template or routing rule, verify the result, then apply it across every affected URL."
            ),
            "priority": highest_priority,
            "affected_pages": affected,
            "page_count": len(affected),
            "source_pages": _unique(
                page for member in members for page in (member.get("source_pages") or [])
            ),
            "link_text_samples": _unique(
                text for member in members for text in (member.get("link_text_samples") or [])
            ),
        })
        output.append(sample)
    return output


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

    existing_raw = [
        dict(item)
        for item in (result.get("raw_findings") or [])
        if isinstance(item, dict) and str(item.get("rule") or "") not in QUALITY_RULES
    ]

    soft_404_paths = {
        _page_path(page)
        for page in pages
        if page.get("soft_404_suspected") and not page.get("trust_discovery_probe")
    }
    existing_raw = [
        item
        for item in existing_raw
        if not (
            str(item.get("page_url") or "") in soft_404_paths
            and str(item.get("rule") or "") in SOFT_404_NOISE_RULES
        )
    ]

    quality_raw: list[dict] = []
    for page in pages:
        # Trust probes exist to prevent missing-trust false positives; they are not
        # part of the representative SEO sample and should not generate new tasks.
        if page.get("trust_discovery_probe"):
            continue
        quality_raw.extend(build_indexability_quality_findings(page, create_finding))

    raw_findings = existing_raw + quality_raw
    grouped = group_findings(existing_raw) + group_indexability_quality_findings(quality_raw)
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
