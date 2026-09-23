from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from app.repair_identity import build_repair_identity
from app.scan_comparison import build_scan_comparison_v1
from app.scan_comparison_integrity import (
    build_validated_customer_scan_comparison_presentation,
    validate_scan_comparison_v1,
)

FIXTURE = Path(__file__).parent / "fixtures" / "funbooker_rescan_comparison_v1.json"


def stable_repair(rule: str, finding_id: str, page_url: str) -> dict:
    item = {
        "finding_id": finding_id,
        "rule": rule,
        "category": rule,
        "page_scope": "page",
        "page_template_family": "activity",
        "repair_surface": f"surface_{rule}",
        "remediation_family": f"remediate_{rule}",
        "affected_pages": [page_url],
    }
    item["repair_fingerprint"] = build_repair_identity(item)["fingerprint"]
    return item


def build_comparison(previous: list[dict], current: list[dict]) -> dict:
    return build_scan_comparison_v1(
        previous_scan_id="scan-old",
        current_scan_id="scan-new",
        current_previous_scan_id="scan-old",
        previous_fixes=previous,
        current_fixes=current,
        current_pages=[],
        previous_score=75,
        current_score=72,
        previous_pages_checked=126,
        current_pages_checked=139,
    )


def production_funbooker_comparison() -> tuple[dict, dict]:
    fixture = json.loads(FIXTURE.read_text())
    comparison = build_scan_comparison_v1(
        previous_scan_id=fixture["previous"]["scan_id"],
        current_scan_id=fixture["current"]["scan_id"],
        current_previous_scan_id=fixture["current"]["previous_scan_id"],
        previous_fixes=deepcopy(fixture["previous_repairs"]),
        current_fixes=deepcopy(fixture["current_repairs"]),
        current_pages=[],
        previous_score=fixture["previous"]["health_score"],
        current_score=fixture["current"]["health_score"],
        previous_pages_checked=fixture["previous"]["pages_checked"],
        current_pages_checked=fixture["current"]["pages_checked"],
    )
    return fixture, comparison


def test_current_reference_population_is_deterministic_and_summary_bound():
    current = [
        stable_repair("missing_title", "finding-z", "/z"),
        stable_repair("missing_meta_description", "finding-a", "/a"),
    ]
    comparison = build_comparison([], current)
    references = comparison["current_repair_references"]
    assert references == sorted(
        references,
        key=lambda item: (
            item["repair_fingerprint"] or "~",
            item["finding_id"],
            item["repair_fingerprint_source"],
            item["repair_identity_stable"],
        ),
    )
    assert comparison["summary"]["current_repairs_total"] == 2
    assert comparison["summary"]["current_repairs_with_stable_verification_identity"] == 2
    validate_scan_comparison_v1(comparison)


@pytest.mark.parametrize(
    "field",
    [
        "current_repairs_without_reference_fingerprint",
        "current_repairs_with_stable_verification_identity",
    ],
)
def test_funbooker_rejects_current_identity_coverage_summary_tampering(field):
    _, comparison = production_funbooker_comparison()
    assert comparison["summary"][field] == 0
    comparison["summary"][field] = 1
    with pytest.raises(ValueError, match=f"summary.{field}"):
        validate_scan_comparison_v1(comparison)


def test_funbooker_rejects_injected_candidate_not_present_in_current_repairs():
    _, comparison = production_funbooker_comparison()
    comparison["new_or_came_back_repair_fingerprints"] = ["f" * 24]
    with pytest.raises(ValueError, match="candidate fingerprints contradict current repair references"):
        validate_scan_comparison_v1(comparison)


def test_funbooker_rejects_omitted_h1_candidate():
    _, comparison = production_funbooker_comparison()
    comparison["new_or_came_back_repair_fingerprints"] = []
    comparison["summary"]["new_or_came_back"] = 0
    with pytest.raises(ValueError, match="candidate fingerprints contradict current repair references"):
        validate_scan_comparison_v1(comparison)


def test_funbooker_rejects_continuity_flag_tampering():
    _, comparison = production_funbooker_comparison()
    row = next(item for item in comparison["repair_comparisons"] if item["repair_fingerprint"] == "8ed09e861fa8d04bc18ee355")
    assert row["same_reference_fingerprint_observed"] is True
    assert row["current_finding_id"] == "finding_191c17db74"
    row["same_reference_fingerprint_observed"] = False
    row["current_finding_id"] = ""
    with pytest.raises(ValueError, match="same_reference_fingerprint_observed"):
        validate_scan_comparison_v1(comparison)


def test_funbooker_rejects_current_finding_id_tampering_when_fingerprint_survives():
    _, comparison = production_funbooker_comparison()
    row = next(item for item in comparison["repair_comparisons"] if item["repair_fingerprint"] == "e86f5cafadbb215bc8b17984")
    assert row["current_finding_id"] == "finding_d364eb0440"
    row["current_finding_id"] = "finding_forged"
    with pytest.raises(ValueError, match="current_finding_id"):
        validate_scan_comparison_v1(comparison)


def test_funbooker_current_reference_order_tampering_fails_closed():
    _, comparison = production_funbooker_comparison()
    comparison["current_repair_references"].reverse()
    with pytest.raises(ValueError, match="current_repair_references are not in deterministic"):
        validate_scan_comparison_v1(comparison)


def test_provisional_computed_identity_cannot_be_promoted_to_reference_by_serialization():
    comparison = build_comparison(
        [],
        [{"finding_id": "finding-provisional", "rule": "missing_title", "category": "meta_title"}],
    )
    reference = comparison["current_repair_references"][0]
    assert reference["repair_fingerprint"] == ""
    assert reference["repair_identity_stable"] is False
    reference["repair_fingerprint"] = "a" * 24
    with pytest.raises(ValueError, match="provisional computed fingerprint"):
        validate_scan_comparison_v1(comparison)


def test_funbooker_exact_current_references_preserve_real_before_after_shape():
    fixture, comparison = production_funbooker_comparison()
    validate_scan_comparison_v1(comparison)
    references = comparison["current_repair_references"]
    assert len(references) == fixture["current"]["repair_count"] == 7
    assert {item["repair_fingerprint"] for item in references} == {
        item["repair_fingerprint"] for item in fixture["current_repairs"]
    }
    assert comparison["summary"]["fixed"] == 0
    assert comparison["summary"]["still_detected"] == 0
    assert comparison["summary"]["could_not_verify"] == 6
    assert comparison["new_or_came_back_repair_fingerprints"] == [
        fixture["production_observations"]["new_h1_reference_fingerprint"]
    ]


def test_funbooker_score_change_remains_descriptive_when_sample_scope_changes():
    _, comparison = production_funbooker_comparison()
    presentation = build_validated_customer_scan_comparison_presentation(comparison)
    assert presentation["score_line"] == "Health score changed from 75 to 72."
    assert presentation["sample_line"] == "The assessed sample was 126 pages before and 139 pages now."
    assert "does not prove the site improved or regressed" in presentation["score_caution"]
    assert presentation["score_direction_claim_allowed"] is False
    assert presentation["overall_improvement_or_regression_claim"] is None
