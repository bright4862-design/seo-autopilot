from copy import deepcopy

from app.nextgen_fix_verification import (
    COULD_NOT_VERIFY,
    build_targeted_recheck_plan,
)
from app.nextgen_fix_verification_observation_integrity import (
    OBSERVATION_INPUT_INTEGRITY_VERSION,
    evaluate_verification_observations_strict,
    verification_observation_input_integrity,
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


def contract():
    return {
        "rule_definition_version": "missing_meta_description_v3",
        "comparison_profile_version": "standard150_review_v2",
        "evidence_url_identity_version": PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION,
    }


def pages():
    return [
        {"url": "/a", "status_code": 200, "content_type": "text/html", "indexable": True},
        {"url": "/b", "status_code": 200, "content_type": "text/html", "indexable": True},
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
            "defect_detected": False,
        }
        for request in plan["requests"]
    ]


def integrity(previous, plan):
    return verification_observation_input_integrity(
        previous,
        plan,
        pages(),
        evaluations(plan),
        contract(),
    )


def test_exact_plan_request_transport_remains_valid():
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)

    result = integrity(previous, plan)

    assert result["version"] == OBSERVATION_INPUT_INTEGRITY_VERSION
    assert result["valid"] is True
    assert result["checked_plan_requests"] == 2


def test_whitespace_padded_plan_request_evidence_key_fails_closed():
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    plan = deepcopy(plan)
    plan["requests"][0]["evidence_key"] = f" {plan['requests'][0]['evidence_key']} "

    result = integrity(previous, plan)

    assert result["valid"] is False
    assert result["reason"] == "plan_request_0_evidence_key_must_be_exact_nonempty_string"


def test_non_string_plan_request_criterion_id_fails_closed():
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    plan = deepcopy(plan)
    plan["requests"][0]["criterion_id"] = 123

    result = integrity(previous, plan)

    assert result["valid"] is False
    assert result["reason"] == "plan_request_0_criterion_id_must_be_exact_nonempty_string"


def test_whitespace_padded_plan_request_url_fails_closed_before_url_normalization():
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    plan = deepcopy(plan)
    plan["requests"][0]["url"] = " /a "

    result = integrity(previous, plan)

    assert result["valid"] is False
    assert result["reason"] == "plan_request_0_url_must_be_exact_nonempty_string"


def test_whitespace_padded_plan_request_rule_fails_closed():
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    plan = deepcopy(plan)
    plan["requests"][0]["rule"] = f" {plan['requests'][0]['rule']} "

    result = integrity(previous, plan)

    assert result["valid"] is False
    assert result["reason"] == "plan_request_0_rule_must_be_exact_nonempty_string"


def test_whitespace_padded_historical_affected_page_fails_closed():
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    malformed_previous = deepcopy(previous)
    malformed_previous["affected_pages"][0] = " /a "

    result = integrity(malformed_previous, plan)

    assert result["valid"] is False
    assert result["reason"] == "historical_affected_pages_0_must_be_exact_nonempty_string"


def test_malformed_historical_affected_pages_container_is_not_silently_replaced_by_fallback():
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    malformed_previous = deepcopy(previous)
    malformed_previous["affected_pages"] = "/a"
    malformed_previous["page_url"] = "/a"

    result = integrity(malformed_previous, plan)

    assert result["valid"] is False
    assert result["reason"] == "historical_affected_pages_not_a_list"


def test_whitespace_padded_historical_fallback_page_fails_closed():
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    malformed_previous = deepcopy(previous)
    malformed_previous["affected_pages"] = []
    malformed_previous["page_url"] = " /a "

    result = integrity(malformed_previous, plan)

    assert result["valid"] is False
    assert result["reason"] == "historical_page_url_must_be_exact_nonempty_string"


def test_strict_evaluator_cannot_upgrade_normalized_request_transport_to_proof():
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    plan = deepcopy(plan)
    plan["requests"][0]["evidence_key"] = f" {plan['requests'][0]['evidence_key']} "

    result = evaluate_verification_observations_strict(
        plan,
        previous,
        pages(),
        evaluations(plan),
        contract(),
        scan_origin=ORIGIN,
    )

    assert result["state"] == COULD_NOT_VERIFY
    assert "plan_request_0_evidence_key_must_be_exact_nonempty_string" in result["reason"]
    assert result["observation_input_integrity"]["valid"] is False
