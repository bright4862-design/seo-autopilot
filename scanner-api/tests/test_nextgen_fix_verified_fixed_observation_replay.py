from copy import deepcopy

from app.nextgen_fix_verification import (
    COULD_NOT_VERIFY,
    FAIL,
    PARTIAL,
    PASS,
    build_targeted_recheck_plan,
)
from app.nextgen_fix_verified_fixed_observation_replay import (
    STRICT_VERIFIED_FIXED_OBSERVATION_REPLAY_VERSION,
    strict_verified_fixed_transition_from_observations,
)
from app.repair_coverage import PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION

ORIGIN = "https://example.com"


def fix(**overrides):
    base = {
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
        "rule_definition_version": "missing_meta_description_v3",
        "comparison_profile_version": "standard150_review_v2",
        "evidence_url_identity_version": PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION,
    }
    base.update(overrides)
    return base


def pages(*urls):
    return [
        {"url": url, "status_code": 200, "content_type": "text/html", "indexable": True}
        for url in urls
    ]


def evaluations(plan, detected_states):
    return [
        {
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


def decision_for(detected_states, *, current_pages=None, current_fixes=None, plan=None, rule_rows=None):
    previous = fix()
    plan = plan or build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    current_pages = current_pages if current_pages is not None else pages("/a", "/b")
    rule_rows = rule_rows if rule_rows is not None else evaluations(plan, detected_states)
    return strict_verified_fixed_transition_from_observations(
        previous,
        plan,
        current_pages,
        rule_rows,
        current_fixes if current_fixes is not None else [],
        contract(),
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )


def test_observation_replay_allows_only_when_both_proofs_recompute_from_current_evidence():
    decision = decision_for([False, False])
    assert decision["version"] == STRICT_VERIFIED_FIXED_OBSERVATION_REPLAY_VERSION
    assert decision["allowed"] is True
    assert decision["recomputed_verification_state"] == PASS
    assert decision["recomputed_result"]["state"] == PASS
    assert decision["replay"]["legacy_comparison"]["state"] == "verified_fixed"


def test_observation_replay_rejects_current_rule_failure_even_when_legacy_fix_list_is_empty():
    decision = decision_for([True, True])
    assert decision["allowed"] is False
    assert decision["recomputed_verification_state"] == FAIL
    assert decision["recomputed_result"]["state"] == FAIL
    assert decision["replay"]["legacy_comparison"]["state"] == "verified_fixed"
    assert "nextgen_result_is_not_pass" in decision["reason"]


def test_observation_replay_rejects_partial_current_rule_failure_with_exact_scope():
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    decision = strict_verified_fixed_transition_from_observations(
        previous,
        plan,
        pages("/a", "/b"),
        evaluations(plan, [False, True]),
        [],
        contract(),
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert decision["allowed"] is False
    assert decision["recomputed_verification_state"] == PARTIAL
    assert decision["recomputed_result"]["unresolved_scope"] == [plan["requests"][1]["evidence_key"]]


def test_observation_replay_disappeared_url_is_could_not_verify_not_fix_proof():
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    decision = strict_verified_fixed_transition_from_observations(
        previous,
        plan,
        pages("/a"),
        evaluations(plan, [False, False]),
        [],
        contract(),
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert decision["allowed"] is False
    assert decision["recomputed_verification_state"] == COULD_NOT_VERIFY
    reasons = {item["reason"] for item in decision["recomputed_result"]["unverifiable_scope"]}
    assert "required_page_not_observed" in reasons


def test_observation_replay_duplicate_rule_evidence_fails_closed():
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    rows = evaluations(plan, [False, False])
    rows.append(deepcopy(rows[0]))
    decision = strict_verified_fixed_transition_from_observations(
        previous,
        plan,
        pages("/a", "/b"),
        rows,
        [],
        contract(),
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert decision["allowed"] is False
    assert decision["recomputed_verification_state"] == COULD_NOT_VERIFY
    reasons = {item["reason"] for item in decision["recomputed_result"]["unverifiable_scope"]}
    assert "ambiguous_duplicate_rule_evaluation" in reasons


def test_observation_replay_tampered_plan_population_fails_closed_before_transition():
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    plan = deepcopy(plan)
    plan["requests"] = plan["requests"][:1]
    decision = strict_verified_fixed_transition_from_observations(
        previous,
        plan,
        pages("/a", "/b"),
        evaluations(plan, [False]),
        [],
        contract(),
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert decision["allowed"] is False
    assert decision["recomputed_verification_state"] == COULD_NOT_VERIFY
    assert "complete historical evidence population" in decision["recomputed_result"]["reason"]
