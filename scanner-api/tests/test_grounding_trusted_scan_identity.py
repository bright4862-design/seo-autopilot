from __future__ import annotations

from app.grounding_verifier import build_evidence_set, verify_grounded_payload


REAL_URL = "https://example.com/real"
FOREIGN_URL = "https://example.com/foreign-root-evidence"


def root_evidence(*, evidence_url: str = REAL_URL) -> dict:
    return {
        "version": "root_cause_evidence_v1_verified",
        "state": "verified",
        "root_cause_id": "root-shared",
        "repair_surface_id": "surface:template",
        "evidence_refs": [evidence_url],
    }


def fix(fix_id: str, *, scan_id: str | None = None, scan_run_id: str | None = None, evidence_url: str = REAL_URL) -> dict:
    payload = {
        "fix_id": fix_id,
        "root_cause_evidence": root_evidence(evidence_url=evidence_url),
    }
    if scan_id is not None:
        payload["scan_id"] = scan_id
    if scan_run_id is not None:
        payload["scan_run_id"] = scan_run_id
    return payload


def sealed_l2(
    *,
    producer_scan_id: str | None = "scan-trusted",
    producer_scan_run_id: str | None = "scan-trusted",
    fixes: list[dict] | None = None,
    nested_v8_source: bool = False,
) -> dict:
    source = {
        "authority_seal_version": "authority_v8",
        "authority_sealed_at": "2026-09-23T07:00:00Z",
        "authority_proof": "trusted-scan-grounding-proof",
        "website_url": "https://example.com",
        "pages": [{"url": REAL_URL, "status_code": 200}],
        "fixes": fixes or [fix("fix-1"), fix("fix-2")],
    }
    if producer_scan_id is None and producer_scan_run_id is None:
        return source

    handoff = {
        "handoff_version": "fixlist_handoff_v2",
        "scan": {
            **({"scan_id": producer_scan_id} if producer_scan_id is not None else {}),
            **({"scan_run_id": producer_scan_run_id} if producer_scan_run_id is not None else {}),
        },
    }
    if nested_v8_source:
        source["health_score_explanation"] = {
            "stage3_delivery": {"handoff_v2_source": handoff}
        }
    else:
        source["stage3_handoff_v2_source"] = handoff
    return source


def annotation(*, url: str = REAL_URL) -> dict:
    return {
        "schema_version": "ai_annotation_v2",
        "annotation_id": "trusted-scan-root",

        "evidence": [{"url": url, "require_live": False}],
        "numeric_claims": [],
        "fix_refs": [],
        "root_cause_refs": ["root-shared"],
        "state_claims": [],
    }


def test_exact_trusted_scan_identity_allows_shared_root_grouping_without_local_assertions():
    evidence = build_evidence_set(sealed_l2())

    assert "root-shared" in evidence.root_cause_refs
    assert "root-shared" not in evidence.ambiguous_root_cause_refs
    assert verify_grounded_payload(annotation(), evidence_set=evidence).status == "verified"


def test_matching_repair_local_scan_identity_allows_shared_root_grouping():
    source = sealed_l2(
        fixes=[
            fix("fix-1", scan_id="scan-trusted", scan_run_id="scan-trusted"),
            fix("fix-2", scan_id="scan-trusted", scan_run_id="scan-trusted"),
        ]
    )
    evidence = build_evidence_set(source)

    assert "root-shared" not in evidence.ambiguous_root_cause_refs
    assert verify_grounded_payload(annotation(), evidence_set=evidence).status == "verified"


def test_foreign_repair_local_identity_cannot_join_trusted_shared_root_or_authorize_url():
    source = sealed_l2(
        fixes=[
            fix("fix-1"),
            fix(
                "fix-2",
                scan_id="foreign-scan",
                scan_run_id="foreign-scan",
                evidence_url=FOREIGN_URL,
            ),
        ]
    )
    evidence = build_evidence_set(source)

    assert "root-shared" in evidence.root_cause_refs
    assert "root-shared" not in evidence.ambiguous_root_cause_refs
    assert FOREIGN_URL not in evidence.url_members
    assert verify_grounded_payload(annotation(), evidence_set=evidence).status == "verified"
    rejected = verify_grounded_payload(annotation(url=FOREIGN_URL), evidence_set=evidence)
    assert rejected.status == "rejected"
    assert rejected.reasons == ["url_not_in_evidence"]


def test_all_foreign_members_cannot_manufacture_grounded_root():
    source = sealed_l2(
        fixes=[
            fix("fix-1", scan_id="foreign-scan", scan_run_id="foreign-scan"),
            fix("fix-2", scan_id="foreign-scan", scan_run_id="foreign-scan"),
        ]
    )
    evidence = build_evidence_set(source)

    assert "root-shared" not in evidence.root_cause_refs
    result = verify_grounded_payload(annotation(), evidence_set=evidence)
    assert result.status == "rejected"
    assert result.reasons == ["root_cause_ref_missing"]


def test_mismatched_producer_scan_identity_fails_closed_for_nested_root_evidence():
    evidence = build_evidence_set(
        sealed_l2(producer_scan_id="scan-trusted", producer_scan_run_id="different-run")
    )

    assert "root-shared" not in evidence.root_cause_refs
    result = verify_grounded_payload(annotation(), evidence_set=evidence)
    assert result.status == "rejected"
    assert result.reasons == ["root_cause_ref_missing"]


def test_repeated_root_without_sealed_producer_identity_does_not_coalesce():
    source = sealed_l2(producer_scan_id=None, producer_scan_run_id=None)
    evidence = build_evidence_set(source)

    assert evidence.ambiguous_root_cause_refs == frozenset({"root-shared"})
    result = verify_grounded_payload(annotation(), evidence_set=evidence)
    assert result.status == "rejected"
    assert result.reasons == ["root_cause_ref_ambiguous"]


def test_v8_nested_handoff_source_supplies_trusted_scan_identity():
    source = sealed_l2(nested_v8_source=True)
    evidence = build_evidence_set(source)

    assert "root-shared" not in evidence.ambiguous_root_cause_refs
    assert verify_grounded_payload(annotation(), evidence_set=evidence).status == "verified"
