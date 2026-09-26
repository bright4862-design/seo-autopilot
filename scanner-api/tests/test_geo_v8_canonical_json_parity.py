import json
import subprocess

import pytest

from app.geo_readiness import CHECKS, Observation
from app.geo_v8_canonical_json import VERSION, canonical_json_bytes
from app.geo_v8_transport_candidate import build_geo_v8_transport_candidate
from app.geo_v8_transport_observation_binding import (
    build_geo_v8_transport_observation_binding,
    serialize_geo_v8_transport_observation_binding,
)


JS_CANONICALIZE = r"""
const fs = require('fs');
const value = JSON.parse(fs.readFileSync(0, 'utf8'));

function canonicalize(value) {
  if (value === null || typeof value === 'boolean' || typeof value === 'string') {
    return JSON.stringify(value);
  }
  if (typeof value === 'number') {
    if (!Number.isFinite(value) || (!Number.isSafeInteger(value) && Number.isInteger(value))) {
      throw new Error('unsupported number');
    }
    const magnitude = Math.abs(value);
    if (magnitude !== 0 && (magnitude < 1e-6 || magnitude >= 1e21)) {
      throw new Error('number outside canonical range');
    }
    if (!Number.isInteger(value) && Number(value.toFixed(6)) !== value) {
      throw new Error('number exceeds six decimal places');
    }
    return JSON.stringify(Object.is(value, -0) ? 0 : value);
  }
  if (Array.isArray(value)) {
    return '[' + value.map(canonicalize).join(',') + ']';
  }
  if (typeof value === 'object') {
    const keys = Object.keys(value).sort();
    if (keys.some((key) => !/^[\x00-\x7f]*$/.test(key))) {
      throw new Error('non-ASCII key');
    }
    return '{' + keys.map((key) => JSON.stringify(key) + ':' + canonicalize(value[key])).join(',') + '}';
  }
  throw new Error('unsupported value');
}

process.stdout.write(canonicalize(value));
"""


def _javascript_canonical_bytes(value) -> bytes:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    result = subprocess.run(
        ["node", "-e", JS_CANONICALIZE],
        input=payload,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return result.stdout


def _binding_fixture():
    page_ids = ("page_é_😀",)
    observations = [
        Observation(
            page_ids[0],
            check_id,
            "pass",
            f"evidence:{check_id}:café",
            "",
        )
        for check_id in CHECKS
    ]
    candidate = build_geo_v8_transport_candidate(
        page_ids,
        observations,
        parent_authoritative=True,
        entry_verified=True,
        access_limited=False,
    )
    binding = build_geo_v8_transport_observation_binding(
        candidate,
        page_ids,
        observations,
        parent_authoritative=True,
        entry_verified=True,
        access_limited=False,
    )
    serialized = serialize_geo_v8_transport_observation_binding(
        binding,
        page_ids,
        observations,
        parent_authoritative=True,
        entry_verified=True,
        access_limited=False,
    )
    return binding, serialized


def _funbooker_like_binding_fixture():
    page_ids = tuple(f"p_{index:03d}" for index in range(139))
    pass_counts = {
        "search_policy": 139,
        "indexability": 139,
        "discovery": 68,
        "main_text": 139,
        "page_identity": 138,
        "template_integrity": 139,
        "subject_identity": 0,
        "entity_details": 0,
        "schema_agreement": 0,
        "accountability": 0,
        "date_context": 0,
        "source_attribution": 0,
    }
    observations = []
    for index, page_id in enumerate(page_ids):
        for check_id in CHECKS:
            verified = index < pass_counts[check_id]
            observations.append(Observation(
                page_id,
                check_id,
                "pass" if verified else "not_verified",
                f"fixture:{check_id}:{index}" if verified else "",
                "" if verified else "production_like_retained_evidence_insufficient",
            ))
    candidate = build_geo_v8_transport_candidate(
        page_ids,
        observations,
        parent_authoritative=True,
        entry_verified=True,
        access_limited=False,
    )
    binding = build_geo_v8_transport_observation_binding(
        candidate,
        page_ids,
        observations,
        parent_authoritative=True,
        entry_verified=True,
        access_limited=False,
    )
    return binding, observations, page_ids


def test_canonical_json_contract_matches_v8_for_bounded_numeric_and_unicode_values():
    assert VERSION == "geo_v8_canonical_json_v1"
    value = {
        "z": None,
        "a": [0.0, -0.0, 100.0, 0.456835, 0.000001],
        "unicode_value": "café 😀",
    }

    assert canonical_json_bytes(value) == _javascript_canonical_bytes(value)


def test_observation_bound_preseal_bytes_match_v8_canonicalization():
    binding, serialized = _binding_fixture()

    assert serialized == canonical_json_bytes(binding)
    assert serialized == _javascript_canonical_bytes(binding)
    assert b"100.0" not in serialized
    assert b"-0.0" not in serialized


def test_funbooker_like_null_score_binding_is_byte_identical_in_python_and_v8():
    binding, observations, page_ids = _funbooker_like_binding_fixture()
    serialized = serialize_geo_v8_transport_observation_binding(
        binding,
        page_ids,
        observations,
        parent_authoritative=True,
        entry_verified=True,
        access_limited=False,
    )

    assert binding["candidate"]["readiness"]["score"] is None
    assert binding["candidate"]["readiness"]["coverage"] == 0.456835
    assert binding["candidate"]["readiness"]["authority_verified"] is False
    assert serialized == _javascript_canonical_bytes(binding)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -(2**53), 2**53])
def test_canonical_json_rejects_nonportable_numbers(value):
    with pytest.raises(ValueError, match="canonical JSON number"):
        canonical_json_bytes({"value": value})


@pytest.mark.parametrize("value", [0.0000001, 0.1234567, 1e21])
def test_canonical_json_rejects_values_outside_bounded_decimal_contract(value):
    with pytest.raises(ValueError, match="canonical JSON number"):
        canonical_json_bytes({"value": value})


def test_canonical_json_rejects_non_ascii_keys_but_preserves_unicode_values():
    with pytest.raises(ValueError, match="ASCII object keys"):
        canonical_json_bytes({"clé": "value"})

    assert canonical_json_bytes({"key": "clé 😀"}) == '{"key":"clé 😀"}'.encode("utf-8")
