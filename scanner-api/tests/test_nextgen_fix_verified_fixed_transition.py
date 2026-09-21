from app.nextgen_fix_verification import PARTIAL, PASS, VERIFICATION_RESULT_VERSION
from app.nextgen_fix_verified_fixed_transition import (
    STRICT_VERIFIED_FIXED_TRANSITION_VERSION,
    strict_verified_fixed_transition_decision,
)
from app.repair_identity import REPAIR_VERIFICATION_VERSION

FINGERPRINT = "repair-fingerprint-123"
CRITERION = "criterion-123"


def result(
    state=PASS,
    *,
    resolved=("https://example.com/a", "https://example.com/b"),
    unresolved=(),
    required=2,
    observed=2,
    evaluated=2,
    unverifiable=(),
):
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


def previous(fingerprint=FINGERPRINT):
    return {
        "repair_fingerprint": fingerprint,
        "verification_state": "verified_fixed",
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


def test_strict_transition_allows_only_dual_complete_proof():
    decision = strict_verified_fixed_transition_decision(previous(), result(), legacy())
    assert decision["version"] == STRICT_VERIFIED_FIXED_TRANSITION_VERSION
    assert decision["allowed"] is True
    assert decision["reason"] == "nextgen_pass_and_legacy_verified_fixed"


def test_malformed_pass_is_rejected():
    current = result(resolved=("https://example.com/a",), required=2)
    decision = strict_verified_fixed_transition_decision(previous(), current, legacy())
    assert decision["allowed"] is False
    assert decision["reason"].startswith("nextgen_result_not_proven:")


def test_non_pass_result_is_rejected_even_with_legacy_verified_fixed():
    current = result(
        PARTIAL,
        resolved=("https://example.com/a",),
        unresolved=("https://example.com/b",),
    )
    decision = strict_verified_fixed_transition_decision(previous(), current, legacy())
    assert decision["allowed"] is False
    assert decision["reason"] == "nextgen_result_is_not_pass"


def test_unsupported_legacy_version_is_rejected():
    decision = strict_verified_fixed_transition_decision(
        previous(),
        result(),
        legacy(version="old-version"),
    )
    assert decision["allowed"] is False
    assert decision["reason"] == "legacy_comparison_not_proven:unsupported_legacy_verification_version"


def test_legacy_non_verified_state_is_rejected():
    decision = strict_verified_fixed_transition_decision(
        previous(),
        result(),
        legacy(state="could_not_verify"),
    )
    assert decision["allowed"] is False
    assert decision["reason"] == "legacy_comparison_not_proven:legacy_comparison_not_verified_fixed"


def test_changed_repair_identity_is_rejected():
    decision = strict_verified_fixed_transition_decision(
        previous("different-fingerprint"),
        result(),
        legacy(),
    )
    assert decision["allowed"] is False
    assert decision["reason"] == "repair_identity_missing_or_changed"


def test_cross_contract_population_mismatch_is_rejected():
    decision = strict_verified_fixed_transition_decision(
        previous(),
        result(),
        legacy(previous_affected_pages=3, rechecked_pages=3, eligible_rechecked_pages=3),
    )
    assert decision["allowed"] is False
    assert decision["reason"] == "verification_population_mismatch"


def test_boolean_legacy_counts_are_rejected():
    decision = strict_verified_fixed_transition_decision(
        previous(),
        result(),
        legacy(rechecked_pages=True),
    )
    assert decision["allowed"] is False
    assert decision["reason"] == "legacy_comparison_not_proven:legacy_comparison_population_counts_invalid"


def test_noncomparable_legacy_contract_is_rejected():
    decision = strict_verified_fixed_transition_decision(
        previous(),
        result(),
        legacy(comparison_contract_state="incomparable"),
    )
    assert decision["allowed"] is False
    assert decision["reason"] == "legacy_comparison_not_proven:legacy_comparison_contract_not_comparable"
