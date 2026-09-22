from __future__ import annotations

from typing import Any

from .nextgen_fix_verification import (
    ACCEPTANCE_CRITERION_VERSION,
    MAX_RECHECK_URLS,
    VERIFICATION_PLAN_VERSION,
)

PLAN_ENVELOPE_INTEGRITY_VERSION = (
    "fix_verification_plan_envelope_integrity_v1_exact_ready_invariants"
)


def _strict_nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _strict_positive_int(value: Any) -> int | None:
    parsed = _strict_nonnegative_int(value)
    return parsed if parsed is not None and parsed > 0 else None


def _exact_empty_list(value: Any) -> bool:
    return isinstance(value, list) and not value


def verification_plan_envelope_integrity(plan: dict[str, Any]) -> dict[str, Any]:
    """Require an internally consistent, ready-to-prove targeted recheck envelope.

    The core evaluator separately binds the plan to the authoritative historical
    population and request identities. This boundary closes a transport gap in
    the plan's own readiness metadata: a plan marked ``ready`` must not carry
    blockers, invalid/omitted evidence, contradictory counts or limits, or a
    blocked criterion and still participate in proof.
    """
    base = {
        "version": PLAN_ENVELOPE_INTEGRITY_VERSION,
        "valid": False,
        "reason": "verification_plan_envelope_not_proven",
    }
    if not isinstance(plan, dict):
        return {**base, "reason": "verification_plan_not_an_object"}
    if plan.get("version") != VERIFICATION_PLAN_VERSION:
        return {**base, "reason": "unsupported_verification_plan_version"}
    if plan.get("state") != "ready":
        return {**base, "reason": "verification_plan_not_ready"}
    if plan.get("population_complete") is not True:
        return {**base, "reason": "verification_plan_population_not_explicitly_complete"}
    if not _exact_empty_list(plan.get("blockers")):
        return {**base, "reason": "verification_plan_ready_state_has_blockers"}

    population_count = _strict_positive_int(plan.get("population_count"))
    if population_count is None:
        return {**base, "reason": "verification_plan_population_count_invalid"}
    invalid_count = _strict_nonnegative_int(plan.get("invalid_population_count"))
    if invalid_count is None:
        return {**base, "reason": "verification_plan_invalid_population_count_invalid"}
    if invalid_count != 0:
        return {**base, "reason": "verification_plan_ready_state_has_invalid_population"}
    omitted_count = _strict_nonnegative_int(plan.get("omitted_population_count"))
    if omitted_count is None:
        return {**base, "reason": "verification_plan_omitted_population_count_invalid"}
    if omitted_count != 0:
        return {**base, "reason": "verification_plan_ready_state_has_omitted_population"}

    max_recheck_urls = _strict_positive_int(plan.get("max_recheck_urls"))
    if max_recheck_urls is None or max_recheck_urls > MAX_RECHECK_URLS:
        return {**base, "reason": "verification_plan_max_recheck_urls_invalid"}
    if population_count > max_recheck_urls:
        return {**base, "reason": "verification_plan_population_exceeds_declared_limit"}

    requests = plan.get("requests")
    if not isinstance(requests, list) or not requests:
        return {**base, "reason": "verification_plan_requests_missing_or_malformed"}
    if len(requests) != population_count:
        return {**base, "reason": "verification_plan_request_count_mismatch"}

    criterion = plan.get("criterion")
    if not isinstance(criterion, dict):
        return {**base, "reason": "verification_plan_criterion_not_an_object"}
    if criterion.get("version") != ACCEPTANCE_CRITERION_VERSION:
        return {**base, "reason": "unsupported_acceptance_criterion_version"}
    if criterion.get("state") != "ready":
        return {**base, "reason": "acceptance_criterion_not_ready"}
    if not _exact_empty_list(criterion.get("blockers")):
        return {**base, "reason": "acceptance_criterion_ready_state_has_blockers"}

    return {
        **base,
        "valid": True,
        "reason": "ready_plan_envelope_invariants_proven",
        "population_count": population_count,
        "max_recheck_urls": max_recheck_urls,
        "request_count": len(requests),
    }
