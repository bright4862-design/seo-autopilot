from __future__ import annotations

from typing import Any

from .nextgen_fix_verification import COULD_NOT_VERIFY, VERIFICATION_RESULT_VERSION
from .nextgen_fix_verification_observation_integrity import (
    evaluate_verification_observations_strict,
)
from .repair_coverage import (
    PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION,
    repair_evidence_key_function,
)

OBSERVATION_IDENTITY_BINDING_VERSION = (
    "fix_verification_observation_identity_binding_v1_exact_multi_field_identity"
)

_PAGE_IDENTITY_FIELDS = ("url", "final_url", "page_url", "path")
_RULE_EVALUATION_URL_FIELDS = ("url", "page_url")


def _exact_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _strict_population_count(plan: dict[str, Any]) -> int:
    value = plan.get("population_count") if isinstance(plan, dict) else None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value


def _safe_exact_identity(plan: dict[str, Any], field: str) -> str:
    value = plan.get(field) if isinstance(plan, dict) else None
    return value if _exact_nonempty_string(value) else ""


def _identity_values(
    container: dict[str, Any],
    fields: tuple[str, ...],
    *,
    key_for: Any,
    prefix: str,
) -> tuple[dict[str, str], str]:
    """Resolve every supplied observation identity and require exact agreement.

    Optional identity aliases may be omitted or empty. Any non-empty supplied
    alias is proving transport data, however: it must already be an exact string,
    resolve under the published URL-identity contract, and agree with every
    other supplied alias. This prevents a historical URL in ``url`` from hiding
    a foreign redirect target in ``final_url`` (or the equivalent ambiguity in
    rule-evaluation URL aliases).
    """
    resolved: dict[str, str] = {}
    for field in fields:
        if field not in container:
            continue
        value = container.get(field)
        if value is None or value == "":
            continue
        if not _exact_nonempty_string(value):
            return {}, f"{prefix}_{field}_must_be_exact_nonempty_string"
        key = key_for(value)
        if not key:
            return {}, f"{prefix}_{field}_identity_unresolvable"
        resolved[field] = key

    if not resolved:
        return {}, f"{prefix}_evidence_identity_missing"
    if len(set(resolved.values())) != 1:
        return resolved, f"{prefix}_identity_fields_conflict"
    return resolved, ""


