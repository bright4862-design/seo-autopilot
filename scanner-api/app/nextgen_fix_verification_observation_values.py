from __future__ import annotations

from typing import Any

from .nextgen_fix_verification import COULD_NOT_VERIFY, VERIFICATION_RESULT_VERSION
from .nextgen_fix_verification_observation_identity import (
    evaluate_verification_observations_identity_bound,
)

OBSERVATION_VALUE_INTEGRITY_VERSION = (
    "fix_verification_observation_value_integrity_v1_exact_proving_values"
)

_STATUS_FIELDS = ("status_code", "status")
_CONTENT_TYPE_FIELDS = ("content_type", "mime_type")
_EVIDENCE_CLASS_FIELDS = ("page_evidence_class", "evidence_class")
_ROBOTS_FIELDS = ("robots", "robots_meta", "meta_robots")


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


def _present_values(container: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {
        field: container[field]
        for field in fields
        if field in container and container[field] is not None
    }


def _page_value_reason(page: dict[str, Any], index: int) -> str:
    prefix = f"current_page_{index}"

    statuses = _present_values(page, _STATUS_FIELDS)
    if not statuses:
        return f"{prefix}_http_status_missing"
    for field, value in statuses.items():
        if type(value) is not int:
            return f"{prefix}_{field}_must_be_exact_integer"
        if value < 100 or value > 599:
            return f"{prefix}_{field}_out_of_http_range"
    if len(set(statuses.values())) != 1:
        return f"{prefix}_http_status_fields_conflict"

    content_types = _present_values(page, _CONTENT_TYPE_FIELDS)
    if not content_types:
        return f"{prefix}_content_type_missing"
    for field, value in content_types.items():
        if not _exact_nonempty_string(value):
            return f"{prefix}_{field}_must_be_exact_nonempty_string"
    if len(set(content_types.values())) != 1:
        return f"{prefix}_content_type_fields_conflict"

    if "indexable" not in page or type(page.get("indexable")) is not bool:
        return f"{prefix}_indexable_must_be_exact_boolean"

    evidence_classes = _present_values(page, _EVIDENCE_CLASS_FIELDS)
    for field, value in evidence_classes.items():
        if not _exact_nonempty_string(value):
            return f"{prefix}_{field}_must_be_exact_nonempty_string"
    if len(set(evidence_classes.values())) > 1:
        return f"{prefix}_evidence_class_fields_conflict"

    robots_values = _present_values(page, _ROBOTS_FIELDS)
    for field, value in robots_values.items():
        if not _exact_nonempty_string(value):
            return f"{prefix}_{field}_must_be_exact_nonempty_string"
    if len(set(robots_values.values())) > 1:
        return f"{prefix}_robots_fields_conflict"
    if page["indexable"] is True and any(
        "noindex" in value.lower() for value in robots_values.values()
    ):
        return f"{prefix}_indexability_conflicts_with_robots"

    return ""


def _rule_evaluation_value_reason(row: dict[str, Any], index: int) -> str:
    prefix = f"rule_evaluation_{index}"
    if "evaluated" not in row or type(row.get("evaluated")) is not bool:
        return f"{prefix}_evaluated_must_be_exact_boolean"
    if "defect_detected" not in row or type(row.get("defect_detected")) is not bool:
        return f"{prefix}_defect_detected_must_be_exact_boolean"
    return ""


def verification_observation_value_integrity(
    current_pages: list[dict[str, Any]],
    rule_evaluations: list[dict[str, Any]],
) -> dict[str, Any]:
    """Require proof-bearing observation values to arrive without coercion.

    The historical comparator intentionally remains tolerant for compatibility.
    NextGen proof must not inherit that tolerance: strings/floats that happen to
    coerce to HTTP 200, non-string content types that stringify to HTML, unknown
    indexability values, contradictory aliases, or non-boolean predicate values
    are ambiguous evidence and therefore cannot prove PASS/PARTIAL/FAIL.
    """
    base = {
        "version": OBSERVATION_VALUE_INTEGRITY_VERSION,
        "valid": False,
        "reason": "observation_value_integrity_not_proven",
    }
    if not isinstance(current_pages, list):
        return {**base, "reason": "current_pages_not_a_list"}
    if not isinstance(rule_evaluations, list):
        return {**base, "reason": "rule_evaluations_not_a_list"}
    if any(not isinstance(item, dict) for item in current_pages):
        return {**base, "reason": "current_pages_contains_non_object"}
    if any(not isinstance(item, dict) for item in rule_evaluations):
        return {**base, "reason": "rule_evaluations_contains_non_object"}

    for index, page in enumerate(current_pages):
        reason = _page_value_reason(page, index)
        if reason:
            return {**base, "reason": reason, "current_page_index": index}

    for index, row in enumerate(rule_evaluations):
        reason = _rule_evaluation_value_reason(row, index)
        if reason:
            return {**base, "reason": reason, "rule_evaluation_index": index}

    return {
        **base,
        "valid": True,
        "reason": "exact_proving_observation_values_proven",
        "checked_current_pages": len(current_pages),
        "checked_rule_evaluations": len(rule_evaluations),
    }


def _could_not_verify(
    plan: dict[str, Any],
    reason: str,
    *,
    value_integrity: dict[str, Any],
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
        "observation_value_integrity": value_integrity,
    }


def evaluate_verification_observations_value_bound(
    plan: dict[str, Any],
    previous_record: dict[str, Any],
    current_pages: list[dict[str, Any]],
    rule_evaluations: list[dict[str, Any]],
    current_contract: dict[str, Any],
    *,
    scan_origin: str = "",
) -> dict[str, Any]:
    """Fail closed on ambiguous observation values, then bind identity/evaluate."""
    value_integrity = verification_observation_value_integrity(
        current_pages,
        rule_evaluations,
    )
    if value_integrity.get("valid") is not True:
        return _could_not_verify(
            plan if isinstance(plan, dict) else {},
            "Observation proving-value integrity failed: "
            f"{value_integrity.get('reason') or 'not_proven'}",
            value_integrity=value_integrity,
        )

    result = evaluate_verification_observations_identity_bound(
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
            "Identity-bound verification evaluator returned non-object evidence.",
            value_integrity=value_integrity,
        )
    return {
        **result,
        "observation_value_integrity": value_integrity,
    }
