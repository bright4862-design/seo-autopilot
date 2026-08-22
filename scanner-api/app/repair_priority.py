from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

REPAIR_PRIORITY_VERSION = "repair_priority_v1_contextual_evidence"

SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}
ACTION_RANK = {"fix_first": 4, "important": 3, "improve": 2, "review": 1}

SEARCH_FACING_CATEGORIES = {
    "canonical",
    "indexability",
    "meta_title",
    "meta_description",
    "duplicate_content",
    "schema",
    "thin_content",
    "image_alt_text",
    "alt_text",
    "social_metadata",
}

SEARCH_FACING_RULE_TOKENS = (
    "canonical",
    "noindex",
    "indexab",
    "title",
    "meta_description",
    "description",
    "h1",
    "heading",
    "duplicate_content",
    "schema",
    "structured_data",
    "thin_content",
    "image_alt",
)

IMPORTANT_TEMPLATE_FAMILIES = {
    "homepage",
    "loan_program",
    "conversion",
    "calculator",
    "comparison_page",
    "product_page",
    "collection_page",
    "activity_detail",
    "location_landing",
    "booking_or_checkout",
}

OPPORTUNITY_TOKENS = (
    "potential_",
    "opportunity",
    "topic_overlap",
    "keyword_overlap",
    "cannibal",
    "review_recommended",
)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _lower(value: Any) -> str:
    return _clean(value).lower()


def _path(value: Any) -> str:
    raw = _clean(value)
    if not raw:
        return ""
    try:
        parsed = urlparse(raw if "://" in raw else f"https://fixlist.invalid{raw if raw.startswith('/') else '/' + raw}")
        path = parsed.path or "/"
        return path.rstrip("/") or "/"
    except Exception:
        return raw.rstrip("/") or "/"


def _page_url(page: dict[str, Any]) -> str:
    return _clean(page.get("url") or page.get("final_url") or page.get("page_url") or page.get("path"))


def _affected_pages(fix: dict[str, Any]) -> list[str]:
    values = fix.get("affected_pages") if isinstance(fix.get("affected_pages"), list) else []
    if not values:
        fallback = fix.get("page_url") or fix.get("representative_page_url")
        values = [fallback] if fallback else []
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = _path(value)
        if key and key not in seen:
            seen.add(key)
            output.append(key)
    return output


def _template_family(page: dict[str, Any]) -> str:
    return _lower(page.get("page_template_family") or page.get("template_family"))


def _fix_family(fix: dict[str, Any]) -> str:
    return _lower(fix.get("page_template_family") or fix.get("template_family"))


def _usable_html(page: dict[str, Any]) -> bool:
    status = page.get("status_code") if page.get("status_code") is not None else page.get("status")
    try:
        status_value = int(status or 0)
    except (TypeError, ValueError):
        status_value = 0
    if status_value >= 400:
        return False
    content_type = _lower(page.get("content_type") or page.get("mime_type"))
    if content_type and "html" not in content_type and "xhtml" not in content_type:
        return False
    evidence_class = _lower(page.get("page_evidence_class") or page.get("evidence_class"))
    if evidence_class in {"failed_access", "non_html", "fetch_failed", "blocked"}:
        return False
    return True


def _indexability_state(page: dict[str, Any]) -> str:
    if page.get("indexable") is True:
        return "indexable"
    if page.get("indexable") is False:
        return "non_indexable"
    robots = _lower(page.get("robots") or page.get("robots_meta"))
    if "noindex" in robots:
        return "non_indexable"
    return "unknown"


def _important_page(page: dict[str, Any]) -> bool:
    if page.get("is_important_business_page") is True:
        return True
    path = _path(_page_url(page))
    if path in {"/", "/index.html"}:
        return True
    family = _template_family(page)
    if family in IMPORTANT_TEMPLATE_FAMILIES:
        return True
    intent = _lower(page.get("estimated_page_intent") or page.get("page_intent"))
    return intent in {"transactional", "commercial", "conversion", "money_page"}


def _is_search_facing(fix: dict[str, Any]) -> bool:
    category = _lower(fix.get("category"))
    if category in SEARCH_FACING_CATEGORIES:
        return True
    rule = _lower(fix.get("rule") or fix.get("type"))
    return any(token in rule for token in SEARCH_FACING_RULE_TOKENS)


def _base_severity(fix: dict[str, Any]) -> str:
    explicit = _lower(fix.get("base_severity") or fix.get("technical_severity"))
    if explicit in SEVERITY_RANK:
        return explicit
    current = _lower(fix.get("priority"))
    return current if current in SEVERITY_RANK else "medium"


