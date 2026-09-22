"""Graph-bound template/link-zone flow evidence for NextGen Lane B.

This module joins already-derived template evidence to the validated assessed-page
internal-link graph. It is deliberately descriptive evidence only: it does not
infer missing links, create customer Fixes, rank repairs, persist authority, or
perform network/model work.

Only observed assessed directed edges are summarized. Missing template-pair flows
are never promoted into sitewide absence claims.
"""
from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
from typing import Any

from .semantic_graph import TEMPLATE_EVIDENCE_VERSION, ZONE_WEIGHTS, _url
from .semantic_graph_contextual import EVIDENCE_SCOPE, _validated_graph


TEMPLATE_LINK_FLOW_VERSION = "template_link_flow_evidence_v1_graph_bound"
MAX_FLOW_EDGE_SAMPLES = 5


def _empty_result(reason: str) -> dict[str, Any]:
    return {
        "version": TEMPLATE_LINK_FLOW_VERSION,
        "scope": EVIDENCE_SCOPE,
        "state": "not_verified",
        "reason": reason,
        "template_integrity_state": "not_verified",
        "graph_integrity_state": "not_verified",
        "observed_template_flow_count": 0,
        "observed_directed_edge_count": 0,
        "flows": [],
        "sitewide_template_flow_claim": False,
        "sitewide_link_absence_claim": False,
        "customer_fix_created": False,
    }


def _validated_template_membership(
    template_evidence: dict[str, Any],
) -> tuple[dict[str, dict[str, str]], str | None]:
    if not isinstance(template_evidence, dict) or template_evidence.get("version") != TEMPLATE_EVIDENCE_VERSION:
        return {}, "template_version_mismatch"
    if template_evidence.get("scope") != EVIDENCE_SCOPE:
        return {}, "template_scope_mismatch"

    rows = template_evidence.get("pages")
    groups = template_evidence.get("groups")
    if not isinstance(rows, list) or not isinstance(groups, list):
        return {}, "template_shape_invalid"

    declared_groups: dict[str, dict[str, Any]] = {}
    for group in groups:
        if not isinstance(group, dict):
            return {}, "template_group_invalid"
        group_id = str(group.get("group_id") or "").strip()
        template_key = str(group.get("template_key") or "").strip()
        page_count = group.get("page_count")
        if (
            not group_id
            or group_id in declared_groups
            or not template_key
            or isinstance(page_count, bool)
            or not isinstance(page_count, int)
            or page_count <= 0
        ):
            return {}, "template_group_identity_invalid"
        expected_group_id = "tmpl_" + sha256(template_key.encode("utf-8")).hexdigest()[:12]
        if group_id != expected_group_id:
            return {}, "template_group_id_mismatch"
        declared_groups[group_id] = group

    membership: dict[str, dict[str, str]] = {}
    observed_counts: dict[str, int] = defaultdict(int)
    observed_keys: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            return {}, "template_page_invalid"
        url = _url(row.get("url"))
        group_id = str(row.get("group_id") or "").strip()
        template_key = str(row.get("template_key") or "").strip()
        state = str(row.get("state") or "").strip()
        if not url:
            return {}, "template_page_identity_incomplete"
        if url in membership:
            return {}, "template_page_identity_duplicate"
        if not group_id or group_id not in declared_groups or not template_key:
            return {}, "template_page_group_unverified"
        if state not in {"observed", "inferred"}:
            return {}, "template_page_group_unverified"
        if str(declared_groups[group_id].get("template_key") or "").strip() != template_key:
            return {}, "template_group_key_mismatch"

        membership[url] = {
            "group_id": group_id,
            "template_key": template_key,
            "state": state,
        }
        observed_counts[group_id] += 1
        observed_keys[group_id] = template_key

    if set(observed_counts) != set(declared_groups):
        return {}, "template_group_population_mismatch"
    for group_id, declared in declared_groups.items():
        if declared.get("page_count") != observed_counts[group_id]:
            return {}, "template_group_count_mismatch"
        if str(declared.get("template_key") or "").strip() != observed_keys[group_id]:
            return {}, "template_group_key_mismatch"

    return membership, None


