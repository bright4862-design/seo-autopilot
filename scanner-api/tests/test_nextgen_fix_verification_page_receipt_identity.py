from app.nextgen_fix_verification import COULD_NOT_VERIFY, FAIL, PARTIAL, PASS
from app.nextgen_fix_verification_page_receipt_identity import (
    PAGE_RECEIPT_IDENTITY_BINDING_VERSION,
    STRICT_REGRESSION_REOPEN_PAGE_RECEIPT_IDENTITY_BOUND_VERSION,
    STRICT_VERIFIED_FIXED_PAGE_RECEIPT_IDENTITY_BOUND_VERSION,
    strict_regression_reopen_from_page_receipt_identity_bound_inputs,
    strict_verified_fixed_transition_from_page_receipt_identity_bound_inputs,
    verification_page_receipt_identity_binding_integrity,
)
from app.nextgen_fix_verification_plan_identity import (
    PLAN_IDENTITY_BINDING_VERSION,
    build_identity_bound_targeted_recheck_plan,
)
from app.repair_coverage import PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION

ORIGIN = "https://example.com"
PREVIOUS_SCAN_ID = "scan-prev-001"
CURRENT_SCAN_ID = "scan-current-002"


def fix(**overrides):
    base = {
        "scan_run_id": PREVIOUS_SCAN_ID,
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
        "scan_run_id": CURRENT_SCAN_ID,
        "rule_definition_version": "missing_meta_description_v3",
        "comparison_profile_version": "standard150_review_v2",
        "evidence_url_identity_version": PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION,
    }
    base.update(overrides)
    return base


def bound_plan(previous=None):
    return build_identity_bound_targeted_recheck_plan(
        previous or fix(),
        previous_scan_origin=ORIGIN,
        previous_scan_id=PREVIOUS_SCAN_ID,
    )


def pages(plan, *urls):
    request_by_url = {request["url"]: request for request in plan["requests"]}
    return [
        {
            "scan_run_id": CURRENT_SCAN_ID,
            "url": url,
            "evidence_key": request_by_url[url]["evidence_key"],
            "verification_plan_fingerprint": plan["plan_fingerprint"],
            "verification_plan_identity_version": PLAN_IDENTITY_BINDING_VERSION,
            "status_code": 200,
            "content_type": "text/html",
            "indexable": True,
        }
        for url in urls
    ]


def evaluations(plan, detected_states):
    return [
        {
            "scan_run_id": CURRENT_SCAN_ID,
            "url": request["url"],
            "evidence_key": request["evidence_key"],
            "criterion_id": plan["criterion_id"],
            "repair_fingerprint": plan["repair_fingerprint"],
            "rule_definition_version": plan["rule_definition_version"],
            "comparison_profile_version": plan["comparison_profile_version"],
            "evidence_url_identity_version": plan["evidence_url_identity_version"],
            "verification_plan_fingerprint": plan["plan_fingerprint"],
            "verification_plan_identity_version": PLAN_IDENTITY_BINDING_VERSION,
            "evaluated": True,
            "defect_detected": detected,
        }
        for request, detected in zip(plan["requests"], detected_states)
    ]


def test_page_receipt_identity_binding_accepts_exact_receipts():
    plan = bound_plan()
    binding = verification_page_receipt_identity_binding_integrity(
        plan,
        pages(plan, "/a", "/b"),
        evaluations(plan, [False, False]),
        contract(),
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_origin=ORIGIN,
    )
    assert binding["version"] == PAGE_RECEIPT_IDENTITY_BINDING_VERSION
    assert binding["valid"] is True
    assert binding["checked_current_pages"] == 2
    assert binding["checked_evidence_keys"] == [
        plan["requests"][0]["evidence_key"],
        plan["requests"][1]["evidence_key"],
    ]


