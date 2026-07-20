from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

SITEMAP_TIME_RESERVATION_VERSION = "sitemap_time_reservation_v1_crawl_first"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def allocate_scan_time_budget(
    scan_started_at: float,
    total_timeout_seconds: float,
    fetch_timeout_seconds: float,
    *,
    now: float,
) -> dict[str, float]:
    total = max(1.0, float(total_timeout_seconds or 0))
    fetch_timeout = max(0.1, float(fetch_timeout_seconds or 0.1))
    response_reserve = min(6.0, max(2.0, total * 0.08))
    maximum_crawl_reserve = max(0.5, total - response_reserve - 0.5)
    crawl_reserve = min(maximum_crawl_reserve, max(fetch_timeout * 2.0, total * 0.65))
    overall_deadline = scan_started_at + total
    crawl_deadline = overall_deadline - response_reserve
    sitemap_deadline = overall_deadline - response_reserve - crawl_reserve
    return {
        "overall_deadline": overall_deadline,
        "crawl_deadline": crawl_deadline,
        "sitemap_deadline": sitemap_deadline,
        "sitemap_budget_seconds": max(0.0, sitemap_deadline - now),
        "crawl_reserved_seconds": max(0.0, crawl_deadline - sitemap_deadline),
        "response_reserved_seconds": response_reserve,
    }


def build_crawl_failure_buckets(pages: list[dict[str, Any]]) -> dict[str, int]:
    buckets: dict[str, int] = {}
    for page in pages:
        status = int(page.get("status_code") or page.get("status") or 0)
        error = str(page.get("fetch_error") or "").strip().lower()
        reason = ""
        if error:
            if "robots" in error:
                reason = "robots_blocked"
            elif "timeout" in error or "timed_out" in error:
                reason = "timeout"
            elif "non_public" in error:
                reason = "security_blocked"
            else:
                reason = f"fetch_error:{error}"
        elif status == 429:
            reason = "access_limited_429"
        elif 400 <= status < 500:
            reason = "client_error_4xx"
        elif status >= 500:
            reason = "server_error_5xx"
        elif status == 0:
            reason = "no_response"
        if reason:
            buckets[reason] = buckets.get(reason, 0) + 1
    return dict(sorted(buckets.items()))
