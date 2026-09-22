from app.nextgen_fix_verification import (
    COULD_NOT_VERIFY,
    FAIL,
    PARTIAL,
    PASS,
    VERIFICATION_RESULT_VERSION,
    build_acceptance_criterion,
)
from app.nextgen_fix_verification_integrity import (
    STRICT_REGRESSION_REOPEN_VERSION,
    VERIFICATION_RESULT_BINDING_VERSION,
    VERIFICATION_RESULT_INTEGRITY_VERSION,
    strict_regression_reopen_decision,
    verification_result_historical_binding,
    verification_result_integrity,
)
from app.repair_coverage import PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION


def previous():
    record = {
        "rule_id": "missing_title",
        "repair_surface": "head.title",
        "remediation_family": "set_title",
        "affected_pages": ["https://example.com/a", "https://example.com/b"],
        "rule_definition_version": "rule-v1",
        "comparison_profile_version": "profile-v1",
        "evidence_url_identity_version": PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION,
        "verification_state": "verified_fixed",
    }
    criterion = build_acceptance_criterion(record)
    assert criterion["state"] == "ready"
    record.update(
        {
            "repair_fingerprint": criterion["repair_fingerprint"],
            "repair_identity_version": criterion["repair_identity_version"],
            "repair_identity": {
                "version": criterion["repair_identity_version"],
                "fingerprint": criterion["repair_fingerprint"],
                "stable": True,
            },
        }
    )
    return record


def result(
    state,
    *,
    previous_record=None,
    resolved=(),
    unresolved=(),
    required=2,
    observed=2,
    evaluated=2,
    unverifiable=(),
):
    previous_record = previous_record or previous()
    criterion = build_acceptance_criterion(previous_record)
    return {
        "version": VERIFICATION_RESULT_VERSION,
        "state": state,
        "repair_fingerprint": criterion["repair_fingerprint"],
        "criterion_id": criterion["criterion_id"],
        "required_population_count": required,
        "observed_population_count": observed,
        "evaluated_population_count": evaluated,
        "resolved_scope": list(resolved),
        "unresolved_scope": list(unresolved),
        "unverifiable_scope": list(unverifiable),
    }


def test_complete_fail_is_integrity_valid_bound_and_reopens():
    historical = previous()
    current = result(
        FAIL,
        previous_record=historical,
        unresolved=("https://example.com/a", "https://example.com/b"),
    )
    integrity = verification_result_integrity(current)
    binding = verification_result_historical_binding(historical, current)
    decision = strict_regression_reopen_decision(historical, current)
    assert integrity["version"] == VERIFICATION_RESULT_INTEGRITY_VERSION
    assert integrity["valid"] is True
    assert binding["version"] == VERIFICATION_RESULT_BINDING_VERSION
    assert binding["valid"] is True
    assert binding["historical_population_count"] == 2
    assert decision["version"] == STRICT_REGRESSION_REOPEN_VERSION
    assert decision["should_reopen"] is True
    assert decision["reopen_scope"] == ["https://example.com/a", "https://example.com/b"]


def test_complete_partial_reopens_only_exact_unresolved_scope():
    historical = previous()
    current = result(
        PARTIAL,
        previous_record=historical,
        resolved=("https://example.com/a",),
        unresolved=("https://example.com/b",),
    )
    decision = strict_regression_reopen_decision(historical, current)
    assert decision["should_reopen"] is True
    assert decision["reopen_scope"] == ["https://example.com/b"]


def test_forged_fail_without_complete_population_downgrades_to_could_not_verify():
    historical = previous()
    current = result(
        FAIL,
        previous_record=historical,
        unresolved=("https://example.com/a",),
        required=2,
        observed=1,
        evaluated=1,
    )
    decision = strict_regression_reopen_decision(historical, current)
    assert decision["should_reopen"] is False
    assert decision["current_verification_state"] == COULD_NOT_VERIFY
    assert decision["reason"].startswith("regression_not_proven:result_integrity_invalid:")


