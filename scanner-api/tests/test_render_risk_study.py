import pytest

from app.render_risk_study import (
    format_markdown,
    normalize_record,
    summarize_records,
)


def _record(
    index: int,
    stratum: str,
    *,
    detector_material: bool = False,
    manual_verdict: str | None = None,
) -> dict:
    if manual_verdict is None:
        manual_verdict = (
            "material_content_missing" if detector_material else "content_sufficient"
        )
    return {
        "site": f"site-{stratum}-{index}",
        "stratum": stratum,
        "render_evidence": {
            "pages_evaluated": 10,
            "client_rendering_suspected_pages": 3 if detector_material else 0,
            "evidence_state": (
                "material_client_rendering_risk"
                if detector_material
                else "raw_html_sufficient"
            ),
        },
        "manual_js_disabled_verdict": manual_verdict,
    }


def _study(
    *,
    smb_material: int = 0,
    saas_material: int = 0,
    ecommerce_material: int = 0,
) -> list[dict]:
    records = []
    for stratum, material_count in (
        ("smb_cms", smb_material),
        ("saas_js", saas_material),
        ("ecommerce_marketplace", ecommerce_material),
    ):
        records.extend(
            _record(index, stratum, detector_material=index < material_count)
            for index in range(10)
        )
    return records


def test_normalize_record_reads_nested_scan_evidence():
    result = normalize_record(_record(1, "saas_js", detector_material=True))

    assert result["successful_pages"] == 10
    assert result["suspected_pages"] == 3
    assert result["suspected_ratio"] == 0.3
    assert result["detector_material"] is True
    assert result["agreement"] is True
    assert result["false_positive"] is False
    assert result["false_negative"] is False


def test_normalize_record_rejects_invalid_counts_and_strata():
    with pytest.raises(ValueError, match="cannot exceed"):
        normalize_record({
            "site": "bad-counts",
            "stratum": "smb_cms",
            "successful_pages": 2,
            "suspected_pages": 3,
            "scanner_evidence_state": "material_client_rendering_risk",
        })

    with pytest.raises(ValueError, match="stratum"):
        normalize_record({
            "site": "bad-stratum",
            "stratum": "random",
            "successful_pages": 1,
            "suspected_pages": 0,
            "scanner_evidence_state": "raw_html_sufficient",
        })


def test_fewer_than_five_manual_reviews_keeps_detector_in_calibration():
    records = [
        _record(index, "smb_cms", manual_verdict="content_sufficient")
        for index in range(4)
    ]

    summary = summarize_records(records)

    assert summary["calibration"]["complete"] is False
    assert summary["decision"]["action"] == "validate_detector"


def test_false_negative_forces_detector_recalibration():
    records = [
        _record(index, "smb_cms", manual_verdict="content_sufficient")
        for index in range(4)
    ]
    records.append(
        _record(
            5,
            "saas_js",
            detector_material=False,
            manual_verdict="material_content_missing",
        )
    )

    summary = summarize_records(records)

    assert summary["calibration"]["complete"] is True
    assert summary["calibration"]["passed"] is False
    assert summary["calibration"]["false_negative_count"] == 1
    assert summary["decision"]["action"] == "recalibrate_detector"


def test_complete_stratified_study_builds_for_high_risk_strategic_segment():
    summary = summarize_records(_study(saas_material=3))

    assert summary["calibration"]["passed"] is True
    assert summary["measurement"]["complete"] is True
    assert summary["strata"]["saas_js"]["detector_material_incidence"] == 0.3
    assert summary["decision"]["action"] == "build_for_strategic_segment"


def test_complete_low_incidence_study_defers_renderer():
    summary = summarize_records(_study())

    assert summary["measurement"]["complete"] is True
    assert summary["overall"]["detector_material_incidence"] == 0.0
    assert summary["decision"]["action"] == "defer_renderer"


def test_middle_band_revisits_with_customer_evidence():
    summary = summarize_records(_study(saas_material=2))

    assert summary["strata"]["saas_js"]["detector_material_incidence"] == 0.2
    assert summary["decision"]["action"] == "revisit_with_customer_evidence"


def test_markdown_report_exposes_strata_and_decision():
    report = format_markdown(summarize_records(_study(saas_material=3)))

    assert "# Renderer-risk study" in report
    assert "saas_js" in report
    assert "30.0%" in report
    assert "build_for_strategic_segment" in report
