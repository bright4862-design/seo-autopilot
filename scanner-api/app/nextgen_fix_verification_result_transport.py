from __future__ import annotations

from typing import Any

from .nextgen_fix_regression_state_integrity import (
    verification_historical_resolution_state_integrity,
)
from .nextgen_fix_verification import (
    COULD_NOT_VERIFY,
    FAIL,
    PARTIAL,
    PASS,
    VERIFICATION_RESULT_VERSION,
    VERIFICATION_STATES,
)
from .nextgen_fix_verification_integrity import (
    strict_regression_reopen_decision,
    verification_result_integrity,
)
from .nextgen_fix_verified_fixed_transition import (
    strict_verified_fixed_transition_decision,
)
from .repair_identity import REPAIR_VERIFICATION_VERSION

RESULT_TRANSPORT_INTEGRITY_VERSION = (
    "fix_verification_result_transport_integrity_v1_exact_terminal_transport"
)
LEGACY_COMPARISON_TRANSPORT_INTEGRITY_VERSION = (
    "fix_verified_fixed_legacy_comparison_transport_integrity_v1_exact_transport"
)
STRICT_VERIFIED_FIXED_RESULT_TRANSPORT_VERSION = (
    "fix_verified_fixed_result_transport_replay_v1_exact_terminal_transport"
)
STRICT_REGRESSION_REOPEN_RESULT_TRANSPORT_VERSION = (
    "fix_regression_reopen_result_transport_replay_v1_exact_terminal_transport"
)

_PROVING_STATES = frozenset({PASS, PARTIAL, FAIL})
_COUNT_FIELDS = (
    "required_population_count",
    "observed_population_count",
    "evaluated_population_count",
)
_SCOPE_FIELDS = ("resolved_scope", "unresolved_scope")
_LEGACY_COUNT_FIELDS = (
    "previous_affected_pages",
    "rechecked_pages",
    "eligible_rechecked_pages",
)


def _exact_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _strict_nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _scope_reason(value: Any, *, label: str) -> str:
    if not isinstance(value, list):
        return f"{label}_not_a_list"
    seen: set[str] = set()
    for item in value:
        if not _exact_nonempty_string(item):
            return f"{label}_contains_noncanonical_identity"
        if item in seen:
            return f"{label}_contains_duplicate_identity"
        seen.add(item)
    return ""


def _unverifiable_scope_reason(value: Any) -> str:
    if not isinstance(value, list):
        return "unverifiable_scope_not_a_list"
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            return f"unverifiable_scope_{index}_not_an_object"
        evidence_key = item.get("evidence_key")
        reason = item.get("reason")
        if not _exact_nonempty_string(evidence_key):
            return f"unverifiable_scope_{index}_evidence_key_not_exact_nonempty_string"
        if not _exact_nonempty_string(reason):
            return f"unverifiable_scope_{index}_reason_not_exact_nonempty_string"
    return ""


def verification_result_transport_integrity(result: dict[str, Any]) -> dict[str, Any]:
    """Require exact terminal-result transport before a result can become proof.

    The older result integrity helper intentionally accepts normalized state and
    identity strings for compatibility. This additive boundary is for serialized
    NextGen consumers: PASS/PARTIAL/FAIL must already be canonical transport data,
    never values made valid by stripping, casing, or string coercion. A malformed
    result fails closed to COULD_NOT_VERIFY.
    """
    base = {
        "version": RESULT_TRANSPORT_INTEGRITY_VERSION,
        "valid": False,
        "reason": "verification_result_transport_not_proven",
        "effective_state": COULD_NOT_VERIFY,
        "proving": False,
    }
    if not isinstance(result, dict):
        return {**base, "reason": "verification_result_not_an_object"}
    if result.get("version") != VERIFICATION_RESULT_VERSION:
        return {**base, "reason": "unsupported_verification_result_version"}

    state = result.get("state")
    if not _exact_nonempty_string(state) or state not in VERIFICATION_STATES:
        return {**base, "reason": "verification_result_state_not_exact_supported_value"}

    for field in ("repair_fingerprint", "criterion_id"):
        if not _exact_nonempty_string(result.get(field)):
            return {**base, "reason": f"verification_result_{field}_not_exact_nonempty_string"}

    for field in _COUNT_FIELDS:
        if not _strict_nonnegative_int(result.get(field)):
            return {**base, "reason": f"verification_result_{field}_not_strict_nonnegative_integer"}

    for field in _SCOPE_FIELDS:
        reason = _scope_reason(result.get(field), label=field)
        if reason:
            return {**base, "reason": reason}

    unverifiable_reason = _unverifiable_scope_reason(result.get("unverifiable_scope"))
    if unverifiable_reason:
        return {**base, "reason": unverifiable_reason}

    delegated = verification_result_integrity(result)
    if not isinstance(delegated, dict) or delegated.get("valid") is not True:
        delegated_reason = (
            delegated.get("reason")
            if isinstance(delegated, dict) and _exact_nonempty_string(delegated.get("reason"))
            else "invalid_verification_result"
        )
        return {
            **base,
            "reason": f"verification_result_integrity_failed:{delegated_reason}",
            "delegated_result_integrity": delegated if isinstance(delegated, dict) else {},
        }

    effective_state = delegated.get("effective_state")
    if not _exact_nonempty_string(effective_state) or effective_state not in VERIFICATION_STATES:
        return {
            **base,
            "reason": "delegated_verification_state_not_exact_supported_value",
            "delegated_result_integrity": delegated,
        }

    return {
        **base,
        "valid": True,
        "reason": (
            "exact_proving_terminal_result_transport"
            if state in _PROVING_STATES
            else "exact_nonproving_terminal_result_transport"
        ),
        "effective_state": effective_state,
        "proving": state in _PROVING_STATES,
        "delegated_result_integrity": delegated,
    }


