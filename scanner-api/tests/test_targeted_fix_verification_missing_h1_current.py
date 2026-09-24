from app.missing_h1_comparison_contract import (
    MISSING_H1_COMPARISON_PROFILE_VERSION,
    MISSING_H1_REMEDIATION_FAMILY,
    MISSING_H1_REPAIR_SURFACE,
    MISSING_H1_RULE,
    MISSING_H1_RULE_DEFINITION_VERSION,
)
from app.repair_coverage import PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION
from app.targeted_fix_verification import (
    TARGETED_FIX_VERIFICATION_OBSERVATION_VERSION,
    build_rule_evaluation_receipt,
    build_targeted_recheck_plan,
    build_verification_criteria,
    evaluate_targeted_fix_verification,
)

ORIGIN = "https://example.com"


def repair(urls=None, **overrides):
    value = {
        "rule": MISSING_H1_RULE,
        "category": "thin_content",
        "repair_surface": MISSING_H1_REPAIR_SURFACE,
        "remediation_family": MISSING_H1_REMEDIATION_FAMILY,
        "affected_pages": urls or ["/a", "/b"],
        "rule_definition_version": MISSING_H1_RULE_DEFINITION_VERSION,
        "comparison_profile_version": MISSING_H1_COMPARISON_PROFILE_VERSION,
        "evidence_url_identity_version": PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION,
    }
    value.update(overrides)
    return value


def contract():
    return {
        "rule_definition_version": MISSING_H1_RULE_DEFINITION_VERSION,
        "comparison_profile_version": MISSING_H1_COMPARISON_PROFILE_VERSION,
        "evidence_url_identity_version": PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION,
    }


def ready_plan(sealed):
    return build_targeted_recheck_plan(
        sealed,
        source_scan_id="scan-old",
        source_scan_origin=ORIGIN,
    )


def observed(plan, key, *, finding_present=None):
    page = {
        "url": key,
        "status_code": 200,
        "content_type": "text/html",
        "page_evidence_class": "usable_html",
        "indexable": True,
    }
    if finding_present is not None:
        page["comparison_rule_evaluation"] = {
            "rule": MISSING_H1_RULE,
            "rule_definition_version": MISSING_H1_RULE_DEFINITION_VERSION,
            "comparison_profile_version": MISSING_H1_COMPARISON_PROFILE_VERSION,
            "evaluated": True,
            "applicable": True,
            "finding_present": finding_present,
        }
    return {
        "version": TARGETED_FIX_VERIFICATION_OBSERVATION_VERSION,
        "plan_fingerprint": plan["plan_fingerprint"],
        "evidence_key": key,
        "state": "observed",
        "page": page,
    }


def evaluate(plan, sealed, current_fixes, outcomes):
    return evaluate_targeted_fix_verification(
        plan,
        sealed,
        current_scan_origin=ORIGIN,
        current_contract=contract(),
        recheck_outcomes=outcomes,
        current_fixes=current_fixes,
        rule_evaluation_receipt=build_rule_evaluation_receipt(plan, current_fixes),
    )


def test_deployed_missing_h1_contract_is_ready_for_targeted_verification():
    sealed = repair()
    criteria = build_verification_criteria(
        sealed,
        source_scan_id="scan-old",
        source_scan_origin=ORIGIN,
    )
    assert criteria["state"] == "ready"
    assert criteria["rule_definition_version"] == MISSING_H1_RULE_DEFINITION_VERSION
    assert criteria["comparison_profile_version"] == MISSING_H1_COMPARISON_PROFILE_VERSION
    assert criteria["affected_evidence_keys"] == [
        "https://example.com/a",
        "https://example.com/b",
    ]


def test_missing_h1_cannot_pass_from_page_reobservation_without_originating_rule_evidence():
    sealed = repair(["/a"])
    plan = ready_plan(sealed)
    key = plan["requests"][0]["evidence_key"]

    result = evaluate(plan, sealed, [], [observed(plan, key)])

    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "canonical_comparator_could_not_verify"
    assert result["comparator_result"]["state"] == "could_not_verify"


