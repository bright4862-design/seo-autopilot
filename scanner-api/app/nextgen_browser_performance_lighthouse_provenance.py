"""Strict source/provenance binding for direct Lighthouse lab evidence.

This module is additive and pure. It accepts already-observed Lighthouse JSON,
performs no network I/O, creates no credentials, and never grants browser or
provider execution budget. Field-performance evidence is intentionally absent:
this contract is lab-only and must remain separate from CrUX field evidence.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app.nextgen_browser_performance import normalize_lighthouse_evidence
from app.nextgen_browser_performance_contract import validate_lighthouse_contract

LIGHTHOUSE_BOUND_ADAPTER_VERSION = "nextgen_lighthouse_bound_provider_v1"
LIGHTHOUSE_PROVENANCE_VERSION = "nextgen_lighthouse_provenance_v1"
LIGHTHOUSE_BOUND_INTEGRITY_VERSION = "nextgen_lighthouse_bound_integrity_v1"


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
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
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
    value = _text(settings.get("emulatedFormFactor")).lower()
    return value if value in {"mobile", "desktop"} else None


def _runtime_error(payload: Any) -> dict[str, str | None] | None:
    if not isinstance(payload, dict):
        return None
    runtime = payload.get("runtimeError")
    if not isinstance(runtime, dict):
        return None
    code = _text(runtime.get("code")) or None
    message = _text(runtime.get("message")) or None
    return {"code": code, "message": message} if code or message else None


def _error_audit_ids(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    audits = payload.get("audits")
    if not isinstance(audits, dict):
        return []
    failed: list[str] = []
    for audit_id, audit in audits.items():
        if not isinstance(audit_id, str) or not isinstance(audit, dict):
            continue
        display_mode = _text(audit.get("scoreDisplayMode")).lower()
        if _text(audit.get("errorMessage")) or display_mode == "error":
            failed.append(audit_id)
    return sorted(set(failed))


def _sanitize_failed_audits(payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    clone = deepcopy(payload)
    failed = _error_audit_ids(clone)
    audits = clone.get("audits")
    if isinstance(audits, dict):
        for audit_id in failed:
            audits.pop(audit_id, None)
    return clone, failed


def _provenance(
    *,
    requested_url: str | None,
    provider_requested_url: str | None,
    final_url: str | None,
    fetch_time: str | None,
    lighthouse_version: str | None,
    strategy: str | None,
    runtime_error: dict[str, str | None] | None,
    excluded_error_audits: list[str],
) -> dict[str, Any]:
    return {
        "version": LIGHTHOUSE_PROVENANCE_VERSION,
        "requested_url": requested_url,
        "provider_requested_url": provider_requested_url,
        "final_url": final_url,
        "fetch_time": fetch_time,
        "lighthouse_version": lighthouse_version,
        "strategy": strategy,
        "runtime_error": runtime_error,
        "excluded_error_audits": excluded_error_audits,
    }


def _with_metadata(
    evidence: dict[str, Any],
    provenance: dict[str, Any],
) -> dict[str, Any]:
    return {
        **evidence,
        "adapter_version": LIGHTHOUSE_BOUND_ADAPTER_VERSION,
        "provenance": provenance,
    }


def normalize_lighthouse_evidence_bound(
    payload: dict[str, Any] | None,
    *,
    provider: str = "Lighthouse",
    state: str = "connected",
    observed_at: str | None = None,
    source_url: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Normalize direct Lighthouse lab evidence with fail-closed provenance.

    If ``source_url`` is supplied, connected evidence requires the provider's
    ``requestedUrl`` and it must match that caller identity. Redirects are valid:
    a distinct valid ``finalUrl`` becomes the lab evidence source. Lighthouse
    ``runtimeError`` turns the lab component into ``provider_error``. Individual
    audits explicitly marked as errors are excluded rather than retained as
    measurements.
    """
    requested = _http_identity(source_url) if source_url is not None else None
    provider_payload = payload if isinstance(payload, dict) else {}
    provider_requested_raw = (
        provider_payload.get("requestedUrl") if isinstance(payload, dict) else None
    )
    final_raw = provider_payload.get("finalUrl") if isinstance(payload, dict) else None
    provider_requested = _http_identity(provider_requested_raw)
    final_url = _http_identity(final_raw)
    fetch_time = _text(provider_payload.get("fetchTime")) or None
    lighthouse_version = _text(provider_payload.get("lighthouseVersion")) or None
    strategy = _strategy(provider_payload)
    runtime_error = _runtime_error(provider_payload)
    excluded_error_audits = _error_audit_ids(provider_payload)

    def finish(
        evidence: dict[str, Any],
        *,
        requested_identity: str | None = requested or provider_requested,
    ) -> dict[str, Any]:
        return _with_metadata(
            evidence,
            _provenance(
                requested_url=requested_identity,
                provider_requested_url=provider_requested,
                final_url=final_url,
                fetch_time=fetch_time,
                lighthouse_version=lighthouse_version,
                strategy=strategy,
                runtime_error=runtime_error,
                excluded_error_audits=excluded_error_audits,
            ),
        )

    if source_url is not None and requested is None:
        return finish(normalize_lighthouse_evidence(
            None,
            provider=provider,
            state="unavailable",
            observed_at=observed_at,
            source_url=source_url,
            reason=reason or "lighthouse_source_identity_invalid",
        ), requested_identity=None)

    normalized_state = _text(state).lower()
    if normalized_state != "connected":
        return finish(normalize_lighthouse_evidence(
            None,
            provider=provider,
            state=state,
            observed_at=observed_at,
            source_url=requested,
            reason=reason,
        ))

    if not isinstance(payload, dict):
        return finish(normalize_lighthouse_evidence(
            None,
            provider=provider,
            state="unavailable",
            observed_at=observed_at,
            source_url=requested,
            reason=reason or "lighthouse_payload_missing",
        ))

    if provider_requested_raw is None:
        return finish(normalize_lighthouse_evidence(
            None,
            provider=provider,
            state="unavailable",
            observed_at=observed_at,
            source_url=requested,
            reason=reason or "lighthouse_requested_identity_missing",
        ))
    if provider_requested is None:
        return finish(normalize_lighthouse_evidence(
            None,
            provider=provider,
            state="unavailable",
            observed_at=observed_at,
            source_url=requested,
            reason=reason or "lighthouse_requested_identity_invalid",
        ))
    if requested and requested != provider_requested:
        return finish(normalize_lighthouse_evidence(
            None,
            provider=provider,
            state="unavailable",
            observed_at=observed_at,
            source_url=requested,
            reason=reason or "lighthouse_requested_identity_mismatch",
        ))
    if final_raw is not None and final_url is None:
        return finish(normalize_lighthouse_evidence(
            None,
            provider=provider,
            state="unavailable",
            observed_at=observed_at,
            source_url=requested or provider_requested,
            reason=reason or "lighthouse_final_identity_invalid",
        ))

    bound_requested = requested or provider_requested
    bound_source = final_url or bound_requested
    effective_observed_at = _text(observed_at) or fetch_time

    if runtime_error is not None:
        return finish(normalize_lighthouse_evidence(
            None,
            provider=provider,
            state="provider_error",
            observed_at=effective_observed_at,
            source_url=bound_source,
            reason=reason or "lighthouse_runtime_error",
        ), requested_identity=bound_requested)

    sanitized, excluded_error_audits = _sanitize_failed_audits(payload)
    evidence = normalize_lighthouse_evidence(
        sanitized,
        provider=provider,
        state="connected",
        observed_at=effective_observed_at,
        source_url=bound_source,
        reason=reason,
    )
    provenance = _provenance(
        requested_url=bound_requested,
        provider_requested_url=provider_requested,
        final_url=final_url,
        fetch_time=fetch_time,
        lighthouse_version=lighthouse_version,
        strategy=strategy,
        runtime_error=None,
        excluded_error_audits=excluded_error_audits,
    )
    return _with_metadata(evidence, provenance)


