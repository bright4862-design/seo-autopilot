"""Raw-zone-bound template contextual-link opportunity evidence for NextGen Lane B.

This helper upgrades the existing template-bound contextual opportunity evidence with
raw observed template-to-template link-zone flow. It consumes only already-built
Lane-B evidence, performs no network/model work, creates no customer Fix, and never
turns missing assessed-sample flow into a sitewide absence claim.
"""
from __future__ import annotations

from typing import Any

from .semantic_graph import ZONE_WEIGHTS
from .semantic_graph_contextual import EVIDENCE_SCOPE
from .semantic_graph_template_opportunity import (
    TEMPLATE_CONTEXTUAL_OPPORTUNITY_VERSION,
)
from .semantic_graph_template_zone_flow import TEMPLATE_LINK_ZONE_FLOW_VERSION


RAW_ZONE_TEMPLATE_CONTEXTUAL_OPPORTUNITY_VERSION = (
    "template_contextual_internal_link_opportunity_v2_raw_zone_bound"
)


def _empty_result(reason: str) -> dict[str, Any]:
    return {
        "version": RAW_ZONE_TEMPLATE_CONTEXTUAL_OPPORTUNITY_VERSION,
        "scope": EVIDENCE_SCOPE,
        "state": "not_verified",
        "reason": reason,
        "template_contextual_opportunity_integrity_state": "not_verified",
        "template_zone_flow_integrity_state": "not_verified",
        "candidate_count": 0,
        "candidates": [],
        "candidates_truncated": False,
        "sitewide_link_absence_claim": False,
        "sitewide_template_flow_claim": False,
        "sitewide_link_distribution_claim": False,
        "customer_fix_created": False,
    }


def _strict_non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _validated_zone_counts(value: Any) -> dict[str, int] | None:
    if not isinstance(value, dict) or set(value) != set(ZONE_WEIGHTS):
        return None
    result: dict[str, int] = {}
    for zone in ZONE_WEIGHTS:
        count = _strict_non_negative_int(value.get(zone))
        if count is None:
            return None
        result[zone] = count
    return result


def _validated_template_contextual(
    evidence: dict[str, Any],
) -> tuple[list[dict[str, Any]], int, bool, str | None]:
    if (
        not isinstance(evidence, dict)
        or evidence.get("version") != TEMPLATE_CONTEXTUAL_OPPORTUNITY_VERSION
    ):
        return [], 0, False, "template_contextual_opportunity_version_mismatch"
    if evidence.get("scope") != EVIDENCE_SCOPE:
        return [], 0, False, "template_contextual_opportunity_scope_mismatch"
    if evidence.get("state") == "not_verified":
        return [], 0, False, "template_contextual_opportunity_not_verified"
    if evidence.get("template_integrity_state") != "verified":
        return [], 0, False, "template_contextual_template_not_verified"
    if evidence.get("graph_integrity_state") != "verified":
        return [], 0, False, "template_contextual_graph_not_verified"
    if evidence.get("contextual_opportunity_integrity_state") != "verified":
        return [], 0, False, "template_contextual_candidate_not_verified"
    if evidence.get("sitewide_link_absence_claim") is not False:
        return [], 0, False, "template_contextual_sitewide_link_claim_invalid"
    if evidence.get("sitewide_template_flow_claim") is not False:
        return [], 0, False, "template_contextual_sitewide_flow_claim_invalid"
    if evidence.get("customer_fix_created") is not False:
        return [], 0, False, "template_contextual_customer_fix_invalid"

    candidates = evidence.get("candidates")
    candidate_count = _strict_non_negative_int(evidence.get("candidate_count"))
    truncated = evidence.get("candidates_truncated")
    if not isinstance(candidates, list) or candidate_count is None or not isinstance(truncated, bool):
        return [], 0, False, "template_contextual_shape_invalid"
    if candidate_count < len(candidates):
        return [], 0, False, "template_contextual_count_invalid"
    if truncated != (candidate_count > len(candidates)):
        return [], 0, False, "template_contextual_truncation_mismatch"

    expected_state = "candidate" if candidates else "no_candidate_observed"
    if evidence.get("state") != expected_state:
        return [], 0, False, "template_contextual_state_mismatch"

    seen: set[tuple[str, str]] = set()
    validated: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            return [], 0, False, "template_contextual_candidate_invalid"
        source_group = str(candidate.get("source_group_id") or "").strip()
        target_group = str(candidate.get("target_group_id") or "").strip()
        source_url = str(candidate.get("source_url") or "").strip()
        target_url = str(candidate.get("target_url") or "").strip()
        key = (source_url, target_url)
        if not source_group or not target_group or not source_url or not target_url or source_url == target_url:
            return [], 0, False, "template_contextual_candidate_identity_invalid"
        if key in seen:
            return [], 0, False, "template_contextual_candidate_duplicate"
        seen.add(key)
        if candidate.get("cross_template") is not (source_group != target_group):
            return [], 0, False, "template_contextual_cross_template_mismatch"
        if not isinstance(candidate.get("observed_template_flow_present"), bool):
            return [], 0, False, "template_contextual_flow_presence_invalid"
        if candidate.get("sitewide_template_flow_claim") is not False:
            return [], 0, False, "template_contextual_candidate_sitewide_flow_claim_invalid"
        validated.append(candidate)
    return validated, candidate_count, truncated, None


