"""Isolated, bounded Extended 500 *collection* experiment — NEVER reviewed authority.

No Flask route, Cloud Tasks worker, paid-access decisions or Base44 writer.
This candidate runs the existing hardened crawler only in a *spawned child
process*, so its distinct 500-page budget cannot leak into Standard 150
workers. The parent checks exact mode, counts, privacy and a wire-size cap.
Enabling it still does not authorize a queue or customer result.
"""
from __future__ import annotations

import asyncio
import json
import multiprocessing as mp
import re
from typing import Any
from urllib.parse import urlsplit

EXTENDED500_MODE = "extended_500"
COLLECTOR_VERSION = "extended500_private_collector_v1_unreviewed"
MAX_RETAINED_PAGES = 500
MAX_RESULT_BYTES = 8 * 1024 * 1024
MIN_TIMEOUT_SECONDS = 20
MAX_TIMEOUT_SECONDS = 120
MAX_CONCURRENCY = 8
_TOKEN = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_HOST = re.compile(r"[a-z0-9.-]{1,253}\Z")


class Extended500CollectionRefused(ValueError):
    """Non-retryable collection-contract refusal. Contains no secrets."""


def _token(value: Any) -> bool:
    return isinstance(value, str) and bool(_TOKEN.fullmatch(value))


def _site_root(value: Any) -> str:
    if not isinstance(value, str) or len(value) > 2048:
        return ""
    try:
        url = urlsplit(value)
        host = (url.hostname or "").lower().rstrip(".")
        if (
            url.scheme not in {"https", "http"}
            or not _HOST.fullmatch(host) or "." not in host
            or url.username is not None or url.password is not None
            or url.port is not None or url.query or url.fragment
            or url.path not in ("", "/") or host.startswith(".")
            or host.endswith((".local", ".localhost", ".test", ".invalid", ".internal", ".example"))
            or host in {"localhost", "0.0.0.0"} or ".." in host
            or all(c in ".0123456789" for c in host)
        ):
            return ""
        return f"{url.scheme}://{host}/"
    except ValueError:
        return ""


def validate_extended500_collection_request(scan: Any, *, timeout_seconds: int = 120,
                                             concurrency: int = 4) -> str:
    """Use only a service-owned frozen ScanRun; this is not pickup authorization."""
    if not isinstance(scan, dict):
        raise Extended500CollectionRefused("frozen_scanrun_required")
    if scan.get("scan_mode") != EXTENDED500_MODE or scan.get("status") != "queued":
        raise Extended500CollectionRefused("frozen_extended500_queue_required")
    if any(not _token(scan.get(k)) for k in (
        "id", "owner_user_id", "project_id", "request_id", "idempotency_key",
    )):
        raise Extended500CollectionRefused("scanrun_identity_invalid")
    if (type(scan.get("attempt_count")) is not int or scan["attempt_count"] < 1
        or scan.get("respect_robots_txt") is not True
        or scan.get("owner_attested_robots_override") is not False
        or scan.get("path_prefix") not in (None, "")):
        raise Extended500CollectionRefused("scanrun_scope_invalid")
    url = _site_root(scan.get("website_url"))
    if not url or url != scan.get("website_url"):
        raise Extended500CollectionRefused("scanrun_root_url_invalid")
    if urlsplit(url).hostname.removeprefix("www.") != scan.get("normalized_domain"):
        raise Extended500CollectionRefused("scanrun_domain_invalid")
    if (type(timeout_seconds) is not int or not MIN_TIMEOUT_SECONDS <= timeout_seconds <= MAX_TIMEOUT_SECONDS
        or type(concurrency) is not int or not 1 <= concurrency <= MAX_CONCURRENCY):
        raise Extended500CollectionRefused("collector_budget_invalid")
    return url


