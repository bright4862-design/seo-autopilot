from dataclasses import dataclass
from typing import Optional

ACCESS_STRATEGY_POLICY_VERSION = "access_strategy_policy_v1"


@dataclass(frozen=True)
class AccessAssessment:
    failure_kind: str
    identity_sensitivity: str
    owner_action: str
    access_strategy: str
    policy_version: str = ACCESS_STRATEGY_POLICY_VERSION

    def as_audit_record(self) -> dict[str, str]:
        return {
            "access_strategy_policy_version": self.policy_version,
            "failure_kind": self.failure_kind,
            "identity_sensitivity": self.identity_sensitivity,
            "owner_action": self.owner_action,
            "access_strategy": self.access_strategy,
        }


def _owner_action(
    *,
    owner_managed: bool,
    robots_allowed: Optional[bool],
    failure_kind: str,
    owner_exception_capability: str,
) -> tuple[str, str]:
    if failure_kind == "standard_access":
        return "none", "standard_pinned_http"
    if failure_kind == "robots_restricted":
        return "none", "diagnostic_only"
    if not owner_managed:
        return "none", "diagnostic_only"
    if failure_kind != "http_access_denied":
        return "manual_review", "diagnostic_only"
    if owner_exception_capability == "supported":
        return "owner_exception_possible", "owner_allowlist_candidate"
    if owner_exception_capability == "plan_limited":
        return "owner_exception_plan_limited", "owner_allowlist_plan_limited"
    if owner_exception_capability == "verified_bot" and robots_allowed is True:
        return "verified_bot_candidate", "verified_bot_candidate"
    return "manual_review", "diagnostic_only"


def assess_access(
    *,
    robots_allowed: Optional[bool],
    http_status: Optional[int] = None,
    owner_managed: bool = False,
    transport_error_class: Optional[str] = None,
    failure_stage: Optional[str] = None,
    identity_comparison_result: Optional[str] = None,
    owner_exception_capability: str = "unknown",
) -> AccessAssessment:
    if robots_allowed is False:
        failure_kind = "robots_restricted"
    elif http_status == 429:
        failure_kind = "rate_limited"
    elif http_status in {401, 403, 407}:
        failure_kind = "http_access_denied"
    elif transport_error_class and failure_stage in {
        "tcp_connect",
        "tls_handshake",
        "response_wait",
    }:
        failure_kind = "transport_blocked"
    elif http_status is not None and 200 <= http_status < 400:
        failure_kind = "standard_access"
    else:
        failure_kind = "unknown_access_failure"

    identity_sensitivity = (
        "proven"
        if (
            robots_allowed is True
            and failure_kind == "http_access_denied"
            and identity_comparison_result == "fixlist_denied_control_allowed"
        )
        else "unproven"
    )

    owner_action, access_strategy = _owner_action(
        owner_managed=owner_managed,
        robots_allowed=robots_allowed,
        failure_kind=failure_kind,
        owner_exception_capability=owner_exception_capability,
    )

    return AccessAssessment(
        failure_kind=failure_kind,
        identity_sensitivity=identity_sensitivity,
        owner_action=owner_action,
        access_strategy=access_strategy,
    )
