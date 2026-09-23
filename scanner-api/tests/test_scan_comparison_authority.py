from copy import deepcopy

import pytest

from app.repair_identity import REPAIR_IDENTITY_VERSION, build_repair_identity
from app.scan_comparison_authority import (
    build_authenticated_scan_comparison_v1,
    build_scan_comparison_lineage_v1,
)
from app.scan_job import create_authority_seal

KEY = "local-only-comparison-authority-key"
AUTHORITY = "standard_review_snapshot_hmac_identity_v1"
EVIDENCE = "evidence_url_identity_v2_published_route"


def repair(fix_id="repair-old", *, stable=True):
    result = {
        "fix_id": fix_id, "rule": "missing_h1", "category": "heading",
        "page_scope": "page", "page_url": "https://example.com/page",
        "affected_pages": ["https://example.com/page"],
        "repair_surface": "page:/page" if stable else "",
        "remediation_family": "add_semantic_h1" if stable else "",
        "rule_definition_version": "heading-v1", "comparison_profile_version": "standard150-v1",
        "verification_state": "confirmed", "user_status": "open",
        "raw_finding": {"published_evidence": {"evidence_url_identity_version": EVIDENCE}},
    }
    identity = build_repair_identity(result)
    result.update(repair_identity_version=REPAIR_IDENTITY_VERSION, repair_identity_state=identity["state"],
                  repair_identity_stable=identity["stable"], repair_fingerprint=identity["fingerprint"])
    return result


def snapshot(scan_id, date, fixes, score, pages):
    return {
        "version": AUTHORITY, "sealed_at": date, "owner_user_id": "owner",
        "scan_id": scan_id, "project_id": "project", "normalized_domain": "example.com",
        "release_fingerprint": "01ebe8e90df1e6bd",
        "scan": {
            "status": "complete", "release_gate_eligible": True,
            "score_is_provisional": False, "evidence_quality_blocking": False,
            "website_url": "https://example.com/", "normalized_domain": "example.com",
            "requested_origin": "https://example.com", "scope_type": "", "requested_path_prefix": "",
            "completed_at": date, "health_score": score, "pages_crawled": pages,
        },
        "fix_list": {"is_authoritative": True, "score_is_provisional": False,
                     "total_fixes": len(fixes), "health_score": score},
        "recommendations": fixes,
    }


def inputs(*, stable=True, current_fixes=None):
    return sign({
        "previous_snapshot": snapshot("previous", "2026-09-22T10:00:00Z", [repair(stable=stable)], 75, 126),
        "current_snapshot": snapshot("current", "2026-09-23T10:00:00Z",
                                     [repair("repair-new", stable=stable)] if current_fixes is None else current_fixes, 72, 139),
        "expected_owner_user_id": "owner", "expected_project_id": "project",
        "expected_current_scan_id": "current", "signing_key": KEY,
    })


def sign(pair):
    for side in ("previous", "current"):
        pair[f"{side}_proof"] = create_authority_seal(pair[f"{side}_snapshot"], pair["signing_key"])
    return pair


def lineage(pair):
    return build_scan_comparison_lineage_v1(current_previous_scan_id="previous", **pair)


def compare(pair, artifact=None):
    return build_authenticated_scan_comparison_v1(lineage_artifact=lineage(pair) if artifact is None else artifact, **pair)


def test_authenticated_stable_identity_survives_finding_id_changes_without_mutation():
    pair = inputs()
    artifact = lineage(pair)
    original = deepcopy((pair, artifact))
    result = compare(pair, artifact)
    assert result["comparison"]["summary"]["still_detected"] == 1
    assert result["comparison"]["summary"]["fixed"] == 0
    assert result["presentation"]["score_line"] == "Health score changed from 75 to 72."
    assert result["presentation"]["score_direction_claim_allowed"] is False
    assert "sample size changed" in result["presentation"]["score_caution"]
    assert result["current_pages_available"] is False
    assert result["customer_projection_authorized"] is False
    assert result["transport"]["customer_projection_authorized"] is False
    assert (pair, artifact) == original


@pytest.mark.parametrize("side", ["previous", "current"])
def test_modified_result_bytes_fail_original_proof(side):
    pair = inputs()
    artifact = lineage(pair)
    pair[f"{side}_snapshot"]["scan"]["health_score"] = 99
    with pytest.raises(ValueError, match="proof verification"):
        compare(pair, artifact)


@pytest.mark.parametrize("side", ["previous", "current"])
@pytest.mark.parametrize("proof", ["0" * 64, "ABC" * 21 + "D", " "+"a"*64, "", None, True])
def test_malformed_or_forged_result_proof_is_rejected(side, proof):
    pair = inputs()
    pair[f"{side}_proof"] = proof
    with pytest.raises(ValueError):
        lineage(pair)


