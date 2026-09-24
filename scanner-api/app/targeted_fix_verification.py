from __future__ import annotations

import hashlib
import json
from typing import Any
from urllib.parse import urlsplit

from .coverage_probes import COVERAGE_PROBE_SCHEDULER_VERSION, coverage_probe_request_limit
from .missing_h1_comparison_contract import (
    MISSING_H1_COMPARISON_PROFILE_VERSION,
    MISSING_H1_REMEDIATION_FAMILY,
    MISSING_H1_REPAIR_SURFACE,
    MISSING_H1_RULE,
    MISSING_H1_RULE_DEFINITION_VERSION,
)
from .repair_coverage import PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION, published_evidence_url_key
from .repair_identity import (
    REPAIR_IDENTITY_VERSION,
    REPAIR_VERIFICATION_VERSION,
    build_repair_identity,
    compare_repair_runs,
)

TARGETED_FIX_VERIFICATION_CRITERIA_VERSION = "targeted_fix_verification_criteria_v2_missing_h1_capability"
TARGETED_FIX_VERIFICATION_PLAN_VERSION = "targeted_fix_verification_plan_v1_sealed_repair_scope"
TARGETED_FIX_VERIFICATION_OBSERVATION_VERSION = "targeted_fix_verification_observation_v1_plan_bound"
TARGETED_FIX_VERIFICATION_RULE_RECEIPT_VERSION = "targeted_fix_verification_rule_receipt_v1_complete_population"
TARGETED_FIX_VERIFICATION_RESULT_VERSION = "targeted_fix_verification_result_v1_compare_repair_runs"
TARGETED_FIX_VERIFICATION_BUDGET_VERSION = "targeted_fix_verification_budget_v1_shared_scheduler"
TARGETED_FIX_VERIFICATION_PURPOSE = "targeted_fix_verification"

VERIFICATION_STATES = frozenset({"PASS", "PARTIAL", "FAIL", "COULD_NOT_VERIFY"})
MAX_TARGETED_RECHECK_URLS = coverage_probe_request_limit("advanced")

_NOT_VERIFIED_REASONS = frozenset(
    {
        "robots_denied",
        "challenge",
        "rate_limited",
        "timeout",
        "deadline_exhausted",
        "request_budget_exhausted",
        "shared_request_budget_exhausted",
        "request_failed",
        "blocked",
        "fetch_failed",
        "dns_failed",
        "redirect_unverified",
        "body_limit_exceeded",
    }
)


def _exact_string(value: Any) -> str:
    return value if isinstance(value, str) and value and value == value.strip() else ""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _fingerprint(value: Any) -> str:
    try:
        payload = _canonical_json(value)
    except (TypeError, ValueError):
        return ""
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _origin_root(value: str) -> str:
    root = published_evidence_url_key("/", scan_origin=value)
    return root[:-1] if root.endswith("/") else ""


