from copy import deepcopy

from app.nextgen_fix_regression_reopen_replay import strict_regression_reopen_from_observations
from app.nextgen_fix_verification import (
    COULD_NOT_VERIFY,
    PASS,
    build_targeted_recheck_plan,
)
from app.nextgen_fix_verification_observation_values import (
    OBSERVATION_VALUE_INTEGRITY_VERSION,
    evaluate_verification_observations_value_bound,
    verification_observation_value_integrity,
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
        "state": "verified_fixed",
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


def evaluate(current_pages, *, detected_states=(False, False)):
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    return evaluate_verification_observations_value_bound(
        plan,
        previous,
        current_pages,
        evaluations(plan, detected_states),
        contract(),
        scan_origin=ORIGIN,
    )


def test_exact_machine_typed_observation_values_preserve_pass():
    result = evaluate(pages("/a", "/b"))
    assert result["state"] == PASS
    assert result["observation_value_integrity"]["valid"] is True
    assert (
        result["observation_value_integrity"]["version"]
        == OBSERVATION_VALUE_INTEGRITY_VERSION
    )


def test_numeric_string_http_status_fails_closed_instead_of_int_coercion():
    current = pages("/a", "/b")
    current[0]["status_code"] = "200"
    result = evaluate(current)
    assert result["state"] == COULD_NOT_VERIFY
    assert "current_page_0_status_code_must_be_exact_integer" in result["reason"]


def test_float_http_status_fails_closed_instead_of_int_coercion():
    current = pages("/a", "/b")
    current[0]["status_code"] = 200.0
    result = evaluate(current)
    assert result["state"] == COULD_NOT_VERIFY
    assert "current_page_0_status_code_must_be_exact_integer" in result["reason"]


def test_conflicting_status_aliases_fail_closed():
    current = pages("/a", "/b")
    current[0]["status"] = 404
    result = evaluate(current)
    assert result["state"] == COULD_NOT_VERIFY
    assert "current_page_0_http_status_fields_conflict" in result["reason"]


def test_non_string_content_type_that_stringifies_to_html_fails_closed():
    current = pages("/a", "/b")
    current[0]["content_type"] = ["text/html"]
    result = evaluate(current)
    assert result["state"] == COULD_NOT_VERIFY
    assert "current_page_0_content_type_must_be_exact_nonempty_string" in result["reason"]


def test_missing_content_type_fails_closed():
    current = pages("/a", "/b")
    current[0].pop("content_type")
    result = evaluate(current)
    assert result["state"] == COULD_NOT_VERIFY
    assert "current_page_0_content_type_missing" in result["reason"]


def test_string_indexability_fails_closed_instead_of_becoming_unknown_but_comparable():
    current = pages("/a", "/b")
    current[0]["indexable"] = "true"
    result = evaluate(current)
    assert result["state"] == COULD_NOT_VERIFY
    assert "current_page_0_indexable_must_be_exact_boolean" in result["reason"]


def test_indexable_true_conflicting_with_noindex_robots_fails_closed():
    current = pages("/a", "/b")
    current[0]["robots"] = "noindex,follow"
    result = evaluate(current)
    assert result["state"] == COULD_NOT_VERIFY
    assert "current_page_0_indexability_conflicts_with_robots" in result["reason"]


def test_verified_fixed_final_replay_cannot_authorize_coerced_http_status():
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    current = pages("/a", "/b")
    current[0]["status_code"] = "200"

    decision = strict_verified_fixed_transition_from_observations(
        previous,
        plan,
        current,
        evaluations(plan, [False, False]),
        [],
        contract(),
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert decision["allowed"] is False
    assert decision["recomputed_verification_state"] == COULD_NOT_VERIFY
    assert decision["recomputed_result"]["observation_value_integrity"]["valid"] is False


def test_regression_reopen_final_replay_cannot_use_coerced_http_status_as_regression_proof():
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    current = pages("/a", "/b")
    current[0]["status_code"] = "200"

    decision = strict_regression_reopen_from_observations(
        previous,
        plan,
        current,
        evaluations(plan, [True, True]),
        contract(),
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert decision["should_reopen"] is False
    assert decision["recomputed_verification_state"] == COULD_NOT_VERIFY
    assert decision["recomputed_result"]["observation_value_integrity"]["valid"] is False


def test_value_integrity_helper_does_not_mutate_inputs():
    current = pages("/a", "/b")
    previous_pages = deepcopy(current)
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    rows = evaluations(plan, [False, True])
    previous_rows = deepcopy(rows)

    result = verification_observation_value_integrity(current, rows)

    assert result["valid"] is True
    assert current == previous_pages
    assert rows == previous_rows
