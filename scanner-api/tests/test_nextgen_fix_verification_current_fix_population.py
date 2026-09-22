from copy import deepcopy

from app.nextgen_fix_verification import COULD_NOT_VERIFY, PASS
from app.nextgen_fix_verification_current_fix_population import (
    CURRENT_FIX_POPULATION_ATTESTATION_VERSION,
    CURRENT_FIX_POPULATION_BINDING_VERSION,
    STRICT_VERIFIED_FIXED_CURRENT_FIX_POPULATION_BOUND_VERSION,
    current_fix_population_fingerprint,
    strict_verified_fixed_transition_from_complete_current_fix_population,
    verification_current_fix_population_integrity,
)
from app.nextgen_fix_verification_evaluation_receipt_binding import (
    PAGE_OBSERVATION_RECEIPT_VERSION,
    page_observation_receipt_fingerprint,
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


def attestation(current_fixes, *, scan_id=CURRENT_SCAN_ID, complete=True):
    fingerprint, reason = current_fix_population_fingerprint(current_fixes, scan_id=scan_id)
    assert not reason
    return {
        "version": CURRENT_FIX_POPULATION_ATTESTATION_VERSION,
        "scan_id": scan_id,
        "population_complete": complete,
        "population_count": len(current_fixes),
        "population_fingerprint": fingerprint,
    }


def test_population_fingerprint_is_deterministic_for_exact_transport():
    current_fixes = [{"scan_run_id": CURRENT_SCAN_ID, "rule": "title_too_long", "priority": 2}]
    first, first_reason = current_fix_population_fingerprint(current_fixes, scan_id=CURRENT_SCAN_ID)
    reordered = [{"priority": 2, "rule": "title_too_long", "scan_run_id": CURRENT_SCAN_ID}]
    second, second_reason = current_fix_population_fingerprint(reordered, scan_id=CURRENT_SCAN_ID)
    assert first_reason == second_reason == ""
    assert first == second
    assert len(first) == 64


def test_population_fingerprint_changes_when_population_transport_changes():
    current_fixes = [{"scan_run_id": CURRENT_SCAN_ID, "rule": "title_too_long"}]
    original, reason = current_fix_population_fingerprint(current_fixes, scan_id=CURRENT_SCAN_ID)
    assert reason == ""
    changed = deepcopy(current_fixes)
    changed[0]["rule"] = "missing_h1"
    mutated, reason = current_fix_population_fingerprint(changed, scan_id=CURRENT_SCAN_ID)
    assert reason == ""
    assert mutated != original


def test_population_fingerprint_rejects_silent_tuple_coercion():
    fingerprint, reason = current_fix_population_fingerprint(
        [{"scan_run_id": CURRENT_SCAN_ID, "affected_pages": ("/a",)}],
        scan_id=CURRENT_SCAN_ID,
    )
    assert fingerprint == ""
    assert reason.endswith("contains_unsupported_transport_type")


def test_population_integrity_accepts_exact_complete_empty_population():
    current_fixes = []
    binding = verification_current_fix_population_integrity(
        attestation(current_fixes),
        current_fixes,
        scan_id=CURRENT_SCAN_ID,
    )
    assert binding["version"] == CURRENT_FIX_POPULATION_BINDING_VERSION
    assert binding["valid"] is True
    assert binding["population_count"] == 0


def test_population_integrity_rejects_incomplete_empty_population():
    current_fixes = []
    binding = verification_current_fix_population_integrity(
        attestation(current_fixes, complete=False),
        current_fixes,
        scan_id=CURRENT_SCAN_ID,
    )
    assert binding["valid"] is False
    assert binding["reason"] == "current_fix_population_not_declared_complete"


def test_population_integrity_rejects_count_mismatch():
    current_fixes = []
    proof = attestation(current_fixes)
    proof["population_count"] = 1
    binding = verification_current_fix_population_integrity(
        proof,
        current_fixes,
        scan_id=CURRENT_SCAN_ID,
    )
    assert binding["valid"] is False
    assert binding["reason"] == "current_fix_population_count_mismatch"


def test_population_integrity_rejects_foreign_scan_attestation():
    current_fixes = []
    proof = attestation(current_fixes, scan_id="scan-other-999")
    binding = verification_current_fix_population_integrity(
        proof,
        current_fixes,
        scan_id=CURRENT_SCAN_ID,
    )
    assert binding["valid"] is False
    assert binding["reason"] == "current_fix_population_scan_id_mismatch"


def test_population_integrity_rejects_malformed_fingerprint_transport():
    current_fixes = []
    proof = attestation(current_fixes)
    proof["population_fingerprint"] = proof["population_fingerprint"].upper()
    binding = verification_current_fix_population_integrity(
        proof,
        current_fixes,
        scan_id=CURRENT_SCAN_ID,
    )
    assert binding["valid"] is False
    assert binding["reason"] == "current_fix_population_fingerprint_must_be_exact_sha256"


def test_population_integrity_rejects_stale_attestation_after_population_mutation():
    current_fixes = []
    proof = attestation(current_fixes)
    current_fixes.append({"scan_run_id": CURRENT_SCAN_ID, "rule": "new_current_fix"})
    proof["population_count"] = 1
    binding = verification_current_fix_population_integrity(
        proof,
        current_fixes,
        scan_id=CURRENT_SCAN_ID,
    )
    assert binding["valid"] is False
    assert binding["reason"] == "current_fix_population_fingerprint_mismatch"


def test_population_integrity_rejects_unexpected_attestation_claim():
    current_fixes = []
    proof = attestation(current_fixes)
    proof["source"] = "unversioned-side-channel"
    binding = verification_current_fix_population_integrity(
        proof,
        current_fixes,
        scan_id=CURRENT_SCAN_ID,
    )
    assert binding["valid"] is False
    assert binding["reason"] == "current_fix_population_attestation_fields_mismatch"


def test_complete_population_wrapper_allows_exact_pass_with_proven_empty_current_fixes():
    previous = fix()
    plan = bound_plan(previous)
    observed = pages(plan, "/a", "/b")
    rows = bind_receipts(observed, evaluations(plan, [False, False]))
    current_fixes = []
    decision = strict_verified_fixed_transition_from_complete_current_fix_population(
        previous,
        plan,
        observed,
        rows,
        current_fixes,
        attestation(current_fixes),
        contract(),
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_id=CURRENT_SCAN_ID,
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert decision["version"] == STRICT_VERIFIED_FIXED_CURRENT_FIX_POPULATION_BOUND_VERSION
    assert decision["allowed"] is True
    assert decision["recomputed_verification_state"] == PASS
    assert decision["current_fix_population_binding"]["valid"] is True


def test_complete_population_wrapper_denies_unproven_empty_current_fixes():
    previous = fix()
    plan = bound_plan(previous)
    observed = pages(plan, "/a", "/b")
    rows = bind_receipts(observed, evaluations(plan, [False, False]))
    current_fixes = []
    decision = strict_verified_fixed_transition_from_complete_current_fix_population(
        previous,
        plan,
        observed,
        rows,
        current_fixes,
        attestation(current_fixes, complete=False),
        contract(),
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_id=CURRENT_SCAN_ID,
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert decision["allowed"] is False
    assert decision["reason"] == "current_fix_population_binding_failed"
    assert decision["recomputed_verification_state"] == COULD_NOT_VERIFY


def test_disappeared_page_remains_could_not_verify_even_with_complete_fix_population():
    previous = fix()
    plan = bound_plan(previous)
    observed = pages(plan, "/a")
    rows = bind_receipts(observed, evaluations(plan, [False, False]))
    current_fixes = []
    decision = strict_verified_fixed_transition_from_complete_current_fix_population(
        previous,
        plan,
        observed,
        rows,
        current_fixes,
        attestation(current_fixes),
        contract(),
        previous_scan_id=PREVIOUS_SCAN_ID,
        scan_id=CURRENT_SCAN_ID,
        previous_scan_origin=ORIGIN,
        scan_origin=ORIGIN,
    )
    assert decision["allowed"] is False
    assert decision["current_fix_population_binding"]["valid"] is True
    assert decision["recomputed_verification_state"] == COULD_NOT_VERIFY
    reasons = {
        item["reason"]
        for item in decision["recomputed_result"]["unverifiable_scope"]
    }
    assert "required_page_not_observed" in reasons
