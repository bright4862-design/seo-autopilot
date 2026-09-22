"""Cluster-profile-bound semantic-analysis evidence for NextGen Lane B.

This contract extends the published single-snapshot Lane-B analysis boundary with
deterministic semantic-cluster profile evidence. The caller-provided vectorizer is
still executed only by ``semantic_vector_contract_v1`` for integrity/repeatability
verification; cluster profiles consume the exact accepted vector snapshot and never
invoke the provider/adapter again.

The helper is pure evidence generation. It creates no customer Fix and does not
touch orchestration, repair priority, authority/persistence, projection, admission,
release, deployment, or production.
"""
from __future__ import annotations

from typing import Any

from .semantic_graph import (
    DeterministicLocalVectorizer,
    SemanticVectorizer,
    _bounded_pages,
    cannibalization_candidates,
    near_duplicate_candidates,
    semantic_clusters,
)
from .semantic_graph_analysis_bound import (
    EVIDENCE_SCOPE,
    VECTOR_BOUND_CLUSTER_VERSION,
    _SealedSemanticVectorizer,
    _base_result,
    _cannibalization_not_verified,
    _cluster_not_verified,
    _contextual_not_verified,
    _near_duplicate_not_verified,
    _strict_threshold,
)
from .semantic_graph_cluster_profile import (
    SEMANTIC_CLUSTER_PROFILE_VERSION,
    semantic_cluster_profile_evidence,
)
from .semantic_graph_contextual import (
    _page_population,
    contextual_internal_link_opportunities,
)
from .semantic_graph_coverage import (
    SEMANTIC_VECTOR_COVERAGE_VERSION,
    semantic_vector_coverage_evidence,
)
from .semantic_graph_vector_contract import (
    SEMANTIC_VECTOR_CONTRACT_VERSION,
    semantic_vector_contract_evidence,
)


CLUSTER_PROFILE_BOUND_SEMANTIC_ANALYSIS_VERSION = (
    "semantic_analysis_bundle_v3_cluster_profile_bound"
)


def _result(
    *,
    semantic_evidence: dict[str, Any],
    near_duplicates: dict[str, Any],
    clusters: dict[str, Any],
    cannibalization: dict[str, Any],
    contextual: dict[str, Any],
    cluster_profile: dict[str, Any],
) -> dict[str, Any]:
    result = _base_result(
        semantic_evidence=semantic_evidence,
        near_duplicates=near_duplicates,
        clusters=clusters,
        cannibalization=cannibalization,
        contextual=contextual,
    )
    result["version"] = CLUSTER_PROFILE_BOUND_SEMANTIC_ANALYSIS_VERSION
    result["semantic_cluster_profile_version"] = SEMANTIC_CLUSTER_PROFILE_VERSION
    result["semantic_cluster_profile"] = cluster_profile
    return result


def _population_error_semantic_evidence(
    *,
    input_page_count: int,
    reason: str,
) -> dict[str, Any]:
    coverage = semantic_vector_coverage_evidence(
        input_page_count=input_page_count,
        assessed_page_identity_count=0,
        vectorized_pages=0,
        semantic_vector_integrity_state="not_verified",
    )
    return {
        "version": SEMANTIC_VECTOR_CONTRACT_VERSION,
        "scope": EVIDENCE_SCOPE,
        "state": "not_verified",
        "reason": reason,
        "vectorizer_version": None,
        "input_page_count": input_page_count,
        "assessed_page_identity_count": 0,
        "vectorized_pages": 0,
        "vectors": {},
        "determinism_checked": False,
        "determinism_verified": False,
        "input_isolation_enforced": True,
        "semantic_vector_coverage_version": SEMANTIC_VECTOR_COVERAGE_VERSION,
        "semantic_vector_coverage": coverage,
        "page_identity_coverage_state": coverage["page_identity_coverage_state"],
        "semantic_vector_coverage_state": coverage["semantic_vector_coverage_state"],
        "unidentified_page_count": coverage["unidentified_page_count"],
        "unvectorized_page_identity_count": coverage[
            "unvectorized_page_identity_count"
        ],
        "semantic_pair_population_complete": coverage[
            "semantic_pair_population_complete"
        ],
        "semantic_pair_scope": coverage["semantic_pair_scope"],
        "sitewide_semantic_coverage_claim": False,
    }


def cluster_profile_bound_semantic_analysis_evidence(
    pages: list[dict[str, Any]],
    graph: dict[str, Any],
    *,
    vectorizer: SemanticVectorizer | None = None,
    cluster_threshold: float = 0.62,
    cannibalization_threshold: float = 0.72,
    duplicate_threshold: float = 0.82,
    contextual_threshold: float = 0.58,
) -> dict[str, Any]:
    """Evaluate semantic outputs and cluster profiles from one accepted snapshot.

    The adapter is invoked at most twice: both invocations belong to
    ``semantic_vector_contract_v1`` and exist solely to verify repeatability and
    input isolation. Every semantic consumer after that point receives the sealed
    accepted snapshot. Near-duplicate evidence remains independent because it is
    based on verified main-content shingles rather than semantic vectors.
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
        semantic_evidence = _population_error_semantic_evidence(
            input_page_count=len(pages),
            reason=population_error,
        )
        reason = f"semantic_vector_{population_error}"
        clusters = _cluster_not_verified(reason)
        cluster_profile = semantic_cluster_profile_evidence(
            clusters,
            semantic_evidence,
        )
        return _result(
            semantic_evidence=semantic_evidence,
            near_duplicates=_near_duplicate_not_verified(reason),
            clusters=clusters,
            cannibalization=_cannibalization_not_verified(reason),
            contextual=_contextual_not_verified(reason),
            cluster_profile=cluster_profile,
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
        clusters = _cluster_not_verified(reason)
        cluster_profile = semantic_cluster_profile_evidence(
            clusters,
            semantic_evidence,
        )
        return _result(
            semantic_evidence=semantic_evidence,
            near_duplicates=near_duplicates,
            clusters=clusters,
            cannibalization=_cannibalization_not_verified(reason),
            contextual=_contextual_not_verified(reason),
            cluster_profile=cluster_profile,
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
        "candidate"
        if clusters.get("clusters")
        else (
            "not_verified"
            if not semantic_evidence.get("vectorized_pages")
            else "no_candidate_observed"
        )
    )
    cluster_profile = semantic_cluster_profile_evidence(
        clusters,
        semantic_evidence,
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
    return _result(
        semantic_evidence=semantic_evidence,
        near_duplicates=near_duplicates,
        clusters=clusters,
        cannibalization=cannibalization,
        contextual=contextual,
        cluster_profile=cluster_profile,
    )
