from app.crawler_acceptance import (
    build_acceptance_record,
    format_acceptance_markdown,
    summarize_acceptance,
    validate_crawler_contract,
)


def _scan(*, render_state="raw_html_sufficient", evaluated=3):
    pages = [
        {
            "path": "/",
            "status_code": 200,
            "indexable": True,
            "indexability_state": "Indexable",
        },
        {
            "path": "/old",
            "status_code": 301,
            "indexable": False,
            "indexability_state": "Redirected",
            "redirect_state": "single_redirect",
        },
        {
            "path": "/missing",
            "status_code": 200,
            "indexable": False,
            "indexability_state": "Soft 404",
            "soft_404_suspected": True,
        },
    ]
    return {
        "success": True,
        "scanner_version": "scanner-test",
        "pages_crawled": len(pages),
        "pages_found": len(pages),
        "pages": pages,
        "crawled_pages": pages,
        "raw_findings": [
            {
                "id": "soft",
                "rule": "soft_404",
                "page_url": "/missing",
                "affected_pages": ["/missing"],
                "source_pages": ["/sitemap.xml"],
            }
        ],
        "render_evidence": {
            "evidence_state": render_state,
            "pages_evaluated": evaluated,
            "client_rendering_suspected_pages": 0,
            "suspected_ratio": 0.0,
        },
    }


def _review(*, score=84, provisional=False, scan_status="complete"):
    finding = {
        "id": "fix-1",
        "fix_id": "fix-1",
        "rule": "canonical_missing",
        "title": "Add canonical URLs",
        "priority": "medium",
        "page_url": "/",
        "affected_pages": ["/"],
        "source_pages": ["/"],
    }
    return {
        "health_score": score,
        "seo_score": score,
        "cleaned_fixes": [finding],
        "scan_status": scan_status,
        "score_is_provisional": provisional,
        "access_evidence_state": "complete",
        "website_health_report": {
            "health_score": score,
            "score": score,
            "scan_status": scan_status,
            "score_is_provisional": provisional,
        },
        "scan_summary": {"health_score": score, "score": score},
    }


def _manifest(site, stratum):
    return {
        "site": site,
        "url": f"https://{site}.example.com",
        "stratum": stratum,
        "scan_mode": "advanced",
    }


def test_clean_scan_and_review_pass_contract():
    validation = validate_crawler_contract(_scan(), _review())

    assert validation["passed"] is True
    assert validation["errors"] == []


def test_contract_catches_false_negative_evidence_and_review_drift():
    scan = _scan(evaluated=0)
    scan["crawled_pages"][1]["indexable"] = True
    scan["raw_findings"].append({
        "id": "noise",
        "rule": "missing_meta_description",
        "page_url": "/missing",
        "affected_pages": ["/missing"],
        "source_pages": ["/missing"],
    })
    review = _review(scan_status="blocked_or_incomplete", provisional=False)
    review["seo_score"] = 72
    review["cleaned_fixes"] = [
        {
            "id": "dup",
            "fix_id": "dup",
            "rule": "a",
            "affected_pages": ["/"],
            "source_pages": [],
        },
        {
            "id": "dup",
            "fix_id": "dup",
            "rule": "b",
            "affected_pages": [],
            "source_pages": ["/"],
        },
    ]

    validation = validate_crawler_contract(scan, review)

    assert validation["passed"] is False
    assert set(validation["error_codes"]) >= {
        "zero_page_raw_html_sufficient",
        "redirect_marked_indexable",
        "soft_404_metadata_noise",
        "duplicate_review_finding_ids",
        "review_finding_missing_affected_pages",
        "review_finding_missing_source_pages",
        "review_score_mismatch",
        "access_limited_score_not_provisional",
    }


def test_insufficient_renderer_coverage_is_warning_not_contract_failure():
    scan = _scan(render_state="insufficient_raw_html_evidence", evaluated=0)
    scan["render_evidence"]["coverage"] = {"reason": "no_evaluable_html_pages"}

    validation = validate_crawler_contract(scan, _review())

    assert validation["passed"] is True
    assert validation["warning_codes"] == ["insufficient_render_coverage"]


def test_acceptance_summary_requires_nine_balanced_passing_sites():
    strata = ["smb_cms", "saas_js", "ecommerce_marketplace"]
    manifest = [
        _manifest(f"{stratum}-{index}", stratum)
        for stratum in strata
        for index in range(3)
    ]
    records = [
        build_acceptance_record(item, _scan(), _review(), duration_seconds=12.3)
        for item in manifest
    ]

    summary = summarize_acceptance(manifest, records, [])

    assert summary["complete"] is True
    assert summary["acceptance_passed"] is True
    assert summary["freeze_recommendation"] == "freeze_beta_crawler"
    assert summary["completed_by_stratum"] == {
        "smb_cms": 3,
        "saas_js": 3,
        "ecommerce_marketplace": 3,
    }
    report = format_acceptance_markdown(summary)
    assert "Acceptance passed: yes" in report
    assert "freeze_beta_crawler" in report


def test_only_repeated_contract_defects_are_reported_as_recurring():
    strata = ["smb_cms", "saas_js", "ecommerce_marketplace"]
    manifest = [
        _manifest(f"{stratum}-{index}", stratum)
        for stratum in strata
        for index in range(3)
    ]
    records = [
        build_acceptance_record(item, _scan(), _review(), duration_seconds=1)
        for item in manifest
    ]
    records[0]["validation"] = {
        "passed": False,
        "errors": [],
        "warnings": [],
        "error_codes": ["repeated_problem", "single_problem"],
        "warning_codes": [],
    }
    records[1]["validation"] = {
        "passed": False,
        "errors": [],
        "warnings": [],
        "error_codes": ["repeated_problem"],
        "warning_codes": [],
    }

    summary = summarize_acceptance(manifest, records, [])

    assert summary["acceptance_passed"] is False
    assert summary["recurring_contract_violations"] == {
        "repeated_problem": ["smb_cms-0", "smb_cms-1"]
    }



def test_not_redirected_state_is_not_a_redirect_source():
    scan = _scan()
    scan["crawled_pages"][0]["redirect_state"] = "not_redirected"

    validation = validate_crawler_contract(scan, _review())

    assert validation["passed"] is True
    assert "redirect_marked_indexable" not in validation["error_codes"]


def test_actual_redirect_state_cannot_remain_indexable_after_final_200():
    scan = _scan()
    page = scan["crawled_pages"][0]
    page.update({
        "status_code": 200,
        "redirect_state": "single_redirect",
        "redirect_hop_count": 1,
        "indexability_state": "Redirected",
        "indexable": True,
    })

    validation = validate_crawler_contract(scan, _review())

    assert validation["passed"] is False
    assert "redirect_marked_indexable" in validation["error_codes"]
