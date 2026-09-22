from copy import deepcopy

from app.nextgen_browser_performance_coverage import summarize_critical_parity_coverage


def _sample(*urls):
    return {
        "version": "nextgen_performance_sample_v1",
        "selected_pages": len(urls),
        "pages": [
            {
                "url": url,
                "template_family": "product_page",
                "high_value_weight": 1.0,
                "selection_reason": "template_representative",
            }
            for url in urls
        ],
    }


def _parity(url, state="matched"):
    return {
        "version": "nextgen_critical_content_parity_v1",
        "url": url,
        "rendered_url": url if state != "not_verified" else None,
        "state": state,
        "reason": "paired_render_evidence" if state != "not_verified" else "renderer_failed",
        "material_delta": {"matched": False, "material_delta": True, "not_verified": None}[state],
        "verified_fields": ["title"] if state != "not_verified" else [],
        "changed_fields": ["title"] if state == "material_delta" else [],
        "fields": {},
    }


def test_coverage_reports_complete_paired_population_and_material_deltas():
    sample = _sample("https://E.TEST/a#x", "https://e.test/b")
    coverage = summarize_critical_parity_coverage(
        sample,
        [_parity("https://e.test/a", "matched"), _parity("https://e.test/b", "material_delta")],
    )
    assert coverage["state"] == "complete"
    assert coverage["selected_pages"] == 2
    assert coverage["completed_pages"] == 2
    assert coverage["failed_pages"] == 0
    assert coverage["unassessed_pages"] == 0
    assert coverage["material_delta_pages"] == 1
    assert coverage["completion_ratio"] == 1.0
    assert coverage["material_delta_urls"] == ["https://e.test/b"]


def test_coverage_keeps_failed_and_unassessed_pages_distinct():
    coverage = summarize_critical_parity_coverage(
        _sample("https://e.test/a", "https://e.test/b", "https://e.test/c"),
        [_parity("https://e.test/a"), _parity("https://e.test/b", "not_verified")],
    )
    assert coverage["state"] == "partial"
    assert coverage["completed_urls"] == ["https://e.test/a"]
    assert coverage["failed_urls"] == ["https://e.test/b"]
    assert coverage["unassessed_urls"] == ["https://e.test/c"]
    assert coverage["completion_ratio"] == 1 / 3


def test_empty_selected_population_is_not_claimed_complete():
    coverage = summarize_critical_parity_coverage(_sample(), [])
    assert coverage["state"] == "not_applicable"
    assert coverage["reason"] == "no_selected_pages"
    assert coverage["completion_ratio"] is None


def test_foreign_parity_result_fails_coverage_closed():
    coverage = summarize_critical_parity_coverage(
        _sample("https://e.test/a"),
        [_parity("https://other.test/a")],
    )
    assert coverage["state"] == "not_verified"
    assert coverage["reason"] == "parity_result_binding_invalid"
    assert coverage["completed_pages"] is None
    assert coverage["details"]["foreign_result_urls"] == ["https://other.test/a"]


def test_duplicate_parity_result_for_same_selected_page_fails_closed():
    row = _parity("https://e.test/a")
    coverage = summarize_critical_parity_coverage(_sample("https://e.test/a"), [row, deepcopy(row)])
    assert coverage["state"] == "not_verified"
    assert coverage["details"]["duplicate_result_urls"] == ["https://e.test/a"]


def test_forged_completed_result_without_matching_rendered_identity_fails_closed():
    row = _parity("https://e.test/a")
    row["rendered_url"] = "https://e.test/b"
    coverage = summarize_critical_parity_coverage(_sample("https://e.test/a"), [row])
    assert coverage["state"] == "not_verified"
    assert coverage["details"]["malformed_result_indexes"] == [0]


def test_forged_material_delta_flag_fails_closed():
    row = _parity("https://e.test/a", "matched")
    row["material_delta"] = True
    coverage = summarize_critical_parity_coverage(_sample("https://e.test/a"), [row])
    assert coverage["state"] == "not_verified"
    assert coverage["details"]["malformed_result_indexes"] == [0]


def test_sample_requires_absolute_http_identity():
    coverage = summarize_critical_parity_coverage(_sample("/relative"), [])
    assert coverage["state"] == "not_verified"
    assert coverage["reason"] == "sample_page_identity_invalid"


def test_input_evidence_is_not_mutated():
    sample = _sample("https://e.test/a")
    results = [_parity("https://e.test/a")]
    before_sample = deepcopy(sample)
    before_results = deepcopy(results)
    summarize_critical_parity_coverage(sample, results)
    assert sample == before_sample
    assert results == before_results
