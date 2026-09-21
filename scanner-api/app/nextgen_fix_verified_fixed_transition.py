from __future__ import annotations

from typing import Any

from .nextgen_fix_verification import PASS
from .nextgen_fix_verification_integrity import verification_result_integrity
from .repair_identity import REPAIR_VERIFICATION_VERSION, build_repair_identity

STRICT_VERIFIED_FIXED_TRANSITION_VERSION = "fix_verified_fixed_transition_v2_integrity"


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _strict_count(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _legacy_verified_fixed_integrity(legacy_comparison: dict[str, Any]) -> dict[str, Any]:
    """Validate the existing compare_repair_runs verified-fixed proof envelope.

    This is deliberately a consumer-side integrity check. It does not replace or
    loosen compare_repair_runs; a serialized integrator must still obtain the
    legacy comparison from that existing comparator. The helper only rejects
    malformed, partial, foreign-version, or non-comparable transported objects.
    """
    if not isinstance(legacy_comparison, dict):
        return {"valid": False, "reason": "legacy_comparison_not_an_object"}
    if legacy_comparison.get("version") != REPAIR_VERIFICATION_VERSION:
        return {"valid": False, "reason": "unsupported_legacy_verification_version"}
    if _clean(legacy_comparison.get("state")).lower() != "verified_fixed":
        return {"valid": False, "reason": "legacy_comparison_not_verified_fixed"}

    previous = _strict_count(legacy_comparison.get("previous_affected_pages"))
    rechecked = _strict_count(legacy_comparison.get("rechecked_pages"))
    eligible = _strict_count(legacy_comparison.get("eligible_rechecked_pages"))
    if previous is None or rechecked is None or eligible is None or previous <= 0:
        return {"valid": False, "reason": "legacy_comparison_population_counts_invalid"}
    if rechecked != previous or eligible != previous:
        return {"valid": False, "reason": "legacy_comparison_population_not_fully_rechecked"}

    contract_state = _clean(legacy_comparison.get("comparison_contract_state")).lower()
    if contract_state not in {"compatible", "legacy_compatible"}:
        return {"valid": False, "reason": "legacy_comparison_contract_not_comparable"}

    return {
        "valid": True,
        "reason": "legacy_verified_fixed_comparison_complete",
        "previous_affected_pages": previous,
        "comparison_contract_state": contract_state,
    }


def strict_verified_fixed_transition_decision(
    previous_record: dict[str, Any],
    current_result: dict[str, Any],
    legacy_comparison: dict[str, Any],
) -> dict[str, Any]:
    """Require dual complete proof before proposing a durable verified-fixed transition.

    The NextGen result must be an integrity-valid PASS for the same stable repair
    identity, and the existing repair comparator must independently report a
    complete ``verified_fixed`` outcome over the same evidence-population size.
    This function is pure data: it never mutates authority, persistence, customer
    projection, workflow state, or production.
    """
    previous_record = previous_record if isinstance(previous_record, dict) else {}
    current_result = current_result if isinstance(current_result, dict) else {}

    result_integrity = verification_result_integrity(current_result)
    legacy_integrity = _legacy_verified_fixed_integrity(legacy_comparison)

    current_fingerprint = _clean(current_result.get("repair_fingerprint"))
    previous_fingerprint = _clean(previous_record.get("repair_fingerprint"))
    if not previous_fingerprint:
        identity = build_repair_identity(previous_record)
        previous_fingerprint = _clean(identity.get("fingerprint")) if identity.get("stable") else ""

    allowed = False
    reason = "verified_fixed_transition_not_proven"
    if not result_integrity.get("valid"):
        reason = (
            "nextgen_result_not_proven:"
            f"{_clean(result_integrity.get('reason')) or 'invalid_verification_result'}"
        )
    elif _clean(result_integrity.get("effective_state")).upper() != PASS:
        reason = "nextgen_result_is_not_pass"
    elif not previous_fingerprint or not current_fingerprint or previous_fingerprint != current_fingerprint:
        reason = "repair_identity_missing_or_changed"
    elif not legacy_integrity.get("valid"):
        reason = (
            "legacy_comparison_not_proven:"
            f"{_clean(legacy_integrity.get('reason')) or 'invalid_legacy_comparison'}"
        )
    elif result_integrity.get("required_population_count") != legacy_integrity.get("previous_affected_pages"):
        reason = "verification_population_mismatch"
    else:
        allowed = True
        reason = "nextgen_pass_and_legacy_verified_fixed"

    return {
        "version": STRICT_VERIFIED_FIXED_TRANSITION_VERSION,
        "allowed": allowed,
        "reason": reason,
        "repair_fingerprint": current_fingerprint or previous_fingerprint,
        "result_integrity": result_integrity,
        "legacy_comparison_integrity": legacy_integrity,
    }
