from copy import deepcopy

from app.nextgen_fix_verification import COULD_NOT_VERIFY, FAIL, PARTIAL, PASS
from app.nextgen_fix_verification_execution_binding import (
    PLAN_EXECUTION_BINDING_VERSION,
    STRICT_REGRESSION_REOPEN_PLAN_EXECUTION_BOUND_VERSION,
    STRICT_VERIFIED_FIXED_PLAN_EXECUTION_BOUND_VERSION,
    strict_regression_reopen_from_execution_bound_observations,
    strict_verified_fixed_transition_from_execution_bound_observations,
    verification_plan_execution_binding_integrity,
)
from app.nextgen_fix_verification_plan_identity import (
    PLAN_IDENTITY_BINDING_VERSION,
    build_identity_bound_targeted_recheck_plan,
)
from app.repair_coverage import PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION

ORIGIN = "https://example.com"
PREVIOUS_SCAN_ID = "scan-prev-001"
CURRENT_SCAN_ID = "scan-current-002"


def fix(**overrides):
    base = {
        "scan_run_id": PREVIOUS_SCAN_ID,
        "rule": "missing_meta_description",
        "category": "meta_description",
        "repair_surface": "product_template",
        "remediation_family": "add_meta_description",
        "affected_pages": ["/a", "/b"],
        "rule_definition_version": "missing_meta_description_v3",
        "comparison_profile_version": "standard150_review_v2",
        "evidence_url_identity_version": PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION,
    }
    base.update(overrides)
    return base


def contract(**overrides):
    base = {
        "scan_run_id": CURRENT_SCAN_ID,
        "rule_definition_version": "missing_meta_description_v3",
        "comparison_profile_version": "standard150_review_v2",
        "evidence_url_identity_version": PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION,
    }
    base.update(overrides)
    return base


def pages(*urls):
    return [
        {
            "scan_run_id": CURRENT_SCAN_ID,
            "url": url,
            "status_code": 200,
            "content_type": "text/html",
            "indexable": True,
        }
        for url in urls
    ]


def bound_plan(previous=None):
    return build_identity_bound_targeted_recheck_plan(
        previous or fix(),
        previous_scan_origin=ORIGIN,
        previous_scan_id=PREVIOUS_SCAN_ID,
    )


def evaluations(plan, detected_states):
    return [
        {
            "scan_run_id": CURRENT_SCAN_ID,
            "url": request["url"],
            "evidence_key": request["evidence_key"],
            "criterion_id": plan["criterion_id"],
            "repair_fingerprint": plan["repair_fingerprint"],
            "rule_definition_version": plan["rule_definition_version"],
            "comparison_profile_version": plan["comparison_profile_version"],
            "evidence_url_identity_version": plan["evidence_url_identity_version"],
            "verification_plan_fingerprint": plan["plan_fingerprint"],
            "verification_plan_identity_version": PLAN_IDENTITY_BINDING_VERSION,
            "evaluated": True,
            "defect_detected": detected,
        }
        for request, detected in zip(plan["requests"], detected_states)
    ]


def test_execution_binding_accepts_one_exact_evaluation_per_targeted_request():
    plan = bound_plan()
    binding = verification_plan_execution_binding_integrity(
        plan,
        evaluations(plan, [False, False]),
        previous_scan_id=PREVIOUS_SCAN_ID,
    )
    assert binding["version"] == PLAN_EXECUTION_BINDING_VERSION
    assert binding["valid"] is True
    assert binding["plan_fingerprint"] == plan["plan_fingerprint"]
    assert binding["checked_requests"] == 2
    assert binding["checked_rule_evaluations"] == 2
    assert binding["verification_plan_identity_integrity"]["valid"] is True


