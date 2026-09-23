from __future__ import annotations

from copy import deepcopy

from app.grounding_verifier import build_evidence_set, verify_grounded_payload


REAL_URL = "https://example.com/real"
ROOT_URL = "https://example.com/root-evidence"


def sealed_l2() -> dict:
    return {
        "authority_seal_version": "authority_v8",
        "authority_sealed_at": "2026-09-23T05:00:00Z",
        "authority_proof": "root-contract-proof",
        "website_url": "https://example.com",
        "pages": [{"url": REAL_URL, "status_code": 200}],
        "fixes": [
            {
                "fix_id": "fix-1",
                "root_cause_evidence": {
                    "version": "root_cause_evidence_v1_verified",
                    "state": "verified",
                    "root_cause_id": "root-1",
                    "repair_surface_id": "surface:template",
                    "evidence_refs": [ROOT_URL],
                },
            }
        ],
    }


def annotation(*, url: str = REAL_URL, root_refs: list[str] | None = None) -> dict:
    return {
        "schema_version": "ai_annotation_v2",
        "annotation_id": "root-contract",

        "evidence": [{"url": url, "require_live": False}],
        "numeric_claims": [],
        "fix_refs": [],
        "root_cause_refs": ["root-1"] if root_refs is None else root_refs,
        "state_claims": [],
    }


def _result(source: dict):
    return verify_grounded_payload(annotation(), sealed_l2=source)


def test_verified_stage3_root_evidence_defines_root_and_preserves_evidence_url():
    source = sealed_l2()
    evidence = build_evidence_set(source)

    assert "root-1" in evidence.root_cause_refs
    assert ROOT_URL in evidence.url_members
    assert _result(source).status == "verified"


def test_confirmed_stage3_root_evidence_is_accepted_by_existing_contract():
    source = sealed_l2()
    source["fixes"][0]["root_cause_evidence"]["state"] = "confirmed"

    evidence = build_evidence_set(source)
    assert "root-1" in evidence.root_cause_refs
    assert _result(source).status == "verified"


def test_unknown_root_evidence_version_cannot_define_root_or_url_membership():
    source = sealed_l2()
    source["fixes"][0]["root_cause_evidence"]["version"] = "root_cause_evidence_v999"

    evidence = build_evidence_set(source)
    assert "root-1" not in evidence.root_cause_refs
    assert ROOT_URL not in evidence.url_members
    result = _result(source)
    assert result.status == "rejected"
    assert result.reasons == ["root_cause_ref_missing"]


def test_unverified_root_evidence_cannot_define_root():
    source = sealed_l2()
    source["fixes"][0]["root_cause_evidence"]["state"] = "not_verified"

    evidence = build_evidence_set(source)
    assert "root-1" not in evidence.root_cause_refs
    assert _result(source).reasons == ["root_cause_ref_missing"]


def test_conflicted_root_evidence_cannot_define_root():
    source = sealed_l2()
    source["fixes"][0]["root_cause_evidence"]["state"] = "conflicted"

    evidence = build_evidence_set(source)
    assert "root-1" not in evidence.root_cause_refs
    assert _result(source).reasons == ["root_cause_ref_missing"]


def test_verified_root_evidence_without_contributing_refs_cannot_define_root():
    source = sealed_l2()
    source["fixes"][0]["root_cause_evidence"]["evidence_refs"] = []

    evidence = build_evidence_set(source)
    assert "root-1" not in evidence.root_cause_refs
    assert _result(source).reasons == ["root_cause_ref_missing"]


def test_structured_root_evidence_refs_cannot_define_root():
    source = sealed_l2()
    source["fixes"][0]["root_cause_evidence"]["evidence_refs"] = [
        {"operator_debug": "https://private.example/debug"}
    ]

    evidence = build_evidence_set(source)
    assert "root-1" not in evidence.root_cause_refs
    assert _result(source).reasons == ["root_cause_ref_missing"]


def test_root_evidence_outside_fix_contract_cannot_define_root():
    source = sealed_l2()
    orphan = deepcopy(source["fixes"][0]["root_cause_evidence"])
    source["fixes"][0].pop("root_cause_evidence")
    source["root_cause_evidence"] = orphan

    evidence = build_evidence_set(source)
    assert "root-1" not in evidence.root_cause_refs
    assert ROOT_URL not in evidence.url_members
    assert _result(source).reasons == ["root_cause_ref_missing"]


def test_invalid_root_evidence_cannot_authorize_its_plausible_url():
    source = sealed_l2()
    source["fixes"][0]["root_cause_evidence"]["state"] = "conflict"

    result = verify_grounded_payload(
        annotation(url=ROOT_URL, root_refs=[]),
        sealed_l2=source,
    )
    assert result.status == "rejected"
    assert result.reasons == ["url_not_in_evidence"]


def test_explicit_root_causes_collection_remains_supported():
    source = sealed_l2()
    source["fixes"][0].pop("root_cause_evidence")
    source["root_causes"] = [
        {
            "root_cause_id": "root-1",
            "details": {"evidence_url": ROOT_URL},
        }
    ]

    evidence = build_evidence_set(source)
    assert "root-1" in evidence.root_cause_refs
    assert ROOT_URL in evidence.url_members
    assert _result(source).status == "verified"