def test_forged_partial_with_overlapping_scope_never_reopens():
    historical = previous()
    current = result(
        PARTIAL,
        previous_record=historical,
        resolved=("https://example.com/a",),
        unresolved=("https://example.com/a",),
    )
    integrity = verification_result_integrity(current)
    decision = strict_regression_reopen_decision(historical, current)
    assert integrity["valid"] is False
    assert integrity["reason"] == "resolved_and_unresolved_scope_overlap"
    assert decision["should_reopen"] is False
    assert decision["current_verification_state"] == COULD_NOT_VERIFY


def test_forged_fail_with_unverifiable_evidence_never_reopens():
    historical = previous()
    current = result(
        FAIL,
        previous_record=historical,
        unresolved=("https://example.com/a", "https://example.com/b"),
        unverifiable=(
            {
                "evidence_key": "https://example.com/b",
                "reason": "required_page_not_observed",
            },
        ),
    )
    decision = strict_regression_reopen_decision(historical, current)
    assert decision["should_reopen"] is False
    assert decision["current_verification_state"] == COULD_NOT_VERIFY
    assert decision["result_integrity"]["reason"] == "terminal_result_contains_unverifiable_evidence"


def test_pass_requires_complete_resolved_scope_and_never_reopens():
    historical = previous()
    valid_pass = result(
        PASS,
        previous_record=historical,
        resolved=("https://example.com/a", "https://example.com/b"),
    )
    valid_decision = strict_regression_reopen_decision(historical, valid_pass)
    assert valid_decision["should_reopen"] is False
    assert valid_decision["reason"] == "repair_remains_verified"

    forged_pass = result(
        PASS,
        previous_record=historical,
        resolved=("https://example.com/a",),
        required=2,
    )
    forged_decision = strict_regression_reopen_decision(historical, forged_pass)
    assert forged_decision["should_reopen"] is False
    assert forged_decision["current_verification_state"] == COULD_NOT_VERIFY


def test_could_not_verify_is_valid_non_proving_terminal_state():
    historical = previous()
    current = result(
        COULD_NOT_VERIFY,
        previous_record=historical,
        resolved=("https://example.com/a",),
        unresolved=(),
        required=2,
        observed=1,
        evaluated=1,
        unverifiable=(
            {
                "evidence_key": "https://example.com/b",
                "reason": "required_page_not_observed",
            },
        ),
    )
    integrity = verification_result_integrity(current)
    binding = verification_result_historical_binding(historical, current)
    decision = strict_regression_reopen_decision(historical, current)
    assert integrity["valid"] is True
    assert integrity["reason"] == "could_not_verify_is_non_proving_terminal_state"
    assert binding["valid"] is True
    assert decision["should_reopen"] is False
    assert decision["reason"] == "regression_not_proven"


def test_missing_result_identity_fails_closed_for_regression():
    historical = previous()
    current = result(
        FAIL,
        previous_record=historical,
        unresolved=("https://example.com/a", "https://example.com/b"),
    )
    current["criterion_id"] = ""
    integrity = verification_result_integrity(current)
    decision = strict_regression_reopen_decision(historical, current)
    assert integrity["valid"] is False
    assert integrity["reason"] == "verification_result_identity_missing"
    assert decision["should_reopen"] is False
    assert decision["current_verification_state"] == COULD_NOT_VERIFY


def test_changed_fingerprint_never_reopens_even_with_valid_fail():
    historical = previous()
    current = result(
        FAIL,
        previous_record=historical,
        unresolved=("https://example.com/a", "https://example.com/b"),
    )
    current["repair_fingerprint"] = "different-fingerprint"
    decision = strict_regression_reopen_decision(historical, current)
    assert decision["should_reopen"] is False
    assert decision["reason"] == "regression_not_proven:repair_identity_missing_or_changed"


def test_foreign_criterion_id_never_reopens_even_when_structure_is_valid():
    historical = previous()
    current = result(
        FAIL,
        previous_record=historical,
        unresolved=("https://example.com/a", "https://example.com/b"),
    )
    current["criterion_id"] = "foreign-criterion"
    integrity = verification_result_integrity(current)
    binding = verification_result_historical_binding(historical, current)
    decision = strict_regression_reopen_decision(historical, current)
    assert integrity["valid"] is True
    assert binding["valid"] is False
    assert binding["reason"] == "acceptance_criterion_identity_mismatch"
    assert decision["should_reopen"] is False
    assert decision["reason"] == "regression_not_proven:acceptance_criterion_identity_mismatch"


