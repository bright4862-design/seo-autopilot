from app.repair_integration import (
    REPAIR_CONTRACT_VERSION,
    build_shadow_repair_contract,
)


def _page(path: str, *, family: str = "product_page", indexable: bool = True, important: bool = False):
    return {
        "url": f"https://example.com{path}",
        "status_code": 200,
        "content_type": "text/html",
        "page_template_family": family,
        "indexable": indexable,
        "is_important_business_page": important,
    }


def _fix(fix_id: str, rule: str, priority: str, affected, *, family: str = "product_page", **extra):
    return {
        "id": fix_id,
        "fix_id": fix_id,
        "rule": rule,
        "category": extra.pop("category", "meta_description"),
        "priority": priority,
        "affected_pages": [f"https://example.com{path}" for path in affected],
        "page_template_family": family,
        "confidence_score": extra.pop("confidence_score", 92),
        **extra,
    }


def test_shadow_contract_is_additive_and_preserves_current_order():
    pages = [_page("/products/a"), _page("/products/b")]
    fixes = [
        _fix("wide", "missing_meta_description", "medium", ["/products/a", "/products/b"]),
        _fix("urgent", "canonical_missing", "critical", ["/products/a"], category="canonical"),
    ]

    result = build_shadow_repair_contract(fixes, pages)

    assert result["version"] == REPAIR_CONTRACT_VERSION
    assert [fix["id"] for fix in result["fixes"]] == ["wide", "urgent"]
    assert [fix["id"] for fix in result["proposed_fixes"]][0] == "urgent"
    assert result["priority_divergence"]["order_changed"] is True
    assert fixes[0].get("action_priority") is None
    assert result["fixes"][0]["priority"] == "medium"
    assert result["fixes"][0]["base_severity"] == "medium"
    assert result["fixes"][0]["repair_contract_version"] == REPAIR_CONTRACT_VERSION


def test_opportunity_stays_below_confirmed_problem_even_with_more_pages():
    pages = [
        _page(f"/products/{index}", important=(index == 1))
        for index in range(1, 16)
    ]
    opportunity = _fix(
        "opportunity",
        "potential_topic_overlap",
        "high",
        [f"/products/{index}" for index in range(1, 16)],
        evidence_class="opportunity",
    )
    confirmed = _fix(
        "confirmed",
        "missing_meta_description",
        "medium",
        ["/products/1"],
        evidence_class="confirmed_problem",
    )

    result = build_shadow_repair_contract([opportunity, confirmed], pages)
    proposed = result["proposed_fixes"]

    assert proposed[0]["id"] == "confirmed"
    assert proposed[0]["action_priority"] == "important"
    assert proposed[1]["id"] == "opportunity"
    assert proposed[1]["action_priority"] == "review"


def test_shadow_contract_does_not_infer_stable_repair_identity_from_family_alone():
    pages = [_page("/products/a"), _page("/products/b")]
    fix = _fix(
        "family-only",
        "missing_meta_description",
        "high",
        ["/products/a", "/products/b"],
        recommended_value="Add unique descriptions in the CMS.",
    )

    result = build_shadow_repair_contract([fix], pages)
    annotated = result["fixes"][0]

    assert annotated["repair_identity_stable"] is False
    assert annotated["repair_identity_state"] == "provisional"
    assert annotated["priority_context"]["shared_repair_confirmed"] is False


def test_explicit_surface_and_remediation_create_stable_identity_and_repair_leverage():
    pages = [_page("/products/a"), _page("/products/b")]
    fix = _fix(
        "shared",
        "missing_meta_description",
        "high",
        ["/products/a", "/products/b"],
        repair_surface="product_template",
        remediation_family="metadata_template_output",
        shared_repair_confirmed=True,
    )

    result = build_shadow_repair_contract([fix], pages)
    annotated = result["fixes"][0]

    assert annotated["repair_identity_stable"] is True
    assert annotated["repair_identity"]["repair_surface"] == "product_template"
    assert annotated["priority_context"]["shared_repair_confirmed"] is True
