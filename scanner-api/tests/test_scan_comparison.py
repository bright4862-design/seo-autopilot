from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from app.repair_identity import build_repair_identity, compare_repair_runs
from app.scan_comparison import (
    SCAN_COMPARISON_PRESENTATION_VERSION,
    SCAN_COMPARISON_TRANSPORT_VERSION,
    SCAN_COMPARISON_VERSION,
    build_customer_scan_comparison_presentation,
    build_scan_comparison_transport_v1,
    build_scan_comparison_v1,
)

FIXTURE = Path(__file__).parent / "fixtures" / "funbooker_rescan_comparison_v1.json"


def page(url: str, **overrides):
    value = {"url": url, "status_code": 200, "content_type": "text/html", "indexable": True}
    value.update(overrides)
    return value


def repair(
    rule: str,
    *,
    finding_id: str,
    page_url: str,
    state: str = "",
    repair_surface: str | None = None,
    remediation_family: str | None = None,
):
    item = {
        "finding_id": finding_id,
        "rule": rule,
        "category": rule,
        "page_scope": "page",
        "page_template_family": "activity",
        "repair_surface": repair_surface or f"surface_{rule}",
        "remediation_family": remediation_family or f"remediate_{rule}",
        "affected_pages": [page_url],
    }
    if state:
        item["verification_state"] = state
    item["repair_fingerprint"] = build_repair_identity(item)["fingerprint"]
    return item


def funbooker_repairs():
    previous = [
        repair("missing_meta_description", finding_id="old-1", page_url="/a"),
        repair("missing_title", finding_id="old-2", page_url="/b"),
        repair("missing_canonical", finding_id="old-3", page_url="/c"),
        repair("missing_alt_text", finding_id="old-4", page_url="/d"),
        repair("internal_link_redirect", finding_id="old-5", page_url="/e"),
        repair("missing_schema", finding_id="old-6", page_url="/f"),
    ]
    current = []
    for index, prior in enumerate(previous, start=1):
        current_item = deepcopy(prior)
        current_item["finding_id"] = f"new-{index}"
        current.append(current_item)
    current.append(repair("missing_h1", finding_id="new-h1", page_url="/g"))
    return previous, current


def build_funbooker_comparison():
    fixture = json.loads(FIXTURE.read_text())
    previous, current = funbooker_repairs()
    return fixture, build_scan_comparison_v1(
        previous_scan_id=fixture["previous"]["scan_id"],
        current_scan_id=fixture["current"]["scan_id"],
        current_previous_scan_id=fixture["current"]["previous_scan_id"],
        previous_fixes=previous,
        current_fixes=current,
        current_pages=[page(f"/{letter}") for letter in "abcdefg"],
        previous_score=fixture["previous"]["health_score"],
        current_score=fixture["current"]["health_score"],
        previous_pages_checked=fixture["previous"]["pages_checked"],
        current_pages_checked=fixture["current"]["pages_checked"],
    )


def test_canonical_comparator_proves_verified_fixed():
    previous = repair("missing_title", finding_id="old", page_url="/a")
    result = compare_repair_runs(previous, [], [page("/a")])
    assert result["state"] == "verified_fixed"


def test_canonical_comparator_proves_still_detected_even_when_finding_id_changes():
    previous = repair("missing_title", finding_id="old", page_url="/a")
    current = deepcopy(previous)
    current["finding_id"] = "new"
    result = compare_repair_runs(previous, [current], [page("/a")])
    assert result["state"] == "still_detected"
    assert build_repair_identity(previous)["fingerprint"] == build_repair_identity(current)["fingerprint"]


def test_canonical_comparator_proves_came_back_from_previous_verified_fixed_state():
    previous = repair("missing_title", finding_id="old", page_url="/a", state="verified_fixed")
    current = deepcopy(previous)
    current["finding_id"] = "new"
    current.pop("verification_state", None)
    result = compare_repair_runs(previous, [current], [page("/a")])
    assert result["state"] == "came_back"


def test_blocked_evidence_can_never_be_promoted_to_verified_fixed():
    previous = repair("missing_title", finding_id="old", page_url="/a")
    result = compare_repair_runs(
        previous,
        [],
        [page("/a", status_code=403, page_evidence_class="failed_access")],
    )
    assert result["state"] == "could_not_verify"
    assert result["state"] != "verified_fixed"


def test_incomparable_contract_can_never_be_promoted_to_verified_fixed():
    previous = repair("missing_title", finding_id="old", page_url="/a")
    previous["rule_definition_version"] = "missing_title_v1"
    previous["comparison_profile_version"] = "standard150_v1"
    result = compare_repair_runs(
        previous,
        [],
        [page("/a")],
        current_contract={
            "rule_definition_version": "missing_title_v2",
            "comparison_profile_version": "standard150_v1",
        },
    )
    assert result["state"] == "could_not_verify"
    assert result["comparison_contract_state"] == "incomparable"
    assert result["state"] != "verified_fixed"


