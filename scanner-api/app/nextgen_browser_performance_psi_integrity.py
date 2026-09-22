"""Fail-closed integrity validation for source-bound PSI composite evidence.

This module validates already-normalized PageSpeed Insights evidence only. It
performs no network/provider work, creates no credentials, grants no execution
budget, and keeps field CrUX evidence separate from lab Lighthouse evidence.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app.nextgen_browser_performance_contract import validate_pagespeed_contract
from app.nextgen_browser_performance_provider import PROVIDER_ADAPTER_VERSION
from app.nextgen_browser_performance_psi_provenance import (
    PSI_BOUND_ADAPTER_VERSION,
    PSI_PROVENANCE_VERSION,
)

PSI_BOUND_INTEGRITY_VERSION = "nextgen_pagespeed_bound_integrity_v1"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _http_identity(value: Any) -> str | None:
    raw = _text(value)
    if not raw:
        return None
    try:
        parsed = urlsplit(raw)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            return None
        if parsed.username is not None or parsed.password is not None:
            return None
        # Accessing ``port`` forces invalid-port syntax to fail closed.
        _ = parsed.port
    except (TypeError, ValueError):
        return None
    return urlunsplit((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        parsed.path or "/",
        parsed.query,
        "",
    ))


def _origin(identity: str | None) -> str | None:
    normalized = _http_identity(identity)
    if normalized is None:
        return None
    parsed = urlsplit(normalized)
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), "/", "", ""))


def _result(reasons: list[str]) -> dict[str, Any]:
    return {
        "version": PSI_BOUND_INTEGRITY_VERSION,
        "valid": not reasons,
        "reasons": sorted(set(reasons)),
    }


def validate_bound_pagespeed_contract(evidence: Any) -> dict[str, Any]:
    """Validate PSI base shape plus source/provenance relationships.

    This validator is deliberately stricter than the transport envelope. Connected
    field/lab components must be attributable to one unambiguous requested identity.
    Unknown or non-connected components remain valid only when they retain no trusted
    measurements under the existing base contract.
    """
    reasons: list[str] = []
    if not isinstance(evidence, dict):
        return _result(["evidence_not_object"])

    base = validate_pagespeed_contract(evidence)
    if not base.get("valid"):
        reasons.extend(f"base:{item}" for item in base.get("reasons", []))

    if evidence.get("adapter_version") != PSI_BOUND_ADAPTER_VERSION:
        reasons.append("adapter_version_mismatch")
    if evidence.get("base_adapter_version") != PROVIDER_ADAPTER_VERSION:
        reasons.append("base_adapter_version_mismatch")

    provenance = evidence.get("provenance")
    if not isinstance(provenance, dict):
        reasons.append("provenance_missing")
        provenance = {}
    elif provenance.get("version") != PSI_PROVENANCE_VERSION:
        reasons.append("provenance_version_mismatch")

    identity_keys = (
        "requested_url",
        "response_final_url",
        "field_source_url",
        "field_initial_url",
        "lighthouse_requested_url",
        "lighthouse_final_url",
    )
    normalized: dict[str, str | None] = {}
    for key in identity_keys:
        value = provenance.get(key)
        normalized[key] = _http_identity(value)
        if value is not None and normalized[key] is None:
            reasons.append(f"{key}_invalid")

    requested = normalized["requested_url"]
    field_source = normalized["field_source_url"]
    field_initial = normalized["field_initial_url"]
    lighthouse_requested = normalized["lighthouse_requested_url"]
    lighthouse_final = normalized["lighthouse_final_url"]

    strategy = provenance.get("strategy")
    if strategy is not None and strategy not in {"mobile", "desktop"}:
        reasons.append("strategy_invalid")

    origin_fallback = provenance.get("field_origin_fallback")
    if origin_fallback is not None and not isinstance(origin_fallback, bool):
        reasons.append("field_origin_fallback_invalid")

    for key in ("analysis_timestamp", "lighthouse_fetch_time", "lighthouse_version"):
        value = provenance.get(key)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            reasons.append(f"{key}_invalid")

    if requested is not None and field_initial is not None and requested != field_initial:
        reasons.append("field_initial_requested_mismatch")
    if requested is not None and lighthouse_requested is not None and requested != lighthouse_requested:
        reasons.append("lighthouse_requested_identity_mismatch")
    if field_initial is not None and lighthouse_requested is not None and field_initial != lighthouse_requested:
        reasons.append("component_requested_identity_mismatch")

    field = evidence.get("field") if isinstance(evidence.get("field"), dict) else {}
    lab = evidence.get("lab") if isinstance(evidence.get("lab"), dict) else {}

    for name, component in (("field", field), ("lab", lab)):
        source_raw = component.get("source_url")
        if source_raw is not None and _http_identity(source_raw) is None:
            reasons.append(f"{name}_source_identity_invalid")

    if field.get("state") == "connected":
        scope = field.get("scope")
        if scope not in {"url", "origin"}:
            reasons.append("connected_field_scope_invalid")

        component_source = _http_identity(field.get("source_url"))
        if requested is None:
            reasons.append("connected_field_requested_identity_missing")
        if field_initial is None:
            reasons.append("connected_field_initial_identity_missing")
        if field_source is None:
            reasons.append("connected_field_provenance_source_missing")
        elif component_source is not None and component_source != field_source:
            reasons.append("connected_field_source_mismatch")

        if scope == "origin":
            if field_source is not None and _origin(field_source) != field_source:
                reasons.append("connected_field_origin_source_not_origin")
            request_origin = _origin(field_initial or requested)
            if field_source is not None and request_origin is not None and field_source != request_origin:
                reasons.append("connected_field_origin_identity_mismatch")
        elif scope == "url" and origin_fallback is True:
            reasons.append("connected_field_url_scope_with_origin_fallback")

    if lab.get("state") == "connected":
        component_source = _http_identity(lab.get("source_url"))
        if requested is None:
            reasons.append("connected_lab_requested_identity_missing")
        if lighthouse_requested is None:
            reasons.append("connected_lab_provider_requested_identity_missing")
        expected_source = lighthouse_final or lighthouse_requested
        if component_source is None:
            reasons.append("connected_lab_source_identity_missing")
        elif expected_source is None or component_source != expected_source:
            reasons.append("connected_lab_source_identity_mismatch")

    return _result(reasons)
