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


def _fix(
    fix_id: str,
    url: str,
    *,
    rule: str,
    category: str,
    priority: str,
    verification_state: str = "verified",
) -> dict:
    return {
        "fix_id": fix_id,
        "rule": rule,
        "category": category,
        "priority": priority,
        "base_severity": priority,
        "evidence_class": "confirmed_problem",
        "action_priority": "fix_first" if priority in {"critical", "high"} else "improve",
        "priority_reason": "verified synthetic preview fixture",
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
        "verification_state": verification_state,
        "evidence_status": "confirmed" if verification_state == "verified" else "not_verified",
        "repair_surface": f"cms:{fix_id}",
        "remediation_family": f"repair:{fix_id}",
        "issue_title": f"Preview {fix_id}",
        "evidence_summary": f"Bounded evidence for {fix_id}.",
        "secret_internal_trace": f"private:{fix_id}",
        "suppressed_findings": [{"title": f"hidden:{fix_id}"}],
    }


def _review(fixes: list[dict]) -> dict:
    return {
        "cleaned_fixes": fixes,
        "health_score": 88,
        "health_score_status": "available",
        "health_score_explanation": {"applied_ceiling": 100},
        "site_fingerprint": {"coverage_assessment": {"state": "sufficient"}},
    }


def _scan_result(urls: list[str], *, scan_run_id: str = "scan-stage3-b22") -> dict:
    return {
        "scan_id": "scan-stage3-b22",
        "scan_run_id": scan_run_id,
        "website_url": "https://example.com",
        "normalized_domain": "example.com",
        "respect_robots_txt": True,
        "owner_attested_robots_override": False,
        "crawled_pages": [_page(url) for url in urls],
    }


def _scan_record() -> dict:
    return {
        "id": "scan-stage3-b22",
        "owner_user_id": "owner-stage3",
        "project_id": "project-stage3",
        "request_id": "request-stage3-b22",
        "idempotency_key": "idem-stage3-b22",
        "attempt_count": 1,
    }


def test_b22_evidence_led_preview_source_is_customer_safe_and_signed():
    urls = [
        "https://example.com/products/broken",
        "https://example.com/products/duplicate",
        "https://example.com/products/meta",
        "https://example.com/products/unverified",
    ]
    fixes = [
        _fix("broken", urls[0], rule="broken_page", category="404_error", priority="critical"),
        _fix("duplicate", urls[1], rule="duplicate_content", category="duplicate_content", priority="high"),
        _fix("meta", urls[2], rule="missing_meta_description", category="meta_description", priority="medium"),
        _fix(
            "unverified-critical",
            urls[3],
            rule="broken_page",
            category="404_error",
            priority="critical",
            verification_state="not_verified",
        ),
    ]
    scan_result = _scan_result(urls)
    integrated = apply_canonical_repair_contract(_review(fixes), scan_result)

    source = integrated["stage3_private_preview_source"]
    assert source["version"] == "stage3_preview_source_v1_verified_evidence"
    assert source["scan_id"] == "scan-stage3-b22"
    assert source["entitlement_state"] == "requires_authenticated_customer_gate"
    assert source["state"] == "findings"
    assert len(source["findings"]) == 2
    assert [item["rule_id"] for item in source["findings"]] == ["broken", "duplicate"]
    assert all(set(item) == {"rule_id", "title", "impact", "evidence_summary"} for item in source["findings"])
    assert "unverified-critical" not in {item["rule_id"] for item in source["findings"]}

    serialized = json.dumps(source, sort_keys=True)
    assert "private:" not in serialized
    assert "hidden:" not in serialized
    assert "affected_pages" not in serialized
    assert "suppressed_findings" not in serialized

    envelope = build_completion_envelope(_scan_record(), scan_result, integrated, "stage3-b22-secret")
    assert envelope["review"]["stage3_private_preview_source"] == source
    signed = {key: envelope[key] for key in ("version", "identity", "scan", "review")}
    assert envelope["proof"] == create_authority_seal(signed, "stage3-b22-secret")


def test_b22_preview_source_fails_closed_when_producer_scan_identity_is_not_exact():
    url = "https://example.com/products/a"
    integrated = apply_canonical_repair_contract(
        _review([_fix("meta", url, rule="missing_meta_description", category="meta_description", priority="medium")]),
        _scan_result([url], scan_run_id="different-scan-run"),
    )

    assert "stage3_private_preview_source" not in integrated
