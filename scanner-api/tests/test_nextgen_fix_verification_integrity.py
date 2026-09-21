from app.nextgen_fix_verification import COULD_NOT_VERIFY, FAIL, PARTIAL, PASS, VERIFICATION_RESULT_VERSION
from app.nextgen_fix_verification_integrity import (
    STRICT_REGRESSION_REOPEN_VERSION,
    VERIFICATION_RESULT_INTEGRITY_VERSION,
    strict_regression_reopen_decision,
    verification_result_integrity,
)

FINGERPRINT = "repair-fingerprint-123"
CRITERION = "criterion-123"


def result(state, *, resolved=(), unresolved=(), required=2, observed=2, evaluated=2, unverifiable=()):
    return {
        "version": VERIFICATION_RESULT_VERSION,
        "state": state,
        "repair_fingerprint": FINGERPRINT,
        "criterion_id": CRITERION,
        "required_population_count": required,
        "observed_population_count": observed,
        "evaluated_population_count": evaluated,
        "resolved_scope": list(resolved),
        "unresolved_scope": list(unresolved),
        "unverifiable_scope": list(unverifiable),
    }


def previous():
    return {
        "repair_fingerprint": FINGERPRINT,
        "verification_state": "verified_fixed",
    }


def test_complete_fail_is_integrity_valid_and_reopens():
    current = result(FAIL, unresolved=("https://example.com/a", "https://example.com/b"))
    integrity = verification_result_integrity(current)
    decision = strict_regression_reopen_decision(previous(), current)
    assert integrity["version"] == VERIFICATION_RESULT_INTEGRITY_VERSION
    assert integrity["valid"] is True
    assert decision["version"] == STRICT_REGRESSION_REOPEN_VERSION
    assert decision["should_reopen"] is True
    assert decision["reopen_scope"] == ["https://example.com/a", "https://example.com/b"]


def test_complete_partial_reopens_only_exact_unresolved_scope():
    current = result(
        PARTIAL,
        resolved=("https://example.com/a",),
        unresolved=("https://example.com/b",),
    )
    decision = strict_regression_reopen_decision(previous(), current)
    assert decision["should_reopen"] is True
    assert decision["reopen_scope"] == ["https://example.com/b"]


def test_forged_fail_without_complete_population_downgrades_to_could_not_verify():
    current = result(
        FAIL,
        unresolved=("https://example.com/a",),
        required=2,
        observed=1,
        evaluated=1,
    )
    decision = strict_regression_reopen_decision(previous(), current)
    assert decision["should_reopen"] is False
    assert decision["current_verification_state"] == COULD_NOT_VERIFY
    assert decision["reason"].startswith("regression_not_proven:")


def test_forged_partial_with_overlapping_scope_never_reopens():
    current = result(
        PARTIAL,
        resolved=("https://example.com/a",),
        unresolved=("https://example.com/a",),
    )
    integrity = verification_result_integrity(current)
    decision = strict_regression_reopen_decision(previous(), current)
    assert integrity["valid"] is False
    assert integrity["reason"] == "resolved_and_unresolved_scope_overlap"
    assert decision["should_reopen"] is False
    assert decision["current_verification_state"] == COULD_NOT_VERIFY


def test_forged_fail_with_unverifiable_evidence_never_reopens():
    current = result(
        FAIL,
        unresolved=("https://example.com/a", "https://example.com/b"),
        unverifiable=({"evidence_key": "https://example.com/b", "reason": "required_page_not_observed"},),
    )
    decision = strict_regression_reopen_decision(previous(), current)
    assert decision["should_reopen"] is False
    assert decision["current_verification_state"] == COULD_NOT_VERIFY
    assert decision["result_integrity"]["reason"] == "terminal_result_contains_unverifiable_evidence"


def test_pass_requires_complete_resolved_scope_and_never_reopens():
    valid_pass = result(PASS, resolved=("https://example.com/a", "https://example.com/b"))
    valid_decision = strict_regression_reopen_decision(previous(), valid_pass)
    assert valid_decision["should_reopen"] is False
    assert valid_decision["reason"] == "repair_remains_verified"

    forged_pass = result(PASS, resolved=("https://example.com/a",), required=2)
    forged_decision = strict_regression_reopen_decision(previous(), forged_pass)
    assert forged_decision["should_reopen"] is False
    assert forged_decision["current_verification_state"] == COULD_NOT_VERIFY


def test_could_not_verify_is_valid_non_proving_terminal_state():
    current = result(
        COULD_NOT_VERIFY,
        resolved=("https://example.com/a",),
        unresolved=(),
        required=2,
        observed=1,
        evaluated=1,
        unverifiable=({"evidence_key": "https://example.com/b", "reason": "required_page_not_observed"},),
    )
    integrity = verification_result_integrity(current)
    decision = strict_regression_reopen_decision(previous(), current)
    assert integrity["valid"] is True
    assert integrity["reason"] == "could_not_verify_is_non_proving_terminal_state"
    assert decision["should_reopen"] is False
    assert decision["reason"] == "regression_not_proven"


def test_missing_result_identity_fails_closed_for_regression():
    current = result(FAIL, unresolved=("https://example.com/a", "https://example.com/b"))
    current["criterion_id"] = ""
    integrity = verification_result_integrity(current)
    decision = strict_regression_reopen_decision(previous(), current)
    assert integrity["valid"] is False
    assert integrity["reason"] == "verification_result_identity_missing"
    assert decision["should_reopen"] is False
    assert decision["current_verification_state"] == COULD_NOT_VERIFY


def test_changed_fingerprint_never_reopens_even_with_valid_fail():
    current = result(FAIL, unresolved=("https://example.com/a", "https://example.com/b"))
    current["repair_fingerprint"] = "different-fingerprint"
    decision = strict_regression_reopen_decision(previous(), current)
    assert decision["should_reopen"] is False
    assert decision["reason"] == "repair_identity_missing_or_changed"
