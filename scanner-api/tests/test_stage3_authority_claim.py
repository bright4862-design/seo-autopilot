from app.repair_contract_v2 import apply_canonical_repair_contract, STAGE3_AUTHORITY_CLAIM_VERSION


def _page(url):
    return {
        "url": url,
        "final_url": url,
        "status_code": 200,
        "content_type": "text/html",
        "page_evidence_class": "usable_html",
        "indexable": True,
        "page_template_family": "product_page",
        "page_value_role": "money",
    }


def _fix(url):
    return {
        "fix_id": "meta-a",
        "rule": "missing_meta_description",
        "category": "meta_description",
        "priority": "medium",
        "page_scope": "page",
        "page_template_family": "product_page",
        "affected_pages": [url],
        "affected_reported": 1,
        "affected_observed": 1,
        "affected_eligible": 1,
        "checked_eligible": 1,
        "indexable_affected": 1,
        "indexable_checked_eligible": 1,
        "confidence_score": 95,
        "verification_state": "verified",
        "evidence_status": "confirmed",
        "repair_surface": "cms_field",
        "remediation_family": "update_meta_description",
    }


def _review(fix):
    return {
        "cleaned_fixes": [fix],
        "health_score": 88,
        "health_score_explanation": {
            "version": "health_score_explanation_v1",
            "starting_score": 100,
            "final_score": 88,
            "total_deduction": 12,
            "deductions": [{"category": "Search visibility", "points": 12}],
            "coverage_ceiling": 100,
            "applied_ceiling": 100,
            "ceiling_reason": "",
            "floor_applied": False,
            "verification_findings_excluded": False,
        },
        "site_fingerprint": {"coverage_assessment": {"state": "sufficient"}},
    }


def test_exact_scan_identity_emits_versioned_stage3_authority_claim():
    url = "https://example.com/product/a"
    result = apply_canonical_repair_contract(
        _review(_fix(url)),
        {
            "scan_id": "scan-a",
            "scan_run_id": "scan-a",
            "website_url": "https://example.com",
            "normalized_domain": "example.com",
            "crawled_pages": [_page(url)],
        },
    )
    claim = result["stage3_authority_claim"]
    assert claim == {
        "version": STAGE3_AUTHORITY_CLAIM_VERSION,
        "scan_id": "scan-a",
        "delivery_version": result["stage3_delivery"]["version"],
        "score_version": result["stage3_health_score_decision"]["version"],
    }


def test_stage3_authority_claim_is_absent_without_exact_scan_identity():
    url = "https://example.com/product/a"
    result = apply_canonical_repair_contract(
        _review(_fix(url)),
        {
            "scan_id": "scan-a",
            "scan_run_id": "different",
            "website_url": "https://example.com",
            "normalized_domain": "example.com",
            "crawled_pages": [_page(url)],
        },
    )
    assert "stage3_authority_claim" not in result
