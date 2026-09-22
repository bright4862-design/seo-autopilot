"""Template-bound source-to-target contextual-link opportunity evidence.

This Lane-B helper joins contextual internal-link candidate evidence to validated
template membership and the exact assessed-page weighted graph. It is descriptive
evidence only: it does not create customer Fixes, alter repair priority, persist
authority, or make sitewide link-absence claims.

For each contextual candidate, the helper reports the source/target template
identity and any *observed assessed-sample* template-to-template flow. A missing
flow remains explicitly sample-scoped and is never promoted to proof that the
site lacks that relationship.
"""
from __future__ import annotations

from typing import Any

from .semantic_graph import _url
from .semantic_graph_contextual import (
    CONTEXTUAL_INTERNAL_LINK_OPPORTUNITY_VERSION,
    EVIDENCE_SCOPE,
    _validated_graph,
)
from .semantic_graph_template_flow import (
    TEMPLATE_LINK_FLOW_VERSION,
    _validated_template_membership,
    template_link_flow_evidence,
)


TEMPLATE_CONTEXTUAL_OPPORTUNITY_VERSION = (
    "template_contextual_internal_link_opportunity_v1_graph_bound"
)


def _empty_result(reason: str) -> dict[str, Any]:
    return {
        "version": TEMPLATE_CONTEXTUAL_OPPORTUNITY_VERSION,
        "scope": EVIDENCE_SCOPE,
        "state": "not_verified",
        "reason": reason,
        "template_integrity_state": "not_verified",
        "graph_integrity_state": "not_verified",
        "contextual_opportunity_integrity_state": "not_verified",
        "candidate_count": 0,
        "candidates": [],
        "candidates_truncated": False,
        "sitewide_link_absence_claim": False,
        "sitewide_template_flow_claim": False,
        "customer_fix_created": False,
    }


def _strict_non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _validated_contextual_candidates(
    contextual: dict[str, Any],
    membership: dict[str, dict[str, str]],
    edges: dict[tuple[str, str], dict[str, Any]],
) -> tuple[list[dict[str, Any]], int, bool, str | None]:
    if (
        not isinstance(contextual, dict)
        or contextual.get("version") != CONTEXTUAL_INTERNAL_LINK_OPPORTUNITY_VERSION
    ):
        return [], 0, False, "contextual_opportunity_version_mismatch"
    if contextual.get("scope") != EVIDENCE_SCOPE:
        return [], 0, False, "contextual_opportunity_scope_mismatch"
    if contextual.get("graph_integrity_state") != "verified":
        return [], 0, False, "contextual_opportunity_graph_not_verified"
    if contextual.get("sitewide_link_absence_claim") is not False:
        return [], 0, False, "contextual_opportunity_sitewide_claim_invalid"

    candidates = contextual.get("candidates")
    candidate_count = _strict_non_negative_int(contextual.get("candidate_count"))
    truncated = contextual.get("candidates_truncated")
    if not isinstance(candidates, list) or candidate_count is None or not isinstance(truncated, bool):
        return [], 0, False, "contextual_opportunity_shape_invalid"
    if candidate_count < len(candidates):
        return [], 0, False, "contextual_opportunity_count_invalid"
    if not truncated and candidate_count != len(candidates):
        return [], 0, False, "contextual_opportunity_count_mismatch"

    state = str(contextual.get("state") or "")
    if state == "not_verified":
        return [], 0, False, "contextual_opportunity_not_verified"
    if candidates and state != "candidate":
        return [], 0, False, "contextual_opportunity_state_mismatch"
    if not candidates and state not in {"no_candidate_observed", "candidate"}:
        return [], 0, False, "contextual_opportunity_state_mismatch"

    seen: set[tuple[str, str]] = set()
    validated: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            return [], 0, False, "contextual_candidate_invalid"
        source = _url(candidate.get("source_url"))
        target = _url(candidate.get("target_url"))
        pair = (source, target)
        if (
            not source
            or not target
            or source == target
            or source not in membership
            or target not in membership
        ):
            return [], 0, False, "contextual_candidate_population_mismatch"
        if pair in seen:
            return [], 0, False, "contextual_candidate_duplicate"
        seen.add(pair)

        if candidate.get("state") != "candidate":
            return [], 0, False, "contextual_candidate_state_invalid"
        if candidate.get("evidence_scope") != EVIDENCE_SCOPE:
            return [], 0, False, "contextual_candidate_scope_mismatch"
        if candidate.get("sitewide_link_absence_claim") is not False:
            return [], 0, False, "contextual_candidate_sitewide_claim_invalid"
        if candidate.get("proposed_zone") != "contextual":
            return [], 0, False, "contextual_candidate_proposed_zone_invalid"
        if candidate.get("observed_contextual_edge_present") is not False:
            return [], 0, False, "contextual_candidate_contextual_edge_invalid"

        actual_edge = edges.get(pair)
        actual_present = actual_edge is not None
        if candidate.get("observed_edge_present") is not actual_present:
            return [], 0, False, "contextual_candidate_edge_presence_mismatch"
        actual_zone = (
            str(actual_edge.get("strongest_zone") or "").strip().lower()
            if actual_edge
            else None
        )
        if actual_zone == "contextual":
            return [], 0, False, "contextual_candidate_already_contextual"
        if candidate.get("existing_strongest_zone") != actual_zone:
            return [], 0, False, "contextual_candidate_existing_zone_mismatch"
        validated.append(candidate)

    return validated, candidate_count, truncated, None


