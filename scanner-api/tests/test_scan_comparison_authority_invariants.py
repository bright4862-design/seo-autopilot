from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from app.repair_identity import REPAIR_VERIFICATION_VERSION, build_repair_identity
from app.scan_comparison import build_scan_comparison_v1
from app.scan_comparison_integrity import validate_scan_comparison_v1


FIXTURE = Path(__file__).parent / "fixtures" / "funbooker_rescan_comparison_v1.json"


def page(url: str) -> dict[str, object]:
    return {
        "url": url,
        "status_code": 200,
        "content_type": "text/html",
        "indexable": True,
    }


def stable_repair(*, finding_id: str = "old", page_url: str = "/a") -> dict[str, object]:
    repair: dict[str, object] = {
        "finding_id": finding_id,
        "rule": "missing_title",
        "category": "meta_title",
        "repair_surface": "html_head_title",
        "remediation_family": "replace_title",
        "affected_pages": [page_url],
    }
    repair["repair_fingerprint"] = build_repair_identity(repair)["fingerprint"]
    return repair


def fixed_comparison() -> dict[str, object]:
    previous = stable_repair()
    return build_scan_comparison_v1(
        previous_scan_id="scan-old",
        current_scan_id="scan-new",
        current_previous_scan_id="scan-old",
        previous_fixes=[previous],
        current_fixes=[],
        current_pages=[page("/a")],
        previous_score=80,
        current_score=80,
        previous_pages_checked=1,
        current_pages_checked=1,
    )


def production_funbooker_comparison() -> dict[str, object]:
    fixture = json.loads(FIXTURE.read_text())
    return build_scan_comparison_v1(
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


def test_valid_canonical_verified_fixed_envelope_still_passes_integrity():
    comparison = fixed_comparison()
    row = comparison["repair_comparisons"][0]
    assert row["state"] == "verified_fixed"
    assert row["verification_version"] == REPAIR_VERIFICATION_VERSION
    assert row["previous_affected_pages"] == row["rechecked_pages"] == row["eligible_rechecked_pages"] == 1
    assert validate_scan_comparison_v1(comparison) is comparison


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("repair_identity_stable", False, "stable historical repair identity"),
        ("same_reference_fingerprint_observed", True, "same-fingerprint observation"),
        ("verification_version", "repair_verification_old", "canonical repair verification version"),
        ("previous_affected_pages", 0, "at least one previously affected page"),
        ("rechecked_pages", 0, "every previously affected page"),
        ("eligible_rechecked_pages", 0, "every previously affected page"),
        ("comparison_contract_state", "incomparable", "compatible comparison contract"),
    ],
)
def test_serialized_verified_fixed_cannot_bypass_canonical_authority_invariants(field, value, message):
    comparison = fixed_comparison()
    row = comparison["repair_comparisons"][0]
    row[field] = value
    # Keep the generic page counters internally ordered for mutations whose
    # purpose is to reach the stronger verified-fixed-specific integrity gate.
    if field == "previous_affected_pages":
        row["rechecked_pages"] = 0
        row["eligible_rechecked_pages"] = 0
    elif field == "rechecked_pages":
        row["eligible_rechecked_pages"] = 0
    with pytest.raises(ValueError, match=message):
        validate_scan_comparison_v1(comparison)


def test_still_detected_requires_same_reference_fingerprint_observation():
    previous = stable_repair()
    current = deepcopy(previous)
    current["finding_id"] = "new"
    comparison = build_scan_comparison_v1(
        previous_scan_id="scan-old",
        current_scan_id="scan-new",
        current_previous_scan_id="scan-old",
        previous_fixes=[previous],
        current_fixes=[current],
        current_pages=[page("/a")],
        previous_score=80,
        current_score=80,
        previous_pages_checked=1,
        current_pages_checked=1,
    )
    assert comparison["repair_comparisons"][0]["state"] == "still_detected"
    comparison["repair_comparisons"][0]["same_reference_fingerprint_observed"] = False
    comparison["repair_comparisons"][0]["current_finding_id"] = ""
    with pytest.raises(ValueError, match="requires the same stable repair fingerprint"):
        validate_scan_comparison_v1(comparison)


def test_provisional_current_row_with_same_persisted_reference_fingerprint_fails_closed_before_projection():
    previous = stable_repair()
    fingerprint = previous["repair_fingerprint"]
    current = {
        "finding_id": "new-provisional",
        "rule": "missing_title",
        "category": "meta_title",
        "affected_pages": ["/a"],
        "repair_fingerprint": fingerprint,
        "repair_identity_state": "provisional",
        "repair_identity_stable": False,
    }
    assert build_repair_identity(current)["stable"] is False

    comparison = build_scan_comparison_v1(
        previous_scan_id="scan-old",
        current_scan_id="scan-new",
        current_previous_scan_id="scan-old",
        previous_fixes=[previous],
        current_fixes=[current],
        current_pages=[page("/a")],
        previous_score=80,
        current_score=80,
        previous_pages_checked=1,
        current_pages_checked=1,
    )

    # compare_repair_runs() cannot treat the provisional current row as a stable
    # technical match, but the persisted continuity fingerprint is still visible.
    # The integrity boundary therefore refuses customer projection rather than
    # allowing that contradiction to become a verified-fixed claim.
    row = comparison["repair_comparisons"][0]
    assert row["state"] == "verified_fixed"
    assert row["same_reference_fingerprint_observed"] is True
    with pytest.raises(ValueError, match="same-fingerprint observation"):
        validate_scan_comparison_v1(comparison)


def test_comparison_build_and_validation_leave_historical_inputs_unchanged():
    previous = [stable_repair()]
    current = [deepcopy(previous[0])]
    current[0]["finding_id"] = "new"
    pages = [page("/a")]
    before = deepcopy((previous, current, pages))

    comparison = build_scan_comparison_v1(
        previous_scan_id="scan-old",
        current_scan_id="scan-new",
        current_previous_scan_id="scan-old",
        previous_fixes=previous,
        current_fixes=current,
        current_pages=pages,
        previous_score=80,
        current_score=80,
        previous_pages_checked=1,
        current_pages_checked=1,
    )
    validate_scan_comparison_v1(comparison)

    assert (previous, current, pages) == before
    assert comparison["mutates_historical_rows"] is False


def test_real_funbooker_production_shape_remains_readable_and_fail_closed():
    comparison = production_funbooker_comparison()
    assert validate_scan_comparison_v1(comparison) is comparison
    assert comparison["previous_scan_id"] == "6ab272fc6dfa7f9faf97a90f"
    assert comparison["current_scan_id"] == "6ab314008da962a9f8c58929"
    assert comparison["summary"]["fixed"] == 0
    assert comparison["summary"]["still_detected"] == 0
    assert comparison["summary"]["could_not_verify"] == 6
    assert comparison["summary"]["new_or_came_back"] == 1
    assert comparison["score_sample_context"]["sample_size_changed"] is True
    assert comparison["score_sample_context"]["score_direction_claim_allowed"] is False
