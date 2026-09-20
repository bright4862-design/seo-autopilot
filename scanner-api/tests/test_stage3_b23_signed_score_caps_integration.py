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


def _fix(fix_id: str, url: str, *, score_cap: int) -> dict:
    return {
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
        "root_cause_evidence": {
            "version": "root_cause_evidence_v1_verified",
            "state": "verified",
            "root_cause_id": "root:shared-template-meta",
            "repair_surface_id": "surface:product-template",
            "evidence_refs": ["evidence:template-meta"],
            "score_cap": score_cap,
        },
    }


def _scan_record() -> dict:
    return {
        "id": "scan-stage3-b23",
        "owner_user_id": "owner-stage3",
        "project_id": "project-stage3",
        "request_id": "request-stage3-b23",
        "idempotency_key": "idem-stage3-b23",
        "attempt_count": 1,
    }


def _scan_result(urls: list[str]) -> dict:
    return {
        "scan_id": "scan-stage3-b23",
        "scan_run_id": "scan-stage3-b23",
        "website_url": "https://example.com",
        "normalized_domain": "example.com",
        "respect_robots_txt": True,
        "owner_attested_robots_override": False,
        "crawled_pages": [_page(url) for url in urls],
    }


def test_b23_verified_root_cause_cap_is_decided_before_signed_completion_without_raising_existing_ceiling():
    urls = ["https://example.com/products/a", "https://example.com/products/b"]
    review = {
        "cleaned_fixes": [
            _fix("meta-a", urls[0], score_cap=72),
            _fix("meta-b", urls[1], score_cap=72),
        ],
        # This is the already-final legacy score after the existing sample/access/
        # incomplete pipeline has run. B23 may only lower it; it must never
        # recompute or raise this established boundary.
        "health_score": 55,
        "health_score_status": "available",
        "health_score_explanation": {
            "applied_ceiling": 55,
            "ceiling_reason": "incomplete_evidence",
        },
        "site_fingerprint": {
            "coverage_assessment": {"state": "limited_coverage"},
        },
    }
    scan_result = _scan_result(urls)

    integrated = apply_canonical_repair_contract(review, scan_result)
    decision = integrated["stage3_health_score_decision"]

    assert decision["base_health_score"] == 55
    assert decision["coverage_state"] == "limited_coverage"
    assert decision["existing_score_ceiling"] == 55
    assert decision["root_cause_score_ceiling"] == 72
    assert decision["effective_score_ceiling"] == 55
    assert decision["adjusted_health_score"] == 55
    assert decision["applied_root_cause_caps"] == [
        {"root_cause_id": "root:shared-template-meta", "score_cap": 72}
    ]
    # B23 decision evidence is signed, but this source-only slice must not rewrite
    # the customer-visible legacy score before the frozen V7 persistence path is
    # reconciled onto an accepted Stage-1 main.
    assert integrated["health_score"] == 55

    envelope = build_completion_envelope(_scan_record(), scan_result, integrated, "stage3-secret")
    assert envelope["review"]["stage3_health_score_decision"] == decision
    assert envelope["review"]["health_score"] == 55
    signed = {key: envelope[key] for key in ("version", "identity", "scan", "review")}
    assert envelope["proof"] == create_authority_seal(signed, "stage3-secret")
