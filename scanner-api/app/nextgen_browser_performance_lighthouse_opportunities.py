"""Pure strict normalization for Lighthouse opportunity lab evidence.

This helper consumes already-observed Lighthouse JSON plus Lane-C source-bound
Lighthouse evidence. It performs no provider calls, creates no credentials, and
never grants browser execution budget. Opportunity savings remain lab-only and
are rebuilt from the raw provider payload so numeric values are never guessed to
be milliseconds or bytes when the provider unit is absent or contradictory.
"""
from __future__ import annotations

from math import isfinite
from typing import Any
from urllib.parse import urlsplit, urlunsplit

LIGHTHOUSE_OPPORTUNITY_VERSION = "nextgen_lighthouse_opportunity_evidence_v1"
LIGHTHOUSE_OPPORTUNITY_INTEGRITY_VERSION = "nextgen_lighthouse_opportunity_integrity_v1"
SOURCE_LIGHTHOUSE_VERSION = "nextgen_lighthouse_evidence_v1"
SOURCE_LIGHTHOUSE_ADAPTER_VERSION = "nextgen_lighthouse_bound_provider_v1"
SOURCE_LIGHTHOUSE_PROVENANCE_VERSION = "nextgen_lighthouse_provenance_v1"

SOURCE_STATES = {"connected", "disconnected", "unavailable", "rate_limited", "provider_error"}
OPPORTUNITY_STATES = {"normalized", "not_applicable", "not_verified"}
ALLOWED_AUDITS = (
    "render-blocking-resources",
    "unused-javascript",
    "unused-css-rules",
    "modern-image-formats",
    "uses-responsive-images",
    "uses-optimized-images",
    "offscreen-images",
    "legacy-javascript",
    "third-party-summary",
)
_TIME_UNITS = {"ms", "millisecond", "milliseconds"}
_BYTE_UNITS = {"byte", "bytes"}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if isfinite(number) and number >= 0 else None


def _unit_interval(value: Any) -> float | None:
    number = _number(value)
    return number if number is not None and number <= 1 else None


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
    if parsed.username is not None or parsed.password is not None:
        return None
    return urlunsplit((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        parsed.path or "/",
        parsed.query,
        "",
    ))


def _base(source: Any) -> dict[str, Any]:
    evidence = source if isinstance(source, dict) else {}
    provenance = evidence.get("provenance") if isinstance(evidence.get("provenance"), dict) else {}
    return {
        "version": LIGHTHOUSE_OPPORTUNITY_VERSION,
        "evidence_kind": "lab_opportunities",
        "state": "not_verified",
        "reason": None,
        "source_version": evidence.get("version"),
        "source_adapter_version": evidence.get("adapter_version"),
        "source_provenance_version": provenance.get("version"),
        "source_state": evidence.get("state"),
        "source_url": evidence.get("source_url"),
        "requested_url": provenance.get("requested_url"),
        "provider_requested_url": provenance.get("provider_requested_url"),
        "final_url": provenance.get("final_url"),
        "opportunities": [],
        "excluded_opportunities": [],
    }


def _source_rejection(source: Any) -> str | None:
    if not isinstance(source, dict):
        return "source_not_object"
    if source.get("version") != SOURCE_LIGHTHOUSE_VERSION:
        return "source_version_mismatch"
    if source.get("evidence_kind") != "lab":
        return "source_not_lab_evidence"
    if source.get("adapter_version") != SOURCE_LIGHTHOUSE_ADAPTER_VERSION:
        return "source_adapter_version_mismatch"
    state = source.get("state")
    if state not in SOURCE_STATES:
        return "source_state_invalid"
    if state != "connected":
        return f"source_{state}"
    provenance = source.get("provenance")
    if not isinstance(provenance, dict):
        return "source_provenance_missing"
    if provenance.get("version") != SOURCE_LIGHTHOUSE_PROVENANCE_VERSION:
        return "source_provenance_version_mismatch"

    requested = _http_identity(provenance.get("requested_url"))
    provider_requested = _http_identity(provenance.get("provider_requested_url"))
    final_url = _http_identity(provenance.get("final_url")) if provenance.get("final_url") is not None else None
    source_url = _http_identity(source.get("source_url"))
    if requested is None or provider_requested is None or source_url is None:
        return "source_identity_invalid"
    if requested != provider_requested:
        return "source_requested_identity_mismatch"
    if source_url != (final_url or requested):
        return "source_final_identity_mismatch"
    return None


