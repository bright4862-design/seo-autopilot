"""Priority stability and customer-snapshot contract regression.

Architecture importance must not be overturned by a small confidence shift
or by large numbers of repetitive pages when technical severity and action
band agree. All tests are synthetic/no customer records are embedded.
"""
from copy import deepcopy
import json

from app.repair_priority import ACTION_RANK, SEVERITY_RANK
from app.repair_priority_calibration import annotate_calibrated_repair_priority
from app.repair_contract_v2 import apply_canonical_repair_contract
from app.repair_persistence_shadow import validate_v2_persistence_candidate
from app.repair_shadow_calibration import sort_calibrated_repairs


def page(path, family, *, indexable=True):
    url = "https://example.com" + path
    return {"url": url, "final_url": url, "status_code": 200,
            "content_type": "text/html", "page_evidence_class": "usable_html",
            "page_template_family": family, "indexable": indexable}


def finding(identifier, family, urls, *, severity="medium", confidence=0, shared=False):
    return {
        "fix_id": identifier, "id": identifier, "rule": "canonical_missing",
        "category": "canonical", "priority": severity,
        "technical_severity": severity, "evidence_class": "confirmed_problem",
        "page_scope": "page" if len(urls) == 1 else "family",
        "affected_pages": urls, "page_template_family": family,
        "confidence_score": confidence,
        "shared_repair_confirmed": shared, "issue_title": identifier,
    }


def test_structural_outvotes_many_leaves_even_in_adverse_confidence_and_coverage():
    hub = page("/collections/widgets", "collection_page")
    leaves = [page(f"/products/{i}", "product_page") for i in range(120)]
    pages = [hub] + leaves
    structural = annotate_calibrated_repair_priority(
        finding("hub", "collection_page", [hub["url"]], confidence=0), pages)
    repeated = annotate_calibrated_repair_priority(
        finding("leaves", "product_page", [p["url"] for p in leaves],
                confidence=100, shared=True), pages)
    assert structural["base_severity"] == repeated["base_severity"] == "medium"
    assert structural["action_priority"] == repeated["action_priority"]
    assert structural["action_priority_score"] >= repeated["action_priority_score"] + 10


def test_calculator_outranks_large_support_cohort_with_high_confidence():
    calc = page("/mortgage/calculator", "calculator")
    support = [page(f"/guides/{i}", "guide_article") for i in range(130)]
    pages = [calc] + support
    important = annotate_calibrated_repair_priority(
        finding("calculator", "calculator", [calc["url"]], confidence=0), pages)
    ordinary = annotate_calibrated_repair_priority(
        finding("guides", "guide_article", [p["url"] for p in support],
                confidence=100, shared=True), pages)
    assert important["action_priority"] == ordinary["action_priority"]
    assert important["action_priority_score"] > ordinary["action_priority_score"]


def test_high_severity_leaf_still_beats_lower_severity_hub_in_same_action_band():
    hub = page("/collections/widgets", "collection_page")
    leaf = page("/products/one", "product_page")
    pages = [hub, leaf]
    high = annotate_calibrated_repair_priority(
        finding("high_leaf", "product_page", [leaf["url"]], severity="high"), pages)
    medium = annotate_calibrated_repair_priority(
        finding("medium_hub", "collection_page", [hub["url"]]), pages)
    assert high["action_priority"] == "fix_first"
    assert medium["action_priority"] == "important"
    assert high["action_priority_score"] > medium["action_priority_score"]


def test_within_same_action_band_technical_severity_dominates_any_role():
    hub = page("/category", "collection_page")
    leaf = page("/product", "product_page")
    pages = [hub, leaf]
    critical_hub = annotate_calibrated_repair_priority(
        finding("critical_hub", "collection_page", [hub["url"]],
                severity="critical", confidence=100), pages)
    high_leaf = annotate_calibrated_repair_priority(
        finding("high_leaf", "product_page", [leaf["url"]],
                severity="high", confidence=0), pages)
    # The bands coincide (both fix_first). Severity must still dominate.
    assert critical_hub["action_priority"] == high_leaf["action_priority"] == "fix_first"
    assert critical_hub["action_priority_score"] > high_leaf["action_priority_score"]


