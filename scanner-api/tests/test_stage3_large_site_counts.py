from app.stage3_delivery import build_handoff_v2, summarize_candidate_counts
from app.stage3_priority_factors import build_four_factor_priority


def bounded(count=500, *, lower_bound=False):
    return {
        "affected_pages": [f"/products/{i}" for i in range(150)],
        "affected_pages_complete": False,
        "affected_page_count": count,
        "affected_page_count_is_lower_bound": lower_bound,
        "page_count": count,
        "family_breakdown": {"product_page": count},
        "page_template_family": "product_page",
        "rule": "missing_meta_description",
        "repair_observation_count": count,
    }


def evidence(count=500, nonindexable=0):
    return [{"url": f"/products/{i}", "status_code": 200, "content_type": "text/html", "page_template_family": "product_page", "indexable": i >= nonindexable} for i in range(count)]


def test_b21_counts_the_proved_total_before_presentation_sampling():
    counts = summarize_candidate_counts(bounded())
    assert counts["unique_affected_page_count"] == 500
    assert counts["observation_count"] == 500
    assert counts["truncated_sample_count"] == 490
    assert len(counts["displayed_samples"]) == 10
    assert "affected_page_count_is_lower_bound" not in counts


def test_handoff_preserves_unknown_overlap_as_lower_bound():
    handoff = build_handoff_v2(scan_identity={}, fixes=[bounded(lower_bound=True)], user_agent="FixList")
    [fix] = handoff["fixes"]
    assert fix["counts"]["unique_affected_pages"] == 500
    assert fix["counts"]["affected_page_count_is_lower_bound"] is True


def test_child_counts_are_never_added_without_an_exact_union():
    root = {"affected_pages": ["/products/0"], "groups": [bounded(400), bounded(500)]}
    counts = summarize_candidate_counts(root)
    assert counts["unique_affected_page_count"] == 500
    assert counts["affected_page_count_is_lower_bound"] is True


def test_visible_union_larger_than_each_child_still_has_unknown_omitted_overlap():
    first, second = bounded(200), bounded(200)
    second["affected_pages"] = [f"/other/{i}" for i in range(150)]
    counts = summarize_candidate_counts({"groups": [first, second]})
    assert counts["unique_affected_page_count"] == 300
    assert counts["affected_page_count_is_lower_bound"] is True


def test_truncated_all_indexable_family_uses_proved_numerator():
    factors = build_four_factor_priority(bounded(400), evidence())
    assert factors["reach"] == 0.8
    assert factors["reach_affected_indexable"] == 400


def test_truncated_mixed_indexability_subset_has_unknown_reach():
    factors = build_four_factor_priority(bounded(400), evidence(nonindexable=100))
    assert factors["reach"] is None
    assert factors["reach_state"] == "unknown"


def test_lower_bound_never_becomes_an_exact_priority_ratio():
    factors = build_four_factor_priority(bounded(lower_bound=True), evidence())
    assert factors["reach"] is None
    assert factors["reach_state"] == "unknown"


def test_whole_family_count_proves_reach_even_with_nonindexable_pages():
    factors = build_four_factor_priority(bounded(), evidence(nonindexable=100))
    assert factors["reach"] == 1.0
    assert factors["reach_affected_indexable"] == factors["reach_observed_indexable_family"] == 400
