from app.nextgen_fix_verification import (
    PARTIAL,
    PASS,
    VERIFICATION_RESULT_VERSION,
    build_acceptance_criterion,
)
from app.nextgen_fix_verified_fixed_transition import (
    STRICT_VERIFIED_FIXED_TRANSITION_VERSION,
    strict_verified_fixed_transition_decision,
)
from app.repair_coverage import PUBLISHED_EVIDENCE_URL_IDENTITY_VERSION
from app.repair_identity import REPAIR_VERIFICATION_VERSION


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


def test_strict_transition_allows_only_dual_complete_bound_proof():
    historical = previous()
    decision = strict_verified_fixed_transition_decision(
        historical,
        result(historical),
        legacy(),
    )
    assert decision["version"] == STRICT_VERIFIED_FIXED_TRANSITION_VERSION
    assert decision["allowed"] is True
    assert decision["reason"] == "nextgen_pass_and_legacy_verified_fixed"
    assert decision["result_binding"]["valid"] is True
    assert decision["result_binding"]["historical_population_count"] == 2


def test_malformed_pass_is_rejected():
    historical = previous()
    current = result(
        historical,
        resolved=("https://example.com/a",),
        required=2,
    )
    decision = strict_verified_fixed_transition_decision(historical, current, legacy())
    assert decision["allowed"] is False
    assert decision["reason"].startswith("nextgen_result_not_bound:result_integrity_invalid:")


def test_non_pass_result_is_rejected_even_with_legacy_verified_fixed():
    historical = previous()
    current = result(
        historical,
        PARTIAL,
        resolved=("https://example.com/a",),
        unresolved=("https://example.com/b",),
    )
    decision = strict_verified_fixed_transition_decision(historical, current, legacy())
    assert decision["allowed"] is False
    assert decision["reason"] == "nextgen_result_is_not_pass"


def test_unsupported_legacy_version_is_rejected():
    historical = previous()
    decision = strict_verified_fixed_transition_decision(
        historical,
        result(historical),
        legacy(version="old-version"),
    )
    assert decision["allowed"] is False
    assert decision["reason"] == "legacy_comparison_not_proven:unsupported_legacy_verification_version"


def test_legacy_non_verified_state_is_rejected():
    historical = previous()
    decision = strict_verified_fixed_transition_decision(
        historical,
        result(historical),
        legacy(state="could_not_verify"),
    )
    assert decision["allowed"] is False
    assert decision["reason"] == "legacy_comparison_not_proven:legacy_comparison_not_verified_fixed"


def test_changed_repair_identity_is_rejected():
    historical = previous()
    current = result(historical)
    historical["remediation_family"] = "different-action"
    historical.pop("repair_fingerprint", None)
    historical.pop("repair_identity", None)
    decision = strict_verified_fixed_transition_decision(
        historical,
        current,
        legacy(),
    )
    assert decision["allowed"] is False
    assert decision["reason"] == "nextgen_result_not_bound:repair_identity_missing_or_changed"


def test_cross_contract_population_mismatch_is_rejected():
    historical = previous()
    decision = strict_verified_fixed_transition_decision(
        historical,
        result(historical),
        legacy(
            previous_affected_pages=3,
            rechecked_pages=3,
            eligible_rechecked_pages=3,
        ),
    )
    assert decision["allowed"] is False
    assert decision["reason"] == "verification_population_mismatch"


def test_boolean_legacy_counts_are_rejected():
    historical = previous()
    decision = strict_verified_fixed_transition_decision(
        historical,
        result(historical),
        legacy(rechecked_pages=True),
    )
    assert decision["allowed"] is False
    assert decision["reason"] == "legacy_comparison_not_proven:legacy_comparison_population_counts_invalid"


def test_noncomparable_legacy_contract_is_rejected():
    historical = previous()
    decision = strict_verified_fixed_transition_decision(
        historical,
        result(historical),
        legacy(comparison_contract_state="incomparable"),
    )
    assert decision["allowed"] is False
    assert decision["reason"] == "legacy_comparison_not_proven:legacy_comparison_contract_not_comparable"


def test_foreign_criterion_id_is_rejected_even_when_pass_shape_is_complete():
    historical = previous()
    current = result(historical)
    current["criterion_id"] = "foreign-criterion"
    decision = strict_verified_fixed_transition_decision(historical, current, legacy())
    assert decision["allowed"] is False
    assert decision["reason"] == "nextgen_result_not_bound:acceptance_criterion_identity_mismatch"


def test_conflicting_historical_stored_fingerprint_is_rejected():
    historical = previous()
    current = result(historical)
    historical["repair_fingerprint"] = "forged-stored-fingerprint"
    decision = strict_verified_fixed_transition_decision(historical, current, legacy())
    assert decision["allowed"] is False
    assert decision["reason"] == "nextgen_result_not_bound:historical_stored_repair_fingerprint_mismatch"


def test_historical_rule_version_drift_invalidates_old_pass_binding():
    historical = previous()
    current = result(historical)
    historical["rule_definition_version"] = "rule-v2"
    decision = strict_verified_fixed_transition_decision(historical, current, legacy())
    assert decision["allowed"] is False
    assert decision["reason"] == "nextgen_result_not_bound:acceptance_criterion_identity_mismatch"


def test_nested_historical_identity_version_mismatch_is_rejected():
    historical = previous()
    current = result(historical)
    historical["repair_identity"]["version"] = "repair_identity_v0"
    decision = strict_verified_fixed_transition_decision(historical, current, legacy())
    assert decision["allowed"] is False
    assert decision["reason"] == "nextgen_result_not_bound:historical_nested_repair_identity_version_mismatch"


def test_foreign_scope_pass_is_rejected_even_when_shape_is_complete():
    historical = previous()
    current = result(
        historical,
        resolved=("https://example.com/c", "https://example.com/d"),
    )
    decision = strict_verified_fixed_transition_decision(historical, current, legacy())
    assert decision["allowed"] is False
    assert decision["reason"] == "nextgen_result_not_bound:verification_scope_not_bound_to_historical_evidence_population"


def test_forged_subset_pass_and_matching_legacy_counts_are_rejected():
    historical = previous()
    current = result(
        historical,
        resolved=("https://example.com/a",),
        required=1,
        observed=1,
        evaluated=1,
    )
    decision = strict_verified_fixed_transition_decision(
        historical,
        current,
        legacy(previous_affected_pages=1, rechecked_pages=1, eligible_rechecked_pages=1),
    )
    assert decision["allowed"] is False
    assert decision["reason"] == "nextgen_result_not_bound:historical_evidence_population_count_mismatch"


def test_legacy_compatible_is_rejected_for_versioned_nextgen_transition():
    historical = previous()
    decision = strict_verified_fixed_transition_decision(
        historical,
        result(historical),
        legacy(comparison_contract_state="legacy_compatible"),
    )
    assert decision["allowed"] is False
    assert decision["reason"] == "legacy_comparison_not_proven:legacy_comparison_not_versioned_compatible"
