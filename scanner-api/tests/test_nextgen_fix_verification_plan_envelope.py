from copy import deepcopy

from app.nextgen_fix_regression_reopen_replay import strict_regression_reopen_from_observations
from app.nextgen_fix_verification import build_targeted_recheck_plan
from app.nextgen_fix_verification_plan_envelope import (
    PLAN_ENVELOPE_INTEGRITY_VERSION,
    verification_plan_envelope_integrity,
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


def evaluations(plan, detected=False):
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
        for request in plan["requests"]
    ]


def ready_plan(previous=None):
    return build_targeted_recheck_plan(
        previous or fix(),
        previous_scan_origin=ORIGIN,
    )


def test_generated_ready_plan_envelope_is_valid():
    result = verification_plan_envelope_integrity(ready_plan())
    assert result["version"] == PLAN_ENVELOPE_INTEGRITY_VERSION
    assert result["valid"] is True
    assert result["population_count"] == 2
    assert result["request_count"] == 2


def test_unknown_plan_version_fails_closed():
    plan = ready_plan()
    plan["version"] = "fix_verification_plan_v999"
    result = verification_plan_envelope_integrity(plan)
    assert result["valid"] is False
    assert result["reason"] == "unsupported_verification_plan_version"


def test_non_ready_plan_state_fails_closed():
    plan = ready_plan()
    plan["state"] = "bounded_incomplete"
    result = verification_plan_envelope_integrity(plan)
    assert result["valid"] is False
    assert result["reason"] == "verification_plan_not_ready"


def test_population_complete_must_be_exact_true():
    plan = ready_plan()
    plan["population_complete"] = 1
    result = verification_plan_envelope_integrity(plan)
    assert result["valid"] is False
    assert result["reason"] == "verification_plan_population_not_explicitly_complete"


def test_ready_plan_cannot_carry_blockers():
    plan = ready_plan()
    plan["blockers"] = ["ambiguous_or_unresolvable_evidence_url"]
    result = verification_plan_envelope_integrity(plan)
    assert result["valid"] is False
    assert result["reason"] == "verification_plan_ready_state_has_blockers"


def test_ready_plan_cannot_report_invalid_population():
    plan = ready_plan()
    plan["invalid_population_count"] = 1
    result = verification_plan_envelope_integrity(plan)
    assert result["valid"] is False
    assert result["reason"] == "verification_plan_ready_state_has_invalid_population"


def test_ready_plan_cannot_report_omitted_population():
    plan = ready_plan()
    plan["omitted_population_count"] = 1
    result = verification_plan_envelope_integrity(plan)
    assert result["valid"] is False
    assert result["reason"] == "verification_plan_ready_state_has_omitted_population"


def test_max_recheck_urls_rejects_boolean_coercion():
    plan = ready_plan()
    plan["max_recheck_urls"] = True
    result = verification_plan_envelope_integrity(plan)
    assert result["valid"] is False
    assert result["reason"] == "verification_plan_max_recheck_urls_invalid"


def test_population_cannot_exceed_declared_plan_limit():
    plan = ready_plan()
    plan["max_recheck_urls"] = 1
    result = verification_plan_envelope_integrity(plan)
    assert result["valid"] is False
    assert result["reason"] == "verification_plan_population_exceeds_declared_limit"


def test_request_count_must_equal_declared_population_count():
    plan = ready_plan()
    plan["requests"] = plan["requests"][:1]
    result = verification_plan_envelope_integrity(plan)
    assert result["valid"] is False
    assert result["reason"] == "verification_plan_request_count_mismatch"


def test_criterion_version_must_be_supported():
    plan = ready_plan()
    plan["criterion"]["version"] = "fix_acceptance_criterion_v999"
    result = verification_plan_envelope_integrity(plan)
    assert result["valid"] is False
    assert result["reason"] == "unsupported_acceptance_criterion_version"


def test_criterion_must_be_ready():
    plan = ready_plan()
    plan["criterion"]["state"] = "blocked"
    result = verification_plan_envelope_integrity(plan)
    assert result["valid"] is False
    assert result["reason"] == "acceptance_criterion_not_ready"


def test_ready_criterion_cannot_carry_blockers():
    plan = ready_plan()
    plan["criterion"]["blockers"] = ["rule_definition_version_required"]
    result = verification_plan_envelope_integrity(plan)
    assert result["valid"] is False
    assert result["reason"] == "acceptance_criterion_ready_state_has_blockers"


def test_verified_fixed_replay_rejects_contradictory_ready_plan_envelope():
    previous = fix()
    plan = ready_plan(previous)
    plan = deepcopy(plan)
    plan["omitted_population_count"] = 1

    decision = strict_verified_fixed_transition_from_observations(
        previous,
        plan,
        pages(),
        evaluations(plan, detected=False),
        [],
        contract(),
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )

    assert decision["allowed"] is False
    assert decision["reason"] == "verification_plan_envelope_integrity_failed"
    assert decision["verification_plan_envelope_integrity"]["valid"] is False
    assert decision["verification_plan_envelope_integrity"]["reason"] == (
        "verification_plan_ready_state_has_omitted_population"
    )


def test_regression_reopen_replay_rejects_contradictory_ready_plan_envelope():
    previous = fix(state="verified_fixed")
    plan = ready_plan(previous)
    plan = deepcopy(plan)
    plan["blockers"] = ["transport_ambiguity"]

    decision = strict_regression_reopen_from_observations(
        previous,
        plan,
        pages(),
        evaluations(plan, detected=True),
        contract(),
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )

    assert decision["should_reopen"] is False
    assert decision["reason"] == "verification_plan_envelope_integrity_failed"
    assert decision["verification_plan_envelope_integrity"]["valid"] is False
    assert decision["verification_plan_envelope_integrity"]["reason"] == (
        "verification_plan_ready_state_has_blockers"
    )