def test_execution_binding_rejects_missing_plan_fingerprint_claim():
    plan = bound_plan()
    rows = evaluations(plan, [False, False])
    rows[0].pop("verification_plan_fingerprint")
    binding = verification_plan_execution_binding_integrity(
        plan,
        rows,
        previous_scan_id=PREVIOUS_SCAN_ID,
    )
    assert binding["valid"] is False
    assert binding["reason"].endswith(
        "verification_plan_fingerprint_must_be_exact_nonempty_string"
    )


def test_execution_binding_rejects_foreign_plan_fingerprint_claim():
    plan = bound_plan()
    rows = evaluations(plan, [False, False])
    rows[0]["verification_plan_fingerprint"] = "0" * 64
    binding = verification_plan_execution_binding_integrity(
        plan,
        rows,
        previous_scan_id=PREVIOUS_SCAN_ID,
    )
    assert binding["valid"] is False
    assert binding["reason"].endswith("verification_plan_fingerprint_mismatch")


def test_execution_binding_rejects_whitespace_normalized_plan_fingerprint():
    plan = bound_plan()
    rows = evaluations(plan, [False, False])
    rows[0]["verification_plan_fingerprint"] = f" {plan['plan_fingerprint']} "
    binding = verification_plan_execution_binding_integrity(
        plan,
        rows,
        previous_scan_id=PREVIOUS_SCAN_ID,
    )
    assert binding["valid"] is False
    assert binding["reason"].endswith(
        "verification_plan_fingerprint_must_be_exact_nonempty_string"
    )


def test_execution_binding_rejects_missing_plan_identity_version_claim():
    plan = bound_plan()
    rows = evaluations(plan, [False, False])
    rows[0].pop("verification_plan_identity_version")
    binding = verification_plan_execution_binding_integrity(
        plan,
        rows,
        previous_scan_id=PREVIOUS_SCAN_ID,
    )
    assert binding["valid"] is False
    assert binding["reason"].endswith(
        "verification_plan_identity_version_must_be_exact_nonempty_string"
    )


def test_execution_binding_rejects_foreign_plan_identity_version_claim():
    plan = bound_plan()
    rows = evaluations(plan, [False, False])
    rows[0]["verification_plan_identity_version"] = "future_plan_identity_v2"
    binding = verification_plan_execution_binding_integrity(
        plan,
        rows,
        previous_scan_id=PREVIOUS_SCAN_ID,
    )
    assert binding["valid"] is False
    assert binding["reason"].endswith("verification_plan_identity_version_mismatch")


def test_execution_binding_rejects_missing_targeted_evaluation():
    plan = bound_plan()
    rows = evaluations(plan, [False, False])[:1]
    binding = verification_plan_execution_binding_integrity(
        plan,
        rows,
        previous_scan_id=PREVIOUS_SCAN_ID,
    )
    assert binding["valid"] is False
    assert binding["reason"] == "rule_evaluation_population_does_not_exactly_match_targeted_plan"
    assert binding["missing_evidence_keys"] == [plan["requests"][1]["evidence_key"]]


def test_execution_binding_rejects_unexpected_evaluation_outside_plan():
    plan = bound_plan()
    rows = evaluations(plan, [False, False])
    foreign = deepcopy(rows[0])
    foreign["url"] = "/c"
    foreign["evidence_key"] = "https://example.com/c"
    rows.append(foreign)
    binding = verification_plan_execution_binding_integrity(
        plan,
        rows,
        previous_scan_id=PREVIOUS_SCAN_ID,
    )
    assert binding["valid"] is False
    assert binding["reason"] == "rule_evaluation_population_does_not_exactly_match_targeted_plan"
    assert binding["unexpected_evidence_keys"] == ["https://example.com/c"]


def test_execution_binding_rejects_duplicate_evaluation_identity():
    plan = bound_plan()
    rows = evaluations(plan, [False, False])
    rows.append(deepcopy(rows[0]))
    binding = verification_plan_execution_binding_integrity(
        plan,
        rows,
        previous_scan_id=PREVIOUS_SCAN_ID,
    )
    assert binding["valid"] is False
    assert binding["reason"].endswith("duplicate_evidence_key")


