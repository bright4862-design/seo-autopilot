from copy import deepcopy

from app.nextgen_fix_verification import (
    COULD_NOT_VERIFY,
    FAIL,
    PASS,
    VERIFICATION_RESULT_VERSION,
    build_acceptance_criterion,
)
from app.nextgen_fix_verification_result_transport import (
    LEGACY_COMPARISON_TRANSPORT_INTEGRITY_VERSION,
    RESULT_TRANSPORT_INTEGRITY_VERSION,
    STRICT_REGRESSION_REOPEN_RESULT_TRANSPORT_VERSION,
    STRICT_VERIFIED_FIXED_RESULT_TRANSPORT_VERSION,
    legacy_verified_fixed_transport_integrity,
    strict_regression_reopen_from_exact_result_transport,
    strict_verified_fixed_transition_from_exact_result_transport,
    verification_result_transport_integrity,
)
from app.repair_coverage import PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION
from app.repair_identity import REPAIR_VERIFICATION_VERSION


def previous(**overrides):
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
    record.update(overrides)
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
    historical,
    state=PASS,
    *,
    resolved=("https://example.com/a", "https://example.com/b"),
    unresolved=(),
    required=2,
    observed=2,
    evaluated=2,
    unverifiable=(),
):
    criterion = build_acceptance_criterion(historical)
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


def legacy(**overrides):
    base = {
        "version": REPAIR_VERIFICATION_VERSION,
        "state": "verified_fixed",
        "rechecked_pages": 2,
        "eligible_rechecked_pages": 2,
        "previous_affected_pages": 2,
        "comparison_contract_state": "compatible",
    }
    base.update(overrides)
    return base


def test_exact_pass_transport_is_proving_and_does_not_mutate_input():
    historical = previous()
    current = result(historical)
    before = deepcopy(current)
    integrity = verification_result_transport_integrity(current)
    assert integrity["version"] == RESULT_TRANSPORT_INTEGRITY_VERSION
    assert integrity["valid"] is True
    assert integrity["proving"] is True
    assert integrity["effective_state"] == PASS
    assert current == before


def test_whitespace_normalized_terminal_state_is_not_proof():
    historical = previous()
    current = result(historical)
    current["state"] = " PASS "
    integrity = verification_result_transport_integrity(current)
    assert integrity["valid"] is False
    assert integrity["effective_state"] == COULD_NOT_VERIFY
    assert integrity["reason"] == "verification_result_state_not_exact_supported_value"


def test_lowercase_terminal_state_is_not_proof():
    historical = previous()
    current = result(historical)
    current["state"] = "pass"
    integrity = verification_result_transport_integrity(current)
    assert integrity["valid"] is False
    assert integrity["effective_state"] == COULD_NOT_VERIFY


def test_whitespace_normalized_result_identity_is_not_proof():
    historical = previous()
    current = result(historical)
    current["criterion_id"] = f" {current['criterion_id']} "
    integrity = verification_result_transport_integrity(current)
    assert integrity["valid"] is False
    assert integrity["reason"] == "verification_result_criterion_id_not_exact_nonempty_string"


def test_boolean_population_count_is_not_exact_result_transport():
    historical = previous()
    current = result(historical)
    current["observed_population_count"] = True
    integrity = verification_result_transport_integrity(current)
    assert integrity["valid"] is False
    assert integrity["reason"] == "verification_result_observed_population_count_not_strict_nonnegative_integer"


def test_duplicate_scope_identity_is_not_exact_result_transport():
    historical = previous()
    current = result(
        historical,
        resolved=("https://example.com/a", "https://example.com/a"),
    )
    integrity = verification_result_transport_integrity(current)
    assert integrity["valid"] is False
    assert integrity["reason"] == "resolved_scope_contains_duplicate_identity"


def test_malformed_unverifiable_evidence_identity_is_rejected():
    historical = previous()
    current = result(
        historical,
        COULD_NOT_VERIFY,
        resolved=(),
        required=2,
        observed=1,
        evaluated=1,
        unverifiable=(
            {
                "evidence_key": " https://example.com/b ",
                "reason": "required_page_not_observed",
            },
        ),
    )
    integrity = verification_result_transport_integrity(current)
    assert integrity["valid"] is False
    assert integrity["reason"] == "unverifiable_scope_0_evidence_key_not_exact_nonempty_string"


