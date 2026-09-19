from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .repair_priority_calibration import technical_base_severity
from .repair_coverage import repair_evidence_key_function

FOUR_FACTOR_PRIORITY_VERSION = "repair_priority_v3_four_factor_v1"
GSC_PAGE_VALUE_EVIDENCE_VERSION = "gsc_page_value_v1_normalized"

CONFIDENCE_VALUES = {
    "verified": 1.0,
    "heuristic": 0.7,
    "unverified": 0.4,
}

MONEY_FAMILIES = {
    "booking_or_checkout",
    "calculator",
    "comparison_page",
    "conversion",
    "loan_program",
    "pricing_page",
    "product_detail",
    "product_page",
    "activity_detail",
}
HUB_FAMILIES = {
    "homepage",
    "collection_page",
    "location_landing",
    "store_finder",
    "directory",
    "category_page",
}
BLOG_FAMILIES = {"article", "blog", "blog_post", "guide_article", "news_article"}
UTILITY_FAMILIES = {"archive", "help", "legal", "search", "standard", "trust", "utility"}

ACCESS_CORRECTNESS_RULES = {
    "blocked_page",
    "broken_page",
    "failed_page",
    "rate_limited_page",
    "redirect_destination_blocked",
    "redirect_destination_failed",
    "server_error",
    "soft_404_active",
    "template_unresolved_visible",
    "visible_template_token",
}
UNIQUENESS_RULES = {
    "duplicate_content",
    "duplicate_main_content",
    "duplicate_meta_description",
    "duplicate_title_localized",
    "duplicate_title_query_variants",
    "duplicate_title_template",
}
DISCOVERY_RULES = {
    "internal_link_redirect",
    "potential_orphan_pages",
    "sitemap_indexability_conflict",
    "sitemap_redirect",
}
IMPACT_TWO_RULES = {
    "canonical_missing",
    "missing_canonical",
    "missing_h1",
    "multiple_h1",
    "missing_meta_description",
    "empty_meta_description",
    "malformed_meta_description",
    "meta_description_unusable",
    "page_weight",
    "page_weight_large",
    "stale_content",
    "freshness_conflict",
}
IMPACT_ONE_RULES = {
    "image_alt_text",
    "missing_image_alt",
    "title_over_pixel_limit",
    "title_length",
    "social_metadata",
}
DECORATIVE_RULES = {"decorative_image_alt", "decorative_only"}

VERIFIED_STATES = {"accepted", "confirmed", "pass", "verified"}
HEURISTIC_STATES = {
    "heuristic",
    "inconclusive",
    "needs_review",
    "needs_verification",
    "provisional",
}
UNVERIFIED_STATES = {
    "access_limited",
    "blocked",
    "failed",
    "not_verified",
    "unknown",
    "unverified",
}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _lower(value: Any) -> str:
    return _clean(value).lower()


def _raw_key(value: Any) -> str:
    return _clean(value)


def _key_function(*, scan_origin: str, identity_version: str) -> Callable[[Any], str]:
    if identity_version:
        return repair_evidence_key_function(
            legacy_key=_raw_key,
            scan_origin=scan_origin,
            identity_version=identity_version,
        )
    return _raw_key


def _page_url(page: dict[str, Any]) -> str:
    return _clean(page.get("url") or page.get("final_url") or page.get("page_url") or page.get("path"))


def _template_family(page: dict[str, Any]) -> str:
    return _lower(page.get("page_template_family") or page.get("template_family"))


def _fix_family(fix: dict[str, Any]) -> str:
    return _lower(fix.get("page_template_family") or fix.get("template_family"))


def _affected_values(fix: dict[str, Any]) -> list[Any]:
    values = fix.get("affected_pages") if isinstance(fix.get("affected_pages"), list) else []
    if values:
        return values
    fallback = fix.get("page_url") or fix.get("representative_page_url")
    return [fallback] if fallback else []


def _indexable(page: dict[str, Any]) -> bool | None:
    if page.get("indexable") is True:
        return True
    if page.get("indexable") is False:
        return False
    robots = _lower(page.get("robots") or page.get("robots_meta") or page.get("meta_robots"))
    if "noindex" in robots:
        return False
    return None


def _verification_class(fix: dict[str, Any]) -> str:
    states = {
        _lower(fix.get("verification_state")),
        _lower(fix.get("evidence_status")),
        _lower(fix.get("assessment_state")),
    }
    states.discard("")
    if states & VERIFIED_STATES:
        return "verified"
    if states & HEURISTIC_STATES:
        return "heuristic"
    if states & UNVERIFIED_STATES:
        return "unverified"

    confidence = fix.get("evidence_confidence")
    if confidence is None:
        confidence = fix.get("confidence_score")
    try:
        numeric = float(confidence)
    except (TypeError, ValueError):
        return "unverified"
    if numeric >= 90:
        return "verified"
    if numeric >= 60:
        return "heuristic"
    return "unverified"


