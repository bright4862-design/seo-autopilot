from __future__ import annotations

from typing import Any

from .nextgen_fix_verification import (
    COULD_NOT_VERIFY,
    REQUIRED_RECHECK_OBSERVATIONS,
    VERIFICATION_RESULT_VERSION,
    evaluate_verification_plan,
)

OBSERVATION_INPUT_INTEGRITY_VERSION = (
    "fix_verification_observation_input_integrity_v2_exact_plan_request_transport"
)

_HISTORICAL_VERSION_FIELDS = (
    "rule_definition_version",
    "comparison_profile_version",
    "evidence_url_identity_version",
)
_PLAN_IDENTITY_FIELDS = (
    "repair_identity_version",
    "repair_fingerprint",
    "criterion_id",
    "rule",
    "rule_definition_version",
    "comparison_profile_version",
    "evidence_url_identity_version",
)
_CRITERION_IDENTITY_FIELDS = (
    "repair_identity_version",
    "repair_fingerprint",
    "criterion_id",
    "rule",
    "rule_definition_version",
    "comparison_profile_version",
    "evidence_url_identity_version",
    "predicate",
)
_PLAN_REQUEST_IDENTITY_FIELDS = (
    "url",
    "evidence_key",
    "criterion_id",
    "rule",
)
_RULE_EVALUATION_IDENTITY_FIELDS = (
    "criterion_id",
    "repair_fingerprint",
    "rule_definition_version",
    "comparison_profile_version",
    "evidence_url_identity_version",
)


def _exact_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _first_invalid_exact_field(container: dict[str, Any], fields: tuple[str, ...], prefix: str) -> str:
    for field in fields:
        if not _exact_nonempty_string(container.get(field)):
            return f"{prefix}_{field}_must_be_exact_nonempty_string"
    return ""


def _historical_evidence_transport_reason(previous_record: dict[str, Any]) -> str:
    """Reject malformed historical evidence identities before tolerant compatibility logic.

    Historical read compatibility may legitimately fall back from an absent/empty
    ``affected_pages`` list to a representative page field. At the proving
    boundary, however, any supplied affected-page identity must already be an
    exact non-empty string. Non-null malformed ``affected_pages`` containers must
    not be silently ignored in favor of a fallback URL.
    """
    affected = previous_record.get("affected_pages")
    if affected is not None:
        if not isinstance(affected, list):
            return "historical_affected_pages_not_a_list"
        for index, value in enumerate(affected):
            if not _exact_nonempty_string(value):
                return f"historical_affected_pages_{index}_must_be_exact_nonempty_string"
        if affected:
            return ""

    for field in ("page_url", "representative_page_url"):
        value = previous_record.get(field)
        if value is None or value == "":
            continue
        if not _exact_nonempty_string(value):
            return f"historical_{field}_must_be_exact_nonempty_string"
        # The core historical population semantics use page_url first and only
        # fall back to representative_page_url when page_url is absent.
        if field == "page_url":
            return ""
    return ""


def _plan_request_transport_reason(plan: dict[str, Any]) -> str:
    """Require every recheck request to carry exact, non-coerced proving metadata."""
    requests = plan.get("requests")
    if not isinstance(requests, list):
        return "plan_requests_not_a_list"
    if not requests:
        return "plan_requests_empty"

    plan_criterion_id = plan.get("criterion_id")
    plan_rule = plan.get("rule")
    seen_evidence_keys: set[str] = set()
    for index, request in enumerate(requests):
        if not isinstance(request, dict):
            return f"plan_request_{index}_not_an_object"

        reason = _first_invalid_exact_field(
            request,
            _PLAN_REQUEST_IDENTITY_FIELDS,
            f"plan_request_{index}",
        )
        if reason:
            return reason

        if request.get("criterion_id") != plan_criterion_id:
            return f"plan_request_{index}_criterion_id_mismatch"
        if request.get("rule") != plan_rule:
            return f"plan_request_{index}_rule_mismatch"

        evidence_key = request["evidence_key"]
        if evidence_key in seen_evidence_keys:
            return f"plan_request_{index}_duplicate_evidence_key"
        seen_evidence_keys.add(evidence_key)

        if request.get("required_observations") != list(REQUIRED_RECHECK_OBSERVATIONS):
            return f"plan_request_{index}_required_observations_mismatch"

    return ""


def _strict_population_count(plan: dict[str, Any]) -> int:
    value = plan.get("population_count") if isinstance(plan, dict) else None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value


def _safe_exact_identity(plan: dict[str, Any], field: str) -> str:
    value = plan.get(field) if isinstance(plan, dict) else None
    return value if _exact_nonempty_string(value) else ""


def _could_not_verify(
    plan: dict[str, Any],
    reason: str,
    *,
    input_integrity: dict[str, Any],
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
        "observation_input_integrity": input_integrity,
    }


