"""Provider-neutral, lab-only execution context for Lighthouse evidence.

Pure normalization only: no browser/provider calls, credentials, persistence,
scoring, or execution entitlement. Direct Lighthouse and PSI Lighthouse inputs
normalize into one lab-context contract while field evidence is rejected.
"""
from __future__ import annotations

from math import isfinite
from typing import Any
from urllib.parse import urlsplit, urlunsplit

LAB_CONTEXT_VERSION = "nextgen_lighthouse_lab_context_v1"
LAB_CONTEXT_INTEGRITY_VERSION = "nextgen_lighthouse_lab_context_integrity_v1"
DIRECT_ADAPTER_VERSION = "nextgen_lighthouse_bound_provider_v1"
DIRECT_PROVENANCE_VERSION = "nextgen_lighthouse_provenance_v1"
PSI_ADAPTER_VERSION = "nextgen_pagespeed_bound_provider_v1"
PSI_PROVENANCE_VERSION = "nextgen_pagespeed_provenance_v1"
LIGHTHOUSE_EVIDENCE_VERSION = "nextgen_lighthouse_evidence_v1"
LAB_CONTEXT_STATES = {"normalized", "not_verified"}
THROTTLING_ALIASES = {
    "simulate": "simulated",
    "simulated": "simulated",
    "devtools": "devtools",
    "provided": "provided",
}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if isfinite(number) and number >= 0 else None


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


