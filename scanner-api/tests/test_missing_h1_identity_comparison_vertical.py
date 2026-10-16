from app.missing_h1_contract import (
    MISSING_H1_COMPARISON_PROFILE_VERSION,
    MISSING_H1_REMEDIATION_FAMILY,
    MISSING_H1_REPAIR_SURFACE,
    MISSING_H1_RULE_DEFINITION_VERSION,
    build_missing_h1_comparison_evidence,
    missing_h1_contract_fields,
)
from app.repair_identity import annotate_repair_identity, compare_repair_runs
from app.scan_comparison import build_scan_comparison_v1

EVIDENCE = "evidence_url_identity_v2_published_route"


def h1_fix(*, fingerprint_override=None, stable=True):
    fix = {
        "fix_id": "h1",
        "rule": "missing_h1",
        "category": "thin_content",
        "page_url": "https://example.com/page",
        "affected_pages": ["https://example.com/page"],
        "evidence_url_identity_version": EVIDENCE,
        "rule_definition_version": MISSING_H1_RULE_DEFINITION_VERSION,
        "comparison_profile_version": MISSING_H1_COMPARISON_PROFILE_VERSION,
    }
    if stable:
        fix.update(missing_h1_contract_fields())
    annotated = annotate_repair_identity(fix)
    if fingerprint_override is not None:
        annotated["repair_fingerprint"] = fingerprint_override
    return annotated


def contract():
    return {
        "evidence_url_identity_version": EVIDENCE,
        "rule_definition_version": MISSING_H1_RULE_DEFINITION_VERSION,
        "comparison_profile_version": MISSING_H1_COMPARISON_PROFILE_VERSION,
    }


def page(*, finding_present=False, with_rule_evidence=True):
    result = {
        "url": "https://example.com/page",
        "status_code": 200,
        "content_type": "text/html",
        "page_evidence_class": "usable_html",
        "indexable": True,
    }
    if with_rule_evidence:
        result["comparison_rule_evaluation"] = {
            "rule": "missing_h1",
            "rule_definition_version": MISSING_H1_RULE_DEFINITION_VERSION,
            "comparison_profile_version": MISSING_H1_COMPARISON_PROFILE_VERSION,
            "evaluated": True,
            "applicable": True,
            "finding_present": finding_present,
        }
    return result


def test_missing_h1_contract_is_stable_and_copy_independent():
    left = annotate_repair_identity({**h1_fix(), "recommended_value": "Add one H1"})
    right = annotate_repair_identity({**h1_fix(), "recommended_value": "Use a primary heading"})
    assert left["repair_identity_stable"] is True
    assert right["repair_identity_stable"] is True
    assert left["repair_fingerprint"] == right["repair_fingerprint"]
    assert left["repair_surface"] == MISSING_H1_REPAIR_SURFACE
    assert left["remediation_family"] == MISSING_H1_REMEDIATION_FAMILY


def test_signed_rule_evidence_builder_records_present_absent_and_unavailable_pages():
    evidence = build_missing_h1_comparison_evidence(
        [
            {"url": "https://example.com/missing", "status_code": 200, "content_type": "text/html",
             "page_evidence_class": "usable_html", "h1_count": 0, "indexable": True},
            {"url": "https://example.com/fixed", "status_code": 200, "content_type": "text/html",
             "page_evidence_class": "usable_html", "h1_count": 1, "indexable": True},
            {"url": "https://example.com/blocked", "status_code": 403, "content_type": "text/html",
             "page_evidence_class": "failed_access", "h1_count": 0},
        ],
        scan_origin="https://example.com",
        identity_version=EVIDENCE,
    )
    assert evidence["observation_count"] == 3
    assert evidence["evaluated_page_count"] == 2
    assert evidence["finding_present_count"] == 1
    assert evidence["finding_absent_count"] == 1
    by_url = {row["page_url"]: row for row in evidence["observations"]}
    assert by_url["https://example.com/missing"]["finding_present"] is True
    assert by_url["https://example.com/fixed"]["finding_present"] is False
    assert by_url["https://example.com/blocked"]["evaluated"] is False
    assert by_url["https://example.com/blocked"]["finding_present"] is None


