from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from app.grounding_verifier import build_evidence_set, verify_grounded_payload

FIXTURE = Path(__file__).with_name("fixtures") / "grounding_v8_sealed_l2_v1.json"


def sealed_l2() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["sealed_l2"]


def annotation(**overrides):
    payload = {
        "schema_version": "ai_annotation_v1",
        "annotation_id": "v8-grounded",
        "text": "Grounded V8 evidence.",
        "evidence": [
            {
                "url": "https://example.com/products/CaseSensitive?variant=1#hero",
                "require_live": True,
            }
        ],
        "numeric_claims": [
            {
                "name": "adjusted_health_score",
                "value": 73,
                "source_ref": "$.health_score_explanation.stage3_delivery.health_score_decision.adjusted_health_score",
            }
        ],
        "fix_refs": ["fix:canonical-template"],
        "root_cause_refs": ["root:canonical-template"],
        "state_claims": [
            {"field": "status", "value": "complete", "source_ref": "$.status"}
        ],
    }
    payload.update(overrides)
    return payload


def test_v8_stage3_handoff_published_and_request_urls_are_members():
    evidence = build_evidence_set(sealed_l2())
    assert "https://example.com/products/CaseSensitive?variant=1" in evidence.url_members
    assert "https://example.com/products/CaseSensitive?variant=1&utm_source=x" in evidence.url_members


def test_v8_stage3_handoff_rule_id_is_a_fix_identity_only_inside_fixes_container():
    source = sealed_l2()
    source["diagnostics"]["rule_id"] = "not-a-fix"
    evidence = build_evidence_set(source)
    assert "fix:canonical-template" in evidence.fix_refs
    assert "not-a-fix" not in evidence.fix_refs


def test_v8_nested_root_cause_and_fix_refs_verify():
    result = verify_grounded_payload(annotation(), sealed_l2=sealed_l2())
    assert result.status == "verified"


def test_v8_verified_payload_preserves_exact_refs_and_fragment():
    payload = annotation()
    result = verify_grounded_payload(payload, sealed_l2=sealed_l2())
    assert result.status == "verified"
    assert result.verified_payload == payload


def test_v8_duplicate_url_identities_collapse_for_membership_without_rewriting_payload():
    evidence = build_evidence_set(sealed_l2())
    canonical = "https://example.com/products/CaseSensitive?variant=1"
    assert canonical in evidence.url_members
    assert sum(member == canonical for member in evidence.url_members) == 1
    result = verify_grounded_payload(annotation(), evidence_set=evidence)
    assert result.verified_payload["evidence"][0]["url"].endswith("#hero")


def test_v8_non_identifier_source_paths_are_addressable_exactly():
    payload = annotation(
        numeric_claims=[
            {
                "name": "diagnostic_count",
                "value": 2,
                "source_ref": '$.diagnostics["count.total"]',
            }
        ],
        state_claims=[
            {
                "field": "coverage_state",
                "value": "sufficient",
                "source_ref": '$.diagnostics["coverage-state"]',
            }
        ],
    )
    result = verify_grounded_payload(payload, sealed_l2=sealed_l2())
    assert result.status == "verified"


def test_numeric_provenance_rejects_integer_float_type_drift():
    payload = annotation(
        numeric_claims=[{"name": "health_score", "value": 73.0, "source_ref": "$.health_score"}]
    )
    result = verify_grounded_payload(payload, sealed_l2=sealed_l2())
    assert result.status == "rejected"
    assert "numeric_value_mismatch" in result.reasons


def test_state_provenance_rejects_integer_float_type_drift():
    payload = annotation(
        numeric_claims=[],
        state_claims=[{"field": "health_score", "value": 73.0, "source_ref": "$.health_score"}],
    )
    result = verify_grounded_payload(payload, sealed_l2=sealed_l2())
    assert result.status == "rejected"
    assert "state_value_mismatch" in result.reasons


def test_equal_python_numbers_with_different_json_types_are_a_deterministic_conflict():
    first = annotation(annotation_id="a", numeric_claims=[{"name": "score", "value": 73, "source_ref": "$.health_score"}])
    second = annotation(annotation_id="b", numeric_claims=[{"name": "score", "value": 73.0, "source_ref": "$.health_score"}])
    result = verify_grounded_payload(
        {"schema_version": "chat_answer_v1", "answer_id": "conflict", "annotations": [first, second]},
        sealed_l2=sealed_l2(),
    )
    assert result.status == "rejected"
    assert result.reasons == ["deterministic_conflict"]


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("authority_seal_version", ""),
        ("authority_sealed_at", None),
        ("authority_proof", {"unexpected": "object"}),
    ],
)
def test_malformed_v8_seal_markers_return_unavailable(field, bad_value):
    source = sealed_l2()
    source[field] = bad_value
    result = verify_grounded_payload(annotation(), sealed_l2=source)
    assert result.status == "unavailable"
    assert result.reasons[0].startswith("sealed_l2_markers_missing:")


def test_v8_evidence_set_is_deterministic_and_input_is_immutable():
    source = sealed_l2()
    before = deepcopy(source)
    first = build_evidence_set(source)
    second = build_evidence_set(deepcopy(source))
    assert first.fingerprint == second.fingerprint
    assert source == before
