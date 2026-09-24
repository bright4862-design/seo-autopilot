import copy

from app.coverage_probes import COVERAGE_PROBE_SCHEDULER_VERSION
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
)
from app.targeted_fix_verification_service_adapter import (
    TARGETED_FIX_VERIFICATION_PREPARED_VERSION,
    TARGETED_FIX_VERIFICATION_SERVICE_ADAPTER_VERSION,
    evaluate_prepared_targeted_fix_verification_service,
    prepare_targeted_fix_verification_service,
)

ORIGIN = "https://example.com"
RULE_VERSION = MISSING_H1_RULE_DEFINITION_VERSION
PROFILE_VERSION = MISSING_H1_COMPARISON_PROFILE_VERSION


def repair(urls=None, **overrides):
    value = {
        "rule": MISSING_H1_RULE,
        "category": "thin_content",
        "repair_surface": MISSING_H1_REPAIR_SURFACE,
        "remediation_family": MISSING_H1_REMEDIATION_FAMILY,
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


def scheduler_summary(
    *,
    configured_probe_requests=18,
    shared_request_limit=100,
    crawl_requests_consumed=80,
    requests_consumed=0,
    requests_reused=0,
    requests_remaining=None,
    budget_exhausted=False,
    deadline_exhausted=False,
):
    if requests_remaining is None:
        requests_remaining = min(
            max(0, configured_probe_requests - requests_consumed),
            max(0, shared_request_limit - crawl_requests_consumed - requests_consumed),
        )
    return {
        "version": COVERAGE_PROBE_SCHEDULER_VERSION,
        "request_budget": {
            "configured_probe_requests": configured_probe_requests,
            "shared_request_limit": shared_request_limit,
            "crawl_requests_consumed": crawl_requests_consumed,
            "requests_consumed": requests_consumed,
            "requests_reused": requests_reused,
            "requests_remaining": requests_remaining,
            "budget_exhausted": budget_exhausted,
            "deadline_exhausted": deadline_exhausted,
        },
    }


def prepared(sealed=None, *, summary=None, requested_urls=None):
    return prepare_targeted_fix_verification_service(
        sealed or repair(),
        source_scan_id="scan-old",
        source_scan_origin=ORIGIN,
        scheduler_summary=summary or scheduler_summary(),
        requested_urls=requested_urls,
    )


def observed(prepared_envelope, key, **page_overrides):
    plan = prepared_envelope["plan"]
    page = {
        "url": key,
        "status_code": 200,
        "content_type": "text/html; charset=utf-8",
        "page_evidence_class": "usable_html",
        "raw_html_truncated": False,
        "robots_txt_fetch_allowed": True,
        "access_block_kind": "",
        "fetch_error": "",
        "indexable": True,
        "comparison_rule_evaluation": {
            "rule": MISSING_H1_RULE,
            "rule_definition_version": MISSING_H1_RULE_DEFINITION_VERSION,
            "comparison_profile_version": MISSING_H1_COMPARISON_PROFILE_VERSION,
            "evaluated": True,
            "applicable": True,
            "finding_present": False,
        },
    }
    page.update(page_overrides)
    return {
        "version": TARGETED_FIX_VERIFICATION_OBSERVATION_VERSION,
        "plan_fingerprint": plan["plan_fingerprint"],
        "evidence_key": key,
        "state": "observed",
        "page": page,
    }


def not_verified(prepared_envelope, key, reason):
    plan = prepared_envelope["plan"]
    return {
        "version": TARGETED_FIX_VERIFICATION_OBSERVATION_VERSION,
        "plan_fingerprint": plan["plan_fingerprint"],
        "evidence_key": key,
        "state": "not_verified",
        "reason": reason,
    }


def evaluate(
    prepared_envelope,
    sealed,
    *,
    summary=None,
    current_fixes=None,
    outcomes=None,
    current_contract=None,
):
    current_fixes = [] if current_fixes is None else current_fixes
    plan = prepared_envelope["plan"]
    if outcomes is None:
        outcomes = [
            observed(prepared_envelope, row["evidence_key"])
            for row in plan["requests"]
        ]
    receipt = build_rule_evaluation_receipt(plan, current_fixes)
    return evaluate_prepared_targeted_fix_verification_service(
        prepared_envelope,
        sealed,
        scheduler_summary=summary or scheduler_summary(),
        current_scan_origin=ORIGIN,
        current_contract=current_contract or contract(),
        recheck_outcomes=outcomes,
        current_fixes=current_fixes,
        rule_evaluation_receipt=receipt,
    )


def test_prepare_service_is_pure_ready_preflight_bound_to_exact_plan_and_budget_snapshot():
    sealed = repair()
    result = prepared(sealed)
    assert result["version"] == TARGETED_FIX_VERIFICATION_PREPARED_VERSION
    assert result["service_adapter_version"] == TARGETED_FIX_VERIFICATION_SERVICE_ADAPTER_VERSION
    assert result["state"] == "ready"
    assert result["prepared_fingerprint"]
    assert result["budget"]["state"] == "fits"
    assert result["execution_contract"] == {
        "performs_io": False,
        "calls_private_worker": False,
        "mutates_authority": False,
        "mutates_persistence": False,
        "mutates_historical_repairs": False,
        "requires_existing_shared_scheduler": True,
        "requires_protected_fetch_path": True,
        "requires_complete_rule_evaluation_receipt": True,
    }


def test_prepare_rejects_foreign_host_scope_expansion():
    result = prepared(
        repair(),
        requested_urls=["https://evil.example/a", "https://example.com/b"],
    )
    assert result["state"] == "could_not_verify"
    assert "requested_url_expands_source_origin" in result["plan"]["blockers"]


def test_prepare_rejects_same_origin_url_outside_sealed_repair_set():
    result = prepared(
        repair(),
        requested_urls=["https://example.com/a", "https://example.com/not-sealed"],
    )
    assert result["state"] == "could_not_verify"
    assert "requested_url_outside_sealed_repair_set" in result["plan"]["blockers"]


def test_prepare_never_turns_insufficient_shared_budget_into_ready():
    result = prepared(
        repair(),
        summary=scheduler_summary(
            configured_probe_requests=1,
            shared_request_limit=81,
            crawl_requests_consumed=80,
        ),
    )
    assert result["state"] == "could_not_verify"
    assert result["reason"] == "shared_request_budget_insufficient"


def test_prepare_never_turns_deadline_exhaustion_into_ready():
    result = prepared(repair(), summary=scheduler_summary(deadline_exhausted=True))
    assert result["state"] == "could_not_verify"
    assert result["reason"] == "deadline_exhausted"


def test_adapter_preserves_canonical_pass_partial_and_fail_states():
    sealed = repair()
    ready = prepared(sealed)
    passed = evaluate(ready, sealed)
    partial = evaluate(ready, sealed, current_fixes=[repair(["/a"])])
    failed = evaluate(ready, sealed, current_fixes=[repair(["/a", "/b"])])
    assert passed["state"] == "PASS"
    assert partial["state"] == "PARTIAL"
    assert failed["state"] == "FAIL"
    assert passed["side_effects_performed"] is False
    assert partial["side_effects_performed"] is False
    assert failed["side_effects_performed"] is False


def test_adapter_preserves_regression_reopen_evidence_without_mutating_historical_repair():
    sealed = repair(verification_state="verified_fixed")
    snapshot = copy.deepcopy(sealed)
    ready = prepared(sealed)
    result = evaluate(ready, sealed, current_fixes=[repair(["/a", "/b"])])
    assert result["state"] == "FAIL"
    assert result["reopen_regression"] is True
    assert result["regression_evidence_keys"] == [
        "https://example.com/a",
        "https://example.com/b",
    ]
    assert sealed == snapshot


def test_disappeared_url_remains_could_not_verify_never_pass():
    sealed = repair()
    ready = prepared(sealed)
    first = ready["plan"]["requests"][0]["evidence_key"]
    result = evaluate(ready, sealed, outcomes=[observed(ready, first)])
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "one_or_more_planned_urls_were_not_observed"


def test_robots_challenge_and_timeout_remain_could_not_verify():
    sealed = repair(["/a"])
    ready = prepared(sealed)
    key = ready["plan"]["requests"][0]["evidence_key"]

    robots = evaluate(
        ready,
        sealed,
        outcomes=[observed(ready, key, robots_txt_fetch_allowed=False)],
    )
    challenge = evaluate(
        ready,
        sealed,
        outcomes=[observed(ready, key, access_block_kind="challenge")],
    )
    timeout = evaluate(
        ready,
        sealed,
        outcomes=[not_verified(ready, key, "timeout")],
    )
    assert robots["state"] == "COULD_NOT_VERIFY"
    assert robots["reason"] == "robots_denied"
    assert challenge["state"] == "COULD_NOT_VERIFY"
    assert challenge["reason"] == "challenge"
    assert timeout["state"] == "COULD_NOT_VERIFY"
    assert timeout["reason"] == "timeout"


def test_rule_version_drift_remains_could_not_verify():
    sealed = repair()
    ready = prepared(sealed)
    result = evaluate(
        ready,
        sealed,
        current_contract=contract(rule_definition_version="missing_h1_v4"),
    )
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "current_comparison_contract_mismatch"


def test_prepared_transport_tamper_fails_closed_before_evaluation():
    sealed = repair()
    ready = prepared(sealed)
    tampered = copy.deepcopy(ready)
    tampered["plan"]["max_targeted_urls"] = 1
    result = evaluate(tampered, sealed)
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "prepared_verification_fingerprint_mismatch"


def test_scheduler_snapshot_substitution_fails_closed():
    sealed = repair()
    ready = prepared(sealed)
    substituted = scheduler_summary(requests_reused=1)
    result = evaluate(ready, sealed, summary=substituted)
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "shared_scheduler_snapshot_fingerprint_mismatch"


def test_prepared_budget_tamper_fails_closed_even_when_plan_is_unchanged():
    sealed = repair()
    ready = prepared(sealed)
    tampered = copy.deepcopy(ready)
    tampered["budget"]["requests_remaining"] += 1
    result = evaluate(tampered, sealed)
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "prepared_verification_fingerprint_mismatch"


def test_service_adapter_never_synthesizes_rule_receipt_or_executes_fetches():
    sealed = repair()
    ready = prepared(sealed)
    plan = ready["plan"]
    outcomes = [
        observed(ready, row["evidence_key"])
        for row in plan["requests"]
    ]
    result = evaluate_prepared_targeted_fix_verification_service(
        ready,
        sealed,
        scheduler_summary=scheduler_summary(),
        current_scan_origin=ORIGIN,
        current_contract=contract(),
        recheck_outcomes=outcomes,
        current_fixes=[],
        rule_evaluation_receipt=None,
    )
    assert result["state"] == "COULD_NOT_VERIFY"
    assert result["reason"] == "rule_evaluation_receipt_missing"
    assert result["side_effects_performed"] is False
