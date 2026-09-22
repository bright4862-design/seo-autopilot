from copy import deepcopy

from app.nextgen_fix_regression_reopen_replay import strict_regression_reopen_from_observations
from app.nextgen_fix_verification import COULD_NOT_VERIFY, PASS, build_targeted_recheck_plan
from app.nextgen_fix_verification_historical_bound import (
    evaluate_verification_observations_historical_bound,
)
from app.nextgen_fix_verification_historical_evidence_aliases import (
    HISTORICAL_EVIDENCE_ALIAS_INTEGRITY_VERSION,
    verification_historical_evidence_alias_integrity,
)
from app.nextgen_fix_verified_fixed_observation_replay import (
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


def test_alias_integrity_accepts_fallback_aliases_inside_explicit_population():
    previous = fix(page_url="/a", representative_page_url="/b")
    integrity = verification_historical_evidence_alias_integrity(previous, scan_origin=ORIGIN)
    assert integrity["version"] == HISTORICAL_EVIDENCE_ALIAS_INTEGRITY_VERSION
    assert integrity["valid"] is True
    assert integrity["historical_population_count"] == 2
    assert integrity["checked_fallback_aliases"] == 2


def test_alias_integrity_rejects_page_url_outside_explicit_population():
    previous = fix(page_url="/c")
    integrity = verification_historical_evidence_alias_integrity(previous, scan_origin=ORIGIN)
    assert integrity["valid"] is False
    assert integrity["reason"] == "historical_page_url_not_in_affected_population"


def test_alias_integrity_rejects_foreign_representative_outside_explicit_population():
    previous = fix(representative_page_url=f"{OTHER_ORIGIN}/a")
    integrity = verification_historical_evidence_alias_integrity(previous, scan_origin=ORIGIN)
    assert integrity["valid"] is False
    assert integrity["reason"] == "historical_representative_page_url_not_in_affected_population"


def test_alias_integrity_accepts_matching_fallbacks_without_explicit_population():
    previous = fix(affected_pages=[], page_url="/a", representative_page_url="/a")
    integrity = verification_historical_evidence_alias_integrity(previous, scan_origin=ORIGIN)
    assert integrity["valid"] is True
    assert integrity["reason"] == "historical_fallback_aliases_resolve_to_one_evidence_identity"
    assert integrity["historical_population_count"] == 1


def test_alias_integrity_rejects_conflicting_fallbacks_without_explicit_population():
    previous = fix(affected_pages=[], page_url="/a", representative_page_url="/b")
    integrity = verification_historical_evidence_alias_integrity(previous, scan_origin=ORIGIN)
    assert integrity["valid"] is False
    assert integrity["reason"] == "historical_fallback_evidence_aliases_conflict"


def test_alias_integrity_rejects_malformed_affected_pages_transport():
    previous = fix(affected_pages="/a", page_url="/a")
    integrity = verification_historical_evidence_alias_integrity(previous, scan_origin=ORIGIN)
    assert integrity["valid"] is False
    assert integrity["reason"] == "historical_affected_pages_not_a_list"


def test_historical_bound_evaluator_fails_closed_on_ignored_fallback_conflict():
    previous = fix(page_url="/c")
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
    assert result["historical_evidence_alias_integrity"]["reason"] == "historical_page_url_not_in_affected_population"


def test_historical_bound_evaluator_preserves_pass_for_consistent_aliases():
    previous = fix(page_url="/a", representative_page_url="/b")
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
    assert result["historical_evidence_alias_integrity"]["valid"] is True


def test_verified_fixed_replay_denies_conflicting_historical_fallback_alias():
    previous = fix(page_url="/c")
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
    assert (
        decision["recomputed_result"]["historical_evidence_alias_integrity"]["reason"]
        == "historical_page_url_not_in_affected_population"
    )


def test_regression_reopen_replay_denies_conflicting_historical_fallback_alias():
    previous = fix(page_url="/c", verification_state="verified_fixed")
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    decision = strict_regression_reopen_from_observations(
        previous,
        plan,
        pages("/a", "/b"),
        evaluations(plan, [True, True]),
        contract(),
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert decision["should_reopen"] is False
    assert decision["recomputed_verification_state"] == COULD_NOT_VERIFY
    assert (
        decision["recomputed_result"]["historical_evidence_alias_integrity"]["reason"]
        == "historical_page_url_not_in_affected_population"
    )
