import copy

from app.coverage_probes import COVERAGE_PROBE_SCHEDULER_VERSION
from app.repair_coverage import PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION
from app.targeted_fix_verification import (
    TARGETED_FIX_VERIFICATION_OBSERVATION_VERSION,
    TARGETED_FIX_VERIFICATION_PURPOSE,
)
from app.targeted_fix_verification_rule_execution_binding import (
    ORIGINATING_RULE_PRODUCER_CONTRACT,
    TARGETED_FIX_VERIFICATION_RULE_EXECUTION_BINDING_VERSION,
    TARGETED_FIX_VERIFICATION_RULE_EXECUTION_RESULT_VERSION,
    build_originating_rule_execution_result,
    build_rule_execution_bound_rule_evaluation_receipt,
    evaluate_rule_execution_bound_targeted_fix_verification_service,
)
from app.targeted_fix_verification_service_adapter import (
    prepare_targeted_fix_verification_service,
)

ORIGIN = "https://example.com"
RULE_VERSION = "missing_h1_v3"
PROFILE_VERSION = "standard150_review_v8"
STAT_KEYS = (
    "eligible",
    "selected",
    "attempted",
    "completed",
    "passed",
    "failed",
    "not_verified",
    "skipped",
    "exhausted",
)


def repair(urls=None, **overrides):
    value = {
        "rule": "missing_h1",
        "category": "thin_content",
        "repair_surface": "product_template",
        "remediation_family": "add_single_h1",
        "affected_pages": urls or ["/a", "/b"],
        "rule_definition_version": RULE_VERSION,
        "comparison_profile_version": PROFILE_VERSION,
        "evidence_url_identity_version": PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION,
    }
    value.update(overrides)
    return value


def contract(**overrides):
    value = {
        "rule_definition_version": RULE_VERSION,
        "comparison_profile_version": PROFILE_VERSION,
        "evidence_url_identity_version": PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION,
    }
    value.update(overrides)
    return value


def stats(**overrides):
    value = {key: 0 for key in STAT_KEYS}
    value.update(overrides)
    return value


def summary(*, consumed=0, remaining=None, observations=None, target_stats=None):
    configured = 18
    shared_limit = 100
    crawl_consumed = 80
    if remaining is None:
        remaining = min(
            max(0, configured - consumed),
            max(0, shared_limit - crawl_consumed - consumed),
        )
    purposes = {}
    if target_stats is not None:
        purposes[TARGETED_FIX_VERIFICATION_PURPOSE] = target_stats
    return {
        "version": COVERAGE_PROBE_SCHEDULER_VERSION,
        "request_budget": {
            "configured_probe_requests": configured,
            "shared_request_limit": shared_limit,
            "crawl_requests_consumed": crawl_consumed,
            "requests_consumed": consumed,
            "requests_reused": 0,
            "requests_remaining": remaining,
            "budget_exhausted": False,
            "deadline_exhausted": False,
            "time_budget_seconds": 30.0,
        },
        "purposes": purposes,
        "observations": observations or [],
        "observation_samples_truncated": False,
    }


def scheduler_observation(url, *, state="pass", reason="verified", evidence_ref=None):
    return {
        "purpose": TARGETED_FIX_VERIFICATION_PURPOSE,
        "version": COVERAGE_PROBE_SCHEDULER_VERSION,
        "state": state,
        "reason": reason,
        "observed_url": url,
        "status_code": 200 if state != "not_verified" else 0,
        "final_url": url if state != "not_verified" else "",
        "source_pages": [],
        "link_text_samples": [],
        "metadata": {},
        "evidence_ref": evidence_ref
        or f"{COVERAGE_PROBE_SCHEDULER_VERSION}:receipt:{url.rsplit('/', 1)[-1]}",
    }


def prepare(sealed, pre):
    return prepare_targeted_fix_verification_service(
        sealed,
        source_scan_id="scan-old",
        source_scan_origin=ORIGIN,
        scheduler_summary=pre,
    )


def observed(prepared, key, *, scheduler_ref=None, **page_overrides):
    page = {
        "url": key,
        "final_url": key,
        "status_code": 200,
        "content_type": "text/html; charset=utf-8",
        "page_evidence_class": "usable_html",
        "raw_html_truncated": False,
        "robots_txt_fetch_allowed": True,
        "access_block_kind": "",
        "fetch_error": "",
    }
    page.update(page_overrides)
    return {
        "version": TARGETED_FIX_VERIFICATION_OBSERVATION_VERSION,
        "plan_fingerprint": prepared["plan"]["plan_fingerprint"],
        "evidence_key": key,
        "scheduler_evidence_ref": scheduler_ref
        or f"{COVERAGE_PROBE_SCHEDULER_VERSION}:receipt:{key.rsplit('/', 1)[-1]}",
        "state": "observed",
        "page": page,
    }


