from copy import deepcopy
from hashlib import sha256

import pytest

from app.geo_readiness import CHECKS, Observation
from app.geo_readiness_v2 import evaluate_geo_v2
from app.geo_v8_transport_candidate import (
    CLAIM_BOUNDARY,
    SEAL_STATE,
    VERSION,
    _candidate_digest,
    build_geo_v8_transport_candidate,
    validate_geo_v8_transport_candidate,
)


def opaque(raw):
    return "p_" + sha256(raw.encode()).hexdigest()[:24]


def rows(page_ids, state="pass"):
    reason = "fixture N/A" if state == "not_applicable" else ""
    evidence = "evidence-ref" if state in {"pass", "fail"} else ""
    return [Observation(page, check, state, evidence, reason) for page in page_ids for check in CHECKS]


def build(page_ids=("page-1",), observations=None, **kwargs):
    ids = list(page_ids)
    if observations is None:
        observations = rows(ids)
    return build_geo_v8_transport_candidate(
        ids,
        observations,
        parent_authoritative=True,
        entry_verified=True,
        **kwargs,
    )


def redigest(candidate):
    candidate["candidate_digest"] = _candidate_digest(candidate)
    return candidate


def robots_page(raw, *, gptbot=False):
    return {
        "page_id": raw,
        "robots_txt_rules_known": True,
        "robots_txt_status": "available",
        "robots_txt_status_code": 200,
        "robots_txt_oai_searchbot_allowed": True,
        "robots_txt_gptbot_allowed": gptbot,
        "robots_txt_googlebot_allowed": True,
    }


def test_full_pass_transport_is_unsealed_and_non_authoritative():
    candidate = build()
    assert candidate["version"] == VERSION
    assert candidate["seal_state"] == SEAL_STATE == "unsealed_candidate"
    assert candidate["authority_verified"] is False
    assert candidate["readiness"]["authority_verified"] is False
    assert candidate["readiness"]["score"] == 100
    assert candidate["claim_boundary"] == CLAIM_BOUNDARY
    assert validate_geo_v8_transport_candidate(candidate) is True


def test_readiness_payload_is_exact_v2_output_before_sidecars():
    ids = ["page-1"]
    observations = rows(ids)
    expected = evaluate_geo_v2(ids, observations, parent_authoritative=True, entry_verified=True)
    candidate = build(ids, observations)
    assert candidate["readiness"] == expected


def test_named_robots_sidecar_is_bound_to_observation_scope_but_not_score():
    raw = "https://example.com/product/1"
    page_id = opaque(raw)
    baseline = build((page_id,))
    candidate = build((page_id,), robots_pages=[robots_page(raw)])
    assert candidate["readiness"] == baseline["readiness"]
    assert candidate["named_robots"][0]["page_id"] == page_id
    assert validate_geo_v8_transport_candidate(candidate)


def test_gptbot_disallow_is_neutral_structural_policy_evidence():
    raw = "https://example.com/"
    page_id = opaque(raw)
    candidate = build((page_id,), robots_pages=[robots_page(raw, gptbot=False)])
    gpt = next(item for item in candidate["named_robots"][0]["bots"] if item["crawler_id"] == "gptbot")
    assert gpt["state"] == "observed"
    assert gpt["directive"] == "disallow"
    assert candidate["readiness"]["score"] == 100


def test_valid_llms_txt_is_optional_sidecar_and_cannot_change_score():
    baseline = build()
    candidate = build(llms_txt_observation={
        "url": "https://example.com/llms.txt",
        "status_code": 200,
        "content_type": "text/plain",
        "body": "# Example\n\n> Structural guide\n\n## Docs\n- [Guide](/guide)\n",
    })
    assert candidate["llms_txt"]["presence"] == "present"
    assert candidate["llms_txt"]["format_status"] == "valid"
    assert candidate["readiness"] == baseline["readiness"]


def test_missing_llms_txt_is_neutral_not_a_readiness_failure():
    candidate = build(llms_txt_observation={"url": "https://example.com/llms.txt", "status_code": 404})
    assert candidate["llms_txt"]["presence"] == "absent"
    assert candidate["llms_txt"]["format_status"] == "not_applicable"
    assert candidate["readiness"]["score"] == 100


