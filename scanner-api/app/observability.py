"""Production observability for the scanner API (roadmap Phase 4).

Emits one structured JSON log line per scan/review lifecycle event on stdout.
Cloud Run ingests stdout JSON as structured logs: the ``severity`` field maps
to the log level and every other field becomes ``jsonPayload.*``, which is what
the log-based metrics and alerts in ``docs/production-monitoring.md`` filter on.

Also owns the customer-safe error envelope: internal exception details are
logged with a generated ``error_id`` while the HTTP response carries only a
safe message plus the same ``error_id``, so support can correlate a customer
report with the full log line without ever exposing internals.
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from typing import Any
from urllib.parse import urlparse

OBSERVABILITY_VERSION = "scan_observability_v1"

_SEVERITIES = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def emit(event: str, *, severity: str = "INFO", **fields: Any) -> dict[str, Any]:
    """Write one structured log line to stdout and return the record."""
    record: dict[str, Any] = {
        "severity": severity if severity in _SEVERITIES else "INFO",
        "event": event,
        "observability_version": OBSERVABILITY_VERSION,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
    }
    for key, value in fields.items():
        if value is not None:
            record[key] = value
    sys.stdout.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    sys.stdout.flush()
    return record


def website_host(website_url: str) -> str:
    """Log the host only — full URLs can carry query strings and paths that
    identify customer content more than monitoring needs."""
    try:
        return (urlparse(str(website_url or "")).hostname or "").lower()
    except ValueError:
        return ""


def _pages(result: dict[str, Any]) -> list[dict]:
    pages = result.get("crawled_pages") or result.get("pages") or []
    return [page for page in pages if isinstance(page, dict)]


def scan_metrics(result: dict[str, Any]) -> dict[str, Any]:
    """Extract the monitoring counters from a scan result."""
    pages = _pages(result)
    status_codes = [int(page.get("status_code") or 0) for page in pages]
    return {
        "success": result.get("success") is True,
        "pages_crawled": int(result.get("pages_crawled") or len(pages)),
        "pages_found": int(result.get("pages_found") or 0),
        "rate_limited_pages": sum(1 for code in status_codes if code == 429),
        "server_error_pages": sum(1 for code in status_codes if code >= 500),
        "failed_pages": int(result.get("verified_failed_page_count") or 0),
        "scanner_version": str(result.get("scanner_version") or result.get("version") or ""),
    }


def review_metrics(result: dict[str, Any]) -> dict[str, Any]:
    """Extract the monitoring counters from a review result."""
    report = result.get("website_health_report") if isinstance(result.get("website_health_report"), dict) else {}
    fixes = result.get("cleaned_fixes") or result.get("fixes") or result.get("findings") or []
    return {
        "review_version": str(result.get("review_version") or ""),
        "scan_status": str(result.get("scan_status") or report.get("scan_status") or ""),
        "health_score": result.get("health_score", report.get("health_score")),
        "score_is_provisional": bool(result.get("score_is_provisional") or report.get("score_is_provisional")),
        "finding_count": len(fixes) if isinstance(fixes, list) else 0,
    }


# Customer-safe error messages by internal error class. Anything unlisted gets
# the generic message — never the raw exception text, which can leak internals
# (hostnames, stack details, dependency errors).
CUSTOMER_SAFE_MESSAGES = {
    "timeout": "The scan took too long and was stopped. Try again, or use a smaller scan mode.",
    "invalid_input": "We could not start this scan. Check the website address and try again.",
    "upstream_unavailable": "The scanner is temporarily unavailable. Please try again in a few minutes.",
    "internal_error": "Something went wrong on our side while scanning. Please try again; if it keeps failing, contact support with the error ID.",
}


def classify_error(exc: BaseException) -> str:
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    if "timeout" in name or "timed out" in text:
        return "timeout"
    if isinstance(exc, (ValueError, TypeError, KeyError)):
        return "invalid_input"
    if "connect" in name or "connection" in text or "unavailable" in text:
        return "upstream_unavailable"
    return "internal_error"


def customer_safe_error(exc: BaseException, *, endpoint: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Log the full exception with an error_id; return the safe response body."""
    error_id = uuid.uuid4().hex[:12]
    error_code = classify_error(exc)
    emit(
        "request_failed",
        severity="ERROR",
        endpoint=endpoint,
        error_id=error_id,
        error_code=error_code,
        error_type=type(exc).__name__,
        error_detail=str(exc)[:1000],
        **(context or {}),
    )
    return {
        "success": False,
        "error_code": error_code,
        "error": CUSTOMER_SAFE_MESSAGES[error_code],
        "error_id": error_id,
    }


class RequestTimer:
    """Times an endpoint and emits the started/completed/failed event pair."""

    def __init__(self, endpoint: str, **context: Any):
        self.endpoint = endpoint
        self.context = {key: value for key, value in context.items() if value not in (None, "")}
        self.started = time.monotonic()
        emit(f"{endpoint}_started", endpoint=endpoint, **self.context)

    @property
    def duration_ms(self) -> int:
        return int((time.monotonic() - self.started) * 1000)

    def completed(self, **fields: Any) -> None:
        merged = {**self.context, **fields}
        emit(
            f"{self.endpoint}_completed",
            endpoint=self.endpoint,
            duration_ms=self.duration_ms,
            **merged,
        )

    def failed(self, exc: BaseException) -> dict[str, Any]:
        return customer_safe_error(
            exc,
            endpoint=self.endpoint,
            context={"duration_ms": self.duration_ms, **self.context},
        )
