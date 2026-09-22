from copy import deepcopy

from app.nextgen_fix_verification import (
    COULD_NOT_VERIFY,
    FAIL,
    PASS,
    build_targeted_recheck_plan,
)
from app.nextgen_fix_verification_plan_lineage import (
    PLAN_LINEAGE_BINDING_VERSION,
    STRICT_REGRESSION_REOPEN_PLAN_SCAN_BOUND_VERSION,
    STRICT_VERIFIED_FIXED_PLAN_SCAN_BOUND_VERSION,
    build_scan_bound_targeted_recheck_plan,
    strict_regression_reopen_from_plan_scan_bound_observations,
    strict_verified_fixed_transition_from_plan_scan_bound_observations,
    verification_plan_lineage_integrity,
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
            "evaluated": True,
            "defect_detected": detected,
        }
        for request, detected in zip(plan["requests"], detected_states)
    ]


def bound_plan(previous=None, *, previous_scan_id=PREVIOUS_SCAN_ID):
    return build_scan_bound_targeted_recheck_plan(
        previous or fix(),
        previous_scan_origin=ORIGIN,
        previous_scan_id=previous_scan_id,
    )


def test_scan_bound_plan_builder_stamps_exact_historical_scan_on_plan_and_requests():
    plan = bound_plan()
    assert plan["state"] == "ready"
    assert plan["population_complete"] is True
    assert plan["plan_lineage_version"] == PLAN_LINEAGE_BINDING_VERSION
    assert plan["source_scan_id"] == PREVIOUS_SCAN_ID
    assert plan["requests"]
    assert all(request["source_scan_id"] == PREVIOUS_SCAN_ID for request in plan["requests"])


def test_scan_bound_plan_builder_blocks_non_exact_historical_scan_id():
    plan = bound_plan(previous_scan_id=f" {PREVIOUS_SCAN_ID}")
    assert plan["state"] == "blocked"
    assert plan["population_complete"] is False
    assert plan["source_scan_id"] == ""
    assert "previous_scan_id_exact_nonempty_string_required" in plan["blockers"]


def test_plan_lineage_integrity_accepts_exact_binding_without_mutating_input():
    plan = bound_plan()
    before = deepcopy(plan)
    result = verification_plan_lineage_integrity(plan, previous_scan_id=PREVIOUS_SCAN_ID)
    assert result["version"] == PLAN_LINEAGE_BINDING_VERSION
    assert result["valid"] is True
    assert result["checked_requests"] == 2
    assert plan == before


def test_plan_lineage_integrity_rejects_missing_lineage_version():
    plan = bound_plan()
    plan.pop("plan_lineage_version")
    result = verification_plan_lineage_integrity(plan, previous_scan_id=PREVIOUS_SCAN_ID)
    assert result["valid"] is False
    assert result["reason"] == "verification_plan_lineage_version_missing_or_unsupported"


def test_plan_lineage_integrity_rejects_foreign_top_level_source_scan():
    plan = bound_plan()
    plan["source_scan_id"] = "scan-other"
    result = verification_plan_lineage_integrity(plan, previous_scan_id=PREVIOUS_SCAN_ID)
    assert result["valid"] is False
    assert result["reason"] == "verification_plan_source_scan_id_mismatch"


def test_plan_lineage_integrity_rejects_null_alias_even_when_other_alias_matches():
    plan = bound_plan()
    plan["scan_run_id"] = PREVIOUS_SCAN_ID
    plan["source_scan_id"] = None
    result = verification_plan_lineage_integrity(plan, previous_scan_id=PREVIOUS_SCAN_ID)
    assert result["valid"] is False
    assert result["reason"] == "verification_plan_source_scan_id_must_be_exact_nonempty_string"


def test_plan_lineage_integrity_requires_every_request_to_name_historical_scan():
    plan = bound_plan()
    plan["requests"][0].pop("source_scan_id")
    result = verification_plan_lineage_integrity(plan, previous_scan_id=PREVIOUS_SCAN_ID)
    assert result["valid"] is False
    assert result["reason"] == "verification_request_0_source_scan_id_missing"


def test_plan_lineage_integrity_rejects_foreign_request_source_scan():
    plan = bound_plan()
    plan["requests"][1]["source_scan_id"] = "scan-other"
    result = verification_plan_lineage_integrity(plan, previous_scan_id=PREVIOUS_SCAN_ID)
    assert result["valid"] is False
    assert result["reason"] == "verification_request_1_source_scan_id_mismatch"


def test_plan_lineage_integrity_rejects_conflicting_request_scan_aliases():
    plan = bound_plan()
    plan["requests"][0]["scan_id"] = CURRENT_SCAN_ID
    result = verification_plan_lineage_integrity(plan, previous_scan_id=PREVIOUS_SCAN_ID)
    assert result["valid"] is False
    assert result["reason"] == "verification_request_0_scan_id_mismatch"


def test_latest_verified_fixed_wrapper_rejects_unbound_legacy_plan_before_proof():
    previous = fix()
    legacy_plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    decision = strict_verified_fixed_transition_from_plan_scan_bound_observations(
        previous,
        legacy_plan,
        pages("/a", "/b"),
        evaluations(legacy_plan, [False, False]),
        [],
        contract(),
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_id=CURRENT_SCAN_ID,
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert decision["version"] == STRICT_VERIFIED_FIXED_PLAN_SCAN_BOUND_VERSION
    assert decision["allowed"] is False
    assert decision["recomputed_verification_state"] == COULD_NOT_VERIFY
    assert decision["reason"] == "verification_plan_lineage_binding_failed"


def test_latest_verified_fixed_wrapper_allows_exact_plan_and_scan_bound_pass():
    previous = fix()
    plan = bound_plan(previous)
    decision = strict_verified_fixed_transition_from_plan_scan_bound_observations(
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
    assert decision["version"] == STRICT_VERIFIED_FIXED_PLAN_SCAN_BOUND_VERSION
    assert decision["allowed"] is True
    assert decision["recomputed_verification_state"] == PASS
    assert decision["verification_plan_lineage_integrity"]["valid"] is True
    assert decision["inner_scan_bound_replay_version"]


def test_latest_regression_wrapper_reopens_exact_plan_and_scan_bound_fail():
    previous = fix(state="verified_fixed")
    plan = bound_plan(previous)
    decision = strict_regression_reopen_from_plan_scan_bound_observations(
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
    assert decision["version"] == STRICT_REGRESSION_REOPEN_PLAN_SCAN_BOUND_VERSION
    assert decision["should_reopen"] is True
    assert decision["recomputed_verification_state"] == FAIL
    assert decision["verification_plan_lineage_integrity"]["valid"] is True
    assert decision["inner_scan_bound_replay_version"]


def test_latest_regression_wrapper_rejects_plan_bound_to_other_historical_scan():
    previous = fix(state="verified_fixed")
    plan = bound_plan(previous, previous_scan_id="scan-other")
    decision = strict_regression_reopen_from_plan_scan_bound_observations(
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
    assert decision["should_reopen"] is False
    assert decision["recomputed_verification_state"] == COULD_NOT_VERIFY
    assert decision["reason"] == "verification_plan_lineage_binding_failed"


def test_latest_plan_scan_bound_wrapper_keeps_disappeared_url_as_non_proof():
    previous = fix()
    plan = bound_plan(previous)
    decision = strict_verified_fixed_transition_from_plan_scan_bound_observations(
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
    assert decision["recomputed_verification_state"] == COULD_NOT_VERIFY
    reasons = {item["reason"] for item in decision["recomputed_result"]["unverifiable_scope"]}
    assert "required_page_not_observed" in reasons
