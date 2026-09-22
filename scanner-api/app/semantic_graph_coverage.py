"""Truthful semantic-vector population coverage evidence for NextGen Lane B.

This pure helper separates semantic adapter integrity from evidence coverage. A
valid deterministic adapter may legitimately omit pages that have no usable local
semantic representation; that omission must remain explicit instead of being
confused with a complete pair scan across every assessed page identity.
"""
from __future__ import annotations

from typing import Any


SEMANTIC_VECTOR_COVERAGE_VERSION = "semantic_vector_coverage_v1"
EVIDENCE_SCOPE = "observed_assessed_pages_only"


def _strict_count(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def semantic_vector_coverage_evidence(
    *,
    input_page_count: Any,
    assessed_page_identity_count: Any,
    vectorized_pages: Any,
    semantic_vector_integrity_state: Any,
) -> dict[str, Any]:
    """Describe how much of the assessed population has semantic vectors.

    Coverage is deliberately separate from vector integrity. ``verified`` vector
    integrity means the transported vectors passed the local deterministic
    contract; it does not mean every assessed page identity produced a vector.
    """
    input_count = _strict_count(input_page_count)
    identity_count = _strict_count(assessed_page_identity_count)
    vector_count = _strict_count(vectorized_pages)
    integrity_state = str(semantic_vector_integrity_state or "")

    reason = None
    if input_count is None or identity_count is None or vector_count is None:
        reason = "semantic_coverage_count_invalid"
    elif identity_count > input_count:
        reason = "semantic_identity_count_exceeds_input"
    elif vector_count > identity_count:
        reason = "semantic_vector_count_exceeds_identity_population"
    elif integrity_state not in {"verified", "not_verified"}:
        reason = "semantic_vector_integrity_state_invalid"

    if reason is not None:
        return {
            "version": SEMANTIC_VECTOR_COVERAGE_VERSION,
            "scope": EVIDENCE_SCOPE,
            "state": "not_verified",
            "reason": reason,
            "input_page_count": input_count,
            "assessed_page_identity_count": identity_count,
            "vectorized_pages": vector_count,
            "page_identity_coverage_state": "not_verified",
            "semantic_vector_coverage_state": "not_verified",
            "unidentified_page_count": None,
            "unvectorized_page_identity_count": None,
            "semantic_pair_population_complete": False,
            "semantic_pair_scope": "not_verified",
            "sitewide_semantic_coverage_claim": False,
        }

    unidentified = input_count - identity_count
    unvectorized = identity_count - vector_count
    if input_count == identity_count:
        identity_coverage_state = "complete"
    elif identity_count > 0:
        identity_coverage_state = "partial"
    else:
        identity_coverage_state = "none"

    if integrity_state != "verified":
        coverage_state = "not_verified"
        coverage_reason = "semantic_vector_integrity_not_verified"
        pair_scope = "not_verified"
        pair_population_complete = False
    elif unidentified == 0 and unvectorized == 0:
        coverage_state = "complete"
        coverage_reason = "all_assessed_page_identities_vectorized"
        pair_scope = "all_assessed_page_identities"
        pair_population_complete = True
    elif vector_count > 0:
        coverage_state = "partial"
        coverage_reason = (
            "page_identity_coverage_incomplete"
            if unidentified > 0
            else "semantic_vector_population_partial"
        )
        pair_scope = "vectorized_assessed_page_subset"
        pair_population_complete = False
    else:
        coverage_state = "none"
        coverage_reason = (
            "page_identity_coverage_incomplete"
            if unidentified > 0
            else "no_semantic_vectors_available"
        )
        pair_scope = "no_vectorized_pages"
        pair_population_complete = False

    return {
        "version": SEMANTIC_VECTOR_COVERAGE_VERSION,
        "scope": EVIDENCE_SCOPE,
        "state": "verified",
        "reason": coverage_reason,
        "input_page_count": input_count,
        "assessed_page_identity_count": identity_count,
        "vectorized_pages": vector_count,
        "page_identity_coverage_state": identity_coverage_state,
        "semantic_vector_coverage_state": coverage_state,
        "unidentified_page_count": unidentified,
        "unvectorized_page_identity_count": unvectorized,
        "semantic_pair_population_complete": pair_population_complete,
        "semantic_pair_scope": pair_scope,
        "sitewide_semantic_coverage_claim": False,
    }
