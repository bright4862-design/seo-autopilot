"""Semantic-cluster context for weighted contextual internal-link opportunities.

This Lane-B helper binds already-produced weighted contextual source→target
candidate evidence to the already-validated semantic-cluster profile. It performs
no crawl, provider/model work, persistence, ranking, customer Fix creation, or
sitewide reachability/coverage inference.
"""
from __future__ import annotations

from typing import Any

from .semantic_graph_cluster_profile import SEMANTIC_CLUSTER_PROFILE_VERSION
from .semantic_graph_opportunity_weighted_route import (
    WEIGHTED_ROUTE_CONTEXTUAL_OPPORTUNITY_VERSION,
    WEIGHTED_ROUTE_EVIDENCE_SCOPE,
)


CLUSTER_CONTEXTUAL_OPPORTUNITY_VERSION = (
    "template_contextual_internal_link_opportunity_v5_semantic_cluster_bound"
)
EVIDENCE_SCOPE = "observed_assessed_pages_only"


def _empty_result(
    reason: str,
    *,
    weighted_route_verified: bool = False,
    cluster_profile_verified: bool = False,
) -> dict[str, Any]:
    return {
        "version": CLUSTER_CONTEXTUAL_OPPORTUNITY_VERSION,
        "scope": EVIDENCE_SCOPE,
        "state": "not_verified",
        "reason": reason,
        "weighted_route_integrity_state": (
            "verified" if weighted_route_verified else "not_verified"
        ),
        "semantic_cluster_profile_integrity_state": (
            "verified" if cluster_profile_verified else "not_verified"
        ),
        "candidate_count": 0,
        "candidates": [],
        "candidates_truncated": False,
        "cluster_context_evaluated_candidate_count": 0,
        "cluster_context_candidate_population_complete": False,
        "semantic_pair_population_complete": False,
        "semantic_vector_coverage_state": "not_verified",
        "sitewide_semantic_coverage_claim": False,
        "sitewide_reachability_claim": False,
        "sitewide_orphan_claim": False,
        "sitewide_link_absence_claim": False,
        "sitewide_template_flow_claim": False,
        "sitewide_link_distribution_claim": False,
        "customer_fix_created": False,
    }


def _strict_non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _validated_weighted_routes(
    evidence: Any,
) -> tuple[list[dict[str, Any]], int, bool, str | None]:
    if not isinstance(evidence, dict):
        return [], 0, False, "weighted_route_evidence_invalid"
    if evidence.get("version") != WEIGHTED_ROUTE_CONTEXTUAL_OPPORTUNITY_VERSION:
        return [], 0, False, "weighted_route_version_mismatch"
    if evidence.get("scope") != EVIDENCE_SCOPE:
        return [], 0, False, "weighted_route_scope_mismatch"
    if evidence.get("state") == "not_verified":
        return [], 0, False, "weighted_route_not_verified"
    if evidence.get("state") not in {"candidate", "no_candidate_observed"}:
        return [], 0, False, "weighted_route_state_invalid"
    if evidence.get("graph_neighborhood_integrity_state") != "verified":
        return [], 0, False, "weighted_route_neighborhood_integrity_not_verified"
    if evidence.get("graph_integrity_state") != "verified":
        return [], 0, False, "weighted_route_graph_integrity_not_verified"
    if evidence.get("weighted_route_evidence_scope") != WEIGHTED_ROUTE_EVIDENCE_SCOPE:
        return [], 0, False, "weighted_route_evidence_scope_mismatch"

    for field in (
        "sitewide_reachability_claim",
        "sitewide_orphan_claim",
        "sitewide_link_absence_claim",
        "sitewide_template_flow_claim",
        "sitewide_link_distribution_claim",
        "customer_fix_created",
    ):
        if evidence.get(field) is not False:
            return [], 0, False, f"weighted_route_{field}_invalid"

    candidates = evidence.get("candidates")
    candidate_count = _strict_non_negative_int(evidence.get("candidate_count"))
    truncated = evidence.get("candidates_truncated")
    evaluated = _strict_non_negative_int(
        evidence.get("weighted_route_evaluated_candidate_count")
    )
    population_complete = evidence.get("weighted_route_candidate_population_complete")
    if (
        not isinstance(candidates, list)
        or candidate_count is None
        or not isinstance(truncated, bool)
        or evaluated is None
        or not isinstance(population_complete, bool)
    ):
        return [], 0, False, "weighted_route_shape_invalid"
    if candidate_count < len(candidates) or evaluated != len(candidates):
        return [], 0, False, "weighted_route_candidate_count_mismatch"
    if truncated != (candidate_count > len(candidates)):
        return [], 0, False, "weighted_route_truncation_mismatch"
    if population_complete != (not truncated):
        return [], 0, False, "weighted_route_population_complete_mismatch"
    expected_state = "candidate" if candidates else "no_candidate_observed"
    if evidence.get("state") != expected_state:
        return [], 0, False, "weighted_route_state_mismatch"

    seen: set[tuple[str, str]] = set()
    validated: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            return [], 0, False, "weighted_route_candidate_invalid"
        source = candidate.get("source_url")
        target = candidate.get("target_url")
        if (
            not isinstance(source, str)
            or not source
            or not isinstance(target, str)
            or not target
            or source == target
            or (source, target) in seen
        ):
            return [], 0, False, "weighted_route_candidate_identity_invalid"
        seen.add((source, target))
        if candidate.get("evidence_scope") != EVIDENCE_SCOPE:
            return [], 0, False, "weighted_route_candidate_scope_mismatch"
        if candidate.get("weighted_route_evidence_scope") != WEIGHTED_ROUTE_EVIDENCE_SCOPE:
            return [], 0, False, "weighted_route_candidate_route_scope_mismatch"
        for field in (
            "sitewide_reachability_claim",
            "sitewide_orphan_claim",
            "sitewide_link_absence_claim",
            "sitewide_template_flow_claim",
            "sitewide_link_distribution_claim",
        ):
            if candidate.get(field) is not False:
                return [], 0, False, f"weighted_route_candidate_{field}_invalid"
        validated.append(candidate)

    return validated, candidate_count, truncated, None


