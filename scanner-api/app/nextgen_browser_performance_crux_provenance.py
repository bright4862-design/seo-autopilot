"""Strict source/coverage provenance binding for direct CrUX queryRecord evidence.

This module is additive and pure. It accepts already-observed CrUX ``queryRecord``
payloads, performs no network I/O, creates no credentials, and never grants provider
execution budget. It strengthens the base provider adapter by requiring an unambiguous
record key, a true origin identity for origin-scoped records, and a valid collection
period before connected field measurements can be trusted.
"""
from __future__ import annotations

from datetime import date
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app.nextgen_browser_performance_contract import validate_field_performance_contract
from app.nextgen_browser_performance_provider import (
    PROVIDER_ADAPTER_VERSION,
    normalize_crux_query_record_evidence,
)

CRUX_BOUND_ADAPTER_VERSION = "nextgen_crux_bound_provider_v1"
CRUX_PROVENANCE_VERSION = "nextgen_crux_provenance_v1"
CRUX_BOUND_INTEGRITY_VERSION = "nextgen_crux_bound_integrity_v1"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _http_identity(value: Any) -> str | None:
    raw = _text(value)
    if not raw:
        return None
    try:
        parsed = urlsplit(raw)
    except Exception:
        return None
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.netloc
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None
    return urlunsplit((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        parsed.path or "/",
        parsed.query,
        "",
    ))


def _origin_identity(value: Any) -> str | None:
    identity = _http_identity(value)
    if identity is None:
        return None
    parsed = urlsplit(identity)
    if parsed.path != "/" or parsed.query:
        return None
    return urlunsplit((parsed.scheme, parsed.netloc, "/", "", ""))


