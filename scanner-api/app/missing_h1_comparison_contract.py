from __future__ import annotations

from typing import Any

MISSING_H1_RULE = "missing_h1"
MISSING_H1_REPAIR_SURFACE = "document_primary_heading"
MISSING_H1_REMEDIATION_FAMILY = "add_semantic_h1"
MISSING_H1_RULE_DEFINITION_VERSION = "missing_h1_rule_v1_usable_html_h1_count_zero"
MISSING_H1_COMPARISON_PROFILE_VERSION = "missing_h1_comparison_v1_exact_affected_pages"
MISSING_H1_COMPARISON_EVIDENCE_VERSION = "scan_comparison_evidence_v1_missing_h1"


def missing_h1_contract_fields() -> dict[str, Any]:
    return {
        "repair_surface": MISSING_H1_REPAIR_SURFACE,
        "remediation_family": MISSING_H1_REMEDIATION_FAMILY,
        "rule_definition_version": MISSING_H1_RULE_DEFINITION_VERSION,
        "comparison_profile_version": MISSING_H1_COMPARISON_PROFILE_VERSION,
    }