def _raw_rejection(payload: Any, source: dict[str, Any]) -> str | None:
    if not isinstance(payload, dict):
        return "provider_payload_missing"
    if isinstance(payload.get("runtimeError"), dict):
        return "provider_runtime_error"
    provenance = source.get("provenance")
    requested = _http_identity(payload.get("requestedUrl"))
    final_raw = payload.get("finalUrl")
    final_url = _http_identity(final_raw) if final_raw is not None else None
    expected_requested = _http_identity(provenance.get("provider_requested_url"))
    expected_final = _http_identity(provenance.get("final_url")) if provenance.get("final_url") is not None else None
    if requested is None:
        return "provider_requested_identity_invalid"
    if requested != expected_requested:
        return "provider_requested_identity_mismatch"
    if final_raw is not None and final_url is None:
        return "provider_final_identity_invalid"
    if final_url != expected_final:
        return "provider_final_identity_mismatch"
    return None


def normalize_lighthouse_opportunity_evidence(payload: Any, source: Any) -> dict[str, Any]:
    """Rebuild bounded Lighthouse opportunity evidence with explicit unit semantics.

    ``details.overallSavingsMs`` and ``details.overallSavingsBytes`` are trusted
    as typed provider fields. ``numericValue`` is used only when ``numericUnit``
    explicitly identifies milliseconds or bytes; otherwise it is never guessed.
    """
    result = _base(source)
    rejection = _source_rejection(source)
    if rejection is not None:
        return {**result, "reason": rejection}
    rejection = _raw_rejection(payload, source)
    if rejection is not None:
        return {**result, "reason": rejection}

    audits = payload.get("audits")
    if not isinstance(audits, dict):
        return {**result, "reason": "provider_audits_missing"}

    present = [audit_id for audit_id in ALLOWED_AUDITS if audit_id in audits]
    if not present:
        return {**result, "state": "not_applicable", "reason": "allowlisted_opportunities_absent"}

    normalized: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for audit_id in present:
        audit = audits.get(audit_id)
        if not isinstance(audit, dict):
            excluded.append({"audit_id": audit_id, "reason": "audit_not_object"})
            continue
        if _text(audit.get("errorMessage")) or _text(audit.get("scoreDisplayMode")).lower() == "error":
            excluded.append({"audit_id": audit_id, "reason": "audit_error"})
            continue

        details = audit.get("details") if isinstance(audit.get("details"), dict) else {}
        savings_ms = _number(details.get("overallSavingsMs"))
        savings_bytes = _number(details.get("overallSavingsBytes"))
        score = _unit_interval(audit.get("score"))
        numeric = _number(audit.get("numericValue"))
        unit = _text(audit.get("numericUnit")).lower()
        explicit_savings = savings_ms is not None or savings_bytes is not None

        if not explicit_savings and numeric is not None:
            if unit in _TIME_UNITS:
                savings_ms = numeric
            elif unit in _BYTE_UNITS:
                savings_bytes = numeric
            else:
                excluded.append({
                    "audit_id": audit_id,
                    "reason": "numeric_unit_unverified",
                    "raw_unit": unit or None,
                })

        if score is None and savings_ms is None and savings_bytes is None:
            if not any(row.get("audit_id") == audit_id for row in excluded):
                excluded.append({"audit_id": audit_id, "reason": "no_trusted_measurements"})
            continue
        normalized.append({
            "audit_id": audit_id,
            "score": score,
            "estimated_savings_ms": savings_ms,
            "estimated_savings_bytes": savings_bytes,
        })

    if normalized:
        return {
            **result,
            "state": "normalized",
            "opportunities": normalized,
            "excluded_opportunities": excluded,
        }
    return {
        **result,
        "reason": "all_opportunity_measurements_unverified",
        "excluded_opportunities": excluded,
    }


def validate_lighthouse_opportunity_contract(payload: Any, source: Any, evidence: Any) -> dict[str, Any]:
    """Bind a derived opportunity artifact to the exact raw/source observations."""
    reasons: list[str] = []
    if not isinstance(evidence, dict):
        return {
            "version": LIGHTHOUSE_OPPORTUNITY_INTEGRITY_VERSION,
            "valid": False,
            "reasons": ["evidence_not_object"],
        }
    if evidence.get("version") != LIGHTHOUSE_OPPORTUNITY_VERSION:
        reasons.append("version_mismatch")
    if evidence.get("evidence_kind") != "lab_opportunities":
        reasons.append("evidence_kind_mismatch")
    if evidence.get("state") not in OPPORTUNITY_STATES:
        reasons.append("state_invalid")
    expected = normalize_lighthouse_opportunity_evidence(payload, source)
    if evidence != expected:
        reasons.append("evidence_source_mismatch")
    return {
        "version": LIGHTHOUSE_OPPORTUNITY_INTEGRITY_VERSION,
        "valid": not reasons,
        "reasons": sorted(set(reasons)),
    }
