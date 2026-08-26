"""Optional, fail-open aggregate scanner telemetry for Supabase.

The crawler never reads from Supabase. A durable scan may schedule one bounded
PostgREST upsert after crawl evidence is finalized; authority and customer
results do not depend on whether that write succeeds.
"""

from __future__ import annotations

import asyncio
import os
import re
from collections import Counter
from typing import Any
from urllib.parse import urlparse

import httpx

from .observability import emit

TELEMETRY_VERSION = "scanner_supabase_telemetry_v1"
TELEMETRY_TABLE = "scanner_telemetry_v1"
DEFAULT_TIMEOUT_SECONDS = 1.5
MAX_TIMEOUT_SECONDS = 3.0

_PENDING_TELEMETRY_TASKS: set[asyncio.Task[bool]] = set()
_SAFE_LABEL = re.compile(r"[^a-z0-9_.:-]+")


def telemetry_enabled() -> bool:
    return os.getenv("SCANNER_SUPABASE_TELEMETRY_ENABLED", "").strip().lower() == "true"


def _bounded_int(value: Any, *, maximum: int = 1_000_000_000) -> int:
    try:
        return max(0, min(maximum, int(value or 0)))
    except (TypeError, ValueError, OverflowError):
        return 0


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _optional_health_score(value: Any) -> int | None:
    score = _optional_int(value)
    return score if score is not None and 0 <= score <= 100 else None


def _label(value: Any, *, fallback: str = "unknown") -> str:
    normalized = _SAFE_LABEL.sub("_", str(value or "").strip().lower()).strip("_")[:64]
    return normalized or fallback