def not_verified(prepared, key, reason):
    return {
        "version": TARGETED_FIX_VERIFICATION_OBSERVATION_VERSION,
        "plan_fingerprint": prepared["plan"]["plan_fingerprint"],
        "evidence_key": key,
        "scheduler_evidence_ref": f"{COVERAGE_PROBE_SCHEDULER_VERSION}:receipt:{key.rsplit('/', 1)[-1]}",
        "state": "not_verified",
        "reason": reason,
    }


def completed_post(prepared, *, state="pass", reason="verified"):
    urls = [row["url"] for row in prepared["plan"]["requests"]]
    return summary(
        consumed=len(urls),
        target_stats=stats(
            eligible=len(urls),
            selected=len(urls),
            attempted=len(urls),
            completed=len(urls),
            passed=len(urls) if state == "pass" else 0,
            failed=len(urls) if state == "fail" else 0,
            not_verified=len(urls) if state == "not_verified" else 0,
        ),
        observations=[
            scheduler_observation(url, state=state, reason=reason) for url in urls
        ],
    )


def context(sealed=None):
    sealed = sealed or repair()
    pre = summary()
    prepared = prepare(sealed, pre)
    post = completed_post(prepared)
    outcomes = [
        observed(prepared, row["evidence_key"])
        for row in prepared["plan"]["requests"]
    ]
    return sealed, pre, prepared, post, outcomes


def _absolute(value):
    if value.startswith(("https://", "http://")):
        return value
    return ORIGIN + (value if value.startswith("/") else "/" + value)


def current_target_keys(current_fixes):
    keys = set()
    for fix in current_fixes:
        if not isinstance(fix, dict):
            continue
        for value in fix.get("affected_pages") or []:
            if isinstance(value, str):
                keys.add(_absolute(value))
    return keys


def rule_results(prepared, outcomes, current_fixes):
    present = current_target_keys(current_fixes)
    results = []
    for outcome in outcomes:
        finding_state = (
            "finding_present"
            if outcome.get("evidence_key") in present
            else "finding_absent"
        )
        results.append(
            build_originating_rule_execution_result(
                prepared["plan"],
                outcome,
                finding_state=finding_state,
            )
        )
    return results


def bound_receipt(
    prepared,
    sealed,
    pre,
    post,
    outcomes,
    current_fixes,
    results,
    current_contract=None,
):
    return build_rule_execution_bound_rule_evaluation_receipt(
        prepared,
        sealed,
        preflight_scheduler_summary=pre,
        postflight_scheduler_summary=post,
        current_scan_origin=ORIGIN,
        current_contract=current_contract or contract(),
        recheck_outcomes=outcomes,
        current_fixes=current_fixes,
        rule_execution_results=results,
    )


def evaluate(
    prepared,
    sealed,
    pre,
    post,
    outcomes,
    current_fixes,
    *,
    results=None,
    receipt=None,
    current_contract=None,
):
    current_contract = current_contract or contract()
    if results is None:
        results = rule_results(prepared, outcomes, current_fixes)
    if receipt is None:
        receipt = bound_receipt(
            prepared,
            sealed,
            pre,
            post,
            outcomes,
            current_fixes,
            results,
            current_contract,
        )
    return evaluate_rule_execution_bound_targeted_fix_verification_service(
        prepared,
        sealed,
        preflight_scheduler_summary=pre,
        postflight_scheduler_summary=post,
        current_scan_origin=ORIGIN,
        current_contract=current_contract,
        recheck_outcomes=outcomes,
        current_fixes=current_fixes,
        rule_execution_results=results,
        rule_execution_bound_receipt=receipt,
    )


def test_exact_originating_rule_execution_binding_preserves_pass():
    sealed, pre, prepared, post, outcomes = context()
    result = evaluate(prepared, sealed, pre, post, outcomes, [])
    assert result["state"] == "PASS"
    assert result["rule_execution_binding"]["state"] == "valid"
    assert (
        result["rule_execution_binding_version"]
        == TARGETED_FIX_VERIFICATION_RULE_EXECUTION_BINDING_VERSION
    )
    assert result["model_calls_performed"] is False
    assert result["side_effects_performed"] is False


