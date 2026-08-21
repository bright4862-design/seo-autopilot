from app.repair_priority_calibration import annotate_calibrated_repair_priority
from app.repair_shadow_calibration import build_calibrated_shadow_review_analysis


def page(path, family, *, indexable=True):
    return {
        "url": f"https://example.com{path}",
        "final_url": f"https://example.com{path}",
        "status_code": 200,
        "content_type": "text/html",
        "page_template_family": family,
        "indexable": indexable,
    }


def finding(
    *,
    fix_id,
    family,
    affected,
    severity="medium",
    evidence_class="confirmed_problem",
    rule="architecture_priority_fixture",
):
    return {
        "id": fix_id,
        "fix_id": fix_id,
        "rule": rule,
        "category": "canonical",
        "priority": severity,
        "technical_severity": severity,
        "evidence_class": evidence_class,
        "affected_pages": affected,
        "page_template_family": family,
        "confidence_score": 90,
    }


def test_funbooker_100_activity_leaves_do_not_outvote_one_collection_at_equal_severity():
    leaves = [page(f"/fr/annonce/{i}/voir", "activity_detail") for i in range(100)]
    hub = page("/fr/category/activites", "collection_page")
    leaf_fix = finding(
        fix_id="leaves",
        family="activity_detail",
        affected=[f"/fr/annonce/{i}/voir" for i in range(100)],
    )
    hub_fix = finding(
        fix_id="hub",
        family="collection_page",
        affected=["/fr/category/activites"],
    )

    analysis = build_calibrated_shadow_review_analysis(
        {"cleaned_fixes": [leaf_fix, hub_fix]},
        leaves + [hub],
    )

    assert analysis["proposed_fixes"][0]["id"] == "hub"
    leaf_result = next(item for item in analysis["fixes"] if item["id"] == "leaves")
    hub_result = next(item for item in analysis["fixes"] if item["id"] == "hub")
    assert leaf_result["priority_context"]["architecture_role_counts"]["commercial_leaf"] == 100
    assert hub_result["priority_context"]["architecture_role_counts"]["structural"] == 1
    assert hub_result["action_priority_score"] > leaf_result["action_priority_score"]


def test_critical_leaf_still_beats_low_severity_structural_issue():
    leaf = page("/product/sku-1", "product_page")
    hub = page("/category/widgets", "collection_page")
    critical_leaf = finding(
        fix_id="critical_leaf",
        family="product_page",
        affected=["/product/sku-1"],
        severity="critical",
    )
    low_hub = finding(
        fix_id="low_hub",
        family="collection_page",
        affected=["/category/widgets"],
        severity="low",
    )

    analysis = build_calibrated_shadow_review_analysis(
        {"cleaned_fixes": [low_hub, critical_leaf]},
        [leaf, hub],
    )

    assert analysis["proposed_fixes"][0]["id"] == "critical_leaf"
    assert analysis["proposed_fixes"][0]["action_priority"] == "fix_first"


def test_finance_calculator_beats_many_guides_at_equal_severity():
    calc = page("/mortgage/calculator", "calculator")
    guides = [page(f"/guides/{i}", "guide_article") for i in range(40)]
    calc_fix = finding(
        fix_id="calc",
        family="calculator",
        affected=["/mortgage/calculator"],
    )
    guide_fix = finding(
        fix_id="guides",
        family="guide_article",
        affected=[f"/guides/{i}" for i in range(40)],
    )

    analysis = build_calibrated_shadow_review_analysis(
        {"cleaned_fixes": [guide_fix, calc_fix]},
        [calc] + guides,
    )

    assert analysis["proposed_fixes"][0]["id"] == "calc"
    assert analysis["proposed_fixes"][0]["priority_context"]["architecture_role_counts"]["business_critical"] == 1