def _validated_template_zone_flow(
    evidence: dict[str, Any],
) -> tuple[dict[tuple[str, str], dict[str, Any]], str | None]:
    if not isinstance(evidence, dict) or evidence.get("version") != TEMPLATE_LINK_ZONE_FLOW_VERSION:
        return {}, "template_zone_flow_version_mismatch"
    if evidence.get("scope") != EVIDENCE_SCOPE:
        return {}, "template_zone_flow_scope_mismatch"
    if evidence.get("state") != "verified":
        return {}, "template_zone_flow_not_verified"
    if evidence.get("template_integrity_state") != "verified":
        return {}, "template_zone_flow_template_not_verified"
    if evidence.get("graph_integrity_state") != "verified":
        return {}, "template_zone_flow_graph_not_verified"
    if evidence.get("raw_link_observation_integrity_state") != "verified":
        return {}, "template_zone_flow_raw_link_not_verified"
    if evidence.get("sitewide_template_flow_claim") is not False:
        return {}, "template_zone_flow_sitewide_flow_claim_invalid"
    if evidence.get("sitewide_link_distribution_claim") is not False:
        return {}, "template_zone_flow_sitewide_distribution_claim_invalid"
    if evidence.get("sitewide_link_absence_claim") is not False:
        return {}, "template_zone_flow_sitewide_link_claim_invalid"
    if evidence.get("customer_fix_created") is not False:
        return {}, "template_zone_flow_customer_fix_invalid"

    declared_flow_count = _strict_non_negative_int(evidence.get("observed_template_flow_count"))
    declared_edge_count = _strict_non_negative_int(evidence.get("observed_directed_edge_count"))
    declared_occurrence_count = _strict_non_negative_int(evidence.get("observed_link_occurrence_count"))
    flows = evidence.get("flows")
    if (
        declared_flow_count is None
        or declared_edge_count is None
        or declared_occurrence_count is None
        or not isinstance(flows, list)
        or declared_flow_count != len(flows)
    ):
        return {}, "template_zone_flow_shape_invalid"

    flow_index: dict[tuple[str, str], dict[str, Any]] = {}
    total_edges = 0
    total_occurrences = 0
    for flow in flows:
        if not isinstance(flow, dict):
            return {}, "template_zone_flow_row_invalid"
        source_group = str(flow.get("source_group_id") or "").strip()
        target_group = str(flow.get("target_group_id") or "").strip()
        key = (source_group, target_group)
        if not source_group or not target_group or key in flow_index:
            return {}, "template_zone_flow_identity_invalid"
        if flow.get("cross_template") is not (source_group != target_group):
            return {}, "template_zone_flow_cross_template_mismatch"

        occurrence_count = _strict_non_negative_int(flow.get("observed_link_occurrence_count"))
        edge_count = _strict_non_negative_int(flow.get("observed_directed_edge_count"))
        source_page_count = _strict_non_negative_int(flow.get("observed_source_page_count"))
        target_page_count = _strict_non_negative_int(flow.get("observed_target_page_count"))
        contextual_occurrences = _strict_non_negative_int(flow.get("contextual_occurrence_count"))
        contextual_edges = _strict_non_negative_int(flow.get("contextual_directed_edge_count"))
        mixed_edges = _strict_non_negative_int(flow.get("mixed_zone_directed_edge_count"))
        zone_counts = _validated_zone_counts(flow.get("zone_occurrence_counts"))
        strongest_counts = _validated_zone_counts(flow.get("strongest_zone_directed_edge_counts"))
        if (
            occurrence_count is None
            or edge_count is None
            or source_page_count is None
            or target_page_count is None
            or contextual_occurrences is None
            or contextual_edges is None
            or mixed_edges is None
            or zone_counts is None
            or strongest_counts is None
        ):
            return {}, "template_zone_flow_metrics_invalid"
        if sum(zone_counts.values()) != occurrence_count:
            return {}, "template_zone_flow_occurrence_count_mismatch"
        if sum(strongest_counts.values()) != edge_count:
            return {}, "template_zone_flow_edge_count_mismatch"
        if contextual_occurrences != zone_counts["contextual"]:
            return {}, "template_zone_flow_contextual_occurrence_mismatch"
        if contextual_edges > edge_count or mixed_edges > edge_count:
            return {}, "template_zone_flow_edge_metric_invalid"
        if contextual_edges > contextual_occurrences:
            return {}, "template_zone_flow_contextual_edge_occurrence_mismatch"
        if occurrence_count < edge_count:
            return {}, "template_zone_flow_occurrence_edge_relation_invalid"
        if edge_count and (source_page_count == 0 or target_page_count == 0):
            return {}, "template_zone_flow_page_count_invalid"
        if flow.get("evidence_scope") != EVIDENCE_SCOPE:
            return {}, "template_zone_flow_row_scope_mismatch"
        if flow.get("sitewide_template_flow_claim") is not False:
            return {}, "template_zone_flow_row_sitewide_flow_claim_invalid"
        if flow.get("sitewide_link_distribution_claim") is not False:
            return {}, "template_zone_flow_row_sitewide_distribution_claim_invalid"
        if flow.get("sitewide_link_absence_claim") is not False:
            return {}, "template_zone_flow_row_sitewide_link_claim_invalid"

        flow_index[key] = flow
        total_edges += edge_count
        total_occurrences += occurrence_count

    if total_edges != declared_edge_count:
        return {}, "template_zone_flow_total_edge_count_mismatch"
    if total_occurrences != declared_occurrence_count:
        return {}, "template_zone_flow_total_occurrence_count_mismatch"
    return flow_index, None


