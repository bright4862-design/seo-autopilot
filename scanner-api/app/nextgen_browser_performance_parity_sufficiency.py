"""Pure sufficiency assessment for Lane-C resolved raw/rendered parity evidence.

This module performs no rendering, network I/O, persistence, scoring, or execution
budget decisions. It distinguishes positive evidence of a material raw/rendered
delta from a claim that critical content matched: a delta can be established by
one contract-valid changed field, while a matched claim requires bilateral
observation of every baseline critical field.
"""
from __future__ import annotations

from typing import Any

from app.nextgen_browser_performance_parity_hardening import (
    RESOLVED_CRITICAL_PARITY_INTEGRITY_VERSION,
    RESOLVED_CRITICAL_PARITY_VERSION,
    validate_resolved_critical_parity_contract,
)

PARITY_SUFFICIENCY_VERSION = "nextgen_critical_parity_sufficiency_v1"
PARITY_SUFFICIENCY_INTEGRITY_VERSION = (
    "nextgen_critical_parity_sufficiency_integrity_v1"
)
PARITY_SUFFICIENCY_KIND = "critical_content_parity_sufficiency"
PARITY_SUFFICIENCY_STATES = {"verified_match", "verified_delta", "not_verified"}
BASELINE_REQUIRED_FIELDS = (
    "title",
    "h1",
    "canonical",
    "indexability",
    "main_content_present",
    "important_links",
)


def _source_value(evidence: Any, key: str) -> Any:
    return evidence.get(key) if isinstance(evidence, dict) else None


def _artifact(
    *,
    state: str,
    reason: str,
    parity: Any,
    verified_fields: list[str],
    changed_fields: list[str],
    missing_required_fields: list[str],
    material_delta: bool | None,
    source_contract_reasons: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "version": PARITY_SUFFICIENCY_VERSION,
        "evidence_kind": PARITY_SUFFICIENCY_KIND,
        "state": state,
        "reason": reason,
        "source_version": _source_value(parity, "version"),
        "source_integrity_version": RESOLVED_CRITICAL_PARITY_INTEGRITY_VERSION,
        "source_state": _source_value(parity, "state"),
        "source_url": _source_value(parity, "url"),
        "required_fields": list(BASELINE_REQUIRED_FIELDS),
        "verified_fields": verified_fields,
        "changed_fields": changed_fields,
        "missing_required_fields": missing_required_fields,
        "material_delta": material_delta,
        "source_contract_reasons": source_contract_reasons or [],
    }


def assess_critical_parity_sufficiency(parity: Any) -> dict[str, Any]:
    """Assess whether a resolved parity row is sufficient for match/delta semantics.

    A contract-valid material delta is positive evidence and therefore remains
    conclusive even when other critical fields were not observed. In contrast,
    a no-delta/matched conclusion is accepted only when every baseline field was
    bilaterally observed. This prevents one-field matches from becoming evidence
    that raw and rendered critical content broadly agree.
    """
    contract = validate_resolved_critical_parity_contract(parity)
    if not contract.get("valid"):
        return _artifact(
            state="not_verified",
            reason="source_contract_invalid",
            parity=parity,
            verified_fields=[],
            changed_fields=[],
            missing_required_fields=list(BASELINE_REQUIRED_FIELDS),
            material_delta=None,
            source_contract_reasons=sorted(contract.get("reasons", [])),
        )

    verified_fields = sorted(parity.get("verified_fields", []))
    changed_fields = sorted(parity.get("changed_fields", []))
    verified = set(verified_fields)
    missing = [field for field in BASELINE_REQUIRED_FIELDS if field not in verified]
    source_state = parity.get("state")

    if source_state == "material_delta":
        return _artifact(
            state="verified_delta",
            reason="material_delta_observed",
            parity=parity,
            verified_fields=verified_fields,
            changed_fields=changed_fields,
            missing_required_fields=missing,
            material_delta=True,
        )

    if source_state == "matched" and not missing:
        return _artifact(
            state="verified_match",
            reason="matched_required_fields_complete",
            parity=parity,
            verified_fields=verified_fields,
            changed_fields=changed_fields,
            missing_required_fields=[],
            material_delta=False,
        )

    if source_state == "matched":
        reason = "matched_required_fields_incomplete"
    else:
        reason = "source_not_verified"
    return _artifact(
        state="not_verified",
        reason=reason,
        parity=parity,
        verified_fields=verified_fields,
        changed_fields=changed_fields,
        missing_required_fields=missing,
        material_delta=None,
    )


def validate_critical_parity_sufficiency(
    parity: Any,
    assessment: Any,
) -> dict[str, Any]:
    """Bind a sufficiency assessment to the exact contract-valid parity source."""
    reasons: list[str] = []
    if not isinstance(assessment, dict):
        return {
            "version": PARITY_SUFFICIENCY_INTEGRITY_VERSION,
            "valid": False,
            "reasons": ["assessment_not_object"],
        }

    expected = assess_critical_parity_sufficiency(parity)
    if assessment.get("version") != PARITY_SUFFICIENCY_VERSION:
        reasons.append("version_mismatch")
    if assessment.get("evidence_kind") != PARITY_SUFFICIENCY_KIND:
        reasons.append("evidence_kind_mismatch")
    if assessment.get("state") not in PARITY_SUFFICIENCY_STATES:
        reasons.append("state_invalid")
    allow_untrusted_source_version = (
        assessment.get("state") == "not_verified"
        and assessment.get("reason") == "source_contract_invalid"
    )
    if (
        assessment.get("source_version") not in {RESOLVED_CRITICAL_PARITY_VERSION, None}
        and not allow_untrusted_source_version
    ):
        reasons.append("source_version_invalid")
    if assessment.get("source_integrity_version") != RESOLVED_CRITICAL_PARITY_INTEGRITY_VERSION:
        reasons.append("source_integrity_version_mismatch")
    if assessment != expected:
        reasons.append("assessment_source_mismatch")

    return {
        "version": PARITY_SUFFICIENCY_INTEGRITY_VERSION,
        "valid": not reasons,
        "reasons": sorted(set(reasons)),
    }
