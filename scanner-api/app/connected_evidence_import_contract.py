"""Pure import-row ambiguity guards for FixList NextGen connected evidence.

This lane-local helper protects manual/aggregate row imports before the existing
provider normalizers consume them.  It performs no network I/O, authentication,
persistence, scoring, projection, or production mutation.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Mapping
from typing import Any

from .connected_evidence import (
    MAX_IMPORT_ROWS,
    normalize_bing_ai_performance_rows,
    normalize_ga4_ai_referral_rows,
    parse_csv_dict_rows,
)

IMPORT_SHAPE_VERSION = "connected_evidence_import_shape_v1"
CSV_SHAPE_VERSION = "connected_evidence_csv_shape_v1"
MAX_IMPORT_BYTES = 5_000_000

BING_AI_PERFORMANCE_PROFILE = "bing_ai_performance_export"
GA4_AI_REFERRAL_PROFILE = "ga4_ai_assistant_referrals"

_PROFILE_ALIAS_GROUPS: dict[str, dict[str, tuple[str, ...]]] = {
    BING_AI_PERFORMANCE_PROFILE: {
        "date": ("date", "day"),
        "url": ("url", "page", "page_url", "cited_page", "cited_url"),
        "grounding_query": ("grounding_query", "query", "grounding_phrase"),
        "citations": ("citations", "citation_count", "total_citations", "citation"),
        "average_cited_pages": ("average_cited_pages", "avg_cited_pages"),
        "topic": ("topic", "topic_name"),
        "intent": ("intent", "query_intent"),
        "citation_share": ("citation_share", "citation share", "share_of_citations"),
        "geography": ("geography",),
        "country": ("country",),
        "region": ("region",),
        "market": ("market",),
        "surface": ("surface", "ai_surface", "experience", "product"),
    },
    GA4_AI_REFERRAL_PROFILE: {
        "source_medium": (
            "session_source_medium",
            "source_medium",
            "session source / medium",
        ),
        "source": ("session_source", "source", "first_user_source"),
        "assistant": ("ai_assistant", "assistant"),
        "date": ("date", "day"),
        "sessions": ("sessions",),
        "engaged_sessions": ("engaged_sessions",),
        "users": ("total_users", "active_users", "users"),
        "key_events": ("key_events", "conversions"),
        "revenue": ("total_revenue", "revenue"),
        "medium": ("session_medium", "medium"),
        "landing_page": (
            "landing_page_plus_query_string",
            "landing_page",
            "landing page + query string",
        ),
        "geography": ("geography",),
        "country": ("country",),
        "region": ("region",),
        "device_category": ("device_category", "deviceCategory"),
    },
}


def _normalize_header(value: Any) -> str:
    text = str(value or "").strip().lower()
    out: list[str] = []
    previous_sep = False
    for char in text:
        if char.isalnum():
            out.append(char)
            previous_sep = False
        elif not previous_sep:
            out.append("_")
            previous_sep = True
    return "".join(out).strip("_")


def _value_identity(value: Any) -> str:
    if isinstance(value, str):
        return value.strip().casefold()
    return str(value).strip().casefold()


def _validated_import_limits(*, max_bytes: int, max_rows: int) -> tuple[int, int]:
    if (
        isinstance(max_bytes, bool)
        or not isinstance(max_bytes, int)
        or max_bytes <= 0
        or max_bytes > MAX_IMPORT_BYTES
    ):
        raise ValueError(f"max_bytes must be within 1..{MAX_IMPORT_BYTES}")
    if (
        isinstance(max_rows, bool)
        or not isinstance(max_rows, int)
        or max_rows <= 0
        or max_rows > MAX_IMPORT_ROWS
    ):
        raise ValueError(f"max_rows must be within 1..{MAX_IMPORT_ROWS}")
    return max_bytes, max_rows


def parse_connected_evidence_import_csv(
    text: str,
    *,
    max_bytes: int = MAX_IMPORT_BYTES,
    max_rows: int = MAX_IMPORT_ROWS,
) -> list[dict[str, str]]:
    """Parse strict bounded CSV rows without silently dropping ragged fields."""

    max_bytes, max_rows = _validated_import_limits(max_bytes=max_bytes, max_rows=max_rows)
    try:
        encoded = text.encode("utf-8")
    except (AttributeError, UnicodeEncodeError):
        raise ValueError("CSV import must be valid UTF-8 text") from None
    if len(encoded) > max_bytes:
        raise ValueError("CSV import exceeds max_bytes")

    stream = io.StringIO(text.lstrip("\ufeff"), newline="")
    reader = csv.reader(stream)
    try:
        header = next(reader)
    except StopIteration:
        return []
    expected_fields = len(header)
    for row_number, row in enumerate(reader, start=1):
        if row_number > max_rows:
            raise ValueError("CSV import exceeds max_rows")
        if len(row) != expected_fields:
            relation = "more" if len(row) > expected_fields else "fewer"
            raise ValueError(f"CSV row {row_number} has {relation} fields than header")

    return parse_csv_dict_rows(text, max_bytes=max_bytes, max_rows=max_rows)


def _profile_alias_indexes(profile: str) -> tuple[dict[str, str], dict[str, str]]:
    groups = _PROFILE_ALIAS_GROUPS.get(profile)
    if groups is None:
        raise ValueError(f"unsupported connected-evidence import profile: {profile}")

    normalized_to_semantic: dict[str, str] = {}
    compact_to_semantic: dict[str, str] = {}
    for semantic, aliases in groups.items():
        for alias in aliases:
            normalized = _normalize_header(alias)
            compact = normalized.replace("_", "")
            previous = normalized_to_semantic.setdefault(normalized, semantic)
            if previous != semantic:
                raise RuntimeError("import alias registry has an ambiguous normalized header")
            previous_compact = compact_to_semantic.setdefault(compact, semantic)
            if previous_compact != semantic:
                raise RuntimeError("import alias registry has an ambiguous compact header")
    return normalized_to_semantic, compact_to_semantic


def validate_connected_evidence_import_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    profile: str,
    max_rows: int = MAX_IMPORT_ROWS,
) -> list[Mapping[str, Any]]:
    """Fail closed on ambiguous provider-row aliases and return rows unchanged.

    The existing import adapters deliberately recognize several provider/export
    header aliases.  Direct Excel-derived dictionaries can carry more than one
    alias for the same semantic field, and the normalizer's tolerant lookup
    would otherwise let mapping order silently decide which value wins.  This
    guard rejects conflicting aliases as well as normalized/underscore-insensitive
    header collisions that intersect a registered alias.
    """

    _, max_rows = _validated_import_limits(max_bytes=MAX_IMPORT_BYTES, max_rows=max_rows)
    normalized_to_semantic, compact_to_semantic = _profile_alias_indexes(profile)

    result: list[Mapping[str, Any]] = []
    for row_number, row in enumerate(rows, start=1):
        if row_number > max_rows:
            raise ValueError("provider import exceeds max_rows")
        if not isinstance(row, Mapping):
            raise ValueError(f"row {row_number} must be an object")

        seen_normalized: dict[str, str] = {}
        seen_compact: dict[str, str] = {}
        semantic_values: dict[str, set[str]] = {}

        for raw_key, value in row.items():
            normalized = _normalize_header(raw_key)
            if not normalized:
                raise ValueError(f"row {row_number} contains an empty normalized header")
            compact = normalized.replace("_", "")

            semantic = normalized_to_semantic.get(normalized) or compact_to_semantic.get(compact)
            if semantic is None:
                continue

            previous_normalized = seen_normalized.get(normalized)
            if previous_normalized is not None and previous_normalized != str(raw_key):
                raise ValueError(
                    f"row {row_number} has duplicate normalized headers for {semantic}"
                )
            seen_normalized[normalized] = str(raw_key)

            previous_compact = seen_compact.get(compact)
            if previous_compact is not None and previous_compact != normalized:
                raise ValueError(
                    f"row {row_number} has ambiguous compact headers for {semantic}"
                )
            seen_compact[compact] = normalized

            if value not in (None, ""):
                semantic_values.setdefault(semantic, set()).add(_value_identity(value))

        for semantic, identities in semantic_values.items():
            if len(identities) > 1:
                raise ValueError(
                    f"row {row_number} has conflicting aliases for {semantic}"
                )

        result.append(row)
    return result


def normalize_bing_ai_performance_import_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    max_rows: int = MAX_IMPORT_ROWS,
    **kwargs: Any,
) -> dict[str, Any]:
    """Strict manual/Excel-derived Bing import entrypoint."""

    checked = validate_connected_evidence_import_rows(
        rows,
        profile=BING_AI_PERFORMANCE_PROFILE,
        max_rows=max_rows,
    )
    return normalize_bing_ai_performance_rows(checked, **kwargs)


def normalize_bing_ai_performance_import_csv(
    text: str,
    *,
    max_bytes: int = MAX_IMPORT_BYTES,
    max_rows: int = MAX_IMPORT_ROWS,
    **kwargs: Any,
) -> dict[str, Any]:
    """Strict bounded CSV Bing import entrypoint."""

    rows = parse_connected_evidence_import_csv(text, max_bytes=max_bytes, max_rows=max_rows)
    return normalize_bing_ai_performance_import_rows(rows, max_rows=max_rows, **kwargs)


def normalize_ga4_ai_referral_import_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    max_rows: int = MAX_IMPORT_ROWS,
    **kwargs: Any,
) -> dict[str, Any]:
    """Strict aggregate/Excel-derived GA4 import entrypoint."""

    checked = validate_connected_evidence_import_rows(
        rows,
        profile=GA4_AI_REFERRAL_PROFILE,
        max_rows=max_rows,
    )
    return normalize_ga4_ai_referral_rows(checked, **kwargs)


def normalize_ga4_ai_referral_import_csv(
    text: str,
    *,
    max_bytes: int = MAX_IMPORT_BYTES,
    max_rows: int = MAX_IMPORT_ROWS,
    **kwargs: Any,
) -> dict[str, Any]:
    """Strict bounded CSV GA4 import entrypoint."""

    rows = parse_connected_evidence_import_csv(text, max_bytes=max_bytes, max_rows=max_rows)
    return normalize_ga4_ai_referral_import_rows(rows, max_rows=max_rows, **kwargs)