def _evidence_class(fix: dict[str, Any]) -> str:
    explicit = _lower(fix.get("evidence_class") or fix.get("repair_evidence_class"))
    if explicit in {"confirmed_problem", "improvement", "opportunity"}:
        return explicit
    text = " ".join(
        _lower(fix.get(key))
        for key in ("rule", "type", "issue_title", "title", "source", "verification_state")
    )
    if any(token in text for token in OPPORTUNITY_TOKENS):
        return "opportunity"
    if _lower(fix.get("verification_state")) in {"needs_verification", "inconclusive", "provisional"}:
        return "improvement"
    return "confirmed_problem"


def _shared_repair_confirmed(fix: dict[str, Any]) -> bool:
    if fix.get("shared_repair_confirmed") is True:
        return True
    confidence = _lower(fix.get("repair_surface_confidence") or fix.get("shared_repair_confidence"))
    state = _lower(fix.get("repair_surface_state") or fix.get("shared_repair_state"))
    return confidence in {"high", "confirmed"} or state in {"confirmed", "confirmed_shared", "shared_repair_confirmed"}


def _confidence(fix: dict[str, Any]) -> float:
    raw = fix.get("evidence_confidence")
    if raw is None:
        raw = fix.get("confidence_score")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = 0.0
    return max(0.0, min(100.0, value))


def _family_label(family: str) -> str:
    return {
        "product_page": "product pages",
        "collection_page": "collection pages",
        "activity_detail": "activity pages",
        "loan_program": "loan pages",
        "guide_article": "guide pages",
        "location_landing": "location pages",
        "booking_or_checkout": "booking pages",
        "conversion": "conversion pages",
    }.get(family, family.replace("_", " ") + (" pages" if family else ""))


@dataclass(frozen=True)
class CoverageContext:
    """Coverage counted over one URL universe, not two.

    The customer-facing string is "N of M <family> pages checked are affected".
    That is only a ratio if N and M are drawn from the same set. Production
    shipped 126/1, 35/30 and 47/6 because the numerator counted every affected
    URL while the denominator counted usable HTML pages in a single family.

    So the counts are kept apart and named for what they are:
      affected_reported  - every URL the detector listed
      affected_observed  - those the crawl actually retained evidence for
      affected_eligible  - those inside the denominator's own universe
    Only affected_eligible may be divided by checked_eligible.
    """

    affected_reported: int
    affected_observed: int
    affected_eligible: int
    checked_eligible: int | None
    indexable_affected: int
    non_indexable_affected: int
    unknown_indexability_affected: int
    indexable_checked_eligible: int | None
    important_affected: int

    @property
    def affected_checked(self) -> int:
        """Backwards-compatible alias for the reported total."""
        return self.affected_reported

    @property
    def affected_universe_is_comparable(self) -> bool:
        """True only when every observed affected page is in the denominator.

        If some are outside it, the quotient understates rather than overstating
        -- "0 of 1 homepage pages are affected" for 126 real affected pages is
        arithmetically valid and substantively a lie. Suppressing the ratio and
        stating the count is the honest answer; partitioning by family is the
        better one and is the rest of this patch.
        """
        return self.affected_observed > 0 and self.affected_eligible == self.affected_observed

    @property
    def checked_coverage(self) -> float | None:
        # No measured universe means no ratio. Access and failure evidence lands
        # here by design: those pages are deliberately outside the usable-HTML
        # denominator, so an observation count is the only honest output.
        if not self.checked_eligible or not self.affected_universe_is_comparable:
            return None
        ratio = self.affected_eligible / max(1, self.checked_eligible)
        return ratio if 0.0 <= ratio <= 1.0 else None

    @property
    def searchable_coverage(self) -> float | None:
        if not self.indexable_checked_eligible or not self.affected_universe_is_comparable:
            return None
        ratio = self.indexable_affected / max(1, self.indexable_checked_eligible)
        return ratio if 0.0 <= ratio <= 1.0 else None


