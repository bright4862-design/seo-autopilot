from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

URL_EVIDENCE_VERSION = "verified_final_url_v1"


def _page_records(result: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("crawled_pages", "pages", "scanned_pages", "crawl_pages"):
        value = result.get(key)
        if isinstance(value, list):
            pages = [page for page in value if isinstance(page, dict)]
            if pages:
                return pages
    return []


def _status_code(page: dict[str, Any]) -> int:
    for key in ("status_code", "http_status", "response_status"):
        try:
            value = int(page.get(key) or 0)
        except (TypeError, ValueError):
            continue
        if value:
            return value
    return 0


def _http_url(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    return parsed._replace(fragment="").geturl()


def apply_verified_url_contract(result: dict[str, Any]) -> dict[str, Any]:
    """Annotate crawl records so downstream AI can cite only live final URLs.

    Error responses remain in the crawl evidence for broken-link diagnostics, but
    they never receive ``verified_final_url`` and therefore cannot be presented as
    a working page to edit.
    """
    if not isinstance(result, dict):
        return result

    verified_live_urls = 0
    confirmed_error_urls = 0
    redirecting_urls = 0
    pages = _page_records(result)
    for page in pages:
        status_code = _status_code(page)
        requested_url = _http_url(
            page.get("url") or page.get("requested_url") or ""
        )
        final_url = _http_url(page.get("final_url") or requested_url)
        fetch_error = str(page.get("fetch_error") or "").strip()

        if status_code == 200 and final_url and not fetch_error:
            page["verified_final_url"] = final_url
            page["url_verification"] = "live_200"
            verified_live_urls += 1
            if requested_url and requested_url != final_url:
                redirecting_urls += 1
            continue

        page.pop("verified_final_url", None)
        if status_code >= 400:
            page["url_verification"] = "confirmed_http_error"
            confirmed_error_urls += 1
        else:
            page["url_verification"] = "unverified"

    result["url_evidence_version"] = URL_EVIDENCE_VERSION
    result["verified_live_url_count"] = verified_live_urls
    result["confirmed_error_url_count"] = confirmed_error_urls

    technical = result.get("technical_audit_summary")
    if not isinstance(technical, dict):
        technical = {}
        result["technical_audit_summary"] = technical
    technical["url_evidence_version"] = URL_EVIDENCE_VERSION
    technical["verified_live_url_count"] = verified_live_urls
    technical["confirmed_error_url_count"] = confirmed_error_urls
    technical["redirecting_url_count"] = redirecting_urls
    return result
