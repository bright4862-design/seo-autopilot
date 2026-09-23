from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from app.repair_identity import build_repair_identity
from app.scan_comparison import build_scan_comparison_v1
from app.scan_comparison_integrity import (
    SCAN_COMPARISON_INTEGRITY_VERSION,
    build_validated_customer_scan_comparison_presentation,
    build_validated_scan_comparison_transport_v1,
    validate_scan_comparison_v1,
)

FIXTURE = Path(__file__).parent / "fixtures" / "funbooker_rescan_comparison_v1.json"


def page(url: str):
    return {"url": url, "status_code": 200, "content_type": "text/html", "indexable": True}


def repair(rule: str, finding_id: str, page_url: str):
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


def stable_comparison():
    previous = [
        repair("missing_meta_description", "old-1", "/a"),
        repair("missing_title", "old-2", "/b"),
        repair("missing_canonical", "old-3", "/c"),
        repair("missing_alt_text", "old-4", "/d"),
        repair("internal_link_redirect", "old-5", "/e"),
        repair("missing_schema", "old-6", "/f"),
    ]
    current = []
    for index, prior in enumerate(previous, start=1):
        item = deepcopy(prior)
        item["finding_id"] = f"new-{index}"
        current.append(item)
    current.append(repair("missing_h1", "new-h1", "/g"))
    return build_scan_comparison_v1(
        previous_scan_id="scan-old",
        current_scan_id="scan-new",
        current_previous_scan_id="scan-old",
        previous_fixes=previous,
        current_fixes=current,
        current_pages=[page(f"/{letter}") for letter in "abcdefg"],
        previous_score=75,
        current_score=72,
        previous_pages_checked=126,
        current_pages_checked=139,
    )


def production_funbooker_comparison():
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


def receipt(scan_id: str):
    return {
        "state": "verified",
        "scan_id": scan_id,
        "authority_seal_version": "standard_review_snapshot_hmac_v8",
        "authority_proof_fingerprint": "a" * 64,
    }


def test_integrity_contract_version_is_explicit():
    assert SCAN_COMPARISON_INTEGRITY_VERSION == "scan_comparison_integrity_v1"


def test_validator_accepts_exact_generated_contract_without_mutation():
    comparison = stable_comparison()
    before = deepcopy(comparison)
    assert validate_scan_comparison_v1(comparison) is comparison
    assert comparison == before


def test_validated_presentation_preserves_sample_scope_warning():
    comparison = stable_comparison()
    presentation = build_validated_customer_scan_comparison_presentation(comparison)
    assert "Pages checked: 126 in the previous scan; 139 in this scan." in presentation["sample_line"]
    assert "cannot tell you whether your site improved or got worse" in presentation["score_caution"]
    assert presentation["overall_improvement_or_regression_claim"] is None


def test_validated_transport_preserves_upstream_authority_boundary():
    comparison = stable_comparison()
    transport = build_validated_scan_comparison_transport_v1(
        comparison,
        previous_authority_receipt=receipt(comparison["previous_scan_id"]),
        current_authority_receipt=receipt(comparison["current_scan_id"]),
    )
    assert transport["customer_projection_authorized"] is False
    assert transport["authority_created_or_modified"] is False


def test_presentation_fails_closed_on_tampered_fixed_summary():
    comparison = stable_comparison()
    comparison["summary"]["fixed"] = 1
    with pytest.raises(ValueError, match="summary.fixed"):
        build_validated_customer_scan_comparison_presentation(comparison)


def test_validator_fails_closed_on_row_state_summary_contradiction():
    comparison = stable_comparison()
    comparison["repair_comparisons"][0]["summary_state"] = "fixed"
    with pytest.raises(ValueError, match="summary_state"):
        validate_scan_comparison_v1(comparison)


def test_validator_fails_closed_on_serialized_lineage_tampering():
    comparison = stable_comparison()
    comparison["current_previous_scan_id"] = "different-previous-scan"
    with pytest.raises(ValueError, match="lineage"):
        validate_scan_comparison_v1(comparison)


def test_validator_requires_unique_deterministic_candidate_fingerprints():
    comparison = stable_comparison()
    fingerprint = comparison["new_or_came_back_repair_fingerprints"][0]
    comparison["new_or_came_back_repair_fingerprints"] = [fingerprint, fingerprint]
    comparison["summary"]["new_or_came_back"] = 2
    with pytest.raises(ValueError, match="unique and deterministic"):
        validate_scan_comparison_v1(comparison)


def test_validator_rejects_candidate_fingerprint_already_present_before():
    comparison = stable_comparison()
    previous_fingerprint = comparison["repair_comparisons"][0]["repair_fingerprint"]
    comparison["new_or_came_back_repair_fingerprints"] = [previous_fingerprint]
    with pytest.raises(ValueError, match="already exists in previous repairs"):
        validate_scan_comparison_v1(comparison)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("score_delta", -4, "score delta"),
        ("sample_size_changed", False, "sample-size flag"),
        ("score_direction_claim_allowed", True, "score direction claims"),
        ("score_context_state", "score_delta_descriptive_only", "score context state"),
    ],
)
def test_validator_rejects_tampered_score_sample_context(field, value, message):
    comparison = stable_comparison()
    comparison["score_sample_context"][field] = value
    with pytest.raises(ValueError, match=message):
        validate_scan_comparison_v1(comparison)


@pytest.mark.parametrize("field", ["creates_customer_fixes", "recomputes_score", "mutates_historical_rows"])
def test_validator_keeps_non_authority_guard_flags_false(field):
    comparison = stable_comparison()
    comparison[field] = True
    with pytest.raises(ValueError, match=field):
        validate_scan_comparison_v1(comparison)


def test_transport_rejects_internally_inconsistent_comparison_before_authority_binding():
    comparison = stable_comparison()
    comparison["summary"]["still_detected"] -= 1
    with pytest.raises(ValueError, match="summary.still_detected"):
        build_validated_scan_comparison_transport_v1(
            comparison,
            previous_authority_receipt=receipt(comparison["previous_scan_id"]),
            current_authority_receipt=receipt(comparison["current_scan_id"]),
        )


def test_production_funbooker_fixture_validates_while_remaining_fail_closed():
    fixture, comparison = production_funbooker_comparison()
    validate_scan_comparison_v1(comparison)
    assert comparison["summary"]["fixed"] == 0
    assert comparison["summary"]["still_detected"] == 0
    assert comparison["summary"]["could_not_verify"] == fixture["previous"]["repair_count"] == 6
    assert comparison["new_or_came_back_repair_fingerprints"] == [
        fixture["production_observations"]["new_h1_reference_fingerprint"]
    ]