def legacy_verified_fixed_transport_integrity(
    legacy_comparison: dict[str, Any],
) -> dict[str, Any]:
    """Require exact transport from the existing verified-fixed comparator.

    This does not change comparator semantics. It only prevents tolerant casing or
    whitespace cleanup at a later consumer from turning ambiguous comparator
    transport into durable verified-fixed proof.
    """
    base = {
        "version": LEGACY_COMPARISON_TRANSPORT_INTEGRITY_VERSION,
        "valid": False,
        "reason": "legacy_comparison_transport_not_proven",
    }
    if not isinstance(legacy_comparison, dict):
        return {**base, "reason": "legacy_comparison_not_an_object"}
    if legacy_comparison.get("version") != REPAIR_VERIFICATION_VERSION:
        return {**base, "reason": "unsupported_legacy_verification_version"}
    if legacy_comparison.get("state") != "verified_fixed":
        return {**base, "reason": "legacy_comparison_state_not_exact_verified_fixed"}
    if legacy_comparison.get("comparison_contract_state") != "compatible":
        return {**base, "reason": "legacy_comparison_contract_state_not_exact_compatible"}
    for field in _LEGACY_COUNT_FIELDS:
        value = legacy_comparison.get(field)
        if not _strict_nonnegative_int(value):
            return {**base, "reason": f"legacy_comparison_{field}_not_strict_nonnegative_integer"}
    return {
        **base,
        "valid": True,
        "reason": "exact_legacy_verified_fixed_transport",
    }


def _verified_fixed_denied(
    reason: str,
    result_transport: dict[str, Any],
    legacy_transport: dict[str, Any],
) -> dict[str, Any]:
    return {
        "version": STRICT_VERIFIED_FIXED_RESULT_TRANSPORT_VERSION,
        "allowed": False,
        "reason": reason,
        "repair_fingerprint": "",
        "result_transport_integrity": result_transport,
        "legacy_comparison_transport_integrity": legacy_transport,
        "inner_verified_fixed_transition_version": "",
    }


def strict_verified_fixed_transition_from_exact_result_transport(
    previous_record: dict[str, Any],
    current_result: dict[str, Any],
    legacy_comparison: dict[str, Any],
    *,
    previous_scan_origin: str = "",
) -> dict[str, Any]:
    """Require exact result/comparator transport before existing dual proof."""
    result_transport = verification_result_transport_integrity(current_result)
    if result_transport.get("valid") is not True:
        return _verified_fixed_denied(
            "verification_result_transport_integrity_failed",
            result_transport,
            {},
        )
    legacy_transport = legacy_verified_fixed_transport_integrity(legacy_comparison)
    if legacy_transport.get("valid") is not True:
        return _verified_fixed_denied(
            "legacy_comparison_transport_integrity_failed",
            result_transport,
            legacy_transport,
        )

    decision = strict_verified_fixed_transition_decision(
        previous_record,
        current_result,
        legacy_comparison,
        previous_scan_origin=previous_scan_origin,
    )
    if not isinstance(decision, dict):
        return _verified_fixed_denied(
            "verified_fixed_transition_returned_non_object",
            result_transport,
            legacy_transport,
        )
    return {
        **decision,
        "version": STRICT_VERIFIED_FIXED_RESULT_TRANSPORT_VERSION,
        "inner_verified_fixed_transition_version": decision.get("version", ""),
        "result_transport_integrity": result_transport,
        "legacy_comparison_transport_integrity": legacy_transport,
    }


def _regression_denied(
    reason: str,
    result_transport: dict[str, Any],
    state_integrity: dict[str, Any],
) -> dict[str, Any]:
    return {
        "version": STRICT_REGRESSION_REOPEN_RESULT_TRANSPORT_VERSION,
        "should_reopen": False,
        "reason": reason,
        "repair_fingerprint": "",
        "reopen_scope": [],
        "reported_current_verification_state": (
            result_transport.get("effective_state", COULD_NOT_VERIFY)
            if isinstance(result_transport, dict)
            else COULD_NOT_VERIFY
        ),
        "current_verification_state": COULD_NOT_VERIFY,
        "result_transport_integrity": result_transport,
        "historical_resolution_state_integrity": state_integrity,
        "inner_regression_reopen_version": "",
    }


def strict_regression_reopen_from_exact_result_transport(
    previous_record: dict[str, Any],
    current_result: dict[str, Any],
    *,
    previous_scan_origin: str = "",
) -> dict[str, Any]:
    """Require exact result transport and unambiguous source state before reopen."""
    result_transport = verification_result_transport_integrity(current_result)
    if result_transport.get("valid") is not True:
        return _regression_denied(
            "verification_result_transport_integrity_failed",
            result_transport,
            {},
        )

    state_integrity = verification_historical_resolution_state_integrity(previous_record)
    if state_integrity.get("valid") is not True:
        return _regression_denied(
            "historical_resolution_state_integrity_failed",
            result_transport,
            state_integrity,
        )

    decision = strict_regression_reopen_decision(
        previous_record,
        current_result,
        previous_scan_origin=previous_scan_origin,
    )
    if not isinstance(decision, dict):
        return _regression_denied(
            "regression_reopen_decision_returned_non_object",
            result_transport,
            state_integrity,
        )
    return {
        **decision,
        "version": STRICT_REGRESSION_REOPEN_RESULT_TRANSPORT_VERSION,
        "inner_regression_reopen_version": decision.get("version", ""),
        "result_transport_integrity": result_transport,
        "historical_resolution_state_integrity": state_integrity,
    }