def test_originating_rule_execution_binding_preserves_partial_and_fail():
    sealed, pre, prepared, post, outcomes = context()
    partial = evaluate(
        prepared,
        sealed,
        pre,
        post,
        outcomes,
        [repair(["/a"])],
    )
    failed = evaluate(
        prepared,
        sealed,
        pre,
        post,
        outcomes,
        [repair(["/a", "/b"])],
    )
    assert partial["state"] == "PARTIAL"
    assert failed["state"] == "FAIL"


def test_verified_fixed_reappearance_reopens_without_mutating_history():
    sealed, pre, prepared, post, outcomes = context(
        repair(verification_state="verified_fixed")
    )
    snapshot = copy.deepcopy(sealed)
    result = evaluate(
        prepared,
        sealed,
        pre,
        post,
        outcomes,
        [repair(["/a", "/b"])],
    )
    assert result["state"] == "FAIL"
    assert result["reopen_regression"] is True
    assert sealed == snapshot


def test_missing_rule_execution_receipt_is_never_accepted():
    sealed, pre, prepared, post, outcomes = context()
    results = rule_results(prepared, outcomes, [])
    result = evaluate_rule_execution_bound_targeted_fix_verification_service(
        prepared,
        sealed,
        preflight_scheduler_summary=pre,
        postflight_scheduler_summary=post,
        current_scan_origin=ORIGIN,
        current_contract=contract(),
        recheck_outcomes=outcomes,
        current_fixes=[],
        rule_execution_results=results,
        rule_execution_bound_receipt=None,
    )
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "rule_execution_bound_receipt_missing_or_invalid"


def test_missing_one_rule_execution_result_fails_closed():
    sealed, pre, prepared, post, outcomes = context()
    results = rule_results(prepared, outcomes, [])
    receipt = bound_receipt(
        prepared, sealed, pre, post, outcomes, [], results[:1]
    )
    assert receipt["state"] == "could_not_verify"
    assert receipt["reason"] == "rule_execution_result_population_mismatch"


def test_duplicate_rule_execution_result_fails_closed():
    sealed, pre, prepared, post, outcomes = context()
    results = rule_results(prepared, outcomes, [])
    results[1] = copy.deepcopy(results[0])
    receipt = bound_receipt(
        prepared, sealed, pre, post, outcomes, [], results
    )
    assert receipt["state"] == "could_not_verify"
    assert receipt["reason"] == "duplicate_rule_execution_result"


def test_same_origin_outside_plan_rule_result_is_rejected():
    sealed, pre, prepared, post, outcomes = context()
    results = rule_results(prepared, outcomes, [])
    results[1]["evidence_key"] = f"{ORIGIN}/c"
    receipt = bound_receipt(
        prepared, sealed, pre, post, outcomes, [], results
    )
    assert receipt["state"] == "could_not_verify"
    assert receipt["reason"] == "rule_execution_result_outside_planned_scope"


def test_foreign_host_rule_result_is_rejected():
    sealed, pre, prepared, post, outcomes = context()
    results = rule_results(prepared, outcomes, [])
    results[1]["evidence_key"] = "https://evil.example/b"
    receipt = bound_receipt(
        prepared, sealed, pre, post, outcomes, [], results
    )
    assert receipt["state"] == "could_not_verify"
    assert receipt["reason"] == "rule_execution_result_outside_planned_scope"


def test_rule_version_drift_in_rule_execution_result_fails_closed():
    sealed, pre, prepared, post, outcomes = context()
    results = rule_results(prepared, outcomes, [])
    results[0]["rule_definition_version"] = "missing_h1_v4"
    receipt = bound_receipt(
        prepared, sealed, pre, post, outcomes, [], results
    )
    assert receipt["state"] == "could_not_verify"
    assert (
        receipt["reason"]
        == "rule_execution_result_rule_definition_version_mismatch"
    )


def test_plan_fingerprint_drift_in_rule_execution_result_fails_closed():
    sealed, pre, prepared, post, outcomes = context()
    results = rule_results(prepared, outcomes, [])
    results[0]["plan_fingerprint"] = "0" * 64
    receipt = bound_receipt(
        prepared, sealed, pre, post, outcomes, [], results
    )
    assert receipt["state"] == "could_not_verify"
    assert receipt["reason"] == "rule_execution_result_plan_fingerprint_mismatch"


