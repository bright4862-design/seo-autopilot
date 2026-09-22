"""Vector-integrity-bound contextual-link opportunity evidence for NextGen Lane B.

The original contextual opportunity helper validates graph identity/integrity before
using graph metrics, but its pluggable semantic adapter remains a caller-provided
runtime dependency. This wrapper binds the semantic adapter through the published
``semantic_vector_contract_v1`` first, then delegates with a sealed vector
snapshot. Invalid, foreign-population, malformed, or nondeterministic semantic
vectors therefore fail closed before they can influence source-to-target
opportunity evidence.

This module is pure: it performs no network/provider work, creates no customer Fix,
and makes no sitewide link-absence claim.
"""
from __future__ import annotations

from typing import Any

from .semantic_graph import (
    DeterministicLocalVectorizer,
    SemanticVectorizer,
    _bounded_pages,
)
from .semantic_graph_contextual import (
    _empty_result,
    _page_population,
    _validated_graph,
    contextual_internal_link_opportunities,
)
from .semantic_graph_vector_contract import (
    SEMANTIC_VECTOR_CONTRACT_VERSION,
    semantic_vector_contract_evidence,
)


VECTOR_BOUND_CONTEXTUAL_OPPORTUNITY_VERSION = (
    "contextual_internal_link_opportunity_v2_vector_bound"
)


class _SealedSemanticVectorizer:
    """Return only the already-validated semantic snapshot.

    The underlying adapter is deliberately not consulted again after the contract
    has verified repeatability. This prevents a third, different adapter result
    from influencing the delegated contextual analyzer.
    """

    version = "sealed_semantic_vector_snapshot_v1"

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


def _upgrade_result(
    result: dict[str, Any],
    *,
    semantic_state: str,
    semantic_reason: str,
    vectorizer_version: str | None,
    determinism_checked: bool,
    determinism_verified: bool,
) -> dict[str, Any]:
    upgraded = dict(result)
    upgraded["version"] = VECTOR_BOUND_CONTEXTUAL_OPPORTUNITY_VERSION
    upgraded["semantic_vector_integrity_state"] = semantic_state
    upgraded["semantic_vector_integrity_reason"] = semantic_reason
    upgraded["semantic_vector_contract_version"] = SEMANTIC_VECTOR_CONTRACT_VERSION
    upgraded["semantic_vectorizer_version"] = vectorizer_version
    upgraded["semantic_vector_determinism_checked"] = determinism_checked
    upgraded["semantic_vector_determinism_verified"] = determinism_verified
    upgraded["customer_fix_created"] = False
    return upgraded


def vector_bound_contextual_internal_link_opportunities(
    pages: list[dict[str, Any]],
    graph: dict[str, Any],
    *,
    semantic_threshold: float = 0.58,
    vectorizer: SemanticVectorizer | None = None,
) -> dict[str, Any]:
    """Return source-to-target contextual-link evidence bound to validated vectors.

    Graph validation deliberately happens before executing a caller-provided
    semantic adapter. If the graph is ambiguous or foreign-population evidence, no
    vectorizer code is executed. Once graph evidence is verified, the adapter is
    validated for population, numeric shape, bounds, and repeatability under
    ``semantic_vector_contract_v1``. Only the resulting sealed snapshot is passed
    to the contextual analyzer.
    """
    pages = _bounded_pages(pages)

    by_url, population_error = _page_population(pages)
    if population_error:
        return _upgrade_result(
            _empty_result(population_error),
            semantic_state="not_evaluated",
            semantic_reason="page_population_not_verified",
            vectorizer_version=None,
            determinism_checked=False,
            determinism_verified=False,
        )

    _, _, graph_error = _validated_graph(set(by_url), graph)
    if graph_error:
        return _upgrade_result(
            _empty_result(graph_error),
            semantic_state="not_evaluated",
            semantic_reason="graph_not_verified",
            vectorizer_version=None,
            determinism_checked=False,
            determinism_verified=False,
        )

    vectorizer = vectorizer or DeterministicLocalVectorizer()
    semantic_evidence = semantic_vector_contract_evidence(
        pages,
        vectorizer,
        verify_determinism=True,
    )
    if semantic_evidence["state"] != "verified":
        failed = _empty_result(f"semantic_vector_{semantic_evidence['reason']}")
        failed["graph_integrity_state"] = "verified"
        return _upgrade_result(
            failed,
            semantic_state="not_verified",
            semantic_reason=str(semantic_evidence["reason"]),
            vectorizer_version=semantic_evidence.get("vectorizer_version"),
            determinism_checked=bool(
                semantic_evidence.get("determinism_checked")
            ),
            determinism_verified=bool(
                semantic_evidence.get("determinism_verified")
            ),
        )

    sealed = _SealedSemanticVectorizer(semantic_evidence["vectors"])
    result = contextual_internal_link_opportunities(
        pages,
        graph,
        semantic_threshold=semantic_threshold,
        vectorizer=sealed,
    )
    return _upgrade_result(
        result,
        semantic_state="verified",
        semantic_reason="validated",
        vectorizer_version=semantic_evidence.get("vectorizer_version"),
        determinism_checked=bool(
            semantic_evidence.get("determinism_checked")
        ),
        determinism_verified=bool(
            semantic_evidence.get("determinism_verified")
        ),
    )
