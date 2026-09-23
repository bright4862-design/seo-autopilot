"""Pure pre-seal GEO transport candidate for serialized V8 integration.

This module does not seal authority, persist results, project customer data,
fetch URLs, call providers/models, or change GEO score arithmetic. It packages
already-computed deterministic GEO readiness plus optional structural sidecars
into one bounded, digest-bound candidate that an integrator can place inside a
future authenticated V8 snapshot.

The candidate digest is an integrity/checkpoint aid only. It is not an authority
signature and must never be presented as proof of AI/search visibility.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import re

from .geo_evidence import VERSION as EVIDENCE_ADAPTER_VERSION
from .geo_llms_txt_evidence import VERSION as LLMS_VERSION, extract_llms_txt_evidence
from .geo_readiness import CHECKS, DIMENSIONS, STATES, Observation, VERSION as V1_VERSION
from .geo_readiness_v2 import (
    CLAIM_BOUNDARY as READINESS_CLAIM_BOUNDARY,
    VERSION as READINESS_VERSION,
    evaluate_geo_v2,
)
from .geo_robots_evidence import VERSION as ROBOTS_VERSION, extract_named_robots_evidence

VERSION = "geo_v8_transport_candidate_v1"
CLAIM_BOUNDARY = "fixlist_structural_readiness_not_ai_provider_outcomes"
SEAL_STATE = "unsealed_candidate"
MAX_ROBOTS_SIDECARS = 150
_HEX64 = re.compile(r"^[0-9a-f]{64}$")

_TOP_KEYS = frozenset({
    "version", "readiness", "evidence_adapter_version", "named_robots",
    "llms_txt", "seal_state", "authority_verified", "claim_boundary",
    "candidate_digest",
})
_READINESS_KEYS = frozenset({
    "geo_readiness_version", "compatibility_base_version", "assessment_status",
    "score", "coverage", "score_bounds", "bounds_kind", "sample_pages",
    "observation_scope", "dimension_scores", "dimensions", "unknown_cells",
    "unknown_cell_count", "reasons", "claim_boundary", "authority_verified",
})


def _canonical_bytes(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _candidate_digest(value: dict) -> str:
    unsigned = deepcopy(value)
    unsigned.pop("candidate_digest", None)
    return sha256(_canonical_bytes(unsigned)).hexdigest()


def _bounded_string(value, maximum=500, *, allow_empty=False):
    return isinstance(value, str) and len(value) <= maximum and (allow_empty or bool(value.strip()))


def _validate_readiness_shape(readiness: dict) -> None:
    if not isinstance(readiness, dict) or set(readiness) != _READINESS_KEYS:
        raise ValueError("Malformed GEO readiness v2 candidate")
    if readiness["geo_readiness_version"] != READINESS_VERSION or readiness["compatibility_base_version"] != V1_VERSION:
        raise ValueError("Unexpected GEO readiness version")
    if readiness["claim_boundary"] != READINESS_CLAIM_BOUNDARY or readiness["authority_verified"] is not False:
        raise ValueError("GEO readiness authority/claim boundary mismatch")
    if readiness["assessment_status"] not in {"assessed", "insufficient_evidence", "access_limited"}:
        raise ValueError("Unexpected GEO assessment status")
    sample_pages = readiness["sample_pages"]
    if type(sample_pages) is not int or not 0 <= sample_pages <= 150:
        raise ValueError("Malformed GEO sample count")
    scope = readiness["observation_scope"]
    if not isinstance(scope, dict) or set(scope) != {"kind", "page_count", "page_set_digest", "origin", "access_limited"}:
        raise ValueError("Malformed GEO observation scope")
    if scope["kind"] != "declared_search_facing_sample" or scope["origin"] != "retained_evidence_only":
        raise ValueError("Unexpected GEO observation scope")
    if scope["page_count"] != sample_pages or type(scope["access_limited"]) is not bool or not _HEX64.fullmatch(scope["page_set_digest"] or ""):
        raise ValueError("Inconsistent GEO observation scope")
    if readiness["unknown_cell_count"] != len(readiness["unknown_cells"]):
        raise ValueError("Inconsistent GEO unknown-cell count")
    if not isinstance(readiness["unknown_cells"], list) or len(readiness["unknown_cells"]) > 150 * len(CHECKS):
        raise ValueError("Malformed GEO unknown-cell transport")
    unknown_keys = set()
    unknown_by_dimension = {dimension: 0 for dimension in DIMENSIONS}
    for row in readiness["unknown_cells"]:
        if not isinstance(row, dict) or set(row) != {"page_id", "check_id", "dimension", "reason"}:
            raise ValueError("Malformed GEO unknown cell")
        if not _bounded_string(row["page_id"], 200) or row["check_id"] not in CHECKS or row["dimension"] != CHECKS[row["check_id"]]:
            raise ValueError("Malformed GEO unknown cell identity")
        if not _bounded_string(row["reason"], 500):
            raise ValueError("Malformed GEO unknown reason")
        key = (row["page_id"], row["check_id"])
        if key in unknown_keys:
            raise ValueError("Duplicate GEO unknown cell")
        unknown_keys.add(key)
        unknown_by_dimension[row["dimension"]] += 1

    access_limited = scope["access_limited"]
    if access_limited:
        if readiness["assessment_status"] != "access_limited" or readiness["score"] is not None or readiness["coverage"] != 0.0:
            raise ValueError("Malformed access-limited GEO candidate")
        if readiness["dimensions"] != {} or readiness["unknown_cells"] != []:
            raise ValueError("Access-limited GEO candidate exposes content diagnostics")
    else:
        if not isinstance(readiness["dimensions"], dict) or set(readiness["dimensions"]) != set(DIMENSIONS):
            raise ValueError("Malformed GEO dimension transport")

    summaries = readiness["dimension_scores"]
    if not isinstance(summaries, dict) or tuple(summaries) != DIMENSIONS:
        raise ValueError("Malformed GEO dimension summaries")
    for dimension in DIMENSIONS:
        summary = summaries[dimension]
        if not isinstance(summary, dict) or set(summary) != {"score", "coverage", "unknown_cells", "not_applicable_cells", "verified_cells"}:
            raise ValueError("Malformed GEO dimension summary")
        if access_limited:
            if any(summary[key] is not None for key in summary):
                raise ValueError("Access-limited GEO dimension summary must be null")
            continue
        for key in ("unknown_cells", "not_applicable_cells", "verified_cells"):
            if type(summary[key]) is not int or not 0 <= summary[key] <= sample_pages * 3:
                raise ValueError("Malformed GEO dimension counts")
        if summary["unknown_cells"] != unknown_by_dimension[dimension]:
            raise ValueError("Unknown-cell summary mismatch")
        if summary["unknown_cells"] + summary["not_applicable_cells"] + summary["verified_cells"] != sample_pages * 3:
            raise ValueError("Incomplete GEO dimension cell accounting")
        detail = readiness["dimensions"][dimension]
        if not isinstance(detail, dict) or set(detail) != {"coverage", "checks", "score"}:
            raise ValueError("Malformed GEO dimension detail")
        if summary["score"] != detail["score"] or summary["coverage"] != detail["coverage"]:
            raise ValueError("GEO dimension summary disagrees with v1-compatible detail")
        expected_checks = {check for check, owner in CHECKS.items() if owner == dimension}
        checks = detail["checks"]
        if not isinstance(checks, dict) or set(checks) != expected_checks:
            raise ValueError("Malformed GEO check transport")
        for check in expected_checks:
            item = checks[check]
            if not isinstance(item, dict) or set(item) != {"counts", "applicable_or_unknown"}:
                raise ValueError("Malformed GEO check detail")
            counts = item["counts"]
            if not isinstance(counts, dict) or set(counts) != set(STATES):
                raise ValueError("Malformed GEO check counts")
            if any(type(counts[state]) is not int or counts[state] < 0 for state in STATES) or sum(counts.values()) != sample_pages:
                raise ValueError("Inconsistent GEO check counts")
            if item["applicable_or_unknown"] != sample_pages - counts["not_applicable"]:
                raise ValueError("Inconsistent GEO applicability count")


def _validate_robots_sidecars(sidecars: list, page_ids: set[str] | None = None) -> None:
    if not isinstance(sidecars, list) or len(sidecars) > MAX_ROBOTS_SIDECARS:
        raise ValueError("Malformed named-crawler sidecar collection")
    seen = set()
    for sidecar in sidecars:
        if not isinstance(sidecar, dict) or sidecar.get("version") != ROBOTS_VERSION:
            raise ValueError("Malformed named-crawler sidecar")
        page_id = sidecar.get("page_id")
        if not _bounded_string(page_id, 200) or page_id in seen:
            raise ValueError("Duplicate or malformed named-crawler page identity")
        if page_ids is not None and page_id not in page_ids:
            raise ValueError("Named-crawler sidecar is outside the GEO observation scope")
        seen.add(page_id)
        if sidecar.get("claim_boundary") != "robots_policy_only_not_provider_fetch_indexing_citations_ranking_visibility_or_traffic":
            raise ValueError("Named-crawler claim boundary mismatch")
        bots = sidecar.get("bots")
        if not isinstance(bots, list) or len(bots) != 3:
            raise ValueError("Malformed named-crawler bot registry")


def _validate_llms_sidecar(sidecar: dict | None) -> None:
    if sidecar is None:
        return
    if not isinstance(sidecar, dict) or sidecar.get("version") != LLMS_VERSION:
        raise ValueError("Malformed llms.txt sidecar")
    if sidecar.get("claim_boundary") != "optional_structural_metadata_not_provider_fetch_indexing_inclusion_citations_ranking_visibility_or_traffic":
        raise ValueError("llms.txt claim boundary mismatch")


def build_geo_v8_transport_candidate(
    page_ids: list[str] | tuple[str, ...],
    observations: list[Observation] | tuple[Observation, ...],
    *,
    parent_authoritative: bool = False,
    entry_verified: bool = False,
    access_limited: bool = False,
    robots_pages: list[dict] | tuple[dict, ...] = (),
    llms_txt_observation: dict | None = None,
) -> dict:
    """Build one bounded, unsealed server-side transport candidate.

    `robots_pages` and `llms_txt_observation` are already-retained observations.
    This helper performs no fetch. Optional sidecars cannot change the readiness
    score because scoring is computed before they are attached.
    """
    if not isinstance(robots_pages, (list, tuple)) or len(robots_pages) > MAX_ROBOTS_SIDECARS:
        raise ValueError("Expected at most 150 retained robots page objects")
    if any(not isinstance(page, dict) for page in robots_pages):
        raise ValueError("Expected retained robots page objects")
    readiness = evaluate_geo_v2(
        page_ids,
        observations,
        parent_authoritative=parent_authoritative,
        entry_verified=entry_verified,
        access_limited=access_limited,
    )
    _validate_readiness_shape(readiness)

    if access_limited:
        named_robots = []
        llms_txt = None
    else:
        named_robots = [extract_named_robots_evidence(page) for page in robots_pages]
        named_robots.sort(key=lambda item: item["page_id"])
        _validate_robots_sidecars(named_robots, set(page_ids))
        llms_txt = extract_llms_txt_evidence(llms_txt_observation) if llms_txt_observation is not None else None
        _validate_llms_sidecar(llms_txt)

    candidate = {
        "version": VERSION,
        "readiness": readiness,
        "evidence_adapter_version": EVIDENCE_ADAPTER_VERSION,
        "named_robots": named_robots,
        "llms_txt": llms_txt,
        "seal_state": SEAL_STATE,
        "authority_verified": False,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    candidate["candidate_digest"] = _candidate_digest(candidate)
    return candidate


def validate_geo_v8_transport_candidate(candidate: dict) -> bool:
    """Validate the Lane-C pre-seal candidate, never an authority signature."""
    if not isinstance(candidate, dict) or set(candidate) != _TOP_KEYS:
        raise ValueError("Malformed GEO V8 transport candidate")
    if candidate["version"] != VERSION or candidate["evidence_adapter_version"] != EVIDENCE_ADAPTER_VERSION:
        raise ValueError("Unexpected GEO V8 transport version")
    if candidate["seal_state"] != SEAL_STATE or candidate["authority_verified"] is not False:
        raise ValueError("Lane-C transport must remain unsealed and non-authoritative")
    if candidate["claim_boundary"] != CLAIM_BOUNDARY:
        raise ValueError("GEO transport claim boundary mismatch")
    digest = candidate["candidate_digest"]
    if not isinstance(digest, str) or not _HEX64.fullmatch(digest) or digest != _candidate_digest(candidate):
        raise ValueError("GEO transport candidate digest mismatch")
    _validate_readiness_shape(candidate["readiness"])
    _validate_robots_sidecars(candidate["named_robots"])
    _validate_llms_sidecar(candidate["llms_txt"])
    if candidate["readiness"]["observation_scope"]["access_limited"] and (candidate["named_robots"] or candidate["llms_txt"] is not None):
        raise ValueError("Access-limited transport must not expose optional sidecars")
    return True
