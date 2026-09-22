"""Versioned integrity contract for pluggable/local semantic vectors.

Lane B is allowed to consume deterministic local semantic adapters, but candidate
quality must not depend on trusting arbitrary transported vector dictionaries.
This module validates adapter identity, assessed-page population, numeric shape,
bounds, repeatability, input purity, and explicit population coverage without
network calls or customer-facing decisions.
"""
from __future__ import annotations

from copy import deepcopy
from math import isfinite, sqrt
from typing import Any

from .semantic_graph import _url
from .semantic_graph_coverage import (
    SEMANTIC_VECTOR_COVERAGE_VERSION,
    semantic_vector_coverage_evidence,
)


SEMANTIC_VECTOR_CONTRACT_VERSION = "semantic_vector_contract_v1"
VALIDATED_VECTOR_ADAPTER_VERSION = "validated_semantic_vectorizer_v1"
EVIDENCE_SCOPE = "observed_assessed_pages_only"
MAX_PAGES = 1_000
MAX_DIMENSIONS_PER_PAGE = 2_048
MAX_TERM_LENGTH = 128
MAX_VECTORIZER_VERSION_LENGTH = 128
MAX_ABS_WEIGHT = 1.0e12


class SemanticVectorContractError(ValueError):
    """Raised by the strict adapter when semantic evidence fails closed."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _page_url(page: dict[str, Any]) -> str:
    """Use the same page-identity normalization as the semantic graph.

    Every Lane-B boundary must agree on page identity before semantic evidence can
    be transported. Reusing ``semantic_graph._url`` prevents the vector contract
    from accepting a different identity string than graph/contextual analyzers for
    values containing internal whitespace.
    """
    for key in ("url", "final_url", "page_url"):
        text = _url(page.get(key))
        if text:
            return text
    return ""


def _assessed_population(pages: Any) -> tuple[set[str], str | None]:
    if not isinstance(pages, list) or len(pages) > MAX_PAGES:
        return set(), "page_population_invalid"
    urls: set[str] = set()
    for page in pages:
        if not isinstance(page, dict):
            return set(), "page_population_invalid"
        url = _page_url(page)
        if not url:
            continue
        if url in urls:
            return set(), "duplicate_page_identity"
        urls.add(url)
    return urls, None


def _version(vectorizer: Any) -> tuple[str, str | None]:
    value = getattr(vectorizer, "version", None)
    if not isinstance(value, str):
        return "", "vectorizer_version_invalid"
    value = value.strip()
    if not value or len(value) > MAX_VECTORIZER_VERSION_LENGTH:
        return "", "vectorizer_version_invalid"
    return value, None


def _canonical_vectors(raw: Any, allowed_urls: set[str]) -> tuple[dict[str, dict[str, float]], str | None]:
    if not isinstance(raw, dict):
        return {}, "vector_shape_invalid"
    if len(raw) > len(allowed_urls):
        return {}, "vector_population_mismatch"

    canonical: dict[str, dict[str, float]] = {}
    for raw_url in sorted(raw, key=lambda value: str(value)):
        if not isinstance(raw_url, str) or raw_url not in allowed_urls:
            return {}, "vector_population_mismatch"
        vector = raw[raw_url]
        if not isinstance(vector, dict) or not vector:
            return {}, "vector_shape_invalid"
        if len(vector) > MAX_DIMENSIONS_PER_PAGE:
            return {}, "vector_dimension_limit_exceeded"

        clean: dict[str, float] = {}
        magnitude_sq = 0.0
        for term in sorted(vector, key=lambda value: str(value)):
            if not isinstance(term, str):
                return {}, "vector_term_invalid"
            if term != term.strip() or not term or len(term) > MAX_TERM_LENGTH:
                return {}, "vector_term_invalid"
            weight = vector[term]
            if isinstance(weight, bool) or not isinstance(weight, (int, float)):
                return {}, "vector_weight_invalid"
            parsed = float(weight)
            if not isfinite(parsed) or abs(parsed) > MAX_ABS_WEIGHT:
                return {}, "vector_weight_invalid"
            clean[term] = parsed
            magnitude_sq += parsed * parsed
        if not isfinite(magnitude_sq) or sqrt(magnitude_sq) == 0.0:
            return {}, "vector_zero_norm"
        canonical[raw_url] = clean
    return canonical, None


def _isolated_vectorizer_call(
    vectorizer: Any,
    pages: Any,
) -> tuple[Any, str | None]:
    """Execute one adapter call against an isolated page snapshot.

    Caller-owned page evidence is never passed to pluggable adapter code. An
    adapter that mutates its private input snapshot is treated as contract-invalid
    even when it restores deterministic vector output, because downstream Lane-B
    analyzers require semantic adapters to behave as pure evidence readers.
    """
    try:
        isolated_pages = deepcopy(pages)
        baseline = deepcopy(isolated_pages)
    except Exception:
        return None, "page_snapshot_error"

    try:
        raw = vectorizer.vectors(isolated_pages)
    except Exception:
        return None, "vectorizer_execution_error"

    try:
        mutated = isolated_pages != baseline
    except Exception:
        return None, "page_snapshot_comparison_error"
    if mutated:
        return None, "vectorizer_input_mutation"
    return raw, None


def semantic_vector_contract_evidence(
    pages: Any,
    vectorizer: Any,
    *,
    verify_determinism: bool = True,
) -> dict[str, Any]:
    """Validate one local/pluggable semantic adapter without trusting its output.

    Invalid or ambiguous evidence returns ``not_verified`` and never transports
    the untrusted vectors. Adapter code only receives deep-copied page snapshots;
    mutation of either invocation is rejected as ``vectorizer_input_mutation``.
    With determinism verification enabled, the adapter is invoked twice against
    fresh equivalent snapshots and both canonical outputs must be exactly equal.

    Adapter integrity is deliberately distinct from semantic population coverage.
    A deterministic adapter may return vectors for only a subset of assessed page
    identities; that subset remains valid evidence, but the returned coverage
    contract makes it explicit that pair analysis is not complete for the whole
    assessed population.
    """
    population, reason = _assessed_population(pages)
    version, version_reason = _version(vectorizer)
    reason = reason or version_reason
    vectors: dict[str, dict[str, float]] = {}
    determinism_verified = False

    if reason is None and not callable(getattr(vectorizer, "vectors", None)):
        reason = "vectorizer_interface_invalid"

    if reason is None:
        first_raw, reason = _isolated_vectorizer_call(vectorizer, pages)
        if reason is None:
            vectors, reason = _canonical_vectors(first_raw, population)

    if reason is None and verify_determinism:
        second_raw, second_call_reason = _isolated_vectorizer_call(vectorizer, pages)
        if second_call_reason is not None:
            reason = second_call_reason
        else:
            second, second_reason = _canonical_vectors(second_raw, population)
            if second_reason is not None:
                reason = second_reason
            elif vectors != second:
                reason = "vectorizer_nondeterministic"
            else:
                determinism_verified = True
    elif reason is None:
        determinism_verified = False

    if reason is not None:
        vectors = {}

    integrity_state = "verified" if reason is None else "not_verified"
    input_page_count = len(pages) if isinstance(pages, list) else 0
    coverage = semantic_vector_coverage_evidence(
        input_page_count=input_page_count,
        assessed_page_identity_count=len(population),
        vectorized_pages=len(vectors),
        semantic_vector_integrity_state=integrity_state,
    )

    return {
        "version": SEMANTIC_VECTOR_CONTRACT_VERSION,
        "scope": EVIDENCE_SCOPE,
        "state": integrity_state,
        "reason": "validated" if reason is None else reason,
        "vectorizer_version": version or None,
        "input_page_count": input_page_count,
        "assessed_page_identity_count": len(population),
        "vectorized_pages": len(vectors),
        "determinism_checked": bool(verify_determinism),
        "determinism_verified": bool(determinism_verified),
        "input_isolation_enforced": True,
        "semantic_vector_coverage_version": SEMANTIC_VECTOR_COVERAGE_VERSION,
        "semantic_vector_coverage": coverage,
        "page_identity_coverage_state": coverage["page_identity_coverage_state"],
        "semantic_vector_coverage_state": coverage["semantic_vector_coverage_state"],
        "unidentified_page_count": coverage["unidentified_page_count"],
        "unvectorized_page_identity_count": coverage["unvectorized_page_identity_count"],
        "semantic_pair_population_complete": coverage["semantic_pair_population_complete"],
        "semantic_pair_scope": coverage["semantic_pair_scope"],
        "sitewide_semantic_coverage_claim": False,
        "vectors": vectors,
        "customer_fix_created": False,
    }


class ValidatedSemanticVectorizer:
    """Strict adapter that can be passed to existing Lane-B semantic analyzers.

    It preserves the existing ``vectors(pages)`` interface while refusing to
    return ambiguous, malformed, foreign-population, mutating, or nondeterministic
    vectors. This is intentionally local/pure; it performs no provider or network
    call and never exposes caller-owned page objects to the delegate.
    """

    def __init__(self, delegate: Any, *, verify_determinism: bool = True):
        self.delegate = delegate
        self.verify_determinism = verify_determinism
        delegate_version, _ = _version(delegate)
        self.version = f"{VALIDATED_VECTOR_ADAPTER_VERSION}:{delegate_version or 'unknown'}"

    def evidence(self, pages: Any) -> dict[str, Any]:
        return semantic_vector_contract_evidence(
            pages,
            self.delegate,
            verify_determinism=self.verify_determinism,
        )

    def vectors(self, pages: Any) -> dict[str, dict[str, float]]:
        evidence = self.evidence(pages)
        if evidence["state"] != "verified":
            raise SemanticVectorContractError(str(evidence["reason"]))
        return {url: dict(vector) for url, vector in evidence["vectors"].items()}