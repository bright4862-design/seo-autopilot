"""Raw-observation-bound link-zone evidence for NextGen Lane B.

The weighted semantic graph intentionally reduces repeated source→target link
observations to one directed edge and retains only the strongest observed zone.
That is useful for graph scoring but lossy for diagnostics. This helper binds the
transported graph back to the bounded raw link observations and preserves the
observed zone distribution without changing the graph contract.

The result is descriptive, assessed-sample evidence only. It performs no network
or provider work, creates no customer Fix, and never treats a missing edge or
zone as proof of sitewide absence.
"""
from __future__ import annotations

from collections import defaultdict
from math import isfinite
from typing import Any

from .semantic_graph import (
    LINK_ZONE_VERSION,
    MAX_ANCHOR_TERMS,
    ZONE_WEIGHTS,
    _bounded_links,
    _bounded_pages,
    _same_host,
    _url,
    infer_link_zone,
)
from .semantic_graph_contextual import EVIDENCE_SCOPE, _page_population, _validated_graph


LINK_ZONE_OBSERVATION_PROFILE_VERSION = "link_zone_observation_profile_v1_graph_bound"
MAX_EDGE_PROFILES = 250


def _empty_result(reason: str) -> dict[str, Any]:
    return {
        "version": LINK_ZONE_OBSERVATION_PROFILE_VERSION,
        "scope": EVIDENCE_SCOPE,
        "state": "not_verified",
        "reason": reason,
        "graph_integrity_state": "not_verified",
        "raw_link_observation_integrity_state": "not_verified",
        "observed_assessed_link_occurrence_count": 0,
        "observed_directed_edge_count": 0,
        "zone_occurrence_counts": {zone: 0 for zone in ZONE_WEIGHTS},
        "edge_profile_count": 0,
        "edge_profiles": [],
        "edge_profiles_truncated": False,
        "sitewide_link_distribution_claim": False,
        "sitewide_link_absence_claim": False,
        "customer_fix_created": False,
    }


def _strict_non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _strict_finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if isfinite(parsed) else None


def _observation_weight(zone_evidence: dict[str, Any]) -> float:
    zone = str(zone_evidence.get("zone") or "").strip().lower()
    confidence = float(zone_evidence.get("confidence") or 0.0)
    anchor_terms = zone_evidence.get("anchor_terms") or []
    base_weight = ZONE_WEIGHTS[zone]
    anchor_bonus = min(0.08, 0.01 * len(anchor_terms))
    confidence_multiplier = 0.5 + 0.5 * confidence
    return round((base_weight + anchor_bonus) * confidence_multiplier, 6)


