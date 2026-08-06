"""Durable Standard 150 job worker.

Base44 functions are reaped once the HTTP response returns, so a crawl started
with waitUntil() dies mid-flight: ScanRun 6a748d5f9e8a27963ae678dc logged
worker_scan_start and then produced nothing for 247s until the watchdog closed
it as orphaned_no_terminal_state.

Cloud Run holds a request for up to 300s (--timeout=300 in cloudbuild.yaml), so
the crawl runs here instead. Cloud Tasks delivers the job with an OIDC token,
retries safely, and the exact ScanRun carries the result.

Split of responsibility:
  Base44 startStandardScanJob  -> authenticate, verify the owner-bound ScanRun,
                                  enqueue the task, answer immediately.
  Cloud Run   /scan-job        -> crawl (the slow part), seal the result, then
                                  drive the EXISTING aiReviewScan and
                                  persistScanAuthority functions against the
                                  same ScanRun.

Idempotency is keyed on the existing scan_id: the task name is derived from it,
and this worker refuses to run against a ScanRun that already reached a terminal
state, so a Cloud Tasks retry can never produce a second FixList or a second
allowance charge.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

WORKER_VERSION = "scan_job_worker_v1_cloud_tasks"

# Cloud Run allows 300s; leave room to hand off the result and write a terminal
# state before the platform closes the request.
CRAWL_BUDGET_SECONDS = 210.0
HANDOFF_TIMEOUT_SECONDS = 60.0

TERMINAL_STATUSES = frozenset({"complete", "limited", "failed", "cancelled"})


def base44_api_url() -> str:
    return str(os.getenv("BASE44_API_URL") or "https://base44.app").rstrip("/")


def base44_app_id() -> str:
    return str(os.getenv("BASE44_APP_ID") or "")


def base44_service_token() -> str:
    return str(os.getenv("BASE44_SERVICE_TOKEN") or "")


def _service_headers() -> dict[str, str]:
    return {
        "content-type": "application/json",
        "Base44-Service-Authorization": base44_service_token(),
        "Base44-App-Id": base44_app_id(),
    }


def _function_url(name: str) -> str:
    return f"{base44_api_url()}/api/apps/{base44_app_id()}/functions/{name}"


async def read_scan_run(client: httpx.AsyncClient, scan_id: str) -> dict[str, Any] | None:
    """Read the exact ScanRun through the service-role entity API."""
    url = f"{base44_api_url()}/api/apps/{base44_app_id()}/entities/ScanRun/{scan_id}"
    try:
        response = await client.get(url, headers=_service_headers(), timeout=20.0)
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    try:
        body = response.json()
    except ValueError:
        return None
    return body if isinstance(body, dict) else None


async def write_terminal_failure(
    client: httpx.AsyncClient,
    scan_id: str,
    failure_code: str,
    detail: str,
) -> bool:
    """Close the exact ScanRun truthfully. Never fabricates evidence."""
    url = f"{base44_api_url()}/api/apps/{base44_app_id()}/entities/ScanRun/{scan_id}"
    payload = {
        "status": "failed",
        "status_detail": detail,
        "error_code": failure_code,
        "error_message": detail,
        "completed_at": _now_iso(),
        "release_gate_eligible": False,
    }
    try:
        response = await client.put(url, headers=_service_headers(), json=payload, timeout=20.0)
    except httpx.HTTPError:
        return False
    return response.status_code < 300


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def identity_matches(scan: dict[str, Any], job: dict[str, Any]) -> bool:
    """The task must name the same durable request the ScanRun was created for."""
    for field in ("request_id", "idempotency_key", "project_id"):
        stored = str(scan.get(field) or "").strip()
        claimed = str(job.get(field) or "").strip()
        if stored and claimed and stored != claimed:
            return False
    return True


def already_terminal(scan: dict[str, Any]) -> bool:
    return str(scan.get("status") or "").lower() in TERMINAL_STATUSES


def has_authority_proof(record: dict[str, Any]) -> bool:
    proof = str(record.get("authority_proof") or "")
    return len(proof) == 64 and all(c in "0123456789abcdef" for c in proof)


async def invoke_function(
    client: httpx.AsyncClient,
    name: str,
    payload: dict[str, Any],
    timeout: float = HANDOFF_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Call an existing Base44 function with the service role."""
    try:
        response = await client.post(
            _function_url(name), headers=_service_headers(), json=payload, timeout=timeout
        )
    except httpx.HTTPError:
        return {"status_code": 503, "body": {}}
    try:
        body = response.json()
    except ValueError:
        body = {}
    if isinstance(body, dict):
        body = body.get("data") if isinstance(body.get("data"), dict) else body
    return {"status_code": response.status_code, "body": body if isinstance(body, dict) else {}}


