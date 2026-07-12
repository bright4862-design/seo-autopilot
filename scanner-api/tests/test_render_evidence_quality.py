from copy import deepcopy

from app.render_evidence_quality import (
    INSUFFICIENT_RENDER_EVIDENCE_STATE,
    apply_render_evidence_quality,
    assess_render_evidence_coverage,
)


def _result(*, evaluated, crawled, found=None, state="raw_html_sufficient", suspected=0):
    return {
        "success": True,
        "pages_crawled": crawled,
        "pages_found": crawled if found is None else found,
        "health_score": 81,
        "findings": [{"rule": "example", "priority": "low"}],
        "crawl_warnings": [],
        "render_evidence": {
            "version": "render_evidence_v1",
            "pages_evaluated": evaluated,
            "client_rendering_suspected_pages": suspected,
            "evidence_state": state,
            "rendering_mode": "raw_html_first",
        },
        "scan_summary": {},
        "technical_audit_summary": {},
    }


def test_zero_evaluable_pages_are_not_raw_html_sufficient():
    result = apply_render_evidence_quality(_result(evaluated=0, crawled=2))

    assert result["render_evidence"]["evidence_state"] == INSUFFICIENT_RENDER_EVIDENCE_STATE
    assert result["render_evidence"]["pre_coverage_evidence_state"] == "raw_html_sufficient"
    assert result["render_evidence_quality"]["reason"] == "no_evaluable_html_pages"
    assert result["health_score"] == 81
    assert result["findings"] == [{"rule": "example", "priority": "low"}]
    assert len(result["crawl_warnings"]) == 1


def test_one_evaluable_page_is_insufficient_for_a_large_crawl():
    coverage = assess_render_evidence_coverage(
        {"pages_evaluated": 1},
        pages_crawled=22,
        pages_found=22,
    )

    assert coverage["sufficient"] is False
    assert coverage["reason"] == "too_few_evaluable_html_pages"
    assert coverage["evaluated_ratio"] == 0.0455


def test_one_page_site_can_produce_sufficient_negative_evidence():
    result = apply_render_evidence_quality(_result(evaluated=1, crawled=1))

    assert result["render_evidence"]["evidence_state"] == "raw_html_sufficient"
    assert result["render_evidence_quality"]["sufficient"] is True


def test_material_signal_is_preserved_even_when_coverage_is_limited():
    result = apply_render_evidence_quality(
        _result(
            evaluated=2,
            crawled=50,
            state="material_client_rendering_risk",
            suspected=2,
        )
    )

    assert result["render_evidence"]["evidence_state"] == "material_client_rendering_risk"
    assert result["render_evidence_quality"]["sufficient"] is False
    assert "pre_coverage_evidence_state" not in result["render_evidence"]


def test_quality_pass_is_idempotent():
    first = apply_render_evidence_quality(_result(evaluated=0, crawled=10))
    snapshot = deepcopy(first)
    second = apply_render_evidence_quality(first)

    assert second == snapshot
    assert len(second["crawl_warnings"]) == 1
