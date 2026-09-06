"""The score has to be able to account for itself.

FixList shows a number and a grade and nothing else, and the number is the
first thing an owner argues with. `compute_health_score_breakdown()` has always
known exactly where every point went -- which area, how much, and which
ceilings bound the result -- and none of it left the scanner.

The rule these pin down is that the explanation is a *record* of the score, not
a second opinion about it. If `final_score` can ever disagree with the stored
`health_score`, the page is showing arithmetic that does not add up, which is
worse than showing nothing.
"""

from app.health_score_explanation import (
    HEALTH_SCORE_EXPLANATION_VERSION,
    apply_score_ceiling,
    build_health_score_explanation,
)
from app.review import compute_health_score_breakdown
from app.review_calibration import apply_review_evidence_calibration
from app.evidence_quality import apply_evidence_quality_gate

FINGERPRINT = {
    "pages_crawled": 150,
    "pages_found": 184,
    "pages_received": 150,
    "sampled_pages_sent_to_ai": 150,
}


def _fix(rule, priority, category, count, **extra):
    return {
        "rule": rule,
        "priority": priority,
        "category": category,
        "page_count": count,
        "affected_pages": [f"/{rule}/{index}" for index in range(count)],
        **extra,
    }


MIXED = [
    _fix("canonical_target_noindex", "critical", "canonical", 30, page_scope="sitewide"),
    _fix("redirect_chain", "high", "internal_link", 12),
    _fix("missing_meta_description", "medium", "meta_description", 9),
    _fix("missing_h1", "medium", "thin_content", 6),
    _fix("image_alt_text", "low", "image_alt_text", 20),
]


def _explain(fixes, fingerprint=None, **kwargs):
    fingerprint = FINGERPRINT if fingerprint is None else fingerprint
    breakdown = compute_health_score_breakdown(fixes, fingerprint)
    return breakdown, build_health_score_explanation(breakdown, **kwargs)


def test_the_explanation_records_the_score_it_explains():
    breakdown, explanation = _explain(MIXED)
    assert explanation["version"] == HEALTH_SCORE_EXPLANATION_VERSION
    assert explanation["starting_score"] == 100
    assert explanation["final_score"] == breakdown["score"]


def test_the_deductions_sum_to_the_stated_total():
    # Bucket penalties are floats and the customer sees whole numbers. Rounding
    # each independently makes a column that does not add up to its own total,
    # which is exactly the kind of arithmetic an owner checks first.
    _, explanation = _explain(MIXED)
    assert sum(row["points"] for row in explanation["deductions"]) == explanation["total_deduction"]
    assert explanation["total_deduction"] > 0


def test_rounding_the_rows_independently_would_not_add_up():
    """The apportionment, on penalties chosen so naive rounding breaks.

    MIXED happens to round cleanly, so removing the remainder step left every
    other assertion green. These four penalties each round down, losing three
    points between them -- a column that visibly does not add up to its own
    total, which is the first thing an owner checks.
    """
    breakdown = {
        "score": 55,
        "total_penalty": 45.0,
        "bucket_penalties": {
            "search_visibility": 11.25,
            "site_structure": 11.25,
            "search_appearance": 11.25,
            "page_content": 11.25,
        },
        "coverage_ceiling": 100,
        "applied_ceiling": 100,
        "ceiling_reason": "",
    }
    explanation = build_health_score_explanation(breakdown)
    naive = sum(int(value) for value in breakdown["bucket_penalties"].values())
    assert naive == 44, "this fixture must not round cleanly, or it proves nothing"
    assert explanation["total_deduction"] == 45
    assert sum(row["points"] for row in explanation["deductions"]) == 45


def test_a_bucket_this_build_cannot_name_is_not_published():
    # The scorer's five buckets are all mapped, so no live fixture can reach
    # this branch -- and a guard nothing exercises is one that gets deleted.
    # A bucket added to the scorer without a customer label must drop out
    # rather than print its key.
    explanation = build_health_score_explanation({
        "score": 70,
        "total_penalty": 30.0,
        "bucket_penalties": {"search_visibility": 20.0, "some_new_bucket": 10.0},
        "coverage_ceiling": 100,
        "applied_ceiling": 100,
        "ceiling_reason": "",
    })
    categories = [row["category"] for row in explanation["deductions"]]
    assert categories == ["Search visibility"]
    assert "some_new_bucket" not in repr(explanation)
    # And the column still adds up to what it shows, not to what was withheld.
    assert sum(row["points"] for row in explanation["deductions"]) == explanation["total_deduction"]


def test_every_deduction_is_a_customer_area_not_a_bucket_key():
    _, explanation = _explain(MIXED)
    assert explanation["deductions"], "a site with findings must show where the points went"
    for row in explanation["deductions"]:
        assert "_" not in row["category"], f"internal bucket key leaked: {row['category']}"
        assert row["category"][0].isupper()
        assert row["points"] >= 1, "a row worth no points is noise"


