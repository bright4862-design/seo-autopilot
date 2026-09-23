import copy

from app.coverage_probes import COVERAGE_PROBE_SCHEDULER_VERSION
from app.repair_coverage import PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION
from app.targeted_fix_verification import (
    TARGETED_FIX_VERIFICATION_OBSERVATION_VERSION,
    TARGETED_FIX_VERIFICATION_PURPOSE,
)
from app.targeted_fix_verification_rule_receipt_binding import (
    TARGETED_FIX_VERIFICATION_RULE_RECEIPT_BINDING_VERSION,
    build_execution_bound_rule_evaluation_receipt,
    evaluate_rule_receipt_bound_targeted_fix_verification_service,
)
from app.targeted_fix_verification_service_adapter import prepare_targeted_fix_verification_service

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
        observations=[scheduler_observation(url, state=state, reason=reason) for url in urls],
    )


def context(sealed=None):
    sealed = sealed or repair()
    pre = summary()
    prepared = prepare(sealed, pre)
    post = completed_post(prepared)
    outcomes = [observed(prepared, row["evidence_key"]) for row in prepared["plan"]["requests"]]
    return sealed, pre, prepared, post, outcomes


def bound_receipt(prepared, sealed, pre, post, outcomes, current_fixes, current_contract=None):
    return build_execution_bound_rule_evaluation_receipt(
        prepared,
        sealed,
        preflight_scheduler_summary=pre,
        postflight_scheduler_summary=post,
        current_scan_origin=ORIGIN,
        current_contract=current_contract or contract(),
        recheck_outcomes=outcomes,
        current_fixes=current_fixes,
    )


def evaluate(prepared, sealed, pre, post, outcomes, current_fixes, *, receipt=None, current_contract=None):
    current_contract = current_contract or contract()
    if receipt is None:
        receipt = bound_receipt(
            prepared, sealed, pre, post, outcomes, current_fixes, current_contract
        )
    return evaluate_rule_receipt_bound_targeted_fix_verification_service(
        prepared,
        sealed,
        preflight_scheduler_summary=pre,
        postflight_scheduler_summary=post,
        current_scan_origin=ORIGIN,
        current_contract=current_contract,
        recheck_outcomes=outcomes,
        current_fixes=current_fixes,
        execution_bound_rule_receipt=receipt,
    )


def test_exact_execution_bound_rule_receipt_preserves_pass():
    sealed, pre, prepared, post, outcomes = context()
    result = evaluate(prepared, sealed, pre, post, outcomes, [])
    assert result["state"] == "PASS"
    assert result["rule_receipt_binding"]["state"] == "valid"
    assert result["rule_receipt_binding_version"] == TARGETED_FIX_VERIFICATION_RULE_RECEIPT_BINDING_VERSION
    assert result["side_effects_performed"] is False


def test_execution_bound_rule_receipt_preserves_partial_and_fail():
    sealed, pre, prepared, post, outcomes = context()
    partial = evaluate(prepared, sealed, pre, post, outcomes, [repair(["/a"])])
    failed = evaluate(prepared, sealed, pre, post, outcomes, [repair(["/a", "/b"])])
    assert partial["state"] == "PARTIAL"
    assert failed["state"] == "FAIL"


def test_verified_fixed_reappearance_reopens_without_mutating_history():
    sealed, pre, prepared, post, outcomes = context(repair(verification_state="verified_fixed"))
    snapshot = copy.deepcopy(sealed)
    result = evaluate(prepared, sealed, pre, post, outcomes, [repair(["/a", "/b"])])
    assert result["state"] == "FAIL"
    assert result["reopen_regression"] is True
    assert sealed == snapshot


def test_missing_bound_receipt_is_never_accepted():
    sealed, pre, prepared, post, outcomes = context()
    result = evaluate_rule_receipt_bound_targeted_fix_verification_service(
        prepared,
        sealed,
        preflight_scheduler_summary=pre,
        postflight_scheduler_summary=post,
        current_scan_origin=ORIGIN,
        current_contract=contract(),
        recheck_outcomes=outcomes,
        current_fixes=[],
        execution_bound_rule_receipt=None,
    )
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "execution_bound_rule_receipt_missing_or_invalid"


def test_receipt_fingerprint_tamper_fails_closed():
    sealed, pre, prepared, post, outcomes = context()
    receipt = bound_receipt(prepared, sealed, pre, post, outcomes, [])
    receipt["receipt_fingerprint"] = "0" * 64
    result = evaluate(prepared, sealed, pre, post, outcomes, [], receipt=receipt)
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "execution_bound_rule_receipt_mismatch"


def test_current_fix_population_changed_after_receipt_fails_closed():
    sealed, pre, prepared, post, outcomes = context()
    receipt = bound_receipt(prepared, sealed, pre, post, outcomes, [])
    result = evaluate(prepared, sealed, pre, post, outcomes, [repair(["/a"])], receipt=receipt)
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "execution_bound_rule_receipt_mismatch"


