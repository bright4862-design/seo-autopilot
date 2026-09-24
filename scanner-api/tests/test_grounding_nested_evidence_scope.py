from __future__ import annotations

from copy import deepcopy

from app.grounding_verifier import build_evidence_set, verify_grounded_payload


def sealed_l2() -> dict:
    return {
        "authority_seal_version": "authority_v8",
        "authority_sealed_at": "2026-09-23T03:00:00Z",
        "authority_proof": "nested-evidence-scope-proof",
        "website_url": "https://example.com",
        "pages": [{"url": "https://example.com/real", "status_code": 200}],
        "fixes": [
            {
                "fix_id": "fix-1",
                "root_cause_id": "root-1",
                "evidence_refs": ["https://example.com/real"],
                "url_provenance": {"published_url": "https://example.com/real"},
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
        "annotation_id": "nested-scope",
        "text": "Grounded evidence is available for this annotation.",
        "evidence": [{"url": url, "require_live": False}],
        "numeric_claims": [],
        "fix_refs": ["fix-1"] if fix_refs is None else fix_refs,
        "root_cause_refs": ["root-1"] if root_cause_refs is None else root_cause_refs,
        "state_claims": [],
    }


def test_nested_fix_diagnostics_cannot_become_url_evidence():
    source = sealed_l2()
    fake = "https://example.com/fake-fix-diagnostic"
    source["fixes"][0]["diagnostics"] = {"evidence_url": fake}

    evidence = build_evidence_set(source)
    assert fake not in evidence.url_members

    result = verify_grounded_payload(annotation(fake), evidence_set=evidence)
    assert result.status == "rejected"
    assert result.reasons == ["url_not_in_evidence"]


def test_diagnostics_nested_under_url_provenance_cannot_become_evidence():
    source = sealed_l2()
    fake = "https://example.com/fake-url-provenance-diagnostic"
    source["fixes"][0]["url_provenance"]["diagnostics"] = {"published_url": fake}

    evidence = build_evidence_set(source)
    assert fake not in evidence.url_members


def test_root_details_keep_direct_evidence_but_not_nested_diagnostics():
    source = sealed_l2()
    fake = "https://example.com/fake-root-diagnostic"
    source["root_causes"][0]["details"]["diagnostics"] = {"published_url": fake}

    evidence = build_evidence_set(source)
    assert "https://example.com/real" in evidence.url_members
    assert fake not in evidence.url_members


def test_duplicate_fix_identity_is_ambiguous_and_rejected():
    source = sealed_l2()
    source["fixes"].append(
        {"fix_id": "fix-1", "evidence_refs": ["https://example.com/real"]}
    )

    evidence = build_evidence_set(source)
    assert evidence.ambiguous_fix_refs == frozenset({"fix-1"})

    result = verify_grounded_payload(annotation(), evidence_set=evidence)
    assert result.status == "rejected"
    assert "fix_ref_ambiguous" in result.reasons


def test_same_fix_record_aliases_do_not_create_false_ambiguity():
    source = sealed_l2()
    source["fixes"][0].update(
        {"id": "fix-1", "rule_id": "fix-1", "repair_id": "fix-1"}
    )

    evidence = build_evidence_set(source)
    assert evidence.ambiguous_fix_refs == frozenset()
    assert verify_grounded_payload(annotation(), evidence_set=evidence).status == "verified"


def test_duplicate_root_cause_identity_is_ambiguous_and_rejected():
    source = sealed_l2()
    source["root_causes"].append(
        {"root_cause_id": "root-1", "evidence_refs": ["https://example.com/real"]}
    )

    evidence = build_evidence_set(source)
    assert evidence.ambiguous_root_cause_refs == frozenset({"root-1"})

    result = verify_grounded_payload(annotation(), evidence_set=evidence)
    assert result.status == "rejected"
    assert "root_cause_ref_ambiguous" in result.reasons


def test_repeated_root_links_across_fixes_do_not_create_false_ambiguity():
    source = sealed_l2()
    source["fixes"].append(
        {
            "fix_id": "fix-2",
            "root_cause_id": "root-1",
            "evidence_refs": ["https://example.com/real"],
        }
    )

    evidence = build_evidence_set(source)
    assert evidence.ambiguous_root_cause_refs == frozenset()
    assert verify_grounded_payload(annotation(), evidence_set=evidence).status == "verified"


def test_incomplete_fix_record_cannot_manufacture_reference_identity():
    source = sealed_l2()
    source["fixes"] = [
        {"title": "missing identity", "evidence_refs": ["https://example.com/real"]}
    ]

    result = verify_grounded_payload(
        annotation(fix_refs=["fix-1"], root_cause_refs=[]),
        sealed_l2=source,
    )
    assert result.status == "rejected"
    assert "fix_ref_missing" in result.reasons


def test_ambiguity_is_part_of_deterministic_evidence_fingerprint():
    source = sealed_l2()
    source["fixes"].append(
        {"fix_id": "fix-1", "evidence_refs": ["https://example.com/real"]}
    )

    left = build_evidence_set(source)
    right = build_evidence_set(deepcopy(source))
    assert left.fingerprint == right.fingerprint
    assert left.ambiguous_fix_refs == right.ambiguous_fix_refs == frozenset({"fix-1"})