def test_scheduler_receipt_mismatch_in_rule_execution_result_fails_closed():
    sealed, pre, prepared, post, outcomes = context()
    results = rule_results(prepared, outcomes, [])
    results[0]["scheduler_evidence_ref"] = "stale-receipt"
    receipt = bound_receipt(
        prepared, sealed, pre, post, outcomes, [], results
    )
    assert receipt["state"] == "could_not_verify"
    assert receipt["reason"] == "rule_execution_scheduler_evidence_ref_mismatch"


def test_page_evidence_fingerprint_mismatch_fails_closed():
    sealed, pre, prepared, post, outcomes = context()
    results = rule_results(prepared, outcomes, [])
    results[0]["page_evidence_fingerprint"] = "0" * 64
    receipt = bound_receipt(
        prepared, sealed, pre, post, outcomes, [], results
    )
    assert receipt["state"] == "could_not_verify"
    assert (
        receipt["reason"]
        == "rule_execution_page_evidence_fingerprint_mismatch"
    )


def test_rule_result_cannot_claim_absent_when_target_fix_is_present():
    sealed, pre, prepared, post, outcomes = context()
    current_fixes = [repair(["/a"])]
    results = rule_results(prepared, outcomes, current_fixes)
    results[0]["finding_state"] = "finding_absent"
    receipt = bound_receipt(
        prepared,
        sealed,
        pre,
        post,
        outcomes,
        current_fixes,
        results,
    )
    assert receipt["state"] == "could_not_verify"
    assert receipt["reason"] == "rule_execution_fix_population_mismatch"


def test_rule_result_cannot_claim_present_when_target_fix_is_absent():
    sealed, pre, prepared, post, outcomes = context()
    results = rule_results(prepared, outcomes, [])
    results[0]["finding_state"] = "finding_present"
    receipt = bound_receipt(
        prepared, sealed, pre, post, outcomes, [], results
    )
    assert receipt["state"] == "could_not_verify"
    assert receipt["reason"] == "rule_execution_fix_population_mismatch"


def test_finding_state_type_coercion_is_rejected():
    sealed, pre, prepared, post, outcomes = context()
    results = rule_results(prepared, outcomes, [])
    results[0]["finding_state"] = 0
    receipt = bound_receipt(
        prepared, sealed, pre, post, outcomes, [], results
    )
    assert receipt["state"] == "could_not_verify"
    assert receipt["reason"] == "rule_execution_finding_state_invalid"


def test_extra_rule_execution_fields_cannot_smuggle_unbound_claims():
    sealed, pre, prepared, post, outcomes = context()
    results = rule_results(prepared, outcomes, [])
    results[0]["client_claim"] = "trust-me"
    receipt = bound_receipt(
        prepared, sealed, pre, post, outcomes, [], results
    )
    assert receipt["state"] == "could_not_verify"
    assert receipt["reason"] == "rule_execution_result_fields_invalid"


def test_model_calls_are_explicitly_forbidden_by_rule_execution_contract():
    sealed, pre, prepared, post, outcomes = context()
    results = rule_results(prepared, outcomes, [])
    results[0]["model_calls_performed"] = True
    receipt = bound_receipt(
        prepared, sealed, pre, post, outcomes, [], results
    )
    assert receipt["state"] == "could_not_verify"
    assert receipt["reason"] == "rule_execution_model_calls_not_allowed"


def test_disappeared_url_cannot_claim_rule_execution_or_pass():
    sealed, pre, prepared, _, _ = context(repair(["/a"]))
    key = prepared["plan"]["requests"][0]["evidence_key"]
    post = completed_post(prepared, state="not_verified", reason="not_observed")
    outcomes = [not_verified(prepared, key, "not_observed")]
    results = [
        build_originating_rule_execution_result(
            prepared["plan"],
            outcomes[0],
            finding_state="finding_absent",
        )
    ]
    assert results[0]["state"] == "could_not_verify"
    assert results[0]["reason"] == "rule_execution_requires_observed_evidence"
    receipt = bound_receipt(
        prepared, sealed, pre, post, outcomes, [], results
    )
    assert receipt["state"] == "could_not_verify"
    assert receipt["reason"] == "rule_execution_requires_observed_evidence"
    result = evaluate(
        prepared,
        sealed,
        pre,
        post,
        outcomes,
        [],
        results=results,
        receipt=receipt,
    )
    assert result["state"] == "COULD_NOT_VERIFY"


