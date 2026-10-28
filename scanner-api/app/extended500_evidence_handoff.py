"""Private Extended 500 signed *evidence handoff*, not a customer authority result.

This module has no endpoint, dispatch, database writes, billing, or entitlement.
The explicit unreviewed state prevents a synthetic 500-page raw collection from
being mistaken for completed SEO analysis. Consumers must independently verify
the HMAC and frozen ScanRun identity before any future persistence step.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse
from typing import Any

from .authority_seal import create_authority_seal, stable_serialize
from .page_output_privacy import project_pages_for_external_boundary

EXTENDED500_HANDOFF_VERSION = "extended500_evidence_handoff_v1_unreviewed"
EXTENDED500_MODE = "extended_500"
EXTENDED500_MAX_PAGES = 500
EXTENDED500_MAX_HANDOFF_BYTES = 8 * 1024 * 1024
_SOURCE_SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
_FINGERPRINT_RE = re.compile(r"[0-9a-f]{16}\Z")


def _token(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 256:
        raise ValueError(f"Missing or invalid {label}")
    return value.strip()


def _domain(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    clean = value.strip().lower()
    if not clean:
        return ""
    if "://" in clean:
        try:
            parsed = urlparse(clean)
            return (parsed.hostname or "").removeprefix("www.").rstrip(".")
        except ValueError:
            return ""
    return clean.removeprefix("www.").rstrip(".")


def _count(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"Invalid {label}")
    return value


def build_extended500_evidence_handoff(
    scan_run: dict[str, Any], result: dict[str, Any], signing_key: str,
) -> dict[str, Any]:
    """Sign one private, non-authoritative 500-page collection bound to a ScanRun.

    This intentionally cannot call Standard 150's completion builder and
    deliberately exports no 'complete' status or review authority.
    """
    if not isinstance(scan_run, dict) or not isinstance(result, dict):
        raise ValueError("Expected ScanRun and result dictionaries")
    if not isinstance(signing_key, str) or not signing_key:
        raise ValueError("Signing key unavailable")
    if scan_run.get("scan_mode") != EXTENDED500_MODE:
        raise ValueError("Expected frozen Extended 500 ScanRun mode")
    if result.get("scan_mode") != EXTENDED500_MODE or result.get("canonical_mode") != EXTENDED500_MODE:
        raise ValueError("Expected explicit Extended 500 result mode")
    if result.get("release_gate_eligible") is True:
        raise ValueError("Unreviewed evidence cannot claim release authority")

    identity = {
        "canonical_mode": EXTENDED500_MODE,
        "owner_user_id": _token(scan_run.get("owner_user_id"), "owner_user_id"),
        "scan_id": _token(scan_run.get("id"), "scan_id"),
        "project_id": _token(scan_run.get("project_id"), "project_id"),
        "request_id": _token(scan_run.get("request_id"), "request_id"),
        "idempotency_key": _token(scan_run.get("idempotency_key"), "idempotency_key"),
        "normalized_domain": _domain(scan_run.get("normalized_domain") or scan_run.get("website_url")),
        "attempt_count": str(_count(scan_run.get("attempt_count"), "attempt_count")),
    }
    if not identity["normalized_domain"] or identity["attempt_count"] == "0":
        raise ValueError("Incomplete ScanRun domain or attempt identity")
    for key in ("scan_id", "request_id", "idempotency_key"):
        if result.get(key) != identity[key]:
            raise ValueError(f"Extended 500 {key} identity mismatch")
    if _domain(result.get("normalized_domain")) != identity["normalized_domain"]:
        raise ValueError("Extended 500 domain identity mismatch")

    pages = result.get("pages")
    mirror = result.get("crawled_pages")
    if not isinstance(pages, list) or not isinstance(mirror, list) or pages != mirror:
        raise ValueError("Extended 500 page aliases must match exactly")
    count = _count(result.get("pages_crawled"), "pages_crawled")
    if not 1 <= count <= EXTENDED500_MAX_PAGES or count != len(pages):
        raise ValueError("Extended 500 assessed page count mismatch")
    if not all(isinstance(page, dict) for page in pages):
        raise ValueError("Expected page dictionaries")
    destinations = [page.get("final_url") or page.get("url") for page in pages]
    if not all(isinstance(url, str) and url.startswith(("http://", "https://")) for url in destinations):
        raise ValueError("Missing retained destination URL")
    if len(set(destinations)) != len(destinations):
        raise ValueError("Duplicate retained destination identity")

    coverage = result.get("scan_coverage")
    if not isinstance(coverage, dict):
        raise ValueError("Missing scan coverage")
    attempts = _count(coverage.get("urls_attempted"), "urls_attempted")
    usable = _count(coverage.get("usable_html_pages"), "usable_html_pages")
    retained = _count(coverage.get("unique_retained_destinations"), "unique_retained_destinations")
    if retained != count or attempts < count or usable > attempts:
        raise ValueError("Extended 500 coverage accounting mismatch")
    discovered = _count(result.get("pages_found"), "pages_found")
    if discovered < count:
        raise ValueError("Discovered inventory smaller than retained pages")

    source_sha = _token(result.get("scanner_source_sha"), "scanner_source_sha").lower()
    fingerprint = _token(result.get("beta_revision_fingerprint"), "beta_revision_fingerprint").lower()
    if not _SOURCE_SHA_RE.fullmatch(source_sha) or not _FINGERPRINT_RE.fullmatch(fingerprint):
        raise ValueError("Extended 500 source identity invalid")

    scan = {
        "canonical_mode": EXTENDED500_MODE,
        "scan_id": identity["scan_id"],
        "request_id": identity["request_id"],
        "idempotency_key": identity["idempotency_key"],
        "normalized_domain": identity["normalized_domain"],
        "pages_found": discovered,
        "pages_crawled": count,
        "scan_coverage": {
            "urls_attempted": attempts,
            "usable_html_pages": usable,
            "unique_retained_destinations": retained,
        },
        "scanner_source_sha": source_sha,
        "beta_revision_fingerprint": fingerprint,
        "pages": project_pages_for_external_boundary(pages),
    }
    # No completed review or release eligibility can be inferred from fetching.
    review = {
        "review_status": "not_reviewed",
        "pages_reviewed": 0,
        "release_gate_eligible": False,
    }
    payload = {
        "version": EXTENDED500_HANDOFF_VERSION,
        "identity": identity,
        "scan": scan,
        "review": review,
    }
    if len(stable_serialize(payload).encode("utf-8")) > EXTENDED500_MAX_HANDOFF_BYTES:
        raise ValueError("Extended 500 evidence handoff byte budget exceeded")
    return {**payload, "proof": create_authority_seal(payload, signing_key)}
