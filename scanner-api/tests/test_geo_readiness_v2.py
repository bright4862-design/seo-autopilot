from copy import deepcopy

import pytest

from app.geo_readiness import CHECKS, DIMENSIONS, Observation, VERSION as V1_VERSION, evaluate_geo
from app.geo_readiness_v2 import VERSION, evaluate_geo_v2


def rows(page_ids=("page-1",), state="pass"):
    return [Observation(page, check, state, "evidence-1" if state in {"pass", "fail"} else "", "fixture" if state == "not_applicable" else "")
            for page in page_ids for check in CHECKS]


def core_v1(result):
    return {key: result[key] for key in (
        "assessment_status", "score", "coverage", "score_bounds", "bounds_kind",
        "sample_pages", "dimensions", "reasons", "authority_verified",
    )}


def core_v2(result):
    return {key: result[key] for key in (
        "assessment_status", "score", "coverage", "score_bounds", "bounds_kind",
        "sample_pages", "dimensions", "reasons", "authority_verified",
    )}


def assess(page_ids=("page-1",), observations=None, **kwargs):
    if observations is None:
        observations = rows(page_ids)
    return evaluate_geo_v2(list(page_ids), observations, parent_authoritative=True, entry_verified=True, **kwargs)


def test_full_known_candidate_is_exact_v1_compatible():
    observations = rows(state="pass")
    v1 = evaluate_geo(["page-1"], observations, parent_authoritative=True, entry_verified=True)
    v2 = assess(observations=observations)
    assert v2["geo_readiness_version"] == VERSION
    assert v2["compatibility_base_version"] == V1_VERSION
    assert core_v2(v2) == core_v1(v1)
    assert v2["score"] == 100
    assert v2["unknown_cells"] == []


def test_full_failure_candidate_is_exact_v1_compatible():
    observations = rows(state="fail")
    v1 = evaluate_geo(["page-1"], observations, parent_authoritative=True, entry_verified=True)
    v2 = assess(observations=observations)
    assert core_v2(v2) == core_v1(v1)
    assert v2["score"] == 0


def test_omitted_cell_is_explicit_unknown_without_changing_v1_score():
    observations = rows()[:-1]
    v1 = evaluate_geo(["page-1"], observations, parent_authoritative=True, entry_verified=True)
    v2 = assess(observations=observations)
    assert core_v2(v2) == core_v1(v1)
    assert v2["unknown_cell_count"] == 1
    assert v2["unknown_cells"] == [{
        "page_id": "page-1", "check_id": "source_attribution", "dimension": "support",
        "reason": "observation_missing",
    }]


def test_explicit_not_verified_reason_is_transported_but_not_evidence_ref():
    observations = rows()
    observations[-1] = Observation("page-1", "source_attribution", "not_verified", "should-not-surface", "JS-only evidence unavailable")
    result = assess(observations=observations)
    assert result["unknown_cells"][0]["reason"] == "JS-only evidence unavailable"
    assert "evidence_ref" not in result["unknown_cells"][0]


def test_not_applicable_is_resolved_not_unknown():
    observations = rows()
    observations[-1] = Observation("page-1", "source_attribution", "not_applicable", reason="clearly non-article structured type")
    result = assess(observations=observations)
    assert result["unknown_cell_count"] == 0
    assert result["dimension_scores"]["support"]["not_applicable_cells"] == 1
    assert result["dimension_scores"]["support"]["verified_cells"] == 2


def test_dimension_scores_are_explicit_and_copy_v1_dimension_values():
    observations = rows()
    observations[0] = Observation("page-1", "search_policy", "fail", "e")
    result = assess(observations=observations)
    assert tuple(result["dimension_scores"]) == DIMENSIONS
    for dimension in DIMENSIONS:
        assert result["dimension_scores"][dimension]["score"] == result["dimensions"][dimension]["score"]
        assert result["dimension_scores"][dimension]["coverage"] == result["dimensions"][dimension]["coverage"]
    assert result["dimension_scores"]["access"]["score"] == pytest.approx(66.666667)


def test_scope_is_explicit_bounded_and_order_independent():
    pages = ("page-b", "page-a")
    observations = rows(pages)
    forward = assess(pages, observations)
    reverse = assess(tuple(reversed(pages)), list(reversed(observations)))
    assert forward["observation_scope"] == reverse["observation_scope"]
    assert forward["observation_scope"]["kind"] == "declared_search_facing_sample"
    assert forward["observation_scope"]["origin"] == "retained_evidence_only"
    assert len(forward["observation_scope"]["page_set_digest"]) == 64


def test_exact_eighty_percent_gate_matches_v1():
    pages = [f"p{i}" for i in range(5)]
    complete = [Observation(p, c, "pass", "e") for p in pages for c in CHECKS]
    for missing, expected in ((12, "assessed"), (13, "insufficient_evidence")):
        v1 = evaluate_geo(pages, complete[missing:], parent_authoritative=True, entry_verified=True)
        v2 = evaluate_geo_v2(pages, complete[missing:], parent_authoritative=True, entry_verified=True)
        assert v2["assessment_status"] == expected == v1["assessment_status"]
        assert core_v2(v2) == core_v1(v1)


def test_access_limited_suppresses_content_diagnostics_and_numeric_scores():
    result = assess(access_limited=True)
    assert result["assessment_status"] == "access_limited"
    assert result["score"] is None
    assert result["dimensions"] == {}
    assert result["unknown_cells"] == []
    assert result["observation_scope"]["access_limited"] is True
    assert all(summary["score"] is None and summary["coverage"] is None for summary in result["dimension_scores"].values())


def test_all_unknown_stays_insufficient_and_lists_complete_matrix():
    result = assess(observations=[])
    assert result["assessment_status"] == "insufficient_evidence"
    assert result["score"] is None
    assert result["unknown_cell_count"] == len(CHECKS)
    assert result["coverage"] == 0


def test_all_not_applicable_stays_unscored_without_unknown_cells():
    observations = rows(state="not_applicable")
    result = assess(observations=observations)
    assert result["score"] is None
    assert result["coverage"] == 0
    assert result["unknown_cells"] == []
    assert all(summary["not_applicable_cells"] == 3 for summary in result["dimension_scores"].values())


def test_candidate_keeps_authority_false_and_claim_boundary_explicit():
    result = assess()
    assert result["authority_verified"] is False
    assert result["claim_boundary"] == "structural_readiness_not_ai_citations_inclusion_visibility_or_traffic"


def test_input_is_not_mutated():
    pages = ["page-1"]
    observations = rows()
    before_pages = deepcopy(pages)
    before_observations = deepcopy(observations)
    assess(tuple(pages), observations)
    assert pages == before_pages
    assert observations == before_observations


@pytest.mark.parametrize("pages,observations", [
    (["p", "p"], []),
    ([str(i) for i in range(151)], []),
    (["p"], [Observation("other", "search_policy", "pass", "e")]),
    (["p"], [Observation("p", "made_up", "pass", "e")]),
    (["p"], [Observation("p", "search_policy", "maybe", "e")]),
])
def test_v2_does_not_weaken_v1_validation(pages, observations):
    with pytest.raises(ValueError):
        evaluate_geo_v2(pages, observations, parent_authoritative=True, entry_verified=True)


def test_unknown_cells_are_deterministic_in_page_then_check_order():
    pages = ["b", "a"]
    result = evaluate_geo_v2(pages, [], parent_authoritative=True, entry_verified=True)
    expected = [(page, check) for page in sorted(pages) for check in CHECKS]
    assert [(row["page_id"], row["check_id"]) for row in result["unknown_cells"]] == expected
