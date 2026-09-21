from __future__ import annotations

import hashlib
import json
from typing import Any

from .repair_coverage import PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION, repair_evidence_key_function
from .repair_identity import build_repair_identity, verification_contract_comparability, verification_eligibility

ACCEPTANCE_CRITERION_VERSION = "fix_acceptance_criterion_v1"
VERIFICATION_PLAN_VERSION = "fix_verification_plan_v1"
VERIFICATION_RESULT_VERSION = "fix_verification_result_v1"
REGRESSION_REOPEN_VERSION = "fix_regression_reopen_v1"

PASS = "PASS"
PARTIAL = "PARTIAL"
FAIL = "FAIL"
COULD_NOT_VERIFY = "COULD_NOT_VERIFY"
VERIFICATION_STATES = frozenset({PASS, PARTIAL, FAIL, COULD_NOT_VERIFY})
MAX_RECHECK_URLS = 150
REQUIRED_RECHECK_OBSERVATIONS = (
    "http_status",
    "content_type",
    "indexability",
    "rule_predicate",
)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _stable_hash(value: dict[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _raw_affected_pages(fix: dict[str, Any]) -> list[str]:
    values = fix.get("affected_pages") if isinstance(fix.get("affected_pages"), list) else []
    if not values:
        fallback = fix.get("page_url") or fix.get("representative_page_url")
        values = [fallback] if fallback else []
    return [_clean(value) for value in values if _clean(value)]


def _declared_population_count(plan: dict[str, Any]) -> int | None:
    value = plan.get("population_count") if isinstance(plan, dict) else None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def build_acceptance_criterion(previous_fix: dict[str, Any]) -> dict[str, Any]:
    """Build a versioned, machine-testable repair acceptance criterion.

    New NextGen verification deliberately requires explicit rule/profile/URL
    identity versions. This does not alter the existing historical comparator.
    """
    previous_fix = previous_fix if isinstance(previous_fix, dict) else {}
    identity = build_repair_identity(previous_fix)
    rule_definition_version = _clean(previous_fix.get("rule_definition_version"))
    comparison_profile_version = _clean(previous_fix.get("comparison_profile_version"))
    evidence_url_identity_version = _clean(previous_fix.get("evidence_url_identity_version"))

    blockers: list[str] = []
    if not identity.get("stable") or not _clean(identity.get("fingerprint")):
        blockers.append("stable_repair_identity_required")
    if not rule_definition_version:
        blockers.append("rule_definition_version_required")
    if not comparison_profile_version:
        blockers.append("comparison_profile_version_required")
    if not evidence_url_identity_version:
        blockers.append("evidence_url_identity_version_required")
    elif evidence_url_identity_version != PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION:
        blockers.append("unsupported_evidence_url_identity_version")

    material = {
        "version": ACCEPTANCE_CRITERION_VERSION,
        "repair_identity_version": _clean(identity.get("version")),
        "repair_fingerprint": _clean(identity.get("fingerprint")),
        "rule": _clean(identity.get("rule_id") or identity.get("rule")),
        "rule_definition_version": rule_definition_version,
        "comparison_profile_version": comparison_profile_version,
        "evidence_url_identity_version": evidence_url_identity_version,
        "predicate": "defect_detected_equals_false",
    }
    return {
        **material,
        "criterion_id": _stable_hash(material),
        "state": "ready" if not blockers else "blocked",
        "blockers": blockers,
        "predicate_contract": {
            "field": "defect_detected",
            "operator": "equals",
            "expected": False,
            "requires_actual_re_evaluation": True,
            "population_semantics": "all_required_evidence",
        },
    }


def build_targeted_recheck_plan(
    previous_fix: dict[str, Any],
    *,
    previous_scan_origin: str = "",
    max_urls: int = MAX_RECHECK_URLS,
) -> dict[str, Any]:
    """Return a bounded declarative recheck plan; performs no network work."""
    previous_fix = previous_fix if isinstance(previous_fix, dict) else {}
    criterion = build_acceptance_criterion(previous_fix)
    raw_pages = _raw_affected_pages(previous_fix)
    try:
        requested_limit = int(max_urls)
    except (TypeError, ValueError):
        requested_limit = MAX_RECHECK_URLS
    limit = max(1, min(requested_limit, MAX_RECHECK_URLS))

    blockers = list(criterion.get("blockers") or [])
    if not raw_pages:
        blockers.append("affected_evidence_population_required")

    evidence_version = _clean(criterion.get("evidence_url_identity_version"))
    key_for = None
    if evidence_version == PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION:
        key_for = repair_evidence_key_function(
            scan_origin=previous_scan_origin,
            identity_version=evidence_version,
        )

    population: list[dict[str, str]] = []
    invalid_pages: list[str] = []
    seen: set[str] = set()
    for raw in raw_pages:
        key = key_for(raw) if key_for else ""
        if not key:
            invalid_pages.append(raw)
            continue
        if key in seen:
            continue
        seen.add(key)
        population.append({"url": raw, "evidence_key": key})
    if invalid_pages:
        blockers.append("ambiguous_or_unresolvable_evidence_url")

    requested = population[:limit]
    omitted_count = max(0, len(population) - len(requested))
    population_complete = not blockers and omitted_count == 0 and len(requested) == len(population) and bool(population)
    plan_state = "blocked" if blockers else ("bounded_incomplete" if omitted_count else "ready")

    return {
        "version": VERIFICATION_PLAN_VERSION,
        "state": plan_state,
        "repair_identity_version": _clean(criterion.get("repair_identity_version")),
        "repair_fingerprint": _clean(criterion.get("repair_fingerprint")),
        "criterion": criterion,
        "criterion_id": _clean(criterion.get("criterion_id")),
        "rule": _clean(criterion.get("rule")),
        "rule_definition_version": _clean(criterion.get("rule_definition_version")),
        "comparison_profile_version": _clean(criterion.get("comparison_profile_version")),
        "evidence_url_identity_version": evidence_version,
        "population_count": len(population),
        "population_complete": population_complete,
        "invalid_population_count": len(invalid_pages),
        "omitted_population_count": omitted_count,
        "max_recheck_urls": limit,
        "blockers": blockers,
        "requests": [
            {
                **item,
                "criterion_id": _clean(criterion.get("criterion_id")),
                "rule": _clean(criterion.get("rule")),
                "required_observations": list(REQUIRED_RECHECK_OBSERVATIONS),
            }
            for item in requested
        ],
    }


def _result_base(plan: dict[str, Any]) -> dict[str, Any]:
    population_count = _declared_population_count(plan)
    return {
        "version": VERIFICATION_RESULT_VERSION,
        "state": COULD_NOT_VERIFY,
        "repair_fingerprint": _clean(plan.get("repair_fingerprint")) if isinstance(plan, dict) else "",
        "criterion_id": _clean(plan.get("criterion_id")) if isinstance(plan, dict) else "",
        "required_population_count": population_count if population_count is not None else 0,
        "observed_population_count": 0,
        "evaluated_population_count": 0,
        "resolved_scope": [],
        "unresolved_scope": [],
        "unverifiable_scope": [],
    }


def _cannot_verify(
    plan: dict[str, Any],
    reason: str,
    *,
    unverifiable_scope: list[dict[str, str]] | None = None,
    observed_count: int = 0,
    evaluated_count: int = 0,
    resolved_scope: list[str] | None = None,
    unresolved_scope: list[str] | None = None,
) -> dict[str, Any]:
    result = _result_base(plan)
    result.update({
        "state": COULD_NOT_VERIFY,
        "reason": reason,
        "observed_population_count": observed_count,
        "evaluated_population_count": evaluated_count,
        "resolved_scope": list(resolved_scope or []),
        "unresolved_scope": list(unresolved_scope or []),
        "unverifiable_scope": list(unverifiable_scope or []),
    })
    return result


def _page_evidence_key(page: dict[str, Any], key_for: Any) -> str:
    if not isinstance(page, dict):
        return ""
    return key_for(page.get("url") or page.get("final_url") or page.get("page_url") or page.get("path"))


def _evaluation_evidence_key(row: dict[str, Any], key_for: Any) -> tuple[str, str]:
    if not isinstance(row, dict):
        return "", "invalid_evaluation_row"
    declared = _clean(row.get("evidence_key"))
    raw_url = row.get("url") or row.get("page_url")
    derived = key_for(raw_url) if raw_url else ""
    if declared and derived and declared != derived:
        return "", "evaluation_url_identity_mismatch"
    key = declared or derived
    return (key, "") if key else ("", "evaluation_evidence_key_missing")


def _historical_evidence_keys(previous_fix: dict[str, Any], key_for: Any) -> tuple[list[str], str]:
    keys: list[str] = []
    seen: set[str] = set()
    for raw in _raw_affected_pages(previous_fix if isinstance(previous_fix, dict) else {}):
        key = key_for(raw)
        if not key:
            return [], "Historical affected-page evidence cannot be resolved under the declared URL-identity contract."
        if key in seen:
            continue
        seen.add(key)
        keys.append(key)
    if not keys:
        return [], "Historical affected-page evidence population is empty."
    return keys, ""


def evaluate_verification_plan(
    plan: dict[str, Any],
    previous_fix: dict[str, Any],
    current_pages: list[dict[str, Any]],
    rule_evaluations: list[dict[str, Any]],
    current_contract: dict[str, Any] | None,
    *,
    scan_origin: str = "",
) -> dict[str, Any]:
    """Evaluate explicit re-observation evidence without inferring from disappearance."""
    if not isinstance(plan, dict) or plan.get("version") != VERIFICATION_PLAN_VERSION:
        return _cannot_verify(plan if isinstance(plan, dict) else {}, "Unknown or missing verification-plan version.")
    if plan.get("state") != "ready" or plan.get("population_complete") is not True:
        return _cannot_verify(plan, "The targeted recheck plan is blocked or does not cover the complete required evidence population.")

    criterion = plan.get("criterion") if isinstance(plan.get("criterion"), dict) else {}
    if criterion.get("version") != ACCEPTANCE_CRITERION_VERSION or criterion.get("state") != "ready":
        return _cannot_verify(plan, "The acceptance criterion is missing, blocked, or uses an unsupported version.")

    expected_criterion = build_acceptance_criterion(previous_fix if isinstance(previous_fix, dict) else {})
    criterion_fields = (
        "criterion_id",
        "repair_identity_version",
        "repair_fingerprint",
        "rule",
        "rule_definition_version",
        "comparison_profile_version",
        "evidence_url_identity_version",
        "predicate",
    )
    if expected_criterion.get("state") != "ready" or any(
        _clean(criterion.get(field)) != _clean(expected_criterion.get(field)) for field in criterion_fields
    ) or criterion.get("predicate_contract") != expected_criterion.get("predicate_contract"):
        return _cannot_verify(plan, "The acceptance criterion does not exactly match the historical repair contract.")

    plan_identity_fields = (
        "repair_identity_version",
        "repair_fingerprint",
        "criterion_id",
        "rule",
        "rule_definition_version",
        "comparison_profile_version",
        "evidence_url_identity_version",
    )
    if any(_clean(plan.get(field)) != _clean(expected_criterion.get(field)) for field in plan_identity_fields):
        return _cannot_verify(plan, "The verification plan identity/version metadata does not match the historical repair contract.")

    identity = build_repair_identity(previous_fix if isinstance(previous_fix, dict) else {})
    fingerprint = _clean(identity.get("fingerprint"))
    if not identity.get("stable") or not fingerprint or fingerprint != _clean(plan.get("repair_fingerprint")):
        return _cannot_verify(plan, "Stable repair identity is missing or does not match the verification plan.")
    if _clean(identity.get("version")) != _clean(plan.get("repair_identity_version")):
        return _cannot_verify(plan, "Repair identity version does not match the verification plan.")

    contract_state, contract_reason = verification_contract_comparability(previous_fix, current_contract)
    if contract_state != "compatible":
        return _cannot_verify(plan, f"Repair comparison contract is not compatible: {contract_reason}")

    expected_versions = {
        "rule_definition_version": _clean(criterion.get("rule_definition_version")),
        "comparison_profile_version": _clean(criterion.get("comparison_profile_version")),
        "evidence_url_identity_version": _clean(criterion.get("evidence_url_identity_version")),
    }
    if not isinstance(current_contract, dict) or any(
        _clean(current_contract.get(field)) != expected for field, expected in expected_versions.items()
    ):
        return _cannot_verify(plan, "Current comparison versions do not exactly match the acceptance criterion.")

    evidence_version = expected_versions["evidence_url_identity_version"]
    if evidence_version != PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION:
        return _cannot_verify(plan, "Unsupported evidence URL identity version.")
    key_for = repair_evidence_key_function(scan_origin=scan_origin, identity_version=evidence_version)

    expected_keys, population_error = _historical_evidence_keys(previous_fix, key_for)
    if population_error:
        return _cannot_verify(plan, population_error)

    requests = plan.get("requests") if isinstance(plan.get("requests"), list) else []
    if not requests or any(not isinstance(item, dict) for item in requests):
        return _cannot_verify(plan, "The recheck plan contains an empty or malformed evidence population.")
    required_keys = [_clean(item.get("evidence_key")) for item in requests]
    if any(not key for key in required_keys) or len(set(required_keys)) != len(required_keys):
        return _cannot_verify(plan, "The recheck plan contains an empty or ambiguous evidence population.")

    declared_population_count = _declared_population_count(plan)
    if (
        declared_population_count is None
        or declared_population_count != len(expected_keys)
        or len(required_keys) != len(expected_keys)
        or set(required_keys) != set(expected_keys)
    ):
        return _cannot_verify(plan, "The recheck plan does not exactly match the complete historical evidence population.")

    for item in requests:
        declared_key = _clean(item.get("evidence_key"))
        derived_key = key_for(item.get("url")) if item.get("url") else ""
        if not derived_key or derived_key != declared_key:
            return _cannot_verify(plan, "A recheck request URL does not match its declared evidence identity.")
        if _clean(item.get("criterion_id")) != _clean(plan.get("criterion_id")) or _clean(item.get("rule")) != _clean(plan.get("rule")):
            return _cannot_verify(plan, "A recheck request does not match the plan criterion/rule identity.")
        if item.get("required_observations") != list(REQUIRED_RECHECK_OBSERVATIONS):
            return _cannot_verify(plan, "A recheck request does not carry the complete required observation contract.")

    page_index: dict[str, dict[str, Any]] = {}
    duplicate_page_keys: set[str] = set()
    for page in current_pages or []:
        key = _page_evidence_key(page, key_for)
        if not key:
            continue
        if key in page_index:
            duplicate_page_keys.add(key)
        else:
            page_index[key] = page

    evaluation_index: dict[str, dict[str, Any]] = {}
    duplicate_evaluation_keys: set[str] = set()
    invalid_evaluations: list[dict[str, str]] = []
    for row in rule_evaluations or []:
        key, error = _evaluation_evidence_key(row, key_for)
        if error:
            invalid_evaluations.append({"evidence_key": key, "reason": error})
            continue
        if key in evaluation_index:
            duplicate_evaluation_keys.add(key)
        else:
            evaluation_index[key] = row

    observed_count = 0
    evaluated_count = 0
    resolved_scope: list[str] = []
    unresolved_scope: list[str] = []
    unverifiable_scope: list[dict[str, str]] = list(invalid_evaluations)

    for key in required_keys:
        if key in duplicate_page_keys:
            unverifiable_scope.append({"evidence_key": key, "reason": "ambiguous_duplicate_page_evidence"})
            continue
        page = page_index.get(key)
        if not page:
            unverifiable_scope.append({"evidence_key": key, "reason": "required_page_not_observed"})
            continue
        observed_count += 1

        eligibility_state, eligibility_reason = verification_eligibility(previous_fix, page)
        if eligibility_state != "eligible":
            unverifiable_scope.append({"evidence_key": key, "reason": f"{eligibility_state}: {eligibility_reason}"})
            continue

        if key in duplicate_evaluation_keys:
            unverifiable_scope.append({"evidence_key": key, "reason": "ambiguous_duplicate_rule_evaluation"})
            continue
        row = evaluation_index.get(key)
        if not isinstance(row, dict):
            unverifiable_scope.append({"evidence_key": key, "reason": "rule_predicate_not_re_evaluated"})
            continue
        if _clean(row.get("criterion_id")) != _clean(plan.get("criterion_id")):
            unverifiable_scope.append({"evidence_key": key, "reason": "acceptance_criterion_identity_mismatch"})
            continue
        if _clean(row.get("repair_fingerprint")) != fingerprint:
            unverifiable_scope.append({"evidence_key": key, "reason": "repair_identity_mismatch"})
            continue
        if not all(_clean(row.get(field)) == expected for field, expected in expected_versions.items()):
            unverifiable_scope.append({"evidence_key": key, "reason": "rule_evaluation_version_mismatch"})
            continue
        if row.get("evaluated") is not True:
            unverifiable_scope.append({"evidence_key": key, "reason": "rule_predicate_not_re_evaluated"})
            continue
        detected = row.get("defect_detected")
        if not isinstance(detected, bool):
            unverifiable_scope.append({"evidence_key": key, "reason": "rule_predicate_result_missing_or_ambiguous"})
            continue

        evaluated_count += 1
        (unresolved_scope if detected else resolved_scope).append(key)

    if unverifiable_scope:
        return _cannot_verify(
            plan,
            "One or more required evidence members could not be re-observed and re-evaluated comparably.",
            unverifiable_scope=unverifiable_scope,
            observed_count=observed_count,
            evaluated_count=evaluated_count,
            resolved_scope=resolved_scope,
            unresolved_scope=unresolved_scope,
        )

    result = _result_base(plan)
    result.update({
        "observed_population_count": observed_count,
        "evaluated_population_count": evaluated_count,
        "resolved_scope": resolved_scope,
        "unresolved_scope": unresolved_scope,
        "unverifiable_scope": [],
    })
    if unresolved_scope and resolved_scope:
        result.update({"state": PARTIAL, "reason": "The repair predicate remains detected for the exact unresolved scope."})
    elif unresolved_scope:
        result.update({"state": FAIL, "reason": "The repair predicate remains detected across the comparable rechecked population."})
    else:
        result.update({"state": PASS, "reason": "Every required evidence member was re-observed comparably and the versioned repair predicate was explicitly re-evaluated as no longer detected."})
    return result


def verified_fixed_transition_allowed(result: dict[str, Any], legacy_comparison: dict[str, Any]) -> bool:
    """Require both NextGen PASS and the existing verified_fixed gate."""
    return bool(
        isinstance(result, dict)
        and result.get("version") == VERIFICATION_RESULT_VERSION
        and result.get("state") == PASS
        and isinstance(legacy_comparison, dict)
        and legacy_comparison.get("state") == "verified_fixed"
    )


def regression_reopen_decision(previous_record: dict[str, Any], current_result: dict[str, Any]) -> dict[str, Any]:
    """Return a pure-data reopen decision; never mutates workflow/persistence."""
    previous_record = previous_record if isinstance(previous_record, dict) else {}
    current_result = current_result if isinstance(current_result, dict) else {}
    current_fingerprint = _clean(current_result.get("repair_fingerprint"))
    previous_fingerprint = _clean(previous_record.get("repair_fingerprint"))
    if not previous_fingerprint:
        identity = build_repair_identity(previous_record)
        previous_fingerprint = _clean(identity.get("fingerprint")) if identity.get("stable") else ""

    previous_state = _clean(
        previous_record.get("state")
        or previous_record.get("verification_state")
        or previous_record.get("repair_verification_state")
        or previous_record.get("status")
    )
    current_state = _clean(current_result.get("state")).upper()
    previously_resolved = previous_state.upper() == PASS or previous_state.lower() in {"verified_fixed", "fixed", "resolved"}

    should_reopen = False
    reason = "no_regression_reopen"
    if current_result.get("version") != VERIFICATION_RESULT_VERSION:
        reason = "unsupported_current_verification_result"
    elif not previous_fingerprint or not current_fingerprint or previous_fingerprint != current_fingerprint:
        reason = "repair_identity_missing_or_changed"
    elif not previously_resolved:
        reason = "previous_repair_was_not_verified_resolved"
    elif current_state in {FAIL, PARTIAL}:
        should_reopen = True
        reason = "verified_repair_regressed"
    elif current_state == COULD_NOT_VERIFY:
        reason = "regression_not_proven"
    elif current_state == PASS:
        reason = "repair_remains_verified"
    else:
        reason = "unknown_current_verification_state"

    return {
        "version": REGRESSION_REOPEN_VERSION,
        "should_reopen": should_reopen,
        "reason": reason,
        "repair_fingerprint": current_fingerprint or previous_fingerprint,
        "reopen_scope": list(current_result.get("unresolved_scope") or []) if should_reopen else [],
        "source_verification_state": previous_state,
        "current_verification_state": current_state,
    }
