from __future__ import annotations

from typing import Any

from .nextgen_fix_verification import (
    COULD_NOT_VERIFY,
    FAIL,
    PARTIAL,
    PASS,
    REGRESSION_REOPEN_VERSION,
    VERIFICATION_RESULT_VERSION,
    VERIFICATION_STATES,
    build_acceptance_criterion,
)
from .repair_coverage import PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION, repair_evidence_key_function
from .repair_identity import build_repair_identity

VERIFICATION_RESULT_INTEGRITY_VERSION = "fix_verification_result_integrity_v1"
VERIFICATION_RESULT_BINDING_VERSION = "fix_verification_result_binding_v2_population_bound"
STRICT_REGRESSION_REOPEN_VERSION = "fix_regression_reopen_v4_population_bound"


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _strict_count(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _scope(value: Any) -> tuple[list[str], str]:
    if not isinstance(value, list):
        return [], "scope_not_a_list"
    cleaned = [_clean(item) for item in value]
    if any(not item for item in cleaned):
        return [], "scope_contains_empty_identity"
    if len(set(cleaned)) != len(cleaned):
        return [], "scope_contains_duplicate_identity"
    return cleaned, ""


def _historical_evidence_population(
    previous_record: dict[str, Any],
    *,
    previous_scan_origin: str = "",
) -> tuple[list[str], str]:
    """Rebuild the exact historical evidence-key population from trusted context.

    Result objects are transport data, so their population counts/scopes are not
    proof by themselves. Re-derive the historical evidence identities from the
    repair record using the caller-owned historical scan origin. Root-relative
    URLs therefore fail closed when that authoritative origin is unavailable.
    """
    previous_record = previous_record if isinstance(previous_record, dict) else {}
    identity_version = _clean(previous_record.get("evidence_url_identity_version"))
    if identity_version != PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION:
        return [], "historical_evidence_url_identity_version_unsupported"

    try:
        key_for = repair_evidence_key_function(
            scan_origin=previous_scan_origin,
            identity_version=identity_version,
        )
    except (TypeError, ValueError):
        return [], "historical_evidence_url_identity_context_invalid"

    values = previous_record.get("affected_pages") if isinstance(previous_record.get("affected_pages"), list) else []
    if not values:
        fallback = previous_record.get("page_url") or previous_record.get("representative_page_url")
        values = [fallback] if fallback else []
    if not values:
        return [], "historical_evidence_population_missing"

    population: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = key_for(value)
        if not key:
            return [], "historical_evidence_identity_ambiguous_or_unresolvable"
        if key not in seen:
            seen.add(key)
            population.append(key)
    if not population:
        return [], "historical_evidence_population_missing"
    return population, ""


def verification_result_integrity(result: dict[str, Any]) -> dict[str, Any]:
    """Validate whether a terminal result proves a complete comparable outcome.

    This helper treats result objects as untrusted pure data. It is intentionally
    stricter than display/read compatibility: PASS/PARTIAL/FAIL must demonstrate
    complete population accounting with no unverifiable evidence before they can
    participate in regression-reopen decisions. COULD_NOT_VERIFY is accepted as
    a terminal state but never upgraded into proof of resolution or regression.
    """
    if not isinstance(result, dict):
        return {
            "version": VERIFICATION_RESULT_INTEGRITY_VERSION,
            "valid": False,
            "reason": "verification_result_not_an_object",
            "effective_state": COULD_NOT_VERIFY,
        }
    reported_state = _clean(result.get("state")).upper()
    base = {
        "version": VERIFICATION_RESULT_INTEGRITY_VERSION,
        "reported_state": reported_state,
        "effective_state": reported_state if reported_state in VERIFICATION_STATES else COULD_NOT_VERIFY,
        "repair_fingerprint": _clean(result.get("repair_fingerprint")),
        "criterion_id": _clean(result.get("criterion_id")),
    }
    if result.get("version") != VERIFICATION_RESULT_VERSION:
        return {**base, "valid": False, "reason": "unsupported_verification_result_version", "effective_state": COULD_NOT_VERIFY}
    if reported_state not in VERIFICATION_STATES:
        return {**base, "valid": False, "reason": "unknown_verification_result_state", "effective_state": COULD_NOT_VERIFY}
    if not base["repair_fingerprint"] or not base["criterion_id"]:
        return {**base, "valid": False, "reason": "verification_result_identity_missing", "effective_state": COULD_NOT_VERIFY}

    if reported_state == COULD_NOT_VERIFY:
        return {**base, "valid": True, "reason": "could_not_verify_is_non_proving_terminal_state"}

    required = _strict_count(result.get("required_population_count"))
    observed = _strict_count(result.get("observed_population_count"))
    evaluated = _strict_count(result.get("evaluated_population_count"))
    if required is None or observed is None or evaluated is None or required <= 0:
        return {**base, "valid": False, "reason": "verification_population_counts_invalid", "effective_state": COULD_NOT_VERIFY}
    if observed != required or evaluated != required:
        return {**base, "valid": False, "reason": "verification_population_not_fully_observed_and_evaluated", "effective_state": COULD_NOT_VERIFY}

    resolved, resolved_error = _scope(result.get("resolved_scope"))
    unresolved, unresolved_error = _scope(result.get("unresolved_scope"))
    unverifiable = result.get("unverifiable_scope")
    if resolved_error or unresolved_error:
        return {**base, "valid": False, "reason": resolved_error or unresolved_error, "effective_state": COULD_NOT_VERIFY}
    if not isinstance(unverifiable, list):
        return {**base, "valid": False, "reason": "unverifiable_scope_not_a_list", "effective_state": COULD_NOT_VERIFY}
    if unverifiable:
        return {**base, "valid": False, "reason": "terminal_result_contains_unverifiable_evidence", "effective_state": COULD_NOT_VERIFY}
    if set(resolved) & set(unresolved):
        return {**base, "valid": False, "reason": "resolved_and_unresolved_scope_overlap", "effective_state": COULD_NOT_VERIFY}
    if len(resolved) + len(unresolved) != required:
        return {**base, "valid": False, "reason": "verification_scope_does_not_match_population", "effective_state": COULD_NOT_VERIFY}

    if reported_state == PASS and (unresolved or len(resolved) != required):
        return {**base, "valid": False, "reason": "pass_scope_inconsistent", "effective_state": COULD_NOT_VERIFY}
    if reported_state == FAIL and (resolved or len(unresolved) != required):
        return {**base, "valid": False, "reason": "fail_scope_inconsistent", "effective_state": COULD_NOT_VERIFY}
    if reported_state == PARTIAL and (not resolved or not unresolved):
        return {**base, "valid": False, "reason": "partial_scope_inconsistent", "effective_state": COULD_NOT_VERIFY}

    return {
        **base,
        "valid": True,
        "reason": "complete_comparable_terminal_result",
        "required_population_count": required,
    }


def verification_result_historical_binding(
    previous_record: dict[str, Any],
    current_result: dict[str, Any],
    *,
    previous_scan_origin: str = "",
) -> dict[str, Any]:
    """Bind a transported verification result to criterion and evidence population.

    Structural integrity is not enough: a well-shaped PASS/FAIL/PARTIAL can carry
    a foreign criterion, copied fingerprint, or fabricated subset/foreign scope.
    Recompute both the criterion and historical evidence-key population, then
    require the transported proving result to match them exactly.
    """
    previous_record = previous_record if isinstance(previous_record, dict) else {}
    current_result = current_result if isinstance(current_result, dict) else {}
    integrity = verification_result_integrity(current_result)
    base = {
        "version": VERIFICATION_RESULT_BINDING_VERSION,
        "valid": False,
        "reason": "verification_result_not_bound",
        "effective_state": _clean(integrity.get("effective_state")).upper() or COULD_NOT_VERIFY,
        "repair_fingerprint": "",
        "criterion_id": "",
        "result_integrity": integrity,
    }
    if not integrity.get("valid"):
        return {
            **base,
            "reason": f"result_integrity_invalid:{_clean(integrity.get('reason')) or 'invalid_verification_result'}",
            "effective_state": COULD_NOT_VERIFY,
        }

    expected = build_acceptance_criterion(previous_record)
    if expected.get("state") != "ready":
        return {**base, "reason": "historical_acceptance_criterion_not_ready", "effective_state": COULD_NOT_VERIFY}

    identity = build_repair_identity(previous_record)
    expected_fingerprint = _clean(expected.get("repair_fingerprint"))
    expected_identity_version = _clean(expected.get("repair_identity_version"))
    expected_criterion_id = _clean(expected.get("criterion_id"))
    base.update({
        "repair_fingerprint": expected_fingerprint,
        "criterion_id": expected_criterion_id,
    })
    if (
        not identity.get("stable")
        or not expected_fingerprint
        or _clean(identity.get("fingerprint")) != expected_fingerprint
        or _clean(identity.get("version")) != expected_identity_version
    ):
        return {**base, "reason": "historical_repair_identity_not_stable", "effective_state": COULD_NOT_VERIFY}

    stored_fingerprint = _clean(previous_record.get("repair_fingerprint"))
    if stored_fingerprint and stored_fingerprint != expected_fingerprint:
        return {**base, "reason": "historical_stored_repair_fingerprint_mismatch", "effective_state": COULD_NOT_VERIFY}

    stored_identity_version = _clean(previous_record.get("repair_identity_version"))
    if stored_identity_version and stored_identity_version != expected_identity_version:
        return {**base, "reason": "historical_stored_repair_identity_version_mismatch", "effective_state": COULD_NOT_VERIFY}

    nested_identity = previous_record.get("repair_identity")
    if nested_identity is not None:
        if not isinstance(nested_identity, dict):
            return {**base, "reason": "historical_repair_identity_claim_malformed", "effective_state": COULD_NOT_VERIFY}
        nested_fingerprint = _clean(nested_identity.get("fingerprint"))
        nested_version = _clean(nested_identity.get("version"))
        if nested_fingerprint and nested_fingerprint != expected_fingerprint:
            return {**base, "reason": "historical_nested_repair_fingerprint_mismatch", "effective_state": COULD_NOT_VERIFY}
        if nested_version and nested_version != expected_identity_version:
            return {**base, "reason": "historical_nested_repair_identity_version_mismatch", "effective_state": COULD_NOT_VERIFY}
        if "stable" in nested_identity and nested_identity.get("stable") is not True:
            return {**base, "reason": "historical_nested_repair_identity_not_stable", "effective_state": COULD_NOT_VERIFY}

    if _clean(current_result.get("repair_fingerprint")) != expected_fingerprint:
        return {**base, "reason": "repair_identity_missing_or_changed", "effective_state": COULD_NOT_VERIFY}
    if _clean(current_result.get("criterion_id")) != expected_criterion_id:
        return {**base, "reason": "acceptance_criterion_identity_mismatch", "effective_state": COULD_NOT_VERIFY}

    effective_state = _clean(integrity.get("effective_state")).upper() or COULD_NOT_VERIFY
    if effective_state in {PASS, PARTIAL, FAIL}:
        historical_population, population_error = _historical_evidence_population(
            previous_record,
            previous_scan_origin=previous_scan_origin,
        )
        if population_error:
            return {
                **base,
                "reason": population_error,
                "effective_state": COULD_NOT_VERIFY,
            }
        base["historical_population_count"] = len(historical_population)
        if integrity.get("required_population_count") != len(historical_population):
            return {
                **base,
                "reason": "historical_evidence_population_count_mismatch",
                "effective_state": COULD_NOT_VERIFY,
            }
        resolved = current_result.get("resolved_scope") if isinstance(current_result.get("resolved_scope"), list) else []
        unresolved = current_result.get("unresolved_scope") if isinstance(current_result.get("unresolved_scope"), list) else []
        transported_scope = {_clean(item) for item in [*resolved, *unresolved]}
        if transported_scope != set(historical_population):
            return {
                **base,
                "reason": "verification_scope_not_bound_to_historical_evidence_population",
                "effective_state": COULD_NOT_VERIFY,
            }

    return {
        **base,
        "valid": True,
        "reason": "verification_result_bound_to_historical_contract_and_population",
        "effective_state": effective_state,
    }


def strict_regression_reopen_decision(
    previous_record: dict[str, Any],
    current_result: dict[str, Any],
    *,
    previous_scan_origin: str = "",
) -> dict[str, Any]:
    """Return a fail-closed pure-data regression decision for serialized integration.

    A proving result must be structurally complete and bound to both the criterion
    and exact evidence population regenerated from the historical repair record.
    Foreign/subset scopes, stale identity claims, or historical version drift
    therefore become COULD_NOT_VERIFY rather than reopening a repair.
    """
    previous_record = previous_record if isinstance(previous_record, dict) else {}
    current_result = current_result if isinstance(current_result, dict) else {}
    binding = verification_result_historical_binding(
        previous_record,
        current_result,
        previous_scan_origin=previous_scan_origin,
    )
    integrity = binding.get("result_integrity") if isinstance(binding.get("result_integrity"), dict) else {}

    current_fingerprint = _clean(current_result.get("repair_fingerprint"))
    previous_fingerprint = _clean(binding.get("repair_fingerprint"))
    if not previous_fingerprint:
        identity = build_repair_identity(previous_record)
        previous_fingerprint = _clean(identity.get("fingerprint")) if identity.get("stable") else ""

    previous_state = _clean(
        previous_record.get("state")
        or previous_record.get("verification_state")
        or previous_record.get("repair_verification_state")
        or previous_record.get("status")
    )
    reported_state = _clean(current_result.get("state")).upper()
    effective_state = _clean(binding.get("effective_state")).upper() or COULD_NOT_VERIFY
    previously_resolved = previous_state.upper() == PASS or previous_state.lower() in {"verified_fixed", "fixed", "resolved"}

    should_reopen = False
    reason = "no_regression_reopen"
    if not binding.get("valid"):
        reason = f"regression_not_proven:{_clean(binding.get('reason')) or 'unbound_verification_result'}"
    elif not previously_resolved:
        reason = "previous_repair_was_not_verified_resolved"
    elif effective_state in {FAIL, PARTIAL}:
        should_reopen = True
        reason = "verified_repair_regressed"
    elif effective_state == COULD_NOT_VERIFY:
        reason = "regression_not_proven"
    elif effective_state == PASS:
        reason = "repair_remains_verified"
    else:
        reason = "unknown_current_verification_state"

    reopen_scope = []
    if should_reopen:
        unresolved = current_result.get("unresolved_scope")
        reopen_scope = list(unresolved) if isinstance(unresolved, list) else []

    return {
        "version": STRICT_REGRESSION_REOPEN_VERSION,
        "legacy_contract_version": REGRESSION_REOPEN_VERSION,
        "should_reopen": should_reopen,
        "reason": reason,
        "repair_fingerprint": previous_fingerprint or current_fingerprint,
        "reopen_scope": reopen_scope,
        "source_verification_state": previous_state,
        "reported_current_verification_state": reported_state,
        "current_verification_state": effective_state,
        "result_integrity": integrity,
        "result_binding": binding,
    }