def build_coverage_context(fix: dict[str, Any], pages: list[dict[str, Any]]) -> CoverageContext:
    affected = set(_affected_pages(fix))
    page_lookup = {
        _path(_page_url(page)): page
        for page in pages
        if isinstance(page, dict) and _path(_page_url(page))
    }
    matched_affected = [page_lookup[key] for key in affected if key in page_lookup]

    family = _fix_family(fix)
    comparable_family = bool(family and family not in {"mixed", "sitewide", "cross_cutting", "standard"})
    usable = [page for page in pages if isinstance(page, dict) and _usable_html(page)]
    eligible = [page for page in usable if _template_family(page) == family] if comparable_family else []

    explicit_eligible = fix.get("checked_eligible_count") or fix.get("eligible_page_count")
    try:
        explicit_eligible_count = int(explicit_eligible) if explicit_eligible is not None else None
    except (TypeError, ValueError):
        explicit_eligible_count = None

    checked_eligible = explicit_eligible_count if explicit_eligible_count and explicit_eligible_count > 0 else (len(eligible) if comparable_family and eligible else None)

    # The numerator restricted to the denominator's own universe. Without this
    # intersection the two counts describe different sets of URLs and their
    # quotient is not a coverage figure at all.
    eligible_keys = {_path(_page_url(page)) for page in eligible}
    affected_eligible_pages = [page for page in matched_affected if _path(_page_url(page)) in eligible_keys]

    states = [_indexability_state(page) for page in affected_eligible_pages]
    indexable_affected = states.count("indexable")
    non_indexable_affected = states.count("non_indexable")
    unknown_affected = max(0, len(affected_eligible_pages) - indexable_affected - non_indexable_affected)

    indexable_eligible = None
    if checked_eligible is not None:
        if explicit_eligible_count is not None and fix.get("indexable_checked_eligible_count") is not None:
            try:
                indexable_eligible = max(0, int(fix.get("indexable_checked_eligible_count") or 0))
            except (TypeError, ValueError):
                indexable_eligible = None
        elif eligible:
            indexable_eligible = sum(1 for page in eligible if _indexability_state(page) == "indexable")

    important_affected = sum(1 for page in matched_affected if _important_page(page))

    # An explicit eligible count supplied by a detector has no URL set behind
    # it, so the intersection cannot be computed and the observed count is the
    # most that can honestly be claimed as eligible.
    affected_eligible = (
        min(len(matched_affected), checked_eligible)
        if explicit_eligible_count is not None and checked_eligible is not None
        else len(affected_eligible_pages)
    )

    return CoverageContext(
        affected_reported=len(affected),
        affected_observed=len(matched_affected),
        affected_eligible=affected_eligible,
        checked_eligible=checked_eligible,
        indexable_affected=indexable_affected,
        non_indexable_affected=non_indexable_affected,
        unknown_indexability_affected=unknown_affected,
        indexable_checked_eligible=indexable_eligible,
        important_affected=important_affected,
    )


def _action_priority(base_severity: str, evidence_class: str, context: CoverageContext, *, search_facing: bool) -> str:
    if evidence_class == "opportunity":
        return "review"
    if evidence_class == "improvement":
        return "improve" if base_severity in {"low", "medium"} else "important"

    if base_severity in {"critical", "high"}:
        band = "fix_first"
    elif base_severity == "medium":
        band = "important"
    else:
        band = "improve"

    # Search-facing work that is overwhelmingly confined to deliberately
    # non-indexable checked pages should not receive the same action urgency.
    known = context.indexable_affected + context.non_indexable_affected
    if search_facing and known >= 3 and context.non_indexable_affected / known >= 0.80:
        if band == "fix_first" and base_severity != "critical":
            band = "important"
        elif band == "important":
            band = "improve"
    return band


def _sort_score(
    base_severity: str,
    action_priority: str,
    context: CoverageContext,
    fix: dict[str, Any],
    *,
    search_facing: bool,
) -> int:
    score = ACTION_RANK[action_priority] * 1000 + SEVERITY_RANK[base_severity] * 100
    coverage = context.searchable_coverage if search_facing and context.searchable_coverage is not None else context.checked_coverage
    if coverage is not None:
        score += round(min(1.0, coverage) * 40)
    score += min(20, context.important_affected * 5)
    score += round(_confidence(fix) / 10)
    if _shared_repair_confirmed(fix) and context.affected_checked >= 2:
        score += 15
    known = context.indexable_affected + context.non_indexable_affected
    if search_facing and known >= 3 and context.non_indexable_affected / known >= 0.80:
        score -= 25
    return score


