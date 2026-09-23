"""Adversarial regressions for the two reported grounding trust-boundary defects."""
from copy import deepcopy

import pytest

from app.grounding_verifier import build_evidence_set, verify_grounded_payload


def snapshot():
    return {
        "authority_seal_version": "authority_v8", "authority_sealed_at": "2026-09-23T00:00:00Z",
        "authority_proof": "offline-fixture-not-a-real-proof", "website_url": "https://example.com",
        "health_score": 88, "status": "complete",
        "pages": [{"url": "https://example.com/real", "status_code": 200}],
        "fixes": [{"fix_id": "fix-1", "affected_urls": ["https://example.com/real"]}],
    }


def claim():
    return {
        "schema_version": "ai_annotation_v2", "annotation_id": "clean",
        "evidence": [{"url": "https://example.com/real#section", "require_live": True}],
        "numeric_claims": [{"source_ref": "$.health_score", "value": 88}],
        "state_claims": [{"source_ref": "$.status", "value": "complete"}],
        "fix_refs": ["fix-1"], "root_cause_refs": [],
    }


@pytest.mark.parametrize("wrapper", ["diagnostics", "metadata", "unknown"])
@pytest.mark.parametrize("location", ["root", "record", "nested_evidence"])
def test_collection_name_cannot_grant_evidence_membership(wrapper, location):
    source = snapshot()
    fake = {
        "pages": [{"url": "https://example.com/forged", "status_code": 200}],
        "fixes": [{"fix_id": "forged-fix"}],
        "root_causes": [{"root_cause_id": "forged-root"}],
        "health_score": 999,
    }
    target = source if location == "root" else source["fixes"][0]
    if location == "nested_evidence":
        target = target.setdefault("evidence", {})
    target[wrapper] = fake
    evidence = build_evidence_set(source)
    assert evidence.url_members == {"https://example.com/real"}
    assert evidence.live_urls == {"https://example.com/real"}
    assert evidence.fix_refs == {"fix-1"}
    assert not evidence.root_cause_refs
    assert all(wrapper not in path for path in evidence.state_values)
    bad = claim()
    bad.update(evidence=[{"url": "https://example.com/forged", "require_live": True}], fix_refs=["forged-fix"], root_cause_refs=["forged-root"])
    result = verify_grounded_payload(bad, evidence_set=evidence)
    assert result.status == "rejected"
    assert result.reasons == ["fix_ref_missing", "root_cause_ref_missing", "url_not_in_evidence"]


@pytest.mark.parametrize("text", [
    "Grounded claim.",
    "See https://example.com/invented.",
    "The health score is 999.",
    "FixList applied the repair.",
    "Le correctif a déjà été appliqué.",
    "There are no remaining issues anywhere on the website.",
])
def test_v1_prose_is_rejected_even_when_declarations_remain_valid(text):
    payload = claim()
    payload.update(schema_version="ai_annotation_v1", text=text)
    payload["numeric_claims"][0]["name"] = "health_score"
    payload["state_claims"][0]["field"] = "status"
    result = verify_grounded_payload(payload, sealed_l2=snapshot())
    assert result.status == "rejected"
    assert result.reasons == ["unconstrained_text_unsupported"]
    assert result.verified_payload is None
    assert result.rendered_annotations == []


def test_v2_clean_claims_render_only_verified_literal_records_without_mutation():
    source, payload = snapshot(), claim()
    before = deepcopy((source, payload))
    result = verify_grounded_payload(payload, sealed_l2=source)
    assert result.status == "verified"
    assert result.verified_payload == payload
    assert result.rendered_annotations == [
        'Evidence URL: "https://example.com/real".\n'
        'Recorded value at "$.health_score": 88.\n'
        'Recorded value at "$.status": "complete".\n'
        'Repair reference: "fix-1".'
    ]
    assert (source, payload) == before


@pytest.mark.parametrize("key,value", [
    ("text", "Health score 999"), ("headline", "Applied repair"), ("template", "Everything is fixed"),
])
def test_v2_has_no_free_prose_slot(key, value):
    payload = claim()
    payload[key] = value
    result = verify_grounded_payload(payload, sealed_l2=snapshot())
    assert result.status == "rejected"
    assert result.reasons == ["schema_invalid"]


@pytest.mark.parametrize("claim_list,label", [("numeric_claims", "name"), ("state_claims", "field")])
def test_v2_cannot_relabel_a_valid_source_as_another_claim(claim_list, label):
    payload = claim()
    payload[claim_list][0][label] = "FixList applied repair"
    assert verify_grounded_payload(payload, sealed_l2=snapshot()).status == "rejected"


def test_diagnostic_scalar_cannot_supply_a_source_bound_claim():
    source = snapshot()
    source["metadata"] = {"health_score": 999, "repair_applied": True}
    payload = claim()
    payload["numeric_claims"] = [{"source_ref": "$.metadata.health_score", "value": 999}]
    payload["state_claims"] = [{"source_ref": "$.metadata.repair_applied", "value": True}]
    result = verify_grounded_payload(payload, sealed_l2=source)
    assert result.status == "rejected"
    assert result.reasons == ["numeric_source_missing", "state_source_missing"]


def test_duplicate_annotation_ids_cannot_make_redaction_ambiguous():
    payload = {"schema_version": "chat_answer_v2", "answer_id": "answer", "annotations": [claim(), claim()]}
    assert verify_grounded_payload(payload, sealed_l2=snapshot()).reasons == ["schema_invalid"]


def test_metadata_changes_do_not_change_evidence_fingerprint():
    source = snapshot()
    expected = build_evidence_set(source).fingerprint
    source["diagnostics"] = {"pages": [{"url": "https://example.com/forged", "status_code": 200}]}
    source["metadata"] = {"health_score": 999}
    assert build_evidence_set(source).fingerprint == expected


def test_large_integer_claim_rejects_without_overflowing_the_verifier():
    payload = claim()
    payload["numeric_claims"][0]["value"] = 10 ** 400
    result = verify_grounded_payload(payload, sealed_l2=snapshot())
    assert result.status == "rejected"
    assert result.reasons == ["numeric_value_mismatch"]
    assert result.rendered_annotations == []


def test_exact_large_integer_source_remains_comparable_without_float_coercion():
    source, payload = snapshot(), claim()
    source["pages_found"] = 10 ** 400
    payload["numeric_claims"] = [{"source_ref": "$.pages_found", "value": 10 ** 400}]
    result = verify_grounded_payload(payload, sealed_l2=source)
    assert result.status == "verified"
    assert result.verified_payload["numeric_claims"][0]["value"] == 10 ** 400