def test_timeout_cannot_claim_rule_execution_or_pass():
    sealed, pre, prepared, _, _ = context(repair(["/a"]))
    key = prepared["plan"]["requests"][0]["evidence_key"]
    post = completed_post(prepared, state="not_verified", reason="timeout")
    outcomes = [not_verified(prepared, key, "timeout")]
    results = [
        build_originating_rule_execution_result(
            prepared["plan"],
            outcomes[0],
            finding_state="finding_absent",
        )
    ]
    receipt = bound_receipt(
        prepared, sealed, pre, post, outcomes, [], results
    )
    assert receipt["state"] == "could_not_verify"
    assert receipt["reason"] == "rule_execution_requires_observed_evidence"


def test_robots_denial_still_fails_closed_after_rule_execution_binding():
    sealed, pre, prepared, post, outcomes = context(repair(["/a"]))
    outcomes[0]["page"]["robots_txt_fetch_allowed"] = False
    results = rule_results(prepared, outcomes, [])
    result = evaluate(
        prepared,
        sealed,
        pre,
        post,
        outcomes,
        [],
        results=results,
    )
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "robots_denied"


def test_challenge_still_fails_closed_after_rule_execution_binding():
    sealed, pre, prepared, post, outcomes = context(repair(["/a"]))
    outcomes[0]["page"]["access_block_kind"] = "challenge"
    results = rule_results(prepared, outcomes, [])
    result = evaluate(
        prepared,
        sealed,
        pre,
        post,
        outcomes,
        [],
        results=results,
    )
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "challenge"


def test_current_fix_identity_conflict_fails_before_rule_truth_can_be_used():
    sealed, pre, prepared, post, outcomes = context(repair(["/a"]))
    current_fixes = [
        repair(
            ["/a"],
            repair_surface="different_surface",
            repair_fingerprint=prepared["plan"]["repair_fingerprint"],
        )
    ]
    results = rule_results(prepared, outcomes, [])
    receipt = bound_receipt(
        prepared,
        sealed,
        pre,
        post,
        outcomes,
        current_fixes,
        results,
    )
    assert receipt["state"] == "could_not_verify"
    assert receipt["reason"] == "current_fix_identity_conflict"


def test_provisional_current_same_persisted_fingerprint_cannot_use_rule_truth():
    sealed, pre, prepared, post, outcomes = context(repair(["/a"]))
    current_fixes = [
        {
            "rule": "missing_h1",
            "affected_pages": ["/a"],
            "repair_fingerprint": prepared["plan"]["repair_fingerprint"],
        }
    ]
    results = rule_results(prepared, outcomes, current_fixes)
    receipt = bound_receipt(
        prepared,
        sealed,
        pre,
        post,
        outcomes,
        current_fixes,
        results,
    )

    assert receipt["state"] == "could_not_verify"
    assert receipt["reason"] == "current_fix_identity_conflict"


def test_matching_current_fix_cannot_expand_beyond_sealed_scope():
    sealed, pre, prepared, post, outcomes = context()
    current_fixes = [repair(["/a", "/b", "/c"])]
    results = rule_results(prepared, outcomes, current_fixes)
    receipt = bound_receipt(
        prepared,
        sealed,
        pre,
        post,
        outcomes,
        current_fixes,
        results,
    )
    assert receipt["state"] == "could_not_verify"
    assert receipt["reason"] == "matching_current_fix_expands_sealed_repair_scope"


def test_non_serializable_page_evidence_fails_closed():
    sealed, pre, prepared, post, outcomes = context(repair(["/a"]))
    outcomes[0]["page"]["opaque"] = {1, 2, 3}
    results = [
        {
            "version": TARGETED_FIX_VERIFICATION_RULE_EXECUTION_RESULT_VERSION,
            "state": "evaluated",
            "producer_contract": ORIGINATING_RULE_PRODUCER_CONTRACT,
            "model_calls_performed": False,
            "plan_fingerprint": prepared["plan"]["plan_fingerprint"],
            "repair_fingerprint": prepared["plan"]["repair_fingerprint"],
            "rule_definition_version": prepared["plan"]["rule_definition_version"],
            "comparison_profile_version": prepared["plan"]["comparison_profile_version"],
            "evidence_url_identity_version": prepared["plan"][
                "evidence_url_identity_version"
            ],
            "evidence_key": outcomes[0]["evidence_key"],
            "scheduler_evidence_ref": outcomes[0]["scheduler_evidence_ref"],
            "page_evidence_fingerprint": "",
            "finding_state": "finding_absent",
        }
    ]
    receipt = bound_receipt(
        prepared, sealed, pre, post, outcomes, [], results
    )
    assert receipt["state"] == "could_not_verify"
    assert receipt["reason"] == "execution_bound_rule_receipt_material_invalid"
