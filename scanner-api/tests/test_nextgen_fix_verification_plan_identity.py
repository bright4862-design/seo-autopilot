from copy import deepcopy

from app.nextgen_fix_verification import COULD_NOT_VERIFY, FAIL, PASS
from app.nextgen_fix_verification_plan_identity import (
    PLAN_IDENTITY_BINDING_VERSION,
    STRICT_REGRESSION_REOPEN_PLAN_IDENTITY_BOUND_VERSION,
    STRICT_VERIFIED_FIXED_PLAN_IDENTITY_BOUND_VERSION,
    build_identity_bound_targeted_recheck_plan,
    strict_regression_reopen_from_identity_bound_observations,
    strict_verified_fixed_transition_from_identity_bound_observations,
    verification_plan_identity_integrity,
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
    return build_identity_bound_targeted_recheck_plan(
        previous or fix(),
        previous_scan_origin=ORIGIN,
        previous_scan_id=previous_scan_id,
    )


def test_identity_bound_builder_commits_exact_ready_plan_transport():
    plan = bound_plan()
    assert plan["state"] == "ready"
    assert plan["plan_identity_version"] == PLAN_IDENTITY_BINDING_VERSION
    assert plan["plan_identity_state"] == "bound"
    assert plan["plan_identity_reason"] == "exact_ready_plan_transport_bound"
    assert len(plan["plan_fingerprint"]) == 64
    assert plan["plan_fingerprint"] == plan["plan_fingerprint"].lower()


def test_identity_integrity_accepts_exact_plan_without_mutating_it():
    plan = bound_plan()
    before = deepcopy(plan)
    result = verification_plan_identity_integrity(
        plan,
        previous_scan_id=PREVIOUS_SCAN_ID,
    )
    assert result["version"] == PLAN_IDENTITY_BINDING_VERSION
    assert result["valid"] is True
    assert result["plan_fingerprint"] == plan["plan_fingerprint"]
    assert result["verification_plan_envelope_integrity"]["valid"] is True
    assert result["verification_plan_lineage_integrity"]["valid"] is True
    assert plan == before


def test_same_exact_plan_material_has_deterministic_fingerprint():
    first = bound_plan()
    second = bound_plan()
    assert first["plan_fingerprint"] == second["plan_fingerprint"]


def test_equivalent_canonical_url_transport_mutation_is_still_not_the_same_plan():
    plan = bound_plan()
    mutated = deepcopy(plan)
    mutated["requests"][0]["url"] = "https://example.com/a"
    result = verification_plan_identity_integrity(
        mutated,
        previous_scan_id=PREVIOUS_SCAN_ID,
    )
    assert result["valid"] is False
    assert result["reason"] == "verification_plan_fingerprint_mismatch"


def test_required_observation_transport_mutation_breaks_plan_identity():
    plan = bound_plan()
    mutated = deepcopy(plan)
    mutated["requests"][0]["required_observations"].reverse()
    result = verification_plan_identity_integrity(
        mutated,
        previous_scan_id=PREVIOUS_SCAN_ID,
    )
    assert result["valid"] is False
    assert result["reason"] == "verification_plan_fingerprint_mismatch"


def test_acceptance_predicate_contract_mutation_breaks_plan_identity():
    plan = bound_plan()
    mutated = deepcopy(plan)
    mutated["criterion"]["predicate_contract"]["expected"] = True
    result = verification_plan_identity_integrity(
        mutated,
        previous_scan_id=PREVIOUS_SCAN_ID,
    )
    assert result["valid"] is False
    assert result["reason"] == "verification_plan_fingerprint_mismatch"


def test_added_transport_metadata_breaks_exact_plan_identity():
    plan = bound_plan()
    mutated = deepcopy(plan)
    mutated["foreign_transport_claim"] = "copied-from-another-plan"
    result = verification_plan_identity_integrity(
        mutated,
        previous_scan_id=PREVIOUS_SCAN_ID,
    )
    assert result["valid"] is False
    assert result["reason"] == "verification_plan_fingerprint_mismatch"


def test_missing_plan_fingerprint_fails_closed():
    plan = bound_plan()
    plan["plan_fingerprint"] = ""
    result = verification_plan_identity_integrity(
        plan,
        previous_scan_id=PREVIOUS_SCAN_ID,
    )
    assert result["valid"] is False
    assert result["reason"] == "verification_plan_fingerprint_not_exact_sha256"


def test_uppercase_sha256_transport_is_not_silently_normalized():
    plan = bound_plan()
    plan["plan_fingerprint"] = plan["plan_fingerprint"].upper()
    result = verification_plan_identity_integrity(
        plan,
        previous_scan_id=PREVIOUS_SCAN_ID,
    )
    assert result["valid"] is False
    assert result["reason"] == "verification_plan_fingerprint_not_exact_sha256"


def test_invalid_historical_scan_identity_cannot_produce_bound_plan():
    plan = bound_plan(previous_scan_id=f" {PREVIOUS_SCAN_ID}")
    assert plan["plan_identity_state"] == "blocked"
    assert plan["plan_fingerprint"] == ""
    result = verification_plan_identity_integrity(
        plan,
        previous_scan_id=PREVIOUS_SCAN_ID,
    )
    assert result["valid"] is False


def test_identity_bound_verified_fixed_wrapper_allows_exact_pass():
    previous = fix()
    plan = bound_plan(previous)
    decision = strict_verified_fixed_transition_from_identity_bound_observations(
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
    assert decision["version"] == STRICT_VERIFIED_FIXED_PLAN_IDENTITY_BOUND_VERSION
    assert decision["allowed"] is True
    assert decision["recomputed_verification_state"] == PASS
    assert decision["verification_plan_identity_integrity"]["valid"] is True
    assert decision["inner_plan_scan_bound_replay_version"]


def test_identity_bound_verified_fixed_wrapper_denies_post_build_plan_mutation():
    previous = fix()
    plan = bound_plan(previous)
    plan["requests"][0]["url"] = "https://example.com/a"
    decision = strict_verified_fixed_transition_from_identity_bound_observations(
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
    assert decision["allowed"] is False
    assert decision["reason"] == "verification_plan_identity_binding_failed"
    assert decision["recomputed_verification_state"] == COULD_NOT_VERIFY


def test_identity_bound_regression_wrapper_reopens_exact_fail_and_denies_mutation():
    previous = fix(state="verified_fixed")
    plan = bound_plan(previous)
    decision = strict_regression_reopen_from_identity_bound_observations(
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
    assert decision["version"] == STRICT_REGRESSION_REOPEN_PLAN_IDENTITY_BOUND_VERSION
    assert decision["should_reopen"] is True
    assert decision["recomputed_verification_state"] == FAIL

    mutated = deepcopy(plan)
    mutated["requests"][1]["required_observations"].reverse()
    denied = strict_regression_reopen_from_identity_bound_observations(
        previous,
        mutated,
        pages("/a", "/b"),
        evaluations(mutated, [True, True]),
        contract(),
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_id=CURRENT_SCAN_ID,
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert denied["should_reopen"] is False
    assert denied["reason"] == "verification_plan_identity_binding_failed"
    assert denied["recomputed_verification_state"] == COULD_NOT_VERIFY


def test_disappeared_required_url_remains_nonproof_after_plan_identity_gate():
    previous = fix()
    plan = bound_plan(previous)
    decision = strict_verified_fixed_transition_from_identity_bound_observations(
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
    reasons = {
        item["reason"]
        for item in decision["recomputed_result"]["unverifiable_scope"]
    }
    assert "required_page_not_observed" in reasons