def validate_extended500_collection_result(scan: dict, raw_result: Any) -> dict:
    """Keep one 500-page *unreviewed* collection; reject untruthful counts."""
    from .page_output_privacy import project_scan_result_for_external_boundary

    if not isinstance(raw_result, dict) or raw_result.get("success") is not True:
        raise Extended500CollectionRefused("collection_failed_or_unverified")
    if raw_result.get("scan_mode") != EXTENDED500_MODE:
        raise Extended500CollectionRefused("foreign_collection_mode")
    if raw_result.get("release_gate_eligible") is True or raw_result.get("review_status") in {
        "reviewed", "complete", "passed",
    }:
        raise Extended500CollectionRefused("collector_must_not_assert_review_authority")
    pages = raw_result.get("pages")
    mirrored = raw_result.get("crawled_pages")
    if not isinstance(pages, list) or not isinstance(mirrored, list) or pages != mirrored:
        raise Extended500CollectionRefused("collection_page_mirror_mismatch")
    number = len(pages)
    if number < 1 or number > MAX_RETAINED_PAGES:
        raise Extended500CollectionRefused("collection_page_budget_exceeded_or_empty")
    if type(raw_result.get("pages_crawled")) is not int or raw_result["pages_crawled"] != number:
        raise Extended500CollectionRefused("collection_assessed_count_invalid")
    found = raw_result.get("pages_found")
    if type(found) is not int or found < number:
        raise Extended500CollectionRefused("collection_discovered_count_invalid")
    coverage = raw_result.get("scan_coverage")
    if not isinstance(coverage, dict):
        raise Extended500CollectionRefused("collection_coverage_missing")
    for field in ("urls_attempted", "usable_html_pages", "unique_retained_destinations"):
        if type(coverage.get(field)) is not int or coverage[field] < 0:
            raise Extended500CollectionRefused("collection_coverage_invalid")
    if (coverage["urls_attempted"] < number
        or coverage["usable_html_pages"] > number
        or coverage["unique_retained_destinations"] != number):
        raise Extended500CollectionRefused("collection_denominator_invalid")
    unique = set()
    for page in pages:
        if not isinstance(page, dict):
            raise Extended500CollectionRefused("collection_page_invalid")
        url = page.get("final_url") or page.get("url")
        if not isinstance(url, str) or not url:
            raise Extended500CollectionRefused("collection_page_identity_missing")
        if url in unique:
            raise Extended500CollectionRefused("collection_duplicate_destination")
        unique.add(url)

    projected = project_scan_result_for_external_boundary(raw_result)
    projected["scan_mode"] = EXTENDED500_MODE
    projected["canonical_mode"] = EXTENDED500_MODE
    projected["release_gate_eligible"] = False
    projected["review_status"] = "not_reviewed"
    projected["pages_reviewed"] = 0
    projected["extended500_collector_version"] = COLLECTOR_VERSION
    for field in ("scan_id", "request_id", "idempotency_key"):
        projected[field] = scan["id" if field == "scan_id" else field]
    projected["normalized_domain"] = scan["normalized_domain"]

    # Count parity must survive the privacy boundary.
    if len(projected.get("pages", [])) != number or projected.get("pages") != projected.get("crawled_pages"):
        raise Extended500CollectionRefused("collection_projection_count_mismatch")
    return projected


def _collector_child(conn, scan: dict, timeout_seconds: int, concurrency: int) -> None:
    """Spawn-only process target. No live Standard 150 request can share budget."""
    try:
        from . import scanner
        # The mode is unique and exists ONLY in this child's process memory.
        if EXTENDED500_MODE in scanner.SCAN_BUDGETS:
            raise Extended500CollectionRefused("collector_budget_collision")
        scanner.SCAN_BUDGETS[EXTENDED500_MODE] = {
            "max_pages": MAX_RETAINED_PAGES, "timeout": timeout_seconds,
            "fetch_timeout": 10, "max_sitemap_fetches": 60,
        }
        result = asyncio.run(scanner.run_scan(
            scan["website_url"], scan_mode=EXTENDED500_MODE, path_prefix=None,
            concurrency=concurrency, timeout_seconds=timeout_seconds, job_mode=True,
        ))
        output = validate_extended500_collection_result(scan, result)
        encoded = json.dumps({"ok": True, "result": output}, ensure_ascii=False,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
        if len(encoded) > MAX_RESULT_BYTES:
            raise Extended500CollectionRefused("collection_wire_payload_too_large")
    except Exception as exc:
        error = str(exc) if isinstance(exc, Extended500CollectionRefused) else "collector_child_failure"
        encoded = json.dumps({"ok": False, "error": error}).encode("utf-8")
    try:
        conn.send_bytes(encoded)
    except (BrokenPipeError, OSError):
        pass
    finally:
        conn.close()


def run_isolated_extended500_collection(
    scan: dict, *, enabled: bool = False, timeout_seconds: int = 120,
    concurrency: int = 4,
) -> dict:
    """Run private unreviewed collector in a fresh spawn; never serve as a route.

    The caller MUST additionally perform Agent B's fresh paid entitlement +
    active owner-slot authorization. 'enabled' is a development-only explicit
    permission, not the production flag or an entitlement.
    """
    if enabled is not True:
        raise Extended500CollectionRefused("extended500_collector_disabled")
    validate_extended500_collection_request(
        scan, timeout_seconds=timeout_seconds, concurrency=concurrency,
    )
    ctx = mp.get_context("spawn")
    parent, child = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=_collector_child, args=(child, dict(scan), timeout_seconds, concurrency),
                       daemon=True, name="fixlist-extended500-unreviewed")
    try:
        proc.start()
        child.close()
        if not parent.poll(timeout_seconds + 10):
            raise Extended500CollectionRefused("collector_process_deadline")
        try:
            message = parent.recv_bytes(MAX_RESULT_BYTES + 1024)
        except (EOFError, OSError, ValueError):
            raise Extended500CollectionRefused("collector_process_response_invalid") from None
        try:
            parsed = json.loads(message)
        except (ValueError, UnicodeError):
            raise Extended500CollectionRefused("collector_process_json_invalid") from None
        if not isinstance(parsed, dict) or parsed.get("ok") is not True:
            raise Extended500CollectionRefused(
                parsed.get("error", "collector_process_failed") if isinstance(parsed, dict)
                else "collector_process_failed"
            )
        output = parsed.get("result")
        if not isinstance(output, dict):
            raise Extended500CollectionRefused("collector_response_missing")
        # Re-validate strict count, privacy, ID binding AFTER process transport.
        return validate_extended500_collection_result(scan, output)
    finally:
        parent.close()
        child.close()
        if proc.is_alive():
            proc.terminate()
        if proc.pid is not None:
            proc.join(timeout=2)
            if proc.is_alive():
                proc.kill()
                proc.join(timeout=2)
