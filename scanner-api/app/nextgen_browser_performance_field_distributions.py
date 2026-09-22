"""Provider-neutral field-distribution evidence for Lane-C performance data.

This module accepts already-observed, already-bound CrUX or PageSpeed Insights
field evidence. It performs no network I/O, creates no credentials, and never
mixes Lighthouse lab measurements into field distributions.
"""
from __future__ import annotations

from datetime import date
from math import isfinite
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app.nextgen_browser_performance_crux_provenance import validate_bound_crux_contract
from app.nextgen_browser_performance_psi_integrity import validate_bound_pagespeed_contract

FIELD_DISTRIBUTION_VERSION = "nextgen_field_metric_distribution_v1"
FIELD_DISTRIBUTION_INTEGRITY_VERSION = "nextgen_field_metric_distribution_integrity_v1"
PROVIDER_STATES = {"connected", "disconnected", "unavailable", "rate_limited", "provider_error"}

METRICS = {
    "lcp": {"unit": "ms", "crux": ("largest_contentful_paint", "largest_contentful_paint_ms"), "psi": "LARGEST_CONTENTFUL_PAINT_MS"},
    "inp": {"unit": "ms", "crux": ("interaction_to_next_paint", "interaction_to_next_paint_ms"), "psi": "INTERACTION_TO_NEXT_PAINT"},
    "cls": {"unit": "score", "crux": ("cumulative_layout_shift",), "psi": "CUMULATIVE_LAYOUT_SHIFT_SCORE"},
    "fcp": {"unit": "ms", "crux": ("first_contentful_paint", "first_contentful_paint_ms"), "psi": "FIRST_CONTENTFUL_PAINT_MS"},
    "ttfb": {"unit": "ms", "crux": ("time_to_first_byte", "experimental_time_to_first_byte"), "psi": "EXPERIMENTAL_TIME_TO_FIRST_BYTE"},
}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) and number >= 0 else None


def _http_identity(value: Any) -> str | None:
    raw = _text(value)
    if not raw:
        return None
    try:
        parsed = urlsplit(raw)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            return None
        if parsed.hostname is None or parsed.username is not None or parsed.password is not None:
            return None
        _ = parsed.port
    except (TypeError, ValueError):
        return None
    return urlunsplit((
        parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", parsed.query, ""
    ))


def _origin(value: Any) -> str | None:
    identity = _http_identity(value)
    if identity is None:
        return None
    parsed = urlsplit(identity)
    return urlunsplit((parsed.scheme, parsed.netloc, "/", "", ""))


