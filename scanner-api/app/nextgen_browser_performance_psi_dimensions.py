"""PSI CrUX field-device binding for NextGen performance evidence.

This module is additive and pure. It accepts an already-observed PageSpeed Insights
payload plus already source-bound PSI evidence. It performs no network I/O, creates
no credentials, and never grants provider or browser execution budget.

PSI exposes CrUX ``UserPageLoadMetricV5.formFactor`` on individual field metrics.
That field context is normalized independently of Lighthouse ``strategy``/
``configSettings.formFactor`` so lab device configuration cannot be laundered into
field evidence. Missing or inconsistent field metric form-factor metadata stays
unavailable rather than being guessed.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any
from urllib.parse import urlsplit, urlunsplit

PSI_FIELD_DIMENSION_VERSION = "nextgen_psi_field_dimension_v1"
PSI_FIELD_DIMENSION_INTEGRITY_VERSION = "nextgen_psi_field_dimension_integrity_v1"
EXPECTED_BOUND_PSI_ADAPTER_VERSION = "nextgen_pagespeed_bound_provider_v1"
EXPECTED_BASE_PROVIDER_ADAPTER_VERSION = "nextgen_performance_provider_adapter_v1"
EXPECTED_BOUND_PSI_PROVENANCE_VERSION = "nextgen_pagespeed_provenance_v1"

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
_PSI_RAW_TO_CANONICAL = {
    "LARGEST_CONTENTFUL_PAINT_MS": "lcp",
    "INTERACTION_TO_NEXT_PAINT": "inp",
    "CUMULATIVE_LAYOUT_SHIFT_SCORE": "cls",
    "FIRST_CONTENTFUL_PAINT_MS": "fcp",
    "EXPERIMENTAL_TIME_TO_FIRST_BYTE": "ttfb",
}
_PSI_CANONICAL_TO_RAW = {value: key for key, value in _PSI_RAW_TO_CANONICAL.items()}


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
    return urlunsplit((parsed.scheme, parsed.netloc, "/", "", ""))


def _bound_reference(bound_psi: Any) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(bound_psi, dict):
        return None, "bound_psi_evidence_missing"
    if bound_psi.get("adapter_version") != EXPECTED_BOUND_PSI_ADAPTER_VERSION:
        return None, "bound_psi_adapter_version_invalid"
    if bound_psi.get("base_adapter_version") != EXPECTED_BASE_PROVIDER_ADAPTER_VERSION:
        return None, "bound_psi_base_adapter_version_invalid"
    provenance = bound_psi.get("provenance")
    if not isinstance(provenance, dict):
        return None, "bound_psi_provenance_missing"
    if provenance.get("version") != EXPECTED_BOUND_PSI_PROVENANCE_VERSION:
        return None, "bound_psi_provenance_version_invalid"
    field = bound_psi.get("field")
    if not isinstance(field, dict):
        return None, "bound_psi_field_missing"
    state = _text(field.get("state")).lower()
    if state not in _PROVIDER_STATES:
        return None, "bound_psi_field_state_invalid"
    if state != "connected":
        return {
            "state": state,
            "reason": _text(field.get("reason")) or state,
        }, None
    if field.get("evidence_kind") != "field":
        return None, "bound_psi_field_kind_invalid"
    if field.get("provider") != "PageSpeed Insights / CrUX":
        return None, "bound_psi_field_provider_invalid"
    scope = field.get("scope")
    if scope not in {"url", "origin"}:
        return None, "bound_psi_field_scope_invalid"
    source = _origin_identity(field.get("source_url")) if scope == "origin" else _http_identity(field.get("source_url"))
    if source is None:
        return None, "bound_psi_field_source_invalid"
    provenance_source = _origin_identity(provenance.get("field_source_url")) if scope == "origin" else _http_identity(provenance.get("field_source_url"))
    if provenance_source != source:
        return None, "bound_psi_field_provenance_source_mismatch"
    metrics = field.get("metrics")
    if not isinstance(metrics, dict) or not metrics:
        return None, "bound_psi_field_metrics_missing"
    unsupported = sorted(set(metrics) - set(_PSI_CANONICAL_TO_RAW))
    if unsupported:
        return None, "bound_psi_field_metric_unknown"
    return {
        "state": state,
        "reason": None,
        "scope": scope,
        "source_url": source,
        "metrics": sorted(metrics),
        "field_initial_url": _http_identity(provenance.get("field_initial_url")),
        "field_origin_fallback": provenance.get("field_origin_fallback"),
    }, None


def _artifact(
    *,
    state: str,
    reason: str | None,
    scope: str | None = None,
    source_url: str | None = None,
    form_factor: str | None = None,
    metric_form_factors: dict[str, str] | None = None,
    dimension_source: str | None = None,
) -> dict[str, Any]:
    return {
        "version": PSI_FIELD_DIMENSION_VERSION,
        "evidence_kind": "field_context",
        "provider": "PageSpeed Insights / CrUX",
        "state": state,
        "reason": reason,
        "scope": scope,
        "source_url": source_url,
        "form_factor": form_factor,
        "aggregation": "single_form_factor" if form_factor in {"phone", "tablet", "desktop"} else None,
        "metric_form_factors": deepcopy(metric_form_factors) if metric_form_factors else None,
        "dimension_source": dimension_source,
        "bound_adapter_version": EXPECTED_BOUND_PSI_ADAPTER_VERSION,
    }


def _experience(payload: Any, bound: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(payload, dict):
        return None, "psi_payload_missing"
    if bound["scope"] == "url":
        candidate = payload.get("loadingExperience")
    elif bound.get("field_origin_fallback") is True:
        candidate = payload.get("loadingExperience")
    else:
        candidate = payload.get("originLoadingExperience")
    if not isinstance(candidate, dict):
        return None, "psi_field_experience_missing"
    raw_id = candidate.get("id")
    candidate_source = _origin_identity(raw_id) if bound["scope"] == "origin" else _http_identity(raw_id)
    if candidate_source is None:
        return None, "psi_field_experience_identity_invalid"
    if candidate_source != bound["source_url"]:
        return None, "psi_field_experience_identity_mismatch"
    bound_initial = bound.get("field_initial_url")
    raw_initial = candidate.get("initial_url")
    if bound_initial is not None:
        candidate_initial = _http_identity(raw_initial)
        if candidate_initial is None:
            return None, "psi_field_initial_identity_invalid"
        if candidate_initial != bound_initial:
            return None, "psi_field_initial_identity_mismatch"
    return candidate, None


def normalize_psi_field_dimension_context(
    payload: dict[str, Any] | None,
    bound_psi: dict[str, Any] | None,
) -> dict[str, Any]:
    """Derive PSI CrUX field form factor without borrowing Lighthouse lab strategy."""
    bound, bound_reason = _bound_reference(bound_psi)
    if bound_reason:
        return _artifact(state="unavailable", reason=bound_reason)
    assert bound is not None
    if bound["state"] != "connected":
        return _artifact(state=bound["state"], reason=bound["reason"])

    experience, experience_reason = _experience(payload, bound)
    if experience_reason:
        return _artifact(
            state="unavailable",
            reason=experience_reason,
            scope=bound["scope"],
            source_url=bound["source_url"],
        )
    assert experience is not None
    raw_metrics = experience.get("metrics")
    if not isinstance(raw_metrics, dict):
        return _artifact(
            state="unavailable",
            reason="psi_field_metrics_missing",
            scope=bound["scope"],
            source_url=bound["source_url"],
        )

    metric_form_factors: dict[str, str] = {}
    missing = False
    for canonical in bound["metrics"]:
        raw_key = _PSI_CANONICAL_TO_RAW[canonical]
        raw_metric = raw_metrics.get(raw_key)
        if not isinstance(raw_metric, dict):
            return _artifact(
                state="unavailable",
                reason="psi_dimension_metric_source_missing",
                scope=bound["scope"],
                source_url=bound["source_url"],
            )
        raw_factor = raw_metric.get("formFactor")
        if raw_factor is None or not _text(raw_factor):
            missing = True
            continue
        normalized = _FORM_FACTORS.get(_text(raw_factor).upper())
        if normalized is None:
            return _artifact(
                state="unavailable",
                reason="psi_metric_form_factor_invalid",
                scope=bound["scope"],
                source_url=bound["source_url"],
            )
        metric_form_factors[canonical] = normalized

    if missing and metric_form_factors:
        return _artifact(
            state="unavailable",
            reason="psi_metric_form_factor_incomplete",
            scope=bound["scope"],
            source_url=bound["source_url"],
        )
    if missing:
        return _artifact(
            state="unavailable",
            reason="psi_metric_form_factor_unavailable",
            scope=bound["scope"],
            source_url=bound["source_url"],
        )
    factors = sorted(set(metric_form_factors.values()))
    if len(factors) != 1:
        return _artifact(
            state="unavailable",
            reason="psi_metric_form_factor_mixed",
            scope=bound["scope"],
            source_url=bound["source_url"],
        )

    return _artifact(
        state="connected",
        reason=None,
        scope=bound["scope"],
        source_url=bound["source_url"],
        form_factor=factors[0],
        metric_form_factors=metric_form_factors,
        dimension_source="field_metric_form_factor",
    )


def validate_psi_field_dimension_contract(
    payload: dict[str, Any] | None,
    bound_psi: dict[str, Any] | None,
    evidence: Any,
) -> dict[str, Any]:
    """Recompute and bind the exact PSI field-device artifact."""
    if not isinstance(evidence, dict):
        return {
            "version": PSI_FIELD_DIMENSION_INTEGRITY_VERSION,
            "valid": False,
            "reasons": ["evidence_not_object"],
        }
    expected = normalize_psi_field_dimension_context(payload, bound_psi)
    reasons: list[str] = []
    for key in (
        "version",
        "evidence_kind",
        "provider",
        "state",
        "reason",
        "scope",
        "source_url",
        "form_factor",
        "aggregation",
        "metric_form_factors",
        "dimension_source",
        "bound_adapter_version",
    ):
        if evidence.get(key) != expected.get(key):
            reasons.append(f"{key}_mismatch")
    if set(evidence) != set(expected):
        reasons.append("artifact_shape_mismatch")
    return {
        "version": PSI_FIELD_DIMENSION_INTEGRITY_VERSION,
        "valid": not reasons,
        "reasons": sorted(set(reasons)),
    }
