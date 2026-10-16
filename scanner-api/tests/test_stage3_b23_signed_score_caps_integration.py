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


def _fix(fix_id: str, url: str, *, score_cap: int, **extra) -> dict:
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
        "root_cause_evidence": {
            "version": "root_cause_evidence_v1_verified",
            "state": "verified",
            "root_cause_id": "root:shared-template-meta",
            "repair_surface_id": "surface:product-template",
            "evidence_refs": ["evidence:template-meta"],
            "score_cap": score_cap,
        },
    }
    payload.update(extra)
    return payload


def _review(
    fixes: list[dict],
    *,
    score: int = 88,
    ceiling: int = 100,
    coverage_state: str = "sufficient",
    ceiling_reason: str = "",
) -> dict:
    return {
        "cleaned_fixes": fixes,
        "health_score": score,
        "health_score_status": "available",
        "health_score_explanation": {
            "applied_ceiling": ceiling,
            "ceiling_reason": ceiling_reason,
        },
        "site_fingerprint": {
            "coverage_assessment": {"state": coverage_state},
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


def test_b23_verified_root_cause_cap_is_decided_before_signed_completion_without_rewriting_legacy_score():
    urls = ["https://example.com/products/a", "https://example.com/products/b"]
    review = _review([
        _fix("meta-a", urls[0], score_cap=72),
        _fix("meta-b", urls[1], score_cap=72),
    ])
    scan_result = _scan_result(urls)

    integrated = apply_canonical_repair_contract(review, scan_result)
    decision = integrated["stage3_health_score_decision"]

    assert decision["base_health_score"] == 88
    assert decision["coverage_state"] == "sufficient"
    assert decision["existing_score_ceiling"] is None
    assert decision["root_cause_score_ceiling"] == 72
    assert decision["effective_score_ceiling"] == 72
    assert decision["adjusted_health_score"] == 72
    assert decision["applied_root_cause_caps"] == [
        {"root_cause_id": "root:shared-template-meta", "score_cap": 72}
    ]
    # B23 decision evidence is signed, but this source-only slice must not rewrite
    # the customer-visible legacy score before the frozen V7 persistence path is
    # reconciled onto an accepted Stage-1 main.
    assert integrated["health_score"] == 88

    envelope = build_completion_envelope(_scan_record(), scan_result, integrated, "stage3-secret")
    assert envelope["review"]["stage3_health_score_decision"] == decision
    assert envelope["review"]["health_score"] == 88
    signed = {key: envelope[key] for key in ("version", "identity", "scan", "review")}
    assert envelope["proof"] == create_authority_seal(signed, "stage3-secret")


def test_b23_existing_incomplete_ceiling_remains_stricter_than_a_verified_root_cause_cap():
    urls = ["https://example.com/products/a", "https://example.com/products/b"]
    integrated = apply_canonical_repair_contract(
        _review(
            [
                _fix("meta-a", urls[0], score_cap=72),
                _fix("meta-b", urls[1], score_cap=72),
            ],
            score=55,
            ceiling=55,
            coverage_state="limited_coverage",
            ceiling_reason="incomplete_evidence",
        ),
        _scan_result(urls),
    )
    decision = integrated["stage3_health_score_decision"]

    assert decision["base_health_score"] == 55
    assert decision["existing_score_ceiling"] == 55
    assert decision["root_cause_score_ceiling"] == 72
    assert decision["effective_score_ceiling"] == 55
    assert decision["adjusted_health_score"] == 55
    assert integrated["health_score"] == 55


def test_b23_conflicting_documented_caps_for_same_verified_root_cause_fail_closed():
    urls = ["https://example.com/products/a", "https://example.com/products/b"]
    review = _review([
        _fix("meta-a", urls[0], score_cap=72),
        _fix("meta-b", urls[1], score_cap=48),
    ])

    integrated = apply_canonical_repair_contract(review, _scan_result(urls))
    [group] = integrated["stage3_root_cause_groups"]
    decision = integrated["stage3_health_score_decision"]

    assert group["grouping_state"] == "verified"
    assert group["score_cap"] is None
    assert group["score_cap_state"] == "conflicted"
    assert decision["root_cause_score_ceiling"] is None
    assert decision["adjusted_health_score"] == 88
    assert decision["applied_root_cause_caps"] == []
    assert decision["ignored_root_cause_caps"] == [
        {
            "root_cause_id": "root:shared-template-meta",
            "score_cap": None,
            "reason": "root_cause_not_verified",
        }
    ]


def test_b23_foreign_repair_scan_identity_cannot_apply_a_documented_cap():
    urls = ["https://example.com/products/a", "https://example.com/products/b"]
    fixes = [
        _fix(
            "meta-a",
            urls[0],
            score_cap=40,
            scan_id="foreign-scan",
            scan_run_id="foreign-scan",
        ),
        _fix(
            "meta-b",
            urls[1],
            score_cap=40,
            scan_id="foreign-scan",
            scan_run_id="foreign-scan",
        ),
    ]
    integrated = apply_canonical_repair_contract(_review(fixes), _scan_result(urls))
    decision = integrated["stage3_health_score_decision"]

    assert len(integrated["stage3_root_cause_groups"]) == 2
    assert all(group["grouping_state"] == "not_verified" for group in integrated["stage3_root_cause_groups"])
    assert decision["root_cause_score_ceiling"] is None
    assert decision["adjusted_health_score"] == 88
    assert decision["applied_root_cause_caps"] == []
