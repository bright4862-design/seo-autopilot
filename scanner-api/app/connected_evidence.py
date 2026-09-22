"""Pure provider-neutral connected-evidence adapters for FixList NextGen.

This module intentionally performs no network I/O, authentication, persistence,
or customer projection.  It converts already-observed provider payloads/imports
into one stable, provenance-bearing evidence envelope.
"""

from __future__ import annotations

import csv
import io
import math
from datetime import date, datetime, timezone
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlparse

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
MAX_IMPORT_ROWS = 50_000

_GA4_ASSISTANT_HOSTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("chatgpt", ("chatgpt.com", "chat.openai.com")),
    ("perplexity", ("perplexity.ai",)),
    ("claude", ("claude.ai",)),
    ("gemini", ("gemini.google.com",)),
    ("microsoft_copilot", ("copilot.microsoft.com",)),
    ("meta_ai", ("meta.ai",)),
    ("poe", ("poe.com",)),
    ("you", ("you.com",)),
    ("phind", ("phind.com",)),
)


def _parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    else:
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            try:
                parsed_date = date.fromisoformat(text)
            except ValueError:
                return None
            dt = datetime(parsed_date.year, parsed_date.month, parsed_date.day, tzinfo=timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iso(value: Any) -> str | None:
    dt = _parse_datetime(value)
    if dt is None:
        return None
    return dt.isoformat().replace("+00:00", "Z")


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _finite_number(value: Any, *, integer: bool = False) -> int | float | None:
    if value is None or value == "":
        return None
    try:
        number = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        raise ValueError(f"not numeric: {value!r}") from None
    if not math.isfinite(number):
        raise ValueError(f"not finite: {value!r}")
    if integer:
        if not number.is_integer():
            raise ValueError(f"not an integer: {value!r}")
        return int(number)
    return number


def _fraction(value: Any) -> float | None:
    if value is None or value == "":
        return None
    text = str(value).strip()
    percent = text.endswith("%")
    if percent:
        text = text[:-1].strip()
    number = _finite_number(text)
    if number is None:
        return None
    if percent:
        number = float(number) / 100.0
    if not 0 <= float(number) <= 1:
        raise ValueError(f"fraction outside 0..1: {value!r}")
    return float(number)


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


def _row_lookup(row: Mapping[str, Any]) -> dict[str, Any]:
    return {_normalize_header(key): value for key, value in row.items()}


def _pick(row: Mapping[str, Any], *aliases: str) -> Any:
    for alias in aliases:
        key = _normalize_header(alias)
        if key in row and row[key] not in (None, ""):
            return row[key]
        compact = key.replace("_", "")
        for row_key, value in row.items():
            if row_key.replace("_", "") == compact and value not in (None, ""):
                return value
    return None


def _freshness_state(
    *,
    retrieved_at: Any,
    source_observed_at: Any,
    stale_after_days: int | None,
) -> str:
    if stale_after_days is None:
        return "verified"
    if stale_after_days < 0:
        raise ValueError("stale_after_days must be non-negative or None")
    retrieved = _parse_datetime(retrieved_at)
    observed = _parse_datetime(source_observed_at)
    if retrieved is None or observed is None:
        return "not_verified"
    age_seconds = (retrieved - observed).total_seconds()
    if age_seconds < 0:
        return "not_verified"
    return "stale" if age_seconds > stale_after_days * 86400 else "verified"


def _envelope(
    *,
    provider: str,
    source_kind: str,
    state: str,
    retrieved_at: Any,
    surface: str | None = None,
    method: str | None = None,
    observed_at: Any | None = None,
    sample: Mapping[str, Any] | None = None,
    confidence: Mapping[str, Any] | None = None,
    provenance: Mapping[str, Any] | None = None,
    records: Sequence[Mapping[str, Any]] = (),
    coverage: Mapping[str, Any] | None = None,
    reason: str | None = None,
    warnings: Sequence[str] = (),
) -> dict[str, Any]:
    if state not in EVIDENCE_STATES:
        raise ValueError(f"unsupported evidence state: {state}")
    retrieved_iso = _iso(retrieved_at)
    if retrieved_iso is None:
        raise ValueError("retrieved_at must be a parseable timestamp")
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "provider": provider,
        "surface": surface or source_kind,
        "method": method or "normalization",
        "source_kind": source_kind,
        "state": state,
        "retrieved_at": retrieved_iso,
        "observed_at": _iso(observed_at),
        "sample": dict(sample or {"coverage_complete_claim": False}),
        "confidence": dict(
            confidence
            or {
                "kind": "evidence_quality_not_statistical_probability",
                "level": "none" if state in UNAVAILABLE_STATES else "provider_observed",
            }
        ),
        "provenance": dict(provenance or {}),
        "coverage": dict(coverage or {}),
        "records": [dict(record) for record in records],
    }
    if reason:
        result["reason"] = reason
    if warnings:
        result["warnings"] = list(warnings)
    return result