# ---------------------------------------------------------------- authority --
#
# The worker must hand aiReviewScan a scan attestation it will verify, so the
# canonical serialisation below must match authoritySeal.js byte for byte:
# object keys sorted, undefined/function/symbol dropped, non-finite numbers
# nulled, no whitespace.

import hashlib
import hmac
import json

SCAN_ATTESTATION_VERSION = "standard_scan_review_payload_hmac_v2"
REVIEW_PAGE_SAMPLE_LIMIT = 60
REVIEW_FINDING_LIMIT = 100


def canonicalize(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, (int, float)):
        return value if value == value and value not in (float("inf"), float("-inf")) else None
    if isinstance(value, list):
        return [canonicalize(item) for item in value]
    if isinstance(value, dict):
        return {key: canonicalize(value[key]) for key in sorted(value)}
    return None


def stable_serialize(value: Any) -> str:
    return json.dumps(canonicalize(value), separators=(",", ":"), ensure_ascii=False)


def create_authority_seal(payload: Any, secret: str) -> str:
    return hmac.new(secret.encode(), stable_serialize(payload).encode(), hashlib.sha256).hexdigest()


def _first_list(result: dict[str, Any], keys: tuple[str, ...]) -> list:
    for key in keys:
        value = result.get(key)
        if isinstance(value, list):
            return value
    return []


