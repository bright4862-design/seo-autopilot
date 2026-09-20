"""Fail-closed Stage-2 envelopes for optional connected CrUX/GSC evidence.

These helpers do not perform network I/O or grant provider access. They only
sanitize evidence already supplied by an authenticated integration layer. Exact
scan identity and the retained Standard-150 URL set are required before page
metrics can be admitted, so stale/cross-scan/provider data cannot silently
become current scan evidence.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Iterable

from .stage2_coverage_evidence import (
    CRUX_ADAPTER_VERSION,
    GSC_ADAPTER_VERSION,
    optional_crux_adapter,
    optional_gsc_adapter,
)

CONNECTED_PROVIDER_EVIDENCE_VERSION = "connected_provider_evidence_v1"
MAX_PROVIDER_PAGES = 150


def _text(value: Any) -> str:
    return str(value or "").strip()


def _date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    raw = _text(value)
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _assessed_url_set(values: Iterable[Any]) -> set[str]:
    urls = {_text(value) for value in values if _text(value)}
    if len(urls) > MAX_PROVIDER_PAGES:
        raise ValueError("Expected at most 150 assessed URLs")
    return urls


def _base(*, provider: str, adapter_version: str, expected_scan_id: str, payload: dict[str, Any] | None) -> dict[str, Any]:
    source_scan_id = _text(payload.get("scan_id")) if isinstance(payload, dict) else ""
    return {
        "version": CONNECTED_PROVIDER_EVIDENCE_VERSION,
        "adapter_version": adapter_version,
        "provider": provider,
        "scan_id": _text(expected_scan_id),
        "source_scan_id": source_scan_id or None,
        "state": "unavailable",
        "reason": "provider_payload_missing" if not isinstance(payload, dict) else "provider_evidence_unavailable",
        "observed_at": None,
        "coverage_complete_claim": False,
    }


def _connection_gate(*, expected_scan_id: str, payload: dict[str, Any] | None, base: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    if not isinstance(payload, dict):
        return base, None
    state = _text(payload.get("connection_state"))
    if state not in {"connected", "disconnected", "unavailable"}:
        return {**base, "reason": "provider_connection_state_invalid"}, None
    if state != "connected":
        return {
            **base,
            "state": state,
            "reason": "provider_disconnected" if state == "disconnected" else "provider_unavailable",
        }, None
    if payload.get("authorized") is not True:
        return {**base, "reason": "owner_authorization_unverified"}, None
    source_scan_id = _text(payload.get("scan_id"))
    if not source_scan_id or source_scan_id != _text(expected_scan_id):
        return {**base, "reason": "scan_identity_mismatch"}, None
    return base, state


def build_crux_scan_evidence(
    *,
    expected_scan_id: str,
    payload: dict[str, Any] | None,
    as_of: date,
) -> dict[str, Any]:
    """Sanitize optional CrUX evidence without inferring performance from HTML."""
    base = _base(
        provider="CrUX",
        adapter_version=CRUX_ADAPTER_VERSION,
        expected_scan_id=expected_scan_id,
        payload=payload,
    )
    gated, connected = _connection_gate(
        expected_scan_id=expected_scan_id,
        payload=payload,
        base=base,
    )
    if connected is None:
        return {**gated, "scope": None, "metrics": None}

    observed_at = _date(payload.get("observed_at"))
    adapted = optional_crux_adapter(
        connection_state="connected",
        observed_at=observed_at,
        as_of=as_of,
        scope=_text(payload.get("scope")),
        metrics=payload.get("metrics") if isinstance(payload.get("metrics"), dict) else None,
    )
    return {
        **gated,
        "state": adapted["state"],
        "reason": {
            "connected": "authorized_current_crux_evidence",
            "stale": "crux_evidence_stale",
        }.get(adapted["state"], "crux_evidence_unavailable"),
        "observed_at": adapted.get("observed_at"),
        "scope": adapted.get("scope"),
        "metrics": adapted.get("metrics"),
    }


def build_gsc_scan_evidence(
    *,
    expected_scan_id: str,
    assessed_urls: Iterable[Any],
    payload: dict[str, Any] | None,
    as_of: date,
) -> dict[str, Any]:
    """Sanitize optional page-level GSC evidence for the exact current scan.

    Connected data is admitted only for exact URLs in the retained assessed set.
    Query strings/search queries or arbitrary provider fields are never retained.
    Duplicate conflicting rows fail closed for that URL rather than choosing one.
    """
    allowed = _assessed_url_set(assessed_urls)
    base = _base(
        provider="Google Search Console",
        adapter_version=GSC_ADAPTER_VERSION,
        expected_scan_id=expected_scan_id,
        payload=payload,
    )
    common = {
        **base,
        "assessed_url_count": len(allowed),
        "candidate_page_rows": 0,
        "selected_page_rows": 0,
        "rejected_outside_scan": 0,
        "duplicate_conflicts": 0,
        "pages": [],
    }
    gated, connected = _connection_gate(
        expected_scan_id=expected_scan_id,
        payload=payload,
        base=common,
    )
    if connected is None:
        return gated

    observed_at = _date(payload.get("observed_at"))
    raw_rows = payload.get("pages")
    if not isinstance(raw_rows, list):
        return {**gated, "reason": "gsc_page_metrics_unavailable"}

    by_url: dict[str, list[dict[str, Any]]] = {}
    rejected = 0
    for item in raw_rows:
        if not isinstance(item, dict):
            continue
        url = _text(item.get("url"))
        if not url or url not in allowed:
            rejected += 1
            continue
        by_url.setdefault(url, []).append(item)

    pages: list[dict[str, Any]] = []
    conflicts = 0
    for url in sorted(by_url):
        rows = by_url[url]
        metric_shapes = [row.get("metrics") for row in rows if isinstance(row.get("metrics"), dict)]
        if len(rows) > 1 and len({repr(sorted(metrics.items())) for metrics in metric_shapes}) > 1:
            conflicts += 1
            pages.append({
                "url": url,
                "state": "unavailable",
                "reason": "duplicate_page_metrics_conflict",
                "metrics": None,
            })
            continue
        metrics = metric_shapes[0] if metric_shapes else None
        adapted = optional_gsc_adapter(
            connection_state="connected",
            as_of=as_of,
            observed_at=observed_at,
            metrics=metrics,
        )
        pages.append({
            "url": url,
            "state": adapted["state"],
            "reason": {
                "connected": "authorized_current_gsc_page_evidence",
                "stale": "gsc_evidence_stale",
            }.get(adapted["state"], "gsc_evidence_unavailable"),
            "metrics": adapted.get("metrics"),
        })

    states = {row["state"] for row in pages}
    if "connected" in states:
        state, reason = "connected", "authorized_current_gsc_evidence"
    elif "stale" in states:
        state, reason = "stale", "gsc_evidence_stale"
    else:
        state, reason = "unavailable", "gsc_evidence_unavailable"

    return {
        **gated,
        "state": state,
        "reason": reason,
        "observed_at": observed_at.isoformat() if observed_at else None,
        "candidate_page_rows": len(raw_rows),
        "selected_page_rows": len(pages),
        "rejected_outside_scan": rejected,
        "duplicate_conflicts": conflicts,
        "pages": pages,
    }