@pytest.mark.parametrize("key", [None, "", True, b"key"])
def test_unavailable_key_is_rejected(key):
    pair = inputs()
    pair["signing_key"] = key
    with pytest.raises(ValueError, match="signing key"):
        lineage(pair)


def test_signing_key_bytes_are_not_trimmed():
    pair = inputs()
    pair["signing_key"] = f" {KEY} "
    sign(pair)
    artifact = lineage(pair)
    compare(pair, artifact)
    pair["signing_key"] = KEY
    with pytest.raises(ValueError, match="proof verification"):
        compare(pair, artifact)


def test_lineage_requires_exact_service_owned_pointer():
    pair = inputs()
    for pointer in ("wrong", "previous ", "", None):
        with pytest.raises(ValueError):
            build_scan_comparison_lineage_v1(current_previous_scan_id=pointer, **pair)
    # Existing signed snapshot or an unsigned field cannot replace the artifact.
    pair["current_snapshot"]["scan"]["previous_scan_id"] = "previous"
    sign(pair)
    with pytest.raises(ValueError, match="artifact"):
        build_authenticated_scan_comparison_v1(lineage_artifact=None, **pair)


@pytest.mark.parametrize("field,value", [("previous_scan_id", "other"), ("owner_user_id", "other"),
                                         ("current_authority_proof", "a" * 64), ("integrity_domain", "other")])
def test_mutated_lineage_fails_signature(field, value):
    pair = inputs()
    artifact = lineage(pair)
    artifact[field] = value
    with pytest.raises(ValueError, match="proof verification"):
        compare(pair, artifact)


def test_lineage_cannot_be_replayed_against_changed_signed_result():
    pair = inputs()
    artifact = lineage(pair)
    pair["current_snapshot"]["scan"]["health_score"] = 73
    pair["current_snapshot"]["fix_list"]["health_score"] = 73
    sign(pair)
    with pytest.raises(ValueError, match="exact scan pair"):
        compare(pair, artifact)


def test_signed_wrong_domain_or_extra_lineage_fields_fail_closed():
    pair = inputs()
    for mutation in ({"integrity_domain": "some_other_valid_hmac_domain"}, {"customer_projection_authorized": True}):
        artifact = lineage(pair)
        artifact.update(mutation)
        artifact["proof"] = create_authority_seal({k: v for k, v in artifact.items() if k != "proof"}, KEY)
        with pytest.raises(ValueError, match="exact scan pair"):
            compare(pair, artifact)


@pytest.mark.parametrize("field,value", [("owner_user_id", "another-owner"), ("project_id", "another-project"),
                                         ("scan_id", "previous"), ("normalized_domain", "other.example"),
                                         ("version", "unknown-seal")])
def test_authentic_but_wrong_identity_is_rejected(field, value):
    pair = inputs()
    pair["current_snapshot"][field] = value
    sign(pair)
    with pytest.raises(ValueError):
        lineage(pair)


@pytest.mark.parametrize("change", [
    {"requested_origin": "http://example.com"},
    {"requested_origin": "https://www.example.com"},
    {"requested_origin": "https://other.example"},
    {"scope_type": "path_prefix", "requested_path_prefix": "/shop", "user_confirmed": True},
    {"scope_type": "path_prefix", "requested_path_prefix": ""},
    {"scope_type": "", "requested_path_prefix": "/shop"},
    {"scope_type": "", "parent_scan_id": "parent"},
])
def test_cross_origin_or_scope_pairs_are_rejected(change):
    pair = inputs()
    pair["current_snapshot"]["scan"].update(change)
    sign(pair)
    with pytest.raises(ValueError):
        lineage(pair)


def test_matching_focused_scope_is_supported_and_separate_from_whole_site():
    pair = inputs()
    for side in ("previous", "current"):
        pair[f"{side}_snapshot"]["scan"].update(scope_type="path_prefix", requested_path_prefix="/shop", user_confirmed=True)
    sign(pair)
    assert lineage(pair)["scope"]["requested_path_prefix"] == "/shop"
    assert compare(pair)["comparison"]["summary"]["still_detected"] == 1


@pytest.mark.parametrize("section,field,value", [
    ("scan", "status", "limited"), ("scan", "release_gate_eligible", False),
    ("scan", "score_is_provisional", True), ("scan", "evidence_quality_blocking", True),
    ("scan", "pages_crawled", True), ("scan", "health_score", 101),
    ("fix_list", "health_score", 10), ("fix_list", "total_fixes", 0),
    ("fix_list", "is_authoritative", False), ("scan", "completed_at", "2026-09-24T00:00:00Z"),
])
def test_contradictory_signed_result_cannot_authorize_comparison(section, field, value):
    pair = inputs()
    pair["current_snapshot"][section][field] = value
    sign(pair)
    with pytest.raises(ValueError):
        compare(pair)