def _page_role_value(page: dict[str, Any]) -> tuple[float | None, str]:
    explicit_role = _lower(page.get("page_value_role") or page.get("business_role"))
    family = _template_family(page)
    intent = _lower(page.get("estimated_page_intent") or page.get("page_intent"))

    if explicit_role == "money" or page.get("is_important_business_page") is True:
        return 1.0, "money"
    if explicit_role == "hub":
        return 0.8, "hub"
    if explicit_role == "blog":
        return 0.5, "blog"
    if explicit_role == "utility":
        return 0.1, "utility"

    if intent in {"commercial", "conversion", "money_page", "transactional"} or family in MONEY_FAMILIES:
        return 1.0, "money"
    if family in HUB_FAMILIES:
        return 0.8, "hub"
    if family in BLOG_FAMILIES:
        return 0.5, "blog"
    if family in UTILITY_FAMILIES:
        return 0.1, "utility"
    return None, "unknown"


def _valid_gsc_page_value(fix: dict[str, Any]) -> float | None:
    evidence = fix.get("gsc_priority_evidence")
    if not isinstance(evidence, dict):
        return None
    if evidence.get("version") != GSC_PAGE_VALUE_EVIDENCE_VERSION:
        return None
    if _lower(evidence.get("provider")) != "gsc":
        return None
    if _lower(evidence.get("state")) not in {"connected_valid", "verified"}:
        return None
    if _lower(evidence.get("freshness_state")) not in {"current", "fresh"}:
        return None
    try:
        value = float(evidence.get("normalized_page_value"))
    except (TypeError, ValueError):
        return None
    if not 0.0 <= value <= 1.0:
        return None
    return value


def _impact(fix: dict[str, Any], affected_pages: list[dict[str, Any]], confidence_state: str) -> tuple[int, str]:
    rule = _lower(fix.get("rule") or fix.get("type"))
    category = _lower(fix.get("category"))

    if rule in DECORATIVE_RULES:
        return 0, "decorative evidence"
    if rule in ACCESS_CORRECTNESS_RULES or category in {"404_error", "access", "correctness"}:
        return 5, "access/correctness"
    if rule in UNIQUENESS_RULES or category in {"duplicate_content", "uniqueness"}:
        return 4, "uniqueness"

    if rule in {"canonical_missing", "missing_canonical"}:
        live_duplicates = fix.get("verified_live_duplicate_routes")
        if confidence_state == "verified" and isinstance(live_duplicates, list) and live_duplicates:
            return 3, "canonical gap with verified live duplicate route"
        return 2, "canonical gap"

    if "noindex" in rule or rule in {"sitemap_indexability_conflict", "route_boundary_candidate_indexable"}:
        if confidence_state == "verified" and any(_page_role_value(page)[0] == 1.0 for page in affected_pages):
            return 5, "verified indexability conflict on a money page"
        return 3, "discovery/indexability conflict"

    if rule in DISCOVERY_RULES or category in {"discovery", "internal_link", "sitemap"}:
        return 3, "discovery"
    if rule in IMPACT_TWO_RULES or category in {"meta_description", "page_weight", "freshness"}:
        return 2, "description/weight/freshness"
    if rule in IMPACT_ONE_RULES or category in {"alt_text", "image_alt_text", "social_metadata", "title_length"}:
        return 1, "low-impact optimization"

    technical_severity, _ = technical_base_severity(fix)
    fallback = {"critical": 5, "high": 4, "medium": 2, "low": 1}.get(technical_severity, 2)
    return fallback, "technical-severity fallback"


@dataclass(frozen=True)
class ReachFactor:
    value: float | None
    affected_indexable: int
    observed_indexable_family: int | None
    state: str
    reason: str


def _reach(
    fix: dict[str, Any],
    pages: list[dict[str, Any]],
    *,
    scan_origin: str,
    identity_version: str,
) -> ReachFactor:
    family = _fix_family(fix)
    if not family or family in {"cross_cutting", "mixed", "sitewide", "standard"}:
        return ReachFactor(None, 0, None, "unknown", "no matching observed/indexable family denominator")

    key_for = _key_function(scan_origin=scan_origin, identity_version=identity_version)
    page_lookup: dict[str, dict[str, Any]] = {}
    denominator_keys: set[str] = set()
    for page in pages or []:
        if not isinstance(page, dict) or _template_family(page) != family or _indexable(page) is not True:
            continue
        key = key_for(_page_url(page))
        if key:
            page_lookup[key] = page
            denominator_keys.add(key)

    if not denominator_keys:
        return ReachFactor(None, 0, None, "unknown", "no matching observed/indexable family denominator")

    affected_keys: list[str] = []
    for raw in _affected_values(fix):
        key = key_for(raw)
        if key and key not in affected_keys:
            affected_keys.append(key)

    # Reach is only a ratio when every affected observation can be placed in the
    # same observed/indexable family universe. Probe-only or cross-family URLs
    # make the denominator non-comparable rather than silently becoming zero.
    if not affected_keys or any(key not in page_lookup for key in affected_keys):
        return ReachFactor(None, 0, len(denominator_keys), "unknown", "affected evidence is outside the matching observed/indexable family denominator")

    numerator = len(affected_keys)
    denominator = len(denominator_keys)
    value = numerator / denominator
    if not 0.0 <= value <= 1.0:
        return ReachFactor(None, numerator, denominator, "unknown", "affected evidence and family denominator are not comparable")
    return ReachFactor(value, numerator, denominator, "known", "matching observed/indexable family denominator")