def build_authority_review_payload(result: dict[str, Any]) -> dict[str, Any]:
    """Bounded review envelope. Mirrors buildAuthorityReviewPayload in entry.ts.

    pages_found carries the FULL discovery inventory; only the page sample sent
    to review is bounded. The 150-page crawl cap never truncates discovery.
    """
    pages = _first_list(result, ("crawled_pages", "pages", "scanned_pages", "crawl_pages"))[:REVIEW_PAGE_SAMPLE_LIMIT]
    findings = _first_list(result, ("grouped_findings", "recommendations", "findings", "raw_findings", "fixes"))[:REVIEW_FINDING_LIMIT]
    technical = result.get("technical_audit_summary") if isinstance(result.get("technical_audit_summary"), dict) else {}
    scan_summary = result.get("scan_summary") if isinstance(result.get("scan_summary"), dict) else {}
    n = lambda v: max(0, int(v)) if isinstance(v, (int, float)) else 0  # noqa: E731

    return {
        "success": True,
        "review_payload_version": SCAN_ATTESTATION_VERSION,
        "scanner_version": result.get("scanner_version"),
        "scanner_build_revision": result.get("scanner_build_revision") or technical.get("scanner_build_revision"),
        "scanner_wrapper_version": result.get("scanner_wrapper_version"),
        "beta_revision_fingerprint": result.get("beta_revision_fingerprint"),
        "advanced_scan_backend": result.get("advanced_scan_backend"),
        "deno_fallback_used": False,
        "scan_mode": "standard_150",
        "canonical_mode": "standard_150",
        "request_id": result.get("request_id"),
        "idempotency_key": result.get("idempotency_key"),
        "scan_id": result.get("scan_id"),
        "scan_run_id": result.get("scan_run_id"),
        "submitted_url": result.get("submitted_url"),
        "website_url": result.get("website_url"),
        "final_url": result.get("final_url"),
        "normalized_domain": result.get("normalized_domain"),
        "respect_robots_txt": True,
        "pages_crawled": n(result.get("pages_crawled")),
        "pages_found": n(result.get("pages_found")),
        "queued_remaining": n(result.get("queued_remaining")),
        "sampled_pages_sent_to_review": len(pages),
        "sampled_findings_sent_to_review": len(findings),
        "page_sample_truncated": n(result.get("pages_crawled")) > len(pages),
        "scanner_elapsed_ms": n(result.get("scanner_elapsed_ms")),
        "scanner_total_budget_seconds": float(result.get("scanner_total_budget_seconds") or 0),
        "scan_deadline_reached": result.get("scan_deadline_reached") is True,
        "requested_crawl_timeout_ms": n(result.get("requested_crawl_timeout_ms")),
        "metadata_evidence_version": result.get("metadata_evidence_version") or technical.get("metadata_evidence_version") or "",
        "title_evidence_version": result.get("title_evidence_version") or technical.get("title_evidence_version") or "",
        "sampling_evidence": result.get("sampling_evidence") or {},
        "crawl_timing": result.get("crawl_timing") or technical.get("crawl_timing") or {},
        "crawl_scope": result.get("crawl_scope") or technical.get("crawl_scope") or {},
        "crawl_policy": result.get("crawl_policy") or technical.get("crawl_policy") or {},
        "crawl_policy_source": result.get("crawl_policy_source") or technical.get("crawl_policy_source") or "",
        "url_evidence_summary": result.get("url_evidence_summary") or technical.get("url_evidence_summary") or {},
        "verified_failed_pages": (result.get("verified_failed_pages") or [])[:25] if isinstance(result.get("verified_failed_pages"), list) else [],
        "suspicious_url_artifacts": (result.get("suspicious_url_artifacts") or [])[:25] if isinstance(result.get("suspicious_url_artifacts"), list) else [],
        "health_score": float(result.get("health_score") or 0),
        "scan_summary": scan_summary,
        "technical_audit_summary": technical,
        "crawl_warnings": (result.get("crawl_warnings") or [])[:12] if isinstance(result.get("crawl_warnings"), list) else [],
        "crawled_pages": pages,
        "grouped_findings": findings,
    }


def build_scan_attestation(result: dict[str, Any], scan: dict[str, Any], signing_key: str) -> dict[str, Any]:
    review_payload = build_authority_review_payload(result)
    identity = {
        "version": SCAN_ATTESTATION_VERSION,
        "owner_user_id": str(scan.get("owner_user_id") or ""),
        "scan_id": str(scan.get("id") or ""),
        "project_id": str(scan.get("project_id") or ""),
        "normalized_domain": str(result.get("normalized_domain") or "").lower().removeprefix("www."),
    }
    proof = create_authority_seal({**identity, "result": review_payload}, signing_key)
    return {
        "authority_review_payload": review_payload,
        "authority_scan_attestation": {**identity, "proof": proof},
    }


def fix_list_belongs_to_scan(fix_list: dict[str, Any], scan: dict[str, Any]) -> bool:
    """A FixList may only be accepted for the exact owner, project and ScanRun."""
    return (
        str(fix_list.get("scan_run_id") or "") == str(scan.get("id") or "")
        and str(fix_list.get("project_id") or "") == str(scan.get("project_id") or "")
        and str(fix_list.get("owner_user_id") or "") == str(scan.get("owner_user_id") or "")
    )


