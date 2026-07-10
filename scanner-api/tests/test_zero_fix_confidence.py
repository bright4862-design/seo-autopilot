from app.review import run_review


def _clean_page(path="/"):
    url = f"https://example.com{path}"
    return {
        "final_url": url,
        "status_code": 200,
        "canonical": url,
        "h1_count": 1,
        "meta_description": "Clear description",
        "image_missing_alt_count": 0,
        "page_template_family": "standard",
    }


def test_complete_zero_fix_review_uses_bounded_confidence_state():
    result = run_review({
        "website_url": "https://example.com",
        "pages": [_clean_page()],
        "scan_coverage": {
            "pages_found": 1,
            "pages_crawled": 1,
            "sampled_pages_sent_to_ai": 1,
        },
    })

    assert result["cleaned_fixes"] == []
    assert result["ai_review_warning"] == ""
    assert result["no_high_confidence_findings"] is True
    assert result["review_confidence_state"] == "no_high_confidence_findings"
    assert result["zero_fix_confidence_version"] == "python_review_v3_zero_fix_confidence"
    assert result["health_grade"] == "No issues found in sample"
    assert result["scan_status"] == "complete_no_high_confidence_findings"

    report = result["website_health_report"]
    assert report["health_grade"] == "No issues found in sample"
    assert "scanned sample" in report["overall_explanation"]
    assert "first FixList item" not in report["next_best_step"]
    assert any("unscanned pages" in item for item in report["limitations"])


def test_incomplete_evidence_does_not_claim_no_high_confidence_findings():
    result = run_review({"website_url": "https://example.com"})

    assert result.get("no_high_confidence_findings") is not True
    assert result["website_health_report"]["health_grade"] == "Scan incomplete"
    assert result["ai_review_warning"]


def test_real_fix_keeps_normal_review_state():
    page = _clean_page("/needs-canonical")
    page["canonical"] = ""
    result = run_review({
        "website_url": "https://example.com",
        "pages": [page],
        "scan_coverage": {
            "pages_found": 1,
            "pages_crawled": 1,
            "sampled_pages_sent_to_ai": 1,
        },
    })

    assert result["cleaned_fixes"]
    assert result.get("no_high_confidence_findings") is not True
    assert result["website_health_report"]["health_grade"] != "No issues found in sample"
