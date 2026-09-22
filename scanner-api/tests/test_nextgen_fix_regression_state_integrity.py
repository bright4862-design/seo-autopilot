from copy import deepcopy

from app.nextgen_fix_regression_reopen_replay import (
    STRICT_REGRESSION_REOPEN_OBSERVATION_REPLAY_VERSION,
    strict_regression_reopen_from_observations,
)
from app.nextgen_fix_regression_state_integrity import (
    REGRESSION_SOURCE_STATE_INTEGRITY_VERSION,
    verification_historical_resolution_state_integrity,
)
from app.nextgen_fix_verification import COULD_NOT_VERIFY, FAIL, build_targeted_recheck_plan
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
        "state": "verified_fixed",
    }
    base.update(overrides)
    return base


def contract():
    return {
        "rule_definition_version": "missing_meta_description_v3",
        "comparison_profile_version": "standard150_review_v2",
        "evidence_url_identity_version": PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION,
    }


def pages():
    return [
        {"url": url, "status_code": 200, "content_type": "text/html", "indexable": True}
        for url in ("/a", "/b")
    ]


def evaluations(plan):
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
            "defect_detected": True,
        }
        for request in plan["requests"]
    ]


def replay(previous):
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    return strict_regression_reopen_from_observations(
        previous,
        plan,
        pages(),
        evaluations(plan),
        contract(),
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )


def test_single_verified_fixed_state_is_exact_and_resolved():
    integrity = verification_historical_resolution_state_integrity({"state": "verified_fixed"})
    assert integrity["version"] == REGRESSION_SOURCE_STATE_INTEGRITY_VERSION
    assert integrity["valid"] is True
    assert integrity["historical_resolved"] is True


def test_existing_resolved_spellings_can_coexist_without_changing_legacy_semantics():
    integrity = verification_historical_resolution_state_integrity(
        {
            "state": "PASS",
            "verification_state": "verified_fixed",
            "repair_verification_state": "fixed",
            "status": "resolved",
        }
    )
    assert integrity["valid"] is True
    assert integrity["historical_resolved"] is True
    assert set(integrity["state_classes"].values()) == {"resolved"}


def test_lowercase_pass_preserves_existing_case_insensitive_resolution_semantics():
    integrity = verification_historical_resolution_state_integrity({"state": "pass"})
    assert integrity["valid"] is True
    assert integrity["historical_resolved"] is True


def test_conflicting_resolved_and_unresolved_aliases_fail_closed():
    integrity = verification_historical_resolution_state_integrity(
        {"state": "verified_fixed", "status": "open"}
    )
    assert integrity["valid"] is False
    assert integrity["reason"] == "historical_resolution_state_conflict"


def test_whitespace_padded_state_fails_closed_without_normalization():
    integrity = verification_historical_resolution_state_integrity({"state": " verified_fixed "})
    assert integrity["valid"] is False
    assert integrity["reason"] == "historical_state_must_not_have_surrounding_whitespace"


def test_non_string_state_fails_closed_without_coercion():
    integrity = verification_historical_resolution_state_integrity({"state": 1})
    assert integrity["valid"] is False
    assert integrity["reason"] == "historical_state_must_be_a_string"


def test_missing_historical_resolution_state_is_not_proof():
    integrity = verification_historical_resolution_state_integrity({})
    assert integrity["valid"] is False
    assert integrity["reason"] == "historical_resolution_state_missing"


def test_exact_unresolved_state_is_valid_transport_but_not_resolution_proof():
    integrity = verification_historical_resolution_state_integrity({"state": "open"})
    assert integrity["valid"] is True
    assert integrity["historical_resolved"] is False
    assert integrity["reason"] == "exact_historical_nonresolved_state_proven"


def test_state_integrity_helper_does_not_mutate_historical_record():
    previous = {
        "state": "verified_fixed",
        "verification_state": "PASS",
        "nested": {"keep": [1, 2, 3]},
    }
    before = deepcopy(previous)
    verification_historical_resolution_state_integrity(previous)
    assert previous == before


def test_final_replay_denies_conflicting_historical_resolution_aliases_before_reopen():
    decision = replay(fix(status="open"))
    assert decision["version"] == STRICT_REGRESSION_REOPEN_OBSERVATION_REPLAY_VERSION
    assert decision["should_reopen"] is False
    assert decision["reason"] == "historical_resolution_state_integrity_failed"
    assert decision["recomputed_verification_state"] == COULD_NOT_VERIFY
    assert decision["historical_resolution_state_integrity"]["reason"] == "historical_resolution_state_conflict"


def test_final_replay_denies_whitespace_padded_historical_resolution_state():
    decision = replay(fix(state=" verified_fixed "))
    assert decision["should_reopen"] is False
    assert decision["reason"] == "historical_resolution_state_integrity_failed"
    assert decision["recomputed_verification_state"] == COULD_NOT_VERIFY


def test_final_replay_preserves_reopen_for_exact_agreeing_resolved_aliases():
    previous = fix(
        verification_state="PASS",
        repair_verification_state="fixed",
        status="resolved",
    )
    decision = replay(previous)
    assert decision["should_reopen"] is True
    assert decision["recomputed_verification_state"] == FAIL
    assert decision["historical_resolution_state_integrity"]["valid"] is True
    assert decision["historical_resolution_state_integrity"]["historical_resolved"] is True