def test_ecommerce_collection_beats_repeated_products_at_equal_severity():
    collection = page("/collections/shoes", "collection_page")
    products = [page(f"/products/{i}", "product_page") for i in range(60)]
    collection_fix = finding(
        fix_id="collection",
        family="collection_page",
        affected=["/collections/shoes"],
    )
    product_fix = finding(
        fix_id="products",
        family="product_page",
        affected=[f"/products/{i}" for i in range(60)],
    )

    collection_result = annotate_calibrated_repair_priority(collection_fix, [collection] + products)
    product_result = annotate_calibrated_repair_priority(product_fix, [collection] + products)

    assert collection_result["action_priority_score"] > product_result["action_priority_score"]


def test_saas_pricing_surface_beats_articles_at_equal_severity():
    pricing = page("/pricing", "pricing_page")
    articles = [page(f"/blog/{i}", "guide_article") for i in range(30)]
    pricing_fix = finding(
        fix_id="pricing",
        family="pricing_page",
        affected=["/pricing"],
    )
    article_fix = finding(
        fix_id="articles",
        family="guide_article",
        affected=[f"/blog/{i}" for i in range(30)],
    )

    pricing_result = annotate_calibrated_repair_priority(pricing_fix, [pricing] + articles)
    article_result = annotate_calibrated_repair_priority(article_fix, [pricing] + articles)

    assert pricing_result["priority_context"]["architecture_role_counts"]["business_critical"] == 1
    assert pricing_result["action_priority_score"] > article_result["action_priority_score"]


def test_repeated_leaf_bonus_saturates_instead_of_scaling_linearly():
    products = [page(f"/products/{i}", "product_page") for i in range(100)]
    one = finding(fix_id="one", family="product_page", affected=["/products/0"])
    hundred = finding(
        fix_id="hundred",
        family="product_page",
        affected=[f"/products/{i}" for i in range(100)],
    )

    one_result = annotate_calibrated_repair_priority(one, products)
    hundred_result = annotate_calibrated_repair_priority(hundred, products)

    assert one_result["priority_context"]["architecture_role_bonus"] < hundred_result["priority_context"]["architecture_role_bonus"]
    assert hundred_result["priority_context"]["architecture_role_bonus"] <= 8


def test_page_family_similarity_does_not_create_shared_repair_evidence():
    products = [page(f"/products/{i}", "product_page") for i in range(3)]
    base = finding(
        fix_id="base",
        family="product_page",
        affected=[f"/products/{i}" for i in range(3)],
    )
    shared = {**base, "fix_id": "shared", "id": "shared", "shared_repair_confirmed": True}

    base_result = annotate_calibrated_repair_priority(base, products)
    shared_result = annotate_calibrated_repair_priority(shared, products)

    assert base_result["repair_leverage_confirmed"] is False
    assert shared_result["action_priority_score"] == base_result["action_priority_score"] + 15


def test_mixed_structural_and_leaf_evidence_gets_role_aware_sample_scoped_reason():
    pages = [
        page("/fr/category/activites", "collection_page"),
        page("/fr/annonce/a/voir", "activity_detail"),
        page("/fr/annonce/b/voir", "activity_detail"),
    ]
    mixed = finding(
        fix_id="mixed",
        family="mixed",
        affected=[
            "/fr/category/activites",
            "/fr/annonce/a/voir",
            "/fr/annonce/b/voir",
        ],
    )

    result = annotate_calibrated_repair_priority(mixed, pages)

    assert result["priority_context"]["checked_eligible"] is None
    assert result["priority_context"]["architecture_role_counts"]["structural"] == 1
    assert result["priority_context"]["architecture_role_counts"]["commercial_leaf"] == 2
    assert "structural page" in result["priority_reason"].lower()
    assert "commercial leaf" in result["priority_reason"].lower()
    assert "site" not in result["priority_reason"].lower()


def test_architecture_context_is_versioned_and_sample_scoped():
    hub = page("/category/widgets", "collection_page")
    hub_fix = finding(
        fix_id="hub",
        family="collection_page",
        affected=["/category/widgets"],
    )

    result = annotate_calibrated_repair_priority(hub_fix, [hub])
    context = result["priority_context"]

    assert context["architecture_priority_version"] == "repair_architecture_priority_v1_role_coverage"
    assert context["repair_reach"] == "structural"
    assert context["coverage_scope"] == "checked_sample"
