"""Constrained claims for deterministic rendering; no caller-authored prose.

A claim has a source path and exact value. Human labels cannot rename another
field into a health score, a repair result, or a statement about authority.
"""
from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from .v1 import _StrictModel, EvidenceRefV1, NumericClaimV1, StateClaimV1, Scalar


class NumericClaimV2(_StrictModel):
    value: int | float
    source_ref: str = Field(min_length=1, max_length=1024)

    _finite_number = field_validator("value")(NumericClaimV1.finite_number.__func__)


class StateClaimV2(_StrictModel):
    value: Scalar
    source_ref: str = Field(min_length=1, max_length=1024)

    _finite_scalar = field_validator("value")(StateClaimV1.finite_scalar.__func__)


class AIAnnotationV2(_StrictModel):
    schema_version: Literal["ai_annotation_v2"]
    annotation_id: str = Field(min_length=1, max_length=160)
    evidence: list[EvidenceRefV1] = Field(min_length=1, max_length=64)
    numeric_claims: list[NumericClaimV2] = Field(default_factory=list, max_length=64)
    fix_refs: list[str] = Field(default_factory=list, max_length=128)
    root_cause_refs: list[str] = Field(default_factory=list, max_length=128)
    state_claims: list[StateClaimV2] = Field(default_factory=list, max_length=64)

    @field_validator("fix_refs", "root_cause_refs")
    @classmethod
    def nonempty_refs(cls, values: list[str]) -> list[str]:
        if any(not value.strip() or len(value) > 512 for value in values):
            raise ValueError("references must be non-empty and bounded")
        return values


class ChatAnswerV2(_StrictModel):
    schema_version: Literal["chat_answer_v2"]
    answer_id: str = Field(min_length=1, max_length=160)
    annotations: list[AIAnnotationV2] = Field(min_length=1, max_length=128)

    @field_validator("annotations")
    @classmethod
    def unique_annotations(cls, values: list[AIAnnotationV2]) -> list[AIAnnotationV2]:
        if len({item.annotation_id for item in values}) != len(values):
            raise ValueError("annotation identifiers must be unique")
        return values
