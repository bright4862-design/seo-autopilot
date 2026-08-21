from __future__ import annotations

from typing import Any

from .repair_architecture_priority import architecture_context, architecture_priority_reason
from .repair_priority import ACTION_RANK, SEVERITY_RANK, annotate_repair_priority

REPAIR_PRIORITY_CALIBRATION_VERSION = "repair_priority_v2_technical_severity"

# Existing Python Review `priority` is a contextual field: its score includes
# evidence confidence, representative-page value, raw affected-page reach, and
# structural/trust boosts. It therefore cannot be reused as the technical/base
# severity for the new repair contract without reintroducing reach bias.
#
# These defaults are intentionally conservative and exist only in the shadow
# prioritization layer. Explicit `base_severity` / `technical_severity` always
# wins. Unknown rules fall back to their technical defect class, not legacy
# customer priority.
RULE_TECHNICAL_SEVERITY = {
    # Access / availability / structural correctness.
    "broken_page": "high",
    "server_error": "high",
    "blocked_page": "high",
    "rate_limited_page": "high",
    "failed_page": "high",
    "redirect_chain": "high",
    "redirect_destination_failed": "high",
    "redirect_destination_blocked": "high",
    "redirect_destination_noindex": "high",
    "route_boundary_candidate_indexable": "high",
    "internal_route_indexable": "high",
    "sitemap_indexability_conflict": "high",
    # Important but normally non-catastrophic configuration/content defects.
    "canonical_missing": "medium",
    "missing_canonical": "medium",
    "sitemap_redirect": "medium",
    "sitemap_canonicalized_url": "medium",
    "internal_link_redirect": "medium",
    "missing_meta_description": "medium",
    "empty_meta_description": "medium",
    "malformed_meta_description": "medium",
    "meta_description_unusable": "medium",
    "missing_h1": "medium",
    "multiple_h1": "medium",
    "schema": "medium",
    "structured_data": "medium",
    # Lower-inherent-impact optimization/investigative rules.
    "image_alt_text": "low",
    "missing_image_alt": "low",
    "title_over_pixel_limit": "low",
    "duplicate_title_template": "low",
    "duplicate_title_localized": "low",
    "duplicate_title_query_variants": "low",
    "duplicate_meta_description": "low",
    "potential_orphan_pages": "low",
    "potential_topic_overlap": "low",
}

# Evidence class expresses consequence/decision confidence, not whether the
# scanner literally observed the condition. A deterministic missing metadata
# field can still be an optimization rather than a blocking technical problem.
RULE_DEFAULT_EVIDENCE_CLASS = {
    "missing_meta_description": "improvement",
    "empty_meta_description": "improvement",
    "malformed_meta_description": "improvement",
    "meta_description_unusable": "improvement",
    "title_over_pixel_limit": "improvement",
    "duplicate_title_template": "improvement",
    "duplicate_title_localized": "improvement",
    "duplicate_title_query_variants": "improvement",
    "duplicate_meta_description": "improvement",
    "missing_h1": "improvement",
    "multiple_h1": "improvement",
    "schema": "improvement",
    "structured_data": "improvement",
    "image_alt_text": "improvement",
    "missing_image_alt": "improvement",
    "failed_page": "improvement",
    "potential_orphan_pages": "opportunity",
    "potential_topic_overlap": "opportunity",
}

DEFECT_CLASS_TECHNICAL_SEVERITY = {
    "blocked_access": "high",
    "crawl_index": "high",
    "structural": "high",
    "semantic_schema": "medium",
    "content_trust": "medium",
    "metadata": "medium",
    "general": "medium",
}

OPPORTUNITY_TOKENS = (
    "potential_",
    "opportunity",
    "topic_overlap",
    "keyword_overlap",
    "cannibal",
    "review_recommended",
)
NEEDS_VERIFICATION_STATES = {
    "needs_verification",
    "inconclusive",
    "provisional",
    "needs_review",
    "unverified",
}


def _clean(value: Any) -> str:
    return str(value or "").strip().lower()


