"""Strict v1 envelopes for future AI output.

These models intentionally carry references, not copied L2 evidence. The
Grounding Verifier resolves every reference against sealed evidence before any
future caller may use the content.
"""
from __future__ import annotations

from math import isfinite
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class EvidenceRefV1(_StrictModel):
    url: str = Field(min_length=1, max_length=4096)
    require_live: bool = False


class NumericClaimV1(_StrictModel):
    name: str = Field(min_length=1, max_length=160)
    value: int | float
    source_ref: str = Field(min_length=1, max_length=1024)

    @field_validator("value")
    @classmethod
    def finite_number(cls, value: int | float) -> int | float:
        if isinstance(value, bool) or (isinstance(value, float) and not isfinite(value)):
            raise ValueError("numeric claim must be finite")
        return value


Scalar = str | int | float | bool


class StateClaimV1(_StrictModel):
    field: str = Field(min_length=1, max_length=160)
    value: Scalar
    source_ref: str = Field(min_length=1, max_length=1024)

    @field_validator("value")
    @classmethod
    def finite_scalar(cls, value: Scalar) -> Scalar:
        if isinstance(value, float) and not isfinite(value):
            raise ValueError("state claim float must be finite")
        return value


class AIAnnotationV1(_StrictModel):
    schema_version: Literal["ai_annotation_v1"]
    annotation_id: str = Field(min_length=1, max_length=160)
    text: str = Field(min_length=1, max_length=12000)
    evidence: list[EvidenceRefV1] = Field(min_length=1, max_length=64)
    numeric_claims: list[NumericClaimV1] = Field(default_factory=list, max_length=64)
    fix_refs: list[str] = Field(default_factory=list, max_length=128)
    root_cause_refs: list[str] = Field(default_factory=list, max_length=128)
    state_claims: list[StateClaimV1] = Field(default_factory=list, max_length=64)

    @field_validator("fix_refs", "root_cause_refs")
    @classmethod
    def nonempty_refs(cls, values: list[str]) -> list[str]:
        if any(not value or len(value) > 512 for value in values):
            raise ValueError("references must be non-empty and bounded")
        return values


class ChatAnswerV1(_StrictModel):
    schema_version: Literal["chat_answer_v1"]
    answer_id: str = Field(min_length=1, max_length=160)
    annotations: list[AIAnnotationV1] = Field(min_length=1, max_length=128)
