import copy

import pytest

from app.coverage_probes import COVERAGE_PROBE_SCHEDULER_VERSION
from app.repair_coverage import PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION
from app.repair_identity import REPAIR_VERIFICATION_VERSION, build_repair_identity
from app.targeted_fix_verification import (
    MAX_TARGETED_RECHECK_URLS,
    TARGETED_FIX_VERIFICATION_OBSERVATION_VERSION,
    TARGETED_FIX_VERIFICATION_PLAN_VERSION,
    TARGETED_FIX_VERIFICATION_RESULT_VERSION,
    build_rule_evaluation_receipt,
    build_targeted_recheck_plan,
    build_verification_criteria,
    evaluate_targeted_fix_verification,
    targeted_verification_budget_proposal,
)

ORIGIN = "https://example.com"
RULE_VERSION = "missing_h1_v3"
PROFILE_VERSION = "standard150_review_v8"


def repair(urls=None, **overrides):
    value = {
        "rule": "missing_h1",
        "category": "thin_content",
        "repair_surface": "product_template",
        "remediation_family": "add_single_h1",
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


def ready_plan(sealed=None, **kwargs):
    return build_targeted_recheck_plan(
        sealed or repair(),
        source_scan_id="scan-old",
        source_scan_origin=ORIGIN,
        **kwargs,
    )


def observed(plan, key, **page_overrides):
    page = {"url": key, "status_code": 200, "content_type": "text/html", "page_evidence_class": "usable_html"}
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


def evaluate(plan, sealed, current_fixes=None, outcomes=None, receipt=None, **kwargs):
    current_fixes = [] if current_fixes is None else current_fixes
    outcomes = outcomes if outcomes is not None else [observed(plan, row["evidence_key"]) for row in plan["requests"]]
    receipt = receipt if receipt is not None else build_rule_evaluation_receipt(plan, current_fixes)
    return evaluate_targeted_fix_verification(
        plan,
        sealed,
        current_scan_origin=kwargs.pop("current_scan_origin", ORIGIN),
        current_contract=kwargs.pop("current_contract", contract()),
        recheck_outcomes=outcomes,
        current_fixes=current_fixes,
        rule_evaluation_receipt=receipt,
        **kwargs,
    )


def test_criteria_are_versioned_machine_testable_and_bound_to_stable_identity():
    sealed = repair()
    criteria = build_verification_criteria(sealed, source_scan_id="scan-old", source_scan_origin=ORIGIN)
    assert criteria["state"] == "ready"
    assert criteria["repair_fingerprint"] == build_repair_identity(sealed)["fingerprint"]
    assert criteria["affected_evidence_keys"] == ["https://example.com/a", "https://example.com/b"]
    assert set(criteria["acceptance"]) == {"PASS", "PARTIAL", "FAIL", "COULD_NOT_VERIFY"}
    assert len(criteria["criteria_fingerprint"]) == 64


@pytest.mark.parametrize(
    "override,blocker",
    [
        ({"repair_surface": ""}, "stable_repair_identity_required"),
        ({"rule_definition_version": ""}, "rule_definition_version_required"),
        ({"comparison_profile_version": ""}, "comparison_profile_version_required"),
        ({"evidence_url_identity_version": "legacy"}, "published_evidence_url_identity_required"),
    ],
)
def test_criteria_fail_closed_on_identity_or_version_ambiguity(override, blocker):
    criteria = build_verification_criteria(repair(**override), source_scan_id="scan-old", source_scan_origin=ORIGIN)
    assert criteria["state"] == "could_not_verify"
    assert blocker in criteria["blockers"]


def test_plan_is_exact_complete_sealed_population_and_bounded():
    plan = ready_plan()
    assert plan["version"] == TARGETED_FIX_VERIFICATION_PLAN_VERSION
    assert plan["state"] == "ready"
    assert plan["population_complete"] is True
    assert plan["sealed_population_count"] == 2
    assert plan["selected_population_count"] == 2
    assert plan["max_targeted_urls"] <= MAX_TARGETED_RECHECK_URLS
    assert [r["url"] for r in plan["requests"]] == ["https://example.com/a", "https://example.com/b"]


@pytest.mark.parametrize(
    "requested,blocker",
    [
        (["https://evil.example/a"], "requested_url_expands_source_origin"),
        (["/a", "/not-sealed"], "requested_url_outside_sealed_repair_set"),
        (["/a", "/a"], "duplicate_requested_url"),
    ],
)
def test_plan_rejects_host_scope_expansion_and_duplicate_abuse(requested, blocker):
    plan = ready_plan(requested_urls=requested)
    assert plan["state"] == "rejected"
    assert plan["requests"] == []
    assert blocker in plan["blockers"]


def test_subset_cannot_become_authoritative_verification_population():
    plan = ready_plan(requested_urls=["/a"])
    assert plan["state"] == "could_not_verify"
    assert plan["population_complete"] is False
    assert "selected_population_is_not_complete_repair_set" in plan["blockers"]


def test_large_sealed_repair_is_not_auto_truncated_into_false_pass_scope():
    sealed = repair([f"/p/{i}" for i in range(MAX_TARGETED_RECHECK_URLS + 1)])
    plan = ready_plan(sealed)
    assert plan["state"] == "could_not_verify"
    assert plan["requests"] == []
    assert "sealed_repair_population_exceeds_targeted_bound" in plan["blockers"]


def test_budget_proposal_reuses_shared_scheduler_contract_without_new_pool():
    plan = ready_plan()
    proposal = targeted_verification_budget_proposal(
        plan,
        {
            "version": COVERAGE_PROBE_SCHEDULER_VERSION,
            "request_budget": {"requests_remaining": 3, "budget_exhausted": False, "deadline_exhausted": False},
        },
    )
    assert proposal["state"] == "fits"
    assert proposal["required_new_request_upper_bound"] == 2


@pytest.mark.parametrize(
    "budget,reason",
    [
        ({"requests_remaining": 1, "budget_exhausted": False, "deadline_exhausted": False}, "shared_request_budget_insufficient"),
        ({"requests_remaining": 2, "budget_exhausted": True, "deadline_exhausted": False}, "shared_request_budget_insufficient"),
        ({"requests_remaining": 2, "budget_exhausted": False, "deadline_exhausted": True}, "deadline_exhausted"),
    ],
)
def test_budget_uncertainty_is_never_fit(budget, reason):
    result = targeted_verification_budget_proposal(ready_plan(), {"version": COVERAGE_PROBE_SCHEDULER_VERSION, "request_budget": budget})
    assert result["state"] == "could_not_verify"
    assert result["reason"] == reason


def test_all_urls_fixed_maps_canonical_comparator_to_pass():
    sealed = repair()
    plan = ready_plan(sealed)
    result = evaluate(plan, sealed)
    assert result["version"] == TARGETED_FIX_VERIFICATION_RESULT_VERSION
    assert result["state"] == "PASS"
    assert {row["comparator_state"] for row in result["page_results"]} == {"verified_fixed"}
    assert {row["comparator_version"] for row in result["page_results"]} == {REPAIR_VERIFICATION_VERSION}
    assert result["reopen_regression"] is False


def test_one_url_still_detected_and_one_fixed_is_partial():
    sealed = repair()
    plan = ready_plan(sealed)
    current = [repair(["/a"])]
    result = evaluate(plan, sealed, current_fixes=current)
    assert result["state"] == "PARTIAL"
    assert result["verified_url_count"] == 1
    assert result["failed_url_count"] == 1


def test_all_urls_still_detected_is_fail():
    sealed = repair()
    plan = ready_plan(sealed)
    current = [repair(["/a", "/b"])]
    result = evaluate(plan, sealed, current_fixes=current)
    assert result["state"] == "FAIL"
    assert result["failed_url_count"] == 2
    assert result["reopen_regression"] is False


def test_previously_verified_fixed_reappearance_signals_regression_reopen_without_mutation():
    sealed = repair(verification_state="verified_fixed")
    plan = ready_plan(sealed)
    current = [repair(["/a", "/b"])]
    result = evaluate(plan, sealed, current_fixes=current)
    assert result["state"] == "FAIL"
    assert result["reopen_regression"] is True
    assert result["regression_evidence_keys"] == ["https://example.com/a", "https://example.com/b"]
    assert sealed["verification_state"] == "verified_fixed"


def test_disappeared_url_is_never_proof_of_fix():
    sealed = repair()
    plan = ready_plan(sealed)
    outcomes = [observed(plan, plan["requests"][0]["evidence_key"])]
    result = evaluate(plan, sealed, outcomes=outcomes)
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "one_or_more_planned_urls_were_not_observed"


@pytest.mark.parametrize("reason", ["robots_denied", "challenge", "rate_limited", "timeout", "request_budget_exhausted", "deadline_exhausted"])
def test_access_and_budget_uncertainty_are_could_not_verify_never_pass(reason):
    sealed = repair()
    plan = ready_plan(sealed)
    first, second = [row["evidence_key"] for row in plan["requests"]]
    outcomes = [not_verified(plan, first, reason), observed(plan, second)]
    result = evaluate(plan, sealed, outcomes=outcomes)
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == reason


def test_failed_access_page_is_delegated_to_comparator_and_cannot_pass():
    sealed = repair(["/a"])
    plan = ready_plan(sealed)
    key = plan["requests"][0]["evidence_key"]
    result = evaluate(plan, sealed, outcomes=[observed(plan, key, status_code=403, page_evidence_class="failed_access")])
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "canonical_comparator_could_not_verify"


def test_rule_version_drift_is_could_not_verify():
    sealed = repair()
    plan = ready_plan(sealed)
    result = evaluate(plan, sealed, current_contract=contract(rule_definition_version="missing_h1_v4"))
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "current_comparison_contract_mismatch"


def test_current_origin_drift_is_could_not_verify():
    sealed = repair()
    plan = ready_plan(sealed)
    result = evaluate(plan, sealed, current_scan_origin="https://other.example")
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "current_scan_origin_mismatch"


def test_rule_evaluation_receipt_is_required_for_empty_current_fix_population():
    sealed = repair()
    plan = ready_plan(sealed)
    result = evaluate_targeted_fix_verification(
        plan,
        sealed,
        current_scan_origin=ORIGIN,
        current_contract=contract(),
        recheck_outcomes=[observed(plan, r["evidence_key"]) for r in plan["requests"]],
        current_fixes=[],
        rule_evaluation_receipt=None,
    )
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "rule_evaluation_receipt_missing"


def test_nonserializable_current_fix_transport_fails_closed_before_rule_absence_can_prove_pass():
    sealed = repair(["/a"])
    plan = ready_plan(sealed)
    current = [{"opaque": object()}]
    receipt = build_rule_evaluation_receipt(plan, current)
    result = evaluate(plan, sealed, current_fixes=current, receipt=receipt)
    assert receipt["state"] == "could_not_verify"
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "current_fix_population_transport_not_serializable"


def test_rule_evaluation_receipt_tampering_is_could_not_verify():
    sealed = repair()
    plan = ready_plan(sealed)
    receipt = build_rule_evaluation_receipt(plan, [])
    receipt["population_complete"] = False
    result = evaluate(plan, sealed, receipt=receipt)
    assert result["state"] == "COULD_NOT_VERIFY"
    assert "rule_evaluation_receipt_population_complete_mismatch" == result["reason"]


def test_extra_or_duplicate_observation_cannot_expand_execution_scope():
    sealed = repair()
    plan = ready_plan(sealed)
    outcomes = [observed(plan, r["evidence_key"]) for r in plan["requests"]]
    extra = copy.deepcopy(outcomes[0])
    extra["evidence_key"] = "https://example.com/not-sealed"
    assert evaluate(plan, sealed, outcomes=[*outcomes, extra])["reason"] == "recheck_outcome_outside_planned_scope"
    assert evaluate(plan, sealed, outcomes=[*outcomes, copy.deepcopy(outcomes[0])])["reason"] == "duplicate_recheck_outcome"


def test_observation_page_identity_must_exactly_match_planned_evidence_key():
    sealed = repair(["/a"])
    plan = ready_plan(sealed)
    key = plan["requests"][0]["evidence_key"]
    result = evaluate(plan, sealed, outcomes=[observed(plan, key, url="https://example.com/A")])
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "observed_page_identity_mismatch"


def test_matching_current_fix_cannot_expand_beyond_sealed_repair_scope():
    sealed = repair(["/a"])
    plan = ready_plan(sealed)
    current = [repair(["/a", "/not-sealed"])]
    result = evaluate(plan, sealed, current_fixes=current)
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "matching_current_fix_expands_sealed_repair_scope"


def test_matching_current_fix_identity_conflict_fails_closed():
    sealed = repair(["/a"])
    plan = ready_plan(sealed)
    current = repair(["/a"], repair_fingerprint="0" * 24)
    result = evaluate(plan, sealed, current_fixes=[current])
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "current_fix_identity_conflict"


def test_stable_previous_provisional_current_same_fingerprint_cannot_be_fixed():
    sealed = repair(["/a"])
    plan = ready_plan(sealed)
    current = {
        "rule": "missing_h1",
        "affected_pages": ["/a"],
        "repair_fingerprint": plan["repair_fingerprint"],
    }

    assert build_repair_identity(sealed)["stable"] is True
    assert build_repair_identity(current)["stable"] is False

    result = evaluate(plan, sealed, current_fixes=[current])
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "current_fix_identity_conflict"


def test_unrelated_provisional_or_conflicting_persistence_row_does_not_poison_target():
    sealed = repair(["/a"])
    plan = ready_plan(sealed)
    unrelated = {
        **repair(["/elsewhere"], rule="missing_meta_description", repair_surface="product_template", remediation_family="add_meta_description"),
        "repair_fingerprint": "f" * 24,
    }
    result = evaluate(plan, sealed, current_fixes=[unrelated])
    assert result["state"] == "PASS"


def test_plan_transport_tamper_fails_closed_before_evaluation():
    sealed = repair()
    plan = ready_plan(sealed)
    plan["requests"][0]["url"] = "https://example.com/tampered"
    result = evaluate(plan, sealed)
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "verification_plan_fingerprint_mismatch"
