from copy import deepcopy

from app.nextgen_fix_regression_reopen_replay import (
    STRICT_REGRESSION_REOPEN_OBSERVATION_REPLAY_VERSION,
    strict_regression_reopen_from_observations,
)
from app.nextgen_fix_verification import COULD_NOT_VERIFY, PASS, build_targeted_recheck_plan
from app.nextgen_fix_verification_origin_binding import (
    SCAN_ORIGIN_BINDING_VERSION,
    evaluate_verification_observations_origin_bound,
    verification_scan_origin_binding_integrity,
)
from app.nextgen_fix_verified_fixed_observation_replay import (
    STRICT_VERIFIED_FIXED_OBSERVATION_REPLAY_VERSION,
    strict_verified_fixed_transition_from_observations,
)
from app.repair_coverage import PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION

ORIGIN = "https://example.com"
OTHER_ORIGIN = "https://other.example"


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


def contract():
    return {
        "rule_definition_version": "missing_meta_description_v3",
        "comparison_profile_version": "standard150_review_v2",
        "evidence_url_identity_version": PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION,
    }


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


def evidence():
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    return previous, plan, pages("/a", "/b"), evaluations(plan, [False, False])


def test_origin_binding_accepts_canonical_same_origin_and_records_exact_context():
    previous, plan, current_pages, rows = evidence()
    binding = verification_scan_origin_binding_integrity(
        previous,
        plan,
        current_pages,
        rows,
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert binding["version"] == SCAN_ORIGIN_BINDING_VERSION
    assert binding["valid"] is True
    assert binding["previous_scan_origin"] == ORIGIN
    assert binding["scan_origin"] == ORIGIN


def test_origin_binding_rejects_noncanonical_previous_origin():
    previous, plan, current_pages, rows = evidence()
    binding = verification_scan_origin_binding_integrity(
        previous,
        plan,
        current_pages,
        rows,
        previous_scan_origin=f"{ORIGIN}/",
        scan_origin=ORIGIN,
    )
    assert binding["valid"] is False
    assert binding["reason"] == "previous_scan_origin_not_exact_canonical_origin"


def test_origin_binding_rejects_distinct_historical_and_current_origins():
    previous, plan, current_pages, rows = evidence()
    binding = verification_scan_origin_binding_integrity(
        previous,
        plan,
        current_pages,
        rows,
        previous_scan_origin=ORIGIN,
        scan_origin=OTHER_ORIGIN,
    )
    assert binding["valid"] is False
    assert binding["reason"] == "historical_and_current_scan_origins_differ"


def test_origin_binding_rejects_foreign_historical_affected_page():
    previous = fix(affected_pages=[f"{OTHER_ORIGIN}/a", "/b"])
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    binding = verification_scan_origin_binding_integrity(
        previous,
        plan,
        pages("/a", "/b"),
        evaluations(plan, [False, False]),
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert binding["valid"] is False
    assert binding["reason"] == "historical_affected_pages_0_origin_mismatch"


def test_origin_binding_rejects_plan_evidence_key_from_foreign_origin():
    previous, plan, current_pages, rows = evidence()
    tampered = deepcopy(plan)
    tampered["requests"][0]["evidence_key"] = f"{OTHER_ORIGIN}/a"
    binding = verification_scan_origin_binding_integrity(
        previous,
        tampered,
        current_pages,
        rows,
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert binding["valid"] is False
    assert binding["reason"] == "plan_request_0_evidence_key_origin_mismatch"


def test_origin_binding_rejects_current_page_from_foreign_origin_before_predicate_proof():
    previous, plan, _, rows = evidence()
    result = evaluate_verification_observations_origin_bound(
        plan,
        previous,
        pages(f"{OTHER_ORIGIN}/a", "/b"),
        rows,
        contract(),
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert result["state"] == COULD_NOT_VERIFY
    assert result["scan_origin_binding"]["reason"] == "current_page_0_url_origin_mismatch"


def test_origin_binding_rejects_rule_evaluation_evidence_key_from_foreign_origin():
    previous, plan, current_pages, rows = evidence()
    rows = deepcopy(rows)
    rows[0]["evidence_key"] = f"{OTHER_ORIGIN}/a"
    result = evaluate_verification_observations_origin_bound(
        plan,
        previous,
        current_pages,
        rows,
        contract(),
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert result["state"] == COULD_NOT_VERIFY
    assert result["scan_origin_binding"]["reason"] == "rule_evaluation_0_evidence_key_origin_mismatch"


def test_origin_bound_evaluator_preserves_valid_pass_semantics():
    previous, plan, current_pages, rows = evidence()
    result = evaluate_verification_observations_origin_bound(
        plan,
        previous,
        current_pages,
        rows,
        contract(),
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert result["state"] == PASS
    assert result["scan_origin_binding"]["valid"] is True


def test_verified_fixed_replay_fails_closed_when_scan_origins_differ():
    previous, plan, current_pages, rows = evidence()
    decision = strict_verified_fixed_transition_from_observations(
        previous,
        plan,
        current_pages,
        rows,
        [],
        contract(),
        previous_scan_origin=ORIGIN,
        scan_origin=OTHER_ORIGIN,
    )
    assert decision["version"] == STRICT_VERIFIED_FIXED_OBSERVATION_REPLAY_VERSION
    assert decision["allowed"] is False
    assert decision["recomputed_verification_state"] == COULD_NOT_VERIFY
    assert decision["recomputed_result"]["scan_origin_binding"]["reason"] == "historical_and_current_scan_origins_differ"


def test_regression_reopen_replay_fails_closed_when_current_evidence_origin_is_foreign():
    previous, plan, _, rows = evidence()
    previous["verification_state"] = "verified_fixed"
    decision = strict_regression_reopen_from_observations(
        previous,
        plan,
        pages(f"{OTHER_ORIGIN}/a", "/b"),
        rows,
        contract(),
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert decision["version"] == STRICT_REGRESSION_REOPEN_OBSERVATION_REPLAY_VERSION
    assert decision["should_reopen"] is False
    assert decision["recomputed_verification_state"] == COULD_NOT_VERIFY
    assert decision["recomputed_result"]["scan_origin_binding"]["reason"] == "current_page_0_url_origin_mismatch"
