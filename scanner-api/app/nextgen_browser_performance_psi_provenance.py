"""Source-bound PageSpeed Insights provenance for Lane-C browser/performance evidence.

This module accepts already-observed PSI payloads only. It performs no network I/O,
creates no credentials, and keeps field (CrUX) evidence separate from lab
(Lighthouse) evidence. It layers strict source/provenance checks over the existing
provider-shape adapter without changing shared orchestration.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app.nextgen_browser_performance import (
    normalize_field_performance_evidence,
    normalize_lighthouse_evidence,
)
from app.nextgen_browser_performance_provider import (
    PROVIDER_ADAPTER_VERSION,
    normalize_pagespeed_insights_evidence_strict,
)

PSI_BOUND_ADAPTER_VERSION = "nextgen_pagespeed_bound_provider_v1"
PSI_PROVENANCE_VERSION = "nextgen_pagespeed_provenance_v1"


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
    path = parsed.path or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.query, ""))


def _origin(identity: str | None) -> str | None:
    if not identity:
        return None
    parsed = urlsplit(identity)
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), "/", "", ""))


def _component_unavailable(*, kind: str, reason: str, observed_at: str | None,
    source_url: str | None, state: str = "unavailable") -> dict[str, Any]:
    if kind == "field":
        return normalize_field_performance_evidence(
            provider="PageSpeed Insights / CrUX",
            state=state,
            observed_at=observed_at,
            source_url=source_url,
            reason=reason,
        )
    return normalize_lighthouse_evidence(
        None,
        provider="PageSpeed Insights / Lighthouse",
        state=state,
        observed_at=observed_at,
        source_url=source_url,
        reason=reason,
    )


def _runtime_error(lighthouse: Any) -> bool:
    if not isinstance(lighthouse, dict):
        return False
    runtime = lighthouse.get("runtimeError")
    if not isinstance(runtime, dict):
        return False
    return bool(_text(runtime.get("code")) or _text(runtime.get("message")))


def _strategy(lighthouse: Any) -> str | None:
    if not isinstance(lighthouse, dict):
        return None
    settings = lighthouse.get("configSettings")
    if not isinstance(settings, dict):
        return None
    value = _text(settings.get("emulatedFormFactor")).lower()
    return value if value in {"mobile", "desktop"} else None


def normalize_pagespeed_insights_evidence_bound(payload: dict[str, Any] | None, *,
    state: str = "connected", observed_at: str | None = None,
    source_url: str | None = None, reason: str | None = None) -> dict[str, Any]:
    """Bind a PSI response to its requested/final identities and runtime provenance.

    Caller ``source_url`` is the requested page identity. Redirects are allowed: the
    provider's final document identity may differ, but connected evidence is retained
    only when the provider supplies the corresponding requested identity and it
    corroborates the caller. A contradictory or missing provider
    ``requestedUrl``/``initial_url`` fails only the affected evidence component
    closed. A Lighthouse ``runtimeError`` invalidates lab evidence without discarding
    otherwise valid CrUX field evidence.
    """
    if source_url is not None and _http_identity(source_url) is None:
        why = reason or "psi_source_identity_invalid"
        return {
            "version": "nextgen_performance_evidence_v1",
            "provider": "PageSpeed Insights",
            "adapter_version": PSI_BOUND_ADAPTER_VERSION,
            "base_adapter_version": PROVIDER_ADAPTER_VERSION,
            "field": _component_unavailable(
                kind="field", reason=why, observed_at=observed_at, source_url=source_url,
            ),
            "lab": _component_unavailable(
                kind="lab", reason=why, observed_at=observed_at, source_url=source_url,
            ),
            "provenance": {
                "version": PSI_PROVENANCE_VERSION,
                "requested_url": None,
                "response_final_url": None,
                "field_source_url": None,
                "field_initial_url": None,
                "field_origin_fallback": None,
                "lighthouse_requested_url": None,
                "lighthouse_final_url": None,
                "analysis_timestamp": _text(observed_at) or None,
                "lighthouse_fetch_time": None,
                "lighthouse_version": None,
                "strategy": None,
            },
        }

    requested = _http_identity(source_url) if source_url is not None else None
    provider_payload = payload if isinstance(payload, dict) else {}
    analysis_timestamp = _text(observed_at) or _text(provider_payload.get("analysisUTCTimestamp")) or None

    base = normalize_pagespeed_insights_evidence_strict(
        payload,
        state=state,
        observed_at=analysis_timestamp,
        source_url=requested,
        reason=reason,
    )
    field = deepcopy(base.get("field"))
    lab = deepcopy(base.get("lab"))

    response_final = _http_identity(provider_payload.get("id"))
    lighthouse = provider_payload.get("lighthouseResult")
    lighthouse = lighthouse if isinstance(lighthouse, dict) else {}
    lh_requested_raw = lighthouse.get("requestedUrl")
    lh_final_raw = lighthouse.get("finalUrl")
    lh_requested = _http_identity(lh_requested_raw)
    lh_final = _http_identity(lh_final_raw)
    lh_fetch_time = _text(lighthouse.get("fetchTime")) or None
    lh_version = _text(lighthouse.get("lighthouseVersion")) or None

    # Bind lab evidence to the documented requested/final identities. Redirects are
    # valid, so only the requested identity must equal the caller's source identity.
    # When the caller supplies a source identity, absence of the provider's requested
    # identity is not sufficient provenance to keep lab evidence connected.
    if isinstance(lab, dict) and lab.get("state") == "connected":
        if requested and lh_requested_raw is None:
            lab = _component_unavailable(
                kind="lab", reason="lighthouse_requested_identity_missing",
                observed_at=analysis_timestamp, source_url=requested,
            )
        elif lh_requested_raw is not None and lh_requested is None:
            lab = _component_unavailable(
                kind="lab", reason="lighthouse_requested_identity_invalid",
                observed_at=analysis_timestamp, source_url=requested,
            )
        elif requested and lh_requested and requested != lh_requested:
            lab = _component_unavailable(
                kind="lab", reason="lighthouse_requested_identity_mismatch",
                observed_at=analysis_timestamp, source_url=requested,
            )
        elif lh_final_raw is not None and lh_final is None:
            lab = _component_unavailable(
                kind="lab", reason="lighthouse_final_identity_invalid",
                observed_at=analysis_timestamp, source_url=requested,
            )
        elif _runtime_error(lighthouse):
            lab = _component_unavailable(
                kind="lab", reason="lighthouse_runtime_error",
                observed_at=analysis_timestamp, source_url=lh_final or requested,
                state="provider_error",
            )
        elif lh_final:
            lab["source_url"] = lh_final
            if not lab.get("observed_at") and lh_fetch_time:
                lab["observed_at"] = lh_fetch_time

    # Bind field evidence to the documented loading-experience identity. PSI may
    # explicitly say page-level data is an origin fallback; preserve that truth.
    field_scope = field.get("scope") if isinstance(field, dict) else None
    experience = (
        provider_payload.get("loadingExperience")
        if field_scope == "url"
        else provider_payload.get("originLoadingExperience")
    )
    experience = experience if isinstance(experience, dict) else {}
    field_id_raw = experience.get("id")
    field_initial_raw = experience.get("initial_url")
    field_id = _http_identity(field_id_raw)
    field_initial = _http_identity(field_initial_raw)
    origin_fallback = experience.get("origin_fallback")
    origin_fallback = origin_fallback if isinstance(origin_fallback, bool) else None

    if isinstance(field, dict) and field.get("state") == "connected":
        # If the caller names the page whose PSI observation is being normalized,
        # require the provider's documented initial request identity. The provider
        # field ``id`` alone identifies the subject/final scope and cannot prove that
        # this response was requested for the caller page.
        if requested and field_initial_raw is None:
            field = _component_unavailable(
                kind="field", reason="psi_field_initial_identity_missing",
                observed_at=analysis_timestamp, source_url=requested,
            )
        elif field_initial_raw is not None and field_initial is None:
            field = _component_unavailable(
                kind="field", reason="psi_field_initial_identity_invalid",
                observed_at=analysis_timestamp, source_url=requested,
            )
        elif requested and field_initial and requested != field_initial:
            field = _component_unavailable(
                kind="field", reason="psi_field_initial_identity_mismatch",
                observed_at=analysis_timestamp, source_url=requested,
            )
        elif field_id_raw is not None and field_id is None:
            field = _component_unavailable(
                kind="field", reason="psi_field_identity_invalid",
                observed_at=analysis_timestamp, source_url=requested,
            )
        else:
            if field_scope == "url" and origin_fallback is True:
                field["scope"] = "origin"
                if field_id:
                    field["source_url"] = _origin(field_id)
                elif requested:
                    field["source_url"] = _origin(requested)
            elif field_id:
                field["source_url"] = _origin(field_id) if field_scope == "origin" else field_id

            bound_source = field.get("source_url")
            if requested and field.get("scope") == "origin" and bound_source:
                if _origin(requested) != _origin(bound_source):
                    field = _component_unavailable(
                        kind="field", reason="psi_field_origin_identity_mismatch",
                        observed_at=analysis_timestamp, source_url=requested,
                    )

    provenance = {
        "version": PSI_PROVENANCE_VERSION,
        "requested_url": requested or lh_requested or field_initial,
        "response_final_url": response_final,
        "field_source_url": field.get("source_url") if isinstance(field, dict) else None,
        "field_initial_url": field_initial,
        "field_origin_fallback": origin_fallback,
        "lighthouse_requested_url": lh_requested,
        "lighthouse_final_url": lh_final,
        "analysis_timestamp": analysis_timestamp,
        "lighthouse_fetch_time": lh_fetch_time,
        "lighthouse_version": lh_version,
        "strategy": _strategy(lighthouse),
    }
    return {
        **base,
        "adapter_version": PSI_BOUND_ADAPTER_VERSION,
        "base_adapter_version": PROVIDER_ADAPTER_VERSION,
        "field": field,
        "lab": lab,
        "provenance": provenance,
    }
