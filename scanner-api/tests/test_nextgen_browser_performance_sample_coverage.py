from copy import deepcopy

from app.nextgen_browser_performance import select_representative_performance_pages
from app.nextgen_browser_performance_sample_coverage import (
    build_representative_sample_coverage,
    validate_representative_sample_coverage_contract,
)


def _page(url, family, *, weight=None, **extra):
    row = {
        "url": url,
        "status_code": 200,
        "page_evidence_class": "usable_html",
        "template_family": family,
        **extra,
    }
    if weight is not None:
        row["high_value_score"] = weight
    return row


def _coverage(pages, *, max_pages=8):
    sample = select_representative_performance_pages(pages, max_pages=max_pages)
    coverage = build_representative_sample_coverage(pages, sample)
    integrity = validate_representative_sample_coverage_contract(pages, sample, coverage)
    return sample, coverage, integrity


def test_reports_template_and_weight_coverage_separately():
    pages = [
        _page("https://e.test/", "homepage", weight=1.0),
        _page("https://e.test/product", "product_page", weight=0.9),
        _page("https://e.test/article", "article", weight=0.1),
    ]
    sample, coverage, integrity = _coverage(pages, max_pages=2)
    assert integrity["valid"] is True
    assert coverage["state"] == "verified"
    assert coverage["template_families"] == 3
    assert coverage["covered_template_families"] == 2
    assert coverage["template_family_coverage_ratio"] == 0.666667
    assert coverage["weighted_pages"] == 3
    assert coverage["selected_weighted_pages"] == 2
    assert coverage["weighted_page_coverage_ratio"] == 0.666667
    assert coverage["population_weight"] == 2.0
    assert coverage["selected_weight"] == 1.9
    assert coverage["weight_coverage_ratio"] == 0.95
    assert coverage["highest_unselected_weight"] == 0.1
    assert coverage["omitted_template_families"] == sample["omitted_template_families"]


def test_complete_sample_reports_full_template_and_weight_coverage():
    pages = [
        _page("https://e.test/", "homepage", weight=1.0),
        _page("https://e.test/product", "product_page", weight=0.8),
        _page("https://e.test/article", "article", weight=0.2),
    ]
    _, coverage, integrity = _coverage(pages, max_pages=3)
    assert integrity["valid"] is True
    assert coverage["template_family_coverage_ratio"] == 1.0
    assert coverage["weighted_page_coverage_ratio"] == 1.0
    assert coverage["weight_coverage_ratio"] == 1.0
    assert coverage["highest_unselected_weight"] is None
    assert coverage["unselected_weighted_families"] == []


def test_high_value_fill_is_reflected_after_template_representatives():
    pages = [
        _page("https://e.test/product/a", "product_page", weight=1.0),
        _page("https://e.test/product/b", "product_page", weight=0.8),
        _page("https://e.test/article", "article", weight=0.1),
    ]
    sample, coverage, _ = _coverage(pages, max_pages=3)
    assert [row["selection_reason"] for row in sample["pages"]].count("high_value_fill") == 1
    assert coverage["selected_weighted_pages"] == 3
    assert coverage["weight_coverage_ratio"] == 1.0


def test_role_based_sampler_weight_is_counted_without_customer_scoring():
    pages = [
        _page("https://e.test/revenue", "service_page", page_role="revenue"),
        _page("https://e.test/plain", "article"),
    ]
    _, coverage, _ = _coverage(pages, max_pages=1)
    assert coverage["weighted_pages"] == 1
    assert coverage["selected_weighted_pages"] == 1
    assert coverage["population_weight"] == 0.9
    assert coverage["selected_weight"] == 0.9


def test_zero_positive_weights_remain_verified_but_weight_ratio_is_not_applicable():
    pages = [
        _page("https://e.test/", "homepage"),
        _page("https://e.test/article", "article"),
    ]
    _, coverage, integrity = _coverage(pages, max_pages=1)
    assert integrity["valid"] is True
    assert coverage["state"] == "verified"
    assert coverage["weighted_pages"] == 0
    assert coverage["weighted_page_coverage_ratio"] is None
    assert coverage["population_weight"] == 0.0
    assert coverage["weight_coverage_ratio"] is None


def test_final_url_duplicates_count_once_using_sampler_winner_weight():
    pages = [
        _page("https://e.test/entry-a", "product_page", weight=0.1, final_url="https://e.test/product"),
        _page("https://e.test/entry-b", "product_page", weight=0.9, final_url="https://e.test/product"),
    ]
    _, coverage, integrity = _coverage(pages, max_pages=1)
    assert integrity["valid"] is True
    assert coverage["eligible_pages"] == 1
    assert coverage["weighted_pages"] == 1
    assert coverage["population_weight"] == 0.9
    assert coverage["selected_weight"] == 0.9


