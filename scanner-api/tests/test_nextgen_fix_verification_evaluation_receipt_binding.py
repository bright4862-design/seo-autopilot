from copy import deepcopy

from app.nextgen_fix_verification import COULD_NOT_VERIFY, FAIL, PARTIAL, PASS
from app.nextgen_fix_verification_evaluation_receipt_binding import (
    EVALUATION_RECEIPT_BINDING_VERSION,
    PAGE_OBSERVATION_RECEIPT_VERSION,
    STRICT_REGRESSION_REOPEN_EVALUATION_RECEIPT_BOUND_VERSION,
    STRICT_VERIFIED_FIXED_EVALUATION_RECEIPT_BOUND_VERSION,
    page_observation_receipt_fingerprint,
    strict_regression_reopen_from_evaluation_receipt_bound_inputs,
    strict_verified_fixed_transition_from_evaluation_receipt_bound_inputs,
    verification_evaluation_receipt_binding_integrity,
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


def bind_receipts(observed_pages, rows):
    by_key = {page["evidence_key"]: page for page in observed_pages}
    bound = deepcopy(rows)
    for row in bound:
        page = by_key.get(row["evidence_key"])
        if page is None:
            continue
        fingerprint, reason = page_observation_receipt_fingerprint(page)
        assert not reason
        row["page_observation_receipt_version"] = PAGE_OBSERVATION_RECEIPT_VERSION
        row["page_observation_receipt_fingerprint"] = fingerprint
    return bound


def test_page_observation_receipt_fingerprint_is_deterministic_for_exact_transport():
    plan = bound_plan()
    page = pages(plan, "/a")[0]
    reordered = {key: page[key] for key in reversed(list(page.keys()))}
    first, first_reason = page_observation_receipt_fingerprint(page)
    second, second_reason = page_observation_receipt_fingerprint(reordered)
    assert first_reason == second_reason == ""
    assert first == second
    assert len(first) == 64


def test_page_observation_receipt_fingerprint_changes_when_comparability_evidence_changes():
    plan = bound_plan()
    page = pages(plan, "/a")[0]
    original, reason = page_observation_receipt_fingerprint(page)
    assert reason == ""
    changed = deepcopy(page)
    changed["status_code"] = 204
    mutated, reason = page_observation_receipt_fingerprint(changed)
    assert reason == ""
    assert mutated != original


def test_evaluation_receipt_binding_accepts_exact_page_receipts():
    plan = bound_plan()
    observed = pages(plan, "/a", "/b")
    rows = bind_receipts(observed, evaluations(plan, [False, False]))
    binding = verification_evaluation_receipt_binding_integrity(
        plan,
        observed,
        rows,
        contract(),
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_origin=ORIGIN,
    )
    assert binding["version"] == EVALUATION_RECEIPT_BINDING_VERSION
    assert binding["valid"] is True
    assert binding["bound_evidence_keys"] == [
        plan["requests"][0]["evidence_key"],
        plan["requests"][1]["evidence_key"],
    ]


def test_evaluation_receipt_binding_rejects_missing_fingerprint_for_present_page():
    plan = bound_plan()
    observed = pages(plan, "/a", "/b")
    rows = bind_receipts(observed, evaluations(plan, [False, False]))
    rows[0].pop("page_observation_receipt_fingerprint")
    binding = verification_evaluation_receipt_binding_integrity(
        plan,
        observed,
        rows,
        contract(),
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_origin=ORIGIN,
    )
    assert binding["valid"] is False
    assert binding["reason"].endswith("page_observation_receipt_fingerprint_must_be_exact_sha256")


def test_evaluation_receipt_binding_rejects_wrong_receipt_version():
    plan = bound_plan()
    observed = pages(plan, "/a", "/b")
    rows = bind_receipts(observed, evaluations(plan, [False, False]))
    rows[0]["page_observation_receipt_version"] = "future_receipt_v9"
    binding = verification_evaluation_receipt_binding_integrity(
        plan,
        observed,
        rows,
        contract(),
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_origin=ORIGIN,
    )
    assert binding["valid"] is False
    assert binding["reason"].endswith("page_observation_receipt_version_mismatch")


def test_evaluation_receipt_binding_rejects_swapped_same_plan_receipts():
    plan = bound_plan()
    observed = pages(plan, "/a", "/b")
    rows = bind_receipts(observed, evaluations(plan, [False, False]))
    rows[0]["page_observation_receipt_fingerprint"], rows[1]["page_observation_receipt_fingerprint"] = (
        rows[1]["page_observation_receipt_fingerprint"],
        rows[0]["page_observation_receipt_fingerprint"],
    )
    binding = verification_evaluation_receipt_binding_integrity(
        plan,
        observed,
        rows,
        contract(),
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_origin=ORIGIN,
    )
    assert binding["valid"] is False
    assert binding["reason"].endswith("page_observation_receipt_fingerprint_mismatch")


def test_evaluation_receipt_binding_rejects_stale_receipt_after_page_mutation():
    plan = bound_plan()
    observed = pages(plan, "/a", "/b")
    rows = bind_receipts(observed, evaluations(plan, [False, False]))
    observed[0]["content_type"] = "application/xhtml+xml"
    binding = verification_evaluation_receipt_binding_integrity(
        plan,
        observed,
        rows,
        contract(),
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_origin=ORIGIN,
    )
    assert binding["valid"] is False
    assert binding["reason"].endswith("page_observation_receipt_fingerprint_mismatch")


def test_evaluation_receipt_binding_rejects_malformed_receipt_hash_transport():
    plan = bound_plan()
    observed = pages(plan, "/a", "/b")
    rows = bind_receipts(observed, evaluations(plan, [False, False]))
    rows[0]["page_observation_receipt_fingerprint"] = rows[0]["page_observation_receipt_fingerprint"].upper()
    binding = verification_evaluation_receipt_binding_integrity(
        plan,
        observed,
        rows,
        contract(),
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_origin=ORIGIN,
    )
    assert binding["valid"] is False
    assert binding["reason"].endswith("page_observation_receipt_fingerprint_must_be_exact_sha256")


def test_missing_page_allows_unclaimed_evaluation_but_records_missing_key():
    plan = bound_plan()
    observed = pages(plan, "/a")
    rows = bind_receipts(observed, evaluations(plan, [False, False]))
    binding = verification_evaluation_receipt_binding_integrity(
        plan,
        observed,
        rows,
        contract(),
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_origin=ORIGIN,
    )
    assert binding["valid"] is True
    assert binding["missing_required_evidence_keys"] == [plan["requests"][1]["evidence_key"]]


def test_missing_page_rejects_evaluation_that_claims_nonexistent_receipt():
    plan = bound_plan()
    observed = pages(plan, "/a")
    rows = bind_receipts(observed, evaluations(plan, [False, False]))
    rows[1]["page_observation_receipt_version"] = PAGE_OBSERVATION_RECEIPT_VERSION
    rows[1]["page_observation_receipt_fingerprint"] = "0" * 64
    binding = verification_evaluation_receipt_binding_integrity(
        plan,
        observed,
        rows,
        contract(),
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_origin=ORIGIN,
    )
    assert binding["valid"] is False
    assert binding["reason"].endswith("claims_missing_page_receipt")


def test_evaluation_receipt_bound_verified_fixed_wrapper_allows_exact_pass():
    previous = fix()
    plan = bound_plan(previous)
    observed = pages(plan, "/a", "/b")
    rows = bind_receipts(observed, evaluations(plan, [False, False]))
    decision = strict_verified_fixed_transition_from_evaluation_receipt_bound_inputs(
        previous,
        plan,
        observed,
        rows,
        [],
        contract(),
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_id=CURRENT_SCAN_ID,
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert decision["version"] == STRICT_VERIFIED_FIXED_EVALUATION_RECEIPT_BOUND_VERSION
    assert decision["allowed"] is True
    assert decision["recomputed_verification_state"] == PASS


def test_evaluation_receipt_bound_regression_wrapper_reopens_exact_fail():
    previous = fix(state="verified_fixed")
    plan = bound_plan(previous)
    observed = pages(plan, "/a", "/b")
    rows = bind_receipts(observed, evaluations(plan, [True, True]))
    decision = strict_regression_reopen_from_evaluation_receipt_bound_inputs(
        previous,
        plan,
        observed,
        rows,
        contract(),
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_id=CURRENT_SCAN_ID,
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert decision["version"] == STRICT_REGRESSION_REOPEN_EVALUATION_RECEIPT_BOUND_VERSION
    assert decision["should_reopen"] is True
    assert decision["recomputed_verification_state"] == FAIL


def test_evaluation_receipt_bound_regression_wrapper_preserves_partial_scope():
    previous = fix(state="verified_fixed")
    plan = bound_plan(previous)
    observed = pages(plan, "/a", "/b")
    rows = bind_receipts(observed, evaluations(plan, [False, True]))
    decision = strict_regression_reopen_from_evaluation_receipt_bound_inputs(
        previous,
        plan,
        observed,
        rows,
        contract(),
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_id=CURRENT_SCAN_ID,
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert decision["should_reopen"] is True
    assert decision["recomputed_verification_state"] == PARTIAL
    assert decision["reopen_scope"] == [plan["requests"][1]["evidence_key"]]


def test_disappeared_page_remains_could_not_verify_after_receipt_binding():
    previous = fix()
    plan = bound_plan(previous)
    observed = pages(plan, "/a")
    rows = bind_receipts(observed, evaluations(plan, [False, False]))
    decision = strict_verified_fixed_transition_from_evaluation_receipt_bound_inputs(
        previous,
        plan,
        observed,
        rows,
        [],
        contract(),
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_id=CURRENT_SCAN_ID,
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert decision["allowed"] is False
    assert decision["evaluation_receipt_binding"]["valid"] is True
    assert decision["recomputed_verification_state"] == COULD_NOT_VERIFY
    reasons = {
        item["reason"]
        for item in decision["recomputed_result"]["unverifiable_scope"]
    }
    assert "required_page_not_observed" in reasons
