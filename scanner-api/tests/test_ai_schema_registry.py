from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.ai_schemas import UnknownAISchemaVersion, validate_ai_schema


def annotation(**overrides):
    payload = {
        "schema_version": "ai_annotation_v1",
        "annotation_id": "a1",
        "text": "The page returned 200.",
        "evidence": [{"url": "https://example.com/a", "require_live": True}],
        "numeric_claims": [{"name": "status", "value": 200, "source_ref": "$.pages[0].status_code"}],
        "fix_refs": ["fix-1"],
        "root_cause_refs": ["root-1"],
        "state_claims": [{"field": "scan_status", "value": "complete", "source_ref": "$.scan_status"}],
    }
    payload.update(overrides)
    return payload


def test_ai_annotation_v1_accepts_exact_shape():
    model = validate_ai_schema(annotation())
    assert model.schema_version == "ai_annotation_v1"
    assert model.annotation_id == "a1"


def test_ai_annotation_v1_rejects_extra_fields():
    with pytest.raises(ValidationError):
        validate_ai_schema(annotation(extra="forbidden"))


def test_ai_annotation_v1_requires_evidence():
    with pytest.raises(ValidationError):
        validate_ai_schema(annotation(evidence=[]))


def test_ai_annotation_v1_rejects_extra_nested_fields():
    payload = annotation()
    payload["evidence"][0]["snippet"] = "raw customer content"
    with pytest.raises(ValidationError):
        validate_ai_schema(payload)


def test_chat_answer_v1_accepts_nested_annotations():
    model = validate_ai_schema({
        "schema_version": "chat_answer_v1",
        "answer_id": "answer-1",
        "annotations": [annotation()],
    })
    assert model.schema_version == "chat_answer_v1"
    assert len(model.annotations) == 1


def test_chat_answer_v1_rejects_extra_fields():
    with pytest.raises(ValidationError):
        validate_ai_schema({
            "schema_version": "chat_answer_v1",
            "answer_id": "answer-1",
            "annotations": [annotation()],
            "prompt": "must never be accepted",
        })


def test_unknown_schema_version_fails_closed():
    with pytest.raises(UnknownAISchemaVersion):
        validate_ai_schema({"schema_version": "ai_annotation_v999"})
