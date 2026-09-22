from __future__ import annotations

from typing import Any

from .repair_coverage import (
    PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION,
    repair_evidence_key_function,
)

HISTORICAL_EVIDENCE_ALIAS_INTEGRITY_VERSION = (
    "fix_verification_historical_evidence_alias_integrity_v1_exact_population_membership"
)

_FALLBACK_IDENTITY_FIELDS = ("page_url", "representative_page_url")


def _exact_nonempty_string(value: Any) -> bool:
    """Return whether proof-bearing text is already exact and non-empty."""
    return isinstance(value, str) and bool(value) and value == value.strip()


def _resolve_exact_identity(value: Any, *, key_for: Any, label: str) -> tuple[str, str]:
    """Resolve one exact historical URL identity without coercion or cleanup."""
    if not _exact_nonempty_string(value):
        return "", f"{label}_must_be_exact_nonempty_string"
    key = key_for(value)
    if not key:
        return "", f"{label}_identity_unresolvable"
    return key, ""


def verification_historical_evidence_alias_integrity(
    previous_record: dict[str, Any],
    *,
    scan_origin: str = "",
) -> dict[str, Any]:
    """Prove historical evidence aliases cannot contradict the selected population.

    Historical compatibility code intentionally has deterministic fallback
    precedence: a non-empty ``affected_pages`` list wins; otherwise ``page_url``
    wins over ``representative_page_url``. That is appropriate for legacy reads,
    but silently ignoring a populated contradictory alias is too permissive for
    verification proof.

    This pure boundary keeps the legacy selector unchanged while requiring every
    populated fallback alias to agree with the proof population. With an explicit
    ``affected_pages`` population, each fallback alias must resolve to a member of
    that population. Without an explicit population, all populated fallback
    aliases must resolve to the same evidence identity. Any malformed, foreign,
    or conflicting alias fails closed before PASS/PARTIAL/FAIL can become proof.
    """
    base = {
        "version": HISTORICAL_EVIDENCE_ALIAS_INTEGRITY_VERSION,
        "valid": False,
        "reason": "historical_evidence_alias_integrity_not_proven",
        "historical_population_count": 0,
        "checked_fallback_aliases": 0,
    }
    if not isinstance(previous_record, dict):
        return {**base, "reason": "previous_record_not_an_object"}
    if not isinstance(scan_origin, str) or scan_origin != scan_origin.strip():
        return {**base, "reason": "scan_origin_invalid"}

    identity_version = previous_record.get("evidence_url_identity_version")
    if not _exact_nonempty_string(identity_version):
        return {
            **base,
            "reason": "historical_evidence_url_identity_version_must_be_exact_nonempty_string",
        }
    if identity_version != PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION:
        return {**base, "reason": "historical_evidence_url_identity_version_unsupported"}

    try:
        key_for = repair_evidence_key_function(
            scan_origin=scan_origin,
            identity_version=identity_version,
        )
    except (TypeError, ValueError):
        return {**base, "reason": "historical_evidence_identity_context_invalid"}

    affected = previous_record.get("affected_pages")
    if affected is not None and not isinstance(affected, list):
        return {**base, "reason": "historical_affected_pages_not_a_list"}

    if isinstance(affected, list) and affected:
        population: list[str] = []
        population_set: set[str] = set()
        for index, value in enumerate(affected):
            key, reason = _resolve_exact_identity(
                value,
                key_for=key_for,
                label=f"historical_affected_pages_{index}",
            )
            if reason:
                return {**base, "reason": reason}
            if key not in population_set:
                population_set.add(key)
                population.append(key)

        checked_aliases = 0
        for field in _FALLBACK_IDENTITY_FIELDS:
            if field not in previous_record or previous_record.get(field) in (None, ""):
                continue
            checked_aliases += 1
            key, reason = _resolve_exact_identity(
                previous_record.get(field),
                key_for=key_for,
                label=f"historical_{field}",
            )
            if reason:
                return {
                    **base,
                    "reason": reason,
                    "historical_population_count": len(population),
                    "checked_fallback_aliases": checked_aliases,
                }
            if key not in population_set:
                return {
                    **base,
                    "reason": f"historical_{field}_not_in_affected_population",
                    "historical_population_count": len(population),
                    "checked_fallback_aliases": checked_aliases,
                }

        return {
            **base,
            "valid": True,
            "reason": "historical_fallback_aliases_bound_to_explicit_affected_population",
            "historical_population_count": len(population),
            "checked_fallback_aliases": checked_aliases,
        }

    fallback_keys: dict[str, str] = {}
    for field in _FALLBACK_IDENTITY_FIELDS:
        if field not in previous_record or previous_record.get(field) in (None, ""):
            continue
        key, reason = _resolve_exact_identity(
            previous_record.get(field),
            key_for=key_for,
            label=f"historical_{field}",
        )
        if reason:
            return {
                **base,
                "reason": reason,
                "checked_fallback_aliases": len(fallback_keys) + 1,
            }
        fallback_keys[field] = key

    if not fallback_keys:
        return {**base, "reason": "historical_evidence_identity_missing"}
    if len(set(fallback_keys.values())) != 1:
        return {
            **base,
            "reason": "historical_fallback_evidence_aliases_conflict",
            "historical_population_count": 1,
            "checked_fallback_aliases": len(fallback_keys),
        }

    return {
        **base,
        "valid": True,
        "reason": "historical_fallback_aliases_resolve_to_one_evidence_identity",
        "historical_population_count": 1,
        "checked_fallback_aliases": len(fallback_keys),
    }
