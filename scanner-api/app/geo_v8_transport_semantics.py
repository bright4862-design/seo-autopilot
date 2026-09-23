"""Fail-closed v1 arithmetic/gate revalidation for GEO V8 pre-seal transport.

The transport candidate digest is deliberately non-authoritative. Before a
serialized integrator seals candidate bytes, this adapter independently derives
v1-compatible score/coverage/status/bounds/reasons from transported check counts
and exact upstream gate facts. It performs no fetch, scoring-policy change,
persistence, projection, sealing, or provider/model call.
"""
from __future__ import annotations

import json

from .geo_readiness import CHECKS, DIMENSIONS, Observation, evaluate_geo
from .geo_v8_transport_candidate import validate_geo_v8_transport_candidate

_V1_COMPAT_FIELDS = (
    "assessment_status",
    "score",
    "coverage",
    "score_bounds",
    "bounds_kind",
    "sample_pages",
    "dimensions",
    "reasons",
    "authority_verified",
)


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _explicit_gates(*, parent_authoritative: bool, entry_verified: bool, access_limited: bool):
    gates = (parent_authoritative, entry_verified, access_limited)
    if any(type(value) is not bool for value in gates):
        raise ValueError("Exact GEO pre-seal validation requires three boolean gate facts")
    return gates


def _count_equivalent_matrix(readiness: dict) -> tuple[list[str], list[Observation]]:
    sample_pages = readiness["sample_pages"]
    page_ids = [f"transport-arithmetic-page-{index}" for index in range(sample_pages)]
    if readiness["observation_scope"]["access_limited"]:
        return page_ids, []

    unknown_by_check = {check_id: 0 for check_id in CHECKS}
    for row in readiness["unknown_cells"]:
        check_id = row["check_id"]
        if check_id not in unknown_by_check:
            raise ValueError("Malformed GEO unknown-cell check identity")
        unknown_by_check[check_id] += 1

    observations = []
    state_order = ("pass", "fail", "not_applicable", "not_verified")
    for check_id, dimension in CHECKS.items():
        detail = readiness["dimensions"].get(dimension)
        if not isinstance(detail, dict):
            raise ValueError("Malformed GEO dimension transport")
        check = detail.get("checks", {}).get(check_id)
        if not isinstance(check, dict):
            raise ValueError("Malformed GEO check transport")
        counts = check.get("counts")
        if not isinstance(counts, dict) or any(type(counts.get(state)) is not int for state in state_order):
            raise ValueError("Malformed GEO check counts")
        if any(counts[state] < 0 for state in state_order) or sum(counts[state] for state in state_order) != sample_pages:
            raise ValueError("Inconsistent GEO check counts")
        if counts["not_verified"] != unknown_by_check[check_id]:
            raise ValueError("GEO unknown-cell transport disagrees with check counts")

        index = 0
        for state in state_order:
            for _ in range(counts[state]):
                page_id = page_ids[index]
                index += 1
                evidence_ref = "transport-arithmetic" if state in {"pass", "fail"} else ""
                reason = "transport-arithmetic" if state == "not_applicable" else ""
                observations.append(Observation(page_id, check_id, state, evidence_ref, reason))
    return page_ids, observations


def validate_geo_v8_transport_semantics(
    candidate: dict,
    *,
    parent_authoritative: bool,
    entry_verified: bool,
    access_limited: bool,
) -> bool:
    """Recompute v1-compatible derived fields from counts + exact gate facts."""
    parent_authoritative, entry_verified, access_limited = _explicit_gates(
        parent_authoritative=parent_authoritative,
        entry_verified=entry_verified,
        access_limited=access_limited,
    )
    validate_geo_v8_transport_candidate(candidate)
    readiness = candidate["readiness"]
    if readiness["observation_scope"]["access_limited"] is not access_limited:
        raise ValueError("GEO pre-seal access-limited gate mismatch")

    page_ids, observations = _count_equivalent_matrix(readiness)
    expected = evaluate_geo(
        page_ids,
        observations,
        parent_authoritative=parent_authoritative,
        entry_verified=entry_verified,
        access_limited=access_limited,
    )
    actual_subset = {field: readiness[field] for field in _V1_COMPAT_FIELDS}
    expected_subset = {field: expected[field] for field in _V1_COMPAT_FIELDS}
    if _canonical(actual_subset) != _canonical(expected_subset):
        raise ValueError("GEO readiness arithmetic/gate semantics mismatch")

    # v2 summaries are redundant by design; they must agree with the
    # independently reconstructed v1-compatible dimension output.
    if not access_limited:
        summaries = readiness["dimension_scores"]
        for dimension in DIMENSIONS:
            detail = expected["dimensions"][dimension]
            summary = summaries.get(dimension)
            if not isinstance(summary, dict):
                raise ValueError("Malformed GEO dimension summary")
            if summary.get("score") != detail["score"] or summary.get("coverage") != detail["coverage"]:
                raise ValueError("GEO dimension summary disagrees with derived arithmetic")
    return True