def test_page_receipt_identity_binding_rejects_swapped_target_labels():
    plan = bound_plan()
    observed = pages(plan, "/a", "/b")
    observed[0]["evidence_key"], observed[1]["evidence_key"] = (
        observed[1]["evidence_key"],
        observed[0]["evidence_key"],
    )
    binding = verification_page_receipt_identity_binding_integrity(
        plan,
        observed,
        evaluations(plan, [False, False]),
        contract(),
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_origin=ORIGIN,
    )
    assert binding["valid"] is False
    assert binding["reason"].endswith("evidence_key_does_not_match_page_identity")


def test_page_receipt_identity_binding_rejects_single_mislabeled_page():
    plan = bound_plan()
    observed = pages(plan, "/a", "/b")
    observed[0]["url"] = "/b"
    binding = verification_page_receipt_identity_binding_integrity(
        plan,
        observed,
        evaluations(plan, [False, False]),
        contract(),
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_origin=ORIGIN,
    )
    assert binding["valid"] is False
    assert binding["reason"].endswith("evidence_key_does_not_match_page_identity")
    assert binding["declared_evidence_key"] == plan["requests"][0]["evidence_key"]
    assert binding["resolved_evidence_key"] == plan["requests"][1]["evidence_key"]


def test_page_receipt_identity_binding_rejects_conflicting_page_url_aliases():
    plan = bound_plan()
    observed = pages(plan, "/a", "/b")
    observed[0]["final_url"] = "/b"
    binding = verification_page_receipt_identity_binding_integrity(
        plan,
        observed,
        evaluations(plan, [False, False]),
        contract(),
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_origin=ORIGIN,
    )
    assert binding["valid"] is False
    assert binding["reason"].startswith("observation_identity_binding_failed:")
    assert binding["observation_identity_binding"]["valid"] is False


def test_page_receipt_identity_binding_rejects_unsupported_url_identity_version():
    plan = bound_plan()
    binding = verification_page_receipt_identity_binding_integrity(
        plan,
        pages(plan, "/a", "/b"),
        evaluations(plan, [False, False]),
        contract(evidence_url_identity_version="future_identity_v9"),
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_origin=ORIGIN,
    )
    assert binding["valid"] is False
    assert "unsupported_evidence_url_identity_version" in binding["reason"]


def test_page_receipt_identity_binding_rejects_whitespace_scan_origin():
    plan = bound_plan()
    binding = verification_page_receipt_identity_binding_integrity(
        plan,
        pages(plan, "/a", "/b"),
        evaluations(plan, [False, False]),
        contract(),
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_origin=f" {ORIGIN} ",
    )
    assert binding["valid"] is False
    assert binding["reason"] == "scan_origin_must_be_exact_nonempty_string"


def test_page_receipt_identity_binding_accepts_path_only_page_identity():
    plan = bound_plan()
    observed = pages(plan, "/a", "/b")
    observed[0]["path"] = observed[0].pop("url")
    binding = verification_page_receipt_identity_binding_integrity(
        plan,
        observed,
        evaluations(plan, [False, False]),
        contract(),
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_origin=ORIGIN,
    )
    assert binding["valid"] is True


def test_page_receipt_identity_binding_rejects_foreign_origin_with_targeted_label():
    plan = bound_plan()
    observed = pages(plan, "/a", "/b")
    observed[0]["url"] = "https://other.example/a"
    binding = verification_page_receipt_identity_binding_integrity(
        plan,
        observed,
        evaluations(plan, [False, False]),
        contract(),
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_origin=ORIGIN,
    )
    assert binding["valid"] is False
    assert binding["reason"].endswith("evidence_key_does_not_match_page_identity")


