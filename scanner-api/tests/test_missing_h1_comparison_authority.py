from copy import deepcopy

import pytest

from app.authority_seal import create_authority_seal
from app.missing_h1_contract import (
    MISSING_H1_COMPARISON_EVIDENCE_VERSION,
    MISSING_H1_COMPARISON_PROFILE_VERSION,
    MISSING_H1_REMEDIATION_FAMILY,
    MISSING_H1_REPAIR_SURFACE,
    MISSING_H1_RULE_DEFINITION_VERSION,
)
from app.repair_identity import REPAIR_IDENTITY_VERSION, build_repair_identity
from app.scan_comparison_authority import (
    build_authenticated_scan_comparison_v1,
    build_scan_comparison_lineage_v1,
)

KEY = "missing-h1-authority-test-key"
AUTHORITY = "standard_review_snapshot_hmac_identity_v1"
EVIDENCE = "evidence_url_identity_v2_published_route"


def repair(fix_id="h1-old"):
    result = {
        "fix_id": fix_id,
        "rule": "missing_h1",
        "category": "thin_content",
        "page_scope": "sitewide",
        "page_url": "https://example.com/page",
        "affected_pages": ["https://example.com/page"],
        "repair_surface": MISSING_H1_REPAIR_SURFACE,
        "remediation_family": MISSING_H1_REMEDIATION_FAMILY,
        "rule_definition_version": MISSING_H1_RULE_DEFINITION_VERSION,
        "comparison_profile_version": MISSING_H1_COMPARISON_PROFILE_VERSION,
        "verification_state": "confirmed",
        "raw_finding": {"published_evidence": {"evidence_url_identity_version": EVIDENCE}},
    }
    identity = build_repair_identity(result)
    result.update(
        repair_identity_version=REPAIR_IDENTITY_VERSION,
        repair_identity_state=identity["state"],
        repair_identity_stable=identity["stable"],
        repair_fingerprint=identity["fingerprint"],
    )
    return result


def evidence(*, finding_present):
    count = 0 if finding_present else 1
    return {
        "version": MISSING_H1_COMPARISON_EVIDENCE_VERSION,
        "rule": "missing_h1",
        "rule_definition_version": MISSING_H1_RULE_DEFINITION_VERSION,
        "comparison_profile_version": MISSING_H1_COMPARISON_PROFILE_VERSION,
        "evidence_url_identity_version": EVIDENCE,
        "observation_count": 1,
        "evaluated_page_count": 1,
        "finding_present_count": 1 if finding_present else 0,
        "finding_absent_count": 0 if finding_present else 1,
        "observations": [{
            "page_url": "https://example.com/page",
            "status_code": 200,
            "content_type": "text/html",
            "page_evidence_class": "usable_html",
            "indexable": True,
            "robots": "",
            "h1_count": count,
            "evaluated": True,
            "applicable": True,
            "finding_present": finding_present,
        }],
    }


def snapshot(scan_id, when, fixes, *, comparison_evidence=None):
    scan = {
        "status": "complete",
        "release_gate_eligible": True,
        "score_is_provisional": False,
        "evidence_quality_blocking": False,
        "website_url": "https://example.com/",
        "normalized_domain": "example.com",
        "requested_origin": "https://example.com",
        "scope_type": "",
        "requested_path_prefix": "",
        "completed_at": when,
        "health_score": 72,
        "pages_crawled": 1,
    }
    if comparison_evidence is not None:
        scan["comparison_evidence"] = comparison_evidence
    return {
        "version": AUTHORITY,
        "sealed_at": when,
        "owner_user_id": "owner",
        "scan_id": scan_id,
        "project_id": "project",
        "normalized_domain": "example.com",
        "release_fingerprint": "01ebe8e90df1e6bd",
        "scan": scan,
        "fix_list": {
            "is_authoritative": True,
            "score_is_provisional": False,
            "total_fixes": len(fixes),
            "health_score": 72,
        },
        "recommendations": fixes,
    }


def pair(*, current_fixes, current_evidence):
    result = {
        "previous_snapshot": snapshot("previous", "2026-09-22T10:00:00Z", [repair()]),
        "current_snapshot": snapshot(
            "current",
            "2026-09-23T10:00:00Z",
            current_fixes,
            comparison_evidence=current_evidence,
        ),
        "expected_owner_user_id": "owner",
        "expected_project_id": "project",
        "expected_current_scan_id": "current",
        "signing_key": KEY,
    }
    for side in ("previous", "current"):
        result[f"{side}_proof"] = create_authority_seal(result[f"{side}_snapshot"], KEY)
    return result


def compare(result):
    lineage = build_scan_comparison_lineage_v1(current_previous_scan_id="previous", **result)
    return build_authenticated_scan_comparison_v1(lineage_artifact=lineage, **result)


def test_authenticated_missing_h1_rule_evidence_can_verify_fixed():
    result = compare(pair(current_fixes=[], current_evidence=evidence(finding_present=False)))
    assert result["current_pages_available"] is True
    assert result["comparison"]["summary"]["fixed"] == 1
    assert result["comparison"]["summary"]["could_not_verify"] == 0


def test_authenticated_stable_missing_h1_current_repair_is_still_detected():
    result = compare(pair(current_fixes=[repair("h1-new")], current_evidence=evidence(finding_present=True)))
    assert result["comparison"]["summary"]["still_detected"] == 1
    assert result["comparison"]["summary"]["fixed"] == 0


def test_rule_evidence_detecting_issue_without_current_stable_repair_fails_closed():
    result = compare(pair(current_fixes=[], current_evidence=evidence(finding_present=True)))
    assert result["comparison"]["summary"]["fixed"] == 0
    assert result["comparison"]["summary"]["could_not_verify"] == 1


def test_comparison_evidence_tampering_breaks_original_authority_proof():
    result = pair(current_fixes=[], current_evidence=evidence(finding_present=False))
    lineage = build_scan_comparison_lineage_v1(current_previous_scan_id="previous", **result)
    result["current_snapshot"]["scan"]["comparison_evidence"]["observations"][0]["h1_count"] = 0
    with pytest.raises(ValueError, match="proof verification"):
        build_authenticated_scan_comparison_v1(lineage_artifact=lineage, **result)


def test_authentic_but_internally_contradictory_comparison_evidence_is_rejected():
    bad = evidence(finding_present=False)
    bad["finding_absent_count"] = 0
    result = pair(current_fixes=[], current_evidence=bad)
    with pytest.raises(ValueError, match="count mismatch"):
        compare(result)


def test_historical_current_snapshot_without_rule_evidence_remains_could_not_verify():
    result = compare(pair(current_fixes=[], current_evidence=None))
    assert result["current_pages_available"] is False
    assert result["comparison"]["summary"]["fixed"] == 0
    assert result["comparison"]["summary"]["could_not_verify"] == 1
