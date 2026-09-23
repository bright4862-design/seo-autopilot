"""Exact scored-observation binding for the GEO V8 pre-seal handoff.

The existing candidate validators prove bounded structure, v1-compatible
arithmetic, exact page scope, and retained robots/llms.txt sidecars. They do not
by themselves prove that the scored pass/fail/not-applicable population came
from the exact retained GEO observations supplied by the trusted integrator.

This pure contract regenerates the complete candidate from that exact typed
Observation population and retains a canonical fingerprint of every observation
identity, state, evidence reference, and reason. It performs no fetch, model or
provider call, score-policy change, persistence, projection, sealing, or
authority establishment.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from hmac import compare_digest
import json

from .geo_readiness import Observation
from .geo_readiness_v2 import _scope_digest
from .geo_v8_transport_candidate import (
    SEAL_STATE,
    build_geo_v8_transport_candidate,
)

VERSION = "geo_v8_transport_observation_binding_v1"
CLAIM_BOUNDARY = "exact_retained_structural_observations_not_ai_provider_outcomes"

_TOP_KEYS = frozenset({
    "version",
    "candidate",
    "page_set_digest",
    "observation_count",
    "observation_population_fingerprint",
    "assessment_gates",
    "seal_state",
    "authority_verified",
    "claim_boundary",
    "binding_digest",
})


def _canonical_bytes(value) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _digest(value) -> str:
    return sha256(_canonical_bytes(value)).hexdigest()


def _binding_digest(binding: dict) -> str:
    unsigned = deepcopy(binding)
    unsigned.pop("binding_digest", None)
    return _digest(unsigned)


def _ordered_observations(
    observations: list[Observation] | tuple[Observation, ...],
) -> list[dict[str, str]]:
    if not isinstance(observations, (list, tuple)):
        raise ValueError("Expected a bounded typed GEO observation population")
    rows = []
    for observation in observations:
        if not isinstance(observation, Observation):
            raise ValueError("Expected a bounded typed GEO observation population")
        rows.append({
            "page_id": observation.page_id,
            "check_id": observation.check_id,
            "state": observation.state,
            "evidence_ref": observation.evidence_ref,
            "reason": observation.reason,
        })
    rows.sort(key=lambda row: (
        row["page_id"],
        row["check_id"],
        row["state"],
        row["evidence_ref"],
        row["reason"],
    ))
    return rows


def _build_exact_binding(
    candidate: dict,
    page_ids: list[str] | tuple[str, ...],
    observations: list[Observation] | tuple[Observation, ...],
    *,
    parent_authoritative: bool,
    entry_verified: bool,
    access_limited: bool,
    robots_pages: list[dict] | tuple[dict, ...] = (),
    llms_txt_observation: dict | None = None,
) -> dict:
    if any(type(value) is not bool for value in (
        parent_authoritative,
        entry_verified,
        access_limited,
    )):
        raise ValueError("Exact GEO observation binding requires three boolean gate facts")
    # Rebuild first so the frozen evaluator applies all Standard-150 bounds,
    # typed-field checks, duplicate checks, and evidence-reference rules before
    # the population is serialized into the provenance fingerprint.
    expected_candidate = build_geo_v8_transport_candidate(
        page_ids,
        observations,
        parent_authoritative=parent_authoritative,
        entry_verified=entry_verified,
        access_limited=access_limited,
        robots_pages=robots_pages,
        llms_txt_observation=llms_txt_observation,
    )
    ordered_observations = _ordered_observations(observations)
    if access_limited and ordered_observations:
        raise ValueError("Access-limited GEO binding must not include content observations")
    if _canonical_bytes(candidate) != _canonical_bytes(expected_candidate):
        raise ValueError(
            "GEO candidate does not match the exact retained GEO observation population"
        )

    gates = {
        "parent_authoritative": parent_authoritative,
        "entry_verified": entry_verified,
        "access_limited": access_limited,
    }
    binding = {
        "version": VERSION,
        "candidate": deepcopy(candidate),
        "page_set_digest": _scope_digest(page_ids),
        "observation_count": len(ordered_observations),
        "observation_population_fingerprint": _digest(ordered_observations),
        "assessment_gates": gates,
        "seal_state": SEAL_STATE,
        "authority_verified": False,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    binding["binding_digest"] = _binding_digest(binding)
    return binding


def build_geo_v8_transport_observation_binding(
    candidate: dict,
    page_ids: list[str] | tuple[str, ...],
    observations: list[Observation] | tuple[Observation, ...],
    *,
    parent_authoritative: bool,
    entry_verified: bool,
    access_limited: bool,
    robots_pages: list[dict] | tuple[dict, ...] = (),
    llms_txt_observation: dict | None = None,
) -> dict:
    """Build one unsealed binding from exact trusted retained observations."""
    return _build_exact_binding(
        candidate,
        page_ids,
        observations,
        parent_authoritative=parent_authoritative,
        entry_verified=entry_verified,
        access_limited=access_limited,
        robots_pages=robots_pages,
        llms_txt_observation=llms_txt_observation,
    )


def validate_geo_v8_transport_observation_binding(
    binding: dict,
    page_ids: list[str] | tuple[str, ...],
    observations: list[Observation] | tuple[Observation, ...],
    *,
    parent_authoritative: bool,
    entry_verified: bool,
    access_limited: bool,
    robots_pages: list[dict] | tuple[dict, ...] = (),
    llms_txt_observation: dict | None = None,
) -> bool:
    """Rebuild the binding and require exact canonical equality."""
    if not isinstance(binding, dict) or set(binding) != _TOP_KEYS:
        raise ValueError("Malformed GEO V8 observation binding")
    if binding.get("version") != VERSION:
        raise ValueError("Unexpected GEO V8 observation binding version")
    if binding.get("seal_state") != SEAL_STATE or binding.get("authority_verified") is not False:
        raise ValueError("GEO V8 observation binding must remain unsealed and non-authoritative")
    if binding.get("claim_boundary") != CLAIM_BOUNDARY:
        raise ValueError("GEO V8 observation binding claim boundary mismatch")
    if binding.get("binding_digest") != _binding_digest(binding):
        raise ValueError("GEO V8 observation binding digest mismatch")

    candidate = binding.get("candidate")
    if not isinstance(candidate, dict):
        raise ValueError("Malformed GEO V8 observation binding candidate")
    expected = _build_exact_binding(
        candidate,
        page_ids,
        observations,
        parent_authoritative=parent_authoritative,
        entry_verified=entry_verified,
        access_limited=access_limited,
        robots_pages=robots_pages,
        llms_txt_observation=llms_txt_observation,
    )
    if _canonical_bytes(binding) != _canonical_bytes(expected):
        raise ValueError("GEO V8 observation binding does not match retained sources")
    return True


def serialize_geo_v8_transport_observation_binding(
    binding: dict,
    page_ids: list[str] | tuple[str, ...],
    observations: list[Observation] | tuple[Observation, ...],
    *,
    parent_authoritative: bool,
    entry_verified: bool,
    access_limited: bool,
    robots_pages: list[dict] | tuple[dict, ...] = (),
    llms_txt_observation: dict | None = None,
) -> bytes:
    """Return canonical pre-seal bytes only after exact observation binding."""
    validate_geo_v8_transport_observation_binding(
        binding,
        page_ids,
        observations,
        parent_authoritative=parent_authoritative,
        entry_verified=entry_verified,
        access_limited=access_limited,
        robots_pages=robots_pages,
        llms_txt_observation=llms_txt_observation,
    )
    return _canonical_bytes(binding)


def validate_geo_v8_transport_observation_binding_reload_identity(
    expected_preseal_bytes: bytes,
    binding: dict,
    page_ids: list[str] | tuple[str, ...],
    observations: list[Observation] | tuple[Observation, ...],
    *,
    parent_authoritative: bool,
    entry_verified: bool,
    access_limited: bool,
    robots_pages: list[dict] | tuple[dict, ...] = (),
    llms_txt_observation: dict | None = None,
) -> bool:
    """Require reloaded observation-bound bytes to equal pre-seal bytes."""
    if type(expected_preseal_bytes) is not bytes or not expected_preseal_bytes:
        raise ValueError("Expected non-empty observation-bound GEO pre-seal bytes")
    reloaded = serialize_geo_v8_transport_observation_binding(
        binding,
        page_ids,
        observations,
        parent_authoritative=parent_authoritative,
        entry_verified=entry_verified,
        access_limited=access_limited,
        robots_pages=robots_pages,
        llms_txt_observation=llms_txt_observation,
    )
    if not compare_digest(expected_preseal_bytes, reloaded):
        raise ValueError("Reloaded observation-bound GEO bytes differ from pre-seal identity")
    return True
