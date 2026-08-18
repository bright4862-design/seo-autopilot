from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import urlparse

REPAIR_IDENTITY_VERSION = "repair_identity_v1_conservative"
REPAIR_VERIFICATION_VERSION = "repair_verification_v2_eligibility_aware"

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

INELIGIBLE_EVIDENCE_CLASSES = {
    "failed_access",
    "fetch_failed",
    "blocked",
    "non_html",
}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _token(value: Any) -> str:
    return re.sub(r"\s+", " ", _clean(value).lower())


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


def _repair_surface(fix: dict[str, Any]) -> str:
    return _token(
        fix.get("repair_surface")
        or fix.get("implementation_surface")
        or fix.get("fix_surface")
    )


def _remediation_family(fix: dict[str, Any]) -> str:
    explicit = _token(
        fix.get("remediation_family")
        or fix.get("recommended_action_family")
        or fix.get("repair_action_family")
    )
    if explicit:
        return explicit
    # Copy text is allowed only as a provisional key. It is useful for display
    # grouping, but changing wording must never be enough to prove a repair fixed.
    return _token(fix.get("recommended_value") or fix.get("recommendation"))


def build_repair_identity(fix: dict[str, Any]) -> dict[str, Any]:
    """Build a conservative cross-scan repair identity.

    A rule + page-family resemblance is not enough for verified repair tracking.
    Stable identity requires an explicit implementation surface and an explicit
    remediation/action family. Otherwise we emit a provisional fingerprint that
    may help presentation, but it is not eligible for automatic `verified_fixed`.
    """
    rule = _token(fix.get("rule") or fix.get("type") or fix.get("issue_type"))
    category = _token(fix.get("category"))
    family = _token(fix.get("page_template_family") or fix.get("template_family"))
    scope = _token(fix.get("page_scope") or "page")
    surface = _repair_surface(fix)
    explicit_remediation = _token(
        fix.get("remediation_family")
        or fix.get("recommended_action_family")
        or fix.get("repair_action_family")
    )
    remediation = explicit_remediation or _remediation_family(fix)

    stable = bool(rule and surface and explicit_remediation)
    if stable:
        material = "|".join([rule, category, scope, family, surface, explicit_remediation])
        state = "stable"
    else:
        material = "|".join([rule, category, scope, family, surface, remediation])
        state = "provisional" if rule else "insufficient"

    fingerprint = hashlib.sha256(material.encode("utf-8")).hexdigest()[:24] if material.strip("|") else ""
    return {
        "version": REPAIR_IDENTITY_VERSION,
        "state": state,
        "stable": stable,
        "fingerprint": fingerprint,
        "rule": rule,
        "category": category,
        "page_scope": scope,
        "page_template_family": family,
        "repair_surface": surface,
        "remediation_family": explicit_remediation,
    }


def annotate_repair_identity(fix: dict[str, Any]) -> dict[str, Any]:
    identity = build_repair_identity(fix)
    return {
        **fix,
        "repair_identity": identity,
        "repair_fingerprint": identity["fingerprint"],
        "repair_identity_state": identity["state"],
        "repair_identity_stable": identity["stable"],
    }


def _page_key(page: dict[str, Any]) -> str:
    return _path(page.get("url") or page.get("final_url") or page.get("page_url") or page.get("path"))


