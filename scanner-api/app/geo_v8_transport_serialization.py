"""Deterministic serialization for the Lane-C GEO V8 pre-seal candidate.

This module validates and serializes an already-built candidate. It does not
sign, seal, persist, project, fetch, call providers/models, or change GEO score
arithmetic. The returned bytes are suitable only as an exact input to a future
separately versioned authority snapshot owned by the serialized integrator.
"""

from .geo_v8_transport_candidate import (
    _canonical_bytes,
    validate_geo_v8_transport_candidate,
)


def serialize_geo_v8_transport_candidate(candidate: dict) -> bytes:
    """Return exact validated canonical UTF-8 bytes, still non-authoritative."""
    validate_geo_v8_transport_candidate(candidate)
    return _canonical_bytes(candidate)
