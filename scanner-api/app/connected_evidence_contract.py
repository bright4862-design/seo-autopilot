"""Strict validation for FixList NextGen connected-evidence envelopes.

This module is deliberately pure: it performs no network I/O, authentication,
persistence, scoring, or customer projection. Provider adapters may emit
``connected_evidence_v1`` envelopes; this validator gives the serialized
integrator one fail-closed boundary before any later use of that evidence.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Mapping

SCHEMA_VERSION = "connected_evidence_v1"
EVIDENCE_STATES = frozenset(
    {
        "verified",
        "not_connected",
        "not_supported",
        "not_verified",
        "stale",
        "provider_error",
    }
)
UNAVAILABLE_STATES = frozenset(
    {"not_connected", "not_supported", "not_verified", "provider_error"}
)

_REQUIRED_TOP_LEVEL = frozenset(
    {
        "schema_version",
        "provider",
        "surface",
        "method",
        "source_kind",
        "state",
        "retrieved_at",
        "observed_at",
        "sample",
        "confidence",
        "provenance",
        "coverage",
        "records",
    }
)
_OPTIONAL_TOP_LEVEL = frozenset({"reason", "warnings"})
_MAX_RECORDS = 50_000
_MAX_KEYS_PER_MAPPING = 256
_MAX_STRING_LENGTH = 16_384
_MAX_REASON_LENGTH = 2_000
_MAX_WARNINGS = 100
_MAX_WARNING_LENGTH = 1_000
_MAX_RECORD_JSON_BYTES = 262_144
_MAX_METADATA_JSON_BYTES = 131_072


def _timestamp(value: Any, *, field: str, required: bool) -> datetime | None:
    if value is None:
        if required:
            raise ValueError(f"{field} is required")
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be an RFC3339 string or null")
    text = value.strip()
    if len(text) > 64:
        raise ValueError(f"{field} is too long")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise ValueError(f"{field} must be an RFC3339 timestamp") from None
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _bounded_string(value: Any, *, field: str, max_length: int = _MAX_STRING_LENGTH) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    text = value.strip()
    if len(text) > max_length:
        raise ValueError(f"{field} exceeds its size bound")
    return text


def _mapping(value: Any, *, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    if len(value) > _MAX_KEYS_PER_MAPPING:
        raise ValueError(f"{field} has too many keys")
    if any(not isinstance(key, str) or not key for key in value):
        raise ValueError(f"{field} keys must be non-empty strings")
    return value


def _json_mapping(
    value: Any,
    *,
    field: str,
    max_bytes: int = _MAX_METADATA_JSON_BYTES,
) -> Mapping[str, Any]:
    mapping = _mapping(value, field=field)
    try:
        encoded = json.dumps(
            mapping,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError):
        raise ValueError(f"{field} must be strict JSON-serializable") from None
    if len(encoded) > max_bytes:
        raise ValueError(f"{field} exceeds its size bound")
    return mapping


def _validate_record(record: Any, *, index: int) -> None:
    mapping = _mapping(record, field=f"records[{index}]")
    try:
        encoded = json.dumps(
            mapping,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError):
        raise ValueError(f"records[{index}] must be strict JSON-serializable") from None
    if len(encoded) > _MAX_RECORD_JSON_BYTES:
        raise ValueError(f"records[{index}] exceeds its size bound")


def validate_connected_evidence(evidence: Mapping[str, Any]) -> Mapping[str, Any]:
    """Validate one ``connected_evidence_v1`` envelope and return it unchanged.

    Validation is intentionally strict. Unknown top-level fields require a
    schema-version change instead of silently changing the authenticated shape
    later. Unavailable states may never carry observed records or observational
    sample/coverage claims; stale evidence retains records but must identify
    when the source was observed.
    """

    top = _mapping(evidence, field="connected evidence")
    keys = frozenset(top)
    missing = _REQUIRED_TOP_LEVEL - keys
    unknown = keys - _REQUIRED_TOP_LEVEL - _OPTIONAL_TOP_LEVEL
    if missing:
        raise ValueError(f"connected evidence missing fields: {sorted(missing)}")
    if unknown:
        raise ValueError(f"connected evidence has unknown fields: {sorted(unknown)}")

    if top["schema_version"] != SCHEMA_VERSION:
        raise ValueError("unsupported connected-evidence schema version")
    _bounded_string(top["provider"], field="provider", max_length=200)
    _bounded_string(top["surface"], field="surface", max_length=300)
    _bounded_string(top["method"], field="method", max_length=300)
    _bounded_string(top["source_kind"], field="source_kind", max_length=300)

    state = top["state"]
    if state not in EVIDENCE_STATES:
        raise ValueError("unsupported connected-evidence state")

    retrieved_at = _timestamp(top["retrieved_at"], field="retrieved_at", required=True)
    observed_at = _timestamp(top["observed_at"], field="observed_at", required=False)
    if observed_at is not None and retrieved_at is not None and observed_at > retrieved_at:
        raise ValueError("observed_at cannot be later than retrieved_at")

    sample = _json_mapping(top["sample"], field="sample")
    if type(sample.get("coverage_complete_claim")) is not bool:
        raise ValueError("sample.coverage_complete_claim must be an explicit boolean")

    confidence = _json_mapping(top["confidence"], field="confidence")
    if confidence.get("kind") != "evidence_quality_not_statistical_probability":
        raise ValueError("confidence.kind must describe evidence quality, not probability")
    level = _bounded_string(confidence.get("level"), field="confidence.level", max_length=200)

    provenance = _json_mapping(top["provenance"], field="provenance")
    transport = provenance.get("transport")
    if state in UNAVAILABLE_STATES:
        if transport is not None:
            _bounded_string(transport, field="provenance.transport", max_length=200)
    else:
        _bounded_string(transport, field="provenance.transport", max_length=200)
    coverage = _json_mapping(top["coverage"], field="coverage")

    records = top["records"]
    if not isinstance(records, list):
        raise ValueError("records must be a list")
    if len(records) > _MAX_RECORDS:
        raise ValueError("records exceed the connected-evidence row bound")
    for index, record in enumerate(records):
        _validate_record(record, index=index)

    reason = top.get("reason")
    if reason is not None:
        _bounded_string(reason, field="reason", max_length=_MAX_REASON_LENGTH)

    warnings = top.get("warnings", [])
    if not isinstance(warnings, list) or len(warnings) > _MAX_WARNINGS:
        raise ValueError("warnings must be a bounded list")
    for index, warning in enumerate(warnings):
        _bounded_string(warning, field=f"warnings[{index}]", max_length=_MAX_WARNING_LENGTH)

    if state in UNAVAILABLE_STATES:
        if records:
            raise ValueError("unavailable connected evidence cannot carry records")
        if observed_at is not None:
            raise ValueError("unavailable connected evidence cannot claim observed_at")
        if level != "none":
            raise ValueError("unavailable connected evidence must use confidence.level=none")
        if reason is None:
            raise ValueError("unavailable connected evidence requires a reason")
        if sample != {"coverage_complete_claim": False}:
            raise ValueError(
                "unavailable connected evidence cannot claim sample observations"
            )
        if coverage:
            raise ValueError(
                "unavailable connected evidence cannot claim coverage observations"
            )
    else:
        if level == "none":
            raise ValueError("observed connected evidence cannot use confidence.level=none")

    if state == "stale":
        if observed_at is None:
            raise ValueError("stale connected evidence requires observed_at")
        if retrieved_at is not None and observed_at >= retrieved_at:
            raise ValueError("stale connected evidence observed_at must predate retrieved_at")

    return evidence
