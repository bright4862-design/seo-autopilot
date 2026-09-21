#!/usr/bin/env python3
"""Emit a signed >36-candidate Stage-3 completion for durable V7 delivery tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scanner-api"))

from app.repair_contract_v2 import apply_canonical_repair_contract  # noqa: E402
from app.scan_job import build_completion_envelope  # noqa: E402

IDENTITY_VERSION = "evidence_url_identity_v2_published_route"
SECRET = "stage3-v7-ranked-test-secret"
SCAN_ID = "scan-stage3-v7-ranked"
OWNER_ID = "owner-stage3-v7-ranked"
PROJECT_ID = "project-stage3-v7-ranked"


def page(url: str, *, family: str = "product_page", indexable: bool = True, role: str = "money") -> dict:
    return {
        "url": url,
        "final_url": url,
        "status_code": 200,
        "content_type": "text/html",
        "page_evidence_class": "usable_html",
        "indexable": indexable,
        "page_template_family": family,
        "page_value_role": role,
    }


def fix(
    fix_id: str,
    url: str,
    *,
    rule: str = "missing_meta_description",
    category: str = "meta_description",
    family: str = "product_page",
    indexable_affected: int = 1,
) -> dict:
    return {
        "fix_id": fix_id,
        "rule": rule,
        "category": category,
        "priority": "medium",
        "page_scope": "page",
        "page_template_family": family,
        "affected_pages": [url],
        "affected_reported": 1,
        "affected_observed": 1,
        "affected_eligible": 1,
        "checked_eligible": 1,
        "indexable_affected": indexable_affected,
        "indexable_checked_eligible": 1,
        "confidence_score": 95,
        "verification_state": "verified",
        "evidence_status": "confirmed",
        "repair_surface": "cms_field",
        "remediation_family": "update_meta_description",
        "issue_title": f"Repair {fix_id}",
        "verification_steps": ["Confirm the corrected value is present on the affected page."],
        "dependency": "Page template",
        "vendor_owner": "Engineering",
        "root_cause_evidence": {
            "version": "root_cause_evidence_v1_verified",
            "state": "verified",
            "root_cause_id": "root:ranked-stage3-template",
            "repair_surface_id": "surface:ranked-stage3-template",
            "evidence_refs": [f"evidence:{fix_id}"],
            "score_cap": 72,
        },
    }


def main() -> None:
    product_urls = [f"https://example.com/products/{index:02d}" for index in range(38)]
    zero_url = "https://example.com/products/nonindexable"
    unknown_url = "https://example.com/misc/unknown"
    pages = [page(url) for url in product_urls]
    pages.append(page(zero_url, indexable=False))
    pages.append(page(unknown_url, family="standard", role="utility"))

    fixes = [fix(f"meta-{index:02d}", product_urls[index]) for index in range(37)]
    fixes.append(fix("zz-soft404", product_urls[37], rule="soft_404_active", category="correctness"))
    fixes.append(fix("zero-reach", zero_url, indexable_affected=0))
    fixes.append(fix("unknown-reach", unknown_url, family="standard"))

    review = {
        "cleaned_fixes": fixes,
        "health_score": 88,
        "health_score_status": "available",
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
        "crawled_pages": pages,
        "pages_found": len(pages),
        "pages_crawled": len(pages),
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
        "request_id": "request-stage3-v7-ranked",
        "idempotency_key": "request-stage3-v7-ranked",
        "attempt_count": 1,
    }
    envelope = build_completion_envelope(scan_record, scan_result, integrated, SECRET)
    print(json.dumps({
        "secret": SECRET,
        "identity_version": IDENTITY_VERSION,
        "scan_id": SCAN_ID,
        "owner_id": OWNER_ID,
        "project_id": PROJECT_ID,
        "envelope": envelope,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