def test_scan_comparison_v1_requires_exact_lineage():
    previous, current = funbooker_repairs()
    with pytest.raises(ValueError, match="lineage"):
        build_scan_comparison_v1(
            previous_scan_id="scan-old",
            current_scan_id="scan-new",
            current_previous_scan_id="different-old",
            previous_fixes=previous,
            current_fixes=current,
            current_pages=[page("/a")],
            previous_score=75,
            current_score=72,
            previous_pages_checked=126,
            current_pages_checked=139,
        )


def test_scan_comparison_uses_stable_fingerprint_not_finding_id():
    fixture, result = build_funbooker_comparison()
    assert result["version"] == SCAN_COMPARISON_VERSION
    assert result["previous_scan_id"] == fixture["previous"]["scan_id"]
    assert result["current_scan_id"] == fixture["current"]["scan_id"]
    assert result["summary"]["still_detected"] == 6
    assert all(row["previous_finding_id"] != row["current_finding_id"] for row in result["repair_comparisons"])
    assert all(row["repair_fingerprint"] for row in result["repair_comparisons"])


def test_scan_comparison_fails_closed_on_persisted_fingerprint_conflict():
    previous, current = funbooker_repairs()
    previous[0]["repair_fingerprint"] = "0" * 24
    with pytest.raises(ValueError, match="conflicts"):
        build_scan_comparison_v1(
            previous_scan_id="scan-old",
            current_scan_id="scan-new",
            current_previous_scan_id="scan-old",
            previous_fixes=previous,
            current_fixes=current,
            current_pages=[page("/a")],
            previous_score=75,
            current_score=72,
            previous_pages_checked=126,
            current_pages_checked=139,
        )


def test_funbooker_shape_tracks_new_h1_without_inventing_score_direction():
    fixture, result = build_funbooker_comparison()
    assert fixture["previous"]["repair_count"] == result["summary"]["previous_repairs_total"] == 6
    assert fixture["current"]["repair_count"] == result["summary"]["current_repairs_total"] == 7
    assert result["summary"]["new_or_came_back"] == 1
    assert len(result["new_or_came_back_repair_fingerprints"]) == 1
    assert result["score_sample_context"]["score_delta"] == -3
    assert result["score_sample_context"]["sample_size_changed"] is True
    assert result["score_sample_context"]["score_direction_claim_allowed"] is False


def test_customer_presentation_warns_when_funbooker_sample_size_changed():
    _, result = build_funbooker_comparison()
    presentation = build_customer_scan_comparison_presentation(result)
    assert presentation["version"] == SCAN_COMPARISON_PRESENTATION_VERSION
    assert presentation["score_line"] == "Health score changed from 75 to 72."
    assert "Pages checked: 126 in the previous scan; 139 in this scan." in presentation["sample_line"]
    assert "cannot tell you whether your site improved or got worse" in presentation["score_caution"]
    assert presentation["score_direction_claim_allowed"] is False
    assert presentation["overall_improvement_or_regression_claim"] is None
    assert "worse by 3" not in " ".join(str(value) for value in presentation.values()).lower()


def test_equal_page_counts_still_do_not_authorize_score_only_direction_claim():
    _, result = build_funbooker_comparison()
    result["score_sample_context"]["current_pages_checked"] = 126
    result["score_sample_context"]["sample_size_changed"] = False
    result["score_sample_context"]["score_context_state"] = "score_delta_descriptive_only"
    presentation = build_customer_scan_comparison_presentation(result)
    assert "may have checked different pages" in presentation["score_caution"].lower()
    assert presentation["score_direction_claim_allowed"] is False


