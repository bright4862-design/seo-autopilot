from copy import deepcopy

from app.nextgen_fix_verification import COULD_NOT_VERIFY, FAIL, PARTIAL, PASS
from app.nextgen_fix_verification_observation_execution import (
    OBSERVATION_EXECUTION_BINDING_VERSION,
    STRICT_REGRESSION_REOPEN_OBSERVATION_EXECUTION_BOUND_VERSION,
    STRICT_VERIFIED_FIXED_OBSERVATION_EXECUTION_BOUND_VERSION,
    strict_regression_reopen_from_observation_execution_bound_inputs,
    strict_verified_fixed_transition_from_observation_execution_bound_inputs,
    verification_observation_execution_binding_integrity,
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


def bound_plan(previous=None):
    return build_identity_bound_targeted_recheck_plan(
        previous or fix(),
        previous_scan_origin=ORIGIN,
        previous_scan_id=PREVIOUS_SCAN_ID,
    )


def pages(plan, *urls):
    request_by_url = {request["url"]: request for request in plan["requests"]}
    return [
        {
            "scan_run_id": CURRENT_SCAN_ID,
            "url": url,
            "evidence_key": request_by_url[url]["evidence_key"],
            "verification_plan_fingerprint": plan["plan_fingerprint"],
            "verification_plan_identity_version": PLAN_IDENTITY_BINDING_VERSION,
            "status_code": 200,
            "content_type": "text/html",
            "indexable": True,
        }
        for url in urls
    ]


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


def test_observation_execution_binding_accepts_exact_page_and_evaluation_receipts():
    plan = bound_plan()
    binding = verification_observation_execution_binding_integrity(
        plan,
        pages(plan, "/a", "/b"),
        evaluations(plan, [False, False]),
        previous_scan_id=PREVIOUS_SCAN_ID,
    )
    assert binding["version"] == OBSERVATION_EXECUTION_BINDING_VERSION
    assert binding["valid"] is True
    assert binding["plan_fingerprint"] == plan["plan_fingerprint"]
    assert binding["checked_current_pages"] == 2
    assert binding["checked_rule_evaluations"] == 2
    assert binding["missing_required_evidence_keys"] == []
    assert binding["verification_plan_execution_binding"]["valid"] is True


def test_observation_execution_binding_rejects_missing_page_plan_fingerprint_claim():
    plan = bound_plan()
    observed = pages(plan, "/a", "/b")
    observed[0].pop("verification_plan_fingerprint")
    binding = verification_observation_execution_binding_integrity(
        plan, observed, evaluations(plan, [False, False]), previous_scan_id=PREVIOUS_SCAN_ID
    )
    assert binding["valid"] is False
    assert binding["reason"].endswith(
        "verification_plan_fingerprint_must_be_exact_nonempty_string"
    )


def test_observation_execution_binding_rejects_foreign_page_plan_fingerprint_claim():
    plan = bound_plan()
    observed = pages(plan, "/a", "/b")
    observed[0]["verification_plan_fingerprint"] = "f" * 64
    binding = verification_observation_execution_binding_integrity(
        plan, observed, evaluations(plan, [False, False]), previous_scan_id=PREVIOUS_SCAN_ID
    )
    assert binding["valid"] is False
    assert binding["reason"].endswith("verification_plan_fingerprint_mismatch")


def test_observation_execution_binding_rejects_whitespace_page_plan_fingerprint_claim():
    plan = bound_plan()
    observed = pages(plan, "/a", "/b")
    observed[0]["verification_plan_fingerprint"] = f" {plan['plan_fingerprint']} "
    binding = verification_observation_execution_binding_integrity(
        plan, observed, evaluations(plan, [False, False]), previous_scan_id=PREVIOUS_SCAN_ID
    )
    assert binding["valid"] is False
    assert binding["reason"].endswith(
        "verification_plan_fingerprint_must_be_exact_nonempty_string"
    )


def test_observation_execution_binding_rejects_missing_page_identity_version_claim():
    plan = bound_plan()
    observed = pages(plan, "/a", "/b")
    observed[0].pop("verification_plan_identity_version")
    binding = verification_observation_execution_binding_integrity(
        plan, observed, evaluations(plan, [False, False]), previous_scan_id=PREVIOUS_SCAN_ID
    )
    assert binding["valid"] is False
    assert binding["reason"].endswith(
        "verification_plan_identity_version_must_be_exact_nonempty_string"
    )


def test_observation_execution_binding_rejects_foreign_page_identity_version_claim():
    plan = bound_plan()
    observed = pages(plan, "/a", "/b")
    observed[0]["verification_plan_identity_version"] = "future_plan_identity_v2"
    binding = verification_observation_execution_binding_integrity(
        plan, observed, evaluations(plan, [False, False]), previous_scan_id=PREVIOUS_SCAN_ID
    )
    assert binding["valid"] is False
    assert binding["reason"].endswith("verification_plan_identity_version_mismatch")


def test_observation_execution_binding_rejects_duplicate_page_evidence_key():
    plan = bound_plan()
    observed = pages(plan, "/a", "/b")
    observed.append(deepcopy(observed[0]))
    binding = verification_observation_execution_binding_integrity(
        plan, observed, evaluations(plan, [False, False]), previous_scan_id=PREVIOUS_SCAN_ID
    )
    assert binding["valid"] is False
    assert binding["reason"].endswith("duplicate_evidence_key")


def test_observation_execution_binding_rejects_page_outside_targeted_plan():
    plan = bound_plan()
    observed = pages(plan, "/a", "/b")
    foreign = deepcopy(observed[0])
    foreign["url"] = "/c"
    foreign["evidence_key"] = "https://example.com/c"
    observed.append(foreign)
    binding = verification_observation_execution_binding_integrity(
        plan, observed, evaluations(plan, [False, False]), previous_scan_id=PREVIOUS_SCAN_ID
    )
    assert binding["valid"] is False
    assert binding["reason"].endswith("evidence_key_not_targeted_by_plan")
    assert binding["unexpected_evidence_key"] == "https://example.com/c"


def test_observation_execution_bound_verified_fixed_wrapper_allows_exact_pass():
    previous = fix()
    plan = bound_plan(previous)
    decision = strict_verified_fixed_transition_from_observation_execution_bound_inputs(
        previous,
        plan,
        pages(plan, "/a", "/b"),
        evaluations(plan, [False, False]),
        [],
        contract(),
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_id=CURRENT_SCAN_ID,
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert decision["version"] == STRICT_VERIFIED_FIXED_OBSERVATION_EXECUTION_BOUND_VERSION
    assert decision["allowed"] is True
    assert decision["recomputed_verification_state"] == PASS
    assert decision["observation_execution_binding"]["valid"] is True
    assert decision["inner_plan_execution_bound_replay_version"]


def test_observation_execution_bound_verified_fixed_wrapper_fails_closed_on_foreign_page_receipt():
    previous = fix()
    plan = bound_plan(previous)
    observed = pages(plan, "/a", "/b")
    observed[1]["verification_plan_fingerprint"] = "0" * 64
    decision = strict_verified_fixed_transition_from_observation_execution_bound_inputs(
        previous,
        plan,
        observed,
        evaluations(plan, [False, False]),
        [],
        contract(),
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_id=CURRENT_SCAN_ID,
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert decision["allowed"] is False
    assert decision["reason"] == "observation_execution_binding_failed"
    assert decision["recomputed_verification_state"] == COULD_NOT_VERIFY


def test_observation_execution_bound_regression_wrapper_reopens_exact_fail():
    previous = fix(state="verified_fixed")
    plan = bound_plan(previous)
    decision = strict_regression_reopen_from_observation_execution_bound_inputs(
        previous,
        plan,
        pages(plan, "/a", "/b"),
        evaluations(plan, [True, True]),
        contract(),
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_id=CURRENT_SCAN_ID,
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert decision["version"] == STRICT_REGRESSION_REOPEN_OBSERVATION_EXECUTION_BOUND_VERSION
    assert decision["should_reopen"] is True
    assert decision["recomputed_verification_state"] == FAIL
    assert decision["observation_execution_binding"]["valid"] is True


def test_observation_execution_bound_regression_wrapper_preserves_partial_scope():
    previous = fix(state="verified_fixed")
    plan = bound_plan(previous)
    decision = strict_regression_reopen_from_observation_execution_bound_inputs(
        previous,
        plan,
        pages(plan, "/a", "/b"),
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


def test_disappeared_page_is_not_execution_failure_but_remains_could_not_verify():
    previous = fix()
    plan = bound_plan(previous)
    observed = pages(plan, "/a")
    binding = verification_observation_execution_binding_integrity(
        plan,
        observed,
        evaluations(plan, [False, False]),
        previous_scan_id=PREVIOUS_SCAN_ID,
    )
    assert binding["valid"] is True
    assert binding["missing_required_evidence_keys"] == [plan["requests"][1]["evidence_key"]]

    decision = strict_verified_fixed_transition_from_observation_execution_bound_inputs(
        previous,
        plan,
        observed,
        evaluations(plan, [False, False]),
        [],
        contract(),
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_id=CURRENT_SCAN_ID,
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert decision["allowed"] is False
    assert decision["observation_execution_binding"]["valid"] is True
    assert decision["recomputed_verification_state"] == COULD_NOT_VERIFY
    reasons = {
        item["reason"]
        for item in decision["recomputed_result"]["unverifiable_scope"]
    }
    assert "required_page_not_observed" in reasons
