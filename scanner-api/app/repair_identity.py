from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import urlparse

REPAIR_IDENTITY_VERSION = "repair_identity_v1_conservative"
REPAIR_VERIFICATION_VERSION = "repair_verification_v1_evidence_rechecked"


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


def _page_keys(pages: list[dict[str, Any]]) -> set[str]:
    keys: set[str] = set()
    for page in pages or []:
        if not isinstance(page, dict):
            continue
        key = _path(page.get("url") or page.get("final_url") or page.get("page_url") or page.get("path"))
        if key:
            keys.add(key)
    return keys


def compare_repair_runs(
    previous_fix: dict[str, Any],
    current_fixes: list[dict[str, Any]],
    current_pages: list[dict[str, Any]],
) -> dict[str, Any]:
    """Classify a previous repair against a later crawl without false `fixed` claims.

    `verified_fixed` is allowed only when a stable repair identity exists, no
    matching repair remains, and every previously affected page was observed
    again in the later crawl. Missing pages become `could_not_verify`, not fixed.
    """
    previous_identity = build_repair_identity(previous_fix)
    previous_affected = _affected_pages(previous_fix)

    if not previous_identity["stable"]:
        return {
            "version": REPAIR_VERIFICATION_VERSION,
            "state": "could_not_verify",
            "reason": "Stable repair identity is not available for this repair.",
            "rechecked_pages": 0,
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
            "previous_affected_pages": len(previous_affected),
        }

    observed = _page_keys(current_pages)
    previous_set = set(previous_affected)
    rechecked = previous_set & observed
    if previous_set and previous_set.issubset(observed):
        return {
            "version": REPAIR_VERIFICATION_VERSION,
            "state": "verified_fixed",
            "reason": "All previously affected pages were checked again and the stable repair fingerprint was no longer detected.",
            "rechecked_pages": len(rechecked),
            "previous_affected_pages": len(previous_affected),
        }

    return {
        "version": REPAIR_VERIFICATION_VERSION,
        "state": "could_not_verify",
        "reason": "One or more previously affected pages were not observed in the latest crawl.",
        "rechecked_pages": len(rechecked),
        "previous_affected_pages": len(previous_affected),
    }
