import copy

import pytest

from app.missing_h1_comparison_contract import (
    MISSING_H1_COMPARISON_PROFILE_VERSION,
    MISSING_H1_REMEDIATION_FAMILY,
    MISSING_H1_REPAIR_SURFACE,
    MISSING_H1_RULE,
    MISSING_H1_RULE_DEFINITION_VERSION,
)
from app.repair_coverage import PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION
from app.targeted_fix_verification import (
    TARGETED_FIX_VERIFICATION_OBSERVATION_VERSION,
    build_rule_evaluation_receipt,
    build_targeted_recheck_plan,
)
from app.targeted_fix_verification_evidence_integrity import (
    TARGETED_FIX_VERIFICATION_EVIDENCE_INTEGRITY_VERSION,
    strict_evaluate_targeted_fix_verification,
    validate_recheck_evidence_integrity,
)

ORIGIN = "https://example.com"
RULE_VERSION = MISSING_H1_RULE_DEFINITION_VERSION
PROFILE_VERSION = MISSING_H1_COMPARISON_PROFILE_VERSION


def repair(urls=None, **overrides):
    value = {
        "rule": MISSING_H1_RULE,
        "category": "thin_content",
        "repair_surface": MISSING_H1_REPAIR_SURFACE,
        "remediation_family": MISSING_H1_REMEDIATION_FAMILY,
        "affected_pages": urls or ["/a", "/b"],
        "rule_definition_version": RULE_VERSION,
        "comparison_profile_version": PROFILE_VERSION,
        "evidence_url_identity_version": PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION,
    }
    value.update(overrides)
    return value


def contract(**overrides):
    value = {
        "rule_definition_version": RULE_VERSION,
        "comparison_profile_version": PROFILE_VERSION,
        "evidence_url_identity_version": PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION,
    }
    value.update(overrides)
    return value


def ready_plan(sealed=None):
    return build_targeted_recheck_plan(
        sealed or repair(),
        source_scan_id="scan-old",
        source_scan_origin=ORIGIN,
    )


def observed(plan, key, **page_overrides):
    page = {
        "url": key,
        "status_code": 200,
        "content_type": "text/html; charset=utf-8",
        "page_evidence_class": "usable_html",
        "raw_html_truncated": False,
        "robots_txt_fetch_allowed": True,
        "access_block_kind": "",
        "fetch_error": "",
        "indexable": True,
        "comparison_rule_evaluation": {
            "rule": MISSING_H1_RULE,
            "rule_definition_version": MISSING_H1_RULE_DEFINITION_VERSION,
            "comparison_profile_version": MISSING_H1_COMPARISON_PROFILE_VERSION,
            "evaluated": True,
            "applicable": True,
            "finding_present": False,
        },
    }
    page.update(page_overrides)
    return {
        "version": TARGETED_FIX_VERIFICATION_OBSERVATION_VERSION,
        "plan_fingerprint": plan["plan_fingerprint"],
        "evidence_key": key,
        "state": "observed",
        "page": page,
    }


def not_verified(plan, key, reason):
    return {
        "version": TARGETED_FIX_VERIFICATION_OBSERVATION_VERSION,
        "plan_fingerprint": plan["plan_fingerprint"],
        "evidence_key": key,
        "state": "not_verified",
        "reason": reason,
    }


def strict_evaluate(plan, sealed, *, current_fixes=None, outcomes=None, current_contract=None):
    current_fixes = [] if current_fixes is None else current_fixes
    outcomes = outcomes if outcomes is not None else [observed(plan, row["evidence_key"]) for row in plan["requests"]]
    receipt = build_rule_evaluation_receipt(plan, current_fixes)
    return strict_evaluate_targeted_fix_verification(
        plan,
        sealed,
        current_scan_origin=ORIGIN,
        current_contract=current_contract or contract(),
        recheck_outcomes=outcomes,
        current_fixes=current_fixes,
        rule_evaluation_receipt=receipt,
    )


def test_complete_safe_page_evidence_delegates_to_canonical_pass():
    sealed = repair()
    plan = ready_plan(sealed)
    result = strict_evaluate(plan, sealed)
    assert result["state"] == "PASS"
    assert result["evidence_integrity_version"] == TARGETED_FIX_VERIFICATION_EVIDENCE_INTEGRITY_VERSION
    assert {row["comparator_state"] for row in result["page_results"]} == {"verified_fixed"}


def test_partial_and_fail_states_still_come_from_existing_comparator():
    sealed = repair()
    plan = ready_plan(sealed)
    partial = strict_evaluate(plan, sealed, current_fixes=[repair(["/a"])])
    failed = strict_evaluate(plan, sealed, current_fixes=[repair(["/a", "/b"])])
    assert partial["state"] == "PARTIAL"
    assert failed["state"] == "FAIL"


def test_regression_reopen_semantics_are_preserved_without_historical_mutation():
    sealed = repair(verification_state="verified_fixed")
    snapshot = copy.deepcopy(sealed)
    plan = ready_plan(sealed)
    result = strict_evaluate(plan, sealed, current_fixes=[repair(["/a", "/b"])])
    assert result["state"] == "FAIL"
    assert result["reopen_regression"] is True
    assert result["regression_evidence_keys"] == ["https://example.com/a", "https://example.com/b"]
    assert sealed == snapshot