def template_contextual_internal_link_opportunities(
    template_evidence: dict[str, Any],
    graph: dict[str, Any],
    contextual_opportunities: dict[str, Any],
) -> dict[str, Any]:
    """Bind contextual source→target candidates to template/link-flow evidence.

    Template membership and graph metrics are revalidated independently. The
    template-flow summary is then regenerated from those validated inputs rather
    than trusting caller-transported flow rows. Candidate graph-presence fields
    are checked against the same validated edge map before template context is
    attached.
    """
    membership, template_error = _validated_template_membership(template_evidence)
    if template_error:
        return _empty_result(template_error)

    edges, _nodes, graph_error = _validated_graph(set(membership), graph)
    if graph_error:
        result = _empty_result(graph_error)
        result["template_integrity_state"] = "verified"
        return result

    candidates, candidate_count, truncated, contextual_error = _validated_contextual_candidates(
        contextual_opportunities,
        membership,
        edges,
    )
    if contextual_error:
        result = _empty_result(contextual_error)
        result["template_integrity_state"] = "verified"
        result["graph_integrity_state"] = "verified"
        return result

    flow_evidence = template_link_flow_evidence(template_evidence, graph)
    if flow_evidence.get("state") != "verified":
        result = _empty_result(
            str(flow_evidence.get("reason") or "template_link_flow_not_verified")
        )
        result["template_integrity_state"] = "verified"
        result["graph_integrity_state"] = "verified"
        result["contextual_opportunity_integrity_state"] = "verified"
        return result

    flow_index = {
        (str(flow.get("source_group_id") or ""), str(flow.get("target_group_id") or "")): flow
        for flow in flow_evidence.get("flows", [])
        if isinstance(flow, dict)
    }
    enriched: list[dict[str, Any]] = []
    for candidate in candidates:
        source = _url(candidate.get("source_url"))
        target = _url(candidate.get("target_url"))
        source_template = membership[source]
        target_template = membership[target]
        flow = flow_index.get((source_template["group_id"], target_template["group_id"]))

        row = dict(candidate)
        row.update(
            {
                "source_group_id": source_template["group_id"],
                "source_template_key": source_template["template_key"],
                "target_group_id": target_template["group_id"],
                "target_template_key": target_template["template_key"],
                "cross_template": source_template["group_id"] != target_template["group_id"],
                "observed_template_flow_present": flow is not None,
                "observed_template_flow_directed_edge_count": (
                    int(flow.get("observed_directed_edge_count") or 0) if flow else 0
                ),
                "observed_template_flow_contextual_edge_count": (
                    int(flow.get("contextual_edge_count") or 0) if flow else 0
                ),
                "observed_template_flow_weight_sum": (
                    float(flow.get("observed_weight_sum") or 0.0) if flow else 0.0
                ),
                "template_flow_evidence_state": (
                    "observed_in_assessed_sample"
                    if flow is not None
                    else "no_observed_flow_in_assessed_sample"
                ),
                "sitewide_template_flow_claim": False,
            }
        )
        enriched.append(row)

    return {
        "version": TEMPLATE_CONTEXTUAL_OPPORTUNITY_VERSION,
        "scope": EVIDENCE_SCOPE,
        "state": "candidate" if enriched else "no_candidate_observed",
        "reason": "validated",
        "template_integrity_state": "verified",
        "graph_integrity_state": "verified",
        "contextual_opportunity_integrity_state": "verified",
        "template_link_flow_version": TEMPLATE_LINK_FLOW_VERSION,
        "candidate_count": candidate_count,
        "candidates": enriched,
        "candidates_truncated": truncated,
        "sitewide_link_absence_claim": False,
        "sitewide_template_flow_claim": False,
        "customer_fix_created": False,
    }
