from copy import deepcopy

from app.nextgen_fix_regression_reopen_replay import (
    strict_regression_reopen_from_observations,
)
from app.nextgen_fix_verification import (
    COULD_NOT_VERIFY,
    PASS,
    build_targeted_recheck_plan,
)
from app.nextgen_fix_verification_observation_identity import (
    OBSERVATION_IDENTITY_BINDING_VERSION,
    evaluate_verification_observations_identity_bound,
    verification_observation_identity_binding,
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


def prepared(detected_states=(False, False)):
    previous = fix()
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    return previous, plan, pages("/a", "/b"), evaluations(plan, detected_states)


def test_exact_multi_field_observation_identity_preserves_normal_pass():
    previous, plan, current_pages, rows = prepared()
    current_pages[0]["path"] = "/a"
    current_pages[0]["final_url"] = "https://example.com/a"

    result = evaluate_verification_observations_identity_bound(
        plan,
        previous,
        current_pages,
        rows,
        contract(),
        scan_origin=ORIGIN,
    )

    assert result["state"] == PASS
    binding = result["observation_identity_binding"]
    assert binding["version"] == OBSERVATION_IDENTITY_BINDING_VERSION
    assert binding["valid"] is True


def test_current_page_conflicting_url_and_final_url_fail_closed():
    previous, plan, current_pages, rows = prepared()
    current_pages[0]["final_url"] = "/foreign"

    result = evaluate_verification_observations_identity_bound(
        plan,
        previous,
        current_pages,
        rows,
        contract(),
        scan_origin=ORIGIN,
    )

    assert result["state"] == COULD_NOT_VERIFY
    assert result["observation_identity_binding"]["reason"] == "current_page_0_identity_fields_conflict"


def test_current_page_whitespace_padded_identity_fails_closed():
    previous, plan, current_pages, rows = prepared()
    current_pages[0]["url"] = " /a "

    result = evaluate_verification_observations_identity_bound(
        plan,
        previous,
        current_pages,
        rows,
        contract(),
        scan_origin=ORIGIN,
    )

    assert result["state"] == COULD_NOT_VERIFY
    assert result["observation_identity_binding"]["reason"] == "current_page_0_url_must_be_exact_nonempty_string"


def test_current_page_without_any_identity_fails_closed():
    previous, plan, current_pages, rows = prepared()
    current_pages[0] = {
        "status_code": 200,
        "content_type": "text/html",
        "indexable": True,
    }

    binding = verification_observation_identity_binding(
        current_pages,
        rows,
        contract(),
        scan_origin=ORIGIN,
    )

    assert binding["valid"] is False
    assert binding["reason"] == "current_page_0_evidence_identity_missing"


def test_rule_evaluation_url_aliases_must_resolve_to_one_identity():
    previous, plan, current_pages, rows = prepared()
    rows[0] = {**rows[0], "page_url": "/foreign"}

    result = evaluate_verification_observations_identity_bound(
        plan,
        previous,
        current_pages,
        rows,
        contract(),
        scan_origin=ORIGIN,
    )

    assert result["state"] == COULD_NOT_VERIFY
    assert result["observation_identity_binding"]["reason"] == "rule_evaluation_0_identity_fields_conflict"


def test_rule_evaluation_evidence_key_must_agree_with_url_identity():
    previous, plan, current_pages, rows = prepared()
    rows[0] = {**rows[0], "evidence_key": "https://example.com/foreign"}

    result = evaluate_verification_observations_identity_bound(
        plan,
        previous,
        current_pages,
        rows,
        contract(),
        scan_origin=ORIGIN,
    )

    assert result["state"] == COULD_NOT_VERIFY
    assert result["observation_identity_binding"]["reason"] == "rule_evaluation_0_identity_fields_conflict"


def test_rule_evaluation_evidence_key_must_already_be_canonical():
    previous, plan, current_pages, rows = prepared()
    rows[0] = {**rows[0], "evidence_key": "HTTPS://EXAMPLE.COM/a"}

    result = evaluate_verification_observations_identity_bound(
        plan,
        previous,
        current_pages,
        rows,
        contract(),
        scan_origin=ORIGIN,
    )

    assert result["state"] == COULD_NOT_VERIFY
    assert result["observation_identity_binding"]["reason"] == "rule_evaluation_0_evidence_key_not_canonical"


def test_verified_fixed_replay_rejects_conflicting_redirect_identity():
    previous, plan, current_pages, rows = prepared()
    current_pages[0]["final_url"] = "/foreign"

    decision = strict_verified_fixed_transition_from_observations(
        previous,
        plan,
        current_pages,
        rows,
        [],
        contract(),
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )

    assert decision["allowed"] is False
    assert decision["recomputed_verification_state"] == COULD_NOT_VERIFY
    assert decision["recomputed_result"]["observation_identity_binding"]["valid"] is False


def test_regression_reopen_replay_rejects_conflicting_redirect_identity():
    previous, plan, current_pages, rows = prepared((True, True))
    previous = {**previous, "state": "verified_fixed"}
    current_pages[0]["final_url"] = "/foreign"

    decision = strict_regression_reopen_from_observations(
        previous,
        plan,
        current_pages,
        rows,
        contract(),
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )

    assert decision["should_reopen"] is False
    assert decision["recomputed_verification_state"] == COULD_NOT_VERIFY
    assert decision["recomputed_result"]["observation_identity_binding"]["valid"] is False


def test_identity_binding_does_not_mutate_observation_inputs():
    previous, plan, current_pages, rows = prepared()
    before_pages = deepcopy(current_pages)
    before_rows = deepcopy(rows)

    binding = verification_observation_identity_binding(
        current_pages,
        rows,
        contract(),
        scan_origin=ORIGIN,
    )

    assert binding["valid"] is True
    assert current_pages == before_pages
    assert rows == before_rows