def _iso_date(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    try:
        return date(int(value["year"]), int(value["month"]), int(value["day"])).isoformat()
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def _blank(*, provider: str, state: str, reason: str | None, scope: Any = None,
           source_url: Any = None, source_contract: str) -> dict[str, Any]:
    normalized_state = _text(state).lower()
    if normalized_state not in PROVIDER_STATES:
        normalized_state = "unavailable"
        reason = reason or "provider_state_invalid"
    return {
        "version": FIELD_DISTRIBUTION_VERSION,
        "evidence_kind": "field",
        "provider": provider,
        "state": normalized_state,
        "reason": _text(reason) or None,
        "scope": scope if scope in {"url", "origin"} else None,
        "source_url": source_url if _http_identity(source_url) else None,
        "source_contract": source_contract,
        "metrics": None,
        "omitted_metrics": [],
    }


def _raw_crux_metric(raw_metrics: Any, canonical: str) -> dict[str, Any] | None:
    if not isinstance(raw_metrics, dict):
        return None
    for key in METRICS[canonical]["crux"]:
        item = raw_metrics.get(key)
        if isinstance(item, dict):
            return item
    return None


def _raw_p75(item: Any, *, provider_kind: str, canonical: str) -> float | None:
    if not isinstance(item, dict):
        return None
    if provider_kind == "crux":
        percentiles = item.get("percentiles")
        raw = percentiles.get("p75") if isinstance(percentiles, dict) else item.get("p75")
    else:
        raw = item.get("percentile")
    value = _number(raw)
    if value is not None and provider_kind == "psi" and canonical == "cls":
        value /= 100.0
    return value


def _raw_bins(item: Any, *, provider_kind: str, canonical: str) -> list[dict[str, float | None]] | None:
    if not isinstance(item, dict):
        return None
    rows = item.get("histogram") if provider_kind == "crux" else item.get("distributions")
    if not isinstance(rows, list) or not rows:
        return None
    result: list[dict[str, float | None]] = []
    for row in rows:
        if not isinstance(row, dict):
            return None
        if provider_kind == "crux":
            lower_raw, upper_raw, proportion_raw = row.get("start"), row.get("end"), row.get("density")
        else:
            lower_raw, upper_raw, proportion_raw = row.get("min"), row.get("max"), row.get("proportion")
        lower = _number(lower_raw)
        upper = None if upper_raw is None else _number(upper_raw)
        proportion = _number(proportion_raw)
        if lower is None or proportion is None or proportion > 1:
            return None
        if upper is not None and upper <= lower:
            return None
        if provider_kind == "psi" and canonical == "cls":
            lower /= 100.0
            if upper is not None:
                upper /= 100.0
        result.append({"min": lower, "max": upper, "proportion": proportion})

    previous_upper: float | None = None
    for index, row in enumerate(result):
        lower, upper = row["min"], row["max"]
        if index and previous_upper is None:
            return None
        if previous_upper is not None and lower < previous_upper:
            return None
        previous_upper = upper
    if abs(sum(float(row["proportion"]) for row in result) - 1.0) > 0.005:
        return None
    return result


def _metric_distribution(item: Any, trusted_metric: Any, *, provider_kind: str,
                         canonical: str) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(trusted_metric, dict):
        return None, "trusted_metric_missing"
    expected_unit = METRICS[canonical]["unit"]
    trusted_value = _number(trusted_metric.get("value"))
    if trusted_value is None or trusted_metric.get("unit") != expected_unit:
        return None, "trusted_metric_invalid"
    raw_p75 = _raw_p75(item, provider_kind=provider_kind, canonical=canonical)
    if raw_p75 is None or abs(raw_p75 - trusted_value) > max(1e-9, abs(trusted_value) * 1e-9):
        return None, "percentile_mismatch"
    bins = _raw_bins(item, provider_kind=provider_kind, canonical=canonical)
    if bins is None:
        return None, "distribution_invalid"
    return {"p75": trusted_value, "unit": expected_unit, "bins": bins}, None


def _finish(*, provider: str, source_contract: str, field: dict[str, Any], raw_metrics: Any,
            provider_kind: str) -> dict[str, Any]:
    state = field.get("state")
    base = _blank(
        provider=provider,
        state=state if state in PROVIDER_STATES else "unavailable",
        reason=field.get("reason"),
        scope=field.get("scope"),
        source_url=field.get("source_url"),
        source_contract=source_contract,
    )
    if state != "connected":
        return base
    trusted_metrics = field.get("metrics") if isinstance(field.get("metrics"), dict) else {}
    normalized: dict[str, dict[str, Any]] = {}
    omitted: list[dict[str, str]] = []
    for canonical in sorted(trusted_metrics):
        if canonical not in METRICS:
            continue
        if provider_kind == "crux":
            item = _raw_crux_metric(raw_metrics, canonical)
        else:
            raw_key = METRICS[canonical]["psi"]
            item = raw_metrics.get(raw_key) if isinstance(raw_metrics, dict) else None
        row, reason = _metric_distribution(
            item, trusted_metrics.get(canonical), provider_kind=provider_kind, canonical=canonical
        )
        if row is None:
            omitted.append({"metric": canonical, "reason": reason or "distribution_unavailable"})
        else:
            normalized[canonical] = row
    if not normalized:
        return {
            **base,
            "state": "unavailable",
            "reason": "field_distributions_unavailable",
            "omitted_metrics": omitted,
        }
    return {**base, "state": "connected", "reason": None, "metrics": normalized, "omitted_metrics": omitted}


def _crux_source_matches(payload: Any, bound_crux: dict[str, Any]) -> bool:
    record = payload.get("record") if isinstance(payload, dict) else None
    provenance = bound_crux.get("provenance") if isinstance(bound_crux.get("provenance"), dict) else {}
    if not isinstance(record, dict):
        return False
    key = record.get("key") if isinstance(record.get("key"), dict) else {}
    scope = provenance.get("record_scope")
    if scope == "url":
        raw_source = _http_identity(key.get("url"))
    elif scope == "origin":
        raw_source = _origin(key.get("origin"))
    else:
        return False
    if raw_source is None or raw_source != provenance.get("record_source_url"):
        return False
    period = record.get("collectionPeriod") if isinstance(record.get("collectionPeriod"), dict) else {}
    raw_coverage = {"first_date": _iso_date(period.get("firstDate")), "last_date": _iso_date(period.get("lastDate"))}
    return raw_coverage == provenance.get("coverage_period")


def normalize_crux_field_distribution_evidence(payload: Any, bound_crux: Any) -> dict[str, Any]:
    """Normalize direct CrUX histograms only after strict bound-CrUX integrity passes."""
    validation = validate_bound_crux_contract(bound_crux)
    if not validation.get("valid") or not isinstance(bound_crux, dict):
        return _blank(
            provider="CrUX", state="unavailable", reason="bound_crux_contract_invalid",
            source_contract="nextgen_crux_bound_integrity_v1",
        )
    if bound_crux.get("state") == "connected" and not _crux_source_matches(payload, bound_crux):
        return _blank(
            provider="CrUX", state="unavailable", reason="crux_distribution_source_mismatch",
            scope=bound_crux.get("scope"), source_url=bound_crux.get("source_url"),
            source_contract=validation.get("version") or "nextgen_crux_bound_integrity_v1",
        )
    record = payload.get("record") if isinstance(payload, dict) else None
    raw_metrics = record.get("metrics") if isinstance(record, dict) else None
    return _finish(
        provider="CrUX",
        source_contract=validation.get("version") or "nextgen_crux_bound_integrity_v1",
        field=bound_crux,
        raw_metrics=raw_metrics,
        provider_kind="crux",
    )


def _psi_experience(payload: Any, field: dict[str, Any], provenance: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    origin_fallback = provenance.get("field_origin_fallback") if isinstance(provenance, dict) else None
    if origin_fallback is True or field.get("scope") == "url":
        experience = payload.get("loadingExperience")
    else:
        experience = payload.get("originLoadingExperience")
    return experience if isinstance(experience, dict) else None


def _psi_source_matches(experience: Any, field: dict[str, Any], provenance: Any) -> bool:
    if not isinstance(experience, dict) or not isinstance(provenance, dict):
        return False
    raw_initial = _http_identity(experience.get("initial_url"))
    if raw_initial is None or raw_initial != provenance.get("field_initial_url"):
        return False
    raw_id = _http_identity(experience.get("id"))
    if raw_id is None:
        return False
    expected = provenance.get("field_source_url")
    if field.get("scope") == "origin":
        raw_id = _origin(raw_id)
    return raw_id == expected


def normalize_psi_field_distribution_evidence(payload: Any, bound_psi: Any) -> dict[str, Any]:
    """Normalize PSI CrUX distributions; Lighthouse lab data is intentionally ignored."""
    validation = validate_bound_pagespeed_contract(bound_psi)
    if not validation.get("valid") or not isinstance(bound_psi, dict):
        return _blank(
            provider="PageSpeed Insights / CrUX", state="unavailable",
            reason="bound_pagespeed_contract_invalid",
            source_contract="nextgen_pagespeed_bound_integrity_v1",
        )
    field = bound_psi.get("field") if isinstance(bound_psi.get("field"), dict) else {}
    provenance = bound_psi.get("provenance")
    experience = _psi_experience(payload, field, provenance)
    if field.get("state") == "connected" and not _psi_source_matches(experience, field, provenance):
        return _blank(
            provider="PageSpeed Insights / CrUX", state="unavailable",
            reason="psi_distribution_source_mismatch", scope=field.get("scope"),
            source_url=field.get("source_url"),
            source_contract=validation.get("version") or "nextgen_pagespeed_bound_integrity_v1",
        )
    raw_metrics = experience.get("metrics") if isinstance(experience, dict) else None
    return _finish(
        provider="PageSpeed Insights / CrUX",
        source_contract=validation.get("version") or "nextgen_pagespeed_bound_integrity_v1",
        field=field,
        raw_metrics=raw_metrics,
        provider_kind="psi",
    )


def validate_field_distribution_contract(evidence: Any) -> dict[str, Any]:
    """Validate provider-neutral field distributions without promoting missing data."""
    reasons: list[str] = []
    if not isinstance(evidence, dict):
        return {"version": FIELD_DISTRIBUTION_INTEGRITY_VERSION, "valid": False, "reasons": ["evidence_not_object"]}
    if evidence.get("version") != FIELD_DISTRIBUTION_VERSION:
        reasons.append("version_mismatch")
    if evidence.get("evidence_kind") != "field":
        reasons.append("evidence_kind_mismatch")
    provider = evidence.get("provider")
    expected_source_contract = {
        "CrUX": "nextgen_crux_bound_integrity_v1",
        "PageSpeed Insights / CrUX": "nextgen_pagespeed_bound_integrity_v1",
    }.get(provider)
    if expected_source_contract is None:
        reasons.append("provider_invalid")
    source_contract = evidence.get("source_contract")
    if source_contract not in {"nextgen_crux_bound_integrity_v1", "nextgen_pagespeed_bound_integrity_v1"}:
        reasons.append("source_contract_invalid")
    elif expected_source_contract is not None and source_contract != expected_source_contract:
        reasons.append("provider_source_contract_mismatch")
    state = evidence.get("state")
    if state not in PROVIDER_STATES:
        reasons.append("state_invalid")
    scope = evidence.get("scope")
    if scope is not None and scope not in {"url", "origin"}:
        reasons.append("scope_invalid")
    source_url = evidence.get("source_url")
    if source_url is not None and _http_identity(source_url) is None:
        reasons.append("source_url_invalid")
    omitted = evidence.get("omitted_metrics")
    if not isinstance(omitted, list):
        reasons.append("omitted_metrics_invalid")
    else:
        seen_omitted: set[str] = set()
        for row in omitted:
            if not isinstance(row, dict) or row.get("metric") not in METRICS or not _text(row.get("reason")):
                reasons.append("omitted_metric_invalid")
                continue
            if row["metric"] in seen_omitted:
                reasons.append("omitted_metric_duplicate")
            seen_omitted.add(row["metric"])

    metrics = evidence.get("metrics")
    if state != "connected":
        if metrics is not None:
            reasons.append("non_connected_retained_metrics")
        return {"version": FIELD_DISTRIBUTION_INTEGRITY_VERSION, "valid": not reasons, "reasons": sorted(set(reasons))}
    if not isinstance(metrics, dict) or not metrics:
        reasons.append("connected_metrics_missing")
        metrics = {}
    for canonical, metric in metrics.items():
        if canonical not in METRICS:
            reasons.append("metric_unsupported")
            continue
        if not isinstance(metric, dict):
            reasons.append("metric_not_object")
            continue
        if metric.get("unit") != METRICS[canonical]["unit"] or _number(metric.get("p75")) is None:
            reasons.append("metric_summary_invalid")
        bins = metric.get("bins")
        if not isinstance(bins, list) or not bins:
            reasons.append("metric_bins_invalid")
            continue
        previous_upper: float | None = None
        total = 0.0
        for index, row in enumerate(bins):
            if not isinstance(row, dict):
                reasons.append("metric_bin_invalid")
                continue
            lower = _number(row.get("min"))
            upper = None if row.get("max") is None else _number(row.get("max"))
            proportion = _number(row.get("proportion"))
            if lower is None or proportion is None or proportion > 1 or (upper is not None and upper <= lower):
                reasons.append("metric_bin_invalid")
                continue
            if index and previous_upper is None:
                reasons.append("metric_bin_after_open_range")
            if previous_upper is not None and lower < previous_upper:
                reasons.append("metric_bin_overlap")
            previous_upper = upper
            total += proportion
        if abs(total - 1.0) > 0.005:
            reasons.append("metric_distribution_mass_invalid")
    if isinstance(omitted, list):
        overlap = set(metrics) & {row.get("metric") for row in omitted if isinstance(row, dict)}
        if overlap:
            reasons.append("metric_present_and_omitted")
    return {"version": FIELD_DISTRIBUTION_INTEGRITY_VERSION, "valid": not reasons, "reasons": sorted(set(reasons))}