def verification_observation_input_integrity(
    previous_record: dict[str, Any],
    plan: dict[str, Any],
    current_pages: list[dict[str, Any]],
    rule_evaluations: list[dict[str, Any]],
    current_contract: dict[str, Any],
) -> dict[str, Any]:
    """Validate proving observation metadata without coercion or normalization.

    The legacy/current evaluators deliberately use tolerant text cleanup for
    historical compatibility. That is appropriate for read compatibility but is
    too permissive at the new proof boundary: numeric version values,
    whitespace-padded fingerprints/criterion/evidence identities, malformed
    historical evidence transports, or normalized plan-request metadata must
    never become apparently comparable proof.

    This helper is pure and intentionally does not perform URL resolution or
    network work. Existing verification-plan evaluation remains authoritative
    for URL-identity derivation, population completeness, page eligibility and
    predicate truth; this layer only makes the transport identity/version types
    exact before that evaluator is allowed to prove PASS/PARTIAL/FAIL.
    """
    base = {
        "version": OBSERVATION_INPUT_INTEGRITY_VERSION,
        "valid": False,
        "reason": "observation_input_integrity_not_proven",
    }
    if not isinstance(previous_record, dict):
        return {**base, "reason": "previous_record_not_an_object"}
    if not isinstance(plan, dict):
        return {**base, "reason": "verification_plan_not_an_object"}
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

    reason = _first_invalid_exact_field(
        previous_record,
        _HISTORICAL_VERSION_FIELDS,
        "historical",
    )
    if reason:
        return {**base, "reason": reason}

    reason = _historical_evidence_transport_reason(previous_record)
    if reason:
        return {**base, "reason": reason}

    reason = _first_invalid_exact_field(plan, _PLAN_IDENTITY_FIELDS, "plan")
    if reason:
        return {**base, "reason": reason}

    criterion = plan.get("criterion")
    if not isinstance(criterion, dict):
        return {**base, "reason": "plan_criterion_not_an_object"}
    reason = _first_invalid_exact_field(
        criterion,
        _CRITERION_IDENTITY_FIELDS,
        "criterion",
    )
    if reason:
        return {**base, "reason": reason}

    reason = _plan_request_transport_reason(plan)
    if reason:
        return {**base, "reason": reason}

    reason = _first_invalid_exact_field(
        current_contract,
        _HISTORICAL_VERSION_FIELDS,
        "current_contract",
    )
    if reason:
        return {**base, "reason": reason}

    for index, row in enumerate(rule_evaluations):
        reason = _first_invalid_exact_field(
            row,
            _RULE_EVALUATION_IDENTITY_FIELDS,
            f"rule_evaluation_{index}",
        )
        if reason:
            return {**base, "reason": reason, "rule_evaluation_index": index}

        has_identity = False
        if "evidence_key" in row:
            has_identity = True
            if not _exact_nonempty_string(row.get("evidence_key")):
                return {
                    **base,
                    "reason": f"rule_evaluation_{index}_evidence_key_must_be_exact_nonempty_string",
                    "rule_evaluation_index": index,
                }
        for field in ("url", "page_url"):
            if field not in row:
                continue
            has_identity = True
            if not _exact_nonempty_string(row.get(field)):
                return {
                    **base,
                    "reason": f"rule_evaluation_{index}_{field}_must_be_exact_nonempty_string",
                    "rule_evaluation_index": index,
                }
        if not has_identity:
            return {
                **base,
                "reason": f"rule_evaluation_{index}_evidence_identity_missing",
                "rule_evaluation_index": index,
            }

    return {
        **base,
        "valid": True,
        "reason": "exact_identity_version_and_plan_request_transport_metadata_proven",
        "checked_plan_requests": len(plan.get("requests") or []),
        "checked_rule_evaluations": len(rule_evaluations),
    }


def evaluate_verification_observations_strict(
    plan: dict[str, Any],
    previous_record: dict[str, Any],
    current_pages: list[dict[str, Any]],
    rule_evaluations: list[dict[str, Any]],
    current_contract: dict[str, Any],
    *,
    scan_origin: str = "",
) -> dict[str, Any]:
    """Fail closed on ambiguous transport metadata, then run the existing evaluator."""
    integrity = verification_observation_input_integrity(
        previous_record,
        plan,
        current_pages,
        rule_evaluations,
        current_contract,
    )
    if integrity.get("valid") is not True:
        return _could_not_verify(
            plan if isinstance(plan, dict) else {},
            f"Observation input identity/version integrity failed: {integrity.get('reason') or 'not_proven'}",
            input_integrity=integrity,
        )

    result = evaluate_verification_plan(
        plan,
        previous_record,
        current_pages,
        rule_evaluations,
        current_contract,
        scan_origin=scan_origin,
    )
    if not isinstance(result, dict):
        return _could_not_verify(
            plan,
            "Verification evaluator returned non-object evidence.",
            input_integrity=integrity,
        )
    return {
        **result,
        "observation_input_integrity": integrity,
    }
