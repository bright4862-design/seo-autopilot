from copy import deepcopy

import pytest

from app.geo_readiness import CHECKS, Observation
from app.geo_v8_transport_candidate import (
    _candidate_digest,
    build_geo_v8_transport_candidate,
    validate_geo_v8_transport_candidate,
)
from app.geo_v8_transport_semantics import validate_geo_v8_transport_semantics


def rows(page_ids, state="pass"):
    evidence = "evidence-ref" if state in {"pass", "fail"} else ""
    reason = "fixture N/A" if state == "not_applicable" else ""
    return [
        Observation(page_id, check_id, state, evidence, reason)
        for page_id in page_ids
        for check_id in CHECKS
    ]


def build(*, observations=None, parent_authoritative=True, entry_verified=True, access_limited=False):
    page_ids = ["page-1"]
    return build_geo_v8_transport_candidate(
        page_ids,
        rows(page_ids) if observations is None else observations,
        parent_authoritative=parent_authoritative,
        entry_verified=entry_verified,
        access_limited=access_limited,
    )


def redigest(candidate):
    candidate["candidate_digest"] = _candidate_digest(candidate)
    return candidate


def validate(candidate, **overrides):
    gates = {
        "parent_authoritative": True,
        "entry_verified": True,
        "access_limited": False,
    }
    gates.update(overrides)
    return validate_geo_v8_transport_semantics(candidate, **gates)


def test_recomputed_digest_cannot_turn_low_coverage_into_assessed_numeric_score():
    candidate = build(observations=[])
    assert candidate["readiness"]["assessment_status"] == "insufficient_evidence"
    assert candidate["readiness"]["score"] is None

    candidate["readiness"]["assessment_status"] = "assessed"
    candidate["readiness"]["score"] = 100
    candidate["readiness"]["reasons"] = []
    redigest(candidate)

    with pytest.raises(ValueError, match="arithmetic/gate semantics mismatch"):
        validate(candidate)


def test_recomputed_digest_cannot_forge_overall_coverage():
    candidate = build(observations=[])
    candidate["readiness"]["coverage"] = 1.0
    redigest(candidate)
    with pytest.raises(ValueError, match="arithmetic/gate semantics mismatch"):
        validate(candidate)


def test_recomputed_digest_cannot_forge_score_bounds():
    candidate = build()
    candidate["readiness"]["score_bounds"] = {"lower": 0.0, "upper": 100.0}
    redigest(candidate)
    with pytest.raises(ValueError, match="arithmetic/gate semantics mismatch"):
        validate(candidate)


def test_explicit_gate_inputs_accept_untampered_candidate():
    candidate = build(parent_authoritative=False, entry_verified=True)
    assert validate(candidate, parent_authoritative=False, entry_verified=True) is True


def test_explicit_gate_inputs_reject_recomputed_parent_gate_tamper():
    candidate = build(parent_authoritative=False, entry_verified=True)
    candidate["readiness"]["assessment_status"] = "assessed"
    candidate["readiness"]["score"] = 100
    candidate["readiness"]["reasons"] = []
    redigest(candidate)
    assert validate_geo_v8_transport_candidate(candidate) is True
    with pytest.raises(ValueError, match="arithmetic/gate semantics mismatch"):
        validate(candidate, parent_authoritative=False, entry_verified=True)


def test_explicit_gate_inputs_require_all_three_booleans():
    candidate = build()
    with pytest.raises(ValueError, match="three boolean gate facts"):
        validate_geo_v8_transport_semantics(
            candidate,
            parent_authoritative=True,
            entry_verified=True,
            access_limited=None,
        )


def test_unknown_cells_must_match_not_verified_counts_per_check():
    observations = rows(["page-1"])
    observations[-1] = Observation(
        "page-1",
        "source_attribution",
        "not_verified",
        "",
        "JS-only uncertainty",
    )
    candidate = build(observations=observations)
    unknown = candidate["readiness"]["unknown_cells"][0]
    unknown["check_id"] = "accountability"
    unknown["dimension"] = "support"
    redigest(candidate)
    with pytest.raises(ValueError, match="[Uu]nknown-cell"):
        validate(candidate)


def test_recomputed_digest_cannot_forge_dimension_na_vs_verified_summary():
    candidate = build()
    summary = candidate["readiness"]["dimension_scores"]["access"]
    assert summary["unknown_cells"] == 0
    assert summary["not_applicable_cells"] == 0
    assert summary["verified_cells"] == 3

    summary["not_applicable_cells"] = 1
    summary["verified_cells"] = 2
    redigest(candidate)

    # Shape accounting alone accepts the rewritten 0 + 1 + 2 == 3 summary.
    assert validate_geo_v8_transport_candidate(candidate) is True
    with pytest.raises(ValueError, match="dimension summary disagrees"):
        validate(candidate)


def test_access_limited_explicit_gate_mismatch_fails_closed():
    candidate = build(access_limited=True)
    with pytest.raises(ValueError, match="access-limited gate mismatch"):
        validate(candidate, access_limited=False)


def test_access_limited_candidate_validates_without_exposing_content_arithmetic():
    candidate = build(access_limited=True)
    assert validate(candidate, access_limited=True) is True


def test_semantic_validation_does_not_mutate_candidate():
    candidate = build(observations=[])
    before = deepcopy(candidate)
    validate(candidate)
    assert candidate == before
