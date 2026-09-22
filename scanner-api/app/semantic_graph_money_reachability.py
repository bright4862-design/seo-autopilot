"""Weighted assessed-graph reachability evidence for classified money pages.

This Lane-B helper consumes only already-observed assessed pages, bounded raw link
observations, and the validated weighted internal-link graph. It performs no
network/model work, creates no customer Fix, and never upgrades an unobserved
route or navigation edge into proof of sitewide orphaning.
"""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from .semantic_graph import (
    ZONE_WEIGHTS,
    _bounded_links,
    _bounded_pages,
    _same_host,
    _url,
    infer_link_zone,
)
from .semantic_graph_contextual import EVIDENCE_SCOPE, _page_population, _validated_graph
from .semantic_graph_zone_profile import graph_bound_link_zone_observation_profile


WEIGHTED_MONEY_PAGE_REACHABILITY_VERSION = (
    "money_page_reachability_v2_weighted_graph_bound"
)
MAX_SEEDS = 8
MAX_SOURCE_SAMPLES = 8

# Mirrors the already-established Stage-2 money-page family vocabulary without
# importing priority/ranking code into the Lane-B evidence helper.
MONEY_TEMPLATE_FAMILIES = {
    "activity_detail",
    "product_page",
    "product_detail",
    "calculator",
    "conversion",
    "booking_or_checkout",
    "loan_program",
    "pricing_page",
}
MONEY_INTENTS = {"commercial", "conversion", "money_page", "transactional"}


def _empty_result(reason: str) -> dict[str, Any]:
    return {
        "version": WEIGHTED_MONEY_PAGE_REACHABILITY_VERSION,
        "scope": EVIDENCE_SCOPE,
        "state": "not_verified",
        "reason": reason,
        "graph_integrity_state": "not_verified",
        "raw_link_observation_integrity_state": "not_verified",
        "seed_integrity_state": "not_verified",
        "classified_money_page_count": 0,
        "weak_route_count": 0,
        "unreached_from_seed_count": 0,
        "pages": [],
        "sitewide_reachability_claim": False,
        "sitewide_orphan_claim": False,
        "sitewide_navigation_absence_claim": False,
        "sitewide_link_absence_claim": False,
        "sitewide_link_distribution_claim": False,
        "customer_fix_created": False,
    }


def _classified_money_page(page: dict[str, Any]) -> tuple[bool, str | None]:
    if page.get("money_page") is True:
        return True, "explicit_money_page_flag"
    value_class = str(page.get("page_value_class") or page.get("page_role") or "").strip().lower()
    if value_class == "money":
        return True, "explicit_money_page_value_class"
    family = str(page.get("page_template_family") or "").strip().lower()
    if family in MONEY_TEMPLATE_FAMILIES:
        return True, "existing_money_template_family"
    intent = str(page.get("estimated_page_intent") or page.get("page_intent") or "").strip().lower()
    if intent in MONEY_INTENTS:
        return True, "existing_money_page_intent"
    return False, None


def _seed_population(
    pages: list[dict[str, Any]],
    population: dict[str, dict[str, Any]],
    seed_urls: list[str] | None,
) -> tuple[list[str], str, str | None]:
    if seed_urls is not None:
        if not isinstance(seed_urls, list) or len(seed_urls) > MAX_SEEDS:
            return [], "not_verified", "seed_list_invalid"
        normalized: list[str] = []
        seen: set[str] = set()
        for value in seed_urls:
            url = _url(value)
            if not url or url in seen:
                return [], "not_verified", "seed_identity_invalid"
            seen.add(url)
            normalized.append(url)
        if any(url not in population for url in normalized):
            return [], "not_verified", "seed_population_mismatch"
        return sorted(normalized), "verified" if normalized else "not_verified", None

    inferred: list[str] = []
    for page in pages:
        url = _url(page.get("url") or page.get("final_url") or page.get("page_url"))
        if not url:
            continue
        discovered_from = page.get("discovered_from")
        labels = {
            str(value or "").strip().lower()
            for value in discovered_from
        } if isinstance(discovered_from, list) else set()
        if page.get("is_seed") is True or "seed" in labels:
            inferred.append(url)
    inferred = sorted(set(inferred))
    if len(inferred) > MAX_SEEDS:
        return [], "not_verified", "inferred_seed_bound_exceeded"
    return inferred, "verified" if inferred else "not_verified", None


