from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from app.scan_comparison_v8_inputs import (
    SCAN_COMPARISON_V8_INPUT_BINDING_VERSION,
    build_v8_bound_scan_comparison_transport_v1,
    build_v8_bound_scan_comparison_v1,
    validate_v8_scan_comparison_input_binding_v1,
)

FIXTURE = Path(__file__).parent / "fixtures" / "funbooker_rescan_comparison_v1.json"


def production_inputs():
    fixture = json.loads(FIXTURE.read_text())
    previous_scan = {
        "id": fixture["previous"]["scan_id"],
        "scan_id": fixture["previous"]["scan_id"],
        "fix_list_id": fixture["previous"]["fix_list_id"],
        "health_score": fixture["previous"]["health_score"],
        "pages_retained": fixture["previous"]["pages_checked"],
    }
    current_scan = {
        "id": fixture["current"]["scan_id"],
        "scan_id": fixture["current"]["scan_id"],
        "previous_scan_id": fixture["current"]["previous_scan_id"],
        "fix_list_id": fixture["current"]["fix_list_id"],
        "health_score": fixture["current"]["health_score"],
        "pages_retained": fixture["current"]["pages_checked"],
    }
    previous_fix_list = {
        "id": fixture["previous"]["fix_list_id"],
        "scan_run_id": fixture["previous"]["scan_id"],
        "health_score": fixture["previous"]["health_score"],
        "total_fixes": fixture["previous"]["repair_count"],
    }
    current_fix_list = {
        "id": fixture["current"]["fix_list_id"],
        "scan_run_id": fixture["current"]["scan_id"],
        "health_score": fixture["current"]["health_score"],
        "total_fixes": fixture["current"]["repair_count"],
    }
    previous_fixes = [
        {
            **deepcopy(item),
            "scan_run_id": fixture["previous"]["scan_id"],
            "fix_list_id": fixture["previous"]["fix_list_id"],
        }
        for item in fixture["previous_repairs"]
    ]
    current_fixes = [
        {
            **deepcopy(item),
            "scan_run_id": fixture["current"]["scan_id"],
            "fix_list_id": fixture["current"]["fix_list_id"],
        }
        for item in fixture["current_repairs"]
    ]
    return fixture, {
        "previous_scan": previous_scan,
        "current_scan": current_scan,
        "previous_fix_list": previous_fix_list,
        "current_fix_list": current_fix_list,
        "previous_fixes": previous_fixes,
        "current_fixes": current_fixes,
        "current_pages": [],
    }


def receipt(scan_id: str):
    return {
        "state": "verified",
        "scan_id": scan_id,
        "authority_seal_version": "standard_review_snapshot_hmac_identity_v1",
        "authority_proof_fingerprint": "a" * 64,
    }


def test_v8_input_binding_version_is_explicit():
    assert SCAN_COMPARISON_V8_INPUT_BINDING_VERSION == "scan_comparison_v8_input_binding_v1"


def test_real_funbooker_shape_binds_exact_rows_and_remains_fail_closed():
    fixture, inputs = production_inputs()
    binding = build_v8_bound_scan_comparison_v1(**inputs)
    comparison = binding["comparison"]

    assert binding["previous_scan_id"] == fixture["previous"]["scan_id"]
    assert binding["current_scan_id"] == fixture["current"]["scan_id"]
    assert binding["previous_fix_count"] == 6
    assert binding["current_fix_count"] == 7
    assert comparison["summary"]["fixed"] == 0
    assert comparison["summary"]["still_detected"] == 0
    assert comparison["summary"]["could_not_verify"] == 6
    assert comparison["summary"]["new_or_came_back"] == 1
    assert comparison["new_or_came_back_repair_fingerprints"] == [
        fixture["production_observations"]["new_h1_reference_fingerprint"]
    ]
    assert comparison["score_sample_context"]["score_delta"] == -3
    assert comparison["score_sample_context"]["sample_size_changed"] is True
    assert comparison["score_sample_context"]["score_direction_claim_allowed"] is False
    assert binding["authority_verified_by_adapter"] is False
    assert binding["requires_upstream_v8_authority_verification"] is True


def test_v8_binding_does_not_mutate_authenticated_inputs():
    _, inputs = production_inputs()
    before = deepcopy(inputs)
    build_v8_bound_scan_comparison_v1(**inputs)
    assert inputs == before


