"""Deterministic semantic-cluster profile evidence for NextGen Lane B.

This helper consumes already-validated Lane-B semantic vector evidence plus
vector-bound semantic cluster evidence. It performs no network/model work and
creates no customer Fix. Cluster membership is independently rebound to the
validated vector population before representative/topic evidence is emitted.
"""
from __future__ import annotations

from hashlib import sha256
from math import isfinite, sqrt
from typing import Any


SEMANTIC_CLUSTER_PROFILE_VERSION = "semantic_cluster_profile_v1_vector_bound"
VECTOR_BOUND_CLUSTER_VERSION = "semantic_cluster_evidence_v1_vector_bound"
SEMANTIC_VECTOR_CONTRACT_VERSION = "semantic_vector_contract_v1"
EVIDENCE_SCOPE = "observed_assessed_pages_only"
MAX_PROFILE_TERMS = 8


def _not_verified(reason: str, *, coverage: dict[str, Any] | None = None) -> dict[str, Any]:
    coverage = coverage or {}
    return {
        "version": SEMANTIC_CLUSTER_PROFILE_VERSION,
        "scope": EVIDENCE_SCOPE,
        "state": "not_verified",
        "reason": reason,
        "cluster_count": 0,
        "profile_count": 0,
        "profiles": [],
        "semantic_vector_coverage_state": coverage.get(
            "semantic_vector_coverage_state", "not_verified"
        ),
        "semantic_pair_population_complete": bool(
            coverage.get("semantic_pair_population_complete")
        ),
        "semantic_pair_scope": coverage.get("semantic_pair_scope", "not_verified"),
        "sitewide_semantic_coverage_claim": False,
        "customer_fix_created": False,
    }


def _validated_vectors(raw: Any) -> tuple[dict[str, dict[str, float]], str | None]:
    if not isinstance(raw, dict):
        return {}, "semantic_vector_shape_invalid"
    vectors: dict[str, dict[str, float]] = {}
    for url in sorted(raw, key=lambda value: str(value)):
        if not isinstance(url, str) or not url:
            return {}, "semantic_vector_identity_invalid"
        vector = raw[url]
        if not isinstance(vector, dict) or not vector:
            return {}, "semantic_vector_shape_invalid"
        clean: dict[str, float] = {}
        norm_sq = 0.0
        for term in sorted(vector, key=lambda value: str(value)):
            if not isinstance(term, str) or not term:
                return {}, "semantic_vector_term_invalid"
            value = vector[term]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return {}, "semantic_vector_weight_invalid"
            parsed = float(value)
            if not isfinite(parsed):
                return {}, "semantic_vector_weight_invalid"
            clean[term] = parsed
            norm_sq += parsed * parsed
        if not isfinite(norm_sq) or norm_sq <= 0.0:
            return {}, "semantic_vector_zero_norm"
        vectors[url] = clean
    return vectors, None


def _cosine(left: dict[str, float], right: dict[str, float]) -> float | None:
    shared = set(left) & set(right)
    dot = sum(left[term] * right[term] for term in shared)
    left_norm = sqrt(sum(value * value for value in left.values()))
    right_norm = sqrt(sum(value * value for value in right.values()))
    denominator = left_norm * right_norm
    if not denominator or not isfinite(denominator):
        return None
    value = dot / denominator
    return value if isfinite(value) else None


def _expected_cluster_id(urls: list[str]) -> str:
    return "sem_" + sha256("|".join(urls).encode("utf-8")).hexdigest()[:12]


