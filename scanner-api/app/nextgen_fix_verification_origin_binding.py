from __future__ import annotations

from typing import Any

from .nextgen_fix_verification import COULD_NOT_VERIFY, VERIFICATION_RESULT_VERSION
from .nextgen_fix_verification_historical_bound import (
    evaluate_verification_observations_historical_bound,
)
from .repair_coverage import published_evidence_url_key

SCAN_ORIGIN_BINDING_VERSION = (
    "fix_verification_scan_origin_binding_v1_exact_authoritative_origins"
)

_IDENTITY_FIELDS = ("url", "final_url", "page_url", "path")
_RULE_IDENTITY_FIELDS = ("url", "page_url")


def _exact_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _canonical_origin(value: Any) -> tuple[str, str]:
    if not _exact_nonempty_string(value):
        return "", "origin_must_be_exact_nonempty_string"
    root = published_evidence_url_key("/", scan_origin=value)
    if not root or not root.endswith("/"):
        return "", "origin_not_resolvable_under_published_identity"
    canonical = root[:-1]
    if canonical != value:
        return "", "origin_not_exact_canonical_origin"
    return canonical, ""


def _belongs_to_origin(evidence_key: str, origin: str) -> bool:
    return evidence_key == f"{origin}/" or evidence_key.startswith(f"{origin}/")


def _identity_value_reason(value: Any, *, origin: str, label: str) -> str:
    if not _exact_nonempty_string(value):
        return f"{label}_must_be_exact_nonempty_string"
    key = published_evidence_url_key(value, scan_origin=origin)
    if not key:
        return f"{label}_unresolvable_under_scan_origin"
    if not _belongs_to_origin(key, origin):
        return f"{label}_origin_mismatch"
    return ""


def _historical_transport_reason(previous_record: dict[str, Any], origin: str) -> str:
    affected = previous_record.get("affected_pages")
    if affected is not None:
        if not isinstance(affected, list):
            return "historical_affected_pages_not_a_list"
        if affected:
            for index, value in enumerate(affected):
                reason = _identity_value_reason(
                    value,
                    origin=origin,
                    label=f"historical_affected_pages_{index}",
                )
                if reason:
                    return reason
            return ""

    for field in ("page_url", "representative_page_url"):
        if field not in previous_record or previous_record.get(field) in (None, ""):
            continue
        return _identity_value_reason(
            previous_record.get(field),
            origin=origin,
            label=f"historical_{field}",
        )
    return "historical_evidence_identity_missing"


def _plan_transport_reason(plan: dict[str, Any], origin: str) -> str:
    requests = plan.get("requests")
    if not isinstance(requests, list) or not requests:
        return "plan_requests_missing_or_malformed"
    for index, request in enumerate(requests):
        if not isinstance(request, dict):
            return f"plan_request_{index}_not_an_object"
        reason = _identity_value_reason(
            request.get("url"),
            origin=origin,
            label=f"plan_request_{index}_url",
        )
        if reason:
            return reason
        evidence_key = request.get("evidence_key")
        if not _exact_nonempty_string(evidence_key):
            return f"plan_request_{index}_evidence_key_must_be_exact_nonempty_string"
        if not _belongs_to_origin(evidence_key, origin):
            return f"plan_request_{index}_evidence_key_origin_mismatch"
        derived = published_evidence_url_key(request["url"], scan_origin=origin)
        if derived != evidence_key:
            return f"plan_request_{index}_url_evidence_key_mismatch"
    return ""


def _current_pages_reason(current_pages: list[dict[str, Any]], origin: str) -> str:
    for index, page in enumerate(current_pages):
        populated = 0
        for field in _IDENTITY_FIELDS:
            if field not in page or page.get(field) is None:
                continue
            populated += 1
            reason = _identity_value_reason(
                page.get(field),
                origin=origin,
                label=f"current_page_{index}_{field}",
            )
            if reason:
                return reason
        if not populated:
            return f"current_page_{index}_identity_missing"
    return ""


def _rule_evaluations_reason(rule_evaluations: list[dict[str, Any]], origin: str) -> str:
    for index, row in enumerate(rule_evaluations):
        declared = row.get("evidence_key")
        if declared is not None:
            if not _exact_nonempty_string(declared):
                return f"rule_evaluation_{index}_evidence_key_must_be_exact_nonempty_string"
            if not _belongs_to_origin(declared, origin):
                return f"rule_evaluation_{index}_evidence_key_origin_mismatch"

        populated = 0
        for field in _RULE_IDENTITY_FIELDS:
            if field not in row or row.get(field) is None:
                continue
            populated += 1
            reason = _identity_value_reason(
                row.get(field),
                origin=origin,
                label=f"rule_evaluation_{index}_{field}",
            )
            if reason:
                return reason
        if declared is None and not populated:
            return f"rule_evaluation_{index}_identity_missing"
    return ""


