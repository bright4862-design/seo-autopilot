"""Retain the exact signed writer request until its staged finalizer is acknowledged."""

from contextvars import ContextVar
from hmac import compare_digest
import re

from .authority_seal import create_authority_seal
from .generated_v9_worker_runtime import (
    V9_WORKER_FUNCTION_IDENTITIES, V9_WORKER_FUNCTION_ROUTES, V9_WORKER_RELEASE_FINGERPRINT,
)
from .workspace import WorkspaceConflict, WorkspaceUnavailable


prepare_staged_completion = ContextVar("prepare_staged_completion", default=None)
WRITERS = {"complete": "persistDurableScanAuthorityV9", "limited": "persistLimitedScanResultV9"}
ARCHIVE_NAME = "writer-request.json.gz"
HEX_PROOF = re.compile("[a-f0-9]{64}")


def exact_job(scan, job):
    required = ("owner_user_id", "project_id", "request_id", "idempotency_key", "normalized_domain", "website_url")
    return (
        bool(scan.get("id")) and scan["id"] == job.get("scan_id")
        and all(isinstance(scan.get(field), str) and scan[field] and scan[field] == job.get(field) for field in required)
        and all(type(scan.get(field)) is bool and scan[field] is job.get(field)
                for field in ("respect_robots_txt", "owner_attested_robots_override"))
        and (scan.get("path_prefix") or "") == (job.get("path_prefix") or "")
        and scan.get("pipeline_mode") == job.get("pipeline_mode") == "staged"
        and type(job.get("page_cap")) is int and type(scan.get("page_cap")) is int
        and scan["page_cap"] == job["page_cap"] and job["page_cap"] in (150, 500)
        and scan.get("scan_mode") == job.get("scan_mode") == f"standard_{job['page_cap']}"
        and type(scan.get("attempt_count")) is int and type(job.get("attempt_count")) is int
        and scan["attempt_count"] == job["attempt_count"] and job["attempt_count"] > 0
    )


def terminal_seal(scan):
    status = scan.get("status")
    full, limited = scan.get("authority_proof"), scan.get("result_integrity_proof")
    expected, incompatible = (full, limited) if status == "complete" else (limited, full)
    if (status in WRITERS and scan.get("fix_list_id") and not incompatible
            and isinstance(expected, str) and HEX_PROOF.fullmatch(expected)):
        return expected
    return None


def released(scan):
    if not scan.get("admission_access_id"):
        return True
    return (scan.get("admission_release_state") == "released"
            and scan.get("admission_release_outcome") in ("released", "already_released")
            and scan.get("admission_release_coordinator_request_id") == scan.get("request_id"))



def binding_for(job, scan, frontier, batch, generations, ready_at, writer):
    # Bind the request to the identity accepted by the launcher and to the
    # exact committed inputs. Copying it across attempts or builds must fail.
    return {
        "version": "staged_writer_request_v1",
        "scan_id": job["scan_id"], "attempt": job["attempt_count"], "batch": batch,
        "owner": scan.get("owner_user_id"), "project": scan.get("project_id"),
        "request": scan.get("request_id"), "idempotency_key": scan.get("idempotency_key"),
        "website_url": job["website_url"], "normalized_domain": job["normalized_domain"],
        "path_prefix": scan.get("path_prefix") or "", "pipeline_mode": job["pipeline_mode"],
        "page_cap": job["page_cap"], "scan_mode": job["scan_mode"],
        "respect_robots_txt": scan.get("respect_robots_txt"),
        "owner_attested_robots_override": scan.get("owner_attested_robots_override"),
        "admission_access_id": scan.get("admission_access_id"),
        "claim_sequence": scan.get("admission_claim_sequence"),
        "barrier_generation": scan.get("admission_barrier_generation"),
        "state_ref": frontier["state_ref"], "generations": generations,
        "ready_at": ready_at, "writer": writer, "route": V9_WORKER_FUNCTION_ROUTES[writer],
        "runtime": V9_WORKER_FUNCTION_IDENTITIES[writer], "release": V9_WORKER_RELEASE_FINGERPRINT,
    }


def verified_packet(record, binding, key):
    envelope = record.get("envelope")
    if record.get("binding") != binding or not isinstance(envelope, dict):
        return None
    document = {k: v for k, v in envelope.items() if k != "proof"}
    proof = envelope.get("proof")
    metadata_proof = record.get("binding_proof")
    if not all(isinstance(value, str) and HEX_PROOF.fullmatch(value) for value in (proof, metadata_proof)):
        return None
    if not compare_digest(create_authority_seal({**binding, "request_proof": proof}, key), metadata_proof):
        return None
    return envelope if compare_digest(create_authority_seal(document, key), proof) else None


async def retain_packet(store, prefix, binding, envelope, key):
    name = prefix + ARCHIVE_NAME
    existing = await store.read(name)
    if existing is None:
        record = {"binding": binding, "envelope": envelope,
                  "binding_proof": create_authority_seal({**binding, "request_proof": envelope["proof"]}, key)}
        try:
            await store.write(name, record)
            return envelope
        except WorkspaceConflict:
            existing = await store.read(name)
    packet = verified_packet(existing.value, binding, key) if existing else None
    if packet is None:
        raise WorkspaceUnavailable("The saved staged writer request does not match its committed evidence")
    return packet