def verification_observation_identity_binding(
    current_pages: list[dict[str, Any]],
    rule_evaluations: list[dict[str, Any]],
    current_contract: dict[str, Any],
    *,
    scan_origin: str = "",
) -> dict[str, Any]:
    """Prove current observation identities are exact and internally consistent.

    The lower strict metadata boundary validates criterion/fingerprint/version
    transport, while the core evaluator binds evidence to the required
    historical population. This additional pure boundary closes the gap between
    those layers: a page or rule-evaluation object may carry multiple URL aliases,
    and a tolerant first-nonempty lookup must never silently choose one identity
    while contradictory transport data is present in another field.

    No network work is performed. Unknown, malformed, non-canonical, conflicting,
    or unresolvable identity evidence fails closed.
    """
    base = {
        "version": OBSERVATION_IDENTITY_BINDING_VERSION,
        "valid": False,
        "reason": "observation_identity_binding_not_proven",
    }
    if not isinstance(current_pages, list):
        return {**base, "reason": "current_pages_not_a_list"}
    if not isinstance(rule_evaluations, list):
        return {**base, "reason": "rule_evaluations_not_a_list"}
    if not isinstance(current_contract, dict):
        return {**base, "reason": "current_contract_not_an_object"}
    if any(not isinstance(item, dict) for item in current_pages):
        return {**base, "reason": "current_pages_contains_non_object"}
    if any(not isinstance(item, dict) for item in rule_evaluations):
        return {**base, "reason": "rule_evaluations_contains_non_object"}
    if not isinstance(scan_origin, str) or scan_origin != scan_origin.strip():
        return {**base, "reason": "scan_origin_invalid"}

    identity_version = current_contract.get("evidence_url_identity_version")
    if not _exact_nonempty_string(identity_version):
        return {
            **base,
            "reason": "current_contract_evidence_url_identity_version_must_be_exact_nonempty_string",
        }
    if identity_version != PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION:
        return {**base, "reason": "unsupported_evidence_url_identity_version"}

    try:
        key_for = repair_evidence_key_function(
            scan_origin=scan_origin,
            identity_version=identity_version,
        )
    except (TypeError, ValueError):
        return {**base, "reason": "observation_identity_context_invalid"}

    for index, page in enumerate(current_pages):
        _resolved, reason = _identity_values(
            page,
            _PAGE_IDENTITY_FIELDS,
            key_for=key_for,
            prefix=f"current_page_{index}",
        )
        if reason:
            return {**base, "reason": reason, "current_page_index": index}

    for index, row in enumerate(rule_evaluations):
        resolved, reason = _identity_values(
            row,
            _RULE_EVALUATION_URL_FIELDS,
            key_for=key_for,
            prefix=f"rule_evaluation_{index}",
        )
        if reason and not reason.endswith("_evidence_identity_missing"):
            return {**base, "reason": reason, "rule_evaluation_index": index}

        evidence_key = row.get("evidence_key")
        if evidence_key is not None and evidence_key != "":
            if not _exact_nonempty_string(evidence_key):
                return {
                    **base,
                    "reason": f"rule_evaluation_{index}_evidence_key_must_be_exact_nonempty_string",
                    "rule_evaluation_index": index,
                }
            canonical_key = key_for(evidence_key)
            if not canonical_key:
                return {
                    **base,
                    "reason": f"rule_evaluation_{index}_evidence_key_identity_unresolvable",
                    "rule_evaluation_index": index,
                }
            if canonical_key != evidence_key:
                return {
                    **base,
                    "reason": f"rule_evaluation_{index}_evidence_key_not_canonical",
                    "rule_evaluation_index": index,
                }
            resolved = {**resolved, "evidence_key": canonical_key}

        if not resolved:
            return {
                **base,
                "reason": f"rule_evaluation_{index}_evidence_identity_missing",
                "rule_evaluation_index": index,
            }
        if len(set(resolved.values())) != 1:
            return {
                **base,
                "reason": f"rule_evaluation_{index}_identity_fields_conflict",
                "rule_evaluation_index": index,
            }

    return {
        **base,
        "valid": True,
        "reason": "exact_multi_field_observation_identity_proven",
        "checked_current_pages": len(current_pages),
        "checked_rule_evaluations": len(rule_evaluations),
    }


def _could_not_verify(
    plan: dict[str, Any],
    reason: str,
    *,
    identity_binding: dict[str, Any],
) -> dict[str, Any]:
    return {
        "version": VERIFICATION_RESULT_VERSION,
        "state": COULD_NOT_VERIFY,
        "reason": reason,
        "repair_fingerprint": _safe_exact_identity(plan, "repair_fingerprint"),
        "criterion_id": _safe_exact_identity(plan, "criterion_id"),
        "required_population_count": _strict_population_count(plan),
        "observed_population_count": 0,
        "evaluated_population_count": 0,
        "resolved_scope": [],
        "unresolved_scope": [],
        "unverifiable_scope": [],
        "observation_identity_binding": identity_binding,
    }


def evaluate_verification_observations_identity_bound(
    plan: dict[str, Any],
    previous_record: dict[str, Any],
    current_pages: list[dict[str, Any]],
    rule_evaluations: list[dict[str, Any]],
    current_contract: dict[str, Any],
    *,
    scan_origin: str = "",
) -> dict[str, Any]:
    """Bind observation identities exactly, then run strict verification."""
    binding = verification_observation_identity_binding(
        current_pages,
        rule_evaluations,
        current_contract,
        scan_origin=scan_origin,
    )
    if binding.get("valid") is not True:
        return _could_not_verify(
            plan if isinstance(plan, dict) else {},
            f"Observation evidence identity binding failed: {binding.get('reason') or 'not_proven'}",
            identity_binding=binding,
        )

    result = evaluate_verification_observations_strict(
        plan,
        previous_record,
        current_pages,
        rule_evaluations,
        current_contract,
        scan_origin=scan_origin,
    )
    if not isinstance(result, dict):
        return _could_not_verify(
            plan if isinstance(plan, dict) else {},
            "Strict verification evaluator returned non-object evidence.",
            identity_binding=binding,
        )
    return {
        **result,
        "observation_identity_binding": binding,
    }
