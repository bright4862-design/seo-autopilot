"""Exact retained-source binding for the Lane-C GEO V8 pre-seal transport.

The transport candidate already proves bounded shape, v1-compatible arithmetic,
assessment gates, and exact observation scope. Optional named-crawler robots and
llms.txt sidecars are still derived data, though: a non-authoritative candidate
digest must not make rewritten sidecar values trustworthy. This adapter
recomputes those sidecars from the exact already-retained source observations
held by the serialized integrator before any candidate bytes are eligible for
sealing.

No fetching, provider/model call, scoring-policy change, persistence, customer
projection, sealing, or authority establishment occurs here.
"""
from __future__ import annotations

import json

from .geo_llms_txt_evidence import extract_llms_txt_evidence
from .geo_robots_evidence import extract_named_robots_evidence
from .geo_v8_transport_scope import validate_geo_v8_transport_scope
from .geo_v8_transport_serialization import serialize_geo_v8_transport_candidate

MAX_ROBOTS_SOURCE_PAGES = 150


def _canonical(value) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _robots_source_pages(
    pages: list[dict] | tuple[dict, ...],
) -> tuple[dict, ...]:
    if not isinstance(pages, (list, tuple)) or len(pages) > MAX_ROBOTS_SOURCE_PAGES:
        raise ValueError("Expected at most 150 retained robots source pages")
    normalized = tuple(pages)
    if any(not isinstance(page, dict) for page in normalized):
        raise ValueError("Expected retained robots source page objects")
    return normalized


def _expected_named_robots(
    pages: tuple[dict, ...],
) -> list[dict]:
    """Normalize retained pages while requiring one exact source identity each.

    Source ordering is intentionally non-authoritative, but duplicate identities
    are not. A duplicated retained observation must never be silently collapsed
    by sorting or by equality with a single transported sidecar.
    """
    expected = [extract_named_robots_evidence(page) for page in pages]
    page_ids = [item["page_id"] for item in expected]
    if len(page_ids) != len(set(page_ids)):
        raise ValueError("Duplicate retained robots source identity")
    expected.sort(key=lambda item: item["page_id"])
    return expected


def validate_geo_v8_transport_sources(
    candidate: dict,
    page_ids: list[str] | tuple[str, ...],
    *,
    parent_authoritative: bool,
    entry_verified: bool,
    access_limited: bool,
    robots_pages: list[dict] | tuple[dict, ...] = (),
    llms_txt_observation: dict | None = None,
) -> bool:
    """Bind optional structural sidecars to exact retained source observations.

    Scope and v1 readiness semantics are validated first. The optional sidecars
    are then independently regenerated using the same pure normalizers that
    produced the candidate. A recomputed candidate digest therefore cannot
    legitimize rewritten robots directives or llms.txt structural fields.
    """
    validate_geo_v8_transport_scope(
        candidate,
        page_ids,
        parent_authoritative=parent_authoritative,
        entry_verified=entry_verified,
        access_limited=access_limited,
    )
    retained_robots = _robots_source_pages(robots_pages)

    if access_limited:
        if retained_robots or llms_txt_observation is not None:
            raise ValueError(
                "Access-limited GEO source binding must not include optional source observations"
            )
        return True

    expected_robots = _expected_named_robots(retained_robots)
    if _canonical(expected_robots) != _canonical(candidate["named_robots"]):
        raise ValueError(
            "Named-crawler GEO sidecars do not match retained source observations"
        )

    expected_llms = (
        extract_llms_txt_evidence(llms_txt_observation)
        if llms_txt_observation is not None
        else None
    )
    if _canonical(expected_llms) != _canonical(candidate["llms_txt"]):
        raise ValueError(
            "llms.txt GEO sidecar does not match retained source observation"
        )
    return True


def serialize_geo_v8_transport_candidate_for_sources(
    candidate: dict,
    page_ids: list[str] | tuple[str, ...],
    *,
    parent_authoritative: bool,
    entry_verified: bool,
    access_limited: bool,
    robots_pages: list[dict] | tuple[dict, ...] = (),
    llms_txt_observation: dict | None = None,
) -> bytes:
    """Return canonical pre-seal bytes only after exact source rebinding."""
    validate_geo_v8_transport_sources(
        candidate,
        page_ids,
        parent_authoritative=parent_authoritative,
        entry_verified=entry_verified,
        access_limited=access_limited,
        robots_pages=robots_pages,
        llms_txt_observation=llms_txt_observation,
    )
    return serialize_geo_v8_transport_candidate(candidate)
