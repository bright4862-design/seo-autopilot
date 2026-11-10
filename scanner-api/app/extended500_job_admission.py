"""Fail-closed, read-only admission preflight for a FUTURE Extended 500 job.

This is deliberately not a task queue, entitlement issuer, claim/CAS writer,
crawler, or result persistence path. Standard 150 retains its legacy route.
A signed grant is necessary but NOT sufficient: a future atomic admission claim
and separate audited entitlement issuer must be built before executing work.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hmac
import re
from typing import Any
from urllib.parse import urlsplit

from .authority_seal import create_authority_seal

EXTENDED500_JOB_MODE = "extended_500"
EXTENDED500_GRANT_VERSION = "extended500_preflight_grant_v1"
EXTENDED500_GRANT_AUDIENCE = "fixlist_extended500_worker"
EXTENDED500_GRANT_MAX_SECONDS = 300
_IDENTITY_FIELDS = (
    "owner_user_id", "project_id", "request_id", "idempotency_key",
)
_GRANT_FIELDS = frozenset({
    "version", "audience", "canonical_mode", "scan_id", "owner_user_id",
    "project_id", "request_id", "idempotency_key", "attempt_count",
    "website_url", "path_prefix", "respect_robots_txt",
    "owner_attested_robots_override", "issued_at", "expires_at", "proof",
})
_TOKEN = re.compile(r"[^\s]{1,256}\Z")


def _string(value: Any) -> str:
    return value if isinstance(value, str) and bool(_TOKEN.fullmatch(value)) else ""


def _url(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    try:
        parsed = urlsplit(value)
        if (parsed.scheme not in ("http", "https") or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.fragment or parsed.query or parsed.port not in (None, 80, 443)):
            return ""
        hostname = parsed.hostname.lower().rstrip(".")
        return f"{parsed.scheme}://{hostname}{parsed.path or '/'}"
    except ValueError:
        return ""


def _path(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str) or not value.startswith("/") or len(value) > 2048:
        return ""
    if "?" in value or "#" in value or "\\" in value or "//" in value:
        return ""
    return value


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def evaluate_extended500_preflight(
    task: dict[str, Any],
    frozen: dict[str, Any],
    signed_grant: dict[str, Any],
    grant_signing_key: str,
    *,
    now: datetime | None = None,
) -> str:
    """Return a stable denial reason or 'verified_read_only'.

    The caller MUST obtain frozen from a service-authenticated ScanRun read.
    The grant is a separate server-minted entitlement assertion, not a task
    field the user can elect. Neither preflight result executes or persists.
    """
    if not all(isinstance(value, dict) for value in (task, frozen, signed_grant)):
        return "malformed_input"
    if task.get("scan_mode") != EXTENDED500_JOB_MODE or frozen.get("scan_mode") != EXTENDED500_JOB_MODE:
        return "mode_not_frozen"
    if str(frozen.get("status") or "").lower() != "queued":
        return "run_not_queued"
    if not _string(task.get("scan_id")) or task["scan_id"] != frozen.get("id"):
        return "scan_identity_mismatch"
    for key in _IDENTITY_FIELDS:
        if not _string(task.get(key)) or task[key] != frozen.get(key):
            return "owner_request_identity_mismatch"
    attempt = task.get("attempt_count")
    if type(attempt) is not int or attempt < 1 or type(frozen.get("attempt_count")) is not int:
        return "attempt_invalid"
    if frozen["attempt_count"] != attempt:
        return "superseded_attempt"

    website = _url(task.get("website_url"))
    persisted = _url(frozen.get("website_url"))
    if not website or not persisted or website != persisted:
        return "target_mismatch"
    if frozen.get("normalized_domain"):
        domain = str(frozen["normalized_domain"]).lower().removeprefix("www.").rstrip(".")
        if domain != (urlsplit(website).hostname or "").removeprefix("www."):
            return "domain_mismatch"
    prefix, stored_prefix = _path(task.get("path_prefix")), _path(frozen.get("path_prefix"))
    if prefix == "" or stored_prefix == "" or prefix != stored_prefix:
        return "scope_mismatch"
    for key in ("respect_robots_txt", "owner_attested_robots_override"):
        if type(task.get(key)) is not bool or type(frozen.get(key)) is not bool:
            return "robots_policy_invalid"
        if task[key] != frozen[key]:
            return "robots_policy_mismatch"
    if task["owner_attested_robots_override"] != (task["respect_robots_txt"] is False):
        return "robots_policy_invalid"

    if set(signed_grant) != _GRANT_FIELDS:
        return "grant_shape_invalid"
    if signed_grant.get("version") != EXTENDED500_GRANT_VERSION or signed_grant.get("audience") != EXTENDED500_GRANT_AUDIENCE:
        return "grant_context_invalid"
    if signed_grant.get("canonical_mode") != EXTENDED500_JOB_MODE:
        return "grant_mode_invalid"
    mappings = (
        ("scan_id", "scan_id"), *[(key, key) for key in _IDENTITY_FIELDS],
        ("attempt_count", "attempt_count"), ("website_url", "website_url"),
        ("path_prefix", "path_prefix"), ("respect_robots_txt", "respect_robots_txt"),
        ("owner_attested_robots_override", "owner_attested_robots_override"),
    )
    for gkey, tkey in mappings:
        # In Python, True == 1. A signed boolean must not impersonate the
        # numeric attempt, nor may numeric flags impersonate frozen bools.
        if (type(signed_grant.get(gkey)) is not type(task.get(tkey))
                or signed_grant.get(gkey) != task.get(tkey)):
            return "grant_identity_mismatch"
    issued, expires = _timestamp(signed_grant.get("issued_at")), _timestamp(signed_grant.get("expires_at"))
    instant = now if isinstance(now, datetime) else datetime.now(timezone.utc)
    if instant.tzinfo is None or not issued or not expires:
        return "grant_time_invalid"
    instant = instant.astimezone(timezone.utc)
    if issued > instant or expires <= instant or not timedelta(0) < (expires - issued) <= timedelta(seconds=EXTENDED500_GRANT_MAX_SECONDS):
        return "grant_expired_or_out_of_window"
    if not isinstance(grant_signing_key, str) or len(grant_signing_key) < 32:
        return "grant_signing_unavailable"
    proof = signed_grant.get("proof")
    if not isinstance(proof, str) or not re.fullmatch(r"[a-f0-9]{64}", proof):
        return "grant_signature_invalid"
    document = {key: value for key, value in signed_grant.items() if key != "proof"}
    try:
        expected = create_authority_seal(document, grant_signing_key)
    except Exception:
        return "grant_signature_invalid"
    if not hmac.compare_digest(expected, proof):
        return "grant_signature_invalid"
    return "verified_read_only"
