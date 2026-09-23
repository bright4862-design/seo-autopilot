from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import urlparse

from .repair_coverage import PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION, repair_evidence_key_function

REPAIR_IDENTITY_VERSION = "repair_identity_v2_technical"
REPAIR_VERIFICATION_VERSION = "repair_verification_v3_contract_comparable"

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
        path = (parsed.path or "/").rstrip("/") or "/"
        return f"{path}?{parsed.query}" if parsed.query else path
    except Exception:
        return raw.rstrip("/") or "/"


def _affected_pages(fix: dict[str, Any], *, scan_origin: str = "", identity_version: str = "") -> list[str]:
    values = fix.get("affected_pages") if isinstance(fix.get("affected_pages"), list) else []
    if not values:
        fallback = fix.get("page_url") or fix.get("representative_page_url")
        values = [fallback] if fallback else []
    output: list[str] = []
    seen: set[str] = set()
    key_for = repair_evidence_key_function(legacy_key=_path, scan_origin=scan_origin, identity_version=identity_version)
    for value in values:
        key = key_for(value)
        if key and key not in seen:
            seen.add(key)
            output.append(key)
    return output


def _identity_field(fix: dict[str, Any], *fields: str) -> str:
    """Read technical identity without turning malformed evidence into text.

    Missing/empty strings may use historical aliases. A present non-string
    cannot be rescued by a lower-precedence alias into verification authority.
    """
    for field in fields:
        value = fix.get(field)
        if value is None:
            continue
        if not isinstance(value, str):
            return ""
        if value == "":
            continue
        return _token(value)
    return ""


def _repair_surface(fix: dict[str, Any]) -> str:
    return _identity_field(fix, "repair_surface", "implementation_surface", "fix_surface")


def _remediation_family(fix: dict[str, Any]) -> str:
    explicit = _identity_field(
        fix, "remediation_family", "recommended_action_family", "repair_action_family"
    )
    if explicit:
        return explicit
    # Copy text is allowed only as a provisional key. It is useful for display
    # grouping, but changing wording must never be enough to prove a repair fixed.
    return _token(fix.get("recommended_value") or fix.get("recommendation"))


