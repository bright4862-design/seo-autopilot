from __future__ import annotations

from copy import deepcopy

import pytest

from app.grounding_verifier import EvidenceUnavailable, build_evidence_set, verify_grounded_payload


def sealed_l2():
    return {
        "authority_seal_version": "authority_v8",
        "authority_sealed_at": "2026-09-22T15:00:00Z",
        "authority_proof": "abc123",
        "website_url": "https://example.com",
        "scan_status": "complete",
        "health_score": 88,
        "pages": [
            {"url": "https://example.com/a", "final_url": "https://example.com/a", "status_code": 200},
            {"url": "https://example.com/b", "status_code": 404},
        ],
        "fixes": [
            {"fix_id": "fix-1", "repair_fingerprint": "fp-1", "affected_urls": ["https://example.com/a"]}
        ],
        "root_causes": [
            {"root_cause_id": "root-1", "state": "verified", "evidence_refs": ["https://example.com/a"]}
        ],
    }


def ann(annotation_id="a1", **overrides):
    payload = {
        "schema_version": "ai_annotation_v1",
        "annotation_id": annotation_id,
        "text": "Grounded claim.",
        "evidence": [{"url": "https://example.com/a", "require_live": True}],
        "numeric_claims": [{"name": "health_score", "value": 88, "source_ref": "$.health_score"}],
        "fix_refs": ["fix-1"],
        "root_cause_refs": ["root-1"],
        "state_claims": [{"field": "scan_status", "value": "complete", "source_ref": "$.scan_status"}],
    }
    payload.update(overrides)
    return payload


def answer(*annotations):
    return {"schema_version": "chat_answer_v1", "answer_id": "answer-1", "annotations": list(annotations)}


def test_evidence_set_is_deterministic_and_reuses_published_identity():
    left = build_evidence_set(sealed_l2())
    right = build_evidence_set(deepcopy(sealed_l2()))
    assert left.fingerprint == right.fingerprint
    assert "https://example.com/a" in left.url_members
    assert "https://example.com/a" in left.live_urls
    assert "https://example.com/b" in left.url_members
    assert "https://example.com/b" not in left.live_urls


def test_evidence_set_requires_seal_markers():
    raw = sealed_l2()
    del raw["authority_proof"]
    with pytest.raises(EvidenceUnavailable):
        build_evidence_set(raw)


def test_clean_annotation_verifies():
    result = verify_grounded_payload(ann(), sealed_l2=sealed_l2())
    assert result.status == "verified"
    assert result.verified_payload["annotation_id"] == "a1"


def test_fabricated_plausible_url_is_rejected():
    bad = ann(evidence=[{"url": "https://example.com/plausible-but-fake", "require_live": False}])
    result = verify_grounded_payload(bad, sealed_l2=sealed_l2())
    assert result.status == "rejected"
    assert "url_not_in_evidence" in result.reasons


def test_nonlive_url_fails_when_liveness_is_required():
    bad = ann(evidence=[{"url": "https://example.com/b", "require_live": True}])
    result = verify_grounded_payload(bad, sealed_l2=sealed_l2())
    assert result.status == "rejected"
    assert "url_not_live" in result.reasons


def test_observed_nonlive_url_can_be_cited_without_live_requirement():
    good = ann(evidence=[{"url": "https://example.com/b", "require_live": False}])
    result = verify_grounded_payload(good, sealed_l2=sealed_l2())
    assert result.status == "verified"


def test_fabricated_count_is_rejected_by_numeric_provenance():
    bad = ann(numeric_claims=[{"name": "health_score", "value": 89, "source_ref": "$.health_score"}])
    result = verify_grounded_payload(bad, sealed_l2=sealed_l2())
    assert result.status == "rejected"
    assert "numeric_value_mismatch" in result.reasons


def test_missing_numeric_source_is_rejected():
    bad = ann(numeric_claims=[{"name": "count", "value": 1, "source_ref": "$.invented.count"}])
    result = verify_grounded_payload(bad, sealed_l2=sealed_l2())
    assert result.status == "rejected"
    assert "numeric_source_missing" in result.reasons


def test_fabricated_fix_id_is_rejected():
    result = verify_grounded_payload(ann(fix_refs=["fix-999"]), sealed_l2=sealed_l2())
    assert result.status == "rejected"
    assert "fix_ref_missing" in result.reasons


def test_fabricated_root_cause_id_is_rejected():
    result = verify_grounded_payload(ann(root_cause_refs=["root-999"]), sealed_l2=sealed_l2())
    assert result.status == "rejected"
    assert "root_cause_ref_missing" in result.reasons


def test_authority_or_state_claim_must_match_exact_source():
    bad = ann(state_claims=[{"field": "scan_status", "value": "partial", "source_ref": "$.scan_status"}])
    result = verify_grounded_payload(bad, sealed_l2=sealed_l2())
    assert result.status == "rejected"
    assert "state_value_mismatch" in result.reasons


def test_deterministic_conflict_rejects_entire_answer():
    a1 = ann("a1")
    a2 = ann("a2", numeric_claims=[{"name": "health_score", "value": 87, "source_ref": "$.health_score"}])
    result = verify_grounded_payload(answer(a1, a2), sealed_l2=sealed_l2())
    assert result.status == "rejected"
    assert "deterministic_conflict" in result.reasons


def test_independent_bad_annotation_is_structurally_redacted():
    good = ann("good")
    bad = ann("bad", fix_refs=["fix-fake"])
    result = verify_grounded_payload(answer(good, bad), sealed_l2=sealed_l2())
    assert result.status == "redacted"
    assert result.redacted_annotation_ids == ["bad"]
    assert [item["annotation_id"] for item in result.verified_payload["annotations"]] == ["good"]


def test_all_bad_annotations_reject_instead_of_emitting_empty_answer():
    result = verify_grounded_payload(answer(ann("bad", fix_refs=["fix-fake"])), sealed_l2=sealed_l2())
    assert result.status == "rejected"


def test_missing_sealed_l2_returns_unavailable():
    result = verify_grounded_payload(ann(), sealed_l2=None)
    assert result.status == "unavailable"
    assert result.verified_payload is None


def test_verification_does_not_mutate_inputs():
    source = sealed_l2()
    payload = ann()
    source_before = deepcopy(source)
    payload_before = deepcopy(payload)
    verify_grounded_payload(payload, sealed_l2=source)
    assert source == source_before
    assert payload == payload_before