def _validated_cluster_profiles(
    evidence: Any,
) -> tuple[dict[str, dict[str, Any]], dict[str, str], str | None]:
    if not isinstance(evidence, dict):
        return {}, {}, "semantic_cluster_profile_evidence_invalid"
    if evidence.get("version") != SEMANTIC_CLUSTER_PROFILE_VERSION:
        return {}, {}, "semantic_cluster_profile_version_mismatch"
    if evidence.get("scope") != EVIDENCE_SCOPE:
        return {}, {}, "semantic_cluster_profile_scope_mismatch"
    if evidence.get("state") == "not_verified":
        return {}, {}, "semantic_cluster_profile_not_verified"
    if evidence.get("state") not in {"verified", "partial", "no_cluster_observed"}:
        return {}, {}, "semantic_cluster_profile_state_invalid"
    if evidence.get("sitewide_semantic_coverage_claim") is not False:
        return {}, {}, "semantic_cluster_profile_sitewide_semantic_coverage_claim_invalid"
    if evidence.get("customer_fix_created") is not False:
        return {}, {}, "semantic_cluster_profile_customer_fix_created_invalid"

    cluster_count = _strict_non_negative_int(evidence.get("cluster_count"))
    profile_count = _strict_non_negative_int(evidence.get("profile_count"))
    profiles = evidence.get("profiles")
    if cluster_count is None or profile_count is None or not isinstance(profiles, list):
        return {}, {}, "semantic_cluster_profile_shape_invalid"
    if cluster_count != profile_count or profile_count != len(profiles):
        return {}, {}, "semantic_cluster_profile_count_mismatch"
    if evidence.get("state") == "no_cluster_observed":
        if profiles:
            return {}, {}, "semantic_cluster_profile_state_mismatch"
        return {}, {}, None
    if not profiles:
        return {}, {}, "semantic_cluster_profile_state_mismatch"

    by_cluster: dict[str, dict[str, Any]] = {}
    membership: dict[str, str] = {}
    verified_profiles = 0
    for profile in profiles:
        if not isinstance(profile, dict):
            return {}, {}, "semantic_cluster_profile_row_invalid"
        cluster_id = profile.get("cluster_id")
        urls = profile.get("urls")
        page_count = _strict_non_negative_int(profile.get("page_count"))
        state = profile.get("state")
        if (
            not isinstance(cluster_id, str)
            or not cluster_id
            or cluster_id in by_cluster
            or not isinstance(urls, list)
            or page_count is None
            or state not in {"verified", "not_verified"}
        ):
            return {}, {}, "semantic_cluster_profile_row_invalid"
        if page_count < 2 or page_count != len(urls):
            return {}, {}, "semantic_cluster_profile_page_count_mismatch"
        if any(not isinstance(url, str) or not url for url in urls):
            return {}, {}, "semantic_cluster_profile_member_invalid"
        if len(set(urls)) != len(urls):
            return {}, {}, "semantic_cluster_profile_member_invalid"
        if any(url in membership for url in urls):
            return {}, {}, "semantic_cluster_profile_member_overlap"

        representative = profile.get("representative_url")
        if state == "verified":
            verified_profiles += 1
            if not isinstance(representative, str) or representative not in urls:
                return {}, {}, "semantic_cluster_profile_representative_invalid"
        elif representative is not None:
            return {}, {}, "semantic_cluster_profile_representative_invalid"

        canonical = dict(profile)
        canonical["urls"] = sorted(urls)
        by_cluster[cluster_id] = canonical
        for url in urls:
            membership[url] = cluster_id

    expected_state = (
        "verified"
        if verified_profiles == len(profiles)
        else "partial"
        if verified_profiles
        else "not_verified"
    )
    if evidence.get("state") != expected_state:
        return {}, {}, "semantic_cluster_profile_state_mismatch"
    return by_cluster, membership, None


