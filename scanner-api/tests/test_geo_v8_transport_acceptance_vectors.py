import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest

from app.geo_readiness import CHECKS, Observation
from app.geo_v8_transport_candidate import (
    build_geo_v8_transport_candidate,
    validate_geo_v8_transport_candidate,
)
from app.geo_v8_transport_serialization import serialize_geo_v8_transport_candidate


FIXTURE = Path(__file__).parent / "fixtures" / "geo_v8_transport_acceptance_vectors.json"


def _rows(page_id, scenario):
    if scenario == "all_unknown":
        return []
    observations = []
    for check, dimension in CHECKS.items():
        if scenario == "marketplace_support_not_applicable" and dimension == "support":
            observations.append(
                Observation(
                    page_id,
                    check,
                    "not_applicable",
                    "",
                    "Deterministically non-article fixture",
                )
            )
        else:
            observations.append(Observation(page_id, check, "pass", "evidence-ref", ""))
    return observations


def _candidate(scenario):
    page_id = "page-1"
    return build_geo_v8_transport_candidate(
        [page_id],
        _rows(page_id, scenario),
        parent_authoritative=True,
        entry_verified=True,
        access_limited=scenario == "access_limited",
    )


def _vectors():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert payload["version"] == "geo_v8_transport_acceptance_vectors_v1"
    assert payload["canonicalization"] == "utf8_json_sort_keys_compact_ensure_ascii_false"
    return payload["vectors"]


@pytest.mark.parametrize("vector", _vectors(), ids=lambda item: item["name"])
def test_fixed_transport_acceptance_vector(vector):
    candidate = _candidate(vector["scenario"])
    serialized = serialize_geo_v8_transport_candidate(candidate)

    assert validate_geo_v8_transport_candidate(candidate) is True
    assert candidate["candidate_digest"] == vector["candidate_digest"]
    assert sha256(serialized).hexdigest() == vector["serialized_sha256"]
    assert len(serialized) == vector["serialized_length"]
    assert candidate["readiness"]["assessment_status"] == vector["assessment_status"]
    assert candidate["readiness"]["score"] == vector["score"]
    assert candidate["readiness"]["coverage"] == vector["coverage"]
    assert candidate["authority_verified"] is False
    assert candidate["readiness"]["authority_verified"] is False


def test_marketplace_acceptance_vector_keeps_support_na_but_does_not_lower_gates():
    candidate = _candidate("marketplace_support_not_applicable")
    support = candidate["readiness"]["dimension_scores"]["support"]

    assert support["not_applicable_cells"] == 3
    assert support["verified_cells"] == 0
    assert support["coverage"] == 0.0
    assert candidate["readiness"]["coverage"] == 0.75
    assert candidate["readiness"]["assessment_status"] == "insufficient_evidence"
    assert candidate["readiness"]["score"] is None
    assert "overall_coverage_below_80_percent" in candidate["readiness"]["reasons"]
    assert "support_coverage_below_50_percent" in candidate["readiness"]["reasons"]


def test_canonical_transport_bytes_ignore_python_mapping_insertion_order():
    candidate = _candidate("full_pass")
    reversed_top_level = {key: candidate[key] for key in reversed(tuple(candidate))}
    assert serialize_geo_v8_transport_candidate(reversed_top_level) == serialize_geo_v8_transport_candidate(candidate)


def test_canonical_transport_serialization_does_not_mutate_candidate():
    candidate = _candidate("all_unknown")
    before = deepcopy(candidate)
    serialize_geo_v8_transport_candidate(candidate)
    assert candidate == before


def test_canonical_transport_serialization_rejects_digest_valid_semantic_forgery():
    candidate = _candidate("full_pass")
    candidate["authority_verified"] = True
    unsigned = deepcopy(candidate)
    unsigned.pop("candidate_digest")
    candidate["candidate_digest"] = sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()

    with pytest.raises(ValueError, match="unsealed and non-authoritative"):
        serialize_geo_v8_transport_candidate(candidate)
