from copy import deepcopy

from app.nextgen_browser_performance_parity_hardening import (
    BOUND_PARITY_COVERAGE_VERSION,
    RESOLVED_CRITICAL_PARITY_VERSION,
    compare_critical_content_parity_resolved,
    summarize_resolved_critical_parity_coverage,
    validate_resolved_critical_parity_contract,
)


def _sample(*urls):
    count = len(urls)
    return {
        "version": "nextgen_performance_sample_v1",
        "requested_max_pages": count,
        "max_pages": count,
        "hard_cap": 12,
        "eligible_page_observations": count,
        "duplicate_page_observations_dropped": 0,
        "eligible_pages": count,
        "template_families": 1 if count else 0,
        "selected_pages": count,
        "template_coverage_complete": True,
        "omitted_template_families": [],
        "pages": [
            {
                "url": url,
                "template_family": "product_page",
                "high_value_weight": 1.0,
                "selection_reason": (
                    "template_representative" if index == 0 else "high_value_fill"
                ),
            }
            for index, url in enumerate(urls)
        ],
    }


def _matched(url):
    return compare_critical_content_parity_resolved(
        {"url": url, "title": "Same"},
        {"url": url, "title": "Same"},
    )


def test_relative_canonical_and_absolute_rendered_canonical_are_equivalent():
    parity = compare_critical_content_parity_resolved(
        {"url": "https://e.test/products/a", "canonical": "/products/a#raw"},
        {"url": "https://e.test/products/a", "canonical": "https://E.TEST/products/a"},
    )
    assert parity["version"] == RESOLVED_CRITICAL_PARITY_VERSION
    assert parity["state"] == "matched"
    assert parity["fields"]["canonical"]["state"] == "same"
    assert parity["fields"]["canonical"]["raw"] == "https://e.test/products/a"


def test_protocol_relative_canonical_uses_document_scheme_and_drops_fragment():
    parity = compare_critical_content_parity_resolved(
        {"url": "https://e.test/p", "canonical": "//E.TEST/p#hero"},
        {"url": "https://e.test/p", "canonical": "https://e.test/p"},
    )
    assert parity["state"] == "matched"
    assert parity["fields"]["canonical"]["state"] == "same"


def test_path_relative_canonical_that_resolves_elsewhere_remains_a_material_delta():
    parity = compare_critical_content_parity_resolved(
        {"url": "https://e.test/catalog/item", "canonical": "../canonical"},
        {"url": "https://e.test/catalog/item", "canonical": "/different"},
    )
    assert parity["state"] == "material_delta"
    assert parity["fields"]["canonical"]["raw"] == "https://e.test/canonical"
    assert parity["fields"]["canonical"]["rendered"] == "https://e.test/different"
    assert "canonical" in parity["changed_fields"]


def test_resolved_parity_does_not_mutate_raw_or_rendered_inputs():
    raw = {"url": "https://e.test/p", "canonical": "/p#x", "title": "Same"}
    rendered = {"url": "https://e.test/p", "canonical": "https://e.test/p", "title": "Same"}
    before_raw, before_rendered = deepcopy(raw), deepcopy(rendered)
    compare_critical_content_parity_resolved(raw, rendered)
    assert raw == before_raw
    assert rendered == before_rendered


def test_resolved_parity_validator_rejects_tampered_resolution_metadata():
    parity = _matched("https://e.test/a")
    parity["canonical_resolution_version"] = "made_up"
    validation = validate_resolved_critical_parity_contract(parity)
    assert validation["valid"] is False
    assert "canonical_resolution_version_mismatch" in validation["reasons"]


def test_contract_bound_coverage_counts_valid_completed_and_material_delta_rows():
    first = _matched("https://e.test/a")
    second = compare_critical_content_parity_resolved(
        {"url": "https://e.test/b", "canonical": "/b"},
        {"url": "https://e.test/b", "canonical": "/other"},
    )
    coverage = summarize_resolved_critical_parity_coverage(
        _sample("https://e.test/a", "https://e.test/b"),
        [first, second],
    )
    assert coverage["version"] == BOUND_PARITY_COVERAGE_VERSION
    assert coverage["state"] == "complete"
    assert coverage["completed_pages"] == 2
    assert coverage["material_delta_pages"] == 1
    assert coverage["material_delta_urls"] == ["https://e.test/b"]


def test_contract_bound_coverage_keeps_failed_and_unassessed_distinct():
    failed = compare_critical_content_parity_resolved(
        {"url": "https://e.test/b", "title": "Raw"},
        None,
        render_state="provider_error",
        render_reason="renderer_failed",
    )
    coverage = summarize_resolved_critical_parity_coverage(
        _sample("https://e.test/a", "https://e.test/b", "https://e.test/c"),
        [_matched("https://e.test/a"), failed],
    )
    assert coverage["state"] == "partial"
    assert coverage["completed_urls"] == ["https://e.test/a"]
    assert coverage["failed_urls"] == ["https://e.test/b"]
    assert coverage["unassessed_urls"] == ["https://e.test/c"]


def test_contract_bound_coverage_rejects_structurally_forged_completed_parity():
    forged = _matched("https://e.test/a")
    forged["verified_fields"] = []
    coverage = summarize_resolved_critical_parity_coverage(
        _sample("https://e.test/a"),
        [forged],
    )
    assert coverage["state"] == "not_verified"
    assert coverage["reason"] == "parity_contract_invalid"
    assert coverage["completed_pages"] is None
    assert coverage["details"]["malformed_results"][0]["index"] == 0


def test_contract_bound_coverage_rejects_invalid_sample_contract_before_counting():
    sample = _sample("https://e.test/a")
    sample.pop("hard_cap")
    coverage = summarize_resolved_critical_parity_coverage(
        sample,
        [_matched("https://e.test/a")],
    )
    assert coverage["state"] == "not_verified"
    assert coverage["reason"] == "sample_contract_invalid"
    assert coverage["completed_pages"] is None


def test_contract_bound_coverage_preserves_foreign_url_fail_closed_binding():
    coverage = summarize_resolved_critical_parity_coverage(
        _sample("https://e.test/a"),
        [_matched("https://other.test/a")],
    )
    assert coverage["state"] == "not_verified"
    assert coverage["reason"] == "parity_result_binding_invalid"
    assert coverage["details"]["foreign_result_urls"] == ["https://other.test/a"]
