"""CrUX device-dimension binding for NextGen field-performance evidence.

This module is additive and pure. It accepts an already-observed direct CrUX
``queryRecord`` payload plus already source-bound CrUX field evidence. It performs
no network I/O, creates no credentials, and never grants provider execution budget.

The CrUX ``record.key.formFactor`` dimension is normalized separately from
Lighthouse lab strategy so field and lab device context cannot be conflated. Per
CrUX semantics, an omitted record form factor means the field measurements are
aggregated across all form factors; it is not silently treated as mobile or desktop.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
from typing import Any
from urllib.parse import urlsplit, urlunsplit

CRUX_FIELD_DIMENSION_VERSION = "nextgen_crux_field_dimension_v1"
CRUX_FIELD_DIMENSION_INTEGRITY_VERSION = "nextgen_crux_field_dimension_integrity_v1"
EXPECTED_BOUND_CRUX_ADAPTER_VERSION = "nextgen_crux_bound_provider_v1"
EXPECTED_BOUND_CRUX_PROVENANCE_VERSION = "nextgen_crux_provenance_v1"

_PROVIDER_STATES = {
    "connected",
    "disconnected",
    "unavailable",
    "rate_limited",
    "provider_error",
}
_FORM_FACTORS = {
    "PHONE": "phone",
    "TABLET": "tablet",
    "DESKTOP": "desktop",
}
_REQUEST_FORM_FACTORS = {
    "phone": "phone",
    "tablet": "tablet",
    "desktop": "desktop",
    "all": "all",
    "all_form_factors": "all",
}


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


def _coverage_from_record(record: Any) -> dict[str, str] | None:
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


def _record_identity(record: Any) -> tuple[str | None, str | None, str | None]:
    if not isinstance(record, dict):
        return None, None, "crux_record_missing"
    key = record.get("key")
    if not isinstance(key, dict):
        return None, None, "crux_record_key_invalid"
    has_url = bool(_text(key.get("url")))
    has_origin = bool(_text(key.get("origin")))
    if has_url == has_origin:
        return None, None, "crux_record_key_invalid"
    if has_url:
        identity = _http_identity(key.get("url"))
        return ("url", identity, None) if identity else (
            None,
            None,
            "crux_record_url_identity_invalid",
        )
    identity = _origin_identity(key.get("origin"))
    return ("origin", identity, None) if identity else (
        None,
        None,
        "crux_record_origin_identity_invalid",
    )


def _record_form_factor(record: Any) -> tuple[str | None, str | None, str | None]:
    if not isinstance(record, dict) or not isinstance(record.get("key"), dict):
        return None, None, "crux_record_key_invalid"
    raw = record["key"].get("formFactor")
    if raw is None or not _text(raw):
        return "all", "record_key_form_factor_omitted", None
    provider_value = _text(raw).upper()
    normalized = _FORM_FACTORS.get(provider_value)
    if normalized is None:
        return None, None, "crux_record_form_factor_invalid"
    return normalized, "record_key_form_factor", None


def _requested_form_factor(value: Any) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    normalized = _REQUEST_FORM_FACTORS.get(_text(value).lower())
    if normalized is None:
        return None, "crux_requested_form_factor_invalid"
    return normalized, None


def _bound_reference(bound_field: Any) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(bound_field, dict):
        return None, "bound_crux_evidence_missing"
    state = _text(bound_field.get("state")).lower()
    if state not in _PROVIDER_STATES:
        return None, "bound_crux_state_invalid"
    if state != "connected":
        return {"state": state}, None
    if bound_field.get("evidence_kind") != "field" or bound_field.get("provider") != "CrUX":
        return None, "bound_crux_evidence_kind_invalid"
    if bound_field.get("adapter_version") != EXPECTED_BOUND_CRUX_ADAPTER_VERSION:
        return None, "bound_crux_adapter_version_invalid"
    scope = bound_field.get("scope")
    if scope not in {"url", "origin"}:
        return None, "bound_crux_scope_invalid"
    source = (
        _origin_identity(bound_field.get("source_url"))
        if scope == "origin"
        else _http_identity(bound_field.get("source_url"))
    )
    if source is None:
        return None, "bound_crux_source_identity_invalid"
    coverage = _valid_coverage(bound_field.get("coverage_period"))
    if coverage is None:
        return None, "bound_crux_coverage_period_invalid"
    provenance = bound_field.get("provenance")
    if not isinstance(provenance, dict):
        return None, "bound_crux_provenance_missing"
    if provenance.get("version") != EXPECTED_BOUND_CRUX_PROVENANCE_VERSION:
        return None, "bound_crux_provenance_version_invalid"
    if provenance.get("record_scope") != scope:
        return None, "bound_crux_provenance_scope_mismatch"
    provenance_source = (
        _origin_identity(provenance.get("record_source_url"))
        if scope == "origin"
        else _http_identity(provenance.get("record_source_url"))
    )
    if provenance_source != source:
        return None, "bound_crux_provenance_source_mismatch"
    if _valid_coverage(provenance.get("coverage_period")) != coverage:
        return None, "bound_crux_provenance_coverage_mismatch"
    return {
        "state": state,
        "scope": scope,
        "source_url": source,
        "coverage_period": coverage,
    }, None


def _artifact(
    *,
    state: str,
    reason: str | None,
    scope: str | None = None,
    source_url: str | None = None,
    coverage_period: dict[str, str] | None = None,
    form_factor: str | None = None,
    dimension_source: str | None = None,
    requested_form_factor: str | None = None,
) -> dict[str, Any]:
    return {
        "version": CRUX_FIELD_DIMENSION_VERSION,
        "evidence_kind": "field_context",
        "provider": "CrUX",
        "state": state,
        "reason": reason,
        "scope": scope,
        "source_url": source_url,
        "coverage_period": deepcopy(coverage_period),
        "form_factor": form_factor,
        "aggregation": (
            "all_form_factors"
            if form_factor == "all"
            else "single_form_factor" if form_factor in {"phone", "tablet", "desktop"} else None
        ),
        "dimension_source": dimension_source,
        "requested_form_factor": requested_form_factor,
        "bound_adapter_version": EXPECTED_BOUND_CRUX_ADAPTER_VERSION,
    }


def normalize_crux_field_dimension_context(
    payload: dict[str, Any] | None,
    bound_field: dict[str, Any] | None,
    *,
    requested_form_factor: str | None = None,
) -> dict[str, Any]:
    """Bind CrUX field measurements to an explicit device aggregation context.

    This helper does not make or authorize a CrUX request. It only interprets the
    already-returned record key after source-bound CrUX evidence exists. An omitted
    ``record.key.formFactor`` is normalized to ``all`` because the CrUX API defines
    that response as aggregated across all form factors.
    """
    requested, requested_reason = _requested_form_factor(requested_form_factor)
    if requested_reason:
        return _artifact(
            state="unavailable",
            reason=requested_reason,
            requested_form_factor=None,
        )

    bound, bound_reason = _bound_reference(bound_field)
    if bound_reason:
        return _artifact(
            state="unavailable",
            reason=bound_reason,
            requested_form_factor=requested,
        )
    assert bound is not None
    if bound["state"] != "connected":
        return _artifact(
            state=bound["state"],
            reason=_text(bound_field.get("reason")) or bound["state"],
            requested_form_factor=requested,
        )

    record = payload.get("record") if isinstance(payload, dict) else None
    record_scope, record_source, identity_reason = _record_identity(record)
    if identity_reason:
        return _artifact(
            state="unavailable",
            reason=identity_reason,
            scope=bound["scope"],
            source_url=bound["source_url"],
            requested_form_factor=requested,
        )
    if record_scope != bound["scope"] or record_source != bound["source_url"]:
        return _artifact(
            state="unavailable",
            reason="crux_dimension_source_identity_mismatch",
            scope=bound["scope"],
            source_url=bound["source_url"],
            requested_form_factor=requested,
        )

    coverage = _coverage_from_record(record)
    if coverage is None:
        return _artifact(
            state="unavailable",
            reason="crux_dimension_collection_period_invalid",
            scope=bound["scope"],
            source_url=bound["source_url"],
            requested_form_factor=requested,
        )
    if coverage != bound["coverage_period"]:
        return _artifact(
            state="unavailable",
            reason="crux_dimension_collection_period_mismatch",
            scope=bound["scope"],
            source_url=bound["source_url"],
            requested_form_factor=requested,
        )

    form_factor, dimension_source, factor_reason = _record_form_factor(record)
    if factor_reason:
        return _artifact(
            state="unavailable",
            reason=factor_reason,
            scope=bound["scope"],
            source_url=bound["source_url"],
            coverage_period=coverage,
            requested_form_factor=requested,
        )
    if requested is not None and requested != form_factor:
        return _artifact(
            state="unavailable",
            reason="crux_requested_form_factor_mismatch",
            scope=bound["scope"],
            source_url=bound["source_url"],
            coverage_period=coverage,
            requested_form_factor=requested,
        )

    return _artifact(
        state="connected",
        reason=None,
        scope=bound["scope"],
        source_url=bound["source_url"],
        coverage_period=coverage,
        form_factor=form_factor,
        dimension_source=dimension_source,
        requested_form_factor=requested,
    )


def validate_crux_field_dimension_contract(
    payload: dict[str, Any] | None,
    bound_field: dict[str, Any] | None,
    evidence: Any,
    *,
    requested_form_factor: str | None = None,
) -> dict[str, Any]:
    """Recompute and compare the exact field-device context artifact."""
    if not isinstance(evidence, dict):
        return {
            "version": CRUX_FIELD_DIMENSION_INTEGRITY_VERSION,
            "valid": False,
            "reasons": ["evidence_not_object"],
        }
    expected = normalize_crux_field_dimension_context(
        payload,
        bound_field,
        requested_form_factor=requested_form_factor,
    )
    reasons: list[str] = []
    for key in (
        "version",
        "evidence_kind",
        "provider",
        "state",
        "reason",
        "scope",
        "source_url",
        "coverage_period",
        "form_factor",
        "aggregation",
        "dimension_source",
        "requested_form_factor",
        "bound_adapter_version",
    ):
        if evidence.get(key) != expected.get(key):
            reasons.append(f"{key}_mismatch")
    if set(evidence) != set(expected):
        reasons.append("artifact_shape_mismatch")
    return {
        "version": CRUX_FIELD_DIMENSION_INTEGRITY_VERSION,
        "valid": not reasons,
        "reasons": sorted(set(reasons)),
    }
