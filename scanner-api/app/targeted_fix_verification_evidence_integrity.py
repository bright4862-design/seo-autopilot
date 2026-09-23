from __future__ import annotations

from typing import Any

from .targeted_fix_verification import (
    TARGETED_FIX_VERIFICATION_OBSERVATION_VERSION,
    TARGETED_FIX_VERIFICATION_PLAN_VERSION,
    _could_not_verify,
    evaluate_targeted_fix_verification,
)

TARGETED_FIX_VERIFICATION_EVIDENCE_INTEGRITY_VERSION = (
    "targeted_fix_verification_evidence_integrity_v1_complete_usable_html"
)

_ACCESS_BLOCK_REASONS = {
    "challenge": "challenge",
    "block": "blocked",
    "rate_limit": "rate_limited",
    "robots_denied": "robots_denied",
}


def _exact_nonempty_string(value: Any) -> str:
    return value if isinstance(value, str) and value and value == value.strip() else ""


def _exact_optional_string(value: Any) -> str | None:
    if value is None:
        return ""
    if not isinstance(value, str) or value != value.strip():
        return None
    return value


def _exact_status_code(page: dict[str, Any]) -> int | None:
    if "status_code" in page:
        value = page.get("status_code")
    elif "status" in page:
        value = page.get("status")
    else:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _observed_page_blocker(page: Any) -> str:
    """Return a fail-closed blocker for proof-bearing targeted page evidence.

    This is intentionally stricter than the canonical repair comparator. It does
    not decide whether a repair is fixed; it only prevents incomplete, challenged,
    robots-ambiguous, truncated, or otherwise unsafe fetch evidence from reaching
    the comparator as if it were a normal re-observation.
    """
    if not isinstance(page, dict):
        return "observed_page_evidence_missing"

    if "robots_txt_fetch_allowed" not in page:
        return "robots_evidence_missing"
    robots_allowed = page.get("robots_txt_fetch_allowed")
    if robots_allowed is False:
        return "robots_denied"
    if robots_allowed is not True:
        return "robots_evidence_ambiguous"

    access_kind = _exact_optional_string(page.get("access_block_kind"))
    if access_kind is None:
        return "access_block_kind_ambiguous"
    if access_kind:
        mapped = _ACCESS_BLOCK_REASONS.get(access_kind)
        return mapped or "access_block_kind_ambiguous"

    fetch_error = _exact_optional_string(page.get("fetch_error"))
    if fetch_error is None:
        return "fetch_error_transport_ambiguous"
    if fetch_error:
        return "fetch_failed"

    truncated = page.get("raw_html_truncated")
    if truncated is True:
        return "body_limit_exceeded"
    if truncated is not False:
        return "raw_html_truncation_state_ambiguous"

    status = _exact_status_code(page)
    if status is None:
        return "observed_page_status_ambiguous"
    if status < 200 or status >= 300:
        return "observed_page_not_2xx"

    content_type = _exact_nonempty_string(page.get("content_type") or page.get("mime_type"))
    if not content_type:
        return "observed_page_content_type_missing"
    media_type = content_type.split(";", 1)[0].strip().lower()
    if media_type not in {"text/html", "application/xhtml+xml"}:
        return "observed_page_not_html"

    evidence_class = _exact_nonempty_string(
        page.get("page_evidence_class") or page.get("evidence_class")
    )
    if not evidence_class:
        return "observed_page_evidence_class_missing"
    if evidence_class != "usable_html":
        return "observed_page_evidence_not_usable"

    return ""


