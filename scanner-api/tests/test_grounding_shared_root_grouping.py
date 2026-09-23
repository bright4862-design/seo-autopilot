from __future__ import annotations

from copy import deepcopy

from app.grounding_verifier import build_evidence_set, verify_grounded_payload


REAL_URL = "https://example.com/real"


def root_evidence(
    *,
    root_id: str = "root-shared",
    surface_id: str | None = "surface:template",
    evidence_refs: list[str] | None = None,
) -> dict:
    evidence = {
        "version": "root_cause_evidence_v1_verified",
        "state": "verified",
        "root_cause_id": root_id,
        "evidence_refs": evidence_refs or [REAL_URL],
    }
    if surface_id is not None:
        evidence["repair_surface_id"] = surface_id
    return evidence


def sealed_l2() -> dict:
    return {
        "authority_seal_version": "authority_v8",
        "authority_sealed_at": "2026-09-23T06:00:00Z",
        "authority_proof": "shared-root-grouping-proof",
        "website_url": "https://example.com",
        "pages": [{"url": REAL_URL, "status_code": 200}],
        "stage3_handoff_v2_source": {
            "handoff_version": "fixlist_handoff_v2",
            "scan": {
                "scan_id": "scan-shared-root",
                "scan_run_id": "scan-shared-root",
            },
        },
        "fixes": [
            {"fix_id": "fix-1", "root_cause_evidence": root_evidence()},
            {"fix_id": "fix-2", "root_cause_evidence": root_evidence()},
        ],
    }


def annotation(*, root_refs: list[str] | None = None) -> dict:
    return {
        "schema_version": "ai_annotation_v1",
        "annotation_id": "shared-root",
        "text": "Grounded shared root cause.",
        "evidence": [{"url": REAL_URL, "require_live": True}],
        "numeric_claims": [],
        "fix_refs": [],
        "root_cause_refs": ["root-shared"] if root_refs is None else root_refs,
        "state_claims": [],
    }


def test_repeated_verified_root_same_surface_is_one_grounding_definition():
    source = sealed_l2()
    evidence = build_evidence_set(source)

    assert "root-shared" in evidence.root_cause_refs
    assert "root-shared" not in evidence.ambiguous_root_cause_refs
    assert verify_grounded_payload(annotation(), evidence_set=evidence).status == "verified"


def test_shared_root_same_surface_may_union_different_evidence_refs():
    source = sealed_l2()
    source["fixes"][0]["root_cause_evidence"]["evidence_refs"] = [
        "https://example.com/evidence-a"
    ]
    source["fixes"][1]["root_cause_evidence"]["evidence_refs"] = [
        "https://example.com/evidence-b"
    ]

    evidence = build_evidence_set(source)
    assert "root-shared" not in evidence.ambiguous_root_cause_refs
    assert "https://example.com/evidence-a" in evidence.url_members
    assert "https://example.com/evidence-b" in evidence.url_members
    assert verify_grounded_payload(annotation(), evidence_set=evidence).status == "verified"


def test_shared_root_missing_surface_uses_stage3_empty_surface_key():
    source = sealed_l2()
    source["fixes"][0]["root_cause_evidence"].pop("repair_surface_id")
    source["fixes"][1]["root_cause_evidence"].pop("repair_surface_id")

    evidence = build_evidence_set(source)
    assert "root-shared" not in evidence.ambiguous_root_cause_refs
    assert verify_grounded_payload(annotation(), evidence_set=evidence).status == "verified"


def test_same_root_different_repair_surfaces_remains_ambiguous():
    source = sealed_l2()
    source["fixes"][1]["root_cause_evidence"]["repair_surface_id"] = "surface:page"

    evidence = build_evidence_set(source)
    assert evidence.ambiguous_root_cause_refs == frozenset({"root-shared"})

    result = verify_grounded_payload(annotation(), evidence_set=evidence)
    assert result.status == "rejected"
    assert result.reasons == ["root_cause_ref_ambiguous"]


def test_explicit_root_definition_colliding_with_stage3_group_is_ambiguous():
    source = sealed_l2()
    source["root_causes"] = [{"root_cause_id": "root-shared"}]

    evidence = build_evidence_set(source)
    assert evidence.ambiguous_root_cause_refs == frozenset({"root-shared"})
    assert verify_grounded_payload(annotation(), evidence_set=evidence).reasons == [
        "root_cause_ref_ambiguous"
    ]


def test_distinct_roots_on_same_surface_do_not_conflict():
    source = sealed_l2()
    source["fixes"][1]["root_cause_evidence"] = root_evidence(root_id="root-other")

    evidence = build_evidence_set(source)
    assert evidence.ambiguous_root_cause_refs == frozenset()
    assert verify_grounded_payload(
        annotation(root_refs=["root-shared", "root-other"]),
        evidence_set=evidence,
    ).status == "verified"


def test_shared_root_grouping_is_deterministic():
    source = sealed_l2()
    left = build_evidence_set(source)
    right = build_evidence_set(deepcopy(source))

    assert left.fingerprint == right.fingerprint
    assert left.ambiguous_root_cause_refs == right.ambiguous_root_cause_refs == frozenset()
