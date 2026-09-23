import copy

from app.coverage_probes import COVERAGE_PROBE_SCHEDULER_VERSION
from app.repair_coverage import PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION
from app.targeted_fix_verification import (
    TARGETED_FIX_VERIFICATION_OBSERVATION_VERSION,
    TARGETED_FIX_VERIFICATION_PURPOSE,
    build_rule_evaluation_receipt,
)
from app.targeted_fix_verification_execution_accounting import (
    TARGETED_FIX_VERIFICATION_EXECUTION_ACCOUNTING_VERSION,
    evaluate_executed_targeted_fix_verification_service,
    validate_targeted_verification_execution_accounting,
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


def scheduler_observation(url, *, state="pass", reason="verified"):
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


def observed(prepared, key, **page_overrides):
    page = {
        "url": key,
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
        "state": "observed",
        "page": page,
    }


def not_verified(prepared, key, reason):
    return {
        "version": TARGETED_FIX_VERIFICATION_OBSERVATION_VERSION,
        "plan_fingerprint": prepared["plan"]["plan_fingerprint"],
        "evidence_key": key,
        "state": "not_verified",
        "reason": reason,
    }


def completed_post(prepared, *, consumed=2, reused=0, state="pass"):
    urls = [row["url"] for row in prepared["plan"]["requests"]]
    return summary(
        consumed=consumed,
        reused=reused,
        target_stats=stats(
            eligible=len(urls),
            selected=len(urls),
            attempted=len(urls),
            completed=len(urls),
            passed=len(urls) if state == "pass" else 0,
            failed=len(urls) if state == "fail" else 0,
            not_verified=len(urls) if state == "not_verified" else 0,
        ),
        observations=[scheduler_observation(url, state=state) for url in urls],
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
    return evaluate_executed_targeted_fix_verification_service(
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


def test_valid_execution_delta_preserves_pass_and_is_side_effect_free():
    sealed = repair()
    pre = summary()
    ready = prepare(sealed, pre=pre)
    result = evaluate(ready, sealed, pre=pre)
    assert result["state"] == "PASS"
    assert result["execution_accounting"]["state"] == "valid"
    assert result["execution_accounting"]["requests_consumed_delta"] == 2
    assert result["execution_accounting_version"] == TARGETED_FIX_VERIFICATION_EXECUTION_ACCOUNTING_VERSION
    assert result["side_effects_performed"] is False


def test_cache_reuse_can_reduce_new_requests_without_expanding_plan():
    sealed = repair()
    pre = summary()
    ready = prepare(sealed, pre=pre)
    post = completed_post(ready, consumed=1, reused=1)
    result = evaluate(ready, sealed, pre=pre, post=post)
    assert result["state"] == "PASS"
    assert result["execution_accounting"]["requests_consumed_delta"] == 1
    assert result["execution_accounting"]["requests_reused_delta"] == 1


def test_execution_wrapper_preserves_partial_and_fail_from_existing_comparator():
    sealed = repair()
    pre = summary()
    ready = prepare(sealed, pre=pre)
    partial = evaluate(
        ready,
        sealed,
        pre=pre,
        current_fixes=[repair(["/a"])],
    )
    failed = evaluate(
        ready,
        sealed,
        pre=pre,
        current_fixes=[repair(["/a", "/b"])],
    )
    assert partial["state"] == "PARTIAL"
    assert failed["state"] == "FAIL"


def test_verified_fixed_reappearance_reopens_as_evidence_without_mutation():
    sealed = repair(verification_state="verified_fixed")
    snapshot = copy.deepcopy(sealed)
    pre = summary()
    ready = prepare(sealed, pre=pre)
    result = evaluate(
        ready,
        sealed,
        pre=pre,
        current_fixes=[repair(["/a", "/b"])],
    )
    assert result["state"] == "FAIL"
    assert result["reopen_regression"] is True
    assert sealed == snapshot


def test_missing_scheduler_observation_fails_closed_before_repair_truth():
    sealed = repair()
    pre = summary()
    ready = prepare(sealed, pre=pre)
    urls = [row["url"] for row in ready["plan"]["requests"]]
    post = summary(
        consumed=2,
        target_stats=stats(eligible=2, selected=2, attempted=2, completed=2, passed=2),
        observations=[scheduler_observation(urls[0])],
    )
    result = evaluate(ready, sealed, pre=pre, post=post)
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "targeted_scheduler_observation_population_mismatch"


def test_scheduler_observation_cannot_smuggle_same_origin_url_outside_plan():
    sealed = repair()
    pre = summary()
    ready = prepare(sealed, pre=pre)
    urls = [row["url"] for row in ready["plan"]["requests"]]
    post = summary(
        consumed=2,
        target_stats=stats(eligible=2, selected=2, attempted=2, completed=2, passed=2),
        observations=[
            scheduler_observation(urls[0]),
            scheduler_observation("https://example.com/not-sealed"),
        ],
    )
    result = evaluate(ready, sealed, pre=pre, post=post)
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "targeted_scheduler_observation_outside_plan"


def test_scheduler_observation_cannot_expand_host():
    sealed = repair()
    pre = summary()
    ready = prepare(sealed, pre=pre)
    urls = [row["url"] for row in ready["plan"]["requests"]]
    post = summary(
        consumed=2,
        target_stats=stats(eligible=2, selected=2, attempted=2, completed=2, passed=2),
        observations=[
            scheduler_observation(urls[0]),
            scheduler_observation("https://evil.example/b"),
        ],
    )
    result = evaluate(ready, sealed, pre=pre, post=post)
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "targeted_scheduler_observation_outside_plan"


def test_duplicate_scheduler_observation_fails_closed():
    sealed = repair()
    pre = summary()
    ready = prepare(sealed, pre=pre)
    first = ready["plan"]["requests"][0]["url"]
    post = summary(
        consumed=2,
        target_stats=stats(eligible=2, selected=2, attempted=2, completed=2, passed=2),
        observations=[scheduler_observation(first), scheduler_observation(first)],
    )
    result = evaluate(ready, sealed, pre=pre, post=post)
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "duplicate_targeted_scheduler_observation"


def test_truncated_scheduler_receipt_is_never_proof():
    sealed = repair()
    pre = summary()
    ready = prepare(sealed, pre=pre)
    post = completed_post(ready)
    post["observation_samples_truncated"] = True
    result = evaluate(ready, sealed, pre=pre, post=post)
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "shared_scheduler_observations_truncated"


def test_scheduler_history_must_be_append_only():
    prior = {
        "purpose": "internal_link",
        "version": "link_integrity_probe_v1_unsampled_same_site",
        "state": "pass",
        "observed_url": "https://example.com/prior",
    }
    sealed = repair()
    pre = summary(observations=[prior])
    ready = prepare(sealed, pre=pre)
    urls = [row["url"] for row in ready["plan"]["requests"]]
    rewritten = {**prior, "state": "fail"}
    post = summary(
        consumed=2,
        target_stats=stats(eligible=2, selected=2, attempted=2, completed=2, passed=2),
        observations=[rewritten, *(scheduler_observation(url) for url in urls)],
    )
    result = evaluate(ready, sealed, pre=pre, post=post)
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "shared_scheduler_observation_history_rewritten"


def test_shared_budget_envelope_cannot_change_during_execution():
    sealed = repair()
    pre = summary()
    ready = prepare(sealed, pre=pre)
    post = completed_post(ready)
    post["request_budget"]["shared_request_limit"] = 101
    result = evaluate(ready, sealed, pre=pre, post=post)
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "shared_scheduler_shared_request_limit_changed_during_execution"


def test_request_counters_cannot_go_backwards():
    sealed = repair()
    pre = summary(consumed=2, reused=1)
    ready = prepare(sealed, pre=pre)
    post = summary(
        consumed=1,
        reused=1,
        target_stats=stats(eligible=2, selected=2, attempted=2, completed=2, passed=2),
        observations=[scheduler_observation(row["url"]) for row in ready["plan"]["requests"]],
    )
    accounting = validate_targeted_verification_execution_accounting(
        ready["plan"],
        sealed,
        preflight_scheduler_summary=pre,
        postflight_scheduler_summary=post,
    )
    assert accounting["state"] == "could_not_verify"
    assert accounting["reason"] == "shared_scheduler_requests_consumed_went_backwards"


def test_execution_cannot_consume_more_new_requests_than_declared_plan_bound():
    sealed = repair()
    pre = summary()
    ready = prepare(sealed, pre=pre)
    post = completed_post(ready, consumed=3)
    result = evaluate(ready, sealed, pre=pre, post=post)
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "targeted_execution_exceeded_declared_new_request_bound"


def test_disappeared_url_is_still_could_not_verify_after_valid_scheduler_execution():
    sealed = repair()
    pre = summary()
    ready = prepare(sealed, pre=pre)
    post = completed_post(ready)
    first = ready["plan"]["requests"][0]["evidence_key"]
    result = evaluate(
        ready,
        sealed,
        pre=pre,
        post=post,
        outcomes=[observed(ready, first)],
    )
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "one_or_more_planned_urls_were_not_observed"


def test_robots_challenge_timeout_and_rule_drift_remain_could_not_verify():
    sealed = repair(["/a"])
    pre = summary()
    ready = prepare(sealed, pre=pre)
    key = ready["plan"]["requests"][0]["evidence_key"]
    post = completed_post(ready, consumed=1)

    robots = evaluate(
        ready,
        sealed,
        pre=pre,
        post=post,
        outcomes=[observed(ready, key, robots_txt_fetch_allowed=False)],
    )
    challenge = evaluate(
        ready,
        sealed,
        pre=pre,
        post=post,
        outcomes=[observed(ready, key, access_block_kind="challenge")],
    )
    timeout = evaluate(
        ready,
        sealed,
        pre=pre,
        post=post,
        outcomes=[not_verified(ready, key, "timeout")],
    )
    drift = evaluate(
        ready,
        sealed,
        pre=pre,
        post=post,
        current_contract=contract(rule_definition_version="missing_h1_v4"),
    )
    assert robots["state"] == "COULD_NOT_VERIFY"
    assert challenge["state"] == "COULD_NOT_VERIFY"
    assert timeout["state"] == "COULD_NOT_VERIFY"
    assert drift["state"] == "COULD_NOT_VERIFY"


def test_postflight_cannot_be_substituted_for_preflight_prepared_snapshot():
    sealed = repair()
    pre = summary()
    ready = prepare(sealed, pre=pre)
    substituted_pre = copy.deepcopy(pre)
    substituted_pre["request_budget"]["time_budget_seconds"] = 31.0
    post = completed_post(ready)
    result = evaluate(ready, sealed, pre=substituted_pre, post=post)
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "shared_scheduler_snapshot_fingerprint_mismatch"


def test_observed_population_requires_exact_request_or_reuse_accounting():
    sealed = repair()
    pre = summary()
    ready = prepare(sealed, pre=pre)
    for consumed, reused in [(0, 0), (1, 0), (0, 1), (1, 2), (0, 100)]:
        post = completed_post(ready, consumed=consumed, reused=reused)
        result = evaluate(ready, sealed, pre=pre, post=post)
        assert result["state"] == "COULD_NOT_VERIFY", (consumed, reused)
        assert result["reason"] == "targeted_execution_request_accounting_population_mismatch"
