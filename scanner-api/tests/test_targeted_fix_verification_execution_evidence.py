import copy

from app.coverage_probes import COVERAGE_PROBE_SCHEDULER_VERSION
from app.repair_coverage import PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION
from app.targeted_fix_verification import (
    TARGETED_FIX_VERIFICATION_OBSERVATION_VERSION,
    TARGETED_FIX_VERIFICATION_PURPOSE,
    build_rule_evaluation_receipt,
)
from app.targeted_fix_verification_execution_evidence import (
    TARGETED_FIX_VERIFICATION_EXECUTION_EVIDENCE_VERSION,
    evaluate_execution_bound_targeted_fix_verification_service,
    validate_targeted_verification_execution_evidence_binding,
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


def summary(
    *,
    consumed=0,
    reused=0,
    remaining=None,
    configured=18,
    shared_limit=100,
    crawl_consumed=80,
    target_stats=None,
    observations=None,
    truncated=False,
    budget_exhausted=False,
    deadline_exhausted=False,
):
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
            "requests_reused": reused,
            "requests_remaining": remaining,
            "budget_exhausted": budget_exhausted,
            "deadline_exhausted": deadline_exhausted,
            "time_budget_seconds": 30.0,
        },
        "purposes": purposes,
        "observations": observations or [],
        "observation_samples_truncated": truncated,
    }


def scheduler_observation(
    url,
    *,
    state="pass",
    reason="verified",
    status_code=None,
    final_url=None,
    evidence_ref=None,
):
    if status_code is None:
        status_code = 200 if state != "not_verified" else 0
    if final_url is None:
        final_url = url if state != "not_verified" else ""
    if evidence_ref is None:
        evidence_ref = f"{COVERAGE_PROBE_SCHEDULER_VERSION}:receipt:{url.rsplit('/', 1)[-1]}"
    return {
        "purpose": TARGETED_FIX_VERIFICATION_PURPOSE,
        "version": COVERAGE_PROBE_SCHEDULER_VERSION,
        "state": state,
        "reason": reason,
        "observed_url": url,
        "status_code": status_code,
        "final_url": final_url,
        "source_pages": [],
        "link_text_samples": [],
        "metadata": {},
        "evidence_ref": evidence_ref,
    }


def prepare(sealed=None, *, pre=None):
    sealed = sealed or repair()
    pre = pre or summary()
    return prepare_targeted_fix_verification_service(
        sealed,
        source_scan_id="scan-old",
        source_scan_origin=ORIGIN,
        scheduler_summary=pre,
    )


def observed(prepared, key, *, scheduler_ref=None, **page_overrides):
    scheduler_ref = scheduler_ref or f"{COVERAGE_PROBE_SCHEDULER_VERSION}:receipt:{key.rsplit('/', 1)[-1]}"
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
        "scheduler_evidence_ref": scheduler_ref,
        "state": "observed",
        "page": page,
    }


def not_verified(prepared, key, reason, *, scheduler_ref=None):
    scheduler_ref = scheduler_ref or f"{COVERAGE_PROBE_SCHEDULER_VERSION}:receipt:{key.rsplit('/', 1)[-1]}"
    return {
        "version": TARGETED_FIX_VERIFICATION_OBSERVATION_VERSION,
        "plan_fingerprint": prepared["plan"]["plan_fingerprint"],
        "evidence_key": key,
        "scheduler_evidence_ref": scheduler_ref,
        "state": "not_verified",
        "reason": reason,
    }


def completed_post(prepared, *, state="pass", reason="verified", consumed=None):
    urls = [row["url"] for row in prepared["plan"]["requests"]]
    if consumed is None:
        consumed = len(urls)
    observations = [scheduler_observation(url, state=state, reason=reason) for url in urls]
    return summary(
        consumed=consumed,
        target_stats=stats(
            eligible=len(urls),
            selected=len(urls),
            attempted=len(urls),
            completed=len(urls),
            passed=len(urls) if state == "pass" else 0,
            failed=len(urls) if state == "fail" else 0,
            not_verified=len(urls) if state == "not_verified" else 0,
        ),
        observations=observations,
    )


