"""Post-reload byte identity for the Lane-C GEO V8 pre-seal transport.

This pure adapter does not read or write persistence. The serialized integrator
supplies the exact canonical bytes captured before sealing plus the reloaded GEO
candidate and its retained source observations. We re-run the full scope/source
binding path and require byte-for-byte canonical identity before those bytes may
be considered eligible for an authenticated authority snapshot.

The candidate digest remains a non-authoritative integrity aid. Only the
serialized authority layer may establish authority after end-to-end sealing.
"""
from __future__ import annotations

from hmac import compare_digest

from .geo_v8_transport_sources import serialize_geo_v8_transport_candidate_for_sources


def validate_geo_v8_transport_reload_identity(
    expected_preseal_bytes: bytes,
    candidate: dict,
    page_ids: list[str] | tuple[str, ...],
    *,
    parent_authoritative: bool,
    entry_verified: bool,
    access_limited: bool,
    robots_pages: list[dict] | tuple[dict, ...] = (),
    llms_txt_observation: dict | None = None,
) -> bool:
    """Require reloaded, source-bound canonical bytes to equal pre-seal bytes.

    This is intentionally a pure acceptance seam. It does not fetch, persist,
    seal, project, score, call a provider/model, or establish authority.
    """
    if type(expected_preseal_bytes) is not bytes or not expected_preseal_bytes:
        raise ValueError("Expected non-empty canonical GEO pre-seal bytes")

    reloaded_bytes = serialize_geo_v8_transport_candidate_for_sources(
        candidate,
        page_ids,
        parent_authoritative=parent_authoritative,
        entry_verified=entry_verified,
        access_limited=access_limited,
        robots_pages=robots_pages,
        llms_txt_observation=llms_txt_observation,
    )
    if not compare_digest(expected_preseal_bytes, reloaded_bytes):
        raise ValueError("Reloaded GEO transport bytes differ from pre-seal identity")
    return True
