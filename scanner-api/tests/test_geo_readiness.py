import pytest

from app.geo_readiness import CHECKS, Observation, evaluate_geo


def rows(state="pass"):
    return [Observation("page-1", check, state, "evidence-1", "fixture") for check in CHECKS]


def assess(observations, **kwargs):
    return evaluate_geo(["page-1"], observations, parent_authoritative=True,
                        entry_verified=True, **kwargs)


@pytest.mark.parametrize("state,score", [("pass", 100), ("fail", 0)])
def test_complete_known_results(state, score):
    result = assess(rows(state))
    assert result["score"] == score
    assert result["coverage"] == 1
    assert result["assessment_status"] == "assessed"


def test_equal_dimensions_and_numeric_bounds():
    observations = [Observation("page-1", c, "fail" if d == "access" else "pass", "e")
                    for c, d in CHECKS.items()]
    result = assess(observations)
    assert result["score"] == 75
    assert result["score_bounds"] == {"lower": 75.0, "upper": 75.0}


def test_missing_dimension_cannot_look_clean():
    result = assess([r for r in rows() if CHECKS[r.check_id] != "support"])
    assert result["score"] is None
    assert result["coverage"] == .75
    assert result["assessment_status"] == "insufficient_evidence"


def test_partial_unknown_is_not_a_pass_or_failure():
    result = assess(rows()[:-1])
    assert result["score"] == 100
    assert result["coverage"] == pytest.approx(11 / 12, abs=1e-6)
    assert result["score_bounds"]["lower"] == pytest.approx(91.666667)
    assert result["score_bounds"]["upper"] == 100


def test_blocked_or_unsealed_scan_cannot_receive_score():
    assert assess(rows(), access_limited=True)["assessment_status"] == "access_limited"
    assert assess(rows(), access_limited=True)["score"] is None
    assert evaluate_geo(["page-1"], rows())["score"] is None


def test_order_does_not_change_output():
    assert assess(rows()) == assess(list(reversed(rows())))


@pytest.mark.parametrize("observations", [
    lambda: rows() + rows()[:1],
    lambda: [Observation("page-1", "made_up", "pass", "e")],
    lambda: [Observation("page-2", next(iter(CHECKS)), "pass", "e")],
    lambda: [Observation("page-1", next(iter(CHECKS)), "maybe", "e")],
    lambda: [Observation("page-1", next(iter(CHECKS)), "pass")],
    lambda: [Observation("page-1", next(iter(CHECKS)), "not_applicable")],
])
def test_invalid_evidence_is_rejected(observations):
    with pytest.raises(ValueError):
        assess(observations())


def test_na_requires_reason_and_never_earns_points():
    result = assess(rows("not_applicable"))
    assert result["score"] is None
    assert result["coverage"] == 0


def test_cap_and_duplicate_pages_are_rejected():
    for pages in (["p"] * 2, [str(i) for i in range(151)]):
        with pytest.raises(ValueError):
            evaluate_geo(pages, [])


def test_empty_scan_has_no_score():
    assert evaluate_geo([], [])["score"] is None


@pytest.mark.parametrize("missing,expected", [(12, "assessed"), (13, "insufficient_evidence")])
def test_exact_eighty_percent_gate(missing, expected):
    pages = [f"p{i}" for i in range(5)]
    complete = [Observation(p, c, "pass", "e") for p in pages for c in CHECKS]
    result = evaluate_geo(pages, complete[missing:], parent_authoritative=True, entry_verified=True)
    assert result["assessment_status"] == expected


def test_string_authority_flag_is_not_truthy_authority():
    with pytest.raises(ValueError):
        evaluate_geo(["page-1"], rows(), parent_authoritative="false", entry_verified=True)


def test_na_excludes_only_its_check_not_unknown_checks():
    observations = rows()
    observations[0] = Observation("page-1", observations[0].check_id, "not_applicable", reason="fixture exclusion")
    assert assess(observations)["coverage"] == 1
    assert assess(observations)["score"] == 100
    assert assess(observations[:-3])["score"] is None
