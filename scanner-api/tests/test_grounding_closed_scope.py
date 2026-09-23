"""Closed-scope regressions for offline grounding evidence construction."""
from __future__ import annotations

import pytest

from app.grounding_verifier import (
    EvidenceUnavailable,
    build_evidence_set,
    build_evidence_set_from_authenticated_snapshot,
    verify_grounded_payload,
)


def snapshot() -> dict:
    return {
        "authority_seal_version": "authority_v8",
        "authority_sealed_at": "2026-09-23T00:00:00Z",
        "authority_proof": "offline-fixture-not-a-real-proof",
        "website_url": "https://example.com",
        "status": "complete",
        "health_score": 88,
        "pages": [
            {
                "url": "https://example.com/real",
                "status_code": 200,
                "invented_score": 999,
            }
        ],
        "fixes": [{"fix_id": "fix-1", "affected_urls": ["https://example.com/real"]}],
        "root_causes": [{"root_cause_id": "root-1"}],
    }


def annotation(**overrides) -> dict:
    payload = {
        "schema_version": "ai_annotation_v1",
        "annotation_id": "closed-scope",
        "text": "Grounded evidence is available for this annotation.",
        "evidence": [{"url": "https://example.com/real", "require_live": True}],
        "numeric_claims": [{"name": "health_score", "value": 88, "source_ref": "$.health_score"}],
        "fix_refs": ["fix-1"],
        "root_cause_refs": ["root-1"],
        "state_claims": [{"field": "status", "value": "complete", "source_ref": "$.status"}],
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize("wrapper", ["diagnostics", "metadata"])
def test_nested_collection_names_cannot_manufacture_evidence(wrapper):
    source = snapshot()
    source[wrapper] = {
        "pages": [{"url": "https://example.com/forged", "status_code": 200}],
        "fixes": [{"fix_id": "forged-fix"}],
        "root_causes": [{"root_cause_id": "forged-root"}],
    }

    evidence = build_evidence_set(source)

    assert "https://example.com/forged" not in evidence.url_members
    assert "https://example.com/forged" not in evidence.live_urls
    assert "forged-fix" not in evidence.fix_refs
    assert "forged-root" not in evidence.root_cause_refs


def test_known_absolute_collection_paths_preserve_clean_control():
    result = verify_grounded_payload(annotation(), sealed_l2=snapshot())
    assert result.status == "verified"


def test_arbitrary_page_scalar_is_not_a_claim_source():
    result = verify_grounded_payload(
        annotation(
            numeric_claims=[
                {"name": "invented_score", "value": 999, "source_ref": "$.pages[0].invented_score"}
            ]
        ),
        sealed_l2=snapshot(),
    )
    assert result.status == "rejected"
    assert result.reasons == ["numeric_source_missing"]


def test_explicit_page_status_scalar_remains_available():
    result = verify_grounded_payload(
        annotation(
            numeric_claims=[
                {"name": "status_code", "value": 200, "source_ref": "$.pages[0].status_code"}
            ]
        ),
        sealed_l2=snapshot(),
    )
    assert result.status == "verified"


def test_seal_markers_alone_do_not_satisfy_authenticated_adapter():
    with pytest.raises(EvidenceUnavailable, match="sealed_l2_authentication_failed"):
        build_evidence_set_from_authenticated_snapshot(snapshot(), authenticate_snapshot=lambda _source: False)


def test_authenticated_adapter_accepts_only_explicit_true_and_preserves_input():
    source = snapshot()
    seen: list[dict] = []

    def authenticate(candidate: dict) -> bool:
        seen.append(candidate)
        return True

    evidence = build_evidence_set_from_authenticated_snapshot(source, authenticate_snapshot=authenticate)
    assert seen == [source]
    assert evidence == build_evidence_set(source)


@pytest.mark.parametrize("outcome", [1, "true", None])
def test_authenticated_adapter_rejects_truthy_non_boolean_results(outcome):
    with pytest.raises(EvidenceUnavailable, match="sealed_l2_authentication_failed"):
        build_evidence_set_from_authenticated_snapshot(snapshot(), authenticate_snapshot=lambda _source: outcome)


def test_authenticated_adapter_converts_authenticator_errors_to_unavailable():
    def fail(_source: dict) -> bool:
        raise RuntimeError("do not leak verifier details")

    with pytest.raises(EvidenceUnavailable, match="sealed_l2_authentication_failed"):
        build_evidence_set_from_authenticated_snapshot(snapshot(), authenticate_snapshot=fail)