def validate_recheck_evidence_integrity(
    plan: Any,
    recheck_outcomes: Any,
) -> dict[str, Any]:
    """Validate exact fail-closed evidence preconditions before comparison.

    Explicit ``not_verified`` outcomes are valid transport because the canonical
    evaluator will map them to COULD_NOT_VERIFY. Only an ``observed`` outcome can
    proceed as proof-bearing page evidence, and that page must carry complete
    usable-HTML and robots/access evidence.
    """
    base = {
        "version": TARGETED_FIX_VERIFICATION_EVIDENCE_INTEGRITY_VERSION,
        "state": "could_not_verify",
        "reason": "recheck_evidence_integrity_unavailable",
        "blocked_evidence_key": "",
        "observed_count": 0,
        "not_verified_count": 0,
    }
    if not isinstance(plan, dict):
        return {**base, "reason": "verification_plan_invalid"}
    if plan.get("version") != TARGETED_FIX_VERIFICATION_PLAN_VERSION or plan.get("state") != "ready":
        return {**base, "reason": "verification_plan_not_ready"}
    plan_fingerprint = _exact_nonempty_string(plan.get("plan_fingerprint"))
    if not plan_fingerprint:
        return {**base, "reason": "verification_plan_fingerprint_missing"}

    requests = plan.get("requests")
    if not isinstance(requests, list) or not requests:
        return {**base, "reason": "verification_plan_requests_invalid"}
    expected_keys: list[str] = []
    for row in requests:
        if not isinstance(row, dict):
            return {**base, "reason": "verification_plan_request_transport_invalid"}
        key = _exact_nonempty_string(row.get("evidence_key"))
        if not key:
            return {**base, "reason": "verification_plan_request_identity_invalid"}
        if key in expected_keys:
            return {**base, "reason": "verification_plan_duplicate_request_identity"}
        expected_keys.append(key)

    if not isinstance(recheck_outcomes, list):
        return {**base, "reason": "recheck_outcomes_invalid"}

    seen: set[str] = set()
    observed_count = 0
    not_verified_count = 0
    for outcome in recheck_outcomes:
        if not isinstance(outcome, dict):
            return {**base, "reason": "recheck_outcome_transport_invalid"}
        if outcome.get("version") != TARGETED_FIX_VERIFICATION_OBSERVATION_VERSION:
            return {**base, "reason": "recheck_outcome_version_mismatch"}
        if outcome.get("plan_fingerprint") != plan_fingerprint:
            return {**base, "reason": "recheck_outcome_plan_mismatch"}

        key = _exact_nonempty_string(outcome.get("evidence_key"))
        if key not in expected_keys:
            return {
                **base,
                "reason": "recheck_outcome_outside_planned_scope",
                "blocked_evidence_key": key,
            }
        if key in seen:
            return {
                **base,
                "reason": "duplicate_recheck_outcome",
                "blocked_evidence_key": key,
            }
        seen.add(key)

        state = outcome.get("state")
        if state == "not_verified":
            not_verified_count += 1
            if not _exact_nonempty_string(outcome.get("reason")):
                return {
                    **base,
                    "reason": "not_verified_reason_missing",
                    "blocked_evidence_key": key,
                }
            if "page" in outcome:
                return {
                    **base,
                    "reason": "not_verified_outcome_carries_page_evidence",
                    "blocked_evidence_key": key,
                }
            continue
        if state != "observed":
            return {
                **base,
                "reason": "recheck_outcome_state_invalid",
                "blocked_evidence_key": key,
            }
        if "reason" in outcome and _exact_optional_string(outcome.get("reason")) != "":
            return {
                **base,
                "reason": "observed_outcome_reason_conflict",
                "blocked_evidence_key": key,
            }

        blocker = _observed_page_blocker(outcome.get("page"))
        if blocker:
            return {
                **base,
                "reason": blocker,
                "blocked_evidence_key": key,
            }
        observed_count += 1

    if seen != set(expected_keys):
        missing = sorted(set(expected_keys) - seen)
        return {
            **base,
            "reason": "one_or_more_planned_urls_were_not_observed",
            "blocked_evidence_key": missing[0] if missing else "",
            "observed_count": observed_count,
            "not_verified_count": not_verified_count,
        }

    return {
        **base,
        "state": "valid",
        "reason": "complete_fail_closed_recheck_evidence",
        "observed_count": observed_count,
        "not_verified_count": not_verified_count,
    }


def strict_evaluate_targeted_fix_verification(
    plan: dict[str, Any],
    sealed_repair: dict[str, Any],
    *,
    current_scan_origin: str,
    current_contract: dict[str, Any] | None,
    recheck_outcomes: list[dict[str, Any]],
    current_fixes: list[dict[str, Any]],
    rule_evaluation_receipt: dict[str, Any] | None,
) -> dict[str, Any]:
    """Fail closed on fetch/evidence ambiguity, then delegate truth to the comparator.

    PASS/PARTIAL/FAIL remain owned by ``evaluate_targeted_fix_verification`` and
    ultimately ``compare_repair_runs``. This wrapper adds only a stricter evidence
    admission gate so unsafe or incomplete page transport can never become PASS.
    """
    integrity = validate_recheck_evidence_integrity(plan, recheck_outcomes)
    if integrity.get("state") != "valid":
        return _could_not_verify(
            plan,
            str(integrity.get("reason") or "recheck_evidence_integrity_unavailable"),
            blocked_evidence_key=integrity.get("blocked_evidence_key", ""),
            evidence_integrity_version=TARGETED_FIX_VERIFICATION_EVIDENCE_INTEGRITY_VERSION,
        )

    result = evaluate_targeted_fix_verification(
        plan,
        sealed_repair,
        current_scan_origin=current_scan_origin,
        current_contract=current_contract,
        recheck_outcomes=recheck_outcomes,
        current_fixes=current_fixes,
        rule_evaluation_receipt=rule_evaluation_receipt,
    )
    return {
        **result,
        "evidence_integrity_version": TARGETED_FIX_VERIFICATION_EVIDENCE_INTEGRITY_VERSION,
    }
