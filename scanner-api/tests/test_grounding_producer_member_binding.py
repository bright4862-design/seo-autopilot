from __future__ import annotations

from copy import deepcopy

from app.grounding_verifier import build_evidence_set, verify_grounded_payload


TRUSTED_SCAN = "scan-trusted"
PAGE_URL = "https://example.com/observed"
MEMBER_URL = "https://example.com/member-proof"
BORROWED_URL = "https://example.com/borrowed-proof"


def root_evidence(root_id: str, evidence_url: str, *, surface: str) -> dict:
    return {
        "version": "root_cause_evidence_v1_verified",
        "state": "verified",
        "root_cause_id": root_id,
        "repair_surface_id": surface,
        "evidence_refs": [evidence_url],
    }


def fix(fix_id: str, root_id: str, evidence_url: str, *, surface: str, **identity) -> dict:
    return {
        "fix_id": fix_id,
        **identity,
        "root_cause_evidence": root_evidence(root_id, evidence_url, surface=surface),
    }


def handoff(*, fixes: list[dict] | object = None) -> dict:
    payload = {
        "handoff_version": "fixlist_handoff_v2",
        "scan": {"scan_id": TRUSTED_SCAN, "scan_run_id": TRUSTED_SCAN},
    }
    if fixes is not None:
        payload["fixes"] = fixes
    return payload


def sealed_l2(*, source: dict, sibling_fixes: list[dict] | None = None, diagnostics: dict | None = None) -> dict:
    payload = {
        "authority_seal_version": "authority_v8",
        "authority_sealed_at": "2026-09-23T09:30:00Z",
        "authority_proof": "producer-member-binding-proof",
        "website_url": "https://example.com",
        "pages": [{"url": PAGE_URL, "status_code": 200}],
        "stage3_handoff_v2_source": source,
    }
    if sibling_fixes is not None:
        payload["fixes"] = sibling_fixes
    if diagnostics is not None:
        payload["diagnostics"] = diagnostics
    return payload


def annotation(root_id: str, *, evidence_url: str = PAGE_URL) -> dict:
    return {
        "schema_version": "ai_annotation_v1",
        "annotation_id": f"member-binding-{root_id}",
        "text": "Grounded root-cause claim.",
        "evidence": [{"url": evidence_url, "require_live": evidence_url == PAGE_URL}],
        "numeric_claims": [],
        "fix_refs": [],
        "root_cause_refs": [root_id],
        "state_claims": [],
    }


def member_fix() -> dict:
    return fix("fix-member", "root-member", MEMBER_URL, surface="surface:member")


def borrowed_fix(**identity) -> dict:
    return fix("fix-borrowed", "root-borrowed", BORROWED_URL, surface="surface:borrowed", **identity)


def test_recognized_handoff_member_can_ground_nested_root_and_evidence_url():
    evidence = build_evidence_set(sealed_l2(source=handoff(fixes=[member_fix()])))

    assert "root-member" in evidence.root_cause_refs
    assert MEMBER_URL in evidence.url_members
    assert verify_grounded_payload(annotation("root-member"), evidence_set=evidence).status == "verified"


def test_top_level_fix_collection_cannot_borrow_trusted_handoff_identity():
    evidence = build_evidence_set(
        sealed_l2(source=handoff(fixes=[member_fix()]), sibling_fixes=[borrowed_fix()])
    )

    assert "root-borrowed" not in evidence.root_cause_refs
    assert BORROWED_URL not in evidence.url_members
    result = verify_grounded_payload(annotation("root-borrowed"), evidence_set=evidence)
    assert result.status == "rejected"
    assert result.reasons == ["root_cause_ref_missing"]


def test_nested_sibling_fix_collection_cannot_borrow_trusted_handoff_identity():
    evidence = build_evidence_set(
        sealed_l2(
            source=handoff(fixes=[member_fix()]),
            diagnostics={"fixes": [borrowed_fix()]},
        )
    )

    assert "root-borrowed" not in evidence.root_cause_refs
    assert BORROWED_URL not in evidence.url_members


def test_matching_local_scan_pair_does_not_override_handoff_containment():
    evidence = build_evidence_set(
        sealed_l2(
            source=handoff(fixes=[member_fix()]),
            sibling_fixes=[borrowed_fix(scan_id=TRUSTED_SCAN, scan_run_id=TRUSTED_SCAN)],
        )
    )

    assert "root-borrowed" not in evidence.root_cause_refs
    assert BORROWED_URL not in evidence.url_members


def test_deepcopied_handoff_member_outside_source_does_not_gain_membership_by_value():
    trusted = member_fix()
    copied = deepcopy(trusted)
    copied["fix_id"] = "fix-copied"
    copied["root_cause_evidence"] = root_evidence(
        "root-copied", BORROWED_URL, surface="surface:copied"
    )
    evidence = build_evidence_set(
        sealed_l2(source=handoff(fixes=[trusted]), sibling_fixes=[copied])
    )

    assert "root-member" in evidence.root_cause_refs
    assert "root-copied" not in evidence.root_cause_refs
    assert BORROWED_URL not in evidence.url_members


def test_legacy_snapshot_without_handoff_fixes_keeps_existing_single_root_behavior():
    evidence = build_evidence_set(
        sealed_l2(source=handoff(), sibling_fixes=[borrowed_fix()])
    )

    assert "root-borrowed" in evidence.root_cause_refs
    assert BORROWED_URL in evidence.url_members
