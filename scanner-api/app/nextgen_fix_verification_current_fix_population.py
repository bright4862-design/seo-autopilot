from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from .nextgen_fix_verification import COULD_NOT_VERIFY
from .nextgen_fix_verification_evaluation_receipt_binding import (
    strict_verified_fixed_transition_from_evaluation_receipt_bound_inputs,
)

CURRENT_FIX_POPULATION_ATTESTATION_VERSION = (
    "fix_verification_current_fix_population_v1_exact_complete_scan_population"
)
CURRENT_FIX_POPULATION_BINDING_VERSION = (
    "fix_verification_current_fix_population_binding_v1_exact_complete_scan_population"
)
STRICT_VERIFIED_FIXED_CURRENT_FIX_POPULATION_BOUND_VERSION = (
    "fix_verified_fixed_current_fix_population_bound_replay_v1_exact_complete_scan_population"
)

_ATTESTATION_FIELDS = frozenset(
    {
        "version",
        "scan_id",
        "population_complete",
        "population_count",
        "population_fingerprint",
    }
)


def _exact_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _exact_sha256(value: Any) -> bool:
    if not _exact_nonempty_string(value) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return value.lower() == value


def _transport_reason(value: Any, path: str) -> str:
    """Reject values that JSON would silently coerce or cannot encode exactly."""
    if value is None or isinstance(value, (str, bool, int)):
        return ""
    if isinstance(value, float):
        return "" if math.isfinite(value) else f"{path}_contains_nonfinite_float"
    if isinstance(value, list):
        for index, item in enumerate(value):
            reason = _transport_reason(item, f"{path}_{index}")
            if reason:
                return reason
        return ""
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                return f"{path}_contains_non_string_object_key"
            reason = _transport_reason(item, f"{path}_{key}")
            if reason:
                return reason
        return ""
    return f"{path}_contains_unsupported_transport_type"