def test_access_limited_candidate_suppresses_content_and_optional_sidecars():
    raw = "https://example.com/"
    candidate = build(
        access_limited=True,
        robots_pages=[robots_page(raw)],
        llms_txt_observation={"url": "https://example.com/llms.txt", "status_code": 200, "body": "# Example"},
    )
    assert candidate["readiness"]["assessment_status"] == "access_limited"
    assert candidate["readiness"]["score"] is None
    assert candidate["readiness"]["dimensions"] == {}
    assert candidate["named_robots"] == []
    assert candidate["llms_txt"] is None
    assert validate_geo_v8_transport_candidate(candidate)


def test_named_robots_page_outside_scope_fails_closed():
    with pytest.raises(ValueError, match="outside the GEO observation scope"):
        build(("page-1",), robots_pages=[robots_page("https://example.com/")])


def test_duplicate_named_robots_page_fails_closed():
    raw = "https://example.com/"
    page_id = opaque(raw)
    with pytest.raises(ValueError, match="Duplicate"):
        build((page_id,), robots_pages=[robots_page(raw), robots_page(raw)])


def test_malformed_llms_observation_fails_closed():
    with pytest.raises(ValueError):
        build(llms_txt_observation={"url": "https://user:secret@example.com/llms.txt", "status_code": 200, "body": "# Bad"})


def test_candidate_is_deterministic_across_observation_and_robots_order():
    raw_a = "https://example.com/a"
    raw_b = "https://example.com/b"
    ids = [opaque(raw_a), opaque(raw_b)]
    observations = rows(ids)
    forward = build(ids, observations, robots_pages=[robots_page(raw_a), robots_page(raw_b)])
    reverse = build(tuple(reversed(ids)), list(reversed(observations)), robots_pages=[robots_page(raw_b), robots_page(raw_a)])
    assert forward == reverse


@pytest.mark.parametrize("path,value", [
    (("readiness", "score"), 17),
    (("readiness", "coverage"), 0.123),
    (("readiness", "unknown_cell_count"), 9),
    (("version",), "geo_v8_transport_candidate_v999"),
    (("authority_verified",), True),
    (("seal_state",), "sealed"),
    (("claim_boundary",), "ranks_in_chatgpt"),
])
def test_tampering_is_rejected_even_when_digest_is_not_updated(path, value):
    candidate = deepcopy(build())
    target = candidate
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        validate_geo_v8_transport_candidate(candidate)


def test_semantic_authority_tamper_is_rejected_even_with_recomputed_digest():
    candidate = deepcopy(build())
    candidate["authority_verified"] = True
    redigest(candidate)
    with pytest.raises(ValueError, match="unsealed and non-authoritative"):
        validate_geo_v8_transport_candidate(candidate)


def test_semantic_readiness_authority_tamper_is_rejected_even_with_recomputed_digest():
    candidate = deepcopy(build())
    candidate["readiness"]["authority_verified"] = True
    redigest(candidate)
    with pytest.raises(ValueError, match="authority/claim boundary"):
        validate_geo_v8_transport_candidate(candidate)


def test_unknown_cell_count_tamper_is_rejected_even_with_recomputed_digest():
    observations = rows(["page-1"])
    observations[-1] = Observation("page-1", "source_attribution", "not_verified", "", "JS-only uncertainty")
    candidate = build(("page-1",), observations)
    candidate["readiness"]["unknown_cell_count"] = 0
    redigest(candidate)
    with pytest.raises(ValueError, match="unknown-cell count"):
        validate_geo_v8_transport_candidate(candidate)


def test_unknown_dimension_summary_tamper_is_rejected_even_with_recomputed_digest():
    observations = rows(["page-1"])
    observations[-1] = Observation("page-1", "source_attribution", "not_verified", "", "JS-only uncertainty")
    candidate = build(("page-1",), observations)
    candidate["readiness"]["dimension_scores"]["support"]["unknown_cells"] = 0
    redigest(candidate)
    with pytest.raises(ValueError, match="Unknown-cell summary mismatch"):
        validate_geo_v8_transport_candidate(candidate)


def test_dimension_cell_accounting_tamper_is_rejected_even_with_recomputed_digest():
    candidate = deepcopy(build())
    candidate["readiness"]["dimension_scores"]["entity"]["verified_cells"] = 2
    redigest(candidate)
    with pytest.raises(ValueError, match="Incomplete GEO dimension cell accounting"):
        validate_geo_v8_transport_candidate(candidate)