def validate_bound_lighthouse_contract(evidence: Any) -> dict[str, Any]:
    """Validate both the existing lab contract and the additive provenance binding."""
    reasons: list[str] = []
    if not isinstance(evidence, dict):
        return {
            "version": LIGHTHOUSE_BOUND_INTEGRITY_VERSION,
            "valid": False,
            "reasons": ["evidence_not_object"],
        }

    base = validate_lighthouse_contract(evidence)
    if not base.get("valid"):
        reasons.extend(f"lab:{item}" for item in base.get("reasons", []))

    if evidence.get("adapter_version") != LIGHTHOUSE_BOUND_ADAPTER_VERSION:
        reasons.append("adapter_version_mismatch")

    provenance = evidence.get("provenance")
    if not isinstance(provenance, dict):
        reasons.append("provenance_missing")
        provenance = {}
    elif provenance.get("version") != LIGHTHOUSE_PROVENANCE_VERSION:
        reasons.append("provenance_version_mismatch")

    requested = _http_identity(provenance.get("requested_url"))
    provider_requested = _http_identity(provenance.get("provider_requested_url"))
    final_url = _http_identity(provenance.get("final_url"))
    source_url = _http_identity(evidence.get("source_url"))

    for key in ("requested_url", "provider_requested_url", "final_url"):
        value = provenance.get(key)
        if value is not None and _http_identity(value) is None:
            reasons.append(f"{key}_invalid")

    strategy = provenance.get("strategy")
    if strategy is not None and strategy not in {"mobile", "desktop"}:
        reasons.append("strategy_invalid")

    runtime_error = provenance.get("runtime_error")
    if runtime_error is not None:
        if not isinstance(runtime_error, dict):
            reasons.append("runtime_error_invalid")
        elif not (_text(runtime_error.get("code")) or _text(runtime_error.get("message"))):
            reasons.append("runtime_error_empty")

    excluded = provenance.get("excluded_error_audits")
    if not isinstance(excluded, list) or any(
        not isinstance(item, str) or not item for item in excluded
    ):
        reasons.append("excluded_error_audits_invalid")
    elif len(excluded) != len(set(excluded)):
        reasons.append("excluded_error_audits_duplicate")

    if evidence.get("state") == "connected":
        if requested is None:
            reasons.append("connected_requested_identity_missing")
        if provider_requested is None:
            reasons.append("connected_provider_requested_identity_missing")
        elif requested is not None and provider_requested != requested:
            reasons.append("connected_requested_identity_mismatch")
        if source_url is None:
            reasons.append("connected_source_identity_missing")
        expected_source = final_url or requested
        if source_url is not None and expected_source is not None and source_url != expected_source:
            reasons.append("connected_source_identity_mismatch")
        if runtime_error is not None:
            reasons.append("connected_with_runtime_error")

    return {
        "version": LIGHTHOUSE_BOUND_INTEGRITY_VERSION,
        "valid": not reasons,
        "reasons": sorted(set(reasons)),
    }
