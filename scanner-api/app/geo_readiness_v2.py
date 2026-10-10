"""Candidate GEO readiness v2 transport built on the frozen v1 arithmetic.

This module adds explicit observation scope, dimension-score summaries and
unknown-cell transport. It does not fetch, call models, change thresholds,
interpret provider visibility, or establish authority. Scoring is delegated to
``geo_readiness.evaluate_geo`` so the existing exact-rational gates remain the
single arithmetic source of truth during compatibility evaluation.
"""
from __future__ import annotations

from hashlib import sha256
import json

from .geo_readiness import CHECKS, DIMENSIONS, Observation, VERSION as V1_VERSION, evaluate_geo

VERSION = "geo_readiness_v2_candidate"
SCOPE_KIND = "declared_search_facing_sample"
CLAIM_BOUNDARY = "structural_readiness_not_ai_citations_inclusion_visibility_or_traffic"


def _scope_digest(page_ids: list[str] | tuple[str, ...]) -> str:
    """Bind the declared page-ID set with an unambiguous canonical encoding."""
    material = json.dumps(
        sorted(page_ids),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(material).hexdigest()


def _matrix(observations: list[Observation] | tuple[Observation, ...]) -> dict[tuple[str, str], Observation]:
    # evaluate_geo validates type, bounds, membership and duplicates before this
    # helper is used, so this map cannot weaken the v1 validation boundary.
    return {(row.page_id, row.check_id): row for row in observations}


def _unknown_cells(page_ids, observations):
    rows = _matrix(observations)
    result = []
    for page_id in sorted(page_ids):
        for check_id, dimension in CHECKS.items():
            row = rows.get((page_id, check_id))
            if row is None:
                result.append({
                    "page_id": page_id,
                    "check_id": check_id,
                    "dimension": dimension,
                    "reason": "observation_missing",
                })
            elif row.state == "not_verified":
                result.append({
                    "page_id": page_id,
                    "check_id": check_id,
                    "dimension": dimension,
                    "reason": row.reason.strip() if row.reason.strip() else "not_verified",
                })
    return result


def _dimension_scores(v1_result):
    if v1_result["assessment_status"] == "access_limited":
        return {
            dimension: {
                "score": None,
                "coverage": None,
                "unknown_cells": None,
                "not_applicable_cells": None,
                "verified_cells": None,
            }
            for dimension in DIMENSIONS
        }

    summaries = {}
    for dimension in DIMENSIONS:
        detail = v1_result["dimensions"][dimension]
        counts = [item["counts"] for item in detail["checks"].values()]
        summaries[dimension] = {
            "score": detail["score"],
            "coverage": detail["coverage"],
            "unknown_cells": sum(item["not_verified"] for item in counts),
            "not_applicable_cells": sum(item["not_applicable"] for item in counts),
            "verified_cells": sum(item["pass"] + item["fail"] for item in counts),
        }
    return summaries


def evaluate_geo_v2(page_ids, observations, *, parent_authoritative=False,
                    entry_verified=False, access_limited=False):
    """Return a v2 candidate without changing any v1 score or gate semantics.

    ``unknown_cells`` is the explicit transport for omitted/not-verified matrix
    cells. Not-applicable cells are deliberately excluded because applicability
    was deterministically resolved rather than left unknown.
    """
    v1 = evaluate_geo(
        page_ids,
        observations,
        parent_authoritative=parent_authoritative,
        entry_verified=entry_verified,
        access_limited=access_limited,
    )
    unknown_cells = [] if access_limited else _unknown_cells(page_ids, observations)
    return {
        "geo_readiness_version": VERSION,
        "compatibility_base_version": V1_VERSION,
        "assessment_status": v1["assessment_status"],
        "score": v1["score"],
        "coverage": v1["coverage"],
        "score_bounds": v1["score_bounds"],
        "bounds_kind": v1["bounds_kind"],
        "sample_pages": v1["sample_pages"],
        "observation_scope": {
            "kind": SCOPE_KIND,
            "page_count": len(page_ids),
            "page_set_digest": _scope_digest(page_ids),
            "origin": "retained_evidence_only",
            "access_limited": access_limited,
        },
        "dimension_scores": _dimension_scores(v1),
        "dimensions": v1["dimensions"],
        "unknown_cells": unknown_cells,
        "unknown_cell_count": len(unknown_cells),
        "reasons": v1["reasons"],
        "claim_boundary": CLAIM_BOUNDARY,
        "authority_verified": False,
    }