def test_page_receipt_identity_bound_verified_fixed_wrapper_allows_exact_pass():
    previous = fix()
    plan = bound_plan(previous)
    decision = strict_verified_fixed_transition_from_page_receipt_identity_bound_inputs(
        previous,
        plan,
        pages(plan, "/a", "/b"),
        evaluations(plan, [False, False]),
        [],
        contract(),
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_id=CURRENT_SCAN_ID,
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert decision["version"] == STRICT_VERIFIED_FIXED_PAGE_RECEIPT_IDENTITY_BOUND_VERSION
    assert decision["allowed"] is True
    assert decision["recomputed_verification_state"] == PASS
    assert decision["page_receipt_identity_binding"]["valid"] is True


def test_page_receipt_identity_bound_verified_fixed_wrapper_fails_closed_on_swapped_labels():
    previous = fix()
    plan = bound_plan(previous)
    observed = pages(plan, "/a", "/b")
    observed[0]["evidence_key"], observed[1]["evidence_key"] = (
        observed[1]["evidence_key"],
        observed[0]["evidence_key"],
    )
    decision = strict_verified_fixed_transition_from_page_receipt_identity_bound_inputs(
        previous,
        plan,
        observed,
        evaluations(plan, [False, False]),
        [],
        contract(),
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_id=CURRENT_SCAN_ID,
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert decision["allowed"] is False
    assert decision["reason"] == "page_receipt_identity_binding_failed"
    assert decision["recomputed_verification_state"] == COULD_NOT_VERIFY


def test_page_receipt_identity_bound_regression_wrapper_reopens_exact_fail():
    previous = fix(state="verified_fixed")
    plan = bound_plan(previous)
    decision = strict_regression_reopen_from_page_receipt_identity_bound_inputs(
        previous,
        plan,
        pages(plan, "/a", "/b"),
        evaluations(plan, [True, True]),
        contract(),
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_id=CURRENT_SCAN_ID,
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert decision["version"] == STRICT_REGRESSION_REOPEN_PAGE_RECEIPT_IDENTITY_BOUND_VERSION
    assert decision["should_reopen"] is True
    assert decision["recomputed_verification_state"] == FAIL


def test_page_receipt_identity_bound_regression_wrapper_preserves_partial_scope():
    previous = fix(state="verified_fixed")
    plan = bound_plan(previous)
    decision = strict_regression_reopen_from_page_receipt_identity_bound_inputs(
        previous,
        plan,
        pages(plan, "/a", "/b"),
        evaluations(plan, [False, True]),
        contract(),
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_id=CURRENT_SCAN_ID,
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert decision["should_reopen"] is True
    assert decision["recomputed_verification_state"] == PARTIAL
    assert decision["reopen_scope"] == [plan["requests"][1]["evidence_key"]]


def test_page_receipt_identity_bound_regression_wrapper_fails_closed_on_mislabeled_page():
    previous = fix(state="verified_fixed")
    plan = bound_plan(previous)
    observed = pages(plan, "/a", "/b")
    observed[0]["url"] = "/b"
    decision = strict_regression_reopen_from_page_receipt_identity_bound_inputs(
        previous,
        plan,
        observed,
        evaluations(plan, [True, True]),
        contract(),
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_id=CURRENT_SCAN_ID,
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert decision["should_reopen"] is False
    assert decision["reason"] == "page_receipt_identity_binding_failed"
    assert decision["recomputed_verification_state"] == COULD_NOT_VERIFY


def test_disappeared_page_remains_non_proof_after_page_receipt_binding():
    previous = fix()
    plan = bound_plan(previous)
    observed = pages(plan, "/a")
    binding = verification_page_receipt_identity_binding_integrity(
        plan,
        observed,
        evaluations(plan, [False, False]),
        contract(),
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_origin=ORIGIN,
    )
    assert binding["valid"] is True
    assert binding["missing_required_evidence_keys"] == [plan["requests"][1]["evidence_key"]]

    decision = strict_verified_fixed_transition_from_page_receipt_identity_bound_inputs(
        previous,
        plan,
        observed,
        evaluations(plan, [False, False]),
        [],
        contract(),
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_id=CURRENT_SCAN_ID,
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert decision["allowed"] is False
    assert decision["page_receipt_identity_binding"]["valid"] is True
    assert decision["recomputed_verification_state"] == COULD_NOT_VERIFY
    reasons = {
        item["reason"]
        for item in decision["recomputed_result"]["unverifiable_scope"]
    }
    assert "required_page_not_observed" in reasons