def test_execution_binding_rejects_mutated_plan_before_checking_execution_claims():
    plan = bound_plan()
    plan["requests"][0]["required_observations"].reverse()
    binding = verification_plan_execution_binding_integrity(
        plan,
        evaluations(plan, [False, False]),
        previous_scan_id=PREVIOUS_SCAN_ID,
    )
    assert binding["valid"] is False
    assert binding["reason"].startswith("verification_plan_identity_integrity_failed:")


def test_execution_bound_verified_fixed_wrapper_allows_exact_pass():
    previous = fix()
    plan = bound_plan(previous)
    decision = strict_verified_fixed_transition_from_execution_bound_observations(
        previous,
        plan,
        pages("/a", "/b"),
        evaluations(plan, [False, False]),
        [],
        contract(),
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_id=CURRENT_SCAN_ID,
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert decision["version"] == STRICT_VERIFIED_FIXED_PLAN_EXECUTION_BOUND_VERSION
    assert decision["allowed"] is True
    assert decision["recomputed_verification_state"] == PASS
    assert decision["verification_plan_execution_binding"]["valid"] is True
    assert decision["inner_plan_identity_bound_replay_version"]


def test_execution_bound_verified_fixed_wrapper_fails_closed_on_foreign_plan_receipt():
    previous = fix()
    plan = bound_plan(previous)
    rows = evaluations(plan, [False, False])
    rows[1]["verification_plan_fingerprint"] = "f" * 64
    decision = strict_verified_fixed_transition_from_execution_bound_observations(
        previous,
        plan,
        pages("/a", "/b"),
        rows,
        [],
        contract(),
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_id=CURRENT_SCAN_ID,
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert decision["allowed"] is False
    assert decision["reason"] == "verification_plan_execution_binding_failed"
    assert decision["recomputed_verification_state"] == COULD_NOT_VERIFY


def test_execution_bound_regression_wrapper_reopens_exact_fail():
    previous = fix(state="verified_fixed")
    plan = bound_plan(previous)
    decision = strict_regression_reopen_from_execution_bound_observations(
        previous,
        plan,
        pages("/a", "/b"),
        evaluations(plan, [True, True]),
        contract(),
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_id=CURRENT_SCAN_ID,
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert decision["version"] == STRICT_REGRESSION_REOPEN_PLAN_EXECUTION_BOUND_VERSION
    assert decision["should_reopen"] is True
    assert decision["recomputed_verification_state"] == FAIL
    assert decision["verification_plan_execution_binding"]["valid"] is True


def test_execution_bound_regression_wrapper_preserves_partial_reopen_scope():
    previous = fix(state="verified_fixed")
    plan = bound_plan(previous)
    decision = strict_regression_reopen_from_execution_bound_observations(
        previous,
        plan,
        pages("/a", "/b"),
        evaluations(plan, [False, True]),
        contract(),
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_id=CURRENT_SCAN_ID,
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert decision["should_reopen"] is True
    assert decision["recomputed_verification_state"] == PARTIAL
    assert decision["reopen_scope"] == [plan["requests"][1]["evidence_key"]]


def test_disappeared_required_url_remains_nonproof_after_execution_binding():
    previous = fix()
    plan = bound_plan(previous)
    decision = strict_verified_fixed_transition_from_execution_bound_observations(
        previous,
        plan,
        pages("/a"),
        evaluations(plan, [False, False]),
        [],
        contract(),
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_id=CURRENT_SCAN_ID,
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert decision["allowed"] is False
    assert decision["verification_plan_execution_binding"]["valid"] is True
    assert decision["recomputed_verification_state"] == COULD_NOT_VERIFY
    reasons = {
        item["reason"]
        for item in decision["recomputed_result"]["unverifiable_scope"]
    }
    assert "required_page_not_observed" in reasons
