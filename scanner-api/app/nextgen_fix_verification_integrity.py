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
)
from .repair_identity import build_repair_identity

VERIFICATION_RESULT_INTEGRITY_VERSION = "fix_verification_result_integrity_v1"
STRICT_REGRESSION_REOPEN_VERSION = "fix_regression_reopen_v2_integrity"


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


def strict_regression_reopen_decision(previous_record: dict[str, Any], current_result: dict[str, Any]) -> dict[str, Any]:
    """Return a fail-closed pure-data regression decision for serialized integration.

    A forged or structurally incomplete PASS/PARTIAL/FAIL result is downgraded to
    COULD_NOT_VERIFY for regression purposes. This prevents a matching fingerprint
    plus a hand-constructed FAIL/PARTIAL object from reopening a previously fixed
    repair without complete comparable evidence.
    """
    previous_record = previous_record if isinstance(previous_record, dict) else {}
    current_result = current_result if isinstance(current_result, dict) else {}
    integrity = verification_result_integrity(current_result)

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
    reported_state = _clean(current_result.get("state")).upper()
    effective_state = _clean(integrity.get("effective_state")).upper() or COULD_NOT_VERIFY
    previously_resolved = previous_state.upper() == PASS or previous_state.lower() in {"verified_fixed", "fixed", "resolved"}

    should_reopen = False
    reason = "no_regression_reopen"
    if not integrity.get("valid"):
        reason = f"regression_not_proven:{_clean(integrity.get('reason')) or 'invalid_verification_result'}"
    elif not previous_fingerprint or not current_fingerprint or previous_fingerprint != current_fingerprint:
        reason = "repair_identity_missing_or_changed"
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
        "repair_fingerprint": current_fingerprint or previous_fingerprint,
        "reopen_scope": reopen_scope,
        "source_verification_state": previous_state,
        "reported_current_verification_state": reported_state,
        "current_verification_state": effective_state,
        "result_integrity": integrity,
    }