def template_link_flow_evidence(
    template_evidence: dict[str, Any],
    graph: dict[str, Any],
) -> dict[str, Any]:
    """Summarize observed directed link flow between validated template groups.

    The graph is revalidated against the exact template-page population before any
    transported edge, zone, or weight can influence a flow row. Flow rows aggregate
    only graph edges that were actually observed among assessed pages.
    """
    membership, template_error = _validated_template_membership(template_evidence)
    if template_error:
        return _empty_result(template_error)

    edges, _nodes, graph_error = _validated_graph(set(membership), graph)
    if graph_error:
        result = _empty_result(graph_error)
        result["template_integrity_state"] = "verified"
        return result

    aggregate: dict[tuple[str, str], dict[str, Any]] = {}
    for (source, target), edge in sorted(edges.items()):
        source_template = membership[source]
        target_template = membership[target]
        key = (source_template["group_id"], target_template["group_id"])
        row = aggregate.get(key)
        if row is None:
            row = {
                "source_group_id": key[0],
                "target_group_id": key[1],
                "source_template_key": source_template["template_key"],
                "target_template_key": target_template["template_key"],
                "cross_template": key[0] != key[1],
                "observed_directed_edge_count": 0,
                "observed_source_page_urls": set(),
                "observed_target_page_urls": set(),
                "observed_weight_sum": 0.0,
                "strongest_zone_counts": {zone: 0 for zone in ZONE_WEIGHTS},
                "sample_edges": [],
            }
            aggregate[key] = row

        zone = str(edge.get("strongest_zone") or "").strip().lower()
        weight = float(edge.get("weight") or 0.0)
        row["observed_directed_edge_count"] += 1
        row["observed_source_page_urls"].add(source)
        row["observed_target_page_urls"].add(target)
        row["observed_weight_sum"] += weight
        row["strongest_zone_counts"][zone] += 1
        if len(row["sample_edges"]) < MAX_FLOW_EDGE_SAMPLES:
            row["sample_edges"].append(
                {
                    "source_url": source,
                    "target_url": target,
                    "strongest_zone": zone,
                    "weight": round(weight, 6),
                }
            )

    flows: list[dict[str, Any]] = []
    for key in sorted(aggregate):
        row = aggregate[key]
        observed_edge_count = row["observed_directed_edge_count"]
        flows.append(
            {
                "source_group_id": row["source_group_id"],
                "target_group_id": row["target_group_id"],
                "source_template_key": row["source_template_key"],
                "target_template_key": row["target_template_key"],
                "cross_template": row["cross_template"],
                "observed_directed_edge_count": observed_edge_count,
                "observed_source_page_count": len(row["observed_source_page_urls"]),
                "observed_target_page_count": len(row["observed_target_page_urls"]),
                "observed_weight_sum": round(row["observed_weight_sum"], 6),
                "strongest_zone_counts": row["strongest_zone_counts"],
                "contextual_edge_count": row["strongest_zone_counts"]["contextual"],
                "sample_edges": row["sample_edges"],
                "sample_edges_truncated": observed_edge_count > MAX_FLOW_EDGE_SAMPLES,
                "evidence_scope": EVIDENCE_SCOPE,
                "sitewide_link_absence_claim": False,
            }
        )

    return {
        "version": TEMPLATE_LINK_FLOW_VERSION,
        "scope": EVIDENCE_SCOPE,
        "state": "verified",
        "reason": "validated",
        "template_integrity_state": "verified",
        "graph_integrity_state": "verified",
        "observed_template_group_count": len({row["group_id"] for row in membership.values()}),
        "observed_template_flow_count": len(flows),
        "observed_directed_edge_count": len(edges),
        "flows": flows,
        "sitewide_template_flow_claim": False,
        "sitewide_link_absence_claim": False,
        "customer_fix_created": False,
    }
