from copy import deepcopy

from app.nextgen_fix_verification import (
    COULD_NOT_VERIFY,
    PASS,
    build_targeted_recheck_plan,
)
from app.nextgen_fix_verification_observation_integrity import (
    OBSERVATION_INPUT_INTEGRITY_VERSION,
    evaluate_verification_observations_strict,
    verification_observation_input_integrity,
)
from app.nextgen_fix_verified_fixed_observation_replay import (
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


def test_exact_observation_metadata_preserves_normal_pass_behavior():
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    result = evaluate_verification_observations_strict(
        plan,
        previous,
        pages("/a", "/b"),
        evaluations(plan, [False, False]),
        contract(),
        scan_origin=ORIGIN,
    )
    assert result["state"] == PASS
    assert result["observation_input_integrity"]["version"] == OBSERVATION_INPUT_INTEGRITY_VERSION
    assert result["observation_input_integrity"]["valid"] is True


def test_numeric_historical_version_fails_closed_instead_of_string_coercion():
    previous = fix(rule_definition_version=3)
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    result = evaluate_verification_observations_strict(
        plan,
        previous,
        pages("/a", "/b"),
        evaluations(plan, [False, False]),
        contract(rule_definition_version=3),
        scan_origin=ORIGIN,
    )
    assert result["state"] == COULD_NOT_VERIFY
    assert "historical_rule_definition_version_must_be_exact_nonempty_string" in result["reason"]


def test_whitespace_padded_current_contract_version_fails_closed():
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    result = evaluate_verification_observations_strict(
        plan,
        previous,
        pages("/a", "/b"),
        evaluations(plan, [False, False]),
        contract(comparison_profile_version=" standard150_review_v2 "),
        scan_origin=ORIGIN,
    )
    assert result["state"] == COULD_NOT_VERIFY
    assert "current_contract_comparison_profile_version_must_be_exact_nonempty_string" in result["reason"]


def test_whitespace_padded_plan_identity_fails_closed_before_evaluation():
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    plan = deepcopy(plan)
    plan["criterion_id"] = f" {plan['criterion_id']} "
    result = evaluate_verification_observations_strict(
        plan,
        previous,
        pages("/a", "/b"),
        evaluations(plan, [False, False]),
        contract(),
        scan_origin=ORIGIN,
    )
    assert result["state"] == COULD_NOT_VERIFY
    assert "plan_criterion_id_must_be_exact_nonempty_string" in result["reason"]


def test_whitespace_padded_nested_criterion_identity_fails_closed():
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    plan = deepcopy(plan)
    plan["criterion"] = {
        **plan["criterion"],
        "repair_fingerprint": f" {plan['criterion']['repair_fingerprint']} ",
    }
    result = evaluate_verification_observations_strict(
        plan,
        previous,
        pages("/a", "/b"),
        evaluations(plan, [False, False]),
        contract(),
        scan_origin=ORIGIN,
    )
    assert result["state"] == COULD_NOT_VERIFY
    assert "criterion_repair_fingerprint_must_be_exact_nonempty_string" in result["reason"]


def test_whitespace_padded_rule_evaluation_evidence_key_fails_closed_without_url_fallback():
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    rows = evaluations(plan, [False, False])
    rows[0] = deepcopy(rows[0])
    rows[0].pop("url")
    rows[0]["evidence_key"] = f" {rows[0]['evidence_key']} "
    result = evaluate_verification_observations_strict(
        plan,
        previous,
        pages("/a", "/b"),
        rows,
        contract(),
        scan_origin=ORIGIN,
    )
    assert result["state"] == COULD_NOT_VERIFY
    assert "rule_evaluation_0_evidence_key_must_be_exact_nonempty_string" in result["reason"]


def test_numeric_rule_evaluation_version_fails_closed_when_text_would_otherwise_match():
    previous = fix(rule_definition_version="3")
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    rows = evaluations(plan, [False, False])
    rows[0] = {**rows[0], "rule_definition_version": 3}
    result = evaluate_verification_observations_strict(
        plan,
        previous,
        pages("/a", "/b"),
        rows,
        contract(rule_definition_version="3"),
        scan_origin=ORIGIN,
    )
    assert result["state"] == COULD_NOT_VERIFY
    assert "rule_evaluation_0_rule_definition_version_must_be_exact_nonempty_string" in result["reason"]


def test_final_observation_replay_uses_exact_metadata_boundary():
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    rows = evaluations(plan, [False, False])
    rows[0] = {**rows[0], "repair_fingerprint": f" {rows[0]['repair_fingerprint']} "}

    integrity = verification_observation_input_integrity(
        previous,
        plan,
        pages("/a", "/b"),
        rows,
        contract(),
    )
    assert integrity["valid"] is False

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
    assert decision["recomputed_result"]["observation_input_integrity"]["valid"] is False