def _strategy(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    settings = payload.get("configSettings")
    if not isinstance(settings, dict):
        return None
    raw = _text(settings.get("emulatedFormFactor") or settings.get("formFactor")).lower()
    return raw if raw in {"mobile", "desktop"} else None


def _throttling(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    settings = payload.get("configSettings")
    if not isinstance(settings, dict):
        return None
    raw = _text(settings.get("throttlingMethod")).lower()
    return THROTTLING_ALIASES.get(raw)


def _locale(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    settings = payload.get("configSettings")
    if not isinstance(settings, dict):
        return None
    value = _text(settings.get("locale"))
    return value or None


def _benchmark(payload: Any) -> float | None:
    if not isinstance(payload, dict):
        return None
    environment = payload.get("environment")
    if not isinstance(environment, dict):
        return None
    return _number(environment.get("benchmarkIndex"))


def _base(*, source_kind: str, evidence: Any) -> dict[str, Any]:
    source = evidence if isinstance(evidence, dict) else {}
    return {
        "version": LAB_CONTEXT_VERSION,
        "evidence_kind": "lab_execution_context",
        "source_kind": source_kind,
        "state": "not_verified",
        "reason": None,
        "source_adapter_version": source.get("adapter_version"),
        "source_url": None,
        "context": None,
        "missing_fields": [],
    }


def _normalize(
    *,
    source_kind: str,
    lighthouse_payload: Any,
    source_evidence: Any,
    provenance: Any,
    expected_adapter: str,
    expected_provenance: str,
    expected_requested_key: str,
    expected_final_key: str,
    expected_fetch_key: str,
    expected_version_key: str,
    lab_component: Any,
) -> dict[str, Any]:
    result = _base(source_kind=source_kind, evidence=source_evidence)
    if not isinstance(source_evidence, dict):
        return {**result, "reason": "source_not_object"}
    if source_evidence.get("adapter_version") != expected_adapter:
        return {**result, "reason": "source_adapter_version_mismatch"}
    if not isinstance(provenance, dict) or provenance.get("version") != expected_provenance:
        return {**result, "reason": "source_provenance_invalid"}
    if not isinstance(lab_component, dict):
        return {**result, "reason": "source_lab_component_missing"}
    if lab_component.get("version") != LIGHTHOUSE_EVIDENCE_VERSION or lab_component.get("evidence_kind") != "lab":
        return {**result, "reason": "source_not_lab_evidence"}
    if lab_component.get("state") != "connected":
        state = _text(lab_component.get("state")).lower() or "unknown"
        return {**result, "reason": f"source_lab_{state}"}
    if not isinstance(lighthouse_payload, dict):
        return {**result, "reason": "lighthouse_payload_missing"}

    raw_requested = _http_identity(lighthouse_payload.get("requestedUrl"))
    raw_final = _http_identity(lighthouse_payload.get("finalUrl"))
    bound_requested = _http_identity(provenance.get(expected_requested_key))
    bound_final = _http_identity(provenance.get(expected_final_key))
    source_url = _http_identity(lab_component.get("source_url"))

    for name, raw_value, normalized in (
        ("requested", lighthouse_payload.get("requestedUrl"), raw_requested),
        ("final", lighthouse_payload.get("finalUrl"), raw_final),
        ("bound_requested", provenance.get(expected_requested_key), bound_requested),
        ("bound_final", provenance.get(expected_final_key), bound_final),
        ("source", lab_component.get("source_url"), source_url),
    ):
        if raw_value is not None and normalized is None:
            return {**result, "reason": f"{name}_identity_invalid"}

    if bound_requested is None or raw_requested is None or raw_requested != bound_requested:
        return {**result, "reason": "requested_identity_mismatch"}
    if bound_final is not None and raw_final != bound_final:
        return {**result, "reason": "final_identity_mismatch"}
    expected_source = bound_final or bound_requested
    if source_url != expected_source:
        return {**result, "reason": "source_identity_mismatch"}

    raw_fetch = _text(lighthouse_payload.get("fetchTime")) or None
    bound_fetch = _text(provenance.get(expected_fetch_key)) or None
    if bound_fetch is not None and raw_fetch != bound_fetch:
        return {**result, "reason": "fetch_time_mismatch"}
    raw_version = _text(lighthouse_payload.get("lighthouseVersion")) or None
    bound_version = _text(provenance.get(expected_version_key)) or None
    if bound_version is not None and raw_version != bound_version:
        return {**result, "reason": "engine_version_mismatch"}
    raw_strategy = _strategy(lighthouse_payload)
    bound_strategy = _text(provenance.get("strategy")).lower() or None
    if bound_strategy is not None and raw_strategy != bound_strategy:
        return {**result, "reason": "device_class_mismatch"}

    context = {
        "device_class": raw_strategy,
        "throttling_mode": _throttling(lighthouse_payload),
        "locale": _locale(lighthouse_payload),
        "observation_time": raw_fetch,
        "engine_version": raw_version,
        "environment_benchmark_index": _benchmark(lighthouse_payload),
    }
    missing = sorted(key for key, value in context.items() if value is None)
    return {
        **result,
        "state": "normalized",
        "reason": None,
        "source_url": source_url,
        "context": context,
        "missing_fields": missing,
    }


def normalize_direct_lighthouse_lab_context(raw_lighthouse: Any, bound_lighthouse: Any) -> dict[str, Any]:
    """Normalize lab execution context from already-bound direct Lighthouse evidence."""
    provenance = bound_lighthouse.get("provenance") if isinstance(bound_lighthouse, dict) else None
    return _normalize(
        source_kind="direct_lighthouse",
        lighthouse_payload=raw_lighthouse,
        source_evidence=bound_lighthouse,
        provenance=provenance,
        expected_adapter=DIRECT_ADAPTER_VERSION,
        expected_provenance=DIRECT_PROVENANCE_VERSION,
        expected_requested_key="provider_requested_url",
        expected_final_key="final_url",
        expected_fetch_key="fetch_time",
        expected_version_key="lighthouse_version",
        lab_component=bound_lighthouse,
    )


def normalize_psi_lighthouse_lab_context(raw_psi: Any, bound_psi: Any) -> dict[str, Any]:
    """Normalize the Lighthouse lab context nested in an already-bound PSI response."""
    lighthouse = raw_psi.get("lighthouseResult") if isinstance(raw_psi, dict) else None
    provenance = bound_psi.get("provenance") if isinstance(bound_psi, dict) else None
    lab = bound_psi.get("lab") if isinstance(bound_psi, dict) else None
    return _normalize(
        source_kind="psi_lighthouse",
        lighthouse_payload=lighthouse,
        source_evidence=bound_psi,
        provenance=provenance,
        expected_adapter=PSI_ADAPTER_VERSION,
        expected_provenance=PSI_PROVENANCE_VERSION,
        expected_requested_key="lighthouse_requested_url",
        expected_final_key="lighthouse_final_url",
        expected_fetch_key="lighthouse_fetch_time",
        expected_version_key="lighthouse_version",
        lab_component=lab,
    )


def validate_lighthouse_lab_context_contract(evidence: Any) -> dict[str, Any]:
    """Validate a normalized lab-context artifact without promoting missing context."""
    reasons: list[str] = []
    if not isinstance(evidence, dict):
        return {"version": LAB_CONTEXT_INTEGRITY_VERSION, "valid": False, "reasons": ["evidence_not_object"]}
    if evidence.get("version") != LAB_CONTEXT_VERSION:
        reasons.append("version_mismatch")
    if evidence.get("evidence_kind") != "lab_execution_context":
        reasons.append("evidence_kind_mismatch")
    if evidence.get("source_kind") not in {"direct_lighthouse", "psi_lighthouse"}:
        reasons.append("source_kind_invalid")
    state = evidence.get("state")
    if state not in LAB_CONTEXT_STATES:
        reasons.append("state_invalid")
    context = evidence.get("context")
    missing = evidence.get("missing_fields")
    if not isinstance(missing, list) or any(not isinstance(item, str) or not item for item in missing):
        reasons.append("missing_fields_invalid")
        missing = []
    elif len(missing) != len(set(missing)) or missing != sorted(missing):
        reasons.append("missing_fields_not_canonical")

    if state == "normalized":
        if evidence.get("reason") is not None:
            reasons.append("normalized_reason_present")
        if _http_identity(evidence.get("source_url")) is None:
            reasons.append("normalized_source_identity_invalid")
        if not isinstance(context, dict):
            reasons.append("normalized_context_missing")
            context = {}
        allowed = {
            "device_class", "throttling_mode", "locale", "observation_time",
            "engine_version", "environment_benchmark_index",
        }
        if set(context) != allowed:
            reasons.append("context_fields_mismatch")
        if context.get("device_class") not in {None, "mobile", "desktop"}:
            reasons.append("device_class_invalid")
        if context.get("throttling_mode") not in {None, "simulated", "devtools", "provided"}:
            reasons.append("throttling_mode_invalid")
        for key in ("locale", "observation_time", "engine_version"):
            value = context.get(key)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                reasons.append(f"{key}_invalid")
        if context.get("environment_benchmark_index") is not None and _number(context.get("environment_benchmark_index")) is None:
            reasons.append("environment_benchmark_index_invalid")
        expected_missing = sorted(key for key, value in context.items() if value is None)
        if missing != expected_missing:
            reasons.append("missing_fields_mismatch")
    else:
        if context is not None:
            reasons.append("not_verified_retained_context")
        if evidence.get("source_url") is not None:
            reasons.append("not_verified_retained_source_url")
        if not isinstance(evidence.get("reason"), str) or not evidence.get("reason"):
            reasons.append("not_verified_reason_missing")
        if missing:
            reasons.append("not_verified_with_missing_fields")

    return {
        "version": LAB_CONTEXT_INTEGRITY_VERSION,
        "valid": not reasons,
        "reasons": sorted(set(reasons)),
    }
