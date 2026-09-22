"""Raw-link-zone-bound template flow evidence for NextGen Lane B.

The existing template-flow contract summarizes one strongest zone per reduced
source->target graph edge. That is intentionally compact, but it loses repeated
observations and mixed-zone evidence for the same directed pair. This helper
binds validated template membership and the weighted graph back to the exact
bounded raw link observations so template-to-template flow retains occurrence
counts, zone distributions, and occurrence-weight evidence.

This module is descriptive evidence only. It performs no network/model work,
creates no customer Fix, and never promotes an unobserved flow into a sitewide
link-absence claim.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from .semantic_graph import (
    MAX_ANCHOR_TERMS,
    ZONE_WEIGHTS,
    _bounded_links,
    _bounded_pages,
    _same_host,
    _url,
    infer_link_zone,
)
from .semantic_graph_contextual import EVIDENCE_SCOPE, _page_population, _validated_graph
from .semantic_graph_template_flow import _validated_template_membership
from .semantic_graph_zone_profile import (
    LINK_ZONE_OBSERVATION_PROFILE_VERSION,
    _observation_weight,
    graph_bound_link_zone_observation_profile,
)


TEMPLATE_LINK_ZONE_FLOW_VERSION = "template_link_zone_flow_evidence_v2_raw_observation_bound"
MAX_FLOW_OCCURRENCE_SAMPLES = 5


def _empty_result(reason: str) -> dict[str, Any]:
    return {
        "version": TEMPLATE_LINK_ZONE_FLOW_VERSION,
        "scope": EVIDENCE_SCOPE,
        "state": "not_verified",
        "reason": reason,
        "template_integrity_state": "not_verified",
        "graph_integrity_state": "not_verified",
        "raw_link_observation_integrity_state": "not_verified",
        "observed_template_flow_count": 0,
        "observed_directed_edge_count": 0,
        "observed_link_occurrence_count": 0,
        "flows": [],
        "sitewide_template_flow_claim": False,
        "sitewide_link_distribution_claim": False,
        "sitewide_link_absence_claim": False,
        "customer_fix_created": False,
    }


def template_link_zone_flow_evidence(
    pages: list[dict[str, Any]],
    links: list[dict[str, Any]],
    template_evidence: dict[str, Any],
    graph: dict[str, Any],
) -> dict[str, Any]:
    """Summarize raw observed link zones between validated template groups.

    Graph and raw-link integrity are verified before any transported weight or
    zone evidence can influence the result. Repeated observations remain repeated
    occurrence evidence, while directed-edge counts remain deduplicated by
    source/target identity. Mixed-zone edges are disclosed explicitly.
    """
    pages = _bounded_pages(pages)
    links = _bounded_links(links)

    population, population_error = _page_population(pages)
    if population_error:
        return _empty_result(population_error)
    if len(population) != len(pages):
        return _empty_result("page_identity_coverage_incomplete")

    membership, template_error = _validated_template_membership(template_evidence)
    if template_error:
        return _empty_result(template_error)
    if set(membership) != set(population):
        result = _empty_result("template_page_population_mismatch")
        result["template_integrity_state"] = "verified"
        return result

    graph_edges, _nodes, graph_error = _validated_graph(set(population), graph)
    if graph_error:
        result = _empty_result(graph_error)
        result["template_integrity_state"] = "verified"
        return result

    raw_profile = graph_bound_link_zone_observation_profile(pages, links, graph)
    if raw_profile.get("state") != "verified":
        result = _empty_result(
            str(raw_profile.get("reason") or "raw_link_zone_profile_not_verified")
        )
        result["template_integrity_state"] = "verified"
        result["graph_integrity_state"] = "verified"
        return result

    aggregate: dict[tuple[str, str], dict[str, Any]] = {}
    observed_occurrence_count = 0
    skipped_external = 0
    skipped_unassessed = 0
    ignored_non_edge = 0

    for raw_link in links:
        source = _url(raw_link.get("source_url") or raw_link.get("source"))
        target = _url(raw_link.get("target_url") or raw_link.get("target") or raw_link.get("href"))
        if not source or not target or source == target:
            ignored_non_edge += 1
            continue
        if not _same_host(source, target):
            skipped_external += 1
            continue
        if source not in population or target not in population:
            skipped_unassessed += 1
            continue

        zone_evidence = infer_link_zone(raw_link)
        zone = str(zone_evidence.get("zone") or "").strip().lower()
        confidence = float(zone_evidence.get("confidence") or 0.0)
        weight = _observation_weight(zone_evidence)
        anchor_terms = list(zone_evidence.get("anchor_terms") or [])[:MAX_ANCHOR_TERMS]
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
                "observed_link_occurrence_count": 0,
                "observed_source_page_urls": set(),
                "observed_target_page_urls": set(),
                "directed_edge_zones": defaultdict(set),
                "zone_occurrence_counts": {known_zone: 0 for known_zone in ZONE_WEIGHTS},
                "zone_confidence_max": {known_zone: 0.0 for known_zone in ZONE_WEIGHTS},
                "zone_occurrence_weight_sums": {known_zone: 0.0 for known_zone in ZONE_WEIGHTS},
                "occurrence_samples": [],
            }
            aggregate[key] = row

        edge_key = (source, target)
        row["observed_link_occurrence_count"] += 1
        row["observed_source_page_urls"].add(source)
        row["observed_target_page_urls"].add(target)
        row["directed_edge_zones"][edge_key].add(zone)
        row["zone_occurrence_counts"][zone] += 1
        row["zone_confidence_max"][zone] = max(
            float(row["zone_confidence_max"][zone]), confidence
        )
        row["zone_occurrence_weight_sums"][zone] += weight
        row["occurrence_samples"].append(
            {
                "source_url": source,
                "target_url": target,
                "zone": zone,
                "zone_confidence": round(confidence, 4),
                "weight": weight,
                "anchor_terms": anchor_terms,
            }
        )
        observed_occurrence_count += 1

    if observed_occurrence_count != raw_profile.get("observed_assessed_link_occurrence_count"):
        result = _empty_result("raw_profile_occurrence_count_mismatch")
        result["template_integrity_state"] = "verified"
        result["graph_integrity_state"] = "verified"
        return result
    if skipped_external != raw_profile.get("skipped_external_links"):
        result = _empty_result("raw_profile_skipped_external_count_mismatch")
        result["template_integrity_state"] = "verified"
        result["graph_integrity_state"] = "verified"
        return result
    if skipped_unassessed != raw_profile.get("skipped_unassessed_targets"):
        result = _empty_result("raw_profile_skipped_unassessed_count_mismatch")
        result["template_integrity_state"] = "verified"
        result["graph_integrity_state"] = "verified"
        return result

    flow_edge_population = {
        edge_key
        for row in aggregate.values()
        for edge_key in row["directed_edge_zones"]
    }
    if flow_edge_population != set(graph_edges):
        result = _empty_result("template_flow_graph_edge_population_mismatch")
        result["template_integrity_state"] = "verified"
        result["graph_integrity_state"] = "verified"
        return result

    flows: list[dict[str, Any]] = []
    for key in sorted(aggregate):
        row = aggregate[key]
        edge_zones = row["directed_edge_zones"]
        contextual_edge_count = sum(
            1 for zones in edge_zones.values() if "contextual" in zones
        )
        mixed_zone_edge_count = sum(1 for zones in edge_zones.values() if len(zones) > 1)
        strongest_zone_counts = {zone: 0 for zone in ZONE_WEIGHTS}
        for edge_key in sorted(edge_zones):
            graph_zone = str(graph_edges[edge_key].get("strongest_zone") or "").strip().lower()
            strongest_zone_counts[graph_zone] += 1

        samples = sorted(
            row["occurrence_samples"],
            key=lambda sample: (
                sample["source_url"],
                sample["target_url"],
                sample["zone"],
                sample["anchor_terms"],
            ),
        )
        occurrence_count = int(row["observed_link_occurrence_count"])
        flows.append(
            {
                "source_group_id": row["source_group_id"],
                "target_group_id": row["target_group_id"],
                "source_template_key": row["source_template_key"],
                "target_template_key": row["target_template_key"],
                "cross_template": row["cross_template"],
                "observed_link_occurrence_count": occurrence_count,
                "observed_directed_edge_count": len(edge_zones),
                "observed_source_page_count": len(row["observed_source_page_urls"]),
                "observed_target_page_count": len(row["observed_target_page_urls"]),
                "contextual_occurrence_count": row["zone_occurrence_counts"]["contextual"],
                "contextual_directed_edge_count": contextual_edge_count,
                "mixed_zone_directed_edge_count": mixed_zone_edge_count,
                "zone_occurrence_counts": row["zone_occurrence_counts"],
                "zone_confidence_max": {
                    zone: round(float(value), 4)
                    for zone, value in row["zone_confidence_max"].items()
                },
                "zone_occurrence_weight_sums": {
                    zone: round(float(value), 6)
                    for zone, value in row["zone_occurrence_weight_sums"].items()
                },
                "strongest_zone_directed_edge_counts": strongest_zone_counts,
                "occurrence_samples": samples[:MAX_FLOW_OCCURRENCE_SAMPLES],
                "occurrence_samples_truncated": occurrence_count > MAX_FLOW_OCCURRENCE_SAMPLES,
                "evidence_scope": EVIDENCE_SCOPE,
                "sitewide_template_flow_claim": False,
                "sitewide_link_distribution_claim": False,
                "sitewide_link_absence_claim": False,
            }
        )

    return {
        "version": TEMPLATE_LINK_ZONE_FLOW_VERSION,
        "scope": EVIDENCE_SCOPE,
        "state": "verified",
        "reason": "validated",
        "template_integrity_state": "verified",
        "graph_integrity_state": "verified",
        "raw_link_observation_integrity_state": "verified",
        "link_zone_observation_profile_version": LINK_ZONE_OBSERVATION_PROFILE_VERSION,
        "observed_template_group_count": len({row["group_id"] for row in membership.values()}),
        "observed_template_flow_count": len(flows),
        "observed_directed_edge_count": len(graph_edges),
        "observed_link_occurrence_count": observed_occurrence_count,
        "ignored_missing_or_self_link_observations": ignored_non_edge,
        "skipped_external_links": skipped_external,
        "skipped_unassessed_targets": skipped_unassessed,
        "flows": flows,
        "sitewide_template_flow_claim": False,
        "sitewide_link_distribution_claim": False,
        "sitewide_link_absence_claim": False,
        "customer_fix_created": False,
    }