def _canonical_priority_pages(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize existing page evidence for shadow priority only.

    Scanner evidence is not changed. The shadow layer merely makes the three
    historical robots fields (`robots`, `robots_meta`, `meta_robots`) resolve to
    the same non-indexable state already used by repair verification. An explicit
    scanner-owned boolean `indexable` always wins.
    """
    normalized: list[dict[str, Any]] = []
    for page in pages or []:
        if not isinstance(page, dict):
            continue
        copied = dict(page)
        if copied.get("indexable") is not True and copied.get("indexable") is not False:
            robots = " ".join(
                _clean(copied.get(key))
                for key in ("robots", "robots_meta", "meta_robots")
                if copied.get(key) is not None
            )
            if "noindex" in robots:
                copied["indexable"] = False
        normalized.append(copied)
    return normalized


def technical_base_severity(fix: dict[str, Any]) -> tuple[str, str]:
    explicit = _clean(fix.get("base_severity") or fix.get("technical_severity"))
    if explicit in SEVERITY_RANK:
        return explicit, "explicit"

    rule = _clean(fix.get("rule") or fix.get("type"))
    if rule in RULE_TECHNICAL_SEVERITY:
        return RULE_TECHNICAL_SEVERITY[rule], "rule_taxonomy"

    defect_class = _clean(fix.get("primary_defect_class") or fix.get("defect_class"))
    if defect_class in DEFECT_CLASS_TECHNICAL_SEVERITY:
        return DEFECT_CLASS_TECHNICAL_SEVERITY[defect_class], "defect_class"

    # Fail conservatively. Do not infer technical severity from the legacy
    # `priority`, because legacy priority is partly a reach/business score.
    return "medium", "conservative_default"


def calibrated_evidence_class(fix: dict[str, Any]) -> str:
    explicit = _clean(fix.get("evidence_class") or fix.get("repair_evidence_class"))
    if explicit in {"confirmed_problem", "improvement", "opportunity"}:
        return explicit

    rule = _clean(fix.get("rule") or fix.get("type"))
    if rule in RULE_DEFAULT_EVIDENCE_CLASS:
        default_class = RULE_DEFAULT_EVIDENCE_CLASS[rule]
        if default_class == "opportunity":
            return "opportunity"
    else:
        default_class = "confirmed_problem"

    text = " ".join(
        _clean(fix.get(key))
        for key in (
            "rule",
            "type",
            "issue_title",
            "title",
            "source",
            "verification_state",
            "evidence_status",
        )
    )
    if any(token in text for token in OPPORTUNITY_TOKENS):
        return "opportunity"

    verification = _clean(fix.get("verification_state"))
    evidence_status = _clean(fix.get("evidence_status"))
    if verification in NEEDS_VERIFICATION_STATES or evidence_status in NEEDS_VERIFICATION_STATES:
        return "improvement"
    return default_class


def _action_priority(base_severity: str, evidence_class: str, context: dict[str, Any], *, search_facing: bool) -> str:
    if evidence_class == "opportunity":
        return "review"
    if evidence_class == "improvement":
        return "important" if base_severity in {"critical", "high"} else "improve"

    if base_severity in {"critical", "high"}:
        band = "fix_first"
    elif base_severity == "medium":
        band = "important"
    else:
        band = "improve"

    indexable = int(context.get("indexable_affected") or 0)
    non_indexable = int(context.get("non_indexable_affected") or 0)
    known = indexable + non_indexable
    if search_facing and known >= 3 and non_indexable / known >= 0.80:
        if band == "fix_first" and base_severity != "critical":
            band = "important"
        elif band == "important":
            band = "improve"
    return band


def _score(
    base_severity: str,
    action_priority: str,
    context: dict[str, Any],
    fix: dict[str, Any],
    *,
    role_bonus: int,
) -> int:
    score = ACTION_RANK[action_priority] * 1000 + SEVERITY_RANK[base_severity] * 100
    searchable = context.get("searchable_coverage")
    checked = context.get("checked_coverage")
    search_facing = bool(context.get("search_facing"))
    coverage = searchable if search_facing and searchable is not None else checked
    if coverage is not None:
        try:
            score += round(min(1.0, max(0.0, float(coverage))) * 40)
        except (TypeError, ValueError):
            pass

    # Architecture replaces the old linear "important page" bonus. Structural
    # and business-critical surfaces receive strong bounded credit, while the
    # marginal value of repeated product/activity leaves saturates quickly.
    score += max(0, int(role_bonus or 0))

    confidence = fix.get("evidence_confidence")
    if confidence is None:
        confidence = fix.get("confidence_score")
    try:
        score += round(max(0.0, min(100.0, float(confidence or 0))) / 10)
    except (TypeError, ValueError):
        pass
    if context.get("shared_repair_confirmed") is True and int(context.get("affected_checked") or 0) >= 2:
        score += 15
    return score


def annotate_calibrated_repair_priority(fix: dict[str, Any], pages: list[dict[str, Any]]) -> dict[str, Any]:
    """Recalibrate one repair without changing its underlying finding.

    Legacy `priority`, crawl evidence, and normal review output remain intact.
    The post-review repair-contract wrapper may use this annotation to build a
    separate canonical snapshot after the ordinary review has finished.
    """
    normalized_pages = _canonical_priority_pages(pages or [])
    annotated = annotate_repair_priority(dict(fix), normalized_pages)
    base_severity, severity_source = technical_base_severity(fix)
    evidence_class = calibrated_evidence_class(fix)
    context = dict(annotated.get("priority_context") or {})
    search_facing = bool(context.get("search_facing"))
    action_priority = _action_priority(base_severity, evidence_class, context, search_facing=search_facing)

    architecture = architecture_context(
        fix,
        normalized_pages,
        checked_eligible=context.get("checked_eligible"),
    )
    score = _score(
        base_severity,
        action_priority,
        context,
        fix,
        role_bonus=int(architecture.get("role_bonus") or 0),
    )

    context.update({
        "version": REPAIR_PRIORITY_CALIBRATION_VERSION,
        "legacy_priority": _clean(fix.get("priority")),
        "base_severity": base_severity,
        "technical_severity_source": severity_source,
        "evidence_class": evidence_class,
        "action_priority": action_priority,
        "action_priority_score": score,
        "architecture_priority_version": architecture.get("version"),
        "architecture_role_counts": architecture.get("role_counts"),
        "architecture_role_bonus": architecture.get("role_bonus"),
        "repair_reach": architecture.get("repair_reach"),
    })

    priority_reason = architecture_priority_reason(
        fix,
        normalized_pages,
        checked_eligible=context.get("checked_eligible"),
        fallback_reason=str(annotated.get("priority_reason") or ""),
    )

    return {
        **annotated,
        "base_severity": base_severity,
        "technical_severity_source": severity_source,
        "evidence_class": evidence_class,
        "action_priority": action_priority,
        "action_priority_score": score,
        "priority_reason": priority_reason,
        "priority_context": context,
        "repair_priority_version": REPAIR_PRIORITY_CALIBRATION_VERSION,
    }
