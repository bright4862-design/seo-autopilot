from app.nextgen_fix_verification import PASS, build_targeted_recheck_plan, evaluate_verification_plan
from app.nextgen_fix_verified_fixed_replay import (
    STRICT_VERIFIED_FIXED_REPLAY_VERSION,
    strict_verified_fixed_transition_from_evidence,
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


def nextgen_pass(previous):
    plan = build_targeted_recheck_plan(previous, previous_scan_origin=ORIGIN)
    current_pages = pages("/a", "/b")
    result = evaluate_verification_plan(
        plan,
        previous,
        current_pages,
        evaluations(plan, [False, False]),
        contract(),
        scan_origin=ORIGIN,
    )
    assert result["state"] == PASS
    return result, current_pages


def test_replay_allows_only_after_existing_comparator_is_recomputed():
    previous = fix()
    result, current_pages = nextgen_pass(previous)
    decision = strict_verified_fixed_transition_from_evidence(
        previous,
        result,
        [],
        current_pages,
        contract(),
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert decision["version"] == STRICT_VERIFIED_FIXED_REPLAY_VERSION
    assert decision["allowed"] is True
    assert decision["legacy_comparison"]["state"] == "verified_fixed"


def test_replay_rejects_same_repair_still_detected_even_if_nextgen_transport_says_pass():
    previous = fix()
    result, current_pages = nextgen_pass(previous)
    decision = strict_verified_fixed_transition_from_evidence(
        previous,
        result,
        [fix()],
        current_pages,
        contract(),
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert decision["allowed"] is False
    assert decision["legacy_comparison"]["state"] == "still_detected"


def test_replay_rejects_disappeared_page_even_if_transport_result_was_previously_pass():
    previous = fix()
    result, _ = nextgen_pass(previous)
    decision = strict_verified_fixed_transition_from_evidence(
        previous,
        result,
        [],
        pages("/a"),
        contract(),
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert decision["allowed"] is False
    assert decision["legacy_comparison"]["state"] == "could_not_verify"


def test_replay_rejects_ineligible_page_even_if_transport_result_was_previously_pass():
    previous = fix()
    result, current_pages = nextgen_pass(previous)
    current_pages[1] = {
        "url": "/b",
        "status_code": 404,
        "content_type": "text/html",
        "indexable": True,
    }
    decision = strict_verified_fixed_transition_from_evidence(
        previous,
        result,
        [],
        current_pages,
        contract(),
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert decision["allowed"] is False
    assert decision["legacy_comparison"]["state"] == "could_not_verify"


def test_replay_rejects_comparison_contract_drift():
    previous = fix()
    result, current_pages = nextgen_pass(previous)
    decision = strict_verified_fixed_transition_from_evidence(
        previous,
        result,
        [],
        current_pages,
        contract(rule_definition_version="missing_meta_description_v4"),
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert decision["allowed"] is False
    assert decision["legacy_comparison"]["state"] == "could_not_verify"


def test_replay_fails_closed_on_malformed_evidence_container():
    previous = fix()
    result, _ = nextgen_pass(previous)
    decision = strict_verified_fixed_transition_from_evidence(
        previous,
        result,
        [],
        "not-a-page-list",
        contract(),
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert decision == {
        "version": STRICT_VERIFIED_FIXED_REPLAY_VERSION,
        "allowed": False,
        "reason": "current_pages_not_a_list",
        "legacy_comparison": {},
        "strict_transition": {},
    }
