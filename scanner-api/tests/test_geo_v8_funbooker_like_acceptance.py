from copy import deepcopy

from app.geo_readiness import CHECKS, Observation
from app.geo_v8_transport_candidate import build_geo_v8_transport_candidate
from app.geo_v8_transport_reload import validate_geo_v8_transport_reload_identity
from app.geo_v8_transport_sources import serialize_geo_v8_transport_candidate_for_sources


PAGE_IDS = tuple(f"p_{index:03d}" for index in range(139))
PASS_COUNTS = {
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
EXPECTED_REASONS = [
    "overall_coverage_below_80_percent",
    "entity_coverage_below_50_percent",
    "support_coverage_below_50_percent",
]


def funbooker_like_observations():
    rows = []
    for index, page_id in enumerate(PAGE_IDS):
        for check_id in CHECKS:
            if index < PASS_COUNTS[check_id]:
                rows.append(
                    Observation(
                        page_id,
                        check_id,
                        "pass",
                        f"fixture:{check_id}:{index}",
                        "",
                    )
                )
            else:
                rows.append(
                    Observation(
                        page_id,
                        check_id,
                        "not_verified",
                        "",
                        "production_like_retained_evidence_insufficient",
                    )
                )
    return rows


def test_funbooker_like_insufficient_evidence_survives_v8_transport_and_reload():
    observations = funbooker_like_observations()
    candidate = build_geo_v8_transport_candidate(
        PAGE_IDS,
        observations,
        parent_authoritative=True,
        entry_verified=True,
        access_limited=False,
    )
    readiness = candidate["readiness"]

    assert len(observations) == 139 * len(CHECKS) == 1668
    assert readiness["sample_pages"] == 139
    assert readiness["assessment_status"] == "insufficient_evidence"
    assert readiness["score"] is None
    assert readiness["coverage"] == 0.456835
    assert readiness["score_bounds"] == {"lower": 45.683453, "upper": 100.0}
    assert readiness["reasons"] == EXPECTED_REASONS
    assert readiness["authority_verified"] is False
    assert candidate["authority_verified"] is False
    assert candidate["seal_state"] == "unsealed_candidate"

    access = readiness["dimensions"]["access"]
    clarity = readiness["dimensions"]["clarity"]
    entity = readiness["dimensions"]["entity"]
    support = readiness["dimensions"]["support"]
    assert access["coverage"] == 0.829736
    assert access["score"] == 100.0
    assert clarity["coverage"] == 0.997602
    assert clarity["score"] == 100.0
    assert entity["coverage"] == 0.0 and entity["score"] is None
    assert support["coverage"] == 0.0 and support["score"] is None

    summaries = readiness["dimension_scores"]
    assert summaries["access"]["verified_cells"] == 346
    assert summaries["access"]["unknown_cells"] == 71
    assert summaries["clarity"]["verified_cells"] == 416
    assert summaries["clarity"]["unknown_cells"] == 1
    assert summaries["entity"]["verified_cells"] == 0
    assert summaries["entity"]["unknown_cells"] == 417
    assert summaries["support"]["verified_cells"] == 0
    assert summaries["support"]["unknown_cells"] == 417
    assert readiness["unknown_cell_count"] == 906

    expected_preseal = serialize_geo_v8_transport_candidate_for_sources(
        candidate,
        PAGE_IDS,
        parent_authoritative=True,
        entry_verified=True,
        access_limited=False,
    )
    reloaded = deepcopy(candidate)
    assert validate_geo_v8_transport_reload_identity(
        expected_preseal,
        reloaded,
        PAGE_IDS,
        parent_authoritative=True,
        entry_verified=True,
        access_limited=False,
    ) is True

    reordered = build_geo_v8_transport_candidate(
        tuple(reversed(PAGE_IDS)),
        list(reversed(observations)),
        parent_authoritative=True,
        entry_verified=True,
        access_limited=False,
    )
    reordered_preseal = serialize_geo_v8_transport_candidate_for_sources(
        reordered,
        tuple(reversed(PAGE_IDS)),
        parent_authoritative=True,
        entry_verified=True,
        access_limited=False,
    )
    assert reordered_preseal == expected_preseal
