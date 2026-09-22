"""Pure provider-shape adapters for NextGen browser/performance evidence.

These helpers accept already-observed provider payloads only. They make no
network calls and create no credentials. Field (CrUX) and lab (Lighthouse)
evidence remain separate.
"""
from __future__ import annotations

from datetime import date
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app.nextgen_browser_performance import (
    PERFORMANCE_EVIDENCE_VERSION,
    PSI_FIELD_KEYS,
    PROVIDER_STATES,
    normalize_field_performance_evidence,
    normalize_lighthouse_evidence,
)

PROVIDER_ADAPTER_VERSION = "nextgen_performance_provider_adapter_v1"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if number < 0 or number != number or number in {float("inf"), float("-inf")} else number


def _http_identity(value: Any) -> str | None:
    raw = _text(value)
    if not raw:
        return None
    try:
        parsed = urlsplit(raw)
    except Exception:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    path = parsed.path or ("/" if parsed.scheme and parsed.netloc else "")
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.query, ""))


def _iso_date(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    try:
        parsed = date(int(value["year"]), int(value["month"]), int(value["day"]))
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    return parsed.isoformat()


def _coverage(record: dict[str, Any]) -> dict[str, str] | None:
    period = record.get("collectionPeriod")
    if not isinstance(period, dict):
        return None
    first_date = _iso_date(period.get("firstDate"))
    last_date = _iso_date(period.get("lastDate"))
    if not first_date or not last_date or first_date > last_date:
        return None
    return {"first_date": first_date, "last_date": last_date}


def _unavailable_crux(*, reason: str, state: str = "unavailable",
    observed_at: str | None = None, scope: str | None = None,
    source_url: str | None = None) -> dict[str, Any]:
    evidence = normalize_field_performance_evidence(
        provider="CrUX", state=state, scope=scope, observed_at=observed_at,
        source_url=source_url, reason=reason,
    )
    return {**evidence, "adapter_version": PROVIDER_ADAPTER_VERSION, "coverage_period": None}


def normalize_crux_query_record_evidence(payload: dict[str, Any] | None, *,
    state: str = "connected", observed_at: str | None = None,
    scope: str | None = None, source_url: str | None = None,
    reason: str | None = None) -> dict[str, Any]:
    """Normalize the documented CrUX ``queryRecord`` envelope fail-closed.

    The record key is authoritative for URL-vs-origin scope. Caller-supplied
    scope/source identity may corroborate it but may not contradict it.
    """
    normalized_state = _text(state).lower()
    if normalized_state not in PROVIDER_STATES:
        normalized_state = "unavailable"
        return _unavailable_crux(
            reason=reason or "provider_state_invalid", state=normalized_state,
            observed_at=observed_at, scope=scope, source_url=source_url,
        )
    if normalized_state != "connected":
        return _unavailable_crux(
            reason=reason or normalized_state, state=normalized_state,
            observed_at=observed_at, scope=scope, source_url=source_url,
        )
    if not isinstance(payload, dict):
        return _unavailable_crux(
            reason=reason or "provider_payload_missing", observed_at=observed_at,
            scope=scope, source_url=source_url,
        )
    record = payload.get("record")
    if not isinstance(record, dict):
        return _unavailable_crux(
            reason=reason or "crux_record_missing", observed_at=observed_at,
            scope=scope, source_url=source_url,
        )
    key = record.get("key") if isinstance(record.get("key"), dict) else {}
    key_url = _http_identity(key.get("url"))
    key_origin = _http_identity(key.get("origin"))
    if bool(key_url) == bool(key_origin):
        return _unavailable_crux(
            reason=reason or "crux_record_key_invalid", observed_at=observed_at,
            scope=scope, source_url=source_url,
        )
    inferred_scope = "url" if key_url else "origin"
    record_source = key_url or key_origin
    requested_scope = _text(scope).lower() or None
    if requested_scope is not None and requested_scope not in {"url", "origin"}:
        return _unavailable_crux(
            reason=reason or "crux_scope_invalid", observed_at=observed_at,
            scope=requested_scope, source_url=source_url,
        )
    if requested_scope is not None and requested_scope != inferred_scope:
        return _unavailable_crux(
            reason=reason or "crux_scope_mismatch", observed_at=observed_at,
            scope=requested_scope, source_url=source_url,
        )
    requested_source = _http_identity(source_url) if source_url is not None else None
    if source_url is not None and requested_source is None:
        return _unavailable_crux(
            reason=reason or "crux_source_identity_invalid", observed_at=observed_at,
            scope=inferred_scope, source_url=source_url,
        )
    if requested_source is not None and requested_source != record_source:
        return _unavailable_crux(
            reason=reason or "crux_record_identity_mismatch", observed_at=observed_at,
            scope=inferred_scope, source_url=source_url,
        )
    metrics = record.get("metrics")
    if not isinstance(metrics, dict) or not metrics:
        return _unavailable_crux(
            reason=reason or "crux_record_metrics_unavailable", observed_at=observed_at,
            scope=inferred_scope, source_url=record_source,
        )
    evidence = normalize_field_performance_evidence(
        provider="CrUX", state="connected", metrics=metrics,
        scope=inferred_scope, observed_at=observed_at,
        source_url=record_source, reason=reason,
    )
    return {
        **evidence,
        "adapter_version": PROVIDER_ADAPTER_VERSION,
        "coverage_period": _coverage(record),
    }


def _psi_metrics(experience: Any) -> dict[str, Any]:
    if not isinstance(experience, dict) or not isinstance(experience.get("metrics"), dict):
        return {}
    mapped: dict[str, Any] = {}
    for raw_key, canonical in PSI_FIELD_KEYS.items():
        item = experience["metrics"].get(raw_key)
        if not isinstance(item, dict):
            continue
        percentile = item.get("percentile")
        if canonical == "cls" and _number(percentile) is not None:
            percentile = float(percentile) / 100.0
        if _number(percentile) is None:
            continue
        mapped[canonical] = {"p75": percentile, "rating": item.get("category")}
    return mapped


def _psi_field_candidate(payload: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    url_metrics = _psi_metrics(payload.get("loadingExperience"))
    if url_metrics:
        return url_metrics, "url"
    origin_metrics = _psi_metrics(payload.get("originLoadingExperience"))
    if origin_metrics:
        return origin_metrics, "origin"
    return None, None


def normalize_pagespeed_insights_evidence_strict(payload: dict[str, Any] | None, *,
    state: str = "connected", observed_at: str | None = None,
    source_url: str | None = None, reason: str | None = None) -> dict[str, Any]:
    """Normalize PSI and fall back to origin field data only when URL data is unusable."""
    normalized_state = _text(state).lower()
    if normalized_state not in PROVIDER_STATES:
        normalized_state, failure_reason = "unavailable", reason or "provider_state_invalid"
    elif normalized_state != "connected":
        failure_reason = reason or normalized_state
    elif not isinstance(payload, dict):
        normalized_state, failure_reason = "unavailable", reason or "provider_payload_missing"
    else:
        failure_reason = None

    if normalized_state != "connected":
        return {
            "version": PERFORMANCE_EVIDENCE_VERSION,
            "provider": "PageSpeed Insights",
            "adapter_version": PROVIDER_ADAPTER_VERSION,
            "field": normalize_field_performance_evidence(
                provider="PageSpeed Insights / CrUX", state=normalized_state,
                observed_at=observed_at, source_url=source_url, reason=failure_reason,
            ),
            "lab": normalize_lighthouse_evidence(
                None, provider="PageSpeed Insights / Lighthouse", state=normalized_state,
                observed_at=observed_at, source_url=source_url, reason=failure_reason,
            ),
        }

    field_values, field_scope = _psi_field_candidate(payload)
    field = normalize_field_performance_evidence(
        provider="PageSpeed Insights / CrUX",
        state="connected" if field_values else "unavailable",
        metrics=field_values, scope=field_scope, observed_at=observed_at,
        source_url=source_url,
        reason=None if field_values else "crux_field_data_unavailable",
    )
    lighthouse = payload.get("lighthouseResult") if isinstance(payload.get("lighthouseResult"), dict) else None
    lab = normalize_lighthouse_evidence(
        lighthouse, provider="PageSpeed Insights / Lighthouse",
        state="connected" if lighthouse else "unavailable",
        observed_at=observed_at, source_url=source_url,
        reason=None if lighthouse else "lighthouse_lab_data_unavailable",
    )
    return {
        "version": PERFORMANCE_EVIDENCE_VERSION,
        "provider": "PageSpeed Insights",
        "adapter_version": PROVIDER_ADAPTER_VERSION,
        "field": field,
        "lab": lab,
    }