def test_reversed_or_equal_seal_times_are_rejected():
    for timestamp in ("2026-09-22T10:00:00Z", "2026-09-20T10:00:00Z"):
        pair = inputs()
        pair["current_snapshot"]["sealed_at"] = timestamp
        pair["current_snapshot"]["scan"]["completed_at"] = timestamp
        sign(pair)
        with pytest.raises(ValueError, match="precede"):
            lineage(pair)


@pytest.mark.parametrize("stable", [False, True])
def test_absent_repair_cannot_be_verified_fixed_without_page_evidence(stable):
    result = compare(inputs(stable=stable, current_fixes=[]))
    assert result["comparison"]["summary"]["fixed"] == 0
    assert result["comparison"]["summary"]["could_not_verify"] == 1


def test_provisional_persisted_fingerprint_continuity_does_not_become_verified():
    result = compare(inputs(stable=False))
    assert result["comparison"]["summary"]["still_detected"] == 0
    assert result["comparison"]["summary"]["could_not_verify"] == 1
    assert result["comparison"]["summary"]["new_or_came_back"] == 0


@pytest.mark.parametrize("version", ["", "unknown-identity"])
def test_unsupported_historical_identity_stays_unverified(version):
    pair = inputs()
    for side in ("previous", "current"):
        pair[f"{side}_snapshot"]["recommendations"][0]["repair_identity_version"] = version
    sign(pair)
    result = compare(pair)
    assert result["comparison"]["summary"]["could_not_verify"] == 1
    assert result["comparison"]["summary"]["still_detected"] == 0


@pytest.mark.parametrize("field,value", [("repair_identity_stable", False), ("repair_identity_state", "provisional"),
                                         ("repair_fingerprint", "a" * 24), ("repair_surface", {"value": "template"})])
def test_inconsistent_signed_stable_identity_is_rejected(field, value):
    pair = inputs()
    pair["previous_snapshot"]["recommendations"][0][field] = value
    sign(pair)
    with pytest.raises(ValueError, match="identity"):
        compare(pair)


@pytest.mark.parametrize("field,value", [("rule_definition_version", "heading-v2"),
                                         ("comparison_profile_version", "standard500-v1"),
                                         ("rule_definition_version", "")])
def test_matching_fingerprint_cannot_bypass_contract_compatibility(field, value):
    pair = inputs()
    pair["current_snapshot"]["recommendations"][0][field] = value
    sign(pair)
    with pytest.raises(ValueError, match="incompatible comparison contracts"):
        compare(pair)


def test_published_url_identity_is_read_from_authenticated_raw_evidence():
    pair = inputs()
    pair["current_snapshot"]["recommendations"][0]["raw_finding"] = {}
    sign(pair)
    with pytest.raises(ValueError, match="incompatible comparison contracts"):
        compare(pair)


def test_matching_current_repair_preserves_distinct_published_url_keys():
    pair = inputs()
    pair["current_snapshot"]["recommendations"][0]["affected_pages"] = [
        "https://example.com/page?offer=a", "https://example.com/page?offer=b",
        "https://example.com/page/?offer=a",
    ]
    sign(pair)
    result = compare(pair)
    assert result["comparison"]["repair_comparisons"][0]["rechecked_pages"] == 3


def test_mixed_current_url_identity_semantics_fail_closed():
    pair = inputs()
    added = repair("other-fix")
    added["raw_finding"] = {}
    pair["current_snapshot"]["recommendations"].append(added)
    pair["current_snapshot"]["fix_list"]["total_fixes"] = 2
    sign(pair)
    with pytest.raises(ValueError, match="incompatible evidence identity"):
        compare(pair)


def test_user_completion_is_never_used_as_verified_fix_state():
    pair = inputs()
    pair["previous_snapshot"]["recommendations"][0]["user_status"] = "done"
    sign(pair)
    assert compare(pair)["comparison"]["summary"]["still_detected"] == 1
    pair["previous_snapshot"]["recommendations"][0]["verification_state"] = "verified_fixed"
    sign(pair)
    assert compare(pair)["comparison"]["summary"]["came_back"] == 1


def test_unmatched_provisional_reference_is_not_proof_of_a_new_finding():
    pair = inputs(stable=False)
    prior = pair["previous_snapshot"]["recommendations"][0]
    current = pair["current_snapshot"]["recommendations"][0]
    current["category"] = "content_heading"
    identity = build_repair_identity(current)
    current["repair_fingerprint"] = identity["fingerprint"]
    assert current["rule"] == prior["rule"]
    assert current["affected_pages"] == prior["affected_pages"]
    sign(pair)
    result = compare(pair)
    assert result["comparison"]["summary"]["could_not_verify"] == 1
    assert result["comparison"]["summary"]["new_or_came_back"] == 1
    assert result["presentation"]["new_or_came_back_is_verified_claim"] is False
