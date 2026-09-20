from app.repair_contract_v2 import apply_canonical_repair_contract
from app.scan_job import build_completion_envelope, create_authority_seal
from app.stage3_priority_factors import FOUR_FACTOR_PRIORITY_VERSION


def _page(url: str, *, family: str = "product_page") -> dict:
    return {
        "url": url,
        "final_url": url,
        "status_code": 200,
        "content_type": "text/html",
        "page_evidence_class": "usable_html",
        "indexable": True,
        "page_template_family": family,
        "page_value_role": "money" if family == "product_page" else "hub",
    }


def _fix(fix_id: str, url: str, **extra) -> dict:
    payload = {
        "fix_id": fix_id,
        "rule": "missing_meta_description",
        "category": "meta_description",
        "priority": "medium",
        "page_scope": "page",
        "page_template_family": "product_page",
        "affected_pages": [url],
        "confidence_score": 95,
        "verification_state": "verified",
        "evidence_status": "confirmed",
        "repair_surface": "cms_field",
        "remediation_family": "update_meta_description",
        "issue_title": fix_id,
    }
    payload.update(extra)
    return payload


def _scan_record() -> dict:
    return {
        "id": "scan-stage3",
        "owner_user_id": "owner-stage3",
        "project_id": "project-stage3",
        "request_id": "request-stage3",
        "idempotency_key": "idem-stage3",
        "attempt_count": 1,
    }


def test_b19_four_factor_envelope_is_attached_before_signed_completion():
    url = "https://example.com/products/a"
    review = {"recommendations": [_fix("meta-a", url)], "cleaned_fixes": [_fix("meta-a", url)]}
    scan_result = {
        "scan_id": "scan-stage3",
        "scan_run_id": "scan-stage3",
        "website_url": "https://example.com",
        "normalized_domain": "example.com",
        "respect_robots_txt": True,
        "owner_attested_robots_override": False,
        "crawled_pages": [_page(url)],
    }

    integrated = apply_canonical_repair_contract(review, scan_result)
    [repair] = integrated["canonical_repairs"]
    factors = repair["stage3_priority_factors"]

    assert factors["version"] == FOUR_FACTOR_PRIORITY_VERSION
    assert factors["impact"] == 2
    assert factors["reach"] == 1.0
    assert factors["page_value"] == 1.0
    assert factors["confidence"] == 1.0
    assert factors["priority_factor_score"] == 2.0
    assert repair["priority_factors"] == factors

    envelope = build_completion_envelope(_scan_record(), scan_result, integrated, "stage3-secret")
    assert envelope["review"]["canonical_repairs"][0]["stage3_priority_factors"] == factors
    signed = {key: envelope[key] for key in ("version", "identity", "scan", "review")}
    assert envelope["proof"] == create_authority_seal(signed, "stage3-secret")


def test_b19_unknown_reach_remains_unknown_in_signed_review_and_repair_leverage_cannot_change_score():
    urls = ["https://example.com/a", "https://example.com/b"]
    base = _fix(
        "broken-mixed",
        urls[0],
        rule="broken_page",
        category="404_error",
        page_template_family="mixed",
        affected_pages=urls,
    )
    scan_result = {
        "scan_id": "scan-stage3",
        "scan_run_id": "scan-stage3",
        "website_url": "https://example.com",
        "normalized_domain": "example.com",
        "respect_robots_txt": True,
        "owner_attested_robots_override": False,
        "crawled_pages": [_page(urls[0], family="standard"), _page(urls[1], family="product_page")],
    }

    first = apply_canonical_repair_contract({"cleaned_fixes": [base]}, scan_result)["canonical_repairs"][0]
    second = apply_canonical_repair_contract(
        {"cleaned_fixes": [{**base, "repair_leverage": 999999, "repair_leverage_score": 999999}]},
        scan_result,
    )["canonical_repairs"][0]

    assert first["stage3_priority_factors"]["reach"] is None
    assert first["stage3_priority_factors"]["reach_state"] == "unknown"
    assert first["stage3_priority_factors"]["priority_factor_score"] is None
    assert second["stage3_priority_factors"]["priority_factor_score"] is None


def test_b20_groups_only_explicit_verified_same_root_cause_with_exact_scan_identity():
    urls = ["https://example.com/products/a", "https://example.com/products/b"]
    common_evidence = {
        "version": "root_cause_evidence_v1_verified",
        "state": "verified",
        "root_cause_id": "root:shared-template-meta",
        "repair_surface_id": "surface:product-template",
        "evidence_refs": ["evidence:template-meta"],
    }
    first = _fix("meta-a", urls[0], root_cause_evidence=common_evidence, finding_domain="seo")
    second = _fix(
        "meta-b",
        urls[1],
        root_cause_evidence=common_evidence,
        finding_domain="geo",
        page_template_family="product_page",
    )
    scan_result = {
        "scan_id": "scan-stage3",
        "scan_run_id": "scan-stage3",
        "website_url": "https://example.com",
        "normalized_domain": "example.com",
        "respect_robots_txt": True,
        "owner_attested_robots_override": False,
        "crawled_pages": [_page(url) for url in urls],
    }

    integrated = apply_canonical_repair_contract({"cleaned_fixes": [first, second]}, scan_result)
    groups = integrated["stage3_root_cause_groups"]

    assert len(groups) == 1
    assert groups[0]["grouping_state"] == "verified"
    assert groups[0]["scan_id"] == "scan-stage3"
    assert groups[0]["root_cause_id"] == "root:shared-template-meta"
    assert groups[0]["domains"] == ["seo", "geo"]
    assert groups[0]["affected_pages"] == urls
    assert groups[0]["suppressed_members"][0]["reason"] == "same_verified_root_cause"

    no_exact_identity = {**scan_result, "scan_run_id": "different-scan"}
    fail_closed = apply_canonical_repair_contract({"cleaned_fixes": [first, second]}, no_exact_identity)
    assert len(fail_closed["stage3_root_cause_groups"]) == 2
    assert all(group["grouping_state"] == "not_verified" for group in fail_closed["stage3_root_cause_groups"])
