from app.repair_priority_calibration import (
    REPAIR_PRIORITY_CALIBRATION_VERSION,
    annotate_calibrated_repair_priority,
    calibrated_evidence_class,
    technical_base_severity,
)
from app.repair_shadow_calibration import build_calibrated_shadow_review_analysis


def _page(path: str, *, family: str = "activity_detail", important: bool = False):
    return {
        "url": f"https://example.com{path}",
        "final_url": f"https://example.com{path}",
        "status_code": 200,
        "content_type": "text/html",
        "page_template_family": family,
        "indexable": True,
        "is_important_business_page": important,
    }


def test_legacy_reach_inflated_priority_is_not_reused_as_base_severity():
    metadata = {
        "rule": "meta_description_unusable",
        "category": "meta_description",
        "priority": "critical",  # legacy score can reach critical through breadth
        "primary_defect_class": "metadata",
        "affected_pages": [f"/activity/{i}" for i in range(47)],
        "page_template_family": "activity_detail",
        "confidence_score": 92,
    }

    severity, source = technical_base_severity(metadata)

    assert severity == "medium"
    assert source == "rule_taxonomy"
    result = annotate_calibrated_repair_priority(metadata, [])
    assert result["priority"] == "critical"  # historical field stays untouched
    assert result["base_severity"] == "medium"
    assert result["evidence_class"] == "improvement"
    assert result["action_priority"] == "improve"
    assert result["repair_priority_version"] == REPAIR_PRIORITY_CALIBRATION_VERSION
    assert result["priority_context"]["legacy_priority"] == "critical"


def test_homepage_redirect_chain_outranks_broad_metadata_in_shadow_without_reordering_source():
    metadata = {
        "id": "metadata",
        "fix_id": "metadata",
        "rule": "meta_description_unusable",
        "category": "meta_description",
        "priority": "critical",
        "primary_defect_class": "metadata",
        "affected_pages": [f"/activity/{i}" for i in range(47)],
        "page_template_family": "activity_detail",
        "confidence_score": 92,
    }
    redirect = {
        "id": "redirect",
        "fix_id": "redirect",
        "rule": "redirect_chain",
        "category": "indexability",
        "priority": "critical",
        "primary_defect_class": "structural",
        "affected_pages": ["/"],
        "page_template_family": "homepage",
        "confidence_score": 94,
        "evidence_status": "confirmed",
    }
    pages = [_page("/", family="homepage", important=True)] + [
        _page(f"/activity/{i}") for i in range(47)
    ]
    review = {"cleaned_fixes": [metadata, redirect]}

    analysis = build_calibrated_shadow_review_analysis(review, pages)

    assert [fix["id"] for fix in review["cleaned_fixes"]] == ["metadata", "redirect"]
    assert [fix["id"] for fix in analysis["fixes"]] == ["metadata", "redirect"]
    assert analysis["current_order_preserved"] is True
    assert analysis["priority_divergence"]["order_changed"] is True
    assert analysis["proposed_fixes"][0]["id"] == "redirect"
    assert analysis["proposed_fixes"][0]["base_severity"] == "high"
    assert analysis["proposed_fixes"][0]["action_priority"] == "fix_first"
    assert analysis["proposed_fixes"][1]["base_severity"] == "medium"
    assert analysis["proposed_fixes"][1]["evidence_class"] == "improvement"
    assert analysis["proposed_fixes"][1]["action_priority"] == "improve"


def test_evidence_status_needs_verification_is_not_confirmed_problem():
    finding = {
        "rule": "title_over_pixel_limit",
        "category": "meta_title",
        "priority": "low",
        "evidence_status": "needs_verification",
    }

    assert calibrated_evidence_class(finding) == "improvement"
    result = annotate_calibrated_repair_priority(finding, [])
    assert result["base_severity"] == "low"
    assert result["evidence_class"] == "improvement"
    assert result["action_priority"] == "improve"


def test_potential_orphan_finding_is_review_not_confirmed_fix():
    finding = {
        "rule": "potential_orphan_pages",
        "category": "indexability",
        "priority": "low",
        "evidence_status": "needs_verification",
        "affected_pages": ["/a", "/b", "/c"],
        "page_template_family": "homepage",
    }

    result = annotate_calibrated_repair_priority(finding, [])

    assert result["base_severity"] == "low"
    assert result["evidence_class"] == "opportunity"
    assert result["action_priority"] == "review"


def test_broad_image_alt_gap_stays_improvement_even_if_legacy_priority_is_high():
    finding = {
        "rule": "image_alt_text",
        "category": "image_alt_text",
        "priority": "high",
        "primary_defect_class": "metadata",
        "affected_pages": [f"/locations/{i}" for i in range(60)],
        "page_template_family": "location_landing",
        "confidence_score": 92,
    }

    result = annotate_calibrated_repair_priority(finding, [])

    assert result["priority"] == "high"
    assert result["base_severity"] == "low"
    assert result["evidence_class"] == "improvement"
    assert result["action_priority"] == "improve"


def test_repeated_title_template_stays_low_impact_improvement_not_reach_driven_problem():
    finding = {
        "rule": "duplicate_title_template",
        "category": "duplicate_content",
        "priority": "high",
        "primary_defect_class": "metadata",
        "affected_pages": [f"/guides/{i}" for i in range(70)],
        "page_template_family": "guide_article",
        "confidence_score": 88,
    }

    result = annotate_calibrated_repair_priority(finding, [])

    assert result["base_severity"] == "low"
    assert result["evidence_class"] == "improvement"
    assert result["action_priority"] == "improve"


def test_explicit_technical_severity_still_overrides_shadow_taxonomy():
    finding = {
        "rule": "meta_description_unusable",
        "category": "meta_description",
        "priority": "critical",
        "technical_severity": "high",
    }

    severity, source = technical_base_severity(finding)

    assert severity == "high"
    assert source == "explicit"
