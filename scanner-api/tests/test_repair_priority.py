from app.repair_priority import annotate_repair_priorities, annotate_repair_priority


def page(url, *, family="product_page", indexable=True, important=False):
    return {
        "url": url,
        "status_code": 200,
        "content_type": "text/html",
        "page_template_family": family,
        "indexable": indexable,
        "is_important_business_page": important,
    }


def test_severity_and_action_priority_are_separate():
    fix = {
        "rule": "missing_meta_description",
        "category": "meta_description",
        "priority": "medium",
        "affected_pages": ["/products/a", "/products/b"],
        "page_template_family": "product_page",
        "confidence_score": 95,
    }
    result = annotate_repair_priority(
        fix,
        [page("/products/a"), page("/products/b")],
    )
    assert result["base_severity"] == "medium"
    assert result["action_priority"] == "important"
    assert result["priority"] == "medium"


def test_search_facing_issue_on_non_indexable_pages_is_demoted_without_rewriting_severity():
    fix = {
        "rule": "missing_meta_description",
        "category": "meta_description",
        "priority": "high",
        "affected_pages": [f"/archive/{i}" for i in range(5)],
        "page_template_family": "archive",
    }
    pages = [page(f"/archive/{i}", family="archive", indexable=False) for i in range(5)]
    result = annotate_repair_priority(fix, pages)
    assert result["base_severity"] == "high"
    assert result["action_priority"] == "important"
    assert result["priority_context"]["non_indexable_affected"] == 5
    assert "lower priority" in result["priority_reason"].lower()


def test_sample_qualified_coverage_uses_checked_family_denominator():
    pages = [page(f"/products/{i}") for i in range(10)]
    fix = {
        "rule": "canonical_missing",
        "category": "canonical",
        "priority": "critical",
        "affected_pages": [f"/products/{i}" for i in range(8)],
        "page_template_family": "product_page",
    }
    result = annotate_repair_priority(fix, pages)
    context = result["priority_context"]
    assert context["checked_eligible"] == 10
    assert context["affected_checked"] == 8
    assert context["checked_coverage"] == 0.8
    assert context["indexable_checked_eligible"] == 10
    assert context["searchable_coverage"] == 0.8
    assert "checked" in result["priority_reason"].lower()


def test_unknown_denominator_never_claims_whole_site_coverage():
    fix = {
        "rule": "broken_page",
        "category": "404_error",
        "priority": "high",
        "affected_pages": ["/a", "/b", "/c"],
        "page_template_family": "mixed",
    }
    result = annotate_repair_priority(
        fix,
        [page("/a", family="standard"), page("/b", family="product_page")],
    )
    assert result["priority_context"]["checked_eligible"] is None
    assert result["priority_context"]["coverage_scope"] == "checked_sample"
    assert "checked pages" in result["priority_reason"].lower()


def test_page_family_does_not_confirm_shared_repair_leverage():
    fix = {
        "rule": "missing_h1",
        "category": "thin_content",
        "priority": "medium",
        "affected_pages": ["/products/a", "/products/b", "/products/c"],
        "page_template_family": "product_page",
        "recommended_value": "Add one H1 to each affected page.",
    }
    result = annotate_repair_priority(
        fix,
        [page("/products/a"), page("/products/b"), page("/products/c")],
    )
    assert result["repair_leverage_confirmed"] is False
    assert result["priority_context"]["shared_repair_confirmed"] is False
    assert "one shared change" not in result["priority_reason"].lower()


def test_explicit_shared_repair_evidence_can_add_leverage_reason_when_coverage_is_unknown():
    fix = {
        "rule": "internal_link_redirect",
        "category": "internal_link",
        "priority": "high",
        "affected_pages": ["/a", "/b", "/c"],
        "page_template_family": "mixed",
        "shared_repair_confirmed": True,
        "repair_surface": "shared_navigation",
    }
    result = annotate_repair_priority(
        fix,
        [page("/a", family="standard"), page("/b", family="standard"), page("/c", family="standard")],
    )
    assert result["repair_leverage_confirmed"] is True
    assert "one shared change" in result["priority_reason"].lower()


def test_important_page_distribution_breaks_ties_without_changing_severity_band():
    important_fix = {
        "id": "important",
        "rule": "missing_meta_description",
        "category": "meta_description",
        "priority": "medium",
        "affected_pages": ["/products/a"],
        "page_template_family": "product_page",
        "confidence_score": 90,
    }
    ordinary_fix = {
        "id": "ordinary",
        "rule": "missing_meta_description",
        "category": "meta_description",
        "priority": "medium",
        "affected_pages": ["/about/team"],
        "page_template_family": "standard",
        "confidence_score": 90,
    }
    pages = [
        page("/products/a", family="product_page", important=True),
        page("/about/team", family="standard", important=False),
    ]
    ranked = annotate_repair_priorities([ordinary_fix, important_fix], pages)
    assert ranked[0]["id"] == "important"
    assert ranked[0]["action_priority"] == "important"
    assert ranked[1]["action_priority"] == "important"


def test_opportunity_never_jumps_above_confirmed_problem_from_volume_alone():
    opportunity = {
        "id": "opportunity",
        "rule": "potential_topic_overlap",
        "category": "duplicate_content",
        "priority": "high",
        "evidence_class": "opportunity",
        "affected_pages": [f"/guides/{i}" for i in range(20)],
        "page_template_family": "guide_article",
    }
    confirmed = {
        "id": "confirmed",
        "rule": "canonical_missing",
        "category": "canonical",
        "priority": "critical",
        "affected_pages": ["/"],
        "page_template_family": "homepage",
    }
    pages = [page("/", family="homepage", important=True)] + [
        page(f"/guides/{i}", family="guide_article") for i in range(20)
    ]
    ranked = annotate_repair_priorities([opportunity, confirmed], pages)
    assert ranked[0]["id"] == "confirmed"
    assert ranked[0]["action_priority"] == "fix_first"
    assert ranked[1]["action_priority"] == "review"