def test_disappeared_url_is_never_proof_of_fix_under_strict_gate():
    sealed = repair()
    plan = ready_plan(sealed)
    only_first = observed(plan, plan["requests"][0]["evidence_key"])
    result = strict_evaluate(plan, sealed, outcomes=[only_first])
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "one_or_more_planned_urls_were_not_observed"


@pytest.mark.parametrize(
    "page_overrides,reason",
    [
        ({"robots_txt_fetch_allowed": False}, "robots_denied"),
        ({"robots_txt_fetch_allowed": None}, "robots_evidence_ambiguous"),
        ({"access_block_kind": "challenge"}, "challenge"),
        ({"access_block_kind": "block"}, "blocked"),
        ({"access_block_kind": "rate_limit"}, "rate_limited"),
        ({"access_block_kind": "mystery_gate"}, "access_block_kind_ambiguous"),
        ({"fetch_error": "connection reset"}, "fetch_failed"),
        ({"raw_html_truncated": True}, "body_limit_exceeded"),
        ({"raw_html_truncated": None}, "raw_html_truncation_state_ambiguous"),
        ({"status_code": 403}, "observed_page_not_2xx"),
        ({"status_code": "200"}, "observed_page_status_ambiguous"),
        ({"content_type": "application/json"}, "observed_page_not_html"),
        ({"page_evidence_class": "failed_access"}, "observed_page_evidence_not_usable"),
    ],
)
def test_ambiguous_or_unsafe_observed_page_evidence_is_could_not_verify(page_overrides, reason):
    sealed = repair(["/a"])
    plan = ready_plan(sealed)
    key = plan["requests"][0]["evidence_key"]
    result = strict_evaluate(plan, sealed, outcomes=[observed(plan, key, **page_overrides)])
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == reason
    assert result["blocked_evidence_key"] == key


def test_missing_robots_evidence_is_could_not_verify_never_pass():
    sealed = repair(["/a"])
    plan = ready_plan(sealed)
    key = plan["requests"][0]["evidence_key"]
    outcome = observed(plan, key)
    del outcome["page"]["robots_txt_fetch_allowed"]
    result = strict_evaluate(plan, sealed, outcomes=[outcome])
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "robots_evidence_missing"


def test_explicit_timeout_and_budget_uncertainty_remain_could_not_verify():
    sealed = repair()
    plan = ready_plan(sealed)
    first, second = [row["evidence_key"] for row in plan["requests"]]
    timeout = strict_evaluate(plan, sealed, outcomes=[not_verified(plan, first, "timeout"), observed(plan, second)])
    budget = strict_evaluate(plan, sealed, outcomes=[not_verified(plan, first, "request_budget_exhausted"), observed(plan, second)])
    assert timeout["state"] == "COULD_NOT_VERIFY"
    assert timeout["reason"] == "timeout"
    assert budget["state"] == "COULD_NOT_VERIFY"
    assert budget["reason"] == "request_budget_exhausted"


def test_rule_version_mismatch_still_fails_closed_after_evidence_gate():
    sealed = repair()
    plan = ready_plan(sealed)
    result = strict_evaluate(plan, sealed, current_contract=contract(rule_definition_version="missing_h1_v4"))
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "current_comparison_contract_mismatch"


def test_not_verified_transport_cannot_smuggle_page_evidence():
    sealed = repair(["/a"])
    plan = ready_plan(sealed)
    key = plan["requests"][0]["evidence_key"]
    outcome = not_verified(plan, key, "robots_denied")
    outcome["page"] = observed(plan, key)["page"]
    result = strict_evaluate(plan, sealed, outcomes=[outcome])
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "not_verified_outcome_carries_page_evidence"


def test_observed_transport_cannot_carry_conflicting_reason_or_outside_scope():
    sealed = repair(["/a"])
    plan = ready_plan(sealed)
    key = plan["requests"][0]["evidence_key"]
    conflict = observed(plan, key)
    conflict["reason"] = "timeout"
    conflict_result = strict_evaluate(plan, sealed, outcomes=[conflict])
    assert conflict_result["state"] == "COULD_NOT_VERIFY"
    assert conflict_result["reason"] == "observed_outcome_reason_conflict"

    outside = observed(plan, key)
    outside["evidence_key"] = "https://example.com/not-sealed"
    outside_result = strict_evaluate(plan, sealed, outcomes=[outside])
    assert outside_result["state"] == "COULD_NOT_VERIFY"
    assert outside_result["reason"] == "recheck_outcome_outside_planned_scope"


def test_integrity_validator_reports_complete_transport_counts_without_deciding_repair_truth():
    sealed = repair()
    plan = ready_plan(sealed)
    first, second = [row["evidence_key"] for row in plan["requests"]]
    check = validate_recheck_evidence_integrity(
        plan,
        [observed(plan, first), not_verified(plan, second, "challenge")],
    )
    assert check["state"] == "valid"
    assert check["observed_count"] == 1
    assert check["not_verified_count"] == 1
