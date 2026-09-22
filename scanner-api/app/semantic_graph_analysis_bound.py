"""Single-snapshot semantic-analysis evidence boundary for NextGen Lane B.

This module composes the existing Lane-B semantic analyzers behind the published
``semantic_vector_contract_v1``. A caller-provided local vectorizer is executed
only for contract verification; every downstream analyzer consumes a sealed copy
of that same validated snapshot. This prevents clusters, cannibalization evidence,
and contextual source-to-target opportunities from observing different semantic
worlds when a buggy or stateful adapter changes between calls.

The helper is pure: it performs no network/provider work, creates no customer Fix,
and does not mutate scanner authority, persistence, repair priority, or orchestration.
"""
from __future__ import annotations

from math import isfinite
from typing import Any

from .semantic_graph import (
    CANNIBALIZATION_CANDIDATE_VERSION,
    NEAR_DUPLICATE_CANDIDATE_VERSION,
    DeterministicLocalVectorizer,
    SemanticVectorizer,
    _bounded_pages,
    cannibalization_candidates,
    near_duplicate_candidates,
    semantic_clusters,
)
from .semantic_graph_contextual import (
    CONTEXTUAL_INTERNAL_LINK_OPPORTUNITY_VERSION,
    _empty_result,
    _page_population,
    contextual_internal_link_opportunities,
)
from .semantic_graph_vector_contract import (
    SEMANTIC_VECTOR_CONTRACT_VERSION,
    semantic_vector_contract_evidence,
)


VECTOR_BOUND_SEMANTIC_ANALYSIS_VERSION = "semantic_analysis_bundle_v1_vector_bound"
VECTOR_BOUND_CLUSTER_VERSION = "semantic_cluster_evidence_v1_vector_bound"
EVIDENCE_SCOPE = "observed_assessed_pages_only"


