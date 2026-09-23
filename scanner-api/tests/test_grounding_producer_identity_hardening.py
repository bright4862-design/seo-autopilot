from __future__ import annotations

from app.grounding_verifier import build_evidence_set, verify_grounded_payload


PAGE_URL = "https://example.com/observed"
ROOT_URL = "https://example.com/root-proof"
TRUSTED_SCAN = "scan-trusted"


def handoff(*, scan_id=TRUSTED_SCAN, scan_run_id=TRUSTED_SCAN, version="fixlist_handoff_v2") -> dict:
    return {
        "handoff_version": version,
        "scan": {
            "scan_id": scan_id,
            "scan_run_id": scan_run_id,
        },
    }


def root_evidence() -> dict:
    return {
        "version": "root_cause_evidence_v1_verified",
        "state": "verified",
        "root_cause_id": "root-trusted",
        "repair_surface_id": "surface:template",
        "evidence_refs": [ROOT_URL],
    }


def fix(*, fix_id="fix-1", **local_identity) -> dict:
    return {
        "fix_id": fix_id,
        **local_identity,
        "root_cause_evidence": root_evidence(),
    }


def sealed_l2(*, fixes=None, direct=None, review=None, health=None) -> dict:
    source = {
        "authority_seal_version": "authority_v8",
        "authority_sealed_at": "2026-09-23T08:00:00Z",
        "authority_proof": "producer-identity-hardening-proof",
        "website_url": "https://example.com",
        "pages": [{"url": PAGE_URL, "status_code": 200}],
        "fixes": fixes if fixes is not None else [fix()],
    }
    if direct is not None:
        source["stage3_handoff_v2_source"] = direct
    if review is not None:
        source["review"] = {"stage3_handoff_v2_source": review}
    if health is not None:
        source["health_score_explanation"] = {
            "stage3_delivery": {"handoff_v2_source": health}
        }
    return source


def annotation(*, evidence_url=PAGE_URL) -> dict:
    return {
        "schema_version": "ai_annotation_v1",
        "annotation_id": "producer-identity",
        "text": "Grounded evidence is available for this annotation.",
        "evidence": [{"url": evidence_url, "require_live": evidence_url == PAGE_URL}],
        "numeric_claims": [],
        "fix_refs": [],
        "root_cause_refs": ["root-trusted"],
        "state_claims": [],
    }


def assert_root_rejected_and_nested_url_withheld(source: dict) -> None:
    evidence = build_evidence_set(source)
    assert "root-trusted" not in evidence.root_cause_refs
    assert ROOT_URL not in evidence.url_members
    result = verify_grounded_payload(annotation(), evidence_set=evidence)
    assert result.status == "rejected"
    assert result.reasons == ["root_cause_ref_missing"]


def test_duplicate_identical_recognized_producer_sources_remain_verified_and_deterministic():
    source = sealed_l2(
        direct=handoff(),
        review=handoff(),
        health=handoff(),
    )
    first = build_evidence_set(source)
    second = build_evidence_set(source)

    assert first.fingerprint == second.fingerprint
    assert "root-trusted" in first.root_cause_refs
    assert ROOT_URL in first.url_members
    assert verify_grounded_payload(annotation(), evidence_set=first).status == "verified"


def test_conflicting_direct_and_review_producer_identities_fail_closed():
    source = sealed_l2(
        direct=handoff(),
        review=handoff(scan_id="scan-other", scan_run_id="scan-other"),
    )
    assert_root_rejected_and_nested_url_withheld(source)


def test_conflicting_health_score_producer_identity_fails_closed():
    source = sealed_l2(
        direct=handoff(),
        health=handoff(scan_id="scan-other", scan_run_id="scan-other"),
    )
    assert_root_rejected_and_nested_url_withheld(source)


def test_unknown_handoff_version_in_any_recognized_source_fails_closed():
    source = sealed_l2(
        direct=handoff(),
        review=handoff(version="fixlist_handoff_v3"),
    )
    assert_root_rejected_and_nested_url_withheld(source)


def test_structured_producer_scan_id_fails_closed():
    source = sealed_l2(direct=handoff(scan_id={"id": TRUSTED_SCAN}))
    assert_root_rejected_and_nested_url_withheld(source)


def test_structured_producer_scan_run_id_fails_closed():
    source = sealed_l2(direct=handoff(scan_run_id=[TRUSTED_SCAN]))
    assert_root_rejected_and_nested_url_withheld(source)


def test_partial_local_scan_id_assertion_cannot_ground_root_or_url():
    source = sealed_l2(
        direct=handoff(),
        fixes=[fix(scan_id=TRUSTED_SCAN)],
    )
    assert_root_rejected_and_nested_url_withheld(source)


def test_partial_local_scan_run_id_assertion_cannot_ground_root_or_url():
    source = sealed_l2(
        direct=handoff(),
        fixes=[fix(scan_run_id=TRUSTED_SCAN)],
    )
    assert_root_rejected_and_nested_url_withheld(source)


def test_empty_local_scan_assertions_cannot_ground_root_or_url():
    source = sealed_l2(
        direct=handoff(),
        fixes=[fix(scan_id="", scan_run_id="")],
    )
    assert_root_rejected_and_nested_url_withheld(source)


def test_matching_complete_local_scan_assertion_remains_verified():
    source = sealed_l2(
        direct=handoff(),
        fixes=[fix(scan_id=TRUSTED_SCAN, scan_run_id=TRUSTED_SCAN)],
    )
    evidence = build_evidence_set(source)

    assert "root-trusted" in evidence.root_cause_refs
    assert ROOT_URL in evidence.url_members
    assert verify_grounded_payload(annotation(), evidence_set=evidence).status == "verified"