def test_contextual_addition_bounded_below_one_severity_step():
    p = page("/category", "collection_page")
    pages = [p] + [page(f"/products/{i}", "product_page") for i in range(130)]
    same = annotate_calibrated_repair_priority(
        finding("structural", "collection_page", [p["url"]], confidence=100), pages)
    base = ACTION_RANK["important"] * 1000 + SEVERITY_RANK["medium"] * 100
    assert 0 <= same["action_priority_score"] - base < 100
    assert same["priority_context"]["architecture_score_policy_version"] == (
        "architecture_score_policy_v2_role_first"
    )


def test_deterministic_ties_preserve_input_order():
    a = page("/collections/a", "collection_page")
    b = page("/collections/b", "collection_page")
    pages = [a, b]
    left = annotate_calibrated_repair_priority(
        finding("left", "collection_page", [a["url"]], confidence=90), pages)
    right = annotate_calibrated_repair_priority(
        finding("right", "collection_page", [b["url"]], confidence=90), pages)
    assert left["action_priority_score"] == right["action_priority_score"]
    assert [x["fix_id"] for x in sort_calibrated_repairs([right, left])] == ["right", "left"]


def test_full_canonical_snapshot_stays_customer_contract_valid_and_json_safe():
    pages = [
        page("/collections/category", "collection_page"),
        page("/products/sku", "product_page"),
    ]
    originals = [
        finding("hub", "collection_page", [pages[0]["url"]], confidence=95),
        finding("sku", "product_page", [pages[1]["url"]], confidence=95),
    ]
    review = {"cleaned_fixes": deepcopy(originals), "recommendations": deepcopy(originals)}
    before = deepcopy(review)
    result = apply_canonical_repair_contract(review, {"crawled_pages": pages})
    assert review == before  # source review remains untouched
    assert result["recommendations"] == originals
    assert result["repair_snapshot_contract_complete"] is True
    assert [x["canonical_action_rank"] for x in result["canonical_repairs"]] == [1, 2]
    assert result["canonical_action_fix_ids"] == [
        x["fix_id"] for x in result["canonical_repairs"]
    ]
    assert result["canonical_repairs"][0]["page_template_family"] == "collection_page"
    assert result["canonical_repairs"][0]["action_priority_score"] > result["canonical_repairs"][1]["action_priority_score"]
    assert validate_v2_persistence_candidate(result, result["canonical_repairs"])["eligible"] is True
    for item in result["canonical_repairs"]:
        assert item["base_severity"] in ("critical", "high", "medium", "low")
        assert item["action_priority"] in ("fix_first", "important", "improve", "review")
        assert item["repair_priority_model_version"] == result["repair_priority_model_version"]
        assert item["priority_context"]["architecture_role_counts"] is not None
        assert item["priority_context"]["architecture_score_policy_version"]
    json.dumps(result, allow_nan=False)


def test_unknown_denominator_and_untrusted_provenance_never_create_sitewide_claim():
    hub = page("/collection", "collection_page")
    hub["architecture_role_evidence"] = {
        "version": "architecture_role_evidence_v1",
        "claims": [{"producer": "fixlist_scanner_verified", "verified": True,
                    "source": "verified_promotional_surface", "role": "support",
                    "evidence_id": "fake"}],
    }
    result = annotate_calibrated_repair_priority(
        finding("test", "collection_page", [hub["url"]]), [hub])
    assert result["priority_context"]["architecture_role_counts"]["structural"] == 1
    assert result["priority_context"]["architecture_role_counts"]["support"] == 0
    assert "sitewide" not in result["priority_reason"].lower()