class _SealedSemanticVectorizer:
    """Replay only the canonical vector snapshot already accepted by the contract."""

    version = "sealed_semantic_analysis_snapshot_v1"

    def __init__(self, vectors: dict[str, dict[str, float]]):
        self._vectors = {
            url: dict(vector)
            for url, vector in sorted(vectors.items())
        }

    def vectors(self, pages: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
        return {
            url: dict(vector)
            for url, vector in self._vectors.items()
        }


def _strict_threshold(value: Any, *, minimum: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} out of bounds")
    parsed = float(value)
    if not isfinite(parsed) or not minimum <= parsed <= 1.0:
        raise ValueError(f"{name} out of bounds")
    return parsed


def _cluster_not_verified(reason: str) -> dict[str, Any]:
    return {
        "version": VECTOR_BOUND_CLUSTER_VERSION,
        "scope": EVIDENCE_SCOPE,
        "state": "not_verified",
        "reason": reason,
        "vectorized_pages": 0,
        "qualifying_pair_count": 0,
        "pair_scan_complete": False,
        "clusters": [],
    }


def _near_duplicate_not_verified(reason: str) -> dict[str, Any]:
    return {
        "version": NEAR_DUPLICATE_CANDIDATE_VERSION,
        "scope": EVIDENCE_SCOPE,
        "eligible_pages": 0,
        "candidate_count": 0,
        "state": "not_verified",
        "reason": reason,
        "candidates": [],
        "candidates_truncated": False,
    }


def _cannibalization_not_verified(reason: str) -> dict[str, Any]:
    return {
        "version": CANNIBALIZATION_CANDIDATE_VERSION,
        "scope": EVIDENCE_SCOPE,
        "state": "not_verified",
        "reason": reason,
        "semantic_pair_scan_complete": False,
        "candidate_count": 0,
        "near_duplicate_filtered_count": 0,
        "near_duplicate_comparison_verified_count": 0,
        "near_duplicate_comparison_not_verified_count": 0,
        "candidates": [],
        "candidates_truncated": False,
    }


def _contextual_not_verified(reason: str) -> dict[str, Any]:
    result = _empty_result(reason)
    result["version"] = CONTEXTUAL_INTERNAL_LINK_OPPORTUNITY_VERSION
    result["graph_integrity_state"] = "not_evaluated"
    return result


def _base_result(
    *,
    semantic_evidence: dict[str, Any],
    near_duplicates: dict[str, Any],
    clusters: dict[str, Any],
    cannibalization: dict[str, Any],
    contextual: dict[str, Any],
) -> dict[str, Any]:
    graph_state = str(contextual.get("graph_integrity_state") or "not_evaluated")
    graph_reason = (
        None
        if graph_state in {"verified", "not_evaluated"}
        else str(contextual.get("reason") or "graph_not_verified")
    )
    return {
        "version": VECTOR_BOUND_SEMANTIC_ANALYSIS_VERSION,
        "scope": EVIDENCE_SCOPE,
        "semantic_vector_contract_version": SEMANTIC_VECTOR_CONTRACT_VERSION,
        "semantic_vector_integrity_state": semantic_evidence.get("state"),
        "semantic_vector_integrity_reason": semantic_evidence.get("reason"),
        "semantic_vectorizer_version": semantic_evidence.get("vectorizer_version"),
        "semantic_vectorized_pages": semantic_evidence.get("vectorized_pages", 0),
        "semantic_vector_determinism_checked": bool(
            semantic_evidence.get("determinism_checked")
        ),
        "semantic_vector_determinism_verified": bool(
            semantic_evidence.get("determinism_verified")
        ),
        "graph_integrity_state": graph_state,
        "graph_integrity_reason": graph_reason,
        "semantic_clusters": clusters,
        "near_duplicate_candidates": near_duplicates,
        "cannibalization_candidates": cannibalization,
        "contextual_internal_link_opportunities": contextual,
        "customer_fix_created": False,
    }


def vector_bound_semantic_analysis_evidence(
    pages: list[dict[str, Any]],
    graph: dict[str, Any],
    *,
    vectorizer: SemanticVectorizer | None = None,
    cluster_threshold: float = 0.62,
    cannibalization_threshold: float = 0.72,
    duplicate_threshold: float = 0.82,
    contextual_threshold: float = 0.58,
) -> dict[str, Any]:
    """Evaluate Lane-B semantic outputs from one validated semantic snapshot.

    Page identity is checked before caller-provided vectorizer code executes.
    Thresholds are strict finite numeric values (``bool`` is rejected). The
    semantic adapter is then validated exactly once under
    ``semantic_vector_contract_v1`` with repeatability checking enabled. If that
    contract fails, no semantic-dependent analyzer executes. Near-duplicate B10
    evidence remains available because it does not depend on semantic vectors.

    A graph-integrity failure is isolated to contextual link-opportunity evidence:
    semantic clusters and cannibalization evidence may still be valid because they
    do not depend on transported graph metrics.
    """
    pages = _bounded_pages(pages)
    cluster_threshold = _strict_threshold(
        cluster_threshold,
        minimum=0.0,
        name="cluster_threshold",
    )
    cannibalization_threshold = _strict_threshold(
        cannibalization_threshold,
        minimum=0.0,
        name="cannibalization_threshold",
    )
    duplicate_threshold = _strict_threshold(
        duplicate_threshold,
        minimum=0.5,
        name="duplicate_threshold",
    )
    contextual_threshold = _strict_threshold(
        contextual_threshold,
        minimum=0.0,
        name="contextual_threshold",
    )

    _, population_error = _page_population(pages)
    if population_error:
        semantic_evidence = {
            "state": "not_verified",
            "reason": population_error,
            "vectorizer_version": None,
            "vectorized_pages": 0,
            "determinism_checked": False,
            "determinism_verified": False,
        }
        reason = f"semantic_vector_{population_error}"
        return _base_result(
            semantic_evidence=semantic_evidence,
            near_duplicates=_near_duplicate_not_verified(reason),
            clusters=_cluster_not_verified(reason),
            cannibalization=_cannibalization_not_verified(reason),
            contextual=_contextual_not_verified(reason),
        )

    near_duplicates = near_duplicate_candidates(
        pages,
        threshold=duplicate_threshold,
    )
    vectorizer = vectorizer or DeterministicLocalVectorizer()
    semantic_evidence = semantic_vector_contract_evidence(
        pages,
        vectorizer,
        verify_determinism=True,
    )
    if semantic_evidence["state"] != "verified":
        reason = f"semantic_vector_{semantic_evidence['reason']}"
        return _base_result(
            semantic_evidence=semantic_evidence,
            near_duplicates=near_duplicates,
            clusters=_cluster_not_verified(reason),
            cannibalization=_cannibalization_not_verified(reason),
            contextual=_contextual_not_verified(reason),
        )

    sealed = _SealedSemanticVectorizer(semantic_evidence["vectors"])
    clusters = semantic_clusters(
        pages,
        threshold=cluster_threshold,
        vectorizer=sealed,
    )
    clusters = dict(clusters)
    clusters["version"] = VECTOR_BOUND_CLUSTER_VERSION
    clusters["state"] = (
        "candidate" if clusters.get("clusters") else (
            "not_verified"
            if not semantic_evidence.get("vectorized_pages")
            else "no_candidate_observed"
        )
    )

    cannibalization = cannibalization_candidates(
        pages,
        semantic_threshold=cannibalization_threshold,
        duplicate_threshold=duplicate_threshold,
        vectorizer=sealed,
    )
    contextual = contextual_internal_link_opportunities(
        pages,
        graph,
        semantic_threshold=contextual_threshold,
        vectorizer=sealed,
    )
    return _base_result(
        semantic_evidence=semantic_evidence,
        near_duplicates=near_duplicates,
        clusters=clusters,
        cannibalization=cannibalization,
        contextual=contextual,
    )