def _iso_date(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    try:
        parsed = date(int(value["year"]), int(value["month"]), int(value["day"]))
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    return parsed.isoformat()


def _coverage(record: Any) -> dict[str, str] | None:
    if not isinstance(record, dict):
        return None
    period = record.get("collectionPeriod")
    if not isinstance(period, dict):
        return None
    first_date = _iso_date(period.get("firstDate"))
    last_date = _iso_date(period.get("lastDate"))
    if not first_date or not last_date or first_date > last_date:
        return None
    return {"first_date": first_date, "last_date": last_date}


def _record_identity(record: Any) -> tuple[str | None, str | None, str | None]:
    if not isinstance(record, dict):
        return None, None, "crux_record_missing"
    key = record.get("key")
    if not isinstance(key, dict):
        return None, None, "crux_record_key_invalid"
    raw_url = key.get("url")
    raw_origin = key.get("origin")
    has_url = bool(_text(raw_url))
    has_origin = bool(_text(raw_origin))
    if has_url == has_origin:
        return None, None, "crux_record_key_invalid"
    if has_url:
        identity = _http_identity(raw_url)
        return ("url", identity, None) if identity else (
            None, None, "crux_record_url_identity_invalid"
        )
    identity = _origin_identity(raw_origin)
    return ("origin", identity, None) if identity else (
        None, None, "crux_record_origin_identity_invalid"
    )


def _provenance(
    *,
    record_scope: str | None,
    record_source_url: str | None,
    requested_scope: str | None,
    requested_source_url: str | None,
    coverage_period: dict[str, str] | None,
    observed_at: str | None,
) -> dict[str, Any]:
    return {
        "version": CRUX_PROVENANCE_VERSION,
        "record_scope": record_scope,
        "record_source_url": record_source_url,
        "requested_scope": requested_scope,
        "requested_source_url": requested_source_url,
        "coverage_period": coverage_period,
        "observed_at": _text(observed_at) or None,
    }


def _with_metadata(evidence: dict[str, Any], provenance: dict[str, Any]) -> dict[str, Any]:
    return {
        **evidence,
        "adapter_version": CRUX_BOUND_ADAPTER_VERSION,
        "base_adapter_version": PROVIDER_ADAPTER_VERSION,
        "provenance": provenance,
    }


def _fail_closed(
    *,
    reason: str,
    observed_at: str | None,
    requested_scope: str | None,
    requested_source_url: str | None,
    record_scope: str | None = None,
    record_source_url: str | None = None,
    coverage_period: dict[str, str] | None = None,
) -> dict[str, Any]:
    evidence = normalize_crux_query_record_evidence(
        None,
        state="unavailable",
        observed_at=observed_at,
        scope=requested_scope,
        source_url=requested_source_url,
        reason=reason,
    )
    return _with_metadata(
        evidence,
        _provenance(
            record_scope=record_scope,
            record_source_url=record_source_url,
            requested_scope=requested_scope,
            requested_source_url=requested_source_url,
            coverage_period=coverage_period,
            observed_at=observed_at,
        ),
    )


def normalize_crux_query_record_evidence_bound(
    payload: dict[str, Any] | None,
    *,
    state: str = "connected",
    observed_at: str | None = None,
    scope: str | None = None,
    source_url: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Normalize direct CrUX evidence only when record identity and coverage are provable.

    Non-connected provider states are preserved without measurements. For connected
    evidence, exactly one documented record key (``url`` or ``origin``) must be present.
    Origin-scoped identities must be actual origins, not page URLs, and connected evidence
    requires a valid provider collection period. Caller scope/source may corroborate the
    provider record but may not contradict or broaden it.
    """
    requested_scope = _text(scope).lower() or None
    requested_source = _http_identity(source_url) if source_url is not None else None

    normalized_state = _text(state).lower()
    if normalized_state != "connected":
        evidence = normalize_crux_query_record_evidence(
            payload,
            state=state,
            observed_at=observed_at,
            scope=requested_scope if requested_scope in {"url", "origin"} else None,
            source_url=requested_source,
            reason=reason,
        )
        return _with_metadata(
            evidence,
            _provenance(
                record_scope=None,
                record_source_url=None,
                requested_scope=requested_scope,
                requested_source_url=requested_source,
                coverage_period=None,
                observed_at=observed_at,
            ),
        )

    if source_url is not None and requested_source is None:
        return _fail_closed(
            reason=reason or "crux_source_identity_invalid",
            observed_at=observed_at,
            requested_scope=requested_scope,
            requested_source_url=None,
        )

    record = payload.get("record") if isinstance(payload, dict) else None
    record_scope, record_source, identity_reason = _record_identity(record)
    if identity_reason:
        return _fail_closed(
            reason=reason or identity_reason,
            observed_at=observed_at,
            requested_scope=requested_scope,
            requested_source_url=requested_source,
        )

    if requested_scope is not None and requested_scope not in {"url", "origin"}:
        return _fail_closed(
            reason=reason or "crux_scope_invalid",
            observed_at=observed_at,
            requested_scope=requested_scope,
            requested_source_url=requested_source,
            record_scope=record_scope,
            record_source_url=record_source,
        )
    if requested_scope is not None and requested_scope != record_scope:
        return _fail_closed(
            reason=reason or "crux_scope_mismatch",
            observed_at=observed_at,
            requested_scope=requested_scope,
            requested_source_url=requested_source,
            record_scope=record_scope,
            record_source_url=record_source,
        )

    if record_scope == "origin" and source_url is not None:
        requested_source = _origin_identity(source_url)
        if requested_source is None:
            return _fail_closed(
                reason=reason or "crux_source_origin_identity_invalid",
                observed_at=observed_at,
                requested_scope=requested_scope,
                requested_source_url=None,
                record_scope=record_scope,
                record_source_url=record_source,
            )
    if requested_source is not None and requested_source != record_source:
        return _fail_closed(
            reason=reason or "crux_record_identity_mismatch",
            observed_at=observed_at,
            requested_scope=requested_scope,
            requested_source_url=requested_source,
            record_scope=record_scope,
            record_source_url=record_source,
        )

    coverage = _coverage(record)
    if coverage is None:
        return _fail_closed(
            reason=reason or "crux_collection_period_invalid",
            observed_at=observed_at,
            requested_scope=requested_scope,
            requested_source_url=requested_source,
            record_scope=record_scope,
            record_source_url=record_source,
        )

    evidence = normalize_crux_query_record_evidence(
        payload,
        state="connected",
        observed_at=observed_at,
        scope=record_scope,
        source_url=record_source,
        reason=reason,
    )
    return _with_metadata(
        evidence,
        _provenance(
            record_scope=record_scope,
            record_source_url=record_source,
            requested_scope=requested_scope,
            requested_source_url=requested_source,
            coverage_period=coverage,
            observed_at=observed_at,
        ),
    )


def _valid_coverage(value: Any) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    first_date = value.get("first_date")
    last_date = value.get("last_date")
    try:
        first = date.fromisoformat(first_date) if isinstance(first_date, str) else None
        last = date.fromisoformat(last_date) if isinstance(last_date, str) else None
    except ValueError:
        return None
    if first is None or last is None or first > last:
        return None
    return {"first_date": first.isoformat(), "last_date": last.isoformat()}


def validate_bound_crux_contract(evidence: Any) -> dict[str, Any]:
    """Validate the base field contract plus CrUX record identity/coverage provenance."""
    reasons: list[str] = []
    if not isinstance(evidence, dict):
        return {
            "version": CRUX_BOUND_INTEGRITY_VERSION,
            "valid": False,
            "reasons": ["evidence_not_object"],
        }

    base = validate_field_performance_contract(evidence)
    if not base.get("valid"):
        reasons.extend(f"field:{item}" for item in base.get("reasons", []))
    if evidence.get("adapter_version") != CRUX_BOUND_ADAPTER_VERSION:
        reasons.append("adapter_version_mismatch")
    if evidence.get("base_adapter_version") != PROVIDER_ADAPTER_VERSION:
        reasons.append("base_adapter_version_mismatch")

    provenance = evidence.get("provenance")
    if not isinstance(provenance, dict):
        reasons.append("provenance_missing")
        provenance = {}
    elif provenance.get("version") != CRUX_PROVENANCE_VERSION:
        reasons.append("provenance_version_mismatch")

    state = evidence.get("state")
    record_scope = provenance.get("record_scope")
    record_source = provenance.get("record_source_url")
    requested_scope = provenance.get("requested_scope")
    requested_source = provenance.get("requested_source_url")
    provenance_coverage = _valid_coverage(provenance.get("coverage_period"))
    evidence_coverage = _valid_coverage(evidence.get("coverage_period"))

    if requested_scope is not None and requested_scope not in {"url", "origin"}:
        reasons.append("requested_scope_invalid")
    if requested_source is not None and _http_identity(requested_source) is None:
        reasons.append("requested_source_identity_invalid")

    if state == "connected":
        if record_scope not in {"url", "origin"}:
            reasons.append("connected_record_scope_missing")
        if evidence.get("scope") != record_scope:
            reasons.append("connected_scope_mismatch")
        if record_scope == "origin":
            normalized_record_source = _origin_identity(record_source)
            normalized_evidence_source = _origin_identity(evidence.get("source_url"))
            if requested_source is not None and _origin_identity(requested_source) is None:
                reasons.append("connected_requested_origin_invalid")
        else:
            normalized_record_source = _http_identity(record_source)
            normalized_evidence_source = _http_identity(evidence.get("source_url"))
        if normalized_record_source is None:
            reasons.append("connected_record_source_invalid")
        if normalized_evidence_source is None:
            reasons.append("connected_source_identity_invalid")
        elif normalized_record_source is not None and normalized_evidence_source != normalized_record_source:
            reasons.append("connected_source_identity_mismatch")
        if requested_scope is not None and requested_scope != record_scope:
            reasons.append("connected_requested_scope_mismatch")
        if requested_source is not None:
            normalized_requested = (
                _origin_identity(requested_source)
                if record_scope == "origin"
                else _http_identity(requested_source)
            )
            if normalized_requested is None:
                reasons.append("connected_requested_source_invalid")
            elif normalized_record_source is not None and normalized_requested != normalized_record_source:
                reasons.append("connected_requested_source_mismatch")
        if evidence_coverage is None:
            reasons.append("connected_coverage_period_missing")
        if provenance_coverage is None:
            reasons.append("connected_provenance_coverage_missing")
        if evidence_coverage is not None and provenance_coverage is not None and evidence_coverage != provenance_coverage:
            reasons.append("connected_coverage_period_mismatch")
    else:
        if evidence.get("coverage_period") is not None:
            reasons.append("non_connected_retained_coverage")

    return {
        "version": CRUX_BOUND_INTEGRITY_VERSION,
        "valid": not reasons,
        "reasons": sorted(set(reasons)),
    }
