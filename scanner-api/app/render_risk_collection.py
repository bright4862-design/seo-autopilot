from __future__ import annotations

import asyncio
from copy import deepcopy
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

import httpx

from .render_risk_study import (
    VALID_EVIDENCE_STATES,
    VALID_MANUAL_VERDICTS,
    VALID_STRATA,
    normalize_record,
)


Sleep = Callable[[float], Awaitable[None]]


def normalize_manifest_record(record: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise TypeError("manifest record must be an object")

    site = str(record.get("site") or record.get("site_id") or "").strip()
    if not site:
        raise ValueError("site is required")

    url = str(record.get("url") or record.get("website_url") or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("url must be an absolute http(s) URL")

    stratum = str(record.get("stratum") or "").strip().lower()
    if stratum not in VALID_STRATA:
        raise ValueError(f"stratum must be one of {sorted(VALID_STRATA)}")

    scan_mode = str(record.get("scan_mode") or "advanced").strip().lower()
    if scan_mode not in {"basic", "quick", "deep", "advanced"}:
        raise ValueError("scan_mode must be basic, quick, deep, or advanced")

    manual_verdict = str(record.get("manual_js_disabled_verdict") or "not_reviewed").strip().lower()
    if manual_verdict not in VALID_MANUAL_VERDICTS:
        raise ValueError(
            f"manual_js_disabled_verdict must be one of {sorted(VALID_MANUAL_VERDICTS)}"
        )

    normalized = {
        **record,
        "site": site,
        "url": url,
        "stratum": stratum,
        "scan_mode": scan_mode,
        "manual_js_disabled_verdict": manual_verdict,
        "notes": str(record.get("notes") or "").strip(),
    }
    path_prefix = str(record.get("path_prefix") or "").strip()
    if path_prefix:
        normalized["path_prefix"] = path_prefix
    return normalized


def build_study_record(manifest_record: dict[str, Any], scan_result: dict[str, Any]) -> dict[str, Any]:
    manifest = normalize_manifest_record(manifest_record)
    if not isinstance(scan_result, dict):
        raise TypeError("scan result must be an object")
    if scan_result.get("success") is False:
        raise ValueError(str(scan_result.get("error") or "scanner returned success=false"))

    evidence = scan_result.get("render_evidence")
    if not isinstance(evidence, dict):
        raise ValueError("scan result did not include render_evidence")
    evidence_state = str(evidence.get("evidence_state") or "").strip()
    if evidence_state not in VALID_EVIDENCE_STATES:
        raise ValueError(
            f"render_evidence.evidence_state must be one of {sorted(VALID_EVIDENCE_STATES)}"
        )

    record = {
        "site": manifest["site"],
        "url": manifest["url"],
        "stratum": manifest["stratum"],
        # Keep the scanner-produced evidence intact. The study summarizer validates
        # it but must never recalculate or restamp the detector state.
        "render_evidence": deepcopy(evidence),
        "manual_js_disabled_verdict": manifest["manual_js_disabled_verdict"],
        "notes": manifest["notes"],
        "scan_status": "complete",
        "scanner_version": str(scan_result.get("scanner_version") or scan_result.get("version") or ""),
        "pages_crawled": _nonnegative_int(scan_result.get("pages_crawled")),
        "pages_found": _nonnegative_int(scan_result.get("pages_found")),
    }
    normalize_record(record)
    return record


def build_failure_record(
    manifest_record: dict[str, Any],
    error: str,
    attempts: int,
    *,
    status_code: int | None = None,
) -> dict[str, Any]:
    manifest = normalize_manifest_record(manifest_record)
    record = {
        "site": manifest["site"],
        "url": manifest["url"],
        "stratum": manifest["stratum"],
        "scan_status": "failed",
        "attempts": max(1, int(attempts or 1)),
        "error": str(error or "scan failed").strip()[:500],
    }
    if status_code is not None:
        record["status_code"] = int(status_code)
    return record


async def fetch_study_record(
    client: httpx.AsyncClient,
    scanner_url: str,
    scanner_key: str,
    manifest_record: dict[str, Any],
    *,
    timeout_seconds: float = 120.0,
    attempts: int = 2,
    retry_delay_seconds: float = 1.0,
    sleep: Sleep = asyncio.sleep,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    manifest = normalize_manifest_record(manifest_record)
    base_url = str(scanner_url or "").strip().rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("scanner_url must be an absolute http(s) URL")
    if not str(scanner_key or "").strip():
        raise ValueError("scanner_key is required")

    maximum_attempts = max(1, min(int(attempts or 1), 5))
    payload = {
        "website_url": manifest["url"],
        "path_prefix": manifest.get("path_prefix") or None,
        "scan_mode": manifest["scan_mode"],
    }
    headers = {
        "content-type": "application/json",
        "x-scanner-key": str(scanner_key).strip(),
    }

    last_error = "scan failed"
    last_status: int | None = None
    for attempt in range(1, maximum_attempts + 1):
        try:
            response = await client.post(
                f"{base_url}/scan",
                headers=headers,
                json=payload,
                timeout=max(1.0, float(timeout_seconds)),
            )
        except httpx.RequestError as exc:
            last_error = f"request failed: {str(exc)[:300]}"
            if attempt < maximum_attempts:
                await sleep(max(0.0, retry_delay_seconds) * attempt)
                continue
            return None, build_failure_record(manifest, last_error, attempt)

        last_status = response.status_code
        result = _response_json(response)
        if not response.is_success:
            last_error = _response_error(response, result)
            retryable = response.status_code == 429 or response.status_code >= 500
            if retryable and attempt < maximum_attempts:
                await sleep(max(0.0, retry_delay_seconds) * attempt)
                continue
            return None, build_failure_record(
                manifest,
                last_error,
                attempt,
                status_code=response.status_code,
            )

        if not isinstance(result, dict):
            last_error = "scanner returned a non-JSON response"
            if attempt < maximum_attempts:
                await sleep(max(0.0, retry_delay_seconds) * attempt)
                continue
            return None, build_failure_record(manifest, last_error, attempt, status_code=last_status)

        try:
            return build_study_record(manifest, result), None
        except (TypeError, ValueError) as exc:
            return None, build_failure_record(
                manifest,
                f"invalid scan result: {exc}",
                attempt,
                status_code=last_status,
            )

    return None, build_failure_record(
        manifest,
        last_error,
        maximum_attempts,
        status_code=last_status,
    )


def _response_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


def _response_error(response: httpx.Response, result: Any) -> str:
    if isinstance(result, dict):
        detail = result.get("detail") or result.get("error") or result.get("message")
        if detail:
            return f"HTTP {response.status_code}: {str(detail)[:350]}"
    text = str(response.text or "").strip().replace("\n", " ")
    return f"HTTP {response.status_code}: {(text or 'request failed')[:350]}"


def _nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0
