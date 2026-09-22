"""Semantic record-identity integrity for FixList NextGen connected evidence.

This pure guard composes after envelope/source/record/coverage/scope validation
and proves that one evidence envelope cannot carry the same logical provider row
more than once under different transport row numbers. It performs no network
I/O, authentication, persistence, scoring, projection, or production mutation.
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from .connected_evidence_scope_contract import (
    validate_connected_evidence_scope_semantics,
)

RECORD_IDENTITY_VERSION = "connected_evidence_record_identity_v1"

_UNAVAILABLE_STATES = frozenset(
    {"not_connected", "not_supported", "not_verified", "provider_error"}
)

_GA4_ASSISTANT_ALIASES: dict[str, str] = {
    "chatgpt": "chatgpt",
    "openai_chatgpt": "chatgpt",
    "perplexity": "perplexity",
    "perplexity_ai": "perplexity",
    "claude": "claude",
    "anthropic_claude": "claude",
    "gemini": "gemini",
    "google_gemini": "gemini",
    "microsoft_copilot": "microsoft_copilot",
    "copilot": "microsoft_copilot",
    "bing_chat": "microsoft_copilot",
    "meta_ai": "meta_ai",
    "poe": "poe",
    "you": "you",
    "you_com": "you",
    "phind": "phind",
}


def _identity_text(value: Any, *, field: str, allow_none: bool = True) -> str | None:
    if value is None and allow_none:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    text = value.strip()
    if not text:
        if allow_none:
            return None
        raise ValueError(f"{field} must be a non-empty string")
    if len(text) > 4096:
        raise ValueError(f"{field} exceeds its size bound")
    return text


def _canonical_ga4_assistant_identity(value: Any, *, field: str) -> str:
    text = _identity_text(value, field=field, allow_none=False)
    assert text is not None
    normalized = "_".join(
        part
        for part in "".join(
            char if char.isalnum() else " " for char in text.lower()
        ).split()
    )
    canonical = _GA4_ASSISTANT_ALIASES.get(normalized)
    if canonical is None:
        raise ValueError(f"{field} is not a registered AI assistant")
    return canonical


def _record_identity(
    evidence: Mapping[str, Any],
    record: Mapping[str, Any],
    *,
    index: int,
) -> tuple[Any, ...]:
    profile_key = (evidence["provider"], evidence["source_kind"])

    if profile_key == ("google_search_console", "search_analytics"):
        dimensions = evidence["coverage"].get("dimensions")
        if not isinstance(dimensions, list) or not dimensions:
            raise ValueError("coverage.dimensions must be a non-empty list")
        values: list[str] = []
        record_dimensions = record.get("dimensions")
        if not isinstance(record_dimensions, Mapping):
            raise ValueError(f"records[{index}].dimensions must be an object")
        for dimension_index, dimension in enumerate(dimensions):
            dimension_name = _identity_text(
                dimension,
                field=f"coverage.dimensions[{dimension_index}]",
                allow_none=False,
            )
            value = _identity_text(
                record_dimensions.get(dimension_name),
                field=f"records[{index}].dimensions.{dimension_name}",
                allow_none=False,
            )
            values.append(value)
        return profile_key + tuple(values)

    if profile_key == ("google_search_console", "url_inspection"):
        return profile_key + (
            _identity_text(
                record.get("inspection_url"),
                field=f"records[{index}].inspection_url",
                allow_none=False,
            ),
        )

    if profile_key == (
        "microsoft_bing_webmaster_tools",
        "ai_performance_export",
    ):
        fields = (
            "kind",
            "date",
            "url",
            "grounding_query",
            "topic",
            "intent",
            "geography",
            "country",
            "region",
            "market",
            "surface",
        )
        return profile_key + tuple(
            _identity_text(
                record.get(field),
                field=f"records[{index}].{field}",
                allow_none=field != "kind",
            )
            for field in fields
        )

    if profile_key == ("google_analytics_4", "ai_assistant_referrals"):
        assistant = _canonical_ga4_assistant_identity(
            record.get("assistant"), field=f"records[{index}].assistant"
        )
        fields = (
            "date",
            "source",
            "medium",
            "landing_page",
            "geography",
            "country",
            "region",
            "device_category",
        )
        return profile_key + (assistant,) + tuple(
            _identity_text(
                record.get(field),
                field=f"records[{index}].{field}",
                allow_none=True,
            )
            for field in fields
        )

    raise ValueError("unsupported connected-evidence provider/source_kind profile")


def connected_evidence_record_identity(
    evidence: Mapping[str, Any],
    record: Mapping[str, Any],
    *,
    index: int,
) -> str:
    """Return one deterministic logical-record identity after full item validation."""

    validate_connected_evidence_scope_semantics(evidence)
    if not isinstance(record, Mapping):
        raise ValueError(f"records[{index}] must be an object")
    identity = _record_identity(evidence, record, index=index)
    return json.dumps(identity, separators=(",", ":"), ensure_ascii=False)


def validate_connected_evidence_record_identity_semantics(
    evidence: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Reject duplicate logical provider rows and return ``evidence`` unchanged.

    Provider row numbers are transport positions, not semantic identities. Two
    rows with the same provider dimensions but different row numbers would make
    later aggregation order-dependent or double-count evidence, so they fail
    closed instead of being silently summed. Accepted GA4 assistant aliases are
    canonicalized for identity so spelling aliases cannot evade duplicate-row
    detection.
    """

    validate_connected_evidence_scope_semantics(evidence)

    if evidence["state"] in _UNAVAILABLE_STATES:
        return evidence

    records = evidence["records"]
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes, bytearray)):
        raise ValueError("records must be a sequence")

    seen: dict[tuple[Any, ...], int] = {}
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise ValueError(f"records[{index}] must be an object")
        identity = _record_identity(evidence, record, index=index)
        previous = seen.get(identity)
        if previous is not None:
            raise ValueError(
                "duplicate connected-evidence logical record at "
                f"records[{previous}] and records[{index}]"
            )
        seen[identity] = index

    return evidence
