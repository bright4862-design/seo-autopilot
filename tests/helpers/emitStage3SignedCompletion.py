#!/usr/bin/env python3
"""Emit one real signed Stage-3 completion envelope for the V7 delivery contract test."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scanner-api"))

from app.repair_contract_v2 import apply_canonical_repair_contract  # noqa: E402
from app.scan_job import build_completion_envelope  # noqa: E402

IDENTITY_VERSION = "evidence_url_identity_v2_published_route"
SECRET = "stage3-v7-durable-test-secret"
SCAN_ID = "scan-stage3-v7-durable"
OWNER_ID = "owner-stage3-v7"
PROJECT_ID = "project-stage3-v7"


def page(url: str) -> dict:
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


def fix(fix_id: str, url: str, *, score_cap: int = 72) -> dict:
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
        "issue_title": f"Repair product description {fix_id}",
        "verification_steps": ["Confirm the corrected description is present on the affected product page."],
        "dependency": "Product page SEO template",
        "vendor_owner": "Engineering",
        "root_cause_evidence": {
            "version": "root_cause_evidence_v1_verified",
            "state": "verified",
            "root_cause_id": "root:shared-product-meta-template",
            "repair_surface_id": "surface:product-template",
            "evidence_refs": [f"evidence:{fix_id}"],
            "score_cap": score_cap,
        },
    }


def main() -> None:
    urls = [
        "https://example.com/products/a",
        "https://example.com/products/b",
    ]
    review = {
        "cleaned_fixes": [fix("meta-a", urls[0]), fix("meta-b", urls[1])],
        "health_score": 88,
        "health_score_status": "available",
        # Existing coverage ceiling is deliberately stricter than the B20/B23 root-cause cap.
        "health_score_explanation": {
            "version": "health_score_explanation_v1",
            "starting_score": 100,
            "final_score": 64,
            "total_deduction": 12,
            "deductions": [{"category": "technical", "points": 12}],
            "coverage_ceiling": 64,
            "applied_ceiling": 64,
            "ceiling_reason": "coverage",
            "floor_applied": False,
            "verification_findings_excluded": False,
        },
        "site_fingerprint": {
            "coverage_assessment": {
                "state": "sufficient",
                "coverage_authority_version": "coverage-v1",
            }
        },
    }
    scan_result = {
        "scan_id": SCAN_ID,
        "scan_run_id": SCAN_ID,
        "website_url": "https://example.com",
        "submitted_url": "https://example.com",
        "requested_origin": "https://example.com",
        "normalized_domain": "example.com",
        "respect_robots_txt": True,
        "owner_attested_robots_override": False,
        "crawled_pages": [page(url) for url in urls],
        "pages_found": 2,
        "pages_crawled": 2,
    }
    integrated = apply_canonical_repair_contract(
        review,
        scan_result,
        identity_version=IDENTITY_VERSION,
    )
    scan_record = {
        "id": SCAN_ID,
        "scan_id": SCAN_ID,
        "owner_user_id": OWNER_ID,
        "project_id": PROJECT_ID,
        "normalized_domain": "example.com",
        "request_id": "request-stage3-v7-durable",
        "idempotency_key": "request-stage3-v7-durable",
        "attempt_count": 1,
    }
    envelope = build_completion_envelope(scan_record, scan_result, integrated, SECRET)
    print(json.dumps({
        "secret": SECRET,
        "identity_version": IDENTITY_VERSION,
        "envelope": envelope,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