def _depths_from_seeds(
    seeds: list[str],
    out_neighbours: dict[str, set[str]],
) -> dict[str, int]:
    depths: dict[str, int] = {}
    queue: deque[str] = deque()
    for seed in sorted(seeds):
        depths[seed] = 0
        queue.append(seed)
    while queue:
        source = queue.popleft()
        next_depth = depths[source] + 1
        for target in sorted(out_neighbours.get(source, set())):
            if target in depths:
                continue
            depths[target] = next_depth
            queue.append(target)
    return depths


def weighted_money_page_reachability_evidence(
    pages: list[dict[str, Any]],
    links: list[dict[str, Any]],
    graph: dict[str, Any],
    *,
    seed_urls: list[str] | None = None,
) -> dict[str, Any]:
    """Bind money-page reachability to exact assessed weighted graph evidence."""
    pages = _bounded_pages(pages)
    links = _bounded_links(links)

    population, population_error = _page_population(pages)
    if population_error:
        return _empty_result(population_error)
    if len(population) != len(pages):
        return _empty_result("page_identity_coverage_incomplete")

    edges, nodes, graph_error = _validated_graph(set(population), graph)
    if graph_error:
        return _empty_result(graph_error)
    if graph.get("sitewide_orphan_claim") is not False:
        result = _empty_result("graph_sitewide_orphan_claim_invalid")
        result["graph_integrity_state"] = "verified"
        return result
    if any(row.get("sitewide_orphan_claim") is not False for row in nodes.values()):
        result = _empty_result("graph_node_sitewide_orphan_claim_invalid")
        result["graph_integrity_state"] = "verified"
        return result

    raw_profile = graph_bound_link_zone_observation_profile(pages, links, graph)
    if raw_profile.get("state") != "verified":
        result = _empty_result(
            str(raw_profile.get("reason") or "raw_link_observation_not_verified")
        )
        result["graph_integrity_state"] = "verified"
        return result

    seeds, seed_state, seed_error = _seed_population(pages, population, seed_urls)
    if seed_error:
        result = _empty_result(seed_error)
        result["graph_integrity_state"] = "verified"
        result["raw_link_observation_integrity_state"] = "verified"
        return result

    out_neighbours: dict[str, set[str]] = {url: set() for url in population}
    inbound_edges: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for (source, target), edge in edges.items():
        out_neighbours[source].add(target)
        inbound_edges[target].append((source, edge))

    edge_zones: dict[tuple[str, str], set[str]] = defaultdict(set)
    edge_occurrences: dict[tuple[str, str], int] = defaultdict(int)
    target_zone_occurrences: dict[str, dict[str, int]] = {
        url: {zone: 0 for zone in ZONE_WEIGHTS} for url in population
    }
    for raw_link in links:
        source = _url(raw_link.get("source_url") or raw_link.get("source"))
        target = _url(raw_link.get("target_url") or raw_link.get("target") or raw_link.get("href"))
        if not source or not target or source == target:
            continue
        if not _same_host(source, target):
            continue
        if source not in population or target not in population:
            continue
        zone = str(infer_link_zone(raw_link).get("zone") or "").strip().lower()
        if zone not in ZONE_WEIGHTS:
            result = _empty_result("raw_link_zone_invalid")
            result["graph_integrity_state"] = "verified"
            result["raw_link_observation_integrity_state"] = "verified"
            return result
        key = (source, target)
        edge_zones[key].add(zone)
        edge_occurrences[key] += 1
        target_zone_occurrences[target][zone] += 1

    if set(edge_zones) != set(edges):
        result = _empty_result("raw_link_graph_edge_population_mismatch")
        result["graph_integrity_state"] = "verified"
        result["raw_link_observation_integrity_state"] = "verified"
        return result

    depths = _depths_from_seeds(seeds, out_neighbours) if seeds else {}
    rows: list[dict[str, Any]] = []
    for url in sorted(population):
        page = population[url]
        is_money, classification_reason = _classified_money_page(page)
        if not is_money:
            continue

        inbound = sorted(inbound_edges.get(url, []), key=lambda item: item[0])
        node = nodes[url]
        observed_in_edges = int(node.get("observed_in_edge_count") or 0)
        if observed_in_edges != len(inbound):
            result = _empty_result("money_page_graph_inlink_count_mismatch")
            result["graph_integrity_state"] = "verified"
            result["raw_link_observation_integrity_state"] = "verified"
            result["seed_integrity_state"] = seed_state
            return result

        inbound_keys = [(source, url) for source, _edge in inbound]
        zone_edge_counts = {
            zone: sum(1 for key in inbound_keys if zone in edge_zones.get(key, set()))
            for zone in ZONE_WEIGHTS
        }
        mixed_zone_count = sum(
            1 for key in inbound_keys if len(edge_zones.get(key, set())) > 1
        )
        inbound_occurrence_count = sum(edge_occurrences.get(key, 0) for key in inbound_keys)
        strongest = sorted(
            inbound,
            key=lambda item: (
                -float(item[1].get("weight") or 0.0),
                item[0],
            ),
        )
        strongest_source = strongest[0][0] if strongest else None
        strongest_edge = strongest[0][1] if strongest else None

        depth = depths.get(url) if seed_state == "verified" else None
        if seed_state != "verified":
            route_state = "seed_not_verified"
        elif depth is None:
            route_state = "no_observed_route_from_seed_in_assessed_graph"
        else:
            route_state = "reachable_from_seed_in_assessed_graph"

        weak_reasons: list[str] = []
        if observed_in_edges == 0:
            weak_reasons.append("zero_observed_in_edges")
        if seed_state == "verified" and depth is None:
            weak_reasons.append("no_observed_route_from_seed")
        elif depth is not None and depth >= 4:
            weak_reasons.append("observed_depth_at_least_4")
        if zone_edge_counts["navigation"] == 0:
            weak_reasons.append("no_navigation_edge_observed")

        if weak_reasons:
            assessment_state = "observed_weak_route"
        elif seed_state == "verified":
            assessment_state = "observed_reachable"
        else:
            assessment_state = "partial_seed_unknown"

        rows.append(
            {
                "url": url,
                "classification_reason": classification_reason,
                "template_family": str(page.get("page_template_family") or "").strip().lower() or None,
                "observed_in_edge_count": observed_in_edges,
                "observed_weighted_in": round(float(node.get("weighted_in") or 0.0), 6),
                "observed_inlink_occurrence_count": inbound_occurrence_count,
                "observed_navigation_in_edge_count": zone_edge_counts["navigation"],
                "observed_contextual_in_edge_count": zone_edge_counts["contextual"],
                "observed_unknown_zone_in_edge_count": zone_edge_counts["unknown"],
                "observed_mixed_zone_in_edge_count": mixed_zone_count,
                "zone_in_edge_counts": zone_edge_counts,
                "zone_in_occurrence_counts": target_zone_occurrences[url],
                "source_url_samples": [source for source, _edge in inbound[:MAX_SOURCE_SAMPLES]],
                "source_url_samples_truncated": len(inbound) > MAX_SOURCE_SAMPLES,
                "strongest_inbound_source_url": strongest_source,
                "strongest_inbound_zone": (
                    str(strongest_edge.get("strongest_zone") or "").strip().lower()
                    if strongest_edge
                    else None
                ),
                "strongest_inbound_weight": (
                    round(float(strongest_edge.get("weight") or 0.0), 6)
                    if strongest_edge
                    else None
                ),
                "observed_depth_from_seed": depth,
                "observed_route_state": route_state,
                "reachability_assessment_state": assessment_state,
                "weak_route_reasons": weak_reasons,
                "evidence_scope": EVIDENCE_SCOPE,
                "sitewide_reachability_claim": False,
                "sitewide_orphan_claim": False,
                "sitewide_navigation_absence_claim": False,
                "sitewide_link_absence_claim": False,
            }
        )

    weak_count = sum(row["reachability_assessment_state"] == "observed_weak_route" for row in rows)
    unreached = sum(
        row["observed_route_state"] == "no_observed_route_from_seed_in_assessed_graph"
        for row in rows
    )
    return {
        "version": WEIGHTED_MONEY_PAGE_REACHABILITY_VERSION,
        "scope": EVIDENCE_SCOPE,
        "state": "verified",
        "reason": "validated",
        "graph_integrity_state": "verified",
        "raw_link_observation_integrity_state": "verified",
        "seed_integrity_state": seed_state,
        "seed_urls": seeds,
        "classified_money_page_count": len(rows),
        "weak_route_count": weak_count,
        "unreached_from_seed_count": unreached,
        "pages": rows,
        "sitewide_reachability_claim": False,
        "sitewide_orphan_claim": False,
        "sitewide_navigation_absence_claim": False,
        "sitewide_link_absence_claim": False,
        "sitewide_link_distribution_claim": False,
        "customer_fix_created": False,
    }