def test_no_rule_name_or_fingerprint_reaches_the_explanation():
    # action_penalties is keyed by rule identity. It is the useful half of the
    # breakdown for us and the half that must never be published.
    breakdown, explanation = _explain(MIXED)
    assert breakdown["action_penalties"], "this fixture must exercise per-action penalties"
    published = repr(explanation)
    for key in breakdown["action_penalties"]:
        assert key not in published, f"an internal action key reached the customer: {key}"
    for rule in ("canonical_target_noindex", "redirect_chain", "image_alt_text"):
        assert rule not in published


def test_deductions_are_ordered_by_what_cost_the_most():
    _, explanation = _explain(MIXED)
    points = [row["points"] for row in explanation["deductions"]]
    assert points == sorted(points, reverse=True)


def test_a_clean_scan_explains_a_perfect_score_with_no_deductions():
    breakdown, explanation = _explain([])
    assert breakdown["score"] == 100
    assert explanation["final_score"] == 100
    assert explanation["deductions"] == []
    assert explanation["total_deduction"] == 0


def test_verification_only_findings_are_declared_excluded():
    _, excluded = _explain(MIXED, verification_findings_excluded=True)
    _, included = _explain(MIXED, verification_findings_excluded=False)
    assert excluded["verification_findings_excluded"] is True
    assert included["verification_findings_excluded"] is False


def test_a_sample_ceiling_is_recorded_as_an_evidence_limit():
    # 20 of 400 pages: the ceiling is about how much the scan saw, and saying so
    # is the difference between "your site scores 92" and "we only looked at 20
    # pages, so 92 is the most this scan can report".
    sampled = dict(FINGERPRINT, pages_crawled=20, pages_found=400)
    breakdown, explanation = _explain([], sampled)
    assert breakdown["coverage_ceiling"] == 92
    assert explanation["final_score"] == 92
    assert explanation["applied_ceiling"] == 92
    assert explanation["ceiling_reason"] == "sample_size"
    assert explanation["total_deduction"] == 0, "a ceiling is not a deduction"


def test_a_site_under_no_ceiling_says_so():
    _, explanation = _explain(MIXED)
    assert explanation["applied_ceiling"] == 100
    assert explanation["ceiling_reason"] == ""


def test_the_floor_is_declared_rather_than_shown_as_bad_arithmetic():
    # Without the floor this scores 11. 100 - total_deduction would then be a
    # different number from the score on screen, and nothing would explain the
    # gap.
    everything = [
        _fix(rule, "critical", category, 140, page_scope="sitewide")
        for rule, category in [
            ("noindex_issue", "indexability"),
            ("canonical_target_noindex", "canonical"),
            ("redirect_chain", "internal_link"),
            ("missing_meta_description", "meta_description"),
            ("missing_h1", "thin_content"),
            ("image_alt_text", "image_alt_text"),
        ]
    ]
    breakdown, explanation = _explain(everything)
    assert breakdown["score"] == 40
    assert explanation["final_score"] == 40
    assert explanation["floor_applied"] is True
    assert 100 - explanation["total_deduction"] < 40, "this fixture must fall through the floor"


def test_a_blocked_crawl_is_an_evidence_limit_not_a_verdict_on_the_site():
    blocked = dict(FINGERPRINT, blocked_access_pages=40, pages_crawled=1, pages_received=1)
    breakdown, explanation = _explain([], blocked)
    assert explanation["final_score"] == breakdown["score"]
    assert explanation["ceiling_reason"] == "blocked_access"
    assert explanation["deductions"] == [], "nothing was found, so nothing may be deducted"


# A light finding set, well clear of every ceiling, so a clamp applied
# afterwards is unambiguously the thing that moved the number.
LIGHT = [_fix("missing_h1", "medium", "thin_content", 4)]


def test_a_later_ceiling_moves_the_final_score_with_it():
    # The quality gate runs after calibration and can clamp the score. An
    # explanation sealed before that clamp would state a score the record does
    # not hold.
    _, explanation = _explain(LIGHT)
    before = explanation["final_score"]
    clamped = apply_score_ceiling(explanation, 55, "incomplete_evidence")
    assert before > 55, "this fixture must be above the ceiling for the clamp to bite"
    assert clamped["final_score"] == 55
    assert clamped["applied_ceiling"] == 55
    assert clamped["ceiling_reason"] == "incomplete_evidence"


def test_a_ceiling_above_the_score_changes_nothing():
    _, explanation = _explain(LIGHT)
    assert explanation["final_score"] < 99
    assert apply_score_ceiling(explanation, 99, "incomplete_evidence") == explanation


def test_an_unrecognised_ceiling_reason_is_refused():
    # The reason is published. Accepting an arbitrary string here is how a
    # diagnostic message reaches the page through a field nobody was watching.
    _, explanation = _explain(LIGHT)
    clamped = apply_score_ceiling(explanation, 55, "worker crashed at 0x7f: see logs")
    assert clamped["ceiling_reason"] == "other"