def test_conflicting_historical_stored_fingerprint_fails_closed():
    historical = previous()
    current = result(
        FAIL,
        previous_record=historical,
        unresolved=("https://example.com/a", "https://example.com/b"),
    )
    historical["repair_fingerprint"] = "forged-stored-fingerprint"
    binding = verification_result_historical_binding(historical, current)
    decision = strict_regression_reopen_decision(historical, current)
    assert binding["valid"] is False
    assert binding["reason"] == "historical_stored_repair_fingerprint_mismatch"
    assert decision["should_reopen"] is False


def test_historical_rule_version_drift_invalidates_old_result_binding():
    historical = previous()
    current = result(
        FAIL,
        previous_record=historical,
        unresolved=("https://example.com/a", "https://example.com/b"),
    )
    historical["rule_definition_version"] = "rule-v2"
    binding = verification_result_historical_binding(historical, current)
    decision = strict_regression_reopen_decision(historical, current)
    assert binding["valid"] is False
    assert binding["reason"] == "acceptance_criterion_identity_mismatch"
    assert decision["should_reopen"] is False


def test_malformed_nested_historical_identity_claim_fails_closed():
    historical = previous()
    current = result(
        FAIL,
        previous_record=historical,
        unresolved=("https://example.com/a", "https://example.com/b"),
    )
    historical["repair_identity"] = "not-an-object"
    binding = verification_result_historical_binding(historical, current)
    decision = strict_regression_reopen_decision(historical, current)
    assert binding["valid"] is False
    assert binding["reason"] == "historical_repair_identity_claim_malformed"
    assert decision["should_reopen"] is False


def test_complete_foreign_scope_fails_historical_population_binding():
    historical = previous()
    current = result(
        FAIL,
        previous_record=historical,
        unresolved=("https://example.com/c", "https://example.com/d"),
    )
    assert verification_result_integrity(current)["valid"] is True
    binding = verification_result_historical_binding(historical, current)
    decision = strict_regression_reopen_decision(historical, current)
    assert binding["valid"] is False
    assert binding["reason"] == "verification_scope_not_bound_to_historical_evidence_population"
    assert decision["should_reopen"] is False
    assert decision["current_verification_state"] == COULD_NOT_VERIFY


def test_structurally_complete_subset_count_fails_historical_population_binding():
    historical = previous()
    current = result(
        FAIL,
        previous_record=historical,
        unresolved=("https://example.com/a",),
        required=1,
        observed=1,
        evaluated=1,
    )
    assert verification_result_integrity(current)["valid"] is True
    binding = verification_result_historical_binding(historical, current)
    decision = strict_regression_reopen_decision(historical, current)
    assert binding["valid"] is False
    assert binding["reason"] == "historical_evidence_population_count_mismatch"
    assert decision["should_reopen"] is False


def test_relative_historical_population_requires_authoritative_origin_for_binding():
    historical = previous()
    historical["affected_pages"] = ["/a", "/b"]
    current = result(
        FAIL,
        previous_record=historical,
        unresolved=("https://example.com/a", "https://example.com/b"),
    )
    without_origin = verification_result_historical_binding(historical, current)
    with_origin = verification_result_historical_binding(
        historical,
        current,
        previous_scan_origin="https://example.com",
    )
    decision = strict_regression_reopen_decision(
        historical,
        current,
        previous_scan_origin="https://example.com",
    )
    assert without_origin["valid"] is False
    assert without_origin["reason"] == "historical_evidence_identity_ambiguous_or_unresolvable"
    assert with_origin["valid"] is True
    assert decision["should_reopen"] is True


def test_missing_historical_population_cannot_reopen_proving_result():
    historical = previous()
    historical.pop("affected_pages")
    current = result(
        FAIL,
        previous_record=historical,
        unresolved=("https://example.com/a", "https://example.com/b"),
    )
    binding = verification_result_historical_binding(historical, current)
    decision = strict_regression_reopen_decision(historical, current)
    assert binding["valid"] is False
    assert binding["reason"] == "historical_evidence_population_missing"
    assert decision["should_reopen"] is False
    assert decision["current_verification_state"] == COULD_NOT_VERIFY
