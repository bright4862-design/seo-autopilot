#!/usr/bin/env python3
"""Read the private evidence of one already-completed real-site QA scan."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from urllib.parse import unquote, urlsplit

SCANNER_ROOT = Path(__file__).resolve().parents[1]
if __name__ == "__main__":
    sys.path.insert(0, str(SCANNER_ROOT))

from app.metadata_title_evidence import is_html_page_evidence
from app.scanner import final_url_identity
from app.workspace import WorkspaceObject
from scripts import collect_staged_scan_receipts as receipt
from scripts.collect_published_paid_500 import EMPTY_COHORT, digest, require_fields, verify_signature

INPUT_VERSION = "real_site_qa_receipt_input_v1"
EVIDENCE_VERSION = "real_site_qa_receipt_evidence_v1"
OUTCOMES = {"complete_at_cap", "complete_queue_exhausted", "limited"}
LIMIT_REASONS = {
    "rate_limit": "staged_rate_limit",
    "initial_access_limited": "staged_partial_evidence",
    "wall_budget": "staged_wall_budget",
    "request_budget": "staged_partial_evidence",
}
REOPENED_RUN_FIELDS = (
    "id", "project_id", "website_url", "page_cap", "scan_mode", "pipeline_mode", "status",
    "pages_crawled", "pages_planned", "beta_revision_fingerprint", "started_at", "completed_at",
)
require, mapping, matches, positive = receipt.require, receipt.mapping, receipt.matches, receipt.positive


@dataclass(frozen=True)
class ReviewedScope:
    row_id: str
    outcome: str
    path_prefix: str
    url_prefixes: tuple[str, ...]
    authorization_reference_sha256: str
    limit_reason: str = ""


def url_parts(value):
    require(isinstance(value, str) and 0 < len(value) <= 3072 and not any(c.isspace() for c in value),
            "qa_scope_url_invalid")
    try:
        parsed = urlsplit(value)
        decoded = unquote(parsed.path or "/", errors="strict")
        require(parsed.scheme == "https" and parsed.hostname and parsed.username is None
                and parsed.password is None and not parsed.fragment and parsed.port in {None, 443}
                and not any(c in decoded for c in ("\\", "%", "\x00", "#", "?"))
                and "/" not in unquote(parsed.netloc)
                and not {".", ".."}.intersection(decoded.split("/"))
                and len(decoded.split("/")) == len((parsed.path or "/").split("/")), "qa_scope_url_invalid")
    except (ValueError, UnicodeError) as exc:
        raise receipt.EvidenceError("qa_scope_url_invalid") from exc
    return parsed.hostname, decoded.rstrip("/") or "/", parsed.query


def within_scope(url, prefixes):
    host, path, _ = url_parts(url)
    for prefix in prefixes:
        allowed_host, allowed_path, query = url_parts(prefix)
        if not query and host == allowed_host and (
                allowed_path == "/" or path == allowed_path or path.startswith(allowed_path + "/")):
            return True
    return False


def validate_readbacks(packet, *, expected_result_route, claim_key, now_ms=None):
    require(isinstance(packet, dict) and packet.get("schema_version") == INPUT_VERSION, "qa_input_version_invalid")
    scope, runtime, run, browser = (mapping(packet.get(name)) for name in (
        "approved_scope", "worker_runtime", "saved_run", "browser",
    ))
    cap, target, path, outcome = (scope.get(name) for name in (
        "page_cap", "target_url", "path_prefix", "expected_outcome",
    ))
    row, authorization = scope.get("row_id"), scope.get("authorization_reference_sha256")
    prefixes, limit = scope.get("allowed_url_prefixes"), scope.get("expected_limit_reason", "")
    require(type(cap) is int and cap in {150, 500}
            and isinstance(row, str) and re.fullmatch(rf"S(?:0[1-9]|1[0-9]|20)-{cap}", row)
            and isinstance(outcome, str) and outcome in OUTCOMES
            and isinstance(path, str) and path.startswith("/") and not path.startswith("//")
            and matches(receipt.SHA256, authorization) and isinstance(prefixes, list)
            and 0 < len(prefixes) <= 8 and all(not url_parts(prefix)[2] for prefix in prefixes)
            and isinstance(limit, str) and (limit in LIMIT_REASONS if outcome == "limited" else limit == ""),
            "qa_reviewed_scope_invalid")
    target_parts = urlsplit(target) if within_scope(target, prefixes) else None
    require(target_parts is not None and within_scope(target_parts._replace(path=path, query="").geturl(), prefixes),
            "qa_target_outside_reviewed_scope")
    source, fingerprint = runtime.get("source_sha"), runtime.get("release_fingerprint")
    process_mode = runtime.get("pipeline_mode")
    require(matches(receipt.SOURCE_SHA, source) and matches(receipt.FINGERPRINT, fingerprint)
            and runtime.get("service") == receipt.WORKER_SERVICE and process_mode in {"monolith", "staged"}
            and matches(receipt.WORKER_REVISION, runtime.get("revision"))
            and matches(receipt.SHA256, runtime.get("staged_config_sha256"))
            and matches(receipt.SHA256, runtime.get("staged_owner_cohort_sha256")), "qa_runtime_identity_invalid")
    if process_mode == "monolith":
        # The canonical paid worker's process mode differs from the immutable
        # staged attempt in its delivery. Bind both sides and the empty cohort.
        require(runtime["staged_owner_cohort_sha256"] == EMPTY_COHORT and run.get("staged_rollout_scope") == "paid",
                "qa_paid_runtime_identity_invalid")

    owner, project = scope.get("owner_user_id"), scope.get("project_id")
    scan, request, fix_list = (run.get(name) for name in ("id", "request_id", "fix_list_id"))
    require(matches(receipt.OWNER_ID, owner)
            and all(matches(receipt.ID, item) for item in (project, scan, request, fix_list)), "qa_attempt_identity_invalid")
    complete = outcome != "limited"
    status = "complete" if complete else "limited"
    require_fields(run, {
        "owner_user_id": owner, "project_id": project, "idempotency_key": request,
        "website_url": target, "page_cap": cap, "scan_mode": f"standard_{cap}", "pipeline_mode": "staged",
        "status": status, "beta_revision_fingerprint": fingerprint, "release_gate_eligible": complete,
        "admission_release_state": "released",
        "admission_release_coordinator_request_id": request,
    }, "qa_saved_attempt_mismatch")
    proof_field = "authority_proof" if complete else "result_integrity_proof"
    require(matches(receipt.SHA256, run.get(proof_field)) and (complete or not run.get("authority_proof")),
            "qa_saved_terminal_proof_missing")
    publication = mapping(mapping(run.get("crawl_timing")).get("target_cooldown_publication"))
    require(publication.get("state") != "unconfirmed", "qa_target_cooldown_unconfirmed")
    pages, planned, batch, attempt = (run.get(name) for name in (
        "pages_crawled", "pages_planned", "last_committed_batch", "attempt_count",
    ))
    require(positive(pages) and positive(planned) and 0 < pages <= planned <= cap
            and type(batch) is int and 0 <= batch < receipt.MAX_RECORDED_DELIVERIES - 2 and pages <= (batch + 1) * 50
            and positive(attempt) and attempt < 2**31
            and (pages == planned == cap if outcome == "complete_at_cap" else outcome == "limited" or pages < cap),
            "qa_terminal_progress_mismatch")
    start, end, reopened, release, allowed_from, allowed_until = (receipt.parse_timestamp(value) for value in (
        run.get("started_at"), run.get("completed_at"), browser.get("history_reopened_at"),
        run.get("admission_release_reconciled_at"), scope.get("authorized_from"), scope.get("authorized_until"),
    ))
    now = time.time_ns() // 1_000_000 if now_ms is None else now_ms
    require(allowed_from <= start < end <= allowed_until and end <= reopened <= now + 30_000
            and start <= release <= now + 30_000 and end - start <= 1_800_000
            and run.get("admission_release_outcome") in {"released", "already_released"}, "qa_attempt_window_mismatch")

    claim_fields = ("barrier_generation", "claim_sequence", "acceptance_cohort_id", "acceptance_release_id",
                    "acceptance_source_sha", "acceptance_expires_at")
    claim = {"version": run.get("admission_cohort_evidence_version"), "owner_user_id": owner, "request_id": request,
             "admission_mode": run.get("admission_mode"), **{name: run.get("admission_" + name) for name in claim_fields}}
    require(claim["version"] == "admission_claim_evidence_v1" and positive(claim["claim_sequence"])
            and type(claim["barrier_generation"]) is int and claim["barrier_generation"] >= 0, "qa_admission_claim_invalid")
    if claim["admission_mode"] == "acceptance_only":
        require(all(matches(receipt.ID, claim[name]) for name in ("acceptance_cohort_id", "acceptance_release_id"))
                and claim["acceptance_source_sha"] == source and positive(claim["acceptance_expires_at"])
                and start < claim["acceptance_expires_at"] * 1000, "qa_admission_claim_invalid")
    else:
        require(claim["admission_mode"] == "open" and all(claim[name] == "" for name in claim_fields[2:5])
                and claim["acceptance_expires_at"] is None, "qa_admission_claim_invalid")
    verify_signature(claim, run.get("admission_cohort_evidence_proof"), claim_key,
                     b"fixlist-admission-claim-evidence-v1", "qa_admission_claim_signature_invalid")

    require_fields(browser, {
        "owner_user_id": owner, "role": "user", "result_route": expected_result_route,
        "history_url": f"https://getfixlist.com/dashboard?scan_id={scan}",
    }, "qa_published_history_mismatch")
    projection = mapping(browser.get("projection"))
    require_fields(projection, {
        "success": True, "access": "full", "release_contract_current": True, "scan_id": scan, "fix_list_id": fix_list,
        "authority_verified": complete, "result_integrity_verified": not complete,
    }, "qa_terminal_readback_mismatch")
    require_fields(projection.get("run"), {field: run[field] for field in REOPENED_RUN_FIELDS}, "qa_terminal_readback_mismatch")
    if not complete:
        reasons = projection["run"].get("coverage_reasons")
        require(isinstance(reasons, list) and LIMIT_REASONS[limit] in reasons, "qa_limited_readback_reason_mismatch")
    return (
        receipt.Canary(scan, attempt, hashlib.sha256(request.encode()).hexdigest(), status, pages, planned, batch + 1,
                       start, start, end, runtime, cap, owner, project, target),
        ReviewedScope(row, outcome, path, tuple(prefixes), authorization, limit),
    )


def page_sets(document, canary, scope):
    pages = document.get("pages")
    require(isinstance(pages, list) and len(pages) <= canary.page_cap, "qa_page_manifest_invalid")
    urls, usable = set(), set()
    for value in pages:
        page = mapping(value)
        final = page.get("final_url") or page.get("url")
        require(within_scope(page.get("url"), scope.url_prefixes) and within_scope(final, scope.url_prefixes),
                "qa_page_outside_reviewed_scope")
        url = final_url_identity(final)
        require(url and url not in urls, "qa_page_identity_duplicate")
        urls.add(url)
        status = page.get("status_code")
        if type(status) is int and 200 <= status < 300 and not page.get("fetch_error") and is_html_page_evidence(page):
            usable.add(url)
    return urls, usable


async def verify_page_evidence(canary, storage, prefix, artifacts, generations, *, scope):
    async def read(path):
        observed = await storage.read_evidence(prefix + path)
        require(isinstance(observed, WorkspaceObject) and str(observed.generation) == generations[path],
                "qa_page_artifact_generation_mismatch")
        return mapping(observed.value)

    plan = await read("plan.json")
    job = mapping(plan.get("job"))
    request = job.get("request_id")
    require(matches(receipt.ID, request) and hashlib.sha256(request.encode()).hexdigest() == canary.request_digest,
            "qa_plan_identity_mismatch")
    require_fields(job, {
        "scan_id": canary.scan_id, "attempt_count": canary.attempt, "owner_user_id": canary.owner_user_id,
        "project_id": canary.project_id, "website_url": canary.target_url, "idempotency_key": request,
        "scan_mode": f"standard_{canary.page_cap}", "page_cap": canary.page_cap, "pipeline_mode": "staged",
        "respect_robots_txt": True, "owner_attested_robots_override": False,
    }, "qa_plan_identity_mismatch")
    if canary.runtime["pipeline_mode"] == "monolith":
        require(job.get("staged_rollout_scope") == "paid", "qa_paid_plan_contract_invalid")
    require((job.get("path_prefix") or "/") == scope.path_prefix and mapping(plan.get("state")).get("pages") == [],
            "qa_plan_scope_mismatch")

    previous, batches = set(), []
    for _, pages_path in artifacts:
        current, _ = page_sets(await read(pages_path), canary, scope)
        require(previous <= current and len(current - previous) <= 50, "qa_committed_page_set_changed")
        batches.append(len(current - previous))
        previous = current

    result = await read("result.json.gz")
    limited = canary.terminal_status == "limited"
    require_fields(result, {
        "success": True, "scan_id": canary.scan_id, "request_id": request, "idempotency_key": request,
        "submitted_url": canary.target_url, "scan_mode": f"standard_{canary.page_cap}", "pipeline_mode": "staged",
        "pipeline_limited": limited, "page_cap": canary.page_cap, "pages_crawled": canary.pages,
        "advanced_scan_backend": "python_scanner_api", "deno_fallback_used": False,
        "beta_revision_fingerprint": canary.runtime["release_fingerprint"],
    }, "qa_worker_result_mismatch")
    timing = mapping(result.get("crawl_timing"))
    require((not limited or result.get("pipeline_limit_reason") == scope.limit_reason)
            and (scope.outcome != "complete_queue_exhausted" or timing.get("queue_exhausted") is True),
            "qa_worker_terminal_reason_mismatch")
    urls, usable = page_sets(result, canary, scope)
    require(len(urls) == canary.pages and urls == previous, "qa_terminal_page_set_mismatch")
    found, inventory_capped = result.get("pages_found"), result.get("inventory_capped")
    require(type(found) is int and found >= 0 and type(inventory_capped) is bool, "qa_discovered_inventory_missing")
    return {
        "terminal_outcome": scope.outcome, "terminal_limit_reason": scope.limit_reason or None,
        "checked_distinct_url_count": len(urls), "checked_url_set_sha256": digest(sorted(urls)),
        "usable_html_count": len(usable), "usable_html_set_sha256": digest(sorted(usable)),
        "discovered_url_count": found, "inventory_capped": inventory_capped, "committed_batch_page_deltas": batches,
        "rate_limit_observed": (scope.limit_reason in {"rate_limit", "initial_access_limited"}
                                or positive(timing.get("crawl_pressure_429_count"))
                                or positive(timing.get("rate_limit_initial_retry_count"))
                                or timing.get("optional_checks_notice_reason") == "site_rate_limited"),
    }


async def collect_reviewed_site(canary, scope, storage):
    evidence = await receipt.collect(canary, storage, verify_pages=partial(verify_page_evidence, scope=scope))
    require(evidence.get("receipt_evidence_verified") is True, "qa_worker_receipts_unverified")
    return evidence


def read_private(path, limit):
    require(path.is_absolute() and path.resolve(strict=True) == path, "qa_input_path_invalid")
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as source:
        mode = os.fstat(source.fileno()).st_mode
        require(stat.S_ISREG(mode) and stat.S_IMODE(mode) & 0o077 == 0, "qa_input_permissions_invalid")
        contents = source.read(limit + 1)
    require(0 < len(contents) <= limit, "qa_input_size_invalid")
    return contents


def released_result_route(source, fingerprint):
    require(matches(receipt.SOURCE_SHA, source) and matches(receipt.FINGERPRINT, fingerprint), "qa_source_identity_invalid")

    def read(path):
        return json.loads(subprocess.run(["git", "show", f"{source}:{path}"], cwd=SCANNER_ROOT.parent,
                                         capture_output=True, check=True, timeout=5).stdout)
    require(read("data/beta-crawler-revision.json")["fingerprint"] == fingerprint, "qa_source_identity_invalid")
    return read("data/generated-staged-v9-routes.json")["functions"]["getCustomerScanResultV9"]["route_name"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--claim-key-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        raw = read_private(args.input, receipt.MAX_CANARY_BYTES)
        packet = mapping(json.loads(raw))
        runtime = mapping(packet.get("worker_runtime"))
        route = released_result_route(runtime.get("source_sha"), runtime.get("release_fingerprint"))
        canary, scope = validate_readbacks(packet, expected_result_route=route,
                                          claim_key=read_private(args.claim_key_file, 4096))
        output = args.output
        require(output.is_absolute() and output.parent.is_dir() and output.parent.resolve(strict=True) == output.parent
                and not output.is_relative_to(SCANNER_ROOT.parent) and not output.exists(), "qa_output_path_invalid")
        require(not os.getenv("STORAGE_EMULATOR_HOST"), "workspace_emulator_refused")
        from google.cloud import storage

        reader = receipt.ReceiptStorage(storage.Client().bucket(receipt.BUCKET))
        evidence = asyncio.run(asyncio.wait_for(collect_reviewed_site(canary, scope, reader),
                                               receipt.COLLECTION_TIMEOUT_SECONDS))
        report = {
            "schema_version": EVIDENCE_VERSION, "scope": "real_site_terminal_receipt",
            "production_freeze": False, "quality_review_verified": False,
            "qa_row_id": scope.row_id, "authorization_reference_sha256": scope.authorization_reference_sha256,
            "input_capture_sha256": hashlib.sha256(raw).hexdigest(),
            "scan_id": canary.scan_id, "attempt_count": canary.attempt, "page_cap": canary.page_cap,
            "terminal_status": canary.terminal_status, "planned_page_count": canary.planned,
            "committed_batch_count": canary.batches, "duration_seconds": (canary.completed_ms - canary.started_ms) / 1000,
            "source_sha": runtime["source_sha"], "release_fingerprint": runtime["release_fingerprint"],
            "worker_revision": runtime["revision"], "workspace_bucket": receipt.BUCKET,
            **evidence,
        }
        with os.fdopen(os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600), "w") as file:
            json.dump(report, file, indent=2, allow_nan=False)
            file.write("\n")
        print("REAL_SITE_QA_RECEIPT_VERIFIED")
        return 0
    except receipt.EvidenceError as exc:
        print(f"REAL_SITE_QA_RECEIPT_BLOCKED: {exc}", file=sys.stderr)
    except (KeyError, TypeError, ValueError, OSError, ImportError, TimeoutError, subprocess.SubprocessError):
        print("REAL_SITE_QA_RECEIPT_BLOCKED: input_or_collection_unavailable", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