def test_forged_sample_fails_closed_without_coverage_numbers():
    pages = [_page("https://e.test/", "homepage", weight=1.0)]
    sample = select_representative_performance_pages(pages, max_pages=1)
    sample["pages"][0]["url"] = "https://e.test/forged"
    coverage = build_representative_sample_coverage(pages, sample)
    assert coverage["state"] == "not_verified"
    assert coverage["reason"] == "sample_binding_invalid"
    assert coverage["binding_valid"] is False
    assert "pages_mismatch" in coverage["binding_reasons"]
    assert coverage["eligible_pages"] is None
    assert coverage["template_family_coverage_ratio"] is None
    assert coverage["weight_coverage_ratio"] is None


def test_empty_eligible_population_is_not_verified_not_complete():
    pages = [_page("https://e.test/fail", "homepage", weight=1.0, fetch_error="timeout")]
    sample = select_representative_performance_pages(pages, max_pages=1)
    coverage = build_representative_sample_coverage(pages, sample)
    integrity = validate_representative_sample_coverage_contract(pages, sample, coverage)
    assert integrity["valid"] is True
    assert coverage["binding_valid"] is True
    assert coverage["state"] == "not_verified"
    assert coverage["reason"] == "eligible_sample_population_empty"
    assert coverage["eligible_pages"] is None


def test_integrity_rejects_source_population_drift():
    original = [
        _page("https://e.test/", "homepage", weight=1.0),
        _page("https://e.test/a", "article", weight=0.2),
    ]
    sample = select_representative_performance_pages(original, max_pages=2)
    coverage = build_representative_sample_coverage(original, sample)
    changed = original + [_page("https://e.test/product", "product_page", weight=0.8)]
    integrity = validate_representative_sample_coverage_contract(changed, sample, coverage)
    assert integrity["valid"] is False
    assert integrity["reasons"]


def test_integrity_rejects_tampered_coverage_ratio():
    pages = [
        _page("https://e.test/", "homepage", weight=1.0),
        _page("https://e.test/a", "article", weight=0.2),
    ]
    sample = select_representative_performance_pages(pages, max_pages=1)
    coverage = build_representative_sample_coverage(pages, sample)
    forged = deepcopy(coverage)
    forged["template_family_coverage_ratio"] = 1.0
    integrity = validate_representative_sample_coverage_contract(pages, sample, forged)
    assert integrity["valid"] is False
    assert integrity["reasons"] == ["template_family_coverage_ratio_mismatch"]


def test_truthful_fail_closed_artifact_is_integrity_valid():
    pages = [_page("https://e.test/", "homepage", weight=1.0)]
    sample = select_representative_performance_pages(pages, max_pages=1)
    sample["version"] = "foreign_sample_v9"
    coverage = build_representative_sample_coverage(pages, sample)
    integrity = validate_representative_sample_coverage_contract(pages, sample, coverage)
    assert coverage["state"] == "not_verified"
    assert integrity == {
        "version": "nextgen_performance_sample_coverage_integrity_v1",
        "contract": "nextgen_performance_sample_coverage_v1",
        "valid": True,
        "reasons": [],
    }


def test_extra_transport_metadata_is_non_authoritative():
    pages = [_page("https://e.test/", "homepage", weight=1.0)]
    sample = select_representative_performance_pages(pages, max_pages=1)
    coverage = build_representative_sample_coverage(pages, sample)
    transported = {**coverage, "trace_id": "non-authoritative"}
    integrity = validate_representative_sample_coverage_contract(pages, sample, transported)
    assert integrity["valid"] is True


def test_hard_cap_reports_incomplete_coverage_without_implying_execution_entitlement():
    pages = [
        _page(f"https://e.test/p/{index}", f"family-{index}", weight=1.0 - index / 100)
        for index in range(20)
    ]
    sample, coverage, integrity = _coverage(pages, max_pages=999)
    assert integrity["valid"] is True
    assert sample["selected_pages"] == 12
    assert coverage["eligible_pages"] == 20
    assert coverage["selected_pages"] == 12
    assert coverage["template_family_coverage_ratio"] == 0.6
    assert coverage["weighted_page_coverage_ratio"] == 0.6
    assert "execution_budget" not in coverage
    assert "execution_allowed" not in coverage


def test_builder_and_integrity_validator_do_not_mutate_inputs():
    pages = [
        _page("https://e.test/", "homepage", weight=1.0),
        _page("https://e.test/a", "article", weight=0.2),
    ]
    sample = select_representative_performance_pages(pages, max_pages=1)
    before_pages = deepcopy(pages)
    before_sample = deepcopy(sample)
    coverage = build_representative_sample_coverage(pages, sample)
    before_coverage = deepcopy(coverage)
    validate_representative_sample_coverage_contract(pages, sample, coverage)
    assert pages == before_pages
    assert sample == before_sample
    assert coverage == before_coverage
