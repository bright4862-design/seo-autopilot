from __future__ import annotations

from typing import Any

from .nextgen_fix_verified_fixed_transition import strict_verified_fixed_transition_decision
from .repair_identity import compare_repair_runs

STRICT_VERIFIED_FIXED_REPLAY_VERSION = "fix_verified_fixed_replay_v1_recomputed_legacy_comparator"


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _denied(reason: str, *, legacy_comparison: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return one stable fail-closed replay envelope without durable side effects."""
    return {
        "version": STRICT_VERIFIED_FIXED_REPLAY_VERSION,
        "allowed": False,
        "reason": reason,
        "legacy_comparison": legacy_comparison if isinstance(legacy_comparison, dict) else {},
        "strict_transition": {},
    }


def strict_verified_fixed_transition_from_evidence(
    previous_record: dict[str, Any],
    current_result: dict[str, Any],
    current_fixes: list[dict[str, Any]],
    current_pages: list[dict[str, Any]],
    current_contract: dict[str, Any],
    *,
    previous_scan_origin: str = "",
    scan_origin: str = "",
) -> dict[str, Any]:
    """Recompute the existing legacy comparator before proposing verified_fixed.

    A transported legacy-comparison object has no repair fingerprint of its own,
    so a same-sized ``verified_fixed`` result copied from another repair is not
    independently bound to ``previous_record``. This helper avoids trusting such
    transport: it reruns the existing ``compare_repair_runs`` comparator over the
    caller-supplied current evidence, then feeds that exact result into the
    stricter NextGen transition gate. The legacy comparator itself is unchanged.

    This helper is pure. It performs no network work and writes no persistence,
    authority, customer projection, workflow state, or production configuration.
    """
    if not isinstance(previous_record, dict):
        return _denied("previous_record_not_an_object")
    if not isinstance(current_result, dict):
        return _denied("current_result_not_an_object")
    if not isinstance(current_fixes, list):
        return _denied("current_fixes_not_a_list")
    if not isinstance(current_pages, list):
        return _denied("current_pages_not_a_list")
    if not isinstance(current_contract, dict):
        return _denied("current_contract_not_an_object")
    if any(not isinstance(item, dict) for item in current_fixes):
        return _denied("current_fixes_contains_non_object")
    if any(not isinstance(item, dict) for item in current_pages):
        return _denied("current_pages_contains_non_object")
    if not isinstance(previous_scan_origin, str) or previous_scan_origin != previous_scan_origin.strip():
        return _denied("previous_scan_origin_invalid")
    if not isinstance(scan_origin, str) or scan_origin != scan_origin.strip():
        return _denied("scan_origin_invalid")

    try:
        legacy_comparison = compare_repair_runs(
            previous_record,
            current_fixes,
            current_pages,
            current_contract,
            previous_scan_origin=previous_scan_origin,
            scan_origin=scan_origin,
        )
    except (KeyError, TypeError, ValueError) as exc:
        return {
            **_denied("legacy_comparator_replay_failed"),
            "comparator_error_type": type(exc).__name__,
        }

    if not isinstance(legacy_comparison, dict):
        return _denied("legacy_comparator_returned_non_object")

    transition = strict_verified_fixed_transition_decision(
        previous_record,
        current_result,
        legacy_comparison,
        previous_scan_origin=previous_scan_origin,
    )
    if not isinstance(transition, dict):
        return _denied("strict_transition_returned_non_object", legacy_comparison=legacy_comparison)

    allowed = transition.get("allowed") is True
    reason = (
        "legacy_comparator_recomputed_and_transition_proven"
        if allowed
        else f"strict_transition_denied:{_clean(transition.get('reason')) or 'not_proven'}"
    )
    return {
        "version": STRICT_VERIFIED_FIXED_REPLAY_VERSION,
        "allowed": allowed,
        "reason": reason,
        "repair_fingerprint": _clean(transition.get("repair_fingerprint")),
        "legacy_comparison": legacy_comparison,
        "strict_transition": transition,
    }
