from copy import deepcopy

from app.nextgen_browser_performance import select_representative_performance_pages
from app.nextgen_browser_performance_sample_binding import (
    validate_representative_sample_binding,
)


def _page(url, family, *, weight=0.0, **extra):
    return {
        "url": url,
        "status_code": 200,
        "page_evidence_class": "usable_html",
        "template_family": family,
        "high_value_score": weight,
        **extra,
    }


def _bound(pages, *, max_pages=8):
    sample = select_representative_performance_pages(pages, max_pages=max_pages)
    return sample, validate_representative_sample_binding(pages, sample)


def test_binding_accepts_exact_deterministic_sample():
    pages = [
        _page("https://e.test/", "homepage", weight=1.0),
        _page("https://e.test/p/1", "product_page", weight=0.9),
        _page("https://e.test/blog/a", "article", weight=0.2),
    ]
    sample, binding = _bound(pages, max_pages=2)
    assert binding["valid"] is True
    assert binding["reasons"] == []
    assert binding["expected_selected_urls"] == [row["url"] for row in sample["pages"]]


def test_binding_rejects_forged_selected_page_with_plausible_counts():
    pages = [
        _page("https://e.test/product/high", "product_page", weight=1.0),
        _page("https://e.test/product/low", "product_page", weight=0.1),
    ]
    sample = select_representative_performance_pages(pages, max_pages=1)
    forged = deepcopy(sample)
    forged["pages"][0]["url"] = "https://e.test/product/low"
    binding = validate_representative_sample_binding(pages, forged)
    assert binding["valid"] is False
    assert "pages_mismatch" in binding["reasons"]


def test_binding_rejects_reordered_selection_even_when_population_is_same():
    pages = [
        _page("https://e.test/", "homepage", weight=1.0),
        _page("https://e.test/service", "service_page", weight=0.8),
    ]
    sample = select_representative_performance_pages(pages, max_pages=2)
    forged = deepcopy(sample)
    forged["pages"] = list(reversed(forged["pages"]))
    binding = validate_representative_sample_binding(pages, forged)
    assert binding["valid"] is False
    assert "pages_mismatch" in binding["reasons"]


def test_binding_detects_authoritative_candidate_population_drift():
    original = [
        _page("https://e.test/", "homepage", weight=1.0),
        _page("https://e.test/a", "article", weight=0.4),
    ]
    sample = select_representative_performance_pages(original, max_pages=2)
    changed = original + [_page("https://e.test/product", "product_page", weight=0.9)]
    binding = validate_representative_sample_binding(changed, sample)
    assert binding["valid"] is False
    assert any(reason.endswith("_mismatch") for reason in binding["reasons"])


def test_binding_preserves_final_url_deduplication_winner():
    pages = [
        _page(
            "https://e.test/entry-a",
            "product_page",
            weight=0.1,
            final_url="https://e.test/product",
        ),
        _page(
            "https://e.test/entry-b",
            "product_page",
            weight=0.9,
            final_url="https://e.test/product",
        ),
    ]
    sample, binding = _bound(pages, max_pages=8)
    assert binding["valid"] is True
    assert sample["eligible_pages"] == 1
    assert sample["duplicate_page_observations_dropped"] == 1
    assert binding["expected_selected_urls"] == ["https://e.test/product"]


def test_binding_covers_hard_cap_requests_without_expanding_execution_entitlement():
    pages = [
        _page(f"https://e.test/p/{index}", f"family-{index}", weight=index / 100)
        for index in range(20)
    ]
    sample, binding = _bound(pages, max_pages=999)
    assert binding["valid"] is True
    assert sample["requested_max_pages"] == 999
    assert sample["max_pages"] == 12
    assert sample["selected_pages"] == 12


def test_binding_fails_closed_when_selector_outputs_non_absolute_identity():
    pages = [_page("/relative", "homepage", weight=1.0)]
    sample = select_representative_performance_pages(pages, max_pages=1)
    binding = validate_representative_sample_binding(pages, sample)
    assert binding["valid"] is False
    assert binding["reasons"] == ["selected_identity_not_absolute_http"]


def test_binding_rejects_invalid_requested_limit_without_coercing_bool():
    pages = [_page("https://e.test/", "homepage", weight=1.0)]
    sample = select_representative_performance_pages(pages, max_pages=1)
    sample["requested_max_pages"] = True
    binding = validate_representative_sample_binding(pages, sample)
    assert binding["valid"] is False
    assert binding["reasons"] == ["requested_max_pages_invalid"]


def test_binding_does_not_mutate_pages_or_sample():
    pages = [
        _page("https://e.test/", "homepage", weight=1.0),
        _page("https://e.test/a", "article", weight=0.2),
    ]
    sample = select_representative_performance_pages(pages, max_pages=2)
    before_pages = deepcopy(pages)
    before_sample = deepcopy(sample)
    validate_representative_sample_binding(pages, sample)
    assert pages == before_pages
    assert sample == before_sample