def test_rule_contract_changed_after_receipt_fails_closed():
    sealed, pre, prepared, post, outcomes = context()
    receipt = bound_receipt(prepared, sealed, pre, post, outcomes, [])
    result = evaluate(
        prepared,
        sealed,
        pre,
        post,
        outcomes,
        [],
        receipt=receipt,
        current_contract=contract(rule_definition_version="missing_h1_v4"),
    )
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "execution_bound_rule_receipt_mismatch"


def test_scheduler_receipt_swap_cannot_reuse_rule_receipt():
    sealed, pre, prepared, post, outcomes = context(repair(["/a"]))
    receipt = bound_receipt(prepared, sealed, pre, post, outcomes, [])
    post2 = copy.deepcopy(post)
    post2["observations"][0]["evidence_ref"] = "other-receipt"
    outcomes2 = copy.deepcopy(outcomes)
    outcomes2[0]["scheduler_evidence_ref"] = "other-receipt"
    result = evaluate(prepared, sealed, pre, post2, outcomes2, [], receipt=receipt)
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "execution_bound_rule_receipt_mismatch"


def test_missing_execution_outcome_cannot_produce_ready_rule_receipt():
    sealed, pre, prepared, post, outcomes = context()
    receipt = bound_receipt(prepared, sealed, pre, post, outcomes[:1], [])
    assert receipt["state"] == "could_not_verify"
    assert receipt["reason"] == "recheck_outcome_population_mismatch"


def test_foreign_host_execution_expansion_cannot_produce_ready_rule_receipt():
    sealed, pre, prepared, post, outcomes = context()
    post2 = copy.deepcopy(post)
    post2["observations"][1] = scheduler_observation("https://evil.example/b")
    receipt = bound_receipt(prepared, sealed, pre, post2, outcomes, [])
    assert receipt["state"] == "could_not_verify"
    assert receipt["reason"] == "targeted_scheduler_observation_outside_plan"


def test_same_origin_outside_sealed_set_cannot_produce_ready_rule_receipt():
    sealed, pre, prepared, post, outcomes = context()
    post2 = copy.deepcopy(post)
    post2["observations"][1] = scheduler_observation("https://example.com/c")
    receipt = bound_receipt(prepared, sealed, pre, post2, outcomes, [])
    assert receipt["state"] == "could_not_verify"
    assert receipt["reason"] == "targeted_scheduler_observation_outside_plan"


def test_disappeared_url_remains_could_not_verify_even_with_empty_current_fixes():
    sealed, pre, prepared, _, _ = context(repair(["/a"]))
    key = prepared["plan"]["requests"][0]["evidence_key"]
    post = completed_post(prepared, state="not_verified", reason="not_observed")
    outcomes = [not_verified(prepared, key, "not_observed")]
    receipt = bound_receipt(prepared, sealed, pre, post, outcomes, [])
    assert receipt["state"] == "ready"
    result = evaluate(prepared, sealed, pre, post, outcomes, [], receipt=receipt)
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "not_observed"


def test_robots_denial_remains_could_not_verify_after_rule_receipt_binding():
    sealed, pre, prepared, post, outcomes = context(repair(["/a"]))
    outcomes[0]["page"]["robots_txt_fetch_allowed"] = False
    receipt = bound_receipt(prepared, sealed, pre, post, outcomes, [])
    result = evaluate(prepared, sealed, pre, post, outcomes, [], receipt=receipt)
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "robots_denied"


def test_challenge_remains_could_not_verify_after_rule_receipt_binding():
    sealed, pre, prepared, post, outcomes = context(repair(["/a"]))
    outcomes[0]["page"]["access_block_kind"] = "challenge"
    receipt = bound_receipt(prepared, sealed, pre, post, outcomes, [])
    result = evaluate(prepared, sealed, pre, post, outcomes, [], receipt=receipt)
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "challenge"


def test_timeout_remains_could_not_verify_after_rule_receipt_binding():
    sealed, pre, prepared, _, _ = context(repair(["/a"]))
    key = prepared["plan"]["requests"][0]["evidence_key"]
    post = completed_post(prepared, state="not_verified", reason="timeout")
    outcomes = [not_verified(prepared, key, "timeout")]
    receipt = bound_receipt(prepared, sealed, pre, post, outcomes, [])
    result = evaluate(prepared, sealed, pre, post, outcomes, [], receipt=receipt)
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "timeout"


def test_non_serializable_rule_inputs_fail_closed_without_coercion():
    sealed, pre, prepared, post, outcomes = context(repair(["/a"]))
    bad_contract = contract(extra={1, 2, 3})
    receipt = bound_receipt(
        prepared,
        sealed,
        pre,
        post,
        outcomes,
        [],
        current_contract=bad_contract,
    )
    assert receipt["state"] == "could_not_verify"
    assert receipt["reason"] == "execution_bound_rule_receipt_material_invalid"