def test_exact_could_not_verify_transport_is_valid_but_nonproving():
    historical = previous()
    current = result(
        historical,
        COULD_NOT_VERIFY,
        resolved=(),
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
    integrity = verification_result_transport_integrity(current)
    assert integrity["valid"] is True
    assert integrity["proving"] is False
    assert integrity["effective_state"] == COULD_NOT_VERIFY


def test_exact_legacy_verified_fixed_transport_is_valid():
    integrity = legacy_verified_fixed_transport_integrity(legacy())
    assert integrity["version"] == LEGACY_COMPARISON_TRANSPORT_INTEGRITY_VERSION
    assert integrity["valid"] is True


def test_whitespace_legacy_state_cannot_become_verified_fixed_proof():
    integrity = legacy_verified_fixed_transport_integrity(
        legacy(state=" verified_fixed ")
    )
    assert integrity["valid"] is False
    assert integrity["reason"] == "legacy_comparison_state_not_exact_verified_fixed"


def test_whitespace_legacy_contract_state_cannot_become_comparable_proof():
    integrity = legacy_verified_fixed_transport_integrity(
        legacy(comparison_contract_state=" compatible ")
    )
    assert integrity["valid"] is False
    assert integrity["reason"] == "legacy_comparison_contract_state_not_exact_compatible"


def test_strict_verified_fixed_transport_wrapper_allows_exact_dual_proof():
    historical = previous()
    decision = strict_verified_fixed_transition_from_exact_result_transport(
        historical,
        result(historical),
        legacy(),
    )
    assert decision["version"] == STRICT_VERIFIED_FIXED_RESULT_TRANSPORT_VERSION
    assert decision["allowed"] is True
    assert decision["result_transport_integrity"]["valid"] is True
    assert decision["legacy_comparison_transport_integrity"]["valid"] is True
    assert decision["inner_verified_fixed_transition_version"]


def test_strict_verified_fixed_transport_wrapper_rejects_normalized_result_state():
    historical = previous()
    current = result(historical)
    current["state"] = " PASS "
    decision = strict_verified_fixed_transition_from_exact_result_transport(
        historical,
        current,
        legacy(),
    )
    assert decision["allowed"] is False
    assert decision["reason"] == "verification_result_transport_integrity_failed"


def test_strict_verified_fixed_transport_wrapper_rejects_normalized_legacy_state():
    historical = previous()
    decision = strict_verified_fixed_transition_from_exact_result_transport(
        historical,
        result(historical),
        legacy(state=" verified_fixed "),
    )
    assert decision["allowed"] is False
    assert decision["reason"] == "legacy_comparison_transport_integrity_failed"


def test_strict_regression_transport_wrapper_reopens_exact_fail():
    historical = previous()
    current = result(
        historical,
        FAIL,
        resolved=(),
        unresolved=("https://example.com/a", "https://example.com/b"),
    )
    decision = strict_regression_reopen_from_exact_result_transport(
        historical,
        current,
    )
    assert decision["version"] == STRICT_REGRESSION_REOPEN_RESULT_TRANSPORT_VERSION
    assert decision["should_reopen"] is True
    assert decision["current_verification_state"] == FAIL
    assert decision["result_transport_integrity"]["valid"] is True
    assert decision["historical_resolution_state_integrity"]["valid"] is True
    assert decision["inner_regression_reopen_version"]


def test_strict_regression_transport_wrapper_rejects_conflicting_historical_state_aliases():
    historical = previous(status="open")
    current = result(
        historical,
        FAIL,
        resolved=(),
        unresolved=("https://example.com/a", "https://example.com/b"),
    )
    decision = strict_regression_reopen_from_exact_result_transport(
        historical,
        current,
    )
    assert decision["should_reopen"] is False
    assert decision["current_verification_state"] == COULD_NOT_VERIFY
    assert decision["reason"] == "historical_resolution_state_integrity_failed"


def test_disappeared_required_url_remains_nonproof_at_result_transport_boundary():
    historical = previous()
    current = result(
        historical,
        COULD_NOT_VERIFY,
        resolved=(),
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
    decision = strict_regression_reopen_from_exact_result_transport(
        historical,
        current,
    )
    assert decision["should_reopen"] is False
    assert decision["current_verification_state"] == COULD_NOT_VERIFY
    assert decision["result_transport_integrity"]["proving"] is False