def _key_origin(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except Exception:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def _raw_affected_urls(repair: dict[str, Any]) -> list[Any]:
    affected = repair.get("affected_pages")
    if isinstance(affected, list) and affected:
        return list(affected)
    fallback = repair.get("page_url") or repair.get("representative_page_url")
    return [fallback] if fallback else []


def _sealed_evidence_keys(repair: dict[str, Any], *, scan_origin: str) -> tuple[list[str], list[str]]:
    blockers: list[str] = []
    origin = _origin_root(scan_origin)
    if not origin:
        return [], ["invalid_source_scan_origin"]

    raw_urls = _raw_affected_urls(repair)
    if not raw_urls:
        return [], ["sealed_repair_has_no_affected_urls"]

    keys: list[str] = []
    seen: set[str] = set()
    for raw in raw_urls:
        key = published_evidence_url_key(raw, scan_origin=origin)
        if not key:
            blockers.append("sealed_repair_url_identity_unresolved")
            continue
        if _key_origin(key) != origin:
            blockers.append("sealed_repair_url_outside_source_origin")
            continue
        if key not in seen:
            seen.add(key)
            keys.append(key)

    if blockers:
        return [], sorted(set(blockers))
    return sorted(keys), []


def build_verification_criteria(
    sealed_repair: dict[str, Any],
    *,
    source_scan_id: str,
    source_scan_origin: str,
) -> dict[str, Any]:
    """Build the versioned acceptance contract for one already-authority-verified repair.

    This helper does not verify or create an authority seal. The serialized integrator
    must call it only after the existing authority reader has verified the source scan
    and selected repair. The output binds that upstream selection to stable technical
    repair identity, exact comparison versions, and the complete sealed affected-URL set.
    """
    blockers: list[str] = []
    exact_scan_id = _exact_string(source_scan_id)
    if not exact_scan_id:
        blockers.append("invalid_source_scan_id")

    if not isinstance(sealed_repair, dict):
        sealed_repair = {}
        blockers.append("invalid_sealed_repair")

    identity = build_repair_identity(sealed_repair)
    if not identity.get("stable") or identity.get("state") != "stable" or not identity.get("fingerprint"):
        blockers.append("stable_repair_identity_required")

    persisted_fingerprint = sealed_repair.get("repair_fingerprint")
    if persisted_fingerprint is not None:
        persisted_exact = _exact_string(persisted_fingerprint)
        if not persisted_exact or persisted_exact != identity.get("fingerprint"):
            blockers.append("repair_fingerprint_conflicts_with_stable_identity")

    persisted_identity_state = sealed_repair.get("repair_identity_state")
    if persisted_identity_state is not None and persisted_identity_state != "stable":
        blockers.append("repair_identity_state_not_stable")
    persisted_identity_stable = sealed_repair.get("repair_identity_stable")
    if persisted_identity_stable is not None and persisted_identity_stable is not True:
        blockers.append("repair_identity_stable_flag_not_true")

    rule_version = _exact_string(sealed_repair.get("rule_definition_version"))
    comparison_version = _exact_string(sealed_repair.get("comparison_profile_version"))
    evidence_version = _exact_string(sealed_repair.get("evidence_url_identity_version"))
    if not rule_version:
        blockers.append("rule_definition_version_required")
    if not comparison_version:
        blockers.append("comparison_profile_version_required")
    if evidence_version != PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION:
        blockers.append("published_evidence_url_identity_required")

    capability_matches = (
        identity.get("rule") == MISSING_H1_RULE
        and identity.get("repair_surface") == MISSING_H1_REPAIR_SURFACE
        and identity.get("remediation_family") == MISSING_H1_REMEDIATION_FAMILY
        and rule_version == MISSING_H1_RULE_DEFINITION_VERSION
        and comparison_version == MISSING_H1_COMPARISON_PROFILE_VERSION
        and evidence_version == PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION
    )
    if not capability_matches:
        blockers.append("unsupported_targeted_verification_capability")

    origin = _origin_root(source_scan_origin)
    if not origin:
        blockers.append("invalid_source_scan_origin")
        evidence_keys: list[str] = []
    elif evidence_version == PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION:
        evidence_keys, url_blockers = _sealed_evidence_keys(sealed_repair, scan_origin=origin)
        blockers.extend(url_blockers)
    else:
        evidence_keys = []

    blockers = sorted(set(blockers))
    base = {
        "version": TARGETED_FIX_VERIFICATION_CRITERIA_VERSION,
        "state": "ready" if not blockers else "could_not_verify",
        "source_scan_id": exact_scan_id,
        "source_scan_origin": origin,
        "repair_identity_version": REPAIR_IDENTITY_VERSION,
        "repair_verification_version": REPAIR_VERIFICATION_VERSION,
        "repair_fingerprint": identity.get("fingerprint") if identity.get("stable") else "",
        "rule_definition_version": rule_version,
        "comparison_profile_version": comparison_version,
        "evidence_url_identity_version": evidence_version,
        "affected_evidence_keys": evidence_keys,
        "affected_url_count": len(evidence_keys),
        "acceptance": {
            "PASS": "every sealed URL re-observed and compare_repair_runs returns verified_fixed for every URL",
            "PARTIAL": "every sealed URL comparable and per-URL comparator results contain both verified_fixed and still_detected/came_back",
            "FAIL": "every sealed URL comparable and compare_repair_runs returns still_detected/came_back for every URL",
            "COULD_NOT_VERIFY": "any missing, unsafe, incomparable, version-mismatched, identity-ambiguous, budget-exhausted, or unobserved evidence",
        },
        "blockers": blockers,
    }
    base["criteria_fingerprint"] = _fingerprint(base)
    if not base["criteria_fingerprint"]:
        base["state"] = "could_not_verify"
        base["blockers"] = sorted(set([*base["blockers"], "criteria_transport_not_serializable"]))
    return base


def _resolve_requested_urls(requested_urls: Any, *, origin: str) -> tuple[list[str], list[str]]:
    if requested_urls is None:
        return [], []
    if not isinstance(requested_urls, list):
        return [], ["requested_urls_must_be_a_list"]
    resolved: list[str] = []
    seen: set[str] = set()
    blockers: list[str] = []
    for raw in requested_urls:
        key = published_evidence_url_key(raw, scan_origin=origin)
        if not key:
            blockers.append("requested_url_identity_unresolved")
            continue
        if _key_origin(key) != origin:
            blockers.append("requested_url_expands_source_origin")
            continue
        if key in seen:
            blockers.append("duplicate_requested_url")
            continue
        seen.add(key)
        resolved.append(key)
    return sorted(resolved), sorted(set(blockers))


def _plan_fingerprint_material(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": plan.get("version"),
        "criteria_version": plan.get("criteria_version"),
        "criteria_fingerprint": plan.get("criteria_fingerprint"),
        "source_scan_id": plan.get("source_scan_id"),
        "source_scan_origin": plan.get("source_scan_origin"),
        "repair_fingerprint": plan.get("repair_fingerprint"),
        "evidence_url_identity_version": plan.get("evidence_url_identity_version"),
        "population_complete": plan.get("population_complete"),
        "sealed_population_count": plan.get("sealed_population_count"),
        "selected_population_count": plan.get("selected_population_count"),
        "requests": plan.get("requests"),
    }


def build_targeted_recheck_plan(
    sealed_repair: dict[str, Any],
    *,
    source_scan_id: str,
    source_scan_origin: str,
    requested_urls: list[str] | None = None,
    max_urls: int = MAX_TARGETED_RECHECK_URLS,
) -> dict[str, Any]:
    """Build a bounded, same-origin recheck plan that can never expand repair scope."""
    criteria = build_verification_criteria(
        sealed_repair,
        source_scan_id=source_scan_id,
        source_scan_origin=source_scan_origin,
    )
    blockers = list(criteria.get("blockers") or [])
    sealed = list(criteria.get("affected_evidence_keys") or [])

    if isinstance(max_urls, bool) or not isinstance(max_urls, int) or max_urls <= 0:
        effective_limit = 0
        blockers.append("invalid_targeted_recheck_limit")
    else:
        effective_limit = min(max_urls, MAX_TARGETED_RECHECK_URLS)

    if requested_urls is None:
        selected = list(sealed)
        selection_requested = False
    else:
        selected, request_blockers = _resolve_requested_urls(
            requested_urls,
            origin=str(criteria.get("source_scan_origin") or ""),
        )
        blockers.extend(request_blockers)
        selection_requested = True
        outside = sorted(set(selected) - set(sealed))
        if outside:
            blockers.append("requested_url_outside_sealed_repair_set")

    # Any abuse/identity blocker invalidates the entire request. Never salvage the
    # in-scope subset of a request that also attempted scope expansion.
    hard_rejection = any(
        blocker
        in {
            "requested_urls_must_be_a_list",
            "requested_url_identity_unresolved",
            "requested_url_expands_source_origin",
            "duplicate_requested_url",
            "requested_url_outside_sealed_repair_set",
        }
        for blocker in blockers
    )
    if hard_rejection:
        selected = []

    population_complete = bool(sealed) and set(selected) == set(sealed) and len(selected) == len(sealed)
    if not selection_requested and len(sealed) > effective_limit:
        # Do not auto-truncate a repair and then create a path to a false PASS.
        selected = []
        population_complete = False
        blockers.append("sealed_repair_population_exceeds_targeted_bound")
    elif len(selected) > effective_limit:
        selected = []
        population_complete = False
        blockers.append("requested_population_exceeds_targeted_bound")

    if selection_requested and selected and not population_complete:
        blockers.append("selected_population_is_not_complete_repair_set")

    requests = [
        {
            "purpose": TARGETED_FIX_VERIFICATION_PURPOSE,
            "evidence_key": key,
            "url": key,
            "repair_fingerprint": criteria.get("repair_fingerprint", ""),
            "rule_definition_version": criteria.get("rule_definition_version", ""),
            "comparison_profile_version": criteria.get("comparison_profile_version", ""),
            "evidence_url_identity_version": criteria.get("evidence_url_identity_version", ""),
        }
        for key in selected
    ]

    blockers = sorted(set(blockers))
    authoritative_ready = (
        criteria.get("state") == "ready"
        and not blockers
        and population_complete
        and 0 < len(requests) <= effective_limit
    )
    plan = {
        "version": TARGETED_FIX_VERIFICATION_PLAN_VERSION,
        "state": "ready" if authoritative_ready else ("rejected" if hard_rejection else "could_not_verify"),
        "criteria_version": criteria.get("version"),
        "criteria_fingerprint": criteria.get("criteria_fingerprint"),
        "source_scan_id": criteria.get("source_scan_id"),
        "source_scan_origin": criteria.get("source_scan_origin"),
        "repair_identity_version": criteria.get("repair_identity_version"),
        "repair_verification_version": criteria.get("repair_verification_version"),
        "repair_fingerprint": criteria.get("repair_fingerprint"),
        "rule_definition_version": criteria.get("rule_definition_version"),
        "comparison_profile_version": criteria.get("comparison_profile_version"),
        "evidence_url_identity_version": criteria.get("evidence_url_identity_version"),
        "sealed_population_count": len(sealed),
        "selected_population_count": len(selected),
        "population_complete": population_complete,
        "max_targeted_urls": effective_limit,
        "requests": requests,
        "shared_scheduler": {
            "version": COVERAGE_PROBE_SCHEDULER_VERSION,
            "purpose": TARGETED_FIX_VERIFICATION_PURPOSE,
            "worst_case_new_requests": len(requests),
            "must_share_existing_request_limit": True,
            "cache_reuse_may_reduce_actual_requests": True,
        },
        "blockers": blockers,
    }
    plan["plan_fingerprint"] = _fingerprint(_plan_fingerprint_material(plan))
    if not plan["plan_fingerprint"]:
        plan["state"] = "could_not_verify"
        plan["blockers"] = sorted(set([*plan["blockers"], "plan_transport_not_serializable"]))
    return plan


def targeted_verification_budget_proposal(
    plan: dict[str, Any],
    scheduler_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    """Check worst-case request fit against the existing shared scheduler summary.

    This is planning only. The shared scheduler remains authoritative and spends a
    permit before I/O, so an actual timeout/failure still consumes its real request.
    """
    required = len(plan.get("requests") or []) if isinstance(plan, dict) else 0
    base = {
        "version": TARGETED_FIX_VERIFICATION_BUDGET_VERSION,
        "shared_scheduler_version": COVERAGE_PROBE_SCHEDULER_VERSION,
        "required_new_request_upper_bound": required,
        "state": "could_not_verify",
        "reason": "scheduler_summary_unavailable",
        "requests_remaining": 0,
    }
    if not isinstance(plan, dict) or plan.get("version") != TARGETED_FIX_VERIFICATION_PLAN_VERSION or plan.get("state") != "ready":
        return {**base, "reason": "verification_plan_not_ready"}
    if not isinstance(scheduler_summary, dict) or scheduler_summary.get("version") != COVERAGE_PROBE_SCHEDULER_VERSION:
        return {**base, "reason": "shared_scheduler_version_mismatch"}
    budget = scheduler_summary.get("request_budget")
    if not isinstance(budget, dict):
        return {**base, "reason": "shared_scheduler_budget_missing"}
    remaining = budget.get("requests_remaining")
    if isinstance(remaining, bool) or not isinstance(remaining, int) or remaining < 0:
        return {**base, "reason": "shared_scheduler_remaining_budget_invalid"}
    if budget.get("deadline_exhausted") is True:
        return {**base, "reason": "deadline_exhausted", "requests_remaining": remaining}
    if budget.get("budget_exhausted") is True or remaining < required:
        return {**base, "reason": "shared_request_budget_insufficient", "requests_remaining": remaining}
    return {
        **base,
        "state": "fits",
        "reason": "worst_case_targeted_requests_fit_shared_scheduler",
        "requests_remaining": remaining,
    }


def build_rule_evaluation_receipt(
    plan: dict[str, Any],
    current_fixes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Bind deterministic rule output to the exact complete targeted population."""
    requests = plan.get("requests") if isinstance(plan, dict) else []
    evidence_keys = sorted(
        str(row.get("evidence_key"))
        for row in requests
        if isinstance(row, dict) and isinstance(row.get("evidence_key"), str)
    )
    fixes_fingerprint = _fingerprint(current_fixes)
    population_complete = bool(
        evidence_keys
        and isinstance(plan, dict)
        and plan.get("population_complete") is True
        and fixes_fingerprint
    )
    return {
        "version": TARGETED_FIX_VERIFICATION_RULE_RECEIPT_VERSION,
        "state": "ready" if population_complete else "could_not_verify",
        "plan_fingerprint": plan.get("plan_fingerprint") if isinstance(plan, dict) else "",
        "repair_fingerprint": plan.get("repair_fingerprint") if isinstance(plan, dict) else "",
        "rule_definition_version": plan.get("rule_definition_version") if isinstance(plan, dict) else "",
        "comparison_profile_version": plan.get("comparison_profile_version") if isinstance(plan, dict) else "",
        "evidence_url_identity_version": plan.get("evidence_url_identity_version") if isinstance(plan, dict) else "",
        "population_complete": population_complete,
        "evaluated_evidence_keys": evidence_keys,
        "current_fixes_fingerprint": fixes_fingerprint,
    }


def _could_not_verify(plan: Any, reason: str, **extra: Any) -> dict[str, Any]:
    return {
        "version": TARGETED_FIX_VERIFICATION_RESULT_VERSION,
        "state": "COULD_NOT_VERIFY",
        "reason": reason,
        "repair_fingerprint": plan.get("repair_fingerprint", "") if isinstance(plan, dict) else "",
        "plan_fingerprint": plan.get("plan_fingerprint", "") if isinstance(plan, dict) else "",
        "reopen_regression": False,
        "page_results": [],
        **extra,
    }


def _validate_plan_against_repair(
    plan: dict[str, Any],
    sealed_repair: dict[str, Any],
) -> str:
    if plan.get("version") != TARGETED_FIX_VERIFICATION_PLAN_VERSION or plan.get("state") != "ready":
        return "verification_plan_not_ready"
    if plan.get("population_complete") is not True:
        return "verification_plan_population_incomplete"
    if plan.get("repair_identity_version") != REPAIR_IDENTITY_VERSION:
        return "repair_identity_version_mismatch"
    if plan.get("repair_verification_version") != REPAIR_VERIFICATION_VERSION:
        return "repair_comparator_version_mismatch"
    if plan.get("evidence_url_identity_version") != PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION:
        return "evidence_url_identity_version_mismatch"
    if not plan.get("plan_fingerprint") or plan.get("plan_fingerprint") != _fingerprint(_plan_fingerprint_material(plan)):
        return "verification_plan_fingerprint_mismatch"

    criteria = build_verification_criteria(
        sealed_repair,
        source_scan_id=plan.get("source_scan_id"),
        source_scan_origin=plan.get("source_scan_origin"),
    )
    if criteria.get("state") != "ready":
        return "sealed_repair_no_longer_meets_verification_criteria"
    if criteria.get("criteria_fingerprint") != plan.get("criteria_fingerprint"):
        return "verification_criteria_fingerprint_mismatch"
    expected = list(criteria.get("affected_evidence_keys") or [])
    actual = [
        row.get("evidence_key")
        for row in plan.get("requests") or []
        if isinstance(row, dict)
    ]
    if actual != expected or len(actual) != len(set(actual)):
        return "verification_plan_scope_mismatch"
    return ""


def _matching_current_fix_keys(
    sealed_fingerprint: str,
    current_fixes: list[dict[str, Any]],
    *,
    current_origin: str,
) -> tuple[dict[str, list[dict[str, Any]]], str]:
    by_key: dict[str, list[dict[str, Any]]] = {}
    for fix in current_fixes:
        if not isinstance(fix, dict):
            return {}, "current_fix_transport_invalid"
        identity = build_repair_identity(fix)
        computed_matches = bool(
            identity.get("stable") and identity.get("fingerprint") == sealed_fingerprint
        )
        persisted = fix.get("repair_fingerprint")
        persisted_exact = _exact_string(persisted) if persisted is not None else ""
        persisted_claims_match = bool(persisted is not None and persisted_exact == sealed_fingerprint)

        # Unrelated rows must not poison targeted verification merely because their
        # own persistence identity is provisional or uses a different contract.
        # Ambiguity matters only when either identity source claims this repair.
        if persisted_claims_match and not computed_matches:
            return {}, "current_fix_identity_conflict"
        if computed_matches and persisted is not None and persisted_exact != sealed_fingerprint:
            return {}, "current_fix_identity_conflict"
        if not computed_matches:
            continue
        raw_urls = _raw_affected_urls(fix)
        if not raw_urls:
            return {}, "matching_current_fix_scope_missing"
        resolved: set[str] = set()
        for raw in raw_urls:
            key = published_evidence_url_key(raw, scan_origin=current_origin)
            if not key or _key_origin(key) != current_origin:
                return {}, "matching_current_fix_scope_ambiguous"
            resolved.add(key)
        for key in resolved:
            by_key.setdefault(key, []).append(fix)
    return by_key, ""


def evaluate_targeted_fix_verification(
    plan: dict[str, Any],
    sealed_repair: dict[str, Any],
    *,
    current_scan_origin: str,
    current_contract: dict[str, Any] | None,
    recheck_outcomes: list[dict[str, Any]],
    current_fixes: list[dict[str, Any]],
    rule_evaluation_receipt: dict[str, Any] | None,
) -> dict[str, Any]:
    """Evaluate H1-4 using per-URL calls to the canonical repair comparator.

    The only aggregation introduced here is repair-level PASS/PARTIAL/FAIL over
    canonical comparator results. Any unknown/ineligible/missing input collapses
    the whole repair result to COULD_NOT_VERIFY.
    """
    if not isinstance(plan, dict) or not isinstance(sealed_repair, dict):
        return _could_not_verify(plan, "invalid_verification_inputs")

    plan_error = _validate_plan_against_repair(plan, sealed_repair)
    if plan_error:
        return _could_not_verify(plan, plan_error)

    current_origin = _origin_root(current_scan_origin)
    if not current_origin or current_origin != plan.get("source_scan_origin"):
        return _could_not_verify(plan, "current_scan_origin_mismatch")

    if not isinstance(current_contract, dict):
        return _could_not_verify(plan, "current_comparison_contract_missing")
    exact_contract = {
        "rule_definition_version": _exact_string(current_contract.get("rule_definition_version")),
        "comparison_profile_version": _exact_string(current_contract.get("comparison_profile_version")),
        "evidence_url_identity_version": _exact_string(current_contract.get("evidence_url_identity_version")),
    }
    if (
        exact_contract["rule_definition_version"] != plan.get("rule_definition_version")
        or exact_contract["comparison_profile_version"] != plan.get("comparison_profile_version")
        or exact_contract["evidence_url_identity_version"] != plan.get("evidence_url_identity_version")
    ):
        return _could_not_verify(plan, "current_comparison_contract_mismatch")

    if not isinstance(current_fixes, list):
        return _could_not_verify(plan, "current_fix_population_invalid")
    current_fixes_fingerprint = _fingerprint(current_fixes)
    if not current_fixes_fingerprint:
        return _could_not_verify(plan, "current_fix_population_transport_not_serializable")
    if not isinstance(rule_evaluation_receipt, dict):
        return _could_not_verify(plan, "rule_evaluation_receipt_missing")
    expected_keys = [row.get("evidence_key") for row in plan.get("requests") or []]
    expected_receipt = {
        "version": TARGETED_FIX_VERIFICATION_RULE_RECEIPT_VERSION,
        "state": "ready",
        "plan_fingerprint": plan.get("plan_fingerprint"),
        "repair_fingerprint": plan.get("repair_fingerprint"),
        "rule_definition_version": plan.get("rule_definition_version"),
        "comparison_profile_version": plan.get("comparison_profile_version"),
        "evidence_url_identity_version": plan.get("evidence_url_identity_version"),
        "population_complete": True,
        "evaluated_evidence_keys": sorted(expected_keys),
        "current_fixes_fingerprint": current_fixes_fingerprint,
    }
    for key, value in expected_receipt.items():
        if rule_evaluation_receipt.get(key) != value:
            return _could_not_verify(plan, f"rule_evaluation_receipt_{key}_mismatch")

    if not isinstance(recheck_outcomes, list):
        return _could_not_verify(plan, "recheck_outcomes_invalid")
    outcome_by_key: dict[str, dict[str, Any]] = {}
    for outcome in recheck_outcomes:
        if not isinstance(outcome, dict):
            return _could_not_verify(plan, "recheck_outcome_transport_invalid")
        if outcome.get("version") != TARGETED_FIX_VERIFICATION_OBSERVATION_VERSION:
            return _could_not_verify(plan, "recheck_outcome_version_mismatch")
        if outcome.get("plan_fingerprint") != plan.get("plan_fingerprint"):
            return _could_not_verify(plan, "recheck_outcome_plan_mismatch")
        key = outcome.get("evidence_key")
        if key not in expected_keys:
            return _could_not_verify(plan, "recheck_outcome_outside_planned_scope")
        if key in outcome_by_key:
            return _could_not_verify(plan, "duplicate_recheck_outcome")
        outcome_by_key[key] = outcome
    if set(outcome_by_key) != set(expected_keys):
        return _could_not_verify(plan, "one_or_more_planned_urls_were_not_observed")

    pages_by_key: dict[str, dict[str, Any]] = {}
    for key in expected_keys:
        outcome = outcome_by_key[key]
        state = outcome.get("state")
        if state == "not_verified":
            reason = _exact_string(outcome.get("reason")) or "recheck_not_verified"
            return _could_not_verify(
                plan,
                reason if reason in _NOT_VERIFIED_REASONS else "recheck_not_verified",
                blocked_evidence_key=key,
                blocked_reason=reason,
            )
        if state != "observed":
            return _could_not_verify(plan, "recheck_outcome_state_invalid", blocked_evidence_key=key)
        page = outcome.get("page")
        if not isinstance(page, dict):
            return _could_not_verify(plan, "observed_page_evidence_missing", blocked_evidence_key=key)
        page_url = page.get("url") or page.get("final_url") or page.get("page_url") or page.get("path")
        observed_key = published_evidence_url_key(page_url, scan_origin=current_origin)
        if not observed_key or observed_key != key:
            return _could_not_verify(plan, "observed_page_identity_mismatch", blocked_evidence_key=key)
        pages_by_key[key] = page

    matching_by_key, fix_error = _matching_current_fix_keys(
        str(plan.get("repair_fingerprint") or ""),
        current_fixes,
        current_origin=current_origin,
    )
    if fix_error:
        return _could_not_verify(plan, fix_error)
    if set(matching_by_key) - set(expected_keys):
        return _could_not_verify(plan, "matching_current_fix_expands_sealed_repair_scope")

    page_results: list[dict[str, Any]] = []
    known_states: list[str] = []
    reopen_keys: list[str] = []
    for key in expected_keys:
        previous_for_key = {**sealed_repair, "affected_pages": [key]}
        comparison = compare_repair_runs(
            previous_for_key,
            matching_by_key.get(key, []),
            [pages_by_key[key]],
            current_contract=exact_contract,
            previous_scan_origin=str(plan.get("source_scan_origin") or ""),
            scan_origin=current_origin,
        )
        comparator_state = comparison.get("state")
        if comparator_state == "verified_fixed":
            state = "PASS"
        elif comparator_state in {"still_detected", "came_back"}:
            state = "FAIL"
            if comparator_state == "came_back":
                reopen_keys.append(key)
        else:
            return _could_not_verify(
                plan,
                "canonical_comparator_could_not_verify",
                blocked_evidence_key=key,
                comparator_result=comparison,
                page_results=page_results,
            )
        known_states.append(state)
        page_results.append(
            {
                "evidence_key": key,
                "state": state,
                "comparator_state": comparator_state,
                "comparator_version": comparison.get("version"),
                "reason": comparison.get("reason", ""),
            }
        )

    if not known_states:
        return _could_not_verify(plan, "verification_population_empty")
    if all(state == "PASS" for state in known_states):
        overall = "PASS"
        reason = "all_sealed_urls_verified_fixed_by_canonical_comparator"
    elif all(state == "FAIL" for state in known_states):
        overall = "FAIL"
        reason = "repair_still_detected_on_all_sealed_urls"
    else:
        overall = "PARTIAL"
        reason = "repair_fixed_on_some_sealed_urls_and_still_detected_on_others"

    result = {
        "version": TARGETED_FIX_VERIFICATION_RESULT_VERSION,
        "state": overall,
        "reason": reason,
        "repair_fingerprint": plan.get("repair_fingerprint"),
        "plan_fingerprint": plan.get("plan_fingerprint"),
        "verified_url_count": sum(1 for state in known_states if state == "PASS"),
        "failed_url_count": sum(1 for state in known_states if state == "FAIL"),
        "total_url_count": len(known_states),
        "reopen_regression": bool(reopen_keys),
        "regression_evidence_keys": reopen_keys,
        "page_results": page_results,
    }
    assert result["state"] in VERIFICATION_STATES
    return result