def semantic_cluster_profile_evidence(
    cluster_evidence: Any,
    semantic_vector_evidence: Any,
) -> dict[str, Any]:
    """Bind cluster membership to one validated vector snapshot and profile it.

    The profile is descriptive evidence only. ``representative_url`` is the
    member nearest the deterministic cluster centroid, not a canonical-page or
    customer repair decision. ``top_terms`` are centroid-weight evidence, not a
    generated topic label or external-model assertion.
    """
    if not isinstance(semantic_vector_evidence, dict):
        return _not_verified("semantic_vector_evidence_invalid")
    coverage = semantic_vector_evidence
    if semantic_vector_evidence.get("version") != SEMANTIC_VECTOR_CONTRACT_VERSION:
        return _not_verified("semantic_vector_contract_version_mismatch", coverage=coverage)
    if semantic_vector_evidence.get("scope") != EVIDENCE_SCOPE:
        return _not_verified("semantic_vector_scope_mismatch", coverage=coverage)
    if semantic_vector_evidence.get("state") != "verified":
        return _not_verified("semantic_vector_integrity_not_verified", coverage=coverage)
    if semantic_vector_evidence.get("determinism_checked") is not True:
        return _not_verified("semantic_vector_determinism_not_checked", coverage=coverage)
    if semantic_vector_evidence.get("determinism_verified") is not True:
        return _not_verified("semantic_vector_determinism_not_verified", coverage=coverage)
    if semantic_vector_evidence.get("input_isolation_enforced") is not True:
        return _not_verified("semantic_vector_input_isolation_not_verified", coverage=coverage)

    vectors, vector_error = _validated_vectors(semantic_vector_evidence.get("vectors"))
    if vector_error:
        return _not_verified(vector_error, coverage=coverage)

    if not isinstance(cluster_evidence, dict):
        return _not_verified("semantic_cluster_evidence_invalid", coverage=coverage)
    if cluster_evidence.get("version") != VECTOR_BOUND_CLUSTER_VERSION:
        return _not_verified("semantic_cluster_version_mismatch", coverage=coverage)
    if cluster_evidence.get("scope") != EVIDENCE_SCOPE:
        return _not_verified("semantic_cluster_scope_mismatch", coverage=coverage)
    cluster_state = str(cluster_evidence.get("state") or "")
    raw_clusters = cluster_evidence.get("clusters")
    if not isinstance(raw_clusters, list):
        return _not_verified("semantic_cluster_shape_invalid", coverage=coverage)
    if cluster_state == "not_verified":
        return _not_verified("semantic_cluster_evidence_not_verified", coverage=coverage)
    if cluster_state not in {"candidate", "no_candidate_observed"}:
        return _not_verified("semantic_cluster_state_invalid", coverage=coverage)
    if cluster_state == "no_candidate_observed":
        if raw_clusters:
            return _not_verified("semantic_cluster_state_inconsistent", coverage=coverage)
        return {
            "version": SEMANTIC_CLUSTER_PROFILE_VERSION,
            "scope": EVIDENCE_SCOPE,
            "state": "no_cluster_observed",
            "reason": "no_semantic_cluster_observed",
            "cluster_count": 0,
            "profile_count": 0,
            "profiles": [],
            "semantic_vector_coverage_state": coverage.get(
                "semantic_vector_coverage_state", "not_verified"
            ),
            "semantic_pair_population_complete": bool(
                coverage.get("semantic_pair_population_complete")
            ),
            "semantic_pair_scope": coverage.get("semantic_pair_scope", "not_verified"),
            "sitewide_semantic_coverage_claim": False,
            "customer_fix_created": False,
        }
    if not raw_clusters:
        return _not_verified("semantic_cluster_state_inconsistent", coverage=coverage)

    seen_members: set[str] = set()
    canonical_clusters: list[tuple[str, list[str]]] = []
    seen_cluster_ids: set[str] = set()
    for raw in raw_clusters:
        if not isinstance(raw, dict):
            return _not_verified("semantic_cluster_row_invalid", coverage=coverage)
        cluster_id = raw.get("cluster_id")
        urls = raw.get("urls")
        page_count = raw.get("page_count")
        if not isinstance(cluster_id, str) or not isinstance(urls, list):
            return _not_verified("semantic_cluster_row_invalid", coverage=coverage)
        if isinstance(page_count, bool) or not isinstance(page_count, int):
            return _not_verified("semantic_cluster_page_count_invalid", coverage=coverage)
        if any(not isinstance(url, str) or not url for url in urls):
            return _not_verified("semantic_cluster_member_invalid", coverage=coverage)
        ordered = sorted(urls)
        if len(ordered) < 2 or len(set(ordered)) != len(ordered):
            return _not_verified("semantic_cluster_member_invalid", coverage=coverage)
        if page_count != len(ordered):
            return _not_verified("semantic_cluster_page_count_mismatch", coverage=coverage)
        if cluster_id != _expected_cluster_id(ordered):
            return _not_verified("semantic_cluster_id_mismatch", coverage=coverage)
        if cluster_id in seen_cluster_ids:
            return _not_verified("semantic_cluster_id_duplicate", coverage=coverage)
        if any(url not in vectors for url in ordered):
            return _not_verified("semantic_cluster_vector_population_mismatch", coverage=coverage)
        if any(url in seen_members for url in ordered):
            return _not_verified("semantic_cluster_member_overlap", coverage=coverage)
        seen_cluster_ids.add(cluster_id)
        seen_members.update(ordered)
        canonical_clusters.append((cluster_id, ordered))

    canonical_clusters.sort(key=lambda item: item[0])
    profiles: list[dict[str, Any]] = []
    unavailable_count = 0
    for cluster_id, members in canonical_clusters:
        centroid_sum: dict[str, float] = {}
        for url in members:
            for term, value in vectors[url].items():
                centroid_sum[term] = centroid_sum.get(term, 0.0) + value
        centroid = {
            term: value / len(members)
            for term, value in centroid_sum.items()
        }
        centroid_norm_sq = sum(value * value for value in centroid.values())
        if not isfinite(centroid_norm_sq) or centroid_norm_sq <= 0.0:
            unavailable_count += 1
            profiles.append(
                {
                    "cluster_id": cluster_id,
                    "state": "not_verified",
                    "reason": "semantic_cluster_centroid_zero_norm",
                    "page_count": len(members),
                    "urls": members,
                    "representative_url": None,
                    "member_to_centroid_similarity_min": None,
                    "member_to_centroid_similarity_mean": None,
                    "member_to_centroid_similarity_max": None,
                    "top_terms": [],
                }
            )
            continue

        similarities: list[tuple[str, float]] = []
        for url in members:
            similarity = _cosine(vectors[url], centroid)
            if similarity is None:
                unavailable_count += 1
                similarities = []
                break
            similarities.append((url, similarity))
        if not similarities:
            profiles.append(
                {
                    "cluster_id": cluster_id,
                    "state": "not_verified",
                    "reason": "semantic_cluster_centroid_similarity_invalid",
                    "page_count": len(members),
                    "urls": members,
                    "representative_url": None,
                    "member_to_centroid_similarity_min": None,
                    "member_to_centroid_similarity_mean": None,
                    "member_to_centroid_similarity_max": None,
                    "top_terms": [],
                }
            )
            continue

        representative_url = min(
            similarities,
            key=lambda item: (-item[1], item[0]),
        )[0]
        similarity_values = [value for _, value in similarities]
        top_terms = [
            {"term": term, "centroid_weight": round(value, 6)}
            for term, value in sorted(
                centroid.items(),
                key=lambda item: (-abs(item[1]), item[0]),
            )[:MAX_PROFILE_TERMS]
        ]
        profiles.append(
            {
                "cluster_id": cluster_id,
                "state": "verified",
                "reason": "validated_vector_bound_cluster_profile",
                "page_count": len(members),
                "urls": members,
                "representative_url": representative_url,
                "member_to_centroid_similarity_min": round(min(similarity_values), 6),
                "member_to_centroid_similarity_mean": round(
                    sum(similarity_values) / len(similarity_values), 6
                ),
                "member_to_centroid_similarity_max": round(max(similarity_values), 6),
                "top_terms": top_terms,
            }
        )

    verified_count = len(profiles) - unavailable_count
    if verified_count == len(profiles):
        state, reason = "verified", "validated"
    elif verified_count:
        state, reason = "partial", "some_cluster_profiles_not_verified"
    else:
        state, reason = "not_verified", "cluster_profiles_not_verified"

    return {
        "version": SEMANTIC_CLUSTER_PROFILE_VERSION,
        "scope": EVIDENCE_SCOPE,
        "state": state,
        "reason": reason,
        "cluster_count": len(canonical_clusters),
        "profile_count": len(profiles),
        "profiles": profiles,
        "semantic_vector_coverage_state": coverage.get(
            "semantic_vector_coverage_state", "not_verified"
        ),
        "semantic_pair_population_complete": bool(
            coverage.get("semantic_pair_population_complete")
        ),
        "semantic_pair_scope": coverage.get("semantic_pair_scope", "not_verified"),
        "sitewide_semantic_coverage_claim": False,
        "customer_fix_created": False,
    }