def unavailable_evidence(
    *,
    provider: str,
    source_kind: str,
    state: str,
    reason: str,
    retrieved_at: Any,
    surface: str | None = None,
    method: str | None = None,
    provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return an explicit fail-closed envelope when connected evidence is unavailable."""

    if state not in UNAVAILABLE_STATES:
        raise ValueError(f"state must be one of {sorted(UNAVAILABLE_STATES)}")
    return _envelope(
        provider=provider,
        source_kind=source_kind,
        state=state,
        retrieved_at=retrieved_at,
        surface=surface,
        method=method,
        provenance=provenance,
        reason=reason,
    )


def _bounded_rows(rows: Iterable[Mapping[str, Any]], *, max_rows: int = MAX_IMPORT_ROWS) -> list[Mapping[str, Any]]:
    result: list[Mapping[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        if index > max_rows:
            raise ValueError("provider import exceeds max_rows")
        result.append(row)
    return result


def parse_csv_dict_rows(
    text: str,
    *,
    max_bytes: int = 5_000_000,
    max_rows: int = MAX_IMPORT_ROWS,
) -> list[dict[str, str]]:
    """Parse a bounded UTF-8 CSV export into dictionaries with no provider assumptions."""

    encoded = text.encode("utf-8")
    if len(encoded) > max_bytes:
        raise ValueError("CSV import exceeds max_bytes")
    stream = io.StringIO(text.lstrip("\ufeff"), newline="")
    reader = csv.DictReader(stream)
    if not reader.fieldnames:
        return []
    normalized = [_normalize_header(field) for field in reader.fieldnames]
    if any(not field for field in normalized) or len(set(normalized)) != len(normalized):
        raise ValueError("CSV headers must be non-empty and unique after normalization")
    rows: list[dict[str, str]] = []
    for index, row in enumerate(reader, start=1):
        if index > max_rows:
            raise ValueError("CSV import exceeds max_rows")
        rows.append({str(key): value for key, value in row.items() if key is not None})
    return rows


def normalize_gsc_search_analytics(
    payload: Mapping[str, Any],
    *,
    dimensions: Sequence[str],
    property_uri: str,
    retrieved_at: Any,
    period_start: str | None = None,
    period_end: str | None = None,
    stale_after_days: int | None = 7,
) -> dict[str, Any]:
    """Normalize an already-fetched Google Search Console Search Analytics response."""

    provenance = {
        "transport": "provided_payload",
        "provider_operation": "searchanalytics.query",
        "property_uri": property_uri,
    }
    if payload.get("error"):
        return unavailable_evidence(
            provider="google_search_console",
            source_kind="search_analytics",
            state="provider_error",
            reason="provider payload contained an error",
            retrieved_at=retrieved_at,
            surface="google_search_console.search_analytics",
            method="api_response_normalization",
            provenance=provenance,
        )

    dims = [str(dimension).strip() for dimension in dimensions if str(dimension).strip()]
    if not dims:
        return unavailable_evidence(
            provider="google_search_console",
            source_kind="search_analytics",
            state="not_supported",
            reason="at least one Search Analytics dimension is required",
            retrieved_at=retrieved_at,
            surface="google_search_console.search_analytics",
            method="api_response_normalization",
            provenance=provenance,
        )

    rows = payload.get("rows") or []
    if not isinstance(rows, list):
        return unavailable_evidence(
            provider="google_search_console",
            source_kind="search_analytics",
            state="not_verified",
            reason="Search Analytics rows were not a list",
            retrieved_at=retrieved_at,
            surface="google_search_console.search_analytics",
            method="api_response_normalization",
            provenance=provenance,
        )
    if len(rows) > MAX_IMPORT_ROWS:
        raise ValueError("Search Analytics rows exceed MAX_IMPORT_ROWS")

    records: list[dict[str, Any]] = []
    try:
        for row_number, raw_row in enumerate(rows, start=1):
            if not isinstance(raw_row, Mapping):
                raise ValueError(f"row {row_number} was not an object")
            keys = raw_row.get("keys") or []
            if not isinstance(keys, list) or len(keys) != len(dims):
                raise ValueError(f"row {row_number} dimension/key cardinality mismatch")
            dimension_values = {dimension: str(value) for dimension, value in zip(dims, keys)}
            clicks = _finite_number(raw_row.get("clicks"), integer=True)
            impressions = _finite_number(raw_row.get("impressions"), integer=True)
            ctr = _finite_number(raw_row.get("ctr"))
            position = _finite_number(raw_row.get("position"))
            if clicks is not None and clicks < 0:
                raise ValueError(f"row {row_number} clicks were negative")
            if impressions is not None and impressions < 0:
                raise ValueError(f"row {row_number} impressions were negative")
            if ctr is not None and not 0 <= ctr <= 1:
                raise ValueError(f"row {row_number} ctr was outside 0..1")
            record = {
                "dimensions": dimension_values,
                "clicks": clicks,
                "impressions": impressions,
                "ctr": ctr,
                "position": position,
                "row_number": row_number,
            }
            records.append(record)
    except ValueError as exc:
        return unavailable_evidence(
            provider="google_search_console",
            source_kind="search_analytics",
            state="not_verified",
            reason=str(exc),
            retrieved_at=retrieved_at,
            surface="google_search_console.search_analytics",
            method="api_response_normalization",
            provenance=provenance,
        )

    if period_start is None and "date" in dims:
        dates = [record["dimensions"].get("date") for record in records]
        valid_dates = sorted(value for value in dates if _parse_datetime(value))
        if valid_dates:
            period_start = valid_dates[0]
            period_end = period_end or valid_dates[-1]

    state = _freshness_state(
        retrieved_at=retrieved_at,
        source_observed_at=period_end,
        stale_after_days=stale_after_days,
    )
    if state == "not_verified":
        return unavailable_evidence(
            provider="google_search_console",
            source_kind="search_analytics",
            state="not_verified",
            reason="freshness could not be verified because period_end was unavailable, invalid, or later than retrieval",
            retrieved_at=retrieved_at,
            surface="google_search_console.search_analytics",
            method="api_response_normalization",
            provenance=provenance,
        )
    return _envelope(
        provider="google_search_console",
        source_kind="search_analytics",
        state=state,
        retrieved_at=retrieved_at,
        surface="google_search_console.search_analytics",
        method="api_response_normalization",
        observed_at=period_end,
        sample={"kind": "provider_aggregate_rows", "coverage_complete_claim": False, "row_count": len(records)},
        confidence={"kind": "evidence_quality_not_statistical_probability", "level": "first_party_provider_observed"},
        provenance=provenance,
        coverage={
            "period_start": period_start,
            "period_end": period_end,
            "row_count": len(records),
            "dimensions": dims,
            "response_aggregation_type": _clean_text(payload.get("responseAggregationType")),
        },
        records=records,
    )


def normalize_google_url_inspection(
    payload: Mapping[str, Any],
    *,
    inspection_url: str,
    property_uri: str,
    retrieved_at: Any,
    source_observed_at: Any | None = None,
    stale_after_days: int | None = 7,
) -> dict[str, Any]:
    """Normalize an already-fetched Google Search Console URL Inspection result."""

    provenance = {
        "transport": "provided_payload",
        "provider_operation": "urlInspection.index.inspect",
        "property_uri": property_uri,
        "inspection_url": inspection_url,
    }
    if payload.get("error"):
        return unavailable_evidence(
            provider="google_search_console",
            source_kind="url_inspection",
            state="provider_error",
            reason="provider payload contained an error",
            retrieved_at=retrieved_at,
            surface="google_search_console.url_inspection",
            method="api_response_normalization",
            provenance=provenance,
        )

    inspection_result = payload.get("inspectionResult")
    if not isinstance(inspection_result, Mapping):
        return unavailable_evidence(
            provider="google_search_console",
            source_kind="url_inspection",
            state="not_verified",
            reason="inspectionResult was missing",
            retrieved_at=retrieved_at,
            surface="google_search_console.url_inspection",
            method="api_response_normalization",
            provenance=provenance,
        )
    index = inspection_result.get("indexStatusResult")
    if not isinstance(index, Mapping):
        return unavailable_evidence(
            provider="google_search_console",
            source_kind="url_inspection",
            state="not_verified",
            reason="indexStatusResult was missing",
            retrieved_at=retrieved_at,
            surface="google_search_console.url_inspection",
            method="api_response_normalization",
            provenance=provenance,
        )

    record = {
        "inspection_url": inspection_url,
        "inspection_result_link": _clean_text(inspection_result.get("inspectionResultLink")),
        "verdict": _clean_text(index.get("verdict")),
        "coverage_state": _clean_text(index.get("coverageState")),
        "robots_txt_state": _clean_text(index.get("robotsTxtState")),
        "indexing_state": _clean_text(index.get("indexingState")),
        "page_fetch_state": _clean_text(index.get("pageFetchState")),
        "google_canonical": _clean_text(index.get("googleCanonical")),
        "user_canonical": _clean_text(index.get("userCanonical")),
        "last_crawl_time": _iso(index.get("lastCrawlTime")),
        "crawled_as": _clean_text(index.get("crawledAs")),
        "referring_urls": list(index.get("referringUrls") or []),
        "sitemap": list(index.get("sitemap") or []),
    }
    state = _freshness_state(
        retrieved_at=retrieved_at,
        source_observed_at=source_observed_at or retrieved_at,
        stale_after_days=stale_after_days,
    )
    if state == "not_verified":
        return unavailable_evidence(
            provider="google_search_console",
            source_kind="url_inspection",
            state="not_verified",
            reason="freshness could not be verified because retrieval/observation time was invalid",
            retrieved_at=retrieved_at,
            surface="google_search_console.url_inspection",
            method="api_response_normalization",
            provenance=provenance,
        )
    return _envelope(
        provider="google_search_console",
        source_kind="url_inspection",
        state=state,
        retrieved_at=retrieved_at,
        surface="google_search_console.url_inspection",
        method="api_response_normalization",
        observed_at=source_observed_at or retrieved_at,
        sample={"kind": "single_url_inspection", "coverage_complete_claim": False, "url_count": 1},
        confidence={"kind": "evidence_quality_not_statistical_probability", "level": "first_party_provider_observed"},
        provenance=provenance,
        coverage={"url_count": 1},
        records=[record],
    )


def normalize_bing_ai_performance_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    site_url: str,
    retrieved_at: Any,
    source_observed_at: Any | None = None,
    stale_after_days: int | None = 7,
    import_name: str | None = None,
) -> dict[str, Any]:
    """Normalize manually exported Bing AI Performance rows.

    This is deliberately an import adapter, not a Bing API client.  It accepts
    CSV/Excel-derived dictionaries and does not claim that an AI Performance API
    endpoint exists.
    """

    provenance = {
        "transport": "manual_export",
        "provider_surface": "bing_webmaster_tools_ai_performance",
        "site_url": site_url,
        "import_name": import_name,
        "api_used": False,
    }
    input_rows = _bounded_rows(rows)
    records: list[dict[str, Any]] = []
    rejected = 0
    recognized_headers = False
    observed_dates: list[str] = []

    for row_number, raw in enumerate(input_rows, start=1):
        if not isinstance(raw, Mapping):
            rejected += 1
            continue
        row = _row_lookup(raw)
        date_value = _pick(row, "date", "day")
        url = _clean_text(_pick(row, "url", "page", "page_url", "cited_page", "cited_url"))
        query = _clean_text(_pick(row, "grounding_query", "query", "grounding_phrase"))
        citations_raw = _pick(row, "citations", "citation_count", "total_citations", "citation")
        avg_pages_raw = _pick(row, "average_cited_pages", "avg_cited_pages")
        topic = _clean_text(_pick(row, "topic", "topic_name"))
        intent = _clean_text(_pick(row, "intent", "query_intent"))
        citation_share_raw = _pick(row, "citation_share", "citation share", "share_of_citations")
        geography = _clean_text(_pick(row, "geography"))
        country = _clean_text(_pick(row, "country"))
        region = _clean_text(_pick(row, "region"))
        market = _clean_text(_pick(row, "market"))
        surface = _clean_text(_pick(row, "surface", "ai_surface", "experience", "product"))

        if any(value is not None for value in (date_value, url, query, citations_raw, avg_pages_raw, topic, intent, citation_share_raw, geography, country, region, market, surface)):
            recognized_headers = True
        else:
            rejected += 1
            continue

        try:
            citations = _finite_number(citations_raw, integer=True)
            average_cited_pages = _finite_number(avg_pages_raw)
            citation_share = _fraction(citation_share_raw)
            if citations is not None and citations < 0:
                raise ValueError("citations were negative")
            if average_cited_pages is not None and average_cited_pages < 0:
                raise ValueError("average_cited_pages was negative")
        except ValueError:
            rejected += 1
            continue

        normalized_date = None
        if date_value is not None:
            parsed = _parse_datetime(date_value)
            if parsed is None:
                rejected += 1
                continue
            normalized_date = parsed.date().isoformat()

        if url and query:
            kind = "grounding_query_page"
        elif url:
            kind = "page_citation"
        elif query:
            kind = "grounding_query"
        elif citations is not None or average_cited_pages is not None:
            kind = "summary_or_trend"
        else:
            rejected += 1
            continue

        if normalized_date is not None:
            observed_dates.append(normalized_date)
        records.append(
            {
                "kind": kind,
                "date": normalized_date,
                "url": url,
                "grounding_query": query,
                "citations": citations,
                "average_cited_pages": average_cited_pages,
                "topic": topic,
                "intent": intent,
                "citation_share": citation_share,
                "geography": geography,
                "country": country,
                "region": region,
                "market": market,
                "surface": surface,
                "row_number": row_number,
            }
        )

    if not recognized_headers:
        return unavailable_evidence(
            provider="microsoft_bing_webmaster_tools",
            source_kind="ai_performance_export",
            state="not_supported",
            reason="no supported Bing AI Performance export columns were found",
            retrieved_at=retrieved_at,
            surface="bing_webmaster_tools.ai_performance",
            method="manual_export_normalization",
            provenance=provenance,
        )
    if not records:
        return unavailable_evidence(
            provider="microsoft_bing_webmaster_tools",
            source_kind="ai_performance_export",
            state="not_verified",
            reason="recognized Bing AI Performance rows could not be verified",
            retrieved_at=retrieved_at,
            surface="bing_webmaster_tools.ai_performance",
            method="manual_export_normalization",
            provenance=provenance,
        )

    observed = source_observed_at or (max(observed_dates) if observed_dates else None)
    state = _freshness_state(
        retrieved_at=retrieved_at,
        source_observed_at=observed,
        stale_after_days=stale_after_days,
    )
    if state == "not_verified":
        return unavailable_evidence(
            provider="microsoft_bing_webmaster_tools",
            source_kind="ai_performance_export",
            state="not_verified",
            reason="freshness could not be verified because the export observation date was unavailable, invalid, or later than retrieval",
            retrieved_at=retrieved_at,
            surface="bing_webmaster_tools.ai_performance",
            method="manual_export_normalization",
            provenance=provenance,
        )
    warnings = []
    if rejected:
        warnings.append(f"{rejected} row(s) rejected during normalization")
    return _envelope(
        provider="microsoft_bing_webmaster_tools",
        source_kind="ai_performance_export",
        state=state,
        retrieved_at=retrieved_at,
        surface="bing_webmaster_tools.ai_performance",
        method="manual_export_normalization",
        observed_at=observed,
        sample={"kind": "provider_export_rows", "coverage_complete_claim": False, "row_count": len(records)},
        confidence={
            "kind": "evidence_quality_not_statistical_probability",
            "level": "first_party_provider_observed",
            "limitations": ["citation counts/share are observational and are not ranking or quality scores"],
        },
        provenance=provenance,
        coverage={
            "input_row_count": len(input_rows),
            "normalized_row_count": len(records),
            "rejected_row_count": rejected,
            "period_end": observed,
        },
        records=records,
        warnings=warnings,
    )


def normalize_bing_ai_performance_csv(
    text: str,
    **kwargs: Any,
) -> dict[str, Any]:
    return normalize_bing_ai_performance_rows(parse_csv_dict_rows(text), **kwargs)


def _normalize_source_host(value: Any) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    lowered = text.lower()
    first = lowered.split(" / ", 1)[0].strip()
    candidate = first if "://" in first else f"https://{first}"
    parsed = urlparse(candidate)
    host = (parsed.hostname or first.split("/", 1)[0]).lower().strip(".")
    return host or None


def _classify_ai_assistant(source_value: Any, explicit_assistant: Any = None) -> str | None:
    explicit = _clean_text(explicit_assistant)
    if explicit:
        return _normalize_header(explicit)
    host = _normalize_source_host(source_value)
    if not host:
        return None
    for assistant, domains in _GA4_ASSISTANT_HOSTS:
        for domain in domains:
            if host == domain or host.endswith(f".{domain}"):
                return assistant
    if "chatgpt" in host:
        return "chatgpt"
    return None


def normalize_ga4_ai_referral_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    property_id: str,
    retrieved_at: Any,
    source_observed_at: Any | None = None,
    stale_after_days: int | None = 7,
    import_name: str | None = None,
) -> dict[str, Any]:
    """Normalize aggregate GA4 rows whose referral source is an AI assistant."""

    provenance = {
        "transport": "provided_rows",
        "provider_surface": "ga4_reporting_export_or_response",
        "property_id": property_id,
        "import_name": import_name,
    }
    input_rows = _bounded_rows(rows)
    records: list[dict[str, Any]] = []
    unmatched = 0
    rejected = 0
    saw_source_field = False
    observed_dates: list[str] = []

    for row_number, raw in enumerate(input_rows, start=1):
        if not isinstance(raw, Mapping):
            rejected += 1
            continue
        row = _row_lookup(raw)
        source_medium = _pick(row, "session_source_medium", "source_medium", "session source / medium")
        source = _pick(row, "session_source", "source", "first_user_source") or source_medium
        explicit_assistant = _pick(row, "ai_assistant", "assistant")
        if source is not None or explicit_assistant is not None:
            saw_source_field = True
        assistant = _classify_ai_assistant(source, explicit_assistant)
        if assistant is None:
            unmatched += 1
            continue

        date_value = _pick(row, "date", "day")
        normalized_date = None
        if date_value is not None:
            parsed_date = _parse_datetime(date_value)
            if parsed_date is None:
                rejected += 1
                continue
            normalized_date = parsed_date.date().isoformat()

        try:
            sessions = _finite_number(_pick(row, "sessions"), integer=True)
            engaged_sessions = _finite_number(_pick(row, "engaged_sessions"), integer=True)
            users = _finite_number(_pick(row, "total_users", "active_users", "users"), integer=True)
            key_events = _finite_number(_pick(row, "key_events", "conversions"))
            revenue = _finite_number(_pick(row, "total_revenue", "revenue"))
            for field_name, value in (
                ("sessions", sessions),
                ("engaged_sessions", engaged_sessions),
                ("users", users),
                ("key_events", key_events),
                ("revenue", revenue),
            ):
                if value is not None and value < 0:
                    raise ValueError(f"{field_name} was negative")
        except ValueError:
            rejected += 1
            continue

        if normalized_date is not None:
            observed_dates.append(normalized_date)
        records.append(
            {
                "assistant": assistant,
                "date": normalized_date,
                "source": _clean_text(source),
                "medium": _clean_text(_pick(row, "session_medium", "medium")),
                "landing_page": _clean_text(
                    _pick(
                        row,
                        "landing_page_plus_query_string",
                        "landing_page",
                        "landing page + query string",
                    )
                ),
                "geography": _clean_text(_pick(row, "geography")),
                "country": _clean_text(_pick(row, "country")),
                "region": _clean_text(_pick(row, "region")),
                "device_category": _clean_text(_pick(row, "device_category", "deviceCategory")),
                "sessions": sessions,
                "engaged_sessions": engaged_sessions,
                "users": users,
                "key_events": key_events,
                "revenue": revenue,
                "row_number": row_number,
            }
        )

    if not saw_source_field:
        return unavailable_evidence(
            provider="google_analytics_4",
            source_kind="ai_assistant_referrals",
            state="not_supported",
            reason="no source or explicit AI-assistant field was found",
            retrieved_at=retrieved_at,
            surface="google_analytics_4.referral_traffic",
            method="aggregate_row_normalization",
            provenance=provenance,
        )
    if not records:
        return unavailable_evidence(
            provider="google_analytics_4",
            source_kind="ai_assistant_referrals",
            state="not_verified",
            reason="no recognized AI-assistant referral rows were present",
            retrieved_at=retrieved_at,
            surface="google_analytics_4.referral_traffic",
            method="aggregate_row_normalization",
            provenance=provenance,
        )

    observed = source_observed_at or (max(observed_dates) if observed_dates else None)
    state = _freshness_state(
        retrieved_at=retrieved_at,
        source_observed_at=observed,
        stale_after_days=stale_after_days,
    )
    if state == "not_verified":
        return unavailable_evidence(
            provider="google_analytics_4",
            source_kind="ai_assistant_referrals",
            state="not_verified",
            reason="freshness could not be verified because the analytics observation date was unavailable, invalid, or later than retrieval",
            retrieved_at=retrieved_at,
            surface="google_analytics_4.referral_traffic",
            method="aggregate_row_normalization",
            provenance=provenance,
        )
    warnings = []
    if unmatched:
        warnings.append(f"{unmatched} non-AI or unrecognized referral row(s) excluded")
    if rejected:
        warnings.append(f"{rejected} AI referral row(s) rejected during normalization")
    return _envelope(
        provider="google_analytics_4",
        source_kind="ai_assistant_referrals",
        state=state,
        retrieved_at=retrieved_at,
        surface="google_analytics_4.referral_traffic",
        method="aggregate_row_normalization",
        observed_at=observed,
        sample={"kind": "analytics_aggregate_rows", "coverage_complete_claim": False, "row_count": len(records)},
        confidence={
            "kind": "evidence_quality_not_statistical_probability",
            "level": "first_party_analytics_observed",
            "limitations": ["referral source identifies observed traffic, not all AI mentions or citations"],
        },
        provenance=provenance,
        coverage={
            "input_row_count": len(input_rows),
            "normalized_row_count": len(records),
            "unmatched_row_count": unmatched,
            "rejected_row_count": rejected,
            "period_end": observed,
        },
        records=records,
        warnings=warnings,
    )


def normalize_ga4_ai_referrals_csv(text: str, **kwargs: Any) -> dict[str, Any]:
    return normalize_ga4_ai_referral_rows(parse_csv_dict_rows(text), **kwargs)