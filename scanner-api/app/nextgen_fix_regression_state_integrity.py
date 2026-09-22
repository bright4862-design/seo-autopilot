from __future__ import annotations

from typing import Any

REGRESSION_SOURCE_STATE_INTEGRITY_VERSION = (
    "fix_regression_reopen_source_state_integrity_v1_exact_historical_resolution_state"
)

_STATE_FIELDS = (
    "state",
    "verification_state",
    "repair_verification_state",
    "status",
)
_RESOLVED_STATES = frozenset({"pass", "verified_fixed", "fixed", "resolved"})


def _exact_optional_string(value: Any) -> tuple[str, str]:
    if value is None or value == "":
        return "", ""
    if not isinstance(value, str):
        return "", "must_be_a_string"
    if not value.strip():
        return "", "must_be_nonempty_when_supplied"
    if value != value.strip():
        return "", "must_not_have_surrounding_whitespace"
    return value, ""


def verification_historical_resolution_state_integrity(
    previous_record: dict[str, Any],
) -> dict[str, Any]:
    """Fail closed when historical resolution-state aliases are ambiguous.

    Regression reopening is only meaningful when a historical repair was already
    verified resolved. The compatibility helper accepts several legacy state
    aliases and picks the first populated one. At the final replay boundary that
    precedence is not proof: a copied ``state=verified_fixed`` must not hide a
    contradictory ``status=open`` (or vice versa).

    This pure boundary preserves the historical set of resolved spellings while
    requiring every supplied state alias to be exact transport data and all
    populated aliases to agree on the resolved/not-resolved classification.
    """
    base = {
        "version": REGRESSION_SOURCE_STATE_INTEGRITY_VERSION,
        "valid": False,
        "reason": "historical_resolution_state_integrity_not_proven",
        "historical_resolved": False,
        "state_fields": {},
    }
    if not isinstance(previous_record, dict):
        return {**base, "reason": "previous_record_not_an_object"}

    values: dict[str, str] = {}
    classes: dict[str, str] = {}
    for field in _STATE_FIELDS:
        if field not in previous_record:
            continue
        raw = previous_record.get(field)
        value, error = _exact_optional_string(raw)
        if error:
            return {
                **base,
                "reason": f"historical_{field}_{error}",
                "state_fields": values,
            }
        if not value:
            continue
        values[field] = value
        classes[field] = "resolved" if value.lower() in _RESOLVED_STATES else "not_resolved"

    if not values:
        return {**base, "reason": "historical_resolution_state_missing"}

    unique_classes = set(classes.values())
    if len(unique_classes) != 1:
        return {
            **base,
            "reason": "historical_resolution_state_conflict",
            "state_fields": values,
            "state_classes": classes,
        }

    historical_resolved = unique_classes == {"resolved"}
    return {
        **base,
        "valid": True,
        "reason": (
            "exact_historical_resolution_state_proven"
            if historical_resolved
            else "exact_historical_nonresolved_state_proven"
        ),
        "historical_resolved": historical_resolved,
        "state_fields": values,
        "state_classes": classes,
    }
