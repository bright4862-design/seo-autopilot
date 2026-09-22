"""Record-level semantic validation for FixList NextGen connected evidence.

The generic connected-evidence contract validates envelope shape and chronology,
and the source-profile contract validates provider/source attribution.  This
third pure boundary validates the meaning of normalized records so a
well-shaped envelope cannot carry internally contradictory or spoof-prone
provider observations.

No network I/O, authentication, persistence, scoring, projection, or production
mutation is performed here.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

from .connected_evidence_source_contract import validate_connected_evidence_source_identity

RECORD_SEMANTICS_VERSION = "connected_evidence_record_semantics_v1"

_GA4_ASSISTANT_DOMAINS: dict[str, tuple[str, ...]] = {
    "chatgpt": ("chatgpt.com", "chat.openai.com"),
    "perplexity": ("perplexity.ai",),
    "claude": ("claude.ai",),
    "gemini": ("gemini.google.com",),
    "microsoft_copilot": ("copilot.microsoft.com",),
    "meta_ai": ("meta.ai",),
    "poe": ("poe.com",),
    "you": ("you.com",),
    "phind": ("phind.com",),
}

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


def _bounded_text(value: Any, *, field: str, max_length: int = 4096) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    text = value.strip()
    if len(text) > max_length:
        raise ValueError(f"{field} exceeds its size bound")
    return text


def _absolute_http_url(value: Any, *, field: str) -> str:
    text = _bounded_text(value, field=field)
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"{field} must be an absolute HTTP(S) URL")
    return text


def _finite_number(value: Any, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a numeric JSON value")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    return number


def _non_negative_number(value: Any, *, field: str) -> float:
    number = _finite_number(value, field=field)
    if number < 0:
        raise ValueError(f"{field} must be non-negative")
    return number


def _non_negative_integer(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    if value < 0:
        raise ValueError(f"{field} must be non-negative")
    return value


def _positive_row_number(record: Mapping[str, Any], *, index: int) -> int:
    value = record.get("row_number")
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"records[{index}].row_number must be a positive integer")
    return value


def _validate_unique_row_numbers(records: Sequence[Mapping[str, Any]]) -> None:
    seen: set[int] = set()
    for index, record in enumerate(records):
        row_number = _positive_row_number(record, index=index)
        if row_number in seen:
            raise ValueError("record row_number values must be unique")
        seen.add(row_number)


def _parse_timestamp(value: Any, *, field: str) -> datetime:
    text = _bounded_text(value, field=field, max_length=128)
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from None
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _normalize_assistant_token(value: Any, *, field: str) -> str:
    text = _bounded_text(value, field=field, max_length=128).lower()
    normalized = "_".join(part for part in "".join(char if char.isalnum() else " " for char in text).split())
    canonical = _GA4_ASSISTANT_ALIASES.get(normalized)
    if canonical is None:
        raise ValueError(f"{field} is not a registered AI assistant")
    return canonical


def _source_host(value: Any, *, field: str) -> str:
    text = _bounded_text(value, field=field, max_length=2048).lower()
    first = text.split(" / ", 1)[0].strip()
    candidate = first if "://" in first else f"https://{first}"
    parsed = urlparse(candidate)
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        raise ValueError(f"{field} did not contain a valid source host")
    return host


def _assistant_for_source(value: Any, *, field: str) -> str | None:
    host = _source_host(value, field=field)
    for assistant, domains in _GA4_ASSISTANT_DOMAINS.items():
        if any(host == domain or host.endswith(f".{domain}") for domain in domains):
            return assistant
    return None


def _validate_gsc_search_analytics(records: Sequence[Mapping[str, Any]]) -> None:
    _validate_unique_row_numbers(records)
    for index, record in enumerate(records):
        dimensions = record.get("dimensions")
        if not isinstance(dimensions, Mapping) or not dimensions:
            raise ValueError(f"records[{index}].dimensions must be a non-empty object")
        for dimension, value in dimensions.items():
            _bounded_text(dimension, field=f"records[{index}].dimensions key", max_length=128)
            if not isinstance(value, str):
                raise ValueError(f"records[{index}].dimensions values must be strings")

        clicks = record.get("clicks")
        impressions = record.get("impressions")
        ctr = record.get("ctr")
        position = record.get("position")
        if clicks is not None:
            _non_negative_integer(clicks, field=f"records[{index}].clicks")
        if impressions is not None:
            _non_negative_integer(impressions, field=f"records[{index}].impressions")
        if clicks is not None and impressions is not None and clicks > impressions:
            raise ValueError(f"records[{index}] clicks cannot exceed impressions")
        if ctr is not None:
            ctr_value = _finite_number(ctr, field=f"records[{index}].ctr")
            if not 0 <= ctr_value <= 1:
                raise ValueError(f"records[{index}].ctr must be within 0..1")
        if position is not None:
            _non_negative_number(position, field=f"records[{index}].position")


def _validate_url_inspection(
    evidence: Mapping[str, Any], records: Sequence[Mapping[str, Any]]
) -> None:
    if evidence["state"] not in {"verified", "stale"}:
        return
    if len(records) != 1:
        raise ValueError("URL Inspection observed evidence must contain exactly one record")
    record = records[0]
    index = 0
    for field in ("inspection_result_link", "google_canonical", "user_canonical"):
        value = record.get(field)
        if value not in (None, ""):
            _absolute_http_url(value, field=f"records[{index}].{field}")

    for field in ("referring_urls", "sitemap"):
        values = record.get(field)
        if values is None:
            continue
        if not isinstance(values, list):
            raise ValueError(f"records[{index}].{field} must be a list")
        for item_index, value in enumerate(values):
            _absolute_http_url(value, field=f"records[{index}].{field}[{item_index}]")

    last_crawl_time = record.get("last_crawl_time")
    if last_crawl_time not in (None, ""):
        crawled = _parse_timestamp(last_crawl_time, field=f"records[{index}].last_crawl_time")
        retrieved = _parse_timestamp(evidence["retrieved_at"], field="retrieved_at")
        if crawled > retrieved:
            raise ValueError("URL Inspection last_crawl_time cannot be later than retrieved_at")


def _validate_bing_ai_performance(records: Sequence[Mapping[str, Any]]) -> None:
    _validate_unique_row_numbers(records)
    allowed_kinds = {"grounding_query_page", "page_citation", "grounding_query", "summary_or_trend"}
    for index, record in enumerate(records):
        kind = record.get("kind")
        if kind not in allowed_kinds:
            raise ValueError(f"records[{index}].kind is unsupported")
        has_url = isinstance(record.get("url"), str) and bool(record.get("url", "").strip())
        has_query = isinstance(record.get("grounding_query"), str) and bool(record.get("grounding_query", "").strip())
        expected_kind = (
            "grounding_query_page"
            if has_url and has_query
            else "page_citation"
            if has_url
            else "grounding_query"
            if has_query
            else "summary_or_trend"
        )
        if kind != expected_kind:
            raise ValueError(f"records[{index}].kind contradicts URL/query identity")
        if kind == "summary_or_trend" and record.get("citations") is None and record.get("average_cited_pages") is None:
            raise ValueError(f"records[{index}] summary_or_trend lacks measurable evidence")

        citations = record.get("citations")
        average_cited_pages = record.get("average_cited_pages")
        citation_share = record.get("citation_share")
        if citations is not None:
            _non_negative_integer(citations, field=f"records[{index}].citations")
        if average_cited_pages is not None:
            _non_negative_number(average_cited_pages, field=f"records[{index}].average_cited_pages")
        if citation_share is not None:
            share = _finite_number(citation_share, field=f"records[{index}].citation_share")
            if not 0 <= share <= 1:
                raise ValueError(f"records[{index}].citation_share must be within 0..1")


def _validate_ga4_ai_referrals(records: Sequence[Mapping[str, Any]]) -> None:
    _validate_unique_row_numbers(records)
    for index, record in enumerate(records):
        assistant = _normalize_assistant_token(record.get("assistant"), field=f"records[{index}].assistant")
        source = record.get("source")
        if source not in (None, ""):
            source_assistant = _assistant_for_source(source, field=f"records[{index}].source")
            if source_assistant is None:
                raise ValueError(f"records[{index}].source is not a registered AI-assistant host")
            if source_assistant != assistant:
                raise ValueError(f"records[{index}].assistant contradicts source host")

        for field in ("sessions", "engaged_sessions", "users"):
            value = record.get(field)
            if value is not None:
                _non_negative_integer(value, field=f"records[{index}].{field}")
        for field in ("key_events", "revenue"):
            value = record.get(field)
            if value is not None:
                _non_negative_number(value, field=f"records[{index}].{field}")


def validate_connected_evidence_record_semantics(
    evidence: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Validate normalized provider records and return ``evidence`` unchanged.

    This function intentionally composes after source-identity validation.  It
    fails closed when record semantics are contradictory, ambiguous, or rely on
    spoof-prone source labels.  Unavailable evidence has no records under the
    generic contract and therefore needs no record-level observation proof.
    """

    validate_connected_evidence_source_identity(evidence)
    records = evidence["records"]
    if not isinstance(records, list):
        raise ValueError("records must be a list")
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise ValueError(f"records[{index}] must be an object")

    profile_key = (evidence["provider"], evidence["source_kind"])
    if profile_key == ("google_search_console", "search_analytics"):
        _validate_gsc_search_analytics(records)
    elif profile_key == ("google_search_console", "url_inspection"):
        _validate_url_inspection(evidence, records)
    elif profile_key == ("microsoft_bing_webmaster_tools", "ai_performance_export"):
        _validate_bing_ai_performance(records)
    elif profile_key == ("google_analytics_4", "ai_assistant_referrals"):
        _validate_ga4_ai_referrals(records)
    else:
        raise ValueError("unsupported connected-evidence provider/source_kind profile")
    return evidence
