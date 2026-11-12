"""Exact page-set and gate binding for the Lane-C GEO V8 pre-seal transport.

The base candidate deliberately carries only a collision-safe digest of the
sampled page IDs. A serialized integrator still has the authoritative page set
and assessment gate facts available when it prepares an authenticated V8
snapshot, so this adapter binds those exact inputs to the candidate before
sealing. It does not fetch, persist, score, seal, project, or establish
authority.
"""
from __future__ import annotations

from .geo_readiness_v2 import _scope_digest
from .geo_v8_transport_semantics import validate_geo_v8_transport_semantics
from .geo_v8_transport_serialization import serialize_geo_v8_transport_candidate

MAX_SCOPE_PAGES = 150
MAX_PAGE_ID_LENGTH = 200


def _declared_page_ids(page_ids: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(page_ids, (list, tuple)) or len(page_ids) > MAX_SCOPE_PAGES:
        raise ValueError("Expected at most 150 declared GEO page identities")
    normalized = tuple(page_ids)
    if any(
        not isinstance(page_id, str)
        or not page_id.strip()
        or len(page_id) > MAX_PAGE_ID_LENGTH
        for page_id in normalized
    ):
        raise ValueError("Malformed declared GEO page identity")
    if len(set(normalized)) != len(normalized):
        raise ValueError("Duplicate declared GEO page identity")
    return normalized


def _explicit_gate_inputs(
    *,
    parent_authoritative: bool,
    entry_verified: bool,
    access_limited: bool,
) -> tuple[bool, bool, bool]:
    gates = (parent_authoritative, entry_verified, access_limited)
    if any(type(value) is not bool for value in gates):
        raise ValueError("Exact GEO scope binding requires three boolean gate facts")
    return gates


def validate_geo_v8_transport_scope(
    candidate: dict,
    page_ids: list[str] | tuple[str, ...],
    *,
    parent_authoritative: bool,
    entry_verified: bool,
    access_limited: bool,
) -> bool:
    """Bind a valid pre-seal candidate to exact scope and upstream gate facts.

    The ordinary candidate validator proves internal shape and digest
    consistency. This additional boundary independently revalidates v1
    arithmetic and gate semantics, then proves that the observation-scope
    digest, explicit unknown cells, and named-crawler sidecars belong to the
    exact page set supplied by the serialized integrator.
    """
    declared = _declared_page_ids(page_ids)
    parent_authoritative, entry_verified, access_limited = _explicit_gate_inputs(
        parent_authoritative=parent_authoritative,
        entry_verified=entry_verified,
        access_limited=access_limited,
    )
    validate_geo_v8_transport_semantics(
        candidate,
        parent_authoritative=parent_authoritative,
        entry_verified=entry_verified,
        access_limited=access_limited,
    )

    scope = candidate["readiness"]["observation_scope"]
    if scope["page_count"] != len(declared) or scope["page_set_digest"] != _scope_digest(declared):
        raise ValueError("GEO transport observation scope does not match declared page set")

    allowed = set(declared)
    for row in candidate["readiness"]["unknown_cells"]:
        if row["page_id"] not in allowed:
            raise ValueError("GEO unknown cell is outside the declared observation scope")
    for sidecar in candidate["named_robots"]:
        if sidecar["page_id"] not in allowed:
            raise ValueError("Named-crawler sidecar is outside the declared observation scope")
    return True


def serialize_geo_v8_transport_candidate_for_scope(
    candidate: dict,
    page_ids: list[str] | tuple[str, ...],
    *,
    parent_authoritative: bool,
    entry_verified: bool,
    access_limited: bool,
) -> bytes:
    """Return canonical pre-seal bytes only after exact scope/gate binding."""
    validate_geo_v8_transport_scope(
        candidate,
        page_ids,
        parent_authoritative=parent_authoritative,
        entry_verified=entry_verified,
        access_limited=access_limited,
    )
    return serialize_geo_v8_transport_candidate(candidate)