def test_missing_h1_pass_requires_exact_absent_rule_evaluation_for_every_sealed_url():
    sealed = repair()
    plan = ready_plan(sealed)
    outcomes = [
        observed(plan, row["evidence_key"], finding_present=False)
        for row in plan["requests"]
    ]

    result = evaluate(plan, sealed, [], outcomes)

    assert result["state"] == "PASS"
    assert result["verified_url_count"] == 2
    assert result["failed_url_count"] == 0
    assert {row["comparator_state"] for row in result["page_results"]} == {"verified_fixed"}


def test_missing_h1_partial_requires_positive_current_evidence_on_one_url_and_absence_on_the_other():
    sealed = repair()
    plan = ready_plan(sealed)
    keys = [row["evidence_key"] for row in plan["requests"]]
    current = [repair(["/a"])]
    outcomes = [
        observed(plan, keys[0], finding_present=True),
        observed(plan, keys[1], finding_present=False),
    ]

    result = evaluate(plan, sealed, current, outcomes)

    assert result["state"] == "PARTIAL"
    assert result["verified_url_count"] == 1
    assert result["failed_url_count"] == 1
    assert {row["comparator_state"] for row in result["page_results"]} == {
        "still_detected",
        "verified_fixed",
    }


def test_missing_h1_fail_requires_same_stable_repair_to_remain_on_all_targeted_urls():
    sealed = repair()
    plan = ready_plan(sealed)
    current = [repair(["/a", "/b"])]
    outcomes = [
        observed(plan, row["evidence_key"], finding_present=True)
        for row in plan["requests"]
    ]

    result = evaluate(plan, sealed, current, outcomes)

    assert result["state"] == "FAIL"
    assert result["verified_url_count"] == 0
    assert result["failed_url_count"] == 2
    assert {row["comparator_state"] for row in result["page_results"]} == {"still_detected"}


def test_missing_h1_one_unevaluated_url_keeps_whole_repair_could_not_verify():
    sealed = repair()
    plan = ready_plan(sealed)
    keys = [row["evidence_key"] for row in plan["requests"]]
    outcomes = [
        observed(plan, keys[0], finding_present=False),
        observed(plan, keys[1]),
    ]

    result = evaluate(plan, sealed, [], outcomes)

    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "canonical_comparator_could_not_verify"
    assert result["blocked_evidence_key"] == keys[1]


def test_old_missing_h1_rule_version_is_not_a_supported_targeted_verification_capability():
    criteria = build_verification_criteria(
        repair(rule_definition_version="missing_h1_v3"),
        source_scan_id="scan-old",
        source_scan_origin=ORIGIN,
    )
    assert criteria["state"] == "could_not_verify"
    assert "unsupported_targeted_verification_capability" in criteria["blockers"]


def test_other_stable_repair_family_is_not_a_supported_targeted_verification_capability():
    criteria = build_verification_criteria(
        {
            **repair(),
            "rule": "missing_meta_description",
            "repair_surface": "cms_meta_description_field",
            "remediation_family": "write_meta_description",
        },
        source_scan_id="scan-old",
        source_scan_origin=ORIGIN,
    )
    assert criteria["state"] == "could_not_verify"
    assert "unsupported_targeted_verification_capability" in criteria["blockers"]


def test_conflicting_rule_alias_cannot_enter_missing_h1_targeted_capability():
    criteria = build_verification_criteria(
        {
            **repair(),
            "rule": MISSING_H1_RULE,
            "rule_id": "missing_meta_description",
        },
        source_scan_id="scan-old",
        source_scan_origin=ORIGIN,
    )
    assert criteria["state"] == "could_not_verify"
    assert "unsupported_targeted_verification_capability" in criteria["blockers"]