def build_repair_identity(fix: dict[str, Any]) -> dict[str, Any]:
    """Build a conservative cross-scan repair identity.

    Stable verification identity is deliberately limited to durable technical
    identifiers: canonical rule identity, explicit implementation surface, and
    explicit remediation family. Presentation/grouping metadata such as category,
    page scope, and page-template family is retained as context but never enters
    the stable fingerprint, because those classifications can change while the
    underlying defect remains identical.

    A rule + page-family resemblance is not enough for verified repair tracking.
    Stable identity requires an explicit implementation surface and an explicit
    remediation/action family. Otherwise we emit a provisional fingerprint that
    may help presentation, but it is not eligible for automatic `verified_fixed`.
    """
    rule_id = _identity_field(fix, "rule_id")
    rule = _identity_field(fix, "rule_id", "rule", "type", "issue_type")
    category = _token(fix.get("category"))
    family = _token(fix.get("page_template_family") or fix.get("template_family"))
    scope = _token(fix.get("page_scope") or "page")
    surface = _repair_surface(fix)
    explicit_remediation = _identity_field(
        fix, "remediation_family", "recommended_action_family", "repair_action_family"
    )
    remediation = explicit_remediation or _remediation_family(fix)

    stable = bool(rule and surface and explicit_remediation)
    if stable:
        # Only durable technical identity participates in cross-scan authority.
        # Mutable classification/presentation fields remain outside this hash.
        material = "|".join([rule, surface, explicit_remediation])
        state = "stable"
    else:
        # Provisional identity may use grouping context because it is never
        # allowed to auto-verify a repair as fixed.
        material = "|".join([rule, category, scope, family, surface, remediation])
        state = "provisional" if rule else "insufficient"

    fingerprint = hashlib.sha256(material.encode("utf-8")).hexdigest()[:24] if material.strip("|") else ""
    return {
        "version": REPAIR_IDENTITY_VERSION,
        "state": state,
        "stable": stable,
        "fingerprint": fingerprint,
        "rule": rule,
        "rule_id": rule_id,
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


def _page_key(page: dict[str, Any], *, scan_origin: str = "", identity_version: str = "") -> str:
    key_for = repair_evidence_key_function(legacy_key=_path, scan_origin=scan_origin, identity_version=identity_version)
    return key_for(page.get("url") or page.get("final_url") or page.get("page_url") or page.get("path"))


def _page_lookup(pages: list[dict[str, Any]], *, scan_origin: str = "", identity_version: str = "") -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for page in pages or []:
        if not isinstance(page, dict):
            continue
        key = _page_key(page, scan_origin=scan_origin, identity_version=identity_version)
        if key:
            lookup[key] = page
    return lookup


def _persisted_reference_fingerprint(fix: dict[str, Any]) -> str:
    value = fix.get("repair_fingerprint")
    if not isinstance(value, str):
        return ""
    value = value.strip().lower()
    return value if re.fullmatch(r"[0-9a-f]{24}", value) else ""


def _provisional_current_conflicts(
    previous_identity: dict[str, Any],
    previous_affected: list[str],
    current: dict[str, Any],
    *,
    scan_origin: str = "",
    identity_version: str = "",
) -> bool:
    """Block false-fixed when current evidence points at the repair but lacks stable identity."""
    identity = build_repair_identity(current)
    if identity["stable"]:
        return False
    persisted = _persisted_reference_fingerprint(current)
    if persisted and persisted == previous_identity.get("fingerprint"):
        return True
    if identity.get("rule") != previous_identity.get("rule"):
        return False
    current_affected = set(_affected_pages(current, scan_origin=scan_origin, identity_version=identity_version))
    return bool(current_affected & set(previous_affected))


def _rule_evaluation_state(
    fix: dict[str, Any],
    page: dict[str, Any],
    current_contract: dict[str, Any] | None,
) -> tuple[str, str]:
    """Require originating-rule evidence before a versioned repair can be fixed."""
    previous_rule = _identity_field(fix, "rule_id", "rule", "type", "issue_type")
    previous_rule_version = _clean(fix.get("rule_definition_version"))
    previous_profile = _clean(fix.get("comparison_profile_version"))
    if not previous_rule_version and not previous_profile:
        return "not_required", "Historical repair has no explicit originating-rule contract."

    evidence = page.get("comparison_rule_evaluation") if isinstance(page, dict) else None
    if not isinstance(evidence, dict):
        return "unavailable", "Authenticated originating-rule evaluation is unavailable for this page."
    if _token(evidence.get("rule")) != previous_rule:
        return "unavailable", "Authenticated rule evidence does not match the historical repair."
    if previous_rule_version and _clean(evidence.get("rule_definition_version")) != previous_rule_version:
        return "unavailable", "Authenticated rule-definition evidence is incompatible with the historical repair."
    if previous_profile and _clean(evidence.get("comparison_profile_version")) != previous_profile:
        return "unavailable", "Authenticated comparison-profile evidence is incompatible with the historical repair."
    if isinstance(current_contract, dict):
        current_rule_version = _clean(current_contract.get("rule_definition_version"))
        current_profile = _clean(current_contract.get("comparison_profile_version"))
        if previous_rule_version and current_rule_version != previous_rule_version:
            return "unavailable", "Current rule-definition contract does not match the page evaluation."
        if previous_profile and current_profile != previous_profile:
            return "unavailable", "Current comparison profile does not match the page evaluation."
    if evidence.get("evaluated") is not True or evidence.get("applicable") is not True:
        return "unavailable", "The originating rule was not evaluated as applicable on this page."
    present = evidence.get("finding_present")
    if type(present) is not bool:
        return "unavailable", "The originating rule did not produce an exact finding state."
    return ("finding_present", "The originating rule still detects this repair.") if present else (
        "finding_absent", "The originating rule was re-evaluated and no longer detects this repair."
    )


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


def verification_contract_comparability(
    previous_fix: dict[str, Any],
    current_contract: dict[str, Any] | None,
) -> tuple[str, str]:
    """Check whether rule/comparison semantics are compatible across scans.

    This is deliberately metadata-only and fail-closed once a versioned repair
    declares either field. A changed detector or comparison profile must never
    make a repair disappear and then be reported as `verified_fixed`.

    Legacy repairs with neither version remain readable and continue through the
    page-level eligibility gate. Versioned repairs require the later scan to
    supply matching versions until an explicit compatibility map is introduced.
    """
    previous_rule = _clean(previous_fix.get("rule_definition_version"))
    previous_profile = _clean(previous_fix.get("comparison_profile_version"))
    previous_urls = _clean(previous_fix.get("evidence_url_identity_version"))
    current_urls = _clean((current_contract or {}).get("evidence_url_identity_version")) if isinstance(current_contract, dict) else ""
    supported_urls = {"", PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION}
    if previous_urls not in supported_urls or current_urls not in supported_urls or previous_urls != current_urls:
        return "incomparable", "Evidence URL identity rules differ or are unsupported across these scans."

    if not previous_rule and not previous_profile:
        if previous_urls:
            return "compatible", "Published evidence URL identity rules match across these scans."
        return "legacy_compatible", "No versioned comparison contract was stored on the historical repair."

    if not isinstance(current_contract, dict):
        return "incomparable", "The latest scan did not provide the comparison contract required by this historical repair."

    current_rule = _clean(current_contract.get("rule_definition_version"))
    current_profile = _clean(current_contract.get("comparison_profile_version"))

    if previous_rule and not current_rule:
        return "incomparable", "The latest scan did not provide the rule-definition version required for comparison."
    if previous_profile and not current_profile:
        return "incomparable", "The latest scan did not provide the comparison-profile version required for comparison."
    if previous_rule and previous_rule != current_rule:
        return "incomparable", "Checking rules changed since the previous scan."
    if previous_profile and previous_profile != current_profile:
        return "incomparable", "The crawl comparison profile changed since the previous scan."

    return "compatible", "Rule definition and comparison profile are compatible with the previous repair."


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
    current_contract: dict[str, Any] | None = None,
    *,
    previous_scan_origin: str = "",
    scan_origin: str = "",
) -> dict[str, Any]:
    """Classify a previous repair against a later crawl without false `fixed` claims.

    `verified_fixed` is allowed only when a stable repair identity exists, no
    matching repair remains, rule/comparison semantics are compatible, every
    previously affected page is observed again, and every re-observed page
    remains eligible for the same technical check. Missing, changed-contract,
    or no-longer-comparable evidence becomes `could_not_verify`.
    """
    previous_identity = build_repair_identity(previous_fix)
    previous_version = _clean(previous_fix.get("evidence_url_identity_version"))
    current_version = _clean((current_contract or {}).get("evidence_url_identity_version")) if isinstance(current_contract, dict) else ""
    # Unknown versions are rejected by the comparison gate below, never used
    # to opt a historical repair into current semantics.
    previous_context = {"scan_origin": previous_scan_origin,
                        "identity_version": previous_version if previous_version == PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION else ""}
    current_context = {"scan_origin": scan_origin,
                       "identity_version": current_version if current_version == PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION else ""}
    previous_affected = _affected_pages(previous_fix, **previous_context)

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
    provisional_conflicts = []
    for current in current_fixes or []:
        if not isinstance(current, dict):
            continue
        identity = build_repair_identity(current)
        if identity["stable"] and identity["fingerprint"] == previous_identity["fingerprint"]:
            matching_current.append(current)
        elif _provisional_current_conflicts(
            previous_identity,
            previous_affected,
            current,
            **current_context,
        ):
            provisional_conflicts.append(current)

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
            "rechecked_pages": len(set(_affected_pages(matching_current[0], **current_context))),
            "eligible_rechecked_pages": 0,
            "previous_affected_pages": len(previous_affected),
        }

    if provisional_conflicts:
        return {
            "version": REPAIR_VERIFICATION_VERSION,
            "state": "could_not_verify",
            "reason": "The latest scan contains matching repair evidence without stable technical identity, so disappearance cannot be treated as fixed.",
            "rechecked_pages": 0,
            "eligible_rechecked_pages": 0,
            "previous_affected_pages": len(previous_affected),
            "comparison_contract_state": "current_fix_identity_conflict",
        }

    contract_state, contract_reason = verification_contract_comparability(previous_fix, current_contract)
    if contract_state == "incomparable":
        return {
            "version": REPAIR_VERIFICATION_VERSION,
            "state": "could_not_verify",
            "reason": contract_reason,
            "rechecked_pages": 0,
            "eligible_rechecked_pages": 0,
            "previous_affected_pages": len(previous_affected),
            "comparison_contract_state": contract_state,
        }

    if previous_version == PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION:
        raw_affected = previous_fix.get("affected_pages") or [previous_fix.get("page_url") or previous_fix.get("representative_page_url")]
        key_for = repair_evidence_key_function(**previous_context)
        if any(not key_for(value) for value in raw_affected):
            return {
                "version": REPAIR_VERIFICATION_VERSION,
                "state": "could_not_verify",
                "reason": "One or more previous URLs cannot be resolved against their original scan origin.",
                "rechecked_pages": 0,
                "eligible_rechecked_pages": 0,
                "previous_affected_pages": len(raw_affected),
                "comparison_contract_state": contract_state,
            }

    lookup = _page_lookup(current_pages, **current_context)
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
            "comparison_contract_state": contract_state,
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
            "comparison_contract_state": contract_state,
        }

    rule_evaluations = {key: _rule_evaluation_state(previous_fix, lookup[key], current_contract) for key in previous_set}
    required_rule_evidence = bool(
        _clean(previous_fix.get("rule_definition_version"))
        or _clean(previous_fix.get("comparison_profile_version"))
    )
    if required_rule_evidence:
        present = [key for key, (state, _) in rule_evaluations.items() if state == "finding_present"]
        unavailable = [
            {"page": key, "state": state, "reason": reason}
            for key, (state, reason) in sorted(rule_evaluations.items())
            if state not in {"finding_absent", "finding_present"}
        ]
        if present:
            return {
                "version": REPAIR_VERIFICATION_VERSION,
                "state": "could_not_verify",
                "reason": "Authenticated rule evidence still detects the issue, but no matching stable current repair was available.",
                "rechecked_pages": len(observed),
                "eligible_rechecked_pages": len(eligible),
                "previous_affected_pages": len(previous_affected),
                "comparison_contract_state": "current_repair_population_conflict",
            }
        if unavailable:
            return {
                "version": REPAIR_VERIFICATION_VERSION,
                "state": "could_not_verify",
                "reason": "All previous URLs were comparable, but authenticated originating-rule evidence was incomplete.",
                "rechecked_pages": len(observed),
                "eligible_rechecked_pages": len(eligible),
                "previous_affected_pages": len(previous_affected),
                "rule_evidence_gaps": unavailable,
                "comparison_contract_state": contract_state,
            }

    return {
        "version": REPAIR_VERIFICATION_VERSION,
        "state": "verified_fixed",
        "reason": "All previously affected pages were checked again under compatible rules, remained comparable, and authenticated originating-rule evidence no longer detected the stable repair.",
        "rechecked_pages": len(observed),
        "eligible_rechecked_pages": len(eligible),
        "previous_affected_pages": len(previous_affected),
        "comparison_contract_state": contract_state,
    }