def raw_zone_template_contextual_internal_link_opportunities(
    template_contextual_opportunities: dict[str, Any],
    template_zone_flow: dict[str, Any],
) -> dict[str, Any]:
    """Bind source→target opportunities to verified raw-zone template-flow evidence."""
    candidates, candidate_count, truncated, contextual_error = _validated_template_contextual(
        template_contextual_opportunities
    )
    if contextual_error:
        return _empty_result(contextual_error)

    flow_index, flow_error = _validated_template_zone_flow(template_zone_flow)
    if flow_error:
        result = _empty_result(flow_error)
        result["template_contextual_opportunity_integrity_state"] = "verified"
        return result

    enriched: list[dict[str, Any]] = []
    zero_zone_counts = {zone: 0 for zone in ZONE_WEIGHTS}
    for candidate in candidates:
        source_group = str(candidate.get("source_group_id") or "").strip()
        target_group = str(candidate.get("target_group_id") or "").strip()
        flow = flow_index.get((source_group, target_group))
        observed_flow_present = flow is not None
        if candidate.get("observed_template_flow_present") is not observed_flow_present:
            result = _empty_result("template_contextual_raw_zone_flow_presence_mismatch")
            result["template_contextual_opportunity_integrity_state"] = "verified"
            result["template_zone_flow_integrity_state"] = "verified"
            return result

        row = dict(candidate)
        row.update(
            {
                "raw_zone_template_flow_present": observed_flow_present,
                "raw_zone_template_flow_link_occurrence_count": (
                    int(flow["observed_link_occurrence_count"]) if flow else 0
                ),
                "raw_zone_template_flow_directed_edge_count": (
                    int(flow["observed_directed_edge_count"]) if flow else 0
                ),
                "raw_zone_template_flow_contextual_occurrence_count": (
                    int(flow["contextual_occurrence_count"]) if flow else 0
                ),
                "raw_zone_template_flow_contextual_directed_edge_count": (
                    int(flow["contextual_directed_edge_count"]) if flow else 0
                ),
                "raw_zone_template_flow_mixed_zone_directed_edge_count": (
                    int(flow["mixed_zone_directed_edge_count"]) if flow else 0
                ),
                "raw_zone_template_flow_zone_occurrence_counts": (
                    dict(flow["zone_occurrence_counts"]) if flow else dict(zero_zone_counts)
                ),
                "raw_zone_template_flow_evidence_state": (
                    "observed_in_assessed_sample"
                    if flow
                    else "no_observed_flow_in_assessed_sample"
                ),
                "sitewide_link_distribution_claim": False,
            }
        )
        enriched.append(row)

    return {
        "version": RAW_ZONE_TEMPLATE_CONTEXTUAL_OPPORTUNITY_VERSION,
        "scope": EVIDENCE_SCOPE,
        "state": "candidate" if enriched else "no_candidate_observed",
        "reason": "validated",
        "template_contextual_opportunity_integrity_state": "verified",
        "template_zone_flow_integrity_state": "verified",
        "template_contextual_opportunity_version": TEMPLATE_CONTEXTUAL_OPPORTUNITY_VERSION,
        "template_link_zone_flow_version": TEMPLATE_LINK_ZONE_FLOW_VERSION,
        "candidate_count": candidate_count,
        "candidates": enriched,
        "candidates_truncated": truncated,
        "sitewide_link_absence_claim": False,
        "sitewide_template_flow_claim": False,
        "sitewide_link_distribution_claim": False,
        "customer_fix_created": False,
    }