def test_stable_previous_plus_provisional_current_same_reference_can_never_be_fixed():
    previous = h1_fix()
    current = h1_fix(stable=False, fingerprint_override=previous["repair_fingerprint"])
    result = compare_repair_runs(
        previous,
        [current],
        [page(finding_present=False)],
        contract(),
        previous_scan_origin="https://example.com",
        scan_origin="https://example.com",
    )
    assert result["state"] == "could_not_verify"
    assert result["comparison_contract_state"] == "current_fix_identity_conflict"


def test_stable_previous_plus_provisional_current_overlap_can_never_be_fixed_even_without_reference():
    previous = h1_fix()
    current = h1_fix(stable=False)
    current.pop("repair_fingerprint", None)
    result = compare_repair_runs(
        previous,
        [current],
        [page(finding_present=False)],
        contract(),
        previous_scan_origin="https://example.com",
        scan_origin="https://example.com",
    )
    assert result["state"] == "could_not_verify"
    assert result["comparison_contract_state"] == "current_fix_identity_conflict"


def test_stable_missing_h1_is_still_detected_when_same_stable_identity_remains():
    previous = h1_fix()
    current = h1_fix()
    result = compare_repair_runs(
        previous,
        [current],
        [page(finding_present=True)],
        contract(),
        previous_scan_origin="https://example.com",
        scan_origin="https://example.com",
    )
    assert result["state"] == "still_detected"


def test_missing_h1_becomes_verified_fixed_only_with_authenticated_absent_rule_evaluation():
    result = compare_repair_runs(
        h1_fix(),
        [],
        [page(finding_present=False)],
        contract(),
        previous_scan_origin="https://example.com",
        scan_origin="https://example.com",
    )
    assert result["state"] == "verified_fixed"
    assert "authenticated originating-rule evidence no longer detected" in result["reason"]


def test_page_reobservation_without_originating_rule_evaluation_is_not_fixed():
    result = compare_repair_runs(
        h1_fix(),
        [],
        [page(with_rule_evidence=False)],
        contract(),
        previous_scan_origin="https://example.com",
        scan_origin="https://example.com",
    )
    assert result["state"] == "could_not_verify"
    assert result["rule_evidence_gaps"]


def test_rule_evidence_that_still_detects_issue_cannot_be_fixed_if_repair_population_is_missing():
    result = compare_repair_runs(
        h1_fix(),
        [],
        [page(finding_present=True)],
        contract(),
        previous_scan_origin="https://example.com",
        scan_origin="https://example.com",
    )
    assert result["state"] == "could_not_verify"
    assert result["comparison_contract_state"] == "current_repair_population_conflict"


def test_missing_h1_evidence_builder_excludes_cross_origin_pages():
    evidence = build_missing_h1_comparison_evidence(
        [
            {"url": "https://example.com/local", "status_code": 200, "content_type": "text/html",
             "page_evidence_class": "usable_html", "h1_count": 1},
            {"url": "https://other.example/foreign", "status_code": 200, "content_type": "text/html",
             "page_evidence_class": "usable_html", "h1_count": 1},
        ],
        scan_origin="https://example.com",
        identity_version=EVIDENCE,
    )
    assert evidence["observation_count"] == 1
    assert evidence["observations"][0]["page_url"] == "https://example.com/local"


def test_h1_page_evidence_cannot_verify_an_unrelated_repair_fixed():
    previous = annotate_repair_identity({
        "fix_id": "meta",
        "rule": "missing_meta_description",
        "category": "meta_description",
        "page_url": "https://example.com/page",
        "affected_pages": ["https://example.com/page"],
        "repair_surface": "cms_meta_description_field",
        "remediation_family": "write_meta_description",
        "evidence_url_identity_version": EVIDENCE,
    })
    result = build_scan_comparison_v1(
        previous_scan_id="previous",
        current_scan_id="current",
        current_previous_scan_id="previous",
        previous_fixes=[previous],
        current_fixes=[],
        current_pages=[page(finding_present=False)],
        current_contract={
            "evidence_url_identity_version": EVIDENCE,
            "rules": {
                "missing_h1": {
                    "rule_definition_version": MISSING_H1_RULE_DEFINITION_VERSION,
                    "comparison_profile_version": MISSING_H1_COMPARISON_PROFILE_VERSION,
                }
            },
        },
        previous_score=80,
        current_score=80,
        previous_pages_checked=1,
        current_pages_checked=1,
        previous_scan_origin="https://example.com",
        current_scan_origin="https://example.com",
    )
    assert result["summary"]["fixed"] == 0
    assert result["summary"]["could_not_verify"] == 1
