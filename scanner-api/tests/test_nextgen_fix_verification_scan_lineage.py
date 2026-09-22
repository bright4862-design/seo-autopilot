from copy import deepcopy

from app.nextgen_fix_verification import (
    COULD_NOT_VERIFY,
    FAIL,
    PASS,
    build_targeted_recheck_plan,
)
from app.nextgen_fix_verification_scan_lineage import (
    SCAN_LINEAGE_BINDING_VERSION,
    STRICT_REGRESSION_REOPEN_SCAN_BOUND_VERSION,
    STRICT_VERIFIED_FIXED_SCAN_BOUND_VERSION,
    strict_regression_reopen_from_scan_bound_observations,
    strict_verified_fixed_transition_from_scan_bound_observations,
    verification_scan_lineage_integrity,
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


def test_scan_lineage_accepts_exact_source_claims_across_all_proving_inputs():
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    result = verification_scan_lineage_integrity(
        previous,
        contract(scan_id=CURRENT_SCAN_ID),
        pages("/a", "/b"),
        evaluations(plan, [False, False]),
        [{"scan_run_id": CURRENT_SCAN_ID, "rule": "other_rule"}],
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_id=CURRENT_SCAN_ID,
    )
    assert result["version"] == SCAN_LINEAGE_BINDING_VERSION
    assert result["valid"] is True
    assert result["reason"] == "all_proving_inputs_bound_to_exact_scan_lineage"


def test_scan_lineage_rejects_whitespace_normalized_authoritative_previous_scan_id():
    result = verification_scan_lineage_integrity(
        fix(),
        contract(),
        [],
        [],
        [],
        previous_scan_id=f" {PREVIOUS_SCAN_ID}",
        scan_id=CURRENT_SCAN_ID,
    )
    assert result["valid"] is False
    assert result["reason"] == "previous_scan_id_must_be_exact_nonempty_string"


def test_scan_lineage_rejects_same_historical_and_current_scan_id():
    result = verification_scan_lineage_integrity(
        fix(scan_run_id=PREVIOUS_SCAN_ID),
        contract(scan_run_id=PREVIOUS_SCAN_ID),
        [],
        [],
        [],
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_id=PREVIOUS_SCAN_ID,
    )
    assert result["valid"] is False
    assert result["reason"] == "historical_and_current_scan_ids_must_differ"


def test_scan_lineage_rejects_historical_record_claim_from_another_scan():
    result = verification_scan_lineage_integrity(
        fix(scan_run_id="scan-other"),
        contract(),
        [],
        [],
        [],
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_id=CURRENT_SCAN_ID,
    )
    assert result["valid"] is False
    assert result["reason"] == "previous_record_scan_run_id_mismatch"


def test_scan_lineage_requires_current_contract_source_scan_claim():
    current_contract = contract()
    current_contract.pop("scan_run_id")
    result = verification_scan_lineage_integrity(
        fix(),
        current_contract,
        [],
        [],
        [],
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_id=CURRENT_SCAN_ID,
    )
    assert result["valid"] is False
    assert result["reason"] == "current_contract_source_scan_id_missing"


def test_scan_lineage_requires_every_current_page_to_name_its_source_scan():
    current_pages = pages("/a")
    current_pages[0].pop("scan_run_id")
    result = verification_scan_lineage_integrity(
        fix(),
        contract(),
        current_pages,
        [],
        [],
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_id=CURRENT_SCAN_ID,
    )
    assert result["valid"] is False
    assert result["reason"] == "current_page_0_source_scan_id_missing"


def test_scan_lineage_rejects_current_page_from_foreign_scan():
    current_pages = pages("/a")
    current_pages[0]["scan_run_id"] = "scan-other"
    result = verification_scan_lineage_integrity(
        fix(),
        contract(),
        current_pages,
        [],
        [],
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_id=CURRENT_SCAN_ID,
    )
    assert result["valid"] is False
    assert result["reason"] == "current_page_0_scan_run_id_mismatch"


def test_scan_lineage_rejects_conflicting_rule_evaluation_scan_aliases():
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    rows = evaluations(plan, [False, False])
    rows[0]["scan_id"] = "scan-other"
    result = verification_scan_lineage_integrity(
        previous,
        contract(),
        pages("/a", "/b"),
        rows,
        [],
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_id=CURRENT_SCAN_ID,
    )
    assert result["valid"] is False
    assert result["reason"] == "rule_evaluation_0_scan_id_mismatch"


def test_scan_lineage_rejects_foreign_current_fix_population_member():
    result = verification_scan_lineage_integrity(
        fix(),
        contract(),
        [],
        [],
        [{"scan_run_id": "scan-other", "rule": "missing_meta_description"}],
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_id=CURRENT_SCAN_ID,
    )
    assert result["valid"] is False
    assert result["reason"] == "current_fix_0_scan_run_id_mismatch"


def test_scan_bound_verified_fixed_wrapper_allows_only_after_lineage_and_both_existing_proofs():
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    decision = strict_verified_fixed_transition_from_scan_bound_observations(
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
    assert decision["version"] == STRICT_VERIFIED_FIXED_SCAN_BOUND_VERSION
    assert decision["allowed"] is True
    assert decision["recomputed_verification_state"] == PASS
    assert decision["scan_lineage_binding"]["valid"] is True
    assert decision["inner_observation_replay_version"]


def test_scan_bound_verified_fixed_wrapper_denies_mixed_scan_page_before_inner_replay():
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    current_pages = pages("/a", "/b")
    current_pages[1]["scan_run_id"] = "scan-other"
    decision = strict_verified_fixed_transition_from_scan_bound_observations(
        previous,
        plan,
        current_pages,
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
    assert decision["reason"] == "scan_lineage_binding_failed"
    assert decision["scan_lineage_binding"]["reason"] == "current_page_1_scan_run_id_mismatch"


def test_scan_bound_disappeared_required_url_remains_could_not_verify_not_fixed():
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    decision = strict_verified_fixed_transition_from_scan_bound_observations(
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


def test_scan_bound_regression_wrapper_reopens_exact_source_bound_fail():
    previous = fix(state="verified_fixed")
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    decision = strict_regression_reopen_from_scan_bound_observations(
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
    assert decision["version"] == STRICT_REGRESSION_REOPEN_SCAN_BOUND_VERSION
    assert decision["should_reopen"] is True
    assert decision["recomputed_verification_state"] == FAIL
    assert decision["scan_lineage_binding"]["valid"] is True
    assert decision["inner_observation_replay_version"]


def test_scan_bound_regression_wrapper_denies_foreign_rule_evidence_before_reopen():
    previous = fix(state="verified_fixed")
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    rows = evaluations(plan, [True, True])
    rows[0]["scan_run_id"] = "scan-other"
    decision = strict_regression_reopen_from_scan_bound_observations(
        previous,
        plan,
        pages("/a", "/b"),
        rows,
        contract(),
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_id=CURRENT_SCAN_ID,
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert decision["should_reopen"] is False
    assert decision["recomputed_verification_state"] == COULD_NOT_VERIFY
    assert decision["reason"] == "scan_lineage_binding_failed"
    assert decision["scan_lineage_binding"]["reason"] == "rule_evaluation_0_scan_run_id_mismatch"
