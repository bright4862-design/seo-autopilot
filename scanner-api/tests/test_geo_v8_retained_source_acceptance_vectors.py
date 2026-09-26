import json
from pathlib import Path

import pytest

from app.geo_readiness import CHECKS, Observation
from app.geo_v8_transport_candidate import build_geo_v8_transport_candidate
from app.geo_v8_transport_serialization import serialize_geo_v8_transport_candidate
from app.geo_v8_transport_sources import serialize_geo_v8_transport_candidate_for_sources


FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "geo_v8_retained_source_acceptance_vectors.json"
)


def rows(page_ids):
    return [
        Observation(page_id, check_id, "pass", "evidence-ref", "")
        for page_id in page_ids
        for check_id in CHECKS
    ]


@pytest.fixture(scope="module")
def vectors():
    payload = json.loads(FIXTURE_PATH.read_text())
    assert payload["version"] == "geo_v8_retained_source_acceptance_vectors_v1"
    return payload["vectors"]


@pytest.mark.parametrize("vector_index", [0, 1])
def test_fixed_retained_source_vector_matches_expected_structural_evidence(vectors, vector_index):
    vector = vectors[vector_index]
    page_ids = vector["page_ids"]
    candidate = build_geo_v8_transport_candidate(
        page_ids,
        rows(page_ids),
        parent_authoritative=True,
        entry_verified=True,
        access_limited=False,
        robots_pages=vector["robots_pages"],
        llms_txt_observation=vector["llms_txt_observation"],
    )

    expected_bots = vector["expected"]["named_robots"]
    observed_bots = {
        bot["crawler_id"]: {
            "state": bot["state"],
            "directive": bot["directive"],
        }
        for bot in candidate["named_robots"][0]["bots"]
    }
    assert observed_bots == expected_bots

    expected_llms = vector["expected"]["llms_txt"]
    assert {
        key: candidate["llms_txt"][key]
        for key in expected_llms
    } == expected_llms

    assert candidate["readiness"]["assessment_status"] == "assessed"
    assert candidate["readiness"]["score"] == 100.0
    assert candidate["readiness"]["coverage"] == 1.0
    assert candidate["readiness"]["authority_verified"] is False
    assert candidate["authority_verified"] is False

    source_bound = serialize_geo_v8_transport_candidate_for_sources(
        candidate,
        page_ids,
        parent_authoritative=True,
        entry_verified=True,
        access_limited=False,
        robots_pages=vector["robots_pages"],
        llms_txt_observation=vector["llms_txt_observation"],
    )
    assert source_bound == serialize_geo_v8_transport_candidate(candidate)


def test_fixed_source_vectors_do_not_change_scored_readiness(vectors):
    scores = []
    for vector in vectors:
        candidate = build_geo_v8_transport_candidate(
            vector["page_ids"],
            rows(vector["page_ids"]),
            parent_authoritative=True,
            entry_verified=True,
            access_limited=False,
            robots_pages=vector["robots_pages"],
            llms_txt_observation=vector["llms_txt_observation"],
        )
        scores.append(
            (
                candidate["readiness"]["assessment_status"],
                candidate["readiness"]["score"],
                candidate["readiness"]["coverage"],
            )
        )

    assert scores == [("assessed", 100.0, 1.0), ("assessed", 100.0, 1.0)]