def evaluate(
    prepared,
    sealed,
    *,
    pre=None,
    post=None,
    outcomes=None,
    current_fixes=None,
    current_contract=None,
):
    pre = pre or summary()
    post = post or completed_post(prepared)
    current_fixes = [] if current_fixes is None else current_fixes
    if outcomes is None:
        outcomes = [
            observed(prepared, row["evidence_key"])
            for row in prepared["plan"]["requests"]
        ]
    receipt = build_rule_evaluation_receipt(prepared["plan"], current_fixes)
    return evaluate_execution_bound_targeted_fix_verification_service(
        prepared,
        sealed,
        preflight_scheduler_summary=pre,
        postflight_scheduler_summary=post,
        current_scan_origin=ORIGIN,
        current_contract=current_contract or contract(),
        recheck_outcomes=outcomes,
        current_fixes=current_fixes,
        rule_evaluation_receipt=receipt,
    )


def test_exact_scheduler_receipts_preserve_canonical_pass():
    sealed = repair()
    pre = summary()
    ready = prepare(sealed, pre=pre)
    result = evaluate(ready, sealed, pre=pre)
    assert result["state"] == "PASS"
    assert result["execution_evidence"]["state"] == "valid"
    assert result["execution_evidence"]["bound_observation_count"] == 2
    assert result["execution_evidence_version"] == TARGETED_FIX_VERIFICATION_EXECUTION_EVIDENCE_VERSION
    assert result["side_effects_performed"] is False


def test_execution_evidence_wrapper_preserves_partial_and_fail_from_comparator():
    sealed = repair()
    pre = summary()
    ready = prepare(sealed, pre=pre)
    partial = evaluate(ready, sealed, pre=pre, current_fixes=[repair(["/a"])])
    failed = evaluate(ready, sealed, pre=pre, current_fixes=[repair(["/a", "/b"])])
    assert partial["state"] == "PARTIAL"
    assert failed["state"] == "FAIL"


def test_verified_fixed_reappearance_still_reopens_without_mutation():
    sealed = repair(verification_state="verified_fixed")
    snapshot = copy.deepcopy(sealed)
    pre = summary()
    ready = prepare(sealed, pre=pre)
    result = evaluate(ready, sealed, pre=pre, current_fixes=[repair(["/a", "/b"])])
    assert result["state"] == "FAIL"
    assert result["reopen_regression"] is True
    assert sealed == snapshot


def test_scheduler_evidence_ref_must_be_echoed_exactly_by_recheck_outcome():
    sealed = repair(["/a"])
    pre = summary()
    ready = prepare(sealed, pre=pre)
    key = ready["plan"]["requests"][0]["evidence_key"]
    post = completed_post(ready)
    result = evaluate(
        ready,
        sealed,
        pre=pre,
        post=post,
        outcomes=[observed(ready, key, scheduler_ref="wrong-receipt")],
    )
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "recheck_outcome_scheduler_evidence_ref_mismatch"


def test_scheduler_evidence_ref_missing_is_never_proof():
    sealed = repair(["/a"])
    pre = summary()
    ready = prepare(sealed, pre=pre)
    post = completed_post(ready)
    del post["observations"][0]["evidence_ref"]
    result = evaluate(ready, sealed, pre=pre, post=post)
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "targeted_scheduler_evidence_ref_missing"


def test_observed_outcome_must_match_scheduler_terminal_class():
    sealed = repair(["/a"])
    pre = summary()
    ready = prepare(sealed, pre=pre)
    key = ready["plan"]["requests"][0]["evidence_key"]
    post = completed_post(ready, state="not_verified", reason="timeout")
    result = evaluate(ready, sealed, pre=pre, post=post, outcomes=[observed(ready, key)])
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "scheduler_not_verified_outcome_state_mismatch"


def test_not_verified_scheduler_reason_must_match_exactly():
    sealed = repair(["/a"])
    pre = summary()
    ready = prepare(sealed, pre=pre)
    key = ready["plan"]["requests"][0]["evidence_key"]
    post = completed_post(ready, state="not_verified", reason="timeout")
    result = evaluate(
        ready,
        sealed,
        pre=pre,
        post=post,
        outcomes=[not_verified(ready, key, "challenge")],
    )
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "scheduler_not_verified_reason_mismatch"


def test_exact_timeout_receipt_still_maps_to_could_not_verify_not_pass():
    sealed = repair(["/a"])
    pre = summary()
    ready = prepare(sealed, pre=pre)
    key = ready["plan"]["requests"][0]["evidence_key"]
    post = completed_post(ready, state="not_verified", reason="timeout")
    result = evaluate(
        ready,
        sealed,
        pre=pre,
        post=post,
        outcomes=[not_verified(ready, key, "timeout")],
    )
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "timeout"


