from __future__ import annotations

from copy import deepcopy

from app.grounding_verifier import build_evidence_set, verify_grounded_payload


def sealed_l2() -> dict:
    return {
        "authority_seal_version": "authority_v8",
        "authority_sealed_at": "2026-09-23T04:00:00Z",
        "authority_proof": "identity-scope-proof",
        "website_url": "https://example.com",
        "pages": [{"url": "https://example.com/real", "status_code": 200}],
        "fixes": [
            {
                "fix_id": "fix-1",
                "root_cause_id": "root-1",
                "evidence_refs": ["https://example.com/real"],
            }
        ],
        "root_causes": [
            {
                "root_cause_id": "root-1",
                "details": {"evidence_url": "https://example.com/real"},
            }
        ],
    }


def annotation(
    url: str = "https://example.com/real",
    *,
    fix_refs: list[str] | None = None,
    root_cause_refs: list[str] | None = None,
) -> dict:
    return {
        "schema_version": "ai_annotation_v1",
        "annotation_id": "identity-scope",
        "text": "Grounded identity scope.",
        "evidence": [{"url": url, "require_live": False}],
        "numeric_claims": [],
        "fix_refs": ["fix-1"] if fix_refs is None else fix_refs,
        "root_cause_refs": ["root-1"] if root_cause_refs is None else root_cause_refs,
        "state_claims": [],
    }


def test_conflicting_fix_aliases_on_one_record_fail_closed():
    source = sealed_l2()
    source["fixes"][0]["rule_id"] = "fix-other"

    evidence = build_evidence_set(source)
    assert evidence.conflicting_fix_refs == frozenset({"fix-1", "fix-other"})

    result = verify_grounded_payload(
        annotation(root_cause_refs=[]),
        evidence_set=evidence,
    )
    assert result.status == "rejected"
    assert result.reasons == ["fix_ref_conflicting_alias"]


def test_conflicting_root_aliases_on_one_record_fail_closed():
    source = sealed_l2()
    source["root_causes"][0]["id"] = "root-other"

    evidence = build_evidence_set(source)
    assert evidence.conflicting_root_cause_refs == frozenset({"root-1", "root-other"})

    result = verify_grounded_payload(
        annotation(fix_refs=[]),
        evidence_set=evidence,
    )
    assert result.status == "rejected"
    assert result.reasons == ["root_cause_ref_conflicting_alias"]


def test_matching_aliases_on_one_record_remain_unambiguous():
    source = sealed_l2()
    source["fixes"][0].update({"id": "fix-1", "rule_id": "fix-1", "repair_id": "fix-1"})
    source["root_causes"][0]["id"] = "root-1"

    evidence = build_evidence_set(source)
    assert evidence.conflicting_fix_refs == frozenset()
    assert evidence.conflicting_root_cause_refs == frozenset()
    assert verify_grounded_payload(annotation(), evidence_set=evidence).status == "verified"


def test_repair_fingerprint_is_secondary_ref_not_conflicting_alias():
    source = sealed_l2()
    source["fixes"][0]["repair_fingerprint"] = "fingerprint-1"

    evidence = build_evidence_set(source)
    assert evidence.conflicting_fix_refs == frozenset()
    assert {"fix-1", "fingerprint-1"}.issubset(evidence.fix_refs)

    result = verify_grounded_payload(
        annotation(fix_refs=["fix-1", "fingerprint-1"]),
        evidence_set=evidence,
    )
    assert result.status == "verified"


def test_root_link_on_fix_does_not_define_root_cause():
    source = sealed_l2()
    source.pop("root_causes")

    evidence = build_evidence_set(source)
    assert "root-1" not in evidence.root_cause_refs

    result = verify_grounded_payload(
        annotation(fix_refs=[]),
        evidence_set=evidence,
    )
    assert result.status == "rejected"
    assert result.reasons == ["root_cause_ref_missing"]


def test_nested_verified_root_cause_evidence_defines_root_cause():
    source = sealed_l2()
    source.pop("root_causes")
    source["fixes"][0]["root_cause_evidence"] = {
        "version": "root_cause_evidence_v1_verified",
        "state": "verified",
        "root_cause_id": "root-1",
        "evidence_refs": ["https://example.com/real"],
    }

    evidence = build_evidence_set(source)
    assert "root-1" in evidence.root_cause_refs
    assert verify_grounded_payload(annotation(), evidence_set=evidence).status == "verified"


def test_fix_details_is_not_a_generic_evidence_wrapper():
    source = sealed_l2()
    fake = "https://example.com/fake-fix-details"
    source["fixes"][0]["details"] = {"evidence_url": fake}

    evidence = build_evidence_set(source)
    assert fake not in evidence.url_members

    result = verify_grounded_payload(
        annotation(fake, root_cause_refs=[]),
        evidence_set=evidence,
    )
    assert result.status == "rejected"
    assert result.reasons == ["url_not_in_evidence"]


def test_root_details_remains_direct_evidence_scope():
    source = sealed_l2()
    evidence = build_evidence_set(source)
    assert "https://example.com/real" in evidence.url_members
    assert verify_grounded_payload(annotation(), evidence_set=evidence).status == "verified"


def test_conflict_sets_are_fingerprinted_deterministically():
    source = sealed_l2()
    source["fixes"][0]["rule_id"] = "fix-other"
    source["root_causes"][0]["id"] = "root-other"

    first = build_evidence_set(source)
    second = build_evidence_set(deepcopy(source))
    clean = build_evidence_set(sealed_l2())

    assert first.fingerprint == second.fingerprint
    assert first.fingerprint != clean.fingerprint
    assert first.conflicting_fix_refs == second.conflicting_fix_refs
    assert first.conflicting_root_cause_refs == second.conflicting_root_cause_refs
