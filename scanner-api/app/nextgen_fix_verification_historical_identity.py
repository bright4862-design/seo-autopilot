from __future__ import annotations

from typing import Any

from .repair_identity import REPAIR_IDENTITY_VERSION, build_repair_identity

HISTORICAL_IDENTITY_INTEGRITY_VERSION = (
    "fix_verification_historical_identity_integrity_v1_exact_source_binding"
)

_RULE_SOURCE_FIELDS = ("rule_id", "rule", "type", "issue_type")
_SURFACE_SOURCE_FIELDS = ("repair_surface", "implementation_surface", "fix_surface")
_REMEDIATION_SOURCE_FIELDS = (
    "remediation_family",
    "recommended_action_family",
    "repair_action_family",
)
_OPTIONAL_TOP_LEVEL_IDENTITY_FIELDS = (
    "repair_identity_version",
    "repair_fingerprint",
    "repair_identity_state",
)
_NESTED_IDENTITY_FIELDS = (
    "version",
    "state",
    "fingerprint",
    "rule",
    "rule_id",
    "repair_surface",
    "remediation_family",
)


def _exact_string(value: Any, *, allow_empty: bool = False) -> bool:
    if not isinstance(value, str) or value != value.strip():
        return False
    return allow_empty or bool(value)


def _source_group_reason(
    record: dict[str, Any],
    fields: tuple[str, ...],
    *,
    label: str,
) -> str:
    """Require every supplied stable-identity source alias to be exact text.

    ``build_repair_identity`` intentionally has deterministic alias precedence
    for historical compatibility (for example ``rule_id`` before display copy in
    ``rule``), so aliases are not required to have identical values. But any
    populated alias is proving transport data and must already be an exact string;
    numbers, objects, or whitespace-padded values must never become a stable
    fingerprint through tolerant string coercion/cleanup.
    """
    populated = 0
    for field in fields:
        if field not in record:
            continue
        value = record.get(field)
        if value is None or value == "":
            continue
        populated += 1
        if not _exact_string(value):
            return f"historical_{label}_{field}_must_be_exact_nonempty_string"
    if populated == 0:
        return f"historical_{label}_source_missing"
    return ""


def _optional_top_level_identity_reason(
    record: dict[str, Any],
    derived: dict[str, Any],
) -> str:
    expected = {
        "repair_identity_version": derived.get("version"),
        "repair_fingerprint": derived.get("fingerprint"),
        "repair_identity_state": derived.get("state"),
    }
    for field in _OPTIONAL_TOP_LEVEL_IDENTITY_FIELDS:
        if field not in record:
            continue
        value = record.get(field)
        if value is None or value == "":
            continue
        if not _exact_string(value):
            return f"historical_{field}_must_be_exact_nonempty_string"
        if value != expected.get(field):
            return f"historical_{field}_does_not_match_derived_identity"

    if "repair_identity_stable" in record and record.get("repair_identity_stable") is not None:
        stable = record.get("repair_identity_stable")
        if not isinstance(stable, bool):
            return "historical_repair_identity_stable_must_be_boolean"
        if stable is not derived.get("stable"):
            return "historical_repair_identity_stable_does_not_match_derived_identity"
    return ""


def _nested_identity_reason(record: dict[str, Any], derived: dict[str, Any]) -> str:
    if "repair_identity" not in record or record.get("repair_identity") is None:
        return ""
    nested = record.get("repair_identity")
    if not isinstance(nested, dict):
        return "historical_repair_identity_not_an_object"

    for field in _NESTED_IDENTITY_FIELDS:
        if field not in nested:
            continue
        value = nested.get(field)
        expected = derived.get(field)
        if field == "rule_id" and value == "" and expected == "":
            continue
        if not _exact_string(value):
            return f"historical_repair_identity_{field}_must_be_exact_nonempty_string"
        if value != expected:
            return f"historical_repair_identity_{field}_does_not_match_derived_identity"

    if "stable" in nested:
        stable = nested.get("stable")
        if not isinstance(stable, bool):
            return "historical_repair_identity_stable_must_be_boolean"
        if stable is not derived.get("stable"):
            return "historical_repair_identity_stable_does_not_match_derived_identity"
    return ""


def verification_historical_identity_integrity(previous_record: dict[str, Any]) -> dict[str, Any]:
    """Bind tolerant historical identity reconstruction to exact proving inputs.

    The existing repair identity builder remains unchanged so historical reports
    retain their current comparison behavior. This pure verification boundary is
    stricter: source fields that can participate in the stable fingerprint must be
    exact strings, the derived identity must be stable/current-version, and any
    persisted identity metadata that is present must agree with the freshly
    derived identity. Missing optional persisted metadata remains allowed.
    """
    base = {
        "version": HISTORICAL_IDENTITY_INTEGRITY_VERSION,
        "valid": False,
        "reason": "historical_identity_integrity_not_proven",
    }
    if not isinstance(previous_record, dict):
        return {**base, "reason": "previous_record_not_an_object"}

    for fields, label in (
        (_RULE_SOURCE_FIELDS, "rule"),
        (_SURFACE_SOURCE_FIELDS, "repair_surface"),
        (_REMEDIATION_SOURCE_FIELDS, "remediation_family"),
    ):
        reason = _source_group_reason(previous_record, fields, label=label)
        if reason:
            return {**base, "reason": reason}

    derived = build_repair_identity(previous_record)
    if not isinstance(derived, dict):
        return {**base, "reason": "derived_repair_identity_not_an_object"}
    if derived.get("version") != REPAIR_IDENTITY_VERSION:
        return {**base, "reason": "derived_repair_identity_version_unsupported"}
    if derived.get("stable") is not True or derived.get("state") != "stable":
        return {**base, "reason": "stable_repair_identity_not_proven"}
    fingerprint = derived.get("fingerprint")
    if not _exact_string(fingerprint):
        return {**base, "reason": "derived_repair_fingerprint_invalid"}

    reason = _optional_top_level_identity_reason(previous_record, derived)
    if reason:
        return {**base, "reason": reason}

    reason = _nested_identity_reason(previous_record, derived)
    if reason:
        return {**base, "reason": reason}

    return {
        **base,
        "valid": True,
        "reason": "exact_historical_repair_identity_source_binding_proven",
        "repair_identity_version": derived.get("version"),
        "repair_fingerprint": fingerprint,
    }
