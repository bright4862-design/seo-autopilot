"""Versioned registry for AI envelopes.

Unknown versions fail closed; callers do not get best-effort coercion to a
nearby schema.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from .v1 import AIAnnotationV1, ChatAnswerV1, EvidenceRefV1, NumericClaimV1, StateClaimV1


class UnknownAISchemaVersion(ValueError):
    pass


SCHEMA_REGISTRY: dict[str, type[BaseModel]] = {
    "ai_annotation_v1": AIAnnotationV1,
    "chat_answer_v1": ChatAnswerV1,
}


def validate_ai_schema(payload: Any) -> BaseModel:
    if not isinstance(payload, dict):
        raise UnknownAISchemaVersion("AI payload must be an object with schema_version")
    version = payload.get("schema_version")
    if not isinstance(version, str) or version not in SCHEMA_REGISTRY:
        raise UnknownAISchemaVersion(f"unsupported AI schema version: {version!r}")
    return SCHEMA_REGISTRY[version].model_validate(payload)


__all__ = [
    "AIAnnotationV1",
    "ChatAnswerV1",
    "EvidenceRefV1",
    "NumericClaimV1",
    "StateClaimV1",
    "SCHEMA_REGISTRY",
    "UnknownAISchemaVersion",
    "validate_ai_schema",
]
