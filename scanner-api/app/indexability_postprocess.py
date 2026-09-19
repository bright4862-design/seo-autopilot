from __future__ import annotations

import hashlib
from .search_applicability import filter_search_findings, search_applicability
from .metadata_title_evidence import relative_evidence_url
from .repair_coverage import repair_evidence_key_function, scan_evidence_origin
from .coverage_probes import SOFT_404_PROBE_VERSION, compare_page_to_soft_404_baselines

from .indexability_quality import (
    annotate_indexability_quality,
    build_indexability_quality_findings,
    summarize_indexability_quality,
)
from .navigation_indexability import (
    annotate_navigation_indexability,
    build_navigation_indexability_findings,
    summarize_navigation_indexability,
)


QUALITY_RULES = {
    "soft_404",
    "robots_directive_conflict",
    "noindex_canonical_conflict",
    "sitemap_canonicalized_url",
    "potential_orphan_pages",
    "indexable_faceted_navigation",
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


def _active_soft_404_baselines(result: dict) -> list[dict]:
    """Return only current, explicitly-labelled active soft-404 baselines.

    The scanner producer owns network access and provenance. This postprocess
    boundary consumes only the bounded baseline records it was given; absent,
    stale or unknown evidence must not be reconstructed from the current web.
    """
    coverage = result.get("coverage_probe_evidence")
    if not isinstance(coverage, dict):
        return []
    baselines = coverage.get("soft_404_baselines")
    if not isinstance(baselines, list):
        return []
    return [
        dict(item)
        for item in baselines
        if isinstance(item, dict) and item.get("version") == SOFT_404_PROBE_VERSION
    ]


def _apply_active_soft_404_match(page: dict, baselines: list[dict]) -> dict:
    """Promote a verified active-baseline match without erasing passive evidence."""
    evidence = compare_page_to_soft_404_baselines(page, baselines)
    if evidence.get("state") != "fail" or evidence.get("reason") != "active_soft_404_baseline_match":
        return evidence

    signals = _unique([
        "active_baseline_match",
        *(evidence.get("intent_signals") or []),
        *(page.get("soft_404_signals") or []),
    ])
    page["soft_404_suspected"] = True
    page["soft_404_signals"] = signals
    page["soft_404_confidence"] = max(98, int(page.get("soft_404_confidence") or 0))
    if str(page.get("indexability_state") or "") in {"Indexable", "Canonicalized", "Soft 404"}:
        page["indexable"] = False
        page["indexability_state"] = "Soft 404"
        page["robots_indexability_status"] = "soft_404"
    return evidence


def group_indexability_quality_findings(findings: list[dict]) -> list[dict]:
    groups: dict[tuple[str, str, str], list[dict]] = {}
    for finding in findings:
        rule = str(finding.get("rule") or "")
        family = str(finding.get("page_template_family") or "standard")
        # Active-baseline findings are authenticated under a different evidence
        # revision than legacy/passive soft-404 heuristics. Never collapse the
        # two into one repair card and then imply the active proof covered URLs
        # that were only heuristically classified.
        evidence_version = str(finding.get("observed_evidence_version") or "")
        groups.setdefault((rule, family, evidence_version), []).append(finding)

    output: list[dict] = []
    severity = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    for (rule, family, evidence_version), members in groups.items():
        affected = _unique(
            page
            for member in members
            for page in (member.get("affected_pages") or [member.get("page_url")])
        )[:150]
        if len(affected) < GROUP_MIN_AFFECTED:
            output.extend(members)
            continue

        sample = dict(members[0])
        group_key = f"indexability-quality|{rule}|{family}|{evidence_version}"
        group_id = "finding_" + hashlib.sha1(group_key.encode("utf-8")).hexdigest()[:12]
        highest_priority = max(
            (str(member.get("priority") or "low") for member in members),
            key=lambda value: severity.get(value, 0),
        )
        title = QUALITY_GROUP_TITLES.get(rule, str(sample.get("title") or "Fix repeated indexability issue"))
        verified_observed_pages = _unique(
            page
            for member in members
            for page in (
                member.get("verified_observed_pages")
                if isinstance(member.get("verified_observed_pages"), list)
                else []
            )
        )
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
        if evidence_version and verified_observed_pages:
            sample["observed_evidence_version"] = evidence_version
            sample["verified_observed_pages"] = verified_observed_pages
        output.append(sample)
    return output


def apply_indexability_quality_to_result(result: dict, *, identity_version: str = "") -> dict:
    """Apply bounded indexability and navigation evidence to a scan response.

    This runs at the scanner API boundary after bounded trust-page enrichment. It
    preserves the scanner's existing evidence and only replaces its own idempotent
    quality rules, making the operation safe to run more than once.
    """
    if not isinstance(result, dict) or not result.get("success"):
        return result

    pages = list(result.get("crawled_pages") or result.get("pages") or [])
    if not pages:
        return result
    identity = {"scan_origin": scan_evidence_origin(result) if identity_version else "", "identity_version": identity_version}
    key_for = repair_evidence_key_function(legacy_key=str, **identity)
    active_baselines = _active_soft_404_baselines(result)
    active_soft_404_evidence: dict[int, dict] = {}

    for page in pages:
        annotate_indexability_quality(page)
        active_soft_404_evidence[id(page)] = _apply_active_soft_404_match(page, active_baselines)
        annotate_navigation_indexability(page)
        page["search_applicability"] = search_applicability(page)

    # Import lazily so the quality modules remain independent of scanner finding
    # construction and do not create an import cycle during app startup.
    from .scanner import calculate_health_score, create_finding, group_findings

    existing_raw = [
        dict(item)
        for item in (result.get("raw_findings") or [])
        if isinstance(item, dict) and str(item.get("rule") or "") not in QUALITY_RULES
    ]

    soft_404_paths = {
        (relative_evidence_url(page, **identity) if identity_version else _page_path(page))
        for page in pages
        if page.get("soft_404_suspected") and not page.get("trust_discovery_probe")
    }
    existing_raw = [
        item
        for item in existing_raw
        if not (
            key_for(item.get("page_url") or "") in soft_404_paths
            and str(item.get("rule") or "") in SOFT_404_NOISE_RULES
        )
    ]

    existing_raw = filter_search_findings(existing_raw, pages)

    quality_raw: list[dict] = []
    for page in pages:
        # Trust probes exist to prevent missing-trust false positives; they are not
        # part of the representative SEO sample and should not generate new tasks.
        if page.get("trust_discovery_probe"):
            continue
        page_quality = build_indexability_quality_findings(page, create_finding, **identity)
        active = active_soft_404_evidence.get(id(page)) or {}
        if active.get("state") == "fail" and active.get("reason") == "active_soft_404_baseline_match":
            observed_url = (
                relative_evidence_url(page, **identity)
                if identity_version
                else str(page.get("url") or page.get("final_url") or _page_path(page))
            )
            for finding in page_quality:
                if str(finding.get("rule") or "") != "soft_404":
                    continue
                finding.update({
                    "evidence_status": "confirmed_active_baseline",
                    "verification_state": "verified",
                    "confidence_score": 98,
                    "observed_evidence_version": SOFT_404_PROBE_VERSION,
                    "verified_observed_pages": [observed_url],
                })
        quality_raw.extend(page_quality)

    navigation_raw = build_navigation_indexability_findings(pages, create_finding, **identity)
    raw_findings = existing_raw + quality_raw + navigation_raw
    grouped = (
        group_findings(existing_raw)
        + group_indexability_quality_findings(quality_raw)
        + navigation_raw
    )
    health_score = calculate_health_score(pages, grouped)
    indexability_evidence = summarize_indexability_quality(pages, **identity)
    navigation_evidence = summarize_navigation_indexability(pages, **identity)

    result["pages"] = pages
    result["crawled_pages"] = pages
    result["raw_findings"] = raw_findings
    result["grouped_findings"] = grouped
    result["findings"] = grouped
    result["recommendations"] = grouped
    result["health_score"] = health_score
    result["indexability_quality_evidence"] = indexability_evidence
    result["navigation_indexability_evidence"] = navigation_evidence

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
        "indexability_quality_evidence": indexability_evidence,
        "navigation_indexability_evidence": navigation_evidence,
    })

    technical = result.get("technical_audit_summary")
    if not isinstance(technical, dict):
        technical = {}
        result["technical_audit_summary"] = technical
    technical.update({
        "indexability_quality_evidence": indexability_evidence,
        "navigation_indexability_evidence": navigation_evidence,
        "soft_404_pages": indexability_evidence.get("soft_404_count", 0),
        "canonicalized_pages": indexability_evidence.get("canonicalized_count", 0),
        "indexability_conflicts": sum(indexability_evidence.get("conflict_counts", {}).values()),
        "potential_orphan_candidates": navigation_evidence.get("potential_orphan_candidates", 0),
        "pagination_pages": navigation_evidence.get("pagination_pages", 0),
        "faceted_navigation_pages": navigation_evidence.get("faceted_navigation_pages", 0),
    })

    return result
