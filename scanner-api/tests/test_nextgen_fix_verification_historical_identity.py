from copy import deepcopy

from app.nextgen_fix_regression_reopen_replay import (
    strict_regression_reopen_from_observations,
)
from app.nextgen_fix_verification import (
    COULD_NOT_VERIFY,
    PARTIAL,
    PASS,
    build_targeted_recheck_plan,
)
from app.nextgen_fix_verification_historical_bound import (
    HISTORICAL_BOUND_OBSERVATION_VERSION,
    evaluate_verification_observations_historical_bound,
)
from app.nextgen_fix_verification_historical_identity import (
    HISTORICAL_IDENTITY_INTEGRITY_VERSION,
    verification_historical_identity_integrity,
)
from app.nextgen_fix_verified_fixed_observation_replay import (
    strict_verified_fixed_transition_from_observations,
)
from app.repair_coverage import PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION
from app.repair_identity import build_repair_identity

ORIGIN = "https://example.com"


def fix(**overrides):
    base = {
        "rule_id": "missing_meta_description",
        "rule": "Missing meta description",
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


def test_exact_historical_identity_source_binding_accepts_canonical_rule_plus_display_copy():
    result = verification_historical_identity_integrity(fix())
    assert result["version"] == HISTORICAL_IDENTITY_INTEGRITY_VERSION
    assert result["valid"] is True
    assert result["repair_fingerprint"] == build_repair_identity(fix())["fingerprint"]


def test_numeric_canonical_rule_cannot_be_coerced_into_stable_proof_identity():
    result = verification_historical_identity_integrity(fix(rule_id=3))
    assert result["valid"] is False
    assert result["reason"] == "historical_rule_rule_id_must_be_exact_nonempty_string"


def test_whitespace_padded_repair_surface_cannot_be_normalized_into_proof_identity():
    result = verification_historical_identity_integrity(fix(repair_surface=" product_template "))
    assert result["valid"] is False
    assert result["reason"] == "historical_repair_surface_repair_surface_must_be_exact_nonempty_string"


def test_mismatched_persisted_fingerprint_fails_closed_against_fresh_derivation():
    previous = fix(repair_fingerprint="copied-foreign-fingerprint")
    result = verification_historical_identity_integrity(previous)
    assert result["valid"] is False
    assert result["reason"] == "historical_repair_fingerprint_does_not_match_derived_identity"


def test_matching_persisted_identity_metadata_remains_valid():
    previous = fix()
    derived = build_repair_identity(previous)
    previous = {
        **previous,
        "repair_identity_version": derived["version"],
        "repair_fingerprint": derived["fingerprint"],
        "repair_identity_state": derived["state"],
        "repair_identity_stable": derived["stable"],
        "repair_identity": deepcopy(derived),
    }
    result = verification_historical_identity_integrity(previous)
    assert result["valid"] is True


def test_conflicting_nested_identity_snapshot_fails_closed():
    previous = fix()
    previous["repair_identity"] = {
        **build_repair_identity(previous),
        "fingerprint": "copied-foreign-fingerprint",
    }
    result = verification_historical_identity_integrity(previous)
    assert result["valid"] is False
    assert result["reason"] == "historical_repair_identity_fingerprint_does_not_match_derived_identity"


def test_historical_bound_evaluator_preserves_normal_pass():
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    result = evaluate_verification_observations_historical_bound(
        plan,
        previous,
        pages("/a", "/b"),
        evaluations(plan, [False, False]),
        contract(),
        scan_origin=ORIGIN,
    )
    assert result["state"] == PASS
    assert result["historical_bound_observation_version"] == HISTORICAL_BOUND_OBSERVATION_VERSION
    assert result["historical_identity_integrity"]["valid"] is True


def test_historical_bound_evaluator_turns_tolerantly_coercible_identity_into_could_not_verify():
    previous = fix(remediation_family=7)
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    result = evaluate_verification_observations_historical_bound(
        plan,
        previous,
        pages("/a", "/b"),
        evaluations(plan, [False, False]),
        contract(),
        scan_origin=ORIGIN,
    )
    assert result["state"] == COULD_NOT_VERIFY
    assert result["historical_identity_integrity"]["valid"] is False
    assert "historical_remediation_family_remediation_family_must_be_exact_nonempty_string" in result["reason"]


def test_historical_bound_evaluator_keeps_disappeared_url_as_non_proof():
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    result = evaluate_verification_observations_historical_bound(
        plan,
        previous,
        pages("/a"),
        evaluations(plan, [False, False]),
        contract(),
        scan_origin=ORIGIN,
    )
    assert result["state"] == COULD_NOT_VERIFY
    assert any(item["reason"] == "required_page_not_observed" for item in result["unverifiable_scope"])


def test_final_verified_fixed_replay_rejects_conflicting_historical_fingerprint():
    previous = fix(repair_fingerprint="copied-foreign-fingerprint")
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    decision = strict_verified_fixed_transition_from_observations(
        previous,
        plan,
        pages("/a", "/b"),
        evaluations(plan, [False, False]),
        [],
        contract(),
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert decision["allowed"] is False
    assert decision["recomputed_verification_state"] == COULD_NOT_VERIFY
    assert decision["recomputed_result"]["historical_identity_integrity"]["valid"] is False


def test_regression_reopen_replay_rejects_malformed_historical_identity_source():
    previous = fix(repair_surface=7, verification_state="verified_fixed")
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    decision = strict_regression_reopen_from_observations(
        previous,
        plan,
        pages("/a", "/b"),
        evaluations(plan, [False, True]),
        contract(),
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert decision["should_reopen"] is False
    assert decision["recomputed_verification_state"] == COULD_NOT_VERIFY
    assert decision["recomputed_result"]["historical_identity_integrity"]["valid"] is False


def test_regression_reopen_replay_still_reopens_on_proven_partial_with_valid_identity():
    previous = fix(verification_state="verified_fixed")
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    decision = strict_regression_reopen_from_observations(
        previous,
        plan,
        pages("/a", "/b"),
        evaluations(plan, [False, True]),
        contract(),
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert decision["should_reopen"] is True
    assert decision["recomputed_verification_state"] == PARTIAL
    assert decision["reopen_scope"] == [plan["requests"][1]["evidence_key"]]