def verification_scan_origin_binding_integrity(
    previous_record: dict[str, Any],
    plan: dict[str, Any],
    current_pages: list[dict[str, Any]],
    rule_evaluations: list[dict[str, Any]],
    *,
    previous_scan_origin: str,
    scan_origin: str,
) -> dict[str, Any]:
    """Bind all proving URL evidence to exact authoritative scan origins.

    Published URL identity deliberately accepts caller-owned scan origins so
    root-relative evidence can be resolved. That caller context is itself proof
    material: a relative page from scan B must never be re-labeled as scan A by
    passing the wrong origin. This helper therefore requires canonical origins,
    requires the historical and current origins to match for same-page repair
    verification, and rejects any historical/plan/current identity that resolves
    outside that origin before PASS/PARTIAL/FAIL can be produced.
    """
    base = {
        "version": SCAN_ORIGIN_BINDING_VERSION,
        "valid": False,
        "reason": "scan_origin_binding_not_proven",
        "previous_scan_origin": "",
        "scan_origin": "",
    }
    if not isinstance(previous_record, dict):
        return {**base, "reason": "previous_record_not_an_object"}
    if not isinstance(plan, dict):
        return {**base, "reason": "verification_plan_not_an_object"}
    if not isinstance(current_pages, list):
        return {**base, "reason": "current_pages_not_a_list"}
    if not isinstance(rule_evaluations, list):
        return {**base, "reason": "rule_evaluations_not_a_list"}
    if any(not isinstance(item, dict) for item in current_pages):
        return {**base, "reason": "current_pages_contains_non_object"}
    if any(not isinstance(item, dict) for item in rule_evaluations):
        return {**base, "reason": "rule_evaluations_contains_non_object"}

    previous_origin, previous_error = _canonical_origin(previous_scan_origin)
    if previous_error:
        return {**base, "reason": f"previous_scan_{previous_error}"}
    current_origin, current_error = _canonical_origin(scan_origin)
    if current_error:
        return {
            **base,
            "reason": f"current_scan_{current_error}",
            "previous_scan_origin": previous_origin,
        }
    base.update({
        "previous_scan_origin": previous_origin,
        "scan_origin": current_origin,
    })
    if previous_origin != current_origin:
        return {**base, "reason": "historical_and_current_scan_origins_differ"}

    reason = _historical_transport_reason(previous_record, previous_origin)
    if reason:
        return {**base, "reason": reason}
    reason = _plan_transport_reason(plan, previous_origin)
    if reason:
        return {**base, "reason": reason}
    reason = _current_pages_reason(current_pages, current_origin)
    if reason:
        return {**base, "reason": reason}
    reason = _rule_evaluations_reason(rule_evaluations, current_origin)
    if reason:
        return {**base, "reason": reason}

    return {
        **base,
        "valid": True,
        "reason": "all_proving_evidence_bound_to_exact_scan_origin",
        "checked_plan_requests": len(plan.get("requests") or []),
        "checked_current_pages": len(current_pages),
        "checked_rule_evaluations": len(rule_evaluations),
    }


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
    origin_binding: dict[str, Any],
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
        "scan_origin_binding": origin_binding,
    }


def evaluate_verification_observations_origin_bound(
    plan: dict[str, Any],
    previous_record: dict[str, Any],
    current_pages: list[dict[str, Any]],
    rule_evaluations: list[dict[str, Any]],
    current_contract: dict[str, Any],
    *,
    previous_scan_origin: str,
    scan_origin: str,
) -> dict[str, Any]:
    """Fail closed unless proving evidence is bound to one exact scan origin."""
    binding = verification_scan_origin_binding_integrity(
        previous_record,
        plan,
        current_pages,
        rule_evaluations,
        previous_scan_origin=previous_scan_origin,
        scan_origin=scan_origin,
    )
    if binding.get("valid") is not True:
        return _could_not_verify(
            plan if isinstance(plan, dict) else {},
            "Scan-origin binding integrity failed: "
            f"{binding.get('reason') or 'not_proven'}",
            origin_binding=binding,
        )

    result = evaluate_verification_observations_historical_bound(
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
            "Historical-bound verification evaluator returned non-object evidence.",
            origin_binding=binding,
        )
    return {
        **result,
        "scan_origin_binding": binding,
    }
