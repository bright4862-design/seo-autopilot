from app.access_compatibility_policy import (
    ACCESS_STRATEGY_POLICY_VERSION,
    assess_access,
)


def test_403_does_not_claim_identity_sensitivity_without_controlled_comparison():
    result = assess_access(
        robots_allowed=True,
        http_status=403,
        owner_managed=True,
    )

    assert result.failure_kind == "http_access_denied"
    assert result.identity_sensitivity == "unproven"
    assert result.owner_action == "manual_review"
    assert result.policy_version == ACCESS_STRATEGY_POLICY_VERSION


def test_robots_restriction_outranks_http_denial():
    result = assess_access(
        robots_allowed=False,
        http_status=403,
        owner_managed=True,
    )

    assert result.failure_kind == "robots_restricted"
    assert result.owner_action == "none"


def test_429_is_rate_limited_not_generic_access_denial():
    result = assess_access(
        robots_allowed=True,
        http_status=429,
        owner_managed=True,
    )

    assert result.failure_kind == "rate_limited"
    assert result.owner_action == "manual_review"


def test_transport_failure_is_separate_from_http_denial():
    result = assess_access(
        robots_allowed=True,
        transport_error_class="tls_handshake_failed",
        failure_stage="tls_handshake",
        owner_managed=True,
    )

    assert result.failure_kind == "transport_blocked"
    assert result.identity_sensitivity == "unproven"


def test_contradictory_http_success_and_transport_failure_remains_unknown():
    result = assess_access(
        robots_allowed=True,
        http_status=200,
        transport_error_class="tls_handshake_failed",
        failure_stage="tls_handshake",
        owner_managed=True,
    )

    assert result.failure_kind == "unknown_access_failure"
    assert result.identity_sensitivity == "unproven"
    assert result.owner_action == "manual_review"
    assert result.access_strategy == "diagnostic_only"


def test_identity_sensitivity_requires_exact_controlled_comparison_result():
    unproven = assess_access(
        robots_allowed=True,
        http_status=403,
        identity_comparison_result="inconclusive",
        owner_managed=True,
    )
    proven = assess_access(
        robots_allowed=True,
        http_status=403,
        identity_comparison_result="fixlist_denied_control_allowed",
        owner_managed=True,
    )

    assert unproven.identity_sensitivity == "unproven"
    assert proven.identity_sensitivity == "proven"


def test_identity_proof_requires_matching_http_denial_and_confirmed_robots_allow():
    contradictory = assess_access(
        robots_allowed=True,
        http_status=200,
        identity_comparison_result="fixlist_denied_control_allowed",
        owner_managed=True,
    )
    robots_unknown = assess_access(
        robots_allowed=None,
        http_status=403,
        identity_comparison_result="fixlist_denied_control_allowed",
        owner_managed=True,
    )
    valid = assess_access(
        robots_allowed=True,
        http_status=403,
        identity_comparison_result="fixlist_denied_control_allowed",
        owner_managed=True,
    )

    assert contradictory.identity_sensitivity == "unproven"
    assert robots_unknown.identity_sensitivity == "unproven"
    assert valid.identity_sensitivity == "proven"


def test_owner_exception_requires_explicit_supported_capability():
    result = assess_access(
        robots_allowed=True,
        http_status=403,
        owner_managed=True,
        owner_exception_capability="supported",
    )

    assert result.owner_action == "owner_exception_possible"
    assert result.access_strategy == "owner_allowlist_candidate"


def test_owner_exception_stays_manual_when_robots_state_is_unknown():
    result = assess_access(
        robots_allowed=None,
        http_status=403,
        owner_managed=True,
        owner_exception_capability="supported",
    )

    assert result.failure_kind == "http_access_denied"
    assert result.owner_action == "manual_review"
    assert result.access_strategy == "diagnostic_only"


def test_plan_limited_owner_exception_stays_distinct():
    result = assess_access(
        robots_allowed=True,
        http_status=403,
        owner_managed=True,
        owner_exception_capability="plan_limited",
    )

    assert result.owner_action == "owner_exception_plan_limited"
    assert result.access_strategy == "owner_allowlist_plan_limited"


def test_verified_bot_candidate_requires_confirmed_robots_compliance():
    unknown = assess_access(
        robots_allowed=None,
        http_status=403,
        owner_managed=True,
        owner_exception_capability="verified_bot",
    )
    allowed = assess_access(
        robots_allowed=True,
        http_status=403,
        owner_managed=True,
        owner_exception_capability="verified_bot",
    )

    assert unknown.owner_action == "manual_review"
    assert unknown.access_strategy == "diagnostic_only"
    assert allowed.owner_action == "verified_bot_candidate"
    assert allowed.access_strategy == "verified_bot_candidate"


def test_non_owner_never_gets_owner_side_exception_action():
    result = assess_access(
        robots_allowed=True,
        http_status=403,
        owner_managed=False,
        owner_exception_capability="supported",
    )

    assert result.owner_action == "none"
    assert result.access_strategy == "diagnostic_only"


def test_successful_standard_access_is_not_a_compatibility_failure():
    result = assess_access(
        robots_allowed=True,
        http_status=200,
        owner_managed=True,
    )

    assert result.failure_kind == "standard_access"
    assert result.owner_action == "none"
    assert result.access_strategy == "standard_pinned_http"


def test_audit_record_is_bounded_and_contains_no_raw_request_material():
    result = assess_access(
        robots_allowed=True,
        http_status=403,
        owner_managed=True,
        owner_exception_capability="supported",
        identity_comparison_result="fixlist_denied_control_allowed",
    )

    assert result.as_audit_record() == {
        "access_strategy_policy_version": "access_strategy_policy_v1",
        "failure_kind": "http_access_denied",
        "identity_sensitivity": "proven",
        "owner_action": "owner_exception_possible",
        "access_strategy": "owner_allowlist_candidate",
    }