def test_provisional_previous_repair_remains_could_not_verify_in_contract():
    previous = {
        "finding_id": "old",
        "rule": "missing_title",
        "category": "missing_title",
        "affected_pages": ["/a"],
    }
    result = build_scan_comparison_v1(
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
    assert result["summary"]["could_not_verify"] == 1
    assert result["summary"]["fixed"] == 0
    assert result["repair_comparisons"][0]["state"] == "could_not_verify"


def test_unstable_current_repair_is_not_labeled_new():
    previous, _ = funbooker_repairs()
    unstable = {"finding_id": "new-x", "rule": "missing_h1", "affected_pages": ["/g"]}
    result = build_scan_comparison_v1(
        previous_scan_id="scan-old",
        current_scan_id="scan-new",
        current_previous_scan_id="scan-old",
        previous_fixes=previous,
        current_fixes=[unstable],
        current_pages=[page(f"/{letter}") for letter in "abcdefg"],
        previous_score=75,
        current_score=72,
        previous_pages_checked=126,
        current_pages_checked=139,
    )
    assert result["summary"]["new_or_came_back"] == 0
    assert result["summary"]["current_repairs_without_reference_fingerprint"] == 1


def test_repair_comparison_order_is_deterministic_under_input_reordering():
    fixture = json.loads(FIXTURE.read_text())
    previous, current = funbooker_repairs()
    kwargs = dict(
        previous_scan_id=fixture["previous"]["scan_id"],
        current_scan_id=fixture["current"]["scan_id"],
        current_previous_scan_id=fixture["current"]["previous_scan_id"],
        current_pages=[page(f"/{letter}") for letter in "abcdefg"],
        previous_score=75,
        current_score=72,
        previous_pages_checked=126,
        current_pages_checked=139,
    )
    first = build_scan_comparison_v1(previous_fixes=previous, current_fixes=current, **kwargs)
    second = build_scan_comparison_v1(previous_fixes=list(reversed(previous)), current_fixes=list(reversed(current)), **kwargs)
    assert first["repair_comparisons"] == second["repair_comparisons"]
    assert first["new_or_came_back_repair_fingerprints"] == second["new_or_came_back_repair_fingerprints"]


def receipt(scan_id: str):
    return {
        "state": "verified",
        "scan_id": scan_id,
        "authority_seal_version": "standard_review_snapshot_hmac_v8",
        "authority_proof_fingerprint": "a" * 64,
    }


def test_transport_binds_exact_scan_ids_to_upstream_verified_authority_receipts():
    _, comparison = build_funbooker_comparison()
    transport = build_scan_comparison_transport_v1(
        comparison,
        previous_authority_receipt=receipt(comparison["previous_scan_id"]),
        current_authority_receipt=receipt(comparison["current_scan_id"]),
    )
    assert transport["version"] == SCAN_COMPARISON_TRANSPORT_VERSION
    assert len(transport["comparison_fingerprint"]) == 64
    assert transport["requires_serialized_v8_integrator"] is True
    assert transport["customer_projection_authorized"] is False
    assert transport["authority_created_or_modified"] is False


@pytest.mark.parametrize("mutation", ["unverified", "wrong_scan", "bad_fingerprint"])
def test_transport_fails_closed_without_exact_verified_authority_receipts(mutation):
    _, comparison = build_funbooker_comparison()
    previous_receipt = receipt(comparison["previous_scan_id"])
    current_receipt = receipt(comparison["current_scan_id"])
    if mutation == "unverified":
        current_receipt["state"] = "unavailable"
    elif mutation == "wrong_scan":
        current_receipt["scan_id"] = "different-scan"
    else:
        current_receipt["authority_proof_fingerprint"] = "not-a-sha"
    with pytest.raises(ValueError):
        build_scan_comparison_transport_v1(
            comparison,
            previous_authority_receipt=previous_receipt,
            current_authority_receipt=current_receipt,
        )


def build_production_funbooker_projection_comparison():
    fixture = json.loads(FIXTURE.read_text())
    return fixture, build_scan_comparison_v1(
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


def test_production_funbooker_fixture_preserves_fingerprints_when_finding_ids_change():
    fixture, result = build_production_funbooker_projection_comparison()
    assert fixture["production_observations"]["same_reference_fingerprints_across_scans"] == 6
    changed_ids = [
        row
        for row in result["repair_comparisons"]
        if row["same_reference_fingerprint_observed"]
        and row["previous_finding_id"] != row["current_finding_id"]
    ]
    assert len(changed_ids) == fixture["production_observations"]["finding_ids_changed_while_fingerprint_survived"] == 2
    assert result["new_or_came_back_repair_fingerprints"] == [
        fixture["production_observations"]["new_h1_reference_fingerprint"]
    ]


def test_production_funbooker_provisional_rows_fail_closed_without_false_fixed_claims():
    fixture, result = build_production_funbooker_projection_comparison()
    assert result["summary"]["previous_repairs_with_stable_verification_identity"] == 0
    assert result["summary"]["current_repairs_with_stable_verification_identity"] == 0
    assert result["summary"]["fixed"] == 0
    assert result["summary"]["still_detected"] == 0
    assert result["summary"]["could_not_verify"] == fixture["previous"]["repair_count"] == 6
    assert all(row["state"] == "could_not_verify" for row in result["repair_comparisons"])
    presentation = build_customer_scan_comparison_presentation(result)
    assert presentation["overall_improvement_or_regression_claim"] is None
    assert "cannot tell you whether your site improved or got worse" in presentation["score_caution"]
