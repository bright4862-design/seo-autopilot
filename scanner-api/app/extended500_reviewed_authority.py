"""Dual-attested Extended 500 reviewed *candidate*, NOT a customer result.

A verified 500-page collection is merely evidence. A completely independent
reviewer must sign exact page identities/finding references with its own HMAC
root. Only then can a separate authority root sign a reviewed-but-UNRELEASED
envelope. No endpoint, Base44 writer, customer completion or billing lives here.
"""
from __future__ import annotations

from collections.abc import Mapping
import hmac
import re
from typing import Any
from urllib.parse import urlsplit

from .authority_seal import create_authority_seal, stable_serialize
from .extended500_evidence_handoff import EXTENDED500_HANDOFF_VERSION

REVIEW_VERSION = "extended500_reviewer_attestation_v1"
AUTHORITY_VERSION = "extended500_reviewed_authority_v1_unreleased"
MAX_PAGES = 500
MAX_FINDINGS = 2000
MAX_PAYLOAD_BYTES = 8 * 1024 * 1024
HEX40 = re.compile(r"[a-f0-9]{40}\Z")
HEX16 = re.compile(r"[a-f0-9]{16}\Z")
_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
SEVERITIES = {"critical", "high", "medium", "low", "info"}
EVIDENCE_STATES = {"observed", "verified"}


class Extended500ReviewedRefused(ValueError):
    pass


def _refuse(reason: str) -> None:
    raise Extended500ReviewedRefused(reason)


def _exact_keys(obj: Any, keys: set[str], label: str) -> None:
    if type(obj) is not dict or set(obj) != keys:
        _refuse(f"{label}_shape_invalid")


def _url_origin(url: Any) -> tuple[str, str]:
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return "", ""
        if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.port is not None:
            return "", ""
        return parsed.scheme, parsed.hostname.lower().rstrip(".")
    except (TypeError, ValueError):
        return "", ""


def _normal_host(host: str) -> str:
    return host.removeprefix("www.").rstrip(".")


def _signed(payload: Mapping[str, Any], proof: Any, key: str) -> bool:
    return isinstance(proof, str) and bool(re.fullmatch("[a-f0-9]{64}", proof)) and hmac.compare_digest(
        create_authority_seal(payload, key), proof,
    )


def _strict_identity(frozen: dict[str, Any], identity: dict[str, Any]) -> None:
    _exact_keys(identity, {
        "canonical_mode", "owner_user_id", "scan_id", "project_id",
        "request_id", "idempotency_key", "normalized_domain", "attempt_count",
    }, "identity")
    if not isinstance(frozen, dict) or frozen.get("scan_mode") != "extended_500":
        _refuse("frozen_extended500_required")
    for key in ("owner_user_id", "project_id", "request_id", "idempotency_key"):
        value = frozen.get(key)
        if not isinstance(value, str) or not _ID.fullmatch(value) or identity[key] != value:
            _refuse("owner_request_identity_mismatch")
    if frozen.get("id") != identity["scan_id"] or not isinstance(frozen.get("id"), str) or not _ID.fullmatch(frozen["id"]):
        _refuse("scan_identity_mismatch")
    attempt = frozen.get("attempt_count")
    if type(attempt) is not int or attempt < 1 or identity["attempt_count"] != str(attempt):
        _refuse("attempt_identity_mismatch")
    _, host = _url_origin(frozen.get("website_url"))
    if not host or _normal_host(host) != identity["normalized_domain"] or identity["canonical_mode"] != "extended_500":
        _refuse("domain_mode_identity_mismatch")