def _page_lookup(pages: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for page in pages or []:
        if not isinstance(page, dict):
            continue
        key = _page_key(page)
        if key:
            lookup[key] = page
    return lookup


def _status_code(page: dict[str, Any]) -> int | None:
    raw = page.get("status_code") if page.get("status_code") is not None else page.get("status")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _page_indexability(page: dict[str, Any]) -> str:
    if page.get("indexable") is True:
        return "indexable"
    if page.get("indexable") is False:
        return "non_indexable"
    robots = _token(page.get("robots") or page.get("robots_meta") or page.get("meta_robots"))
    if "noindex" in robots:
        return "non_indexable"
    return "unknown"


def _is_search_facing(fix: dict[str, Any]) -> bool:
    category = _token(fix.get("category"))
    if category in SEARCH_FACING_CATEGORIES:
        return True
    rule = _token(fix.get("rule") or fix.get("type") or fix.get("issue_type"))
    return any(token in rule for token in SEARCH_FACING_RULE_TOKENS)


def verification_eligibility(fix: dict[str, Any], page: dict[str, Any]) -> tuple[str, str]:
    """Return whether a later page is comparable evidence for verifying a repair.

    This intentionally fails closed. Seeing the URL again is not enough: the
    page must still be a usable HTTP success document, and search-facing repairs
    must not be auto-verified after the page becomes deliberately non-indexable.
    Unknown indexability remains comparable so older scans without an explicit
    `indexable` field stay readable; an explicit noindex/non-indexable state is
    treated as ineligible rather than as proof that a metadata repair succeeded.
    """
    if not isinstance(page, dict):
        return "unknown", "Comparable page evidence is unavailable."

    evidence_class = _token(page.get("page_evidence_class") or page.get("evidence_class"))
    if evidence_class in INELIGIBLE_EVIDENCE_CLASSES:
        return "ineligible", f"Page evidence is {evidence_class or 'not usable'}."

    status = _status_code(page)
    if status is None:
        return "unknown", "HTTP status was not available for the rechecked page."
    if status < 200 or status >= 300:
        return "ineligible", f"Page now returns HTTP {status}, so the same check is not comparable."

    content_type = _token(page.get("content_type") or page.get("mime_type"))
    if content_type and "html" not in content_type and "xhtml" not in content_type:
        return "ineligible", "Page is no longer an HTML document eligible for the same check."

    if _is_search_facing(fix) and _page_indexability(page) == "non_indexable":
        return "ineligible", "Page is now non-indexable, so disappearance of the search-facing issue is not proof of repair."

    return "eligible", "The page was re-observed in a comparable state for this repair."


def compare_repair_runs(
    previous_fix: dict[str, Any],
    current_fixes: list[dict[str, Any]],
    current_pages: list[dict[str, Any]],
) -> dict[str, Any]:
    """Classify a previous repair against a later crawl without false `fixed` claims.

    `verified_fixed` is allowed only when a stable repair identity exists, no
    matching repair remains, every previously affected page is observed again,
    and every re-observed page remains eligible for the same technical check.
    Missing or no-longer-comparable evidence becomes `could_not_verify`.
    """
    previous_identity = build_repair_identity(previous_fix)
    previous_affected = _affected_pages(previous_fix)

    if not previous_identity["stable"]:
        return {
            "version": REPAIR_VERIFICATION_VERSION,
            "state": "could_not_verify",
            "reason": "Stable repair identity is not available for this repair.",
            "rechecked_pages": 0,
            "eligible_rechecked_pages": 0,
            "previous_affected_pages": len(previous_affected),
        }

    matching_current = []
    for current in current_fixes or []:
        if not isinstance(current, dict):
            continue
        identity = build_repair_identity(current)
        if identity["stable"] and identity["fingerprint"] == previous_identity["fingerprint"]:
            matching_current.append(current)

    previous_state = _token(
        previous_fix.get("verification_state")
        or previous_fix.get("repair_verification_state")
        or previous_fix.get("status")
    )

    if matching_current:
        state = "came_back" if previous_state in {"verified_fixed", "fixed", "resolved"} else "still_detected"
        return {
            "version": REPAIR_VERIFICATION_VERSION,
            "state": state,
            "reason": "The same stable repair fingerprint is present in the latest crawl.",
            "rechecked_pages": len(set(_affected_pages(matching_current[0]))),
            "eligible_rechecked_pages": 0,
            "previous_affected_pages": len(previous_affected),
        }

    lookup = _page_lookup(current_pages)
    previous_set = set(previous_affected)
    observed = previous_set & set(lookup)
    if not previous_set or not previous_set.issubset(lookup):
        return {
            "version": REPAIR_VERIFICATION_VERSION,
            "state": "could_not_verify",
            "reason": "One or more previously affected pages were not observed in the latest crawl.",
            "rechecked_pages": len(observed),
            "eligible_rechecked_pages": 0,
            "previous_affected_pages": len(previous_affected),
        }

    eligibility = {key: verification_eligibility(previous_fix, lookup[key]) for key in previous_set}
    eligible = [key for key, (state, _) in eligibility.items() if state == "eligible"]
    non_comparable = [
        {"page": key, "state": state, "reason": reason}
        for key, (state, reason) in sorted(eligibility.items())
        if state != "eligible"
    ]
    if non_comparable:
        return {
            "version": REPAIR_VERIFICATION_VERSION,
            "state": "could_not_verify",
            "reason": "All previous URLs were seen again, but one or more were not comparable evidence for the same repair check.",
            "rechecked_pages": len(observed),
            "eligible_rechecked_pages": len(eligible),
            "previous_affected_pages": len(previous_affected),
            "non_comparable_pages": non_comparable,
        }

    return {
        "version": REPAIR_VERIFICATION_VERSION,
        "state": "verified_fixed",
        "reason": "All previously affected pages were checked again in a comparable eligible state and the stable repair fingerprint was no longer detected.",
        "rechecked_pages": len(observed),
        "eligible_rechecked_pages": len(eligible),
        "previous_affected_pages": len(previous_affected),
    }
