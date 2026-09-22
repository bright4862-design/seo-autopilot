"""Source binding for Lane-C raw/rendered critical-content parity evidence.

The resolved parity contract can prove internal shape and consistency, but a
structurally valid envelope still needs to be bound back to the exact raw and
rendered observations that produced it. This helper recomputes resolved parity
from caller-supplied source observations and requires all parity-owned fields to
match before a future integrator can trust the transported evidence.

This module is pure: it performs no rendering, network I/O, persistence,
customer scoring, execution-budget decisions, or provider calls.
"""
from __future__ import annotations

from typing import Any

from app.nextgen_browser_performance_parity_hardening import (
    RESOLVED_CRITICAL_PARITY_VERSION,
    compare_critical_content_parity_resolved,
    validate_resolved_critical_parity_contract,
)

PARITY_SOURCE_BINDING_VERSION = "nextgen_critical_parity_source_binding_v1"

_BOUND_FIELDS = (
    "version",
    "base_version",
    "canonical_resolution_version",
    "url",
    "rendered_url",
    "state",
    "reason",
    "material_delta",
    "verified_fields",
    "changed_fields",
    "fields",
)


def _result(
    *,
    valid: bool,
    reasons: list[str],
    expected: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "version": PARITY_SOURCE_BINDING_VERSION,
        "contract": RESOLVED_CRITICAL_PARITY_VERSION,
        "valid": valid,
        "reasons": sorted(set(reasons)),
        "expected_url": expected.get("url") if isinstance(expected, dict) else None,
        "expected_state": expected.get("state") if isinstance(expected, dict) else None,
    }


def validate_resolved_critical_parity_source_binding(
    raw_page: Any,
    rendered_page: Any,
    evidence: Any,
    *,
    render_state: str = "completed",
    render_reason: str | None = None,
) -> dict[str, Any]:
    """Bind resolved parity evidence to its exact raw/rendered source observations.

    The future serialized integrator must supply the same retained raw/rendered
    observations and render outcome that were used to create ``evidence``. The
    helper recomputes parity and compares every parity-owned field. Extra transport
    metadata is ignored so wrappers may attach non-authoritative context without
    changing the source binding.

    Failed/unavailable renders remain validly bindable only as ``not_verified``
    evidence. They can never be rebound into a matched or material-delta claim.
    """
    if not isinstance(evidence, dict):
        return _result(valid=False, reasons=["evidence_not_object"])

    contract = validate_resolved_critical_parity_contract(evidence)
    if not contract.get("valid"):
        return _result(
            valid=False,
            reasons=[
                f"evidence:{reason}"
                for reason in contract.get("reasons", [])
            ] or ["evidence_contract_invalid"],
        )

    expected = compare_critical_content_parity_resolved(
        raw_page,
        rendered_page,
        render_state=render_state,
        render_reason=render_reason,
    )
    expected_contract = validate_resolved_critical_parity_contract(expected)
    if not expected_contract.get("valid"):
        return _result(
            valid=False,
            reasons=[
                f"recomputed:{reason}"
                for reason in expected_contract.get("reasons", [])
            ] or ["recomputed_contract_invalid"],
            expected=expected,
        )

    reasons = [
        f"{field}_mismatch"
        for field in _BOUND_FIELDS
        if evidence.get(field) != expected.get(field)
    ]
    return _result(
        valid=not reasons,
        reasons=reasons,
        expected=expected,
    )