def _priority_reason(
    fix: dict[str, Any],
    base_severity: str,
    context: CoverageContext,
    *,
    search_facing: bool,
) -> str:
    family = _fix_family(fix)
    label = _family_label(family) if family else "relevant pages"
    affected_count = max(context.affected_checked, len(_affected_pages(fix)))

    # Only state "N of M" when N and M were counted over the same URLs.
    if search_facing and context.indexable_checked_eligible and context.indexable_affected and context.affected_universe_is_comparable:
        return f"{context.indexable_affected} of {context.indexable_checked_eligible} searchable {label} checked are affected."
    if context.checked_eligible and context.affected_eligible and context.affected_universe_is_comparable:
        return f"{context.affected_eligible} of {context.checked_eligible} {label} checked are affected."
    if _shared_repair_confirmed(fix) and affected_count > 1:
        return f"One shared change may improve {affected_count} checked pages."
    if affected_count > 0 and not context.affected_universe_is_comparable:
        # The affected pages sit outside this family's measured universe, so
        # there is no denominator to divide by. Report what was observed. This
        # sits after the shared-repair message, which says more about the same
        # situation when the detector proved a shared surface.
        noun = "page" if affected_count == 1 else "pages"
        return f"{affected_count} checked {noun} are affected."

    # When the eligible denominator is unknown, keep the customer claim scoped
    # to the checked sample. Important-page evidence may refine the explanation,
    # but must not make the wording sound site-wide or exhaustive.
    if context.checked_eligible is None and affected_count > 0:
        if affected_count == 1:
            return "1 checked page is affected."
        if context.important_affected == 1:
            return f"{affected_count} checked pages are affected, including 1 important page."
        if context.important_affected > 1:
            return f"{affected_count} checked pages are affected, including {context.important_affected} important pages."
        return f"{affected_count} checked pages are affected."

    if context.important_affected == 1:
        return "1 important page is affected."
    if context.important_affected > 1:
        return f"{context.important_affected} important pages are affected."
    known = context.indexable_affected + context.non_indexable_affected
    if search_facing and known >= 3 and context.non_indexable_affected / known >= 0.80:
        return "Most affected pages checked are non-indexable, so this is lower priority."
    if base_severity == "critical" and affected_count == 1:
        return "A serious technical problem affects this page."
    if affected_count == 1:
        return "1 checked page is affected."
    return f"{affected_count} checked pages are affected."


def annotate_repair_priority(fix: dict[str, Any], pages: list[dict[str, Any]]) -> dict[str, Any]:
    """Add contextual customer priority without mutating scanner severity.

    This is deliberately a synthesis-layer annotation. It does not change crawl
    topology, sampling, page caps, authority, or the underlying finding evidence.
    """
    base_severity = _base_severity(fix)
    evidence_class = _evidence_class(fix)
    context = build_coverage_context(fix, pages)
    search_facing = _is_search_facing(fix)
    action_priority = _action_priority(base_severity, evidence_class, context, search_facing=search_facing)
    score = _sort_score(base_severity, action_priority, context, fix, search_facing=search_facing)
    shared_confirmed = _shared_repair_confirmed(fix)

    priority_context = {
        "version": REPAIR_PRIORITY_VERSION,
        "base_severity": base_severity,
        "action_priority": action_priority,
        "action_priority_score": score,
        "evidence_class": evidence_class,
        "search_facing": search_facing,
        "affected_checked": context.affected_checked,
        "checked_eligible": context.checked_eligible,
        "checked_coverage": round(context.checked_coverage, 3) if context.checked_coverage is not None else None,
        "indexable_affected": context.indexable_affected,
        "non_indexable_affected": context.non_indexable_affected,
        "unknown_indexability_affected": context.unknown_indexability_affected,
        "indexable_checked_eligible": context.indexable_checked_eligible,
        "searchable_coverage": round(context.searchable_coverage, 3) if context.searchable_coverage is not None else None,
        "important_affected": context.important_affected,
        "shared_repair_confirmed": shared_confirmed,
        "coverage_scope": "checked_sample",
    }

    return {
        **fix,
        "base_severity": base_severity,
        "action_priority": action_priority,
        "action_priority_score": score,
        "priority_reason": _priority_reason(fix, base_severity, context, search_facing=search_facing),
        "repair_leverage_confirmed": shared_confirmed,
        "priority_context": priority_context,
    }


def annotate_repair_priorities(fixes: list[dict[str, Any]], pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    annotated = [annotate_repair_priority(fix, pages) for fix in fixes if isinstance(fix, dict)]
    return sorted(
        annotated,
        key=lambda fix: (
            ACTION_RANK.get(_lower(fix.get("action_priority")), 0),
            int(fix.get("action_priority_score") or 0),
        ),
        reverse=True,
    )