def build_four_factor_priority(
    fix: dict[str, Any],
    pages: list[dict[str, Any]],
    *,
    scan_origin: str = "",
    identity_version: str = "",
) -> dict[str, Any]:
    """Build the B19 factor evidence without replacing canonical review ranking.

    This helper deliberately does not write `priority`, `action_priority` or the
    existing sort score. The integration owner may consume the authenticated
    factor envelope after Python Review has produced canonical repairs.
    """
    key_for = _key_function(scan_origin=scan_origin, identity_version=identity_version)
    page_lookup = {
        key_for(_page_url(page)): page
        for page in pages or []
        if isinstance(page, dict) and key_for(_page_url(page))
    }
    affected_pages = [
        page_lookup[key_for(raw)]
        for raw in _affected_values(fix)
        if key_for(raw) in page_lookup
    ]

    confidence_state = _verification_class(fix)
    confidence = CONFIDENCE_VALUES[confidence_state]
    impact, impact_reason = _impact(fix, affected_pages, confidence_state)
    reach = _reach(
        fix,
        pages,
        scan_origin=scan_origin,
        identity_version=identity_version,
    )

    page_values = [_page_role_value(page) for page in affected_pages]
    known_values = [(value, role) for value, role in page_values if value is not None]
    if known_values:
        base_page_value, page_value_role = max(known_values, key=lambda item: item[0])
        page_value_state = "known"
    else:
        base_page_value, page_value_role = None, "unknown"
        page_value_state = "unknown"

    gsc_value = _valid_gsc_page_value(fix)
    page_value = base_page_value
    page_value_source = "base_role" if base_page_value is not None else "unknown"
    if gsc_value is not None:
        page_value = max(base_page_value or 0.0, gsc_value)
        page_value_source = "base_role+gsc_verified"
        page_value_state = "known"

    score = None
    if reach.value is not None and page_value is not None:
        score = round(impact * reach.value * page_value * confidence, 6)

    technical_severity, technical_severity_source = technical_base_severity(fix)
    explanation = [
        f"Impact {impact}/5: {impact_reason}.",
        (
            f"Reach {reach.value:.3f}: {reach.affected_indexable} of {reach.observed_indexable_family} observed indexable {_fix_family(fix)} pages are affected."
            if reach.value is not None
            else f"Reach unknown: {reach.reason}."
        ),
        (
            f"Page value {page_value:.3f}: {page_value_role} page evidence ({page_value_source})."
            if page_value is not None
            else "Page value unknown: no affected page has an evidenced money/hub/blog/utility role."
        ),
        f"Confidence {confidence:.1f}: {confidence_state} evidence.",
        f"Technical/base severity remains {technical_severity} ({technical_severity_source}); this factor envelope does not overwrite canonical Review ranking.",
    ]

    return {
        "version": FOUR_FACTOR_PRIORITY_VERSION,
        "impact": impact,
        "impact_reason": impact_reason,
        "reach": reach.value,
        "reach_state": reach.state,
        "reach_affected_indexable": reach.affected_indexable,
        "reach_observed_indexable_family": reach.observed_indexable_family,
        "page_value": page_value,
        "page_value_state": page_value_state,
        "page_value_role": page_value_role,
        "page_value_source": page_value_source,
        "confidence": confidence,
        "confidence_state": confidence_state,
        "priority_factor_score": score,
        "score_state": "known" if score is not None else "unknown",
        "technical_base_severity": technical_severity,
        "technical_severity_source": technical_severity_source,
        "explanation": explanation,
    }


def annotate_four_factor_priority(
    fix: dict[str, Any],
    pages: list[dict[str, Any]],
    *,
    scan_origin: str = "",
    identity_version: str = "",
) -> dict[str, Any]:
    return {
        **fix,
        "stage3_priority_factors": build_four_factor_priority(
            fix,
            pages,
            scan_origin=scan_origin,
            identity_version=identity_version,
        ),
    }
