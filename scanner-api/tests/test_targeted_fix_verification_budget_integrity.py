import copy

import pytest

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
    TARGETED_FIX_VERIFICATION_PURPOSE,
    _fingerprint,
    _plan_fingerprint_material,
    build_targeted_recheck_plan,
)
from app.targeted_fix_verification_budget_integrity import (
    TARGETED_FIX_VERIFICATION_BUDGET_INTEGRITY_VERSION,
    strict_targeted_verification_budget_proposal,
    validate_shared_scheduler_snapshot,
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


def ready_plan(sealed=None):
    return build_targeted_recheck_plan(
        sealed or repair(),
        source_scan_id="scan-old",
        source_scan_origin=ORIGIN,
    )


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
            max(
                0,
                shared_request_limit
                - crawl_requests_consumed
                - requests_consumed,
            ),
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


def test_exact_shared_scheduler_snapshot_allows_existing_worst_case_fit_semantics():
    sealed = repair()
    result = strict_targeted_verification_budget_proposal(
        ready_plan(sealed),
        sealed,
        scheduler_summary(),
    )
    assert result["state"] == "fits"
    assert result["required_new_request_upper_bound"] == 2
    assert result["requests_remaining"] == 18
    assert result["integrity_version"] == TARGETED_FIX_VERIFICATION_BUDGET_INTEGRITY_VERSION


def test_scheduler_snapshot_validates_exact_existing_accounting_formula():
    result = validate_shared_scheduler_snapshot(
        scheduler_summary(
            configured_probe_requests=12,
            shared_request_limit=95,
            crawl_requests_consumed=88,
            requests_consumed=3,
            requests_reused=4,
        )
    )
    assert result["state"] == "valid"
    assert result["requests_remaining"] == 4


def test_inconsistent_requests_remaining_fails_closed_before_fit_decision():
    sealed = repair()
    result = strict_targeted_verification_budget_proposal(
        ready_plan(sealed),
        sealed,
        scheduler_summary(requests_remaining=17),
    )
    assert result["state"] == "could_not_verify"
    assert result["reason"] == "shared_scheduler_remaining_budget_inconsistent"


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("configured_probe_requests", True, "shared_scheduler_configured_probe_requests_invalid"),
        ("shared_request_limit", -1, "shared_scheduler_shared_request_limit_invalid"),
        ("crawl_requests_consumed", 1.5, "shared_scheduler_crawl_requests_consumed_invalid"),
        ("requests_consumed", False, "shared_scheduler_requests_consumed_invalid"),
        ("requests_reused", "2", "shared_scheduler_requests_reused_invalid"),
        ("requests_remaining", 2.0, "shared_scheduler_requests_remaining_invalid"),
    ],
)
def test_scheduler_numeric_accounting_is_exact_not_coerced(field, value, reason):
    summary = scheduler_summary()
    summary["request_budget"][field] = value
    result = validate_shared_scheduler_snapshot(summary)
    assert result["state"] == "could_not_verify"
    assert result["reason"] == reason


def test_probe_consumption_above_configured_allowance_fails_closed():
    summary = scheduler_summary(
        configured_probe_requests=18,
        requests_consumed=19,
        requests_remaining=0,
    )
    result = validate_shared_scheduler_snapshot(summary)
    assert result["state"] == "could_not_verify"
    assert result["reason"] == "shared_scheduler_probe_consumption_inconsistent"


def test_budget_exhausted_true_with_remaining_capacity_is_inconsistent():
    summary = scheduler_summary(budget_exhausted=True)
    result = validate_shared_scheduler_snapshot(summary)
    assert result["state"] == "could_not_verify"
    assert result["reason"] == "shared_scheduler_exhaustion_flag_inconsistent"


def test_coherent_budget_exhaustion_never_becomes_fit():
    sealed = repair()
    result = strict_targeted_verification_budget_proposal(
        ready_plan(sealed),
        sealed,
        scheduler_summary(
            configured_probe_requests=2,
            shared_request_limit=82,
            crawl_requests_consumed=80,
            requests_consumed=2,
            budget_exhausted=True,
        ),
    )
    assert result["state"] == "could_not_verify"
    assert result["reason"] == "shared_request_budget_insufficient"


def test_deadline_exhaustion_never_becomes_fit_even_with_capacity_remaining():
    sealed = repair()
    result = strict_targeted_verification_budget_proposal(
        ready_plan(sealed),
        sealed,
        scheduler_summary(deadline_exhausted=True),
    )
    assert result["state"] == "could_not_verify"
    assert result["reason"] == "deadline_exhausted"


def test_cache_reuse_does_not_invent_future_request_capacity():
    sealed = repair()
    result = strict_targeted_verification_budget_proposal(
        ready_plan(sealed),
        sealed,
        scheduler_summary(
            configured_probe_requests=1,
            requests_reused=999,
        ),
    )
    assert result["state"] == "could_not_verify"
    assert result["reason"] == "shared_request_budget_insufficient"


def test_declared_plan_bound_tamper_fails_closed_even_when_plan_fingerprint_does_not_cover_it():
    sealed = repair()
    plan = ready_plan(sealed)
    plan["max_targeted_urls"] = 1
    result = strict_targeted_verification_budget_proposal(
        plan,
        sealed,
        scheduler_summary(),
    )
    assert result["state"] == "could_not_verify"
    assert result["reason"] == "verification_plan_population_exceeds_declared_bound"


def test_shared_scheduler_plan_metadata_tamper_fails_closed():
    sealed = repair()
    plan = ready_plan(sealed)
    plan["shared_scheduler"]["purpose"] = "some_other_purpose"
    result = strict_targeted_verification_budget_proposal(
        plan,
        sealed,
        scheduler_summary(),
    )
    assert result["state"] == "could_not_verify"
    assert result["reason"] == "verification_plan_shared_scheduler_purpose_mismatch"


def test_recomputed_plan_fingerprint_cannot_authorize_same_origin_scope_expansion():
    sealed = repair()
    plan = copy.deepcopy(ready_plan(sealed))
    plan["requests"][0]["evidence_key"] = "https://example.com/not-sealed"
    plan["requests"][0]["url"] = "https://example.com/not-sealed"
    plan["plan_fingerprint"] = _fingerprint(_plan_fingerprint_material(plan))
    result = strict_targeted_verification_budget_proposal(
        plan,
        sealed,
        scheduler_summary(),
    )
    assert result["state"] == "could_not_verify"
    assert result["reason"] == "verification_plan_scope_mismatch"


def test_request_purpose_cannot_be_rewritten_into_another_shared_scheduler_lane():
    sealed = repair()
    plan = copy.deepcopy(ready_plan(sealed))
    plan["requests"][0]["purpose"] = "internal_link"
    plan["plan_fingerprint"] = _fingerprint(_plan_fingerprint_material(plan))
    result = strict_targeted_verification_budget_proposal(
        plan,
        sealed,
        scheduler_summary(),
    )
    assert result["state"] == "could_not_verify"
    assert result["reason"] == "verification_plan_request_purpose_mismatch"
    assert TARGETED_FIX_VERIFICATION_PURPOSE == "targeted_fix_verification"
