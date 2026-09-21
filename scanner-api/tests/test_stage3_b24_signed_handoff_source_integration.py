import json

from app.repair_contract_v2 import apply_canonical_repair_contract
from app.scan_job import build_completion_envelope, create_authority_seal


def _page(url: str) -> dict:
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


def _fix(fix_id: str, url: str) -> dict:
    return {
        "fix_id": fix_id,
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
        "issue_title": "Repair the shared product description template",
        "verification_steps": ["Confirm the corrected description is present on the affected product page."],
        "dependency": "Product page SEO template",
        "vendor_owner": "Engineering",
        "root_cause_evidence": {
            "version": "root_cause_evidence_v1_verified",
            "state": "verified",
            "root_cause_id": "root:shared-product-meta-template",
            "repair_surface_id": "surface:product-template",
            "evidence_refs": [f"evidence:{fix_id}"],
            "score_cap": 72,
        },
    }


def _review(fixes: list[dict]) -> dict:
    return {
        "cleaned_fixes": fixes,
        "health_score": 88,
        "health_score_status": "available",
        "health_score_explanation": {"applied_ceiling": 100},
        "site_fingerprint": {"coverage_assessment": {"state": "sufficient"}},
    }


def _scan_result(urls: list[str], *, scan_run_id: str = "scan-stage3-b24") -> dict:
    return {
        "scan_id": "scan-stage3-b24",
        "scan_run_id": scan_run_id,
        "website_url": "https://example.com",
        "normalized_domain": "example.com",
        "respect_robots_txt": True,
        "owner_attested_robots_override": False,
        "crawled_pages": [_page(url) for url in urls],
    }


def _scan_record() -> dict:
    return {
        "id": "scan-stage3-b24",
        "owner_user_id": "owner-stage3",
        "project_id": "project-stage3",
        "request_id": "request-stage3-b24",
        "idempotency_key": "idem-stage3-b24",
        "attempt_count": 1,
    }


def test_b24_customer_safe_handoff_source_is_attached_before_completion_signing():
    urls = ["https://example.com/products/a", "https://example.com/products/b"]
    integrated = apply_canonical_repair_contract(
        _review([_fix("meta-a", urls[0]), _fix("meta-b", urls[1])]),
        _scan_result(urls),
    )

    source = integrated["stage3_handoff_v2_source"]
    assert source["handoff_version"] == "fixlist_handoff_v2"
    assert source["scan"]["scan_id"] == "scan-stage3-b24"
    assert source["scan"]["scan_run_id"] == "scan-stage3-b24"
    assert source["scan"]["normalized_domain"] == "example.com"
    assert source["user_agent"] == "FixListPythonScanner"
    assert source["fix_count"] >= 1

    assert all(fix["root_cause_id"] == "root:shared-product-meta-template" for fix in source["fixes"])
    assert all("product_page" in fix["family_ids"] for fix in source["fixes"])
    assert all(fix["counts"]["indexable_affected"] == 1 for fix in source["fixes"])
    assert all(fix["priority_factors"].get("version") for fix in source["fixes"])
    assert "suppressed_findings" not in source
    assert "suppressed_members" not in json.dumps(source, sort_keys=True)

    envelope = build_completion_envelope(_scan_record(), _scan_result(urls), integrated, "stage3-b24-secret")
    assert envelope["review"]["stage3_handoff_v2_source"] == source
    signed = {key: envelope[key] for key in ("version", "identity", "scan", "review")}
    assert envelope["proof"] == create_authority_seal(signed, "stage3-b24-secret")


def test_b24_handoff_source_fails_closed_when_producer_scan_identity_is_not_exact():
    url = "https://example.com/products/a"
    integrated = apply_canonical_repair_contract(
        _review([_fix("meta-a", url)]),
        _scan_result([url], scan_run_id="different-scan-run"),
    )

    assert "stage3_handoff_v2_source" not in integrated


def test_b24_signed_source_does_not_stringify_structured_scan_identity_into_customer_handoff():
    url = "https://example.com/products/a"
    sentinel = "https://private.example/operator-debug?token=stage3-b24-scan-identity"
    scan_result = _scan_result([url])
    scan_result["normalized_domain"] = {"operator_debug": sentinel}

    integrated = apply_canonical_repair_contract(
        _review([_fix("meta-a", url)]),
        scan_result,
    )

    source = integrated["stage3_handoff_v2_source"]
    assert source["scan"]["normalized_domain"] is None
    assert sentinel not in json.dumps(source, sort_keys=True)

    envelope = build_completion_envelope(_scan_record(), scan_result, integrated, "stage3-b24-secret")
    signed_source = envelope["review"]["stage3_handoff_v2_source"]
    assert signed_source == source
    assert sentinel not in json.dumps(signed_source, sort_keys=True)


def test_b22_b24_signed_sources_do_not_stringify_structured_customer_fields():
    url = "https://example.com/products/a"
    sentinel = "https://private.example/operator-debug?token=stage3-b22-b24-fields"
    fix = _fix("meta-a", url)
    fix["issue_title"] = {"operator_debug": sentinel}
    fix["evidence_refs"] = ["evidence:public", {"operator_debug": sentinel}]

    integrated = apply_canonical_repair_contract(
        _review([fix]),
        _scan_result([url]),
    )

    preview_source = integrated["stage3_private_preview_source"]
    handoff_source = integrated["stage3_handoff_v2_source"]
    assert preview_source["findings"][0]["title"] == "meta-a"
    assert handoff_source["fixes"][0]["title"] == "meta-a"
    assert "evidence:public" in handoff_source["fixes"][0]["evidence_refs"]

    serialized = json.dumps(
        {"preview": preview_source, "handoff": handoff_source},
        sort_keys=True,
    )
    assert sentinel not in serialized
    assert "operator_debug" not in serialized

    envelope = build_completion_envelope(_scan_record(), _scan_result([url]), integrated, "stage3-b24-secret")
    signed_review = envelope["review"]
    assert signed_review["stage3_private_preview_source"] == preview_source
    assert signed_review["stage3_handoff_v2_source"] == handoff_source
    assert sentinel not in json.dumps(signed_review, sort_keys=True)