def build_extended500_reviewed_authority(
    frozen: dict[str, Any], handoff: dict[str, Any],
    reviewer_attestation: dict[str, Any], *,
    evidence_signing_key: str, reviewer_signing_key: str,
    authority_signing_key: str, expected_source_sha: str,
    expected_fingerprint: str,
) -> dict[str, Any]:
    """Accept only independently *signed* review of the exact frozen collection.

    The real review engine and terminal/persistence issuer are NOT implemented.
    Callers cannot set release_gate_eligible/complete in this contract.
    """
    keys = [evidence_signing_key, reviewer_signing_key, authority_signing_key]
    if any(not isinstance(x, str) or len(x) < 32 for x in keys) or len(set(keys)) != 3:
        _refuse("distinct_server_signing_roots_required")
    if not (isinstance(expected_source_sha, str) and HEX40.fullmatch(expected_source_sha)
            and isinstance(expected_fingerprint, str) and HEX16.fullmatch(expected_fingerprint)):
        _refuse("expected_release_identity_invalid")
    _exact_keys(handoff, {"version", "identity", "scan", "review", "proof"}, "handoff")
    if handoff["version"] != EXTENDED500_HANDOFF_VERSION:
        _refuse("unreviewed_handoff_version_required")
    _exact_keys(handoff["review"],
                {"review_status", "pages_reviewed", "release_gate_eligible"}, "handoff_review")
    if handoff["review"] != {
        "review_status": "not_reviewed", "pages_reviewed": 0, "release_gate_eligible": False,
    }:
        _refuse("handoff_cannot_claim_reviewed")
    raw_handoff = {key: handoff[key] for key in ("version", "identity", "scan", "review")}
    if not _signed(raw_handoff, handoff["proof"], evidence_signing_key):
        _refuse("unreviewed_handoff_signature_invalid")

    identity, scan = handoff["identity"], handoff["scan"]
    _strict_identity(frozen, identity)
    _exact_keys(scan, {
        "canonical_mode", "scan_id", "request_id", "idempotency_key",
        "normalized_domain", "pages_found", "pages_crawled", "scan_coverage",
        "scanner_source_sha", "beta_revision_fingerprint", "pages",
    }, "scan")
    if scan["canonical_mode"] != "extended_500" or any(
        scan.get(field) != identity[field]
        for field in ("scan_id", "request_id", "idempotency_key", "normalized_domain")
    ):
        _refuse("collection_identity_mismatch")
    n = scan["pages_crawled"]
    if type(n) is not int or not 1 <= n <= MAX_PAGES or type(scan["pages_found"]) is not int or scan["pages_found"] < n:
        _refuse("collection_count_invalid")
    pages = scan["pages"]
    if not isinstance(pages, list) or len(pages) != n:
        _refuse("collection_page_count_invalid")
    _exact_keys(scan["scan_coverage"], {
        "urls_attempted", "usable_html_pages", "unique_retained_destinations",
    }, "coverage")
    cov = scan["scan_coverage"]
    if any(type(cov.get(f)) is not int or cov[f] < 0 for f in cov) or cov["urls_attempted"] < n or cov["usable_html_pages"] > n or cov["unique_retained_destinations"] != n:
        _refuse("coverage_denominator_invalid")
    if scan["scanner_source_sha"] != expected_source_sha or scan["beta_revision_fingerprint"] != expected_fingerprint:
        _refuse("release_source_marker_mismatch")
    scheme, frozen_host = _url_origin(frozen.get("website_url"))
    destinations = []
    for page in pages:
        if not isinstance(page, dict) or not isinstance(page.get("final_url") or page.get("url"), str):
            _refuse("page_identity_invalid")
        url = page.get("final_url") or page.get("url")
        page_scheme, page_host = _url_origin(url)
        if page_scheme != scheme or page_host != frozen_host:
            _refuse("foreign_retained_page")
        if any(k in page for k in ("main_text", "_reachability_links", "future_internal_field")):
            _refuse("private_page_field_in_handoff")
        destinations.append(url)
    if len(set(destinations)) != n:
        _refuse("duplicate_retained_page")

    _exact_keys(reviewer_attestation, {
        "version", "review_status", "identity", "scanner_source_sha",
        "beta_revision_fingerprint", "pages_reviewed", "reviewed_destinations",
        "findings", "proof",
    }, "reviewer")
    if reviewer_attestation["version"] != REVIEW_VERSION or reviewer_attestation["review_status"] != "reviewed":
        _refuse("independent_review_required")
    if (reviewer_attestation["identity"] != identity
            or reviewer_attestation["scanner_source_sha"] != expected_source_sha
            or reviewer_attestation["beta_revision_fingerprint"] != expected_fingerprint
            or type(reviewer_attestation["pages_reviewed"]) is not int
            or reviewer_attestation["pages_reviewed"] != n
            or reviewer_attestation["reviewed_destinations"] != destinations):
        _refuse("review_coverage_identity_mismatch")
    findings = reviewer_attestation["findings"]
    if not isinstance(findings, list) or len(findings) > MAX_FINDINGS:
        _refuse("review_findings_budget_invalid")
    for item in findings:
        _exact_keys(item, {"rule_id", "page_url", "severity", "evidence_state"}, "finding")
        if (not isinstance(item["rule_id"], str) or not _ID.fullmatch(item["rule_id"])
                or item["page_url"] not in destinations
                or item["severity"] not in SEVERITIES
                or item["evidence_state"] not in EVIDENCE_STATES):
            _refuse("review_finding_unverified")
    reviewed_body = {k: v for k, v in reviewer_attestation.items() if k != "proof"}
    if not _signed(reviewed_body, reviewer_attestation["proof"], reviewer_signing_key):
        _refuse("independent_reviewer_signature_invalid")
    if len(stable_serialize(raw_handoff).encode("utf-8")) > MAX_PAYLOAD_BYTES:
        _refuse("unreviewed_handoff_bytes_exceeded")
    result = {
        "version": AUTHORITY_VERSION, "identity": identity, "scan": scan,
        "review": reviewed_body,
        "reviewer_proof": reviewer_attestation["proof"],
        "release_gate_eligible": False,
    }
    if len(stable_serialize(result).encode("utf-8")) > MAX_PAYLOAD_BYTES:
        _refuse("reviewed_authority_bytes_exceeded")
    return {**result, "proof": create_authority_seal(result, authority_signing_key)}
