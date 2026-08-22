from app.repair_priority import CoverageContext, _family_label, _priority_reason


def context(affected: int, checked: int) -> CoverageContext:
    return CoverageContext(
        affected_reported=affected,
        affected_observed=affected,
        affected_eligible=affected,
        checked_eligible=checked,
        indexable_affected=0,
        non_indexable_affected=0,
        unknown_indexability_affected=affected,
        indexable_checked_eligible=0,
        important_affected=0,
    )


def test_family_labels_do_not_repeat_page():
    assert _family_label("comparison_page") == "comparison pages"
    assert _family_label("collection_page") == "collection pages"
    assert _family_label("homepage") == "homepage"


def test_priority_reason_uses_singular_verb_for_one_affected_page():
    reason = _priority_reason(
        {"page_template_family": "guide_article", "affected_pages": ["/guide/one"]},
        "medium",
        context(1, 75),
        search_facing=False,
    )
    assert reason == "1 of 75 guide pages checked is affected."