def test_scheduler_and_page_status_must_match_exactly():
    sealed = repair(["/a"])
    pre = summary()
    ready = prepare(sealed, pre=pre)
    key = ready["plan"]["requests"][0]["evidence_key"]
    post = completed_post(ready)
    result = evaluate(
        ready,
        sealed,
        pre=pre,
        post=post,
        outcomes=[observed(ready, key, status_code=204)],
    )
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "scheduler_page_status_mismatch"


def test_redirected_or_disappeared_planned_url_is_never_proof_of_fix():
    sealed = repair(["/a"])
    pre = summary()
    ready = prepare(sealed, pre=pre)
    key = ready["plan"]["requests"][0]["evidence_key"]
    post = completed_post(ready)
    post["observations"][0]["final_url"] = "https://example.com/replacement"
    result = evaluate(
        ready,
        sealed,
        pre=pre,
        post=post,
        outcomes=[observed(ready, key, final_url="https://example.com/replacement")],
    )
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "targeted_scheduler_final_url_changed"


def test_page_final_url_must_bind_to_scheduler_final_url():
    sealed = repair(["/a"])
    pre = summary()
    ready = prepare(sealed, pre=pre)
    key = ready["plan"]["requests"][0]["evidence_key"]
    result = evaluate(
        ready,
        sealed,
        pre=pre,
        outcomes=[observed(ready, key, final_url="https://example.com/other")],
    )
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "scheduler_page_final_url_mismatch"


def test_missing_planned_outcome_cannot_be_inferred_from_scheduler_receipt():
    sealed = repair()
    pre = summary()
    ready = prepare(sealed, pre=pre)
    first = ready["plan"]["requests"][0]["evidence_key"]
    result = evaluate(ready, sealed, pre=pre, outcomes=[observed(ready, first)])
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "recheck_outcome_population_mismatch"


def test_scope_expansion_still_fails_in_shared_execution_accounting_first():
    sealed = repair()
    pre = summary()
    ready = prepare(sealed, pre=pre)
    post = completed_post(ready)
    post["observations"][1] = scheduler_observation("https://evil.example/b")
    result = evaluate(ready, sealed, pre=pre, post=post)
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "targeted_scheduler_observation_outside_plan"


def test_robots_and_challenge_evidence_remain_could_not_verify_after_exact_binding():
    sealed = repair(["/a"])
    pre = summary()
    ready = prepare(sealed, pre=pre)
    key = ready["plan"]["requests"][0]["evidence_key"]

    robots = evaluate(
        ready,
        sealed,
        pre=pre,
        outcomes=[observed(ready, key, robots_txt_fetch_allowed=False)],
    )
    challenge = evaluate(
        ready,
        sealed,
        pre=pre,
        outcomes=[observed(ready, key, access_block_kind="challenge")],
    )
    assert robots["state"] == "COULD_NOT_VERIFY"
    assert robots["reason"] == "robots_denied"
    assert challenge["state"] == "COULD_NOT_VERIFY"
    assert challenge["reason"] == "challenge"


def test_rule_version_drift_still_cannot_become_pass():
    sealed = repair(["/a"])
    pre = summary()
    ready = prepare(sealed, pre=pre)
    result = evaluate(
        ready,
        sealed,
        pre=pre,
        current_contract=contract(rule_definition_version="missing_h1_v4"),
    )
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "current_comparison_contract_mismatch"


def test_binding_validator_reports_exact_bound_count_without_mutating_inputs():
    sealed = repair()
    pre = summary()
    ready = prepare(sealed, pre=pre)
    post = completed_post(ready)
    outcomes = [observed(ready, row["evidence_key"]) for row in ready["plan"]["requests"]]
    plan_snapshot = copy.deepcopy(ready["plan"])
    post_snapshot = copy.deepcopy(post)
    outcome_snapshot = copy.deepcopy(outcomes)
    binding = validate_targeted_verification_execution_evidence_binding(
        ready["plan"],
        sealed,
        preflight_scheduler_summary=pre,
        postflight_scheduler_summary=post,
        recheck_outcomes=outcomes,
    )
    assert binding["state"] == "valid"
    assert binding["bound_observation_count"] == 2
    assert ready["plan"] == plan_snapshot
    assert post == post_snapshot
    assert outcomes == outcome_snapshot