def test_wrong_previous_fix_scan_id_fails_closed_before_comparison():
    _, inputs = production_inputs()
    inputs["previous_fixes"][0]["scan_run_id"] = "another-scan"
    with pytest.raises(ValueError, match="scan_run_id does not match"):
        build_v8_bound_scan_comparison_v1(**inputs)


def test_wrong_current_fix_list_id_fails_closed_before_comparison():
    _, inputs = production_inputs()
    inputs["current_fixes"][0]["fix_list_id"] = inputs["previous_fix_list"]["id"]
    with pytest.raises(ValueError, match="fix_list_id does not match"):
        build_v8_bound_scan_comparison_v1(**inputs)


def test_scan_to_fix_list_reference_mismatch_fails_closed():
    _, inputs = production_inputs()
    inputs["current_scan"]["fix_list_id"] = inputs["previous_fix_list"]["id"]
    with pytest.raises(ValueError, match="current ScanRun"):
        build_v8_bound_scan_comparison_v1(**inputs)


def test_fix_list_to_scan_reference_mismatch_fails_closed():
    _, inputs = production_inputs()
    inputs["previous_fix_list"]["scan_run_id"] = inputs["current_scan"]["scan_id"]
    with pytest.raises(ValueError, match="previous FixList"):
        build_v8_bound_scan_comparison_v1(**inputs)


def test_current_lineage_mismatch_fails_closed():
    _, inputs = production_inputs()
    inputs["current_scan"]["previous_scan_id"] = "another-previous-scan"
    with pytest.raises(ValueError, match="lineage"):
        build_v8_bound_scan_comparison_v1(**inputs)


def test_fix_list_count_mismatch_fails_closed():
    _, inputs = production_inputs()
    inputs["current_fix_list"]["total_fixes"] = 8
    with pytest.raises(ValueError, match="total_fixes"):
        build_v8_bound_scan_comparison_v1(**inputs)


def test_scan_and_fix_list_score_mismatch_fails_closed_without_recompute():
    _, inputs = production_inputs()
    inputs["current_fix_list"]["health_score"] = 73
    with pytest.raises(ValueError, match="health scores disagree"):
        build_v8_bound_scan_comparison_v1(**inputs)


def test_integral_base44_numeric_counts_are_accepted_without_recomputation():
    _, inputs = production_inputs()
    inputs["previous_fix_list"]["total_fixes"] = 6.0
    inputs["current_fix_list"]["total_fixes"] = 7.0
    inputs["previous_scan"]["pages_retained"] = 126.0
    inputs["current_scan"]["pages_retained"] = 139.0
    binding = build_v8_bound_scan_comparison_v1(**inputs)
    assert binding["comparison"]["score_sample_context"]["previous_pages_checked"] == 126
    assert binding["comparison"]["score_sample_context"]["current_pages_checked"] == 139
    assert binding["recomputes_score"] is False


def test_serialized_binding_validation_rejects_count_tampering():
    _, inputs = production_inputs()
    binding = build_v8_bound_scan_comparison_v1(**inputs)
    binding["previous_fix_count"] = 5
    with pytest.raises(ValueError, match="previous_fix_count"):
        validate_v8_scan_comparison_input_binding_v1(binding)


def test_serialized_binding_cannot_claim_authority_verification():
    _, inputs = production_inputs()
    binding = build_v8_bound_scan_comparison_v1(**inputs)
    binding["authority_verified_by_adapter"] = True
    with pytest.raises(ValueError, match="cannot claim"):
        validate_v8_scan_comparison_input_binding_v1(binding)


def test_v8_transport_requires_exact_scan_bound_upstream_receipts():
    _, inputs = production_inputs()
    binding = build_v8_bound_scan_comparison_v1(**inputs)
    transport = build_v8_bound_scan_comparison_transport_v1(
        binding,
        previous_authority_receipt=receipt(binding["previous_scan_id"]),
        current_authority_receipt=receipt(binding["current_scan_id"]),
    )
    assert transport["previous_scan_id"] == binding["previous_scan_id"]
    assert transport["current_scan_id"] == binding["current_scan_id"]
    assert transport["customer_projection_authorized"] is False
    assert transport["authority_created_or_modified"] is False


def test_v8_transport_rejects_cross_scan_authority_receipt():
    _, inputs = production_inputs()
    binding = build_v8_bound_scan_comparison_v1(**inputs)
    with pytest.raises(ValueError, match="scan_id does not match"):
        build_v8_bound_scan_comparison_transport_v1(
            binding,
            previous_authority_receipt=receipt(binding["current_scan_id"]),
            current_authority_receipt=receipt(binding["current_scan_id"]),
        )