def current_fix_population_fingerprint(
    current_fixes: list[dict[str, Any]],
    *,
    scan_id: str,
) -> tuple[str, str]:
    """Fingerprint the exact current-fix population transport for one scan.

    The list is intentionally order-sensitive. The attestation is a receipt for
    the exact transport handed to the legacy comparator, not a semantic set hash.
    A producer that reorders or otherwise rewrites the population must publish a
    new attestation rather than inheriting an old completeness claim.
    """
    if not _exact_nonempty_string(scan_id):
        return "", "scan_id_must_be_exact_nonempty_string"
    if not isinstance(current_fixes, list):
        return "", "current_fixes_not_a_list"
    if any(not isinstance(item, dict) for item in current_fixes):
        return "", "current_fixes_contains_non_object"

    reason = _transport_reason(current_fixes, "current_fixes")
    if reason:
        return "", reason

    payload = json.dumps(
        {
            "version": CURRENT_FIX_POPULATION_ATTESTATION_VERSION,
            "scan_id": scan_id,
            "current_fixes": current_fixes,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest(), ""


def verification_current_fix_population_integrity(
    attestation: dict[str, Any],
    current_fixes: list[dict[str, Any]],
    *,
    scan_id: str,
) -> dict[str, Any]:
    """Require explicit complete-population proof before absence can prove fixed.

    ``compare_repair_runs`` legitimately reasons over the caller-supplied current
    fix population. An empty or truncated list, however, has no provenance by
    itself. This Lane-E boundary requires a versioned producer attestation that
    the supplied list is the complete current-scan fix population and binds that
    claim to the exact list transport. Without it, absence of a matching current
    fix remains unknown and cannot authorize ``verified_fixed``.
    """
    base = {
        "version": CURRENT_FIX_POPULATION_BINDING_VERSION,
        "valid": False,
        "reason": "current_fix_population_completeness_not_proven",
        "scan_id": scan_id if _exact_nonempty_string(scan_id) else "",
    }
    if not _exact_nonempty_string(scan_id):
        return {**base, "reason": "scan_id_must_be_exact_nonempty_string"}
    if not isinstance(attestation, dict):
        return {**base, "reason": "current_fix_population_attestation_not_an_object"}
    if set(attestation) != _ATTESTATION_FIELDS:
        return {**base, "reason": "current_fix_population_attestation_fields_mismatch"}
    if not isinstance(current_fixes, list):
        return {**base, "reason": "current_fixes_not_a_list"}
    if any(not isinstance(item, dict) for item in current_fixes):
        return {**base, "reason": "current_fixes_contains_non_object"}

    if attestation.get("version") != CURRENT_FIX_POPULATION_ATTESTATION_VERSION:
        return {**base, "reason": "unsupported_current_fix_population_attestation_version"}

    claimed_scan_id = attestation.get("scan_id")
    if not _exact_nonempty_string(claimed_scan_id):
        return {**base, "reason": "current_fix_population_scan_id_must_be_exact_nonempty_string"}
    if claimed_scan_id != scan_id:
        return {**base, "reason": "current_fix_population_scan_id_mismatch"}

    if attestation.get("population_complete") is not True:
        return {**base, "reason": "current_fix_population_not_declared_complete"}

    population_count = attestation.get("population_count")
    if isinstance(population_count, bool) or not isinstance(population_count, int) or population_count < 0:
        return {**base, "reason": "current_fix_population_count_must_be_exact_nonnegative_integer"}
    if population_count != len(current_fixes):
        return {
            **base,
            "reason": "current_fix_population_count_mismatch",
            "declared_population_count": population_count,
            "observed_population_count": len(current_fixes),
        }

    claimed_fingerprint = attestation.get("population_fingerprint")
    if not _exact_sha256(claimed_fingerprint):
        return {**base, "reason": "current_fix_population_fingerprint_must_be_exact_sha256"}

    expected_fingerprint, fingerprint_reason = current_fix_population_fingerprint(
        current_fixes,
        scan_id=scan_id,
    )
    if fingerprint_reason:
        return {**base, "reason": f"current_fix_population_transport_invalid:{fingerprint_reason}"}
    if claimed_fingerprint != expected_fingerprint:
        return {
            **base,
            "reason": "current_fix_population_fingerprint_mismatch",
            "expected_population_fingerprint": expected_fingerprint,
            "claimed_population_fingerprint": claimed_fingerprint,
        }

    return {
        **base,
        "valid": True,
        "reason": "exact_complete_current_fix_population_proven",
        "population_count": population_count,
        "population_fingerprint": expected_fingerprint,
    }


def _denied(reason: str, binding: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": STRICT_VERIFIED_FIXED_CURRENT_FIX_POPULATION_BOUND_VERSION,
        "allowed": False,
        "reason": reason,
        "repair_fingerprint": "",
        "recomputed_verification_state": COULD_NOT_VERIFY,
        "recomputed_result": {},
        "replay": {},
        "current_fix_population_binding": binding,
        "inner_evaluation_receipt_bound_replay_version": "",
    }


def strict_verified_fixed_transition_from_complete_current_fix_population(
    previous_record: dict[str, Any],
    plan: dict[str, Any],
    current_pages: list[dict[str, Any]],
    rule_evaluations: list[dict[str, Any]],
    current_fixes: list[dict[str, Any]],
    current_fix_population_attestation: dict[str, Any],
    current_contract: dict[str, Any],
    *,
    previous_scan_id: str,
    scan_id: str,
    previous_scan_origin: str = "",
    scan_origin: str = "",
) -> dict[str, Any]:
    """Require exact current-fix population completeness before verified_fixed.

    This wrapper intentionally has no regression-reopen counterpart. Reopening is
    established by positive re-observed defect evidence and does not depend on
    absence from ``current_fixes``. The completeness attestation is therefore a
    one-way guard on the verified-fixed path only.
    """
    binding = verification_current_fix_population_integrity(
        current_fix_population_attestation,
        current_fixes,
        scan_id=scan_id,
    )
    if binding.get("valid") is not True:
        return _denied("current_fix_population_binding_failed", binding)

    decision = strict_verified_fixed_transition_from_evaluation_receipt_bound_inputs(
        previous_record,
        plan,
        current_pages,
        rule_evaluations,
        current_fixes,
        current_contract,
        previous_scan_id=previous_scan_id,
        scan_id=scan_id,
        previous_scan_origin=previous_scan_origin,
        scan_origin=scan_origin,
    )
    if not isinstance(decision, dict):
        return _denied("evaluation_receipt_bound_verified_fixed_replay_returned_non_object", binding)

    return {
        **decision,
        "version": STRICT_VERIFIED_FIXED_CURRENT_FIX_POPULATION_BOUND_VERSION,
        "inner_evaluation_receipt_bound_replay_version": decision.get("version", ""),
        "current_fix_population_binding": binding,
    }