def graph_bound_link_zone_observation_profile(
    pages: list[dict[str, Any]],
    links: list[dict[str, Any]],
    graph: dict[str, Any],
) -> dict[str, Any]:
    """Bind graph edges to the exact bounded raw link-zone observations.

    Validation deliberately goes beyond graph node-total consistency. The helper
    independently regenerates qualifying assessed internal-link observations and
    verifies edge population, occurrence count, strongest zone, strongest weight,
    confidence, anchor-term union, and skipped-link counters. This prevents a
    self-consistent but forged transported graph edge from becoming trusted
    link-zone evidence.
    """
    pages = _bounded_pages(pages)
    links = _bounded_links(links)

    population, population_error = _page_population(pages)
    if population_error:
        return _empty_result(population_error)
    if len(population) != len(pages):
        return _empty_result("page_identity_coverage_incomplete")

    graph_edges, _nodes, graph_error = _validated_graph(set(population), graph)
    if graph_error:
        return _empty_result(graph_error)

    aggregate: dict[tuple[str, str], dict[str, Any]] = {}
    zone_occurrence_counts = {zone: 0 for zone in ZONE_WEIGHTS}
    zone_occurrence_weight_sums = {zone: 0.0 for zone in ZONE_WEIGHTS}
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
        anchor_terms = list(zone_evidence.get("anchor_terms") or [])
        weight = _observation_weight(zone_evidence)
        zone_occurrence_counts[zone] += 1
        zone_occurrence_weight_sums[zone] += weight

        key = (source, target)
        row = aggregate.get(key)
        if row is None:
            row = {
                "source_url": source,
                "target_url": target,
                "observed_occurrences": 0,
                "zone_occurrence_counts": {known_zone: 0 for known_zone in ZONE_WEIGHTS},
                "zone_confidence_max": {known_zone: 0.0 for known_zone in ZONE_WEIGHTS},
                "anchor_terms": set(),
                "strongest_observed_zone": zone,
                "strongest_observed_zone_confidence": confidence,
                "strongest_observed_weight": weight,
            }
            aggregate[key] = row

        row["observed_occurrences"] += 1
        row["zone_occurrence_counts"][zone] += 1
        row["zone_confidence_max"][zone] = max(
            float(row["zone_confidence_max"][zone]), confidence
        )
        row["anchor_terms"].update(anchor_terms)
        if weight > float(row["strongest_observed_weight"]):
            row["strongest_observed_zone"] = zone
            row["strongest_observed_zone_confidence"] = confidence
            row["strongest_observed_weight"] = weight

    declared_external = _strict_non_negative_int(graph.get("skipped_external_links"))
    declared_unassessed = _strict_non_negative_int(graph.get("skipped_unassessed_targets"))
    if declared_external != skipped_external:
        result = _empty_result("graph_skipped_external_count_mismatch")
        result["graph_integrity_state"] = "verified"
        return result
    if declared_unassessed != skipped_unassessed:
        result = _empty_result("graph_skipped_unassessed_count_mismatch")
        result["graph_integrity_state"] = "verified"
        return result

    if set(graph_edges) != set(aggregate):
        result = _empty_result("graph_edge_observation_population_mismatch")
        result["graph_integrity_state"] = "verified"
        return result

    profiles: list[dict[str, Any]] = []
    for key in sorted(aggregate):
        observed = aggregate[key]
        edge = graph_edges[key]

        graph_occurrences = _strict_non_negative_int(edge.get("observed_occurrences"))
        if graph_occurrences != observed["observed_occurrences"]:
            result = _empty_result("graph_edge_occurrence_mismatch")
            result["graph_integrity_state"] = "verified"
            return result

        graph_zone = str(edge.get("strongest_zone") or "").strip().lower()
        if graph_zone != observed["strongest_observed_zone"]:
            result = _empty_result("graph_edge_strongest_zone_mismatch")
            result["graph_integrity_state"] = "verified"
            return result

        graph_weight = _strict_finite_number(edge.get("weight"))
        if graph_weight != observed["strongest_observed_weight"]:
            result = _empty_result("graph_edge_weight_mismatch")
            result["graph_integrity_state"] = "verified"
            return result

        graph_confidence = _strict_finite_number(edge.get("zone_confidence"))
        if graph_confidence != observed["strongest_observed_zone_confidence"]:
            result = _empty_result("graph_edge_zone_confidence_mismatch")
            result["graph_integrity_state"] = "verified"
            return result

        graph_anchor_terms = edge.get("anchor_terms")
        expected_anchor_terms = sorted(observed["anchor_terms"])[:MAX_ANCHOR_TERMS]
        if not isinstance(graph_anchor_terms, list) or graph_anchor_terms != expected_anchor_terms:
            result = _empty_result("graph_edge_anchor_terms_mismatch")
            result["graph_integrity_state"] = "verified"
            return result

        profiles.append(
            {
                "source_url": observed["source_url"],
                "target_url": observed["target_url"],
                "observed_occurrences": observed["observed_occurrences"],
                "zone_occurrence_counts": observed["zone_occurrence_counts"],
                "zone_confidence_max": {
                    zone: round(float(value), 4)
                    for zone, value in observed["zone_confidence_max"].items()
                },
                "anchor_terms": expected_anchor_terms,
                "strongest_observed_zone": observed["strongest_observed_zone"],
                "strongest_observed_zone_confidence": round(
                    float(observed["strongest_observed_zone_confidence"]), 4
                ),
                "strongest_observed_weight": observed["strongest_observed_weight"],
                "graph_strongest_zone": graph_zone,
                "graph_weight": graph_weight,
                "link_zone_version": LINK_ZONE_VERSION,
                "evidence_scope": EVIDENCE_SCOPE,
                "sitewide_link_distribution_claim": False,
                "sitewide_link_absence_claim": False,
            }
        )

    observed_occurrence_count = sum(zone_occurrence_counts.values())
    edge_profile_count = len(profiles)
    bounded_profiles = profiles[:MAX_EDGE_PROFILES]
    return {
        "version": LINK_ZONE_OBSERVATION_PROFILE_VERSION,
        "scope": EVIDENCE_SCOPE,
        "state": "verified",
        "reason": "validated",
        "graph_integrity_state": "verified",
        "raw_link_observation_integrity_state": "verified",
        "assessed_page_identity_count": len(population),
        "observed_assessed_link_occurrence_count": observed_occurrence_count,
        "observed_directed_edge_count": len(graph_edges),
        "ignored_missing_or_self_link_observations": ignored_non_edge,
        "skipped_external_links": skipped_external,
        "skipped_unassessed_targets": skipped_unassessed,
        "zone_occurrence_counts": zone_occurrence_counts,
        "zone_occurrence_weight_sums": {
            zone: round(value, 6) for zone, value in zone_occurrence_weight_sums.items()
        },
        "edge_profile_count": edge_profile_count,
        "edge_profiles": bounded_profiles,
        "edge_profiles_truncated": edge_profile_count > MAX_EDGE_PROFILES,
        "sitewide_link_distribution_claim": False,
        "sitewide_link_absence_claim": False,
        "customer_fix_created": False,
    }