def _safe_counter(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    output: Counter[str] = Counter()
    for raw_key, raw_count in value.items():
        count = _bounded_int(raw_count)
        if count:
            output[_label(raw_key)] += count
    return dict(sorted(output.items()))


def _pages(result: dict[str, Any]) -> list[dict[str, Any]]:
    value = result.get("crawled_pages") or result.get("pages") or []
    return [page for page in value if isinstance(page, dict)] if isinstance(value, list) else []


def _findings(result: dict[str, Any]) -> list[dict[str, Any]]:
    value = result.get("findings") or result.get("grouped_findings") or result.get("recommendations") or []
    return [finding for finding in value if isinstance(finding, dict)] if isinstance(value, list) else []


def _response_class(status_code: Any) -> str:
    code = _bounded_int(status_code, maximum=999)
    if code <= 0:
        return "unfetched"
    if 100 <= code < 600:
        return f"{code // 100}xx"
    return "other"


def _sampling_decisions(result: dict[str, Any]) -> dict[str, Any]:
    sampling = result.get("sampling_evidence")
    sampling = sampling if isinstance(sampling, dict) else {}
    never_sampled = sampling.get("families_never_sampled")
    never_sampled = never_sampled if isinstance(never_sampled, list) else []
    return {
        "sampling_version": _label(sampling.get("sampling_version"), fallback="unknown"),
        "sitemap_urls_discovered": _bounded_int(sampling.get("sitemap_urls_discovered")),
        "sitemap_urls_sampled": _bounded_int(sampling.get("sitemap_urls_sampled")),
        "family_totals": _safe_counter(sampling.get("family_totals")),
        "family_sampled": _safe_counter(sampling.get("family_sampled")),
        "families_never_sampled": sorted({_label(value) for value in never_sampled})[:64],
        "trust_pages_in_sitemap": _bounded_int(sampling.get("trust_pages_in_sitemap")),
        "trust_pages_sampled": _bounded_int(sampling.get("trust_pages_sampled")),
    }


def build_scan_telemetry(scan_id: str, result: dict[str, Any]) -> dict[str, Any]:
    """Reduce a scan result to a URL-free, content-free aggregate payload."""
    source = result if isinstance(result, dict) else {}
    pages = _pages(source)
    findings = _findings(source)
    page_types: Counter[str] = Counter()
    response_classes: Counter[str] = Counter()
    priorities: Counter[str] = Counter()
    categories: Counter[str] = Counter()
    rules: Counter[str] = Counter()

    for page in pages:
        page_types[_label(page.get("page_template_family") or page.get("estimated_page_intent"))] += 1
        response_classes[_response_class(page.get("status_code"))] += 1
    for finding in findings:
        priorities[_label(finding.get("priority"))] += 1
        categories[_label(finding.get("category"))] += 1
        rules[_label(finding.get("rule"))] += 1

    crawl_timing = source.get("crawl_timing")
    crawl_timing = crawl_timing if isinstance(crawl_timing, dict) else {}
    success = source.get("success") is True
    deadline_reached = source.get("scan_deadline_reached") is True

    return {
        "scan_id": str(scan_id or "").strip()[:200],
        "telemetry_version": TELEMETRY_VERSION,
        "outcome": "failed" if not success else "bounded_partial" if deadline_reached else "complete",
        "scanner_version": str(source.get("scanner_version") or source.get("version") or "")[:128],
        "scanner_build_revision": str(source.get("scanner_build_revision") or "")[:128],
        "scan_mode": _label(source.get("scan_mode"), fallback="unknown"),
        "scanner_elapsed_ms": _bounded_int(source.get("scanner_elapsed_ms")),
        "scan_deadline_reached": deadline_reached,
        "pages_crawled": _bounded_int(source.get("pages_crawled") or len(pages)),
        "pages_found": _bounded_int(source.get("pages_found")),
        "health_score": _optional_health_score(source.get("health_score")),
        "page_type_counts": dict(sorted(page_types.items())),
        "response_class_counts": dict(sorted(response_classes.items())),
        "failure_reason_counts": _safe_counter(crawl_timing.get("failure_reason_buckets")),
        "issue_counts": {
            "total": len(findings),
            "by_priority": dict(sorted(priorities.items())),
            "by_category": dict(sorted(categories.items())),
            "by_rule": dict(sorted(rules.items())),
        },
        "sampling_decisions": _sampling_decisions(source),
    }


def _settings(scan_id: str) -> tuple[str, str, float] | None:
    if not telemetry_enabled():
        return None
    url = os.getenv("SCANNER_TELEMETRY_SUPABASE_URL", "").strip().rstrip("/")
    secret = os.getenv("SCANNER_TELEMETRY_SUPABASE_SECRET_KEY", "").strip()
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or not secret:
        emit(
            "scanner_supabase_telemetry_warning",
            severity="WARNING",
            scan_id=scan_id,
            telemetry_version=TELEMETRY_VERSION,
            reason="misconfigured",
        )
        return None
    try:
        requested_timeout = float(os.getenv("SCANNER_SUPABASE_TELEMETRY_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
    except (TypeError, ValueError):
        requested_timeout = DEFAULT_TIMEOUT_SECONDS
    timeout = max(0.1, min(MAX_TIMEOUT_SECONDS, requested_timeout))
    return url, secret, timeout


async def _persist_payload(payload: dict[str, Any]) -> bool:
    scan_id = str(payload.get("scan_id") or "")
    settings = _settings(scan_id)
    if settings is None:
        return False
    url, secret, timeout_seconds = settings
    headers = {
        "apikey": secret,
        "Authorization": f"Bearer {secret}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            response = await client.post(
                f"{url}/rest/v1/{TELEMETRY_TABLE}",
                params={"on_conflict": "scan_id"},
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
    except httpx.TimeoutException:
        reason = "timeout"
    except httpx.TransportError:
        reason = "transport_error"
    except httpx.HTTPStatusError:
        reason = "http_error"
    except Exception:  # noqa: BLE001 - telemetry must never affect the scanner
        reason = "unexpected_error"
    else:
        emit(
            "scanner_supabase_telemetry_persisted",
            scan_id=scan_id,
            telemetry_version=TELEMETRY_VERSION,
        )
        return True

    emit(
        "scanner_supabase_telemetry_warning",
        severity="WARNING",
        scan_id=scan_id,
        telemetry_version=TELEMETRY_VERSION,
        reason=reason,
    )
    return False


async def persist_scan_telemetry(scan_id: str, result: dict[str, Any]) -> bool:
    """Persist one aggregate payload, returning False for every fail-open path."""
    clean_scan_id = str(scan_id or "").strip()
    if not telemetry_enabled():
        return False
    if not clean_scan_id or len(clean_scan_id) > 200:
        emit(
            "scanner_supabase_telemetry_warning",
            severity="WARNING",
            scan_id=clean_scan_id[:200],
            telemetry_version=TELEMETRY_VERSION,
            reason="invalid_scan_id",
        )
        return False
    try:
        payload = build_scan_telemetry(clean_scan_id, result)
    except Exception:  # noqa: BLE001 - aggregate reduction is fail-open too
        emit(
            "scanner_supabase_telemetry_warning",
            severity="WARNING",
            scan_id=clean_scan_id,
            telemetry_version=TELEMETRY_VERSION,
            reason="payload_error",
        )
        return False
    return await _persist_payload(payload)


def _consume_task(task: asyncio.Task[bool]) -> None:
    _PENDING_TELEMETRY_TASKS.discard(task)
    try:
        task.result()
    except BaseException:
        # _persist_payload is fail-open. This final guard also consumes task
        # cancellation or an unforeseen task-level failure without surfacing it.
        pass


def schedule_scan_telemetry(scan_id: str, result: dict[str, Any]) -> bool:
    """Schedule one detached aggregate upsert without retaining the scan body."""
    clean_scan_id = str(scan_id or "").strip()
    if not telemetry_enabled():
        return False
    if not clean_scan_id or len(clean_scan_id) > 200:
        return False
    try:
        payload = build_scan_telemetry(clean_scan_id, result)
        task = asyncio.create_task(_persist_payload(payload))
    except Exception:  # noqa: BLE001 - scheduling cannot affect the caller
        emit(
            "scanner_supabase_telemetry_warning",
            severity="WARNING",
            scan_id=clean_scan_id,
            telemetry_version=TELEMETRY_VERSION,
            reason="schedule_error",
        )
        return False
    _PENDING_TELEMETRY_TASKS.add(task)
    task.add_done_callback(_consume_task)
    return True


def pending_telemetry_task_count() -> int:
    return len(_PENDING_TELEMETRY_TASKS)