def _relation(source_cluster: str | None, target_cluster: str | None) -> str:
    if source_cluster and target_cluster:
        return "same_cluster" if source_cluster == target_cluster else "different_clusters"
    if source_cluster:
        return "source_cluster_only"
    if target_cluster:
        return "target_cluster_only"
    return "unclustered_pair"


def cluster_context_internal_link_opportunities(
    weighted_route_opportunities: dict[str, Any],
    semantic_cluster_profile: dict[str, Any],
) -> dict[str, Any]:
    """Annotate contextual candidates with deterministic semantic-cluster context."""
    candidates, candidate_count, truncated, route_error = _validated_weighted_routes(
        weighted_route_opportunities
    )
    if route_error:
        return _empty_result(route_error)

    profiles, membership, profile_error = _validated_cluster_profiles(
        semantic_cluster_profile
    )
    if profile_error:
        return _empty_result(profile_error, weighted_route_verified=True)

    coverage_state = str(
        semantic_cluster_profile.get("semantic_vector_coverage_state") or "not_verified"
    )
    pair_complete = bool(
        semantic_cluster_profile.get("semantic_pair_population_complete")
    )
    pair_scope = semantic_cluster_profile.get("semantic_pair_scope")

    enriched: list[dict[str, Any]] = []
    for candidate in candidates:
        source = candidate["source_url"]
        target = candidate["target_url"]
        source_cluster = membership.get(source)
        target_cluster = membership.get(target)
        source_profile = profiles.get(source_cluster) if source_cluster else None
        target_profile = profiles.get(target_cluster) if target_cluster else None
        relation = _relation(source_cluster, target_cluster)

        row = dict(candidate)
        row.update(
            {
                "semantic_cluster_relation": relation,
                "source_semantic_cluster_id": source_cluster,
                "target_semantic_cluster_id": target_cluster,
                "source_semantic_cluster_profile_state": (
                    source_profile.get("state") if source_profile else "not_clustered"
                ),
                "target_semantic_cluster_profile_state": (
                    target_profile.get("state") if target_profile else "not_clustered"
                ),
                "source_semantic_cluster_representative_url": (
                    source_profile.get("representative_url") if source_profile else None
                ),
                "target_semantic_cluster_representative_url": (
                    target_profile.get("representative_url") if target_profile else None
                ),
                "source_is_semantic_cluster_representative": bool(
                    source_profile
                    and source_profile.get("representative_url") == source
                ),
                "target_is_semantic_cluster_representative": bool(
                    target_profile
                    and target_profile.get("representative_url") == target
                ),
                "semantic_cluster_profile_version": SEMANTIC_CLUSTER_PROFILE_VERSION,
                "semantic_cluster_profile_evidence_scope": EVIDENCE_SCOPE,
                "semantic_vector_coverage_state": coverage_state,
                "semantic_pair_population_complete": pair_complete,
                "semantic_pair_scope": pair_scope,
                "sitewide_semantic_coverage_claim": False,
                "customer_fix_created": False,
            }
        )
        enriched.append(row)

    return {
        "version": CLUSTER_CONTEXTUAL_OPPORTUNITY_VERSION,
        "scope": EVIDENCE_SCOPE,
        "state": "candidate" if enriched else "no_candidate_observed",
        "reason": "validated",
        "weighted_route_integrity_state": "verified",
        "semantic_cluster_profile_integrity_state": "verified",
        "semantic_cluster_profile_version": SEMANTIC_CLUSTER_PROFILE_VERSION,
        "candidate_count": candidate_count,
        "candidates": enriched,
        "candidates_truncated": truncated,
        "cluster_context_evaluated_candidate_count": len(enriched),
        "cluster_context_candidate_population_complete": not truncated,
        "semantic_vector_coverage_state": coverage_state,
        "semantic_pair_population_complete": pair_complete,
        "semantic_pair_scope": pair_scope,
        "sitewide_semantic_coverage_claim": False,
        "sitewide_reachability_claim": False,
        "sitewide_orphan_claim": False,
        "sitewide_link_absence_claim": False,
        "sitewide_template_flow_claim": False,
        "sitewide_link_distribution_claim": False,
        "customer_fix_created": False,
    }