def test_a_missing_or_broken_breakdown_produces_no_explanation():
    assert build_health_score_explanation(None) is None
    assert build_health_score_explanation({}) is None
    assert build_health_score_explanation({"score": None}) is None
    assert apply_score_ceiling(None, 55, "incomplete_evidence") is None


# --------------------------------------------------------- the live pipeline --


def _review(fixes, fingerprint=None):
    # `recommendations` is the key calibration reads. Under `recommended_actions`
    # every fixture arrived empty, the score came out 100, and the pipeline
    # tests below passed while exercising nothing.
    return {
        "success": True,
        "recommendations": list(fixes),
        "site_fingerprint": dict(FINGERPRINT if fingerprint is None else fingerprint),
        "scan_status": "complete",
    }


def _calibrated(fixes, payload=None, **review_overrides):
    review = _review(fixes)
    review.update(review_overrides)
    calibrated = apply_review_evidence_calibration(review, payload or {})
    assert calibrated["recommendations"], "the fixture emptied itself in calibration"
    return calibrated


def test_the_calibrated_review_carries_an_explanation_matching_its_score():
    """The invariant that matters, on the object that is actually persisted.

    Everything above tests the builder. This tests that the number on the record
    and the number in its explanation are the same one, through the real
    calibration path -- which recomputes the score from the scoring subset and
    applies its own ceiling afterwards.
    """
    calibrated = _calibrated(MIXED)
    explanation = calibrated.get("health_score_explanation")
    assert explanation, "the calibrated review must carry its own explanation"
    assert explanation["final_score"] == calibrated["health_score"]
    assert explanation["version"] == HEALTH_SCORE_EXPLANATION_VERSION


def test_the_evidence_quality_gate_keeps_the_explanation_in_step():
    """The gate runs last and can lower the score. It must move the explanation.

    This is the seam the invariant breaks at: calibration seals an explanation,
    the gate clamps `health_score` to 55, and the page then shows a breakdown
    that adds up to a different number than the score printed above it.
    """
    payload = {
        "crawled_pages": [
            {"url": "/", "status_code": 200, "title": "Home", "h1": "Home", "word_count": 80},
            {"url": "/hello-world", "status_code": 200, "title": "Hello", "word_count": 30},
            {"url": "/sample-page", "status_code": 200, "title": "Sample", "word_count": 30},
        ],
    }
    # Again LIGHT: a fixture already sitting on the ceiling cannot show that the
    # gate moved anything.
    assert _calibrated(LIGHT, payload)["health_score"] > 55
    gated = apply_evidence_quality_gate(_calibrated(LIGHT, payload), payload)
    assert gated["health_score"] <= 55, "the gate must actually clamp here"

    explanation = gated.get("health_score_explanation")
    assert explanation, "the gate must not drop the explanation"
    assert explanation["final_score"] == gated["health_score"], (
        f"explanation says {explanation['final_score']}, record says {gated['health_score']}"
    )


def test_the_calibration_ceiling_moves_the_explanation_with_the_score():
    # An inconclusive review is clamped to 55 inside calibration itself, after
    # the explanation was built. This is the second of the two seams, and the
    # gate test below only covers the first.
    # LIGHT, not MIXED: MIXED already scores exactly 55 from its findings, so
    # clamping to 55 is a no-op and the clamp is never the thing under test.
    calibrated = _calibrated(LIGHT, scan_status="inconclusive_insufficient_evidence")
    assert _calibrated(LIGHT)["health_score"] > 55, "the fixture must be above the ceiling"

    assert calibrated["health_score"] <= 55
    explanation = calibrated["health_score_explanation"]
    assert explanation["final_score"] == calibrated["health_score"]
    assert explanation["final_score"] == 55
    assert explanation["ceiling_reason"] == "incomplete_evidence"


def test_a_verification_only_finding_is_declared_out_of_the_score():
    # These are "check this" items that never move the number. Saying so is the
    # difference between a customer reading the list as six problems and
    # reading it as five problems and one thing to confirm.
    verification = dict(
        _fix("potential_orphan_pages", "low", "internal_link", 3),
        limitation_code="sampled_crawl_cannot_prove_orphan",
    )
    calibrated = _calibrated([*MIXED, verification])
    assert calibrated["health_score_explanation"]["verification_findings_excluded"] is True
    assert _calibrated(MIXED)["health_score_explanation"]["verification_findings_excluded"] is False


def test_an_unscored_review_carries_no_explanation():
    # health_score_status "insufficient_evidence" stores no score at all. An
    # explanation of a score that does not exist is the same overstatement this
    # whole release is about.
    payload = {"crawled_pages": [{"url": "/", "status_code": 200, "title": "Home", "word_count": 5}]}
    gated = apply_evidence_quality_gate(apply_review_evidence_calibration(_review([]), payload), payload)
    if gated.get("health_score") is None:
        assert not gated.get("health_score_explanation")
