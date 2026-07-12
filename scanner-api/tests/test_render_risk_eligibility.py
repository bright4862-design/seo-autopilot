from app.render_risk_collection import build_study_record
from app.render_risk_study import (
    INSUFFICIENT_EVIDENCE_STATE,
    format_markdown,
    normalize_record,
    summarize_records,
)


def _record(site, stratum, *, state="raw_html_sufficient", pages=10, manual="not_reviewed"):
    return {
        "site": site,
        "stratum": stratum,
        "render_evidence": {
            "pages_evaluated": pages,
            "client_rendering_suspected_pages": 0,
            "evidence_state": state,
            "coverage": {
                "sufficient": state != INSUFFICIENT_EVIDENCE_STATE,
                "reason": "no_evaluable_html_pages" if state == INSUFFICIENT_EVIDENCE_STATE else "",
            },
        },
        "manual_js_disabled_verdict": manual,
    }


def test_insufficient_state_is_valid_but_not_measurement_eligible():
    normalized = normalize_record(
        _record(
            "blocked-shop",
            "ecommerce_marketplace",
            state=INSUFFICIENT_EVIDENCE_STATE,
            pages=0,
            manual="content_sufficient",
        )
    )

    assert normalized["scanner_evidence_state"] == INSUFFICIENT_EVIDENCE_STATE
    assert normalized["measurement_eligible"] is False
    assert normalized["manual_review_conclusive"] is False
    assert normalized["measurement_exclusion_reason"] == "no_evaluable_html_pages"


def test_summary_excludes_insufficient_records_from_incidence_and_completeness():
    records = []
    for stratum in ("smb_cms", "saas_js", "ecommerce_marketplace"):
        for index in range(10):
            records.append(
                _record(
                    f"{stratum}-{index}",
                    stratum,
                    manual="content_sufficient" if index < 2 else "not_reviewed",
                )
            )
    records[-1] = _record(
        "excluded-ecommerce",
        "ecommerce_marketplace",
        state=INSUFFICIENT_EVIDENCE_STATE,
        pages=0,
    )

    summary = summarize_records(records)

    assert summary["records_received"] == 30
    assert summary["site_count"] == 29
    assert summary["excluded_record_count"] == 1
    assert summary["strata"]["ecommerce_marketplace"]["site_count"] == 9
    assert summary["measurement"]["complete"] is False
    assert summary["calibration"]["passed"] is True
    assert summary["decision"]["action"] == "keep_measuring"
    report = format_markdown(summary)
    assert "Measurement-eligible sites: 29" in report
    assert "excluded-ecommerce" in report


def test_collector_preserves_insufficient_state_for_audit_before_pruning():
    manifest = {
        "site": "blocked-shop",
        "url": "https://example.com",
        "stratum": "ecommerce_marketplace",
    }
    scan_result = {
        "success": True,
        "scanner_version": "scanner-test",
        "pages_crawled": 20,
        "pages_found": 20,
        "render_evidence": {
            "pages_evaluated": 0,
            "client_rendering_suspected_pages": 0,
            "evidence_state": INSUFFICIENT_EVIDENCE_STATE,
            "coverage": {
                "sufficient": False,
                "reason": "no_evaluable_html_pages",
            },
        },
    }

    record = build_study_record(manifest, scan_result)

    assert record["render_evidence"]["evidence_state"] == INSUFFICIENT_EVIDENCE_STATE
    assert normalize_record(record)["measurement_eligible"] is False