def test_check_count_tamper_is_rejected_even_with_recomputed_digest():
    candidate = deepcopy(build())
    counts = candidate["readiness"]["dimensions"]["entity"]["checks"]["subject_identity"]["counts"]
    counts["pass"] = 0
    redigest(candidate)
    with pytest.raises(ValueError, match="Inconsistent GEO check counts"):
        validate_geo_v8_transport_candidate(candidate)


def test_robot_sidecar_tamper_is_digest_bound():
    raw = "https://example.com/"
    page_id = opaque(raw)
    candidate = build((page_id,), robots_pages=[robots_page(raw)])
    candidate["named_robots"][0]["bots"][0]["directive"] = "disallow"
    with pytest.raises(ValueError, match="digest mismatch"):
        validate_geo_v8_transport_candidate(candidate)


def test_llms_sidecar_tamper_is_digest_bound():
    candidate = build(llms_txt_observation={"url": "https://example.com/llms.txt", "status_code": 200, "body": "# Example"})
    candidate["llms_txt"]["title"] = "Forged"
    with pytest.raises(ValueError, match="digest mismatch"):
        validate_geo_v8_transport_candidate(candidate)


def test_malformed_unknown_cell_container_fails_with_value_error():
    candidate = deepcopy(build())
    candidate["readiness"]["unknown_cells"] = 7
    redigest(candidate)
    with pytest.raises(ValueError, match="unknown-cell transport"):
        validate_geo_v8_transport_candidate(candidate)


def test_recomputed_digest_does_not_make_malformed_robot_sidecar_valid():
    raw = "https://example.com/"
    page_id = opaque(raw)
    candidate = build((page_id,), robots_pages=[robots_page(raw)])
    candidate["named_robots"][0]["bots"][0]["user_agent"] = "MadeUpBot"
    redigest(candidate)
    with pytest.raises(ValueError, match="registry metadata mismatch"):
        validate_geo_v8_transport_candidate(candidate)


def test_recomputed_digest_does_not_make_malformed_llms_sidecar_valid():
    candidate = build(llms_txt_observation={"url": "https://example.com/llms.txt", "status_code": 200, "body": "# Example"})
    candidate["llms_txt"]["presence"] = "absent"
    redigest(candidate)
    with pytest.raises(ValueError, match="absent llms.txt"):
        validate_geo_v8_transport_candidate(candidate)


def test_inputs_are_not_mutated():
    raw = "https://example.com/"
    page_id = opaque(raw)
    ids = [page_id]
    observations = rows(ids)
    robots = [robots_page(raw)]
    llms = {"url": "https://example.com/llms.txt", "status_code": 200, "body": "# Example"}
    before = deepcopy((ids, observations, robots, llms))
    build_geo_v8_transport_candidate(ids, observations, parent_authoritative=True, entry_verified=True, robots_pages=robots, llms_txt_observation=llms)
    assert (ids, observations, robots, llms) == before


def test_unknown_matrix_stays_unscored_and_transport_is_valid():
    candidate = build(observations=[])
    assert candidate["readiness"]["assessment_status"] == "insufficient_evidence"
    assert candidate["readiness"]["score"] is None
    assert candidate["readiness"]["unknown_cell_count"] == len(CHECKS)
    assert validate_geo_v8_transport_candidate(candidate)


def test_all_not_applicable_stays_unscored_and_transport_is_valid():
    candidate = build(observations=rows(["page-1"], state="not_applicable"))
    assert candidate["readiness"]["score"] is None
    assert candidate["readiness"]["unknown_cell_count"] == 0
    assert validate_geo_v8_transport_candidate(candidate)


def test_optional_sidecars_do_not_rescue_insufficient_readiness():
    raw = "https://example.com/"
    page_id = opaque(raw)
    candidate = build(
        (page_id,),
        observations=[],
        robots_pages=[robots_page(raw)],
        llms_txt_observation={"url": "https://example.com/llms.txt", "status_code": 200, "body": "# Example"},
    )
    assert candidate["readiness"]["assessment_status"] == "insufficient_evidence"
    assert candidate["readiness"]["score"] is None
    assert candidate["named_robots"]
    assert candidate["llms_txt"]["format_status"] == "valid"


def test_candidate_digest_is_64_lower_hex_and_not_authority_signature():
    candidate = build()
    assert len(candidate["candidate_digest"]) == 64
    assert candidate["candidate_digest"] == candidate["candidate_digest"].lower()
    int(candidate["candidate_digest"], 16)
    assert candidate["authority_verified"] is False