async def record_allowance_once(client: httpx.AsyncClient, owner_email: str) -> bool:
    """Charge the customer's free-scan allowance at most once.

    Called only after the authority seal is verified, and only on a ScanRun that
    was not already terminal, so a Cloud Tasks retry cannot double-charge.
    """
    if not owner_email:
        return False
    base = f"{base44_api_url()}/api/apps/{base44_app_id()}/entities/Access"
    try:
        listing = await client.get(
            base, headers=_service_headers(), params={"user_email": owner_email}, timeout=20.0
        )
        rows = listing.json() if listing.status_code == 200 else []
    except (httpx.HTTPError, ValueError):
        return False
    row = rows[0] if isinstance(rows, list) and rows else None
    if isinstance(row, dict) and row.get("has_full_access") is True:
        return True  # nothing to charge
    try:
        if isinstance(row, dict) and row.get("id"):
            used = int(row.get("scans_used") or 0)
            response = await client.put(
                f"{base}/{row['id']}", headers=_service_headers(),
                json={"scans_used": used + 1}, timeout=20.0,
            )
        else:
            response = await client.post(
                base, headers=_service_headers(),
                json={"user_email": owner_email, "scans_used": 1, "has_full_access": False},
                timeout=20.0,
            )
    except httpx.HTTPError:
        return False
    return response.status_code < 300


async def complete_authority(
    client: httpx.AsyncClient,
    scan: dict[str, Any],
    result: dict[str, Any],
    signing_key: str,
) -> dict[str, Any]:
    """Seal -> aiReviewScan -> persistScanAuthority, all on the same ScanRun.

    Returns {ok, failure_code, transient, fix_list_id, authority_proof}.
    `transient` asks the caller to raise so Cloud Tasks retries; the ScanRun is
    left untouched in that case.
    """
    attested = build_scan_attestation(result, scan, signing_key)

    review = await invoke_function(client, "aiReviewScan", {
        "authoritative_scan": {
            "authority_review_payload": attested["authority_review_payload"],
            "authority_scan_attestation": attested["authority_scan_attestation"],
            "authority_attestation_status": "server_attested",
        },
        "client_context": {
            "business_name": str(result.get("business_name") or ""),
            "cms_platform": str(result.get("cms_platform") or ""),
            "important_keywords": [],
            "requested_path_prefix": "",
        },
    })
    if review["status_code"] >= 500:
        return {"ok": False, "transient": True, "failure_code": "review_unavailable"}
    attestation = review["body"].get("authority_review_attestation")
    if review["status_code"] >= 400 or review["body"].get("success") is False or not attestation:
        return {"ok": False, "transient": False, "failure_code": "review_attestation_missing"}

    persisted = await invoke_function(client, "persistScanAuthority", {
        "scan_id": str(scan.get("id") or ""),
        "attestation": attestation,
    })
    if persisted["status_code"] >= 500:
        return {"ok": False, "transient": True, "failure_code": "persistence_unavailable"}
    scan_run = persisted["body"].get("scanRun") if isinstance(persisted["body"].get("scanRun"), dict) else {}
    fix_list_id = str(persisted["body"].get("fixListId") or scan_run.get("fix_list_id") or "")
    if persisted["status_code"] >= 400 or not has_authority_proof(scan_run) or not fix_list_id:
        return {"ok": False, "transient": False, "failure_code": "authority_persistence_failed"}

    # Re-read the FixList and require it to belong to this exact owner, project
    # and ScanRun before anything is treated as authoritative or charged.
    try:
        fetched = await client.get(
            f"{base44_api_url()}/api/apps/{base44_app_id()}/entities/FixList/{fix_list_id}",
            headers=_service_headers(), timeout=20.0,
        )
        fix_list = fetched.json() if fetched.status_code == 200 else {}
    except (httpx.HTTPError, ValueError):
        return {"ok": False, "transient": True, "failure_code": "fix_list_unreadable"}
    if not isinstance(fix_list, dict) or not fix_list_belongs_to_scan(fix_list, scan):
        return {"ok": False, "transient": False, "failure_code": "fix_list_ownership_mismatch"}
    if str(fix_list.get("authority_proof") or "") != str(scan_run.get("authority_proof") or ""):
        return {"ok": False, "transient": False, "failure_code": "fix_list_proof_mismatch"}

    await record_allowance_once(client, str(scan.get("created_by") or scan.get("owner_email") or ""))
    return {
        "ok": True,
        "transient": False,
        "failure_code": "",
        "fix_list_id": fix_list_id,
        "authority_proof": str(scan_run.get("authority_proof") or ""),
    }
