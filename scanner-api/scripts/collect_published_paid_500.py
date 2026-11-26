#!/usr/bin/env python3
"""Verify one named 500-page pilot through the published paid scanner."""

from __future__ import annotations

import argparse
import asyncio
import gzip
import hashlib
import hmac
import io
import json
import os
import re
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

SCANNER_ROOT = Path(__file__).resolve().parents[1]
if __name__ == "__main__":
    sys.path.insert(0, str(SCANNER_ROOT))
    from scripts import collect_staged_scan_receipts as receipt
    from scripts.export_staged_500_fixture import PAGES_PER_SECTION, SECTIONS
else:
    from . import collect_staged_scan_receipts as receipt
    from .export_staged_500_fixture import PAGES_PER_SECTION, SECTIONS

from app.scanner import final_url_identity

@dataclass(frozen=True)
class PaidCanary(receipt.Canary):
    page_cap: int = 500
    owner_user_id: str | None = None
    project_id: str | None = None
    target_url: str | None = None


APP_ID = "6a498732ec779dfaaeab0e53"
PUBLIC_ORIGIN = "https://getfixlist.com"
FIXTURE = "https://fixlist-staged-fixture-919035207432.europe-west1.run.app/"
QUEUE_PREFIX = "projects/seo-autopilot-501517/locations/europe-west1/queues/"
STAGE_QUEUE = QUEUE_PREFIX + "fixlist-scan-stages"
KNOWN_ADMINS = {"6a498da58ef5cec1f5cd4486", "6a498732ec779dfaaeab0e54"}
CONFIG_MAX_AGE_MS = 15 * 60 * 1000
CLOCK_SKEW_MS = 30_000
MAX_ARTIFACT_BYTES = 16 * 1024 * 1024
EMPTY_COHORT = hashlib.sha256(b"[]").hexdigest()
PREREQUISITE_VERSION = "published_paid_500_prerequisites_v1"
BROWSER_VERSION = "published_paid_500_browser_v1"
ACTIVATION_VERSION = "admission_published_500_pilot_snapshot_v1"
CLAIM_VERSION = "admission_claim_evidence_v1"
require, mapping, matches = receipt.require, receipt.mapping, receipt.matches
timestamp = receipt.parse_timestamp


def stable_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value):
    return hashlib.sha256(stable_json(value)).hexdigest()


def verify_signature(value, proof, key, label, code):
    require(matches(receipt.SHA256, proof), code)
    derived = hmac.new(key, label, hashlib.sha256).digest()
    require(hmac.compare_digest(proof, hmac.new(derived, stable_json(value), hashlib.sha256).hexdigest()), code)


def require_fields(document, expected, code):
    require(isinstance(document, dict) and all(
        key in document and type(document[key]) is type(value) and document[key] == value
        for key, value in expected.items()
    ), code)


def canonical_service(value, name):
    return isinstance(value, str) and re.fullmatch(
        rf"https://{re.escape(name)}-[a-z0-9]+(?:[.-][a-z0-9]+)*\.run\.app", value
    ) is not None


def validate_prerequisites(packet, expected, routes, operator_key, now):
    require_fields(packet, {"schema_version": PREREQUISITE_VERSION, "base44_app_id": APP_ID,
                            "source_sha": expected["source_sha"], "release_fingerprint": expected["fingerprint"]},
                   "paid_500_prerequisite_identity_mismatch")
    source, fingerprint = expected["source_sha"], expected["fingerprint"]
    owner = expected["owner_user_id"]
    require(matches(receipt.SOURCE_SHA, source) and matches(receipt.FINGERPRINT, fingerprint)
            and matches(receipt.OWNER_ID, owner) and owner not in KNOWN_ADMINS
            and all(matches(receipt.ID, expected[field]) for field in ("grant_id", "cohort_id", "release_id", "operator_id"))
            and matches(receipt.SHA256, expected["worker_config_sha256"]),
            "paid_500_expected_identity_invalid")
    cohort_digest = digest([owner])
    observed = timestamp(packet.get("observed_at"))
    require(now - CONFIG_MAX_AGE_MS <= observed <= now + CLOCK_SKEW_MS, "paid_500_prerequisite_stale")

    worker = mapping(packet.get("worker"))
    origin = worker.get("origin")
    require(canonical_service(origin, receipt.WORKER_SERVICE), "paid_500_worker_origin_invalid")
    stage_target = f"https://staged-{source[:12]}---{origin.removeprefix('https://')}"
    revision = worker.get("revision")
    require(matches(receipt.WORKER_REVISION, revision), "paid_500_worker_revision_invalid")
    require_fields(worker, {
        "service": receipt.WORKER_SERVICE, "source_sha": source, "release_fingerprint": fingerprint,
        "staged_config_sha256": expected["worker_config_sha256"], "ready": True,
        "pipeline_mode": "monolith", "stage_target": stage_target, "stage_tag_revision": revision,
        "stage_token_audience": origin, "stage_queue": STAGE_QUEUE, "workspace_bucket": receipt.BUCKET,
        "traffic": [{"revision": revision, "percent": 100}], "staged_owner_ids": "", "legacy_owner_ids": "",
    }, "paid_500_canonical_worker_mismatch")

    gateway = mapping(packet.get("gateway"))
    gateway_origin = gateway.get("origin")
    require(canonical_service(gateway_origin, "fixlist-dispatch-gateway"), "paid_500_gateway_origin_invalid")
    require_fields(gateway, {
        "ok": True, "service": "fixlist-dispatch-gateway", "source_sha": source, "worker_origin": origin,
        "staged_rollout_scope": "paid", "pipeline_mode": "staged", "canary_worker_origin": None,
        "staged_500_entitled_enabled": False, "staged_pilot_configuration_valid": True,
        "queue": QUEUE_PREFIX + "fixlist-standard150", "drain_queue": QUEUE_PREFIX + "fixlist-standard150-drain",
        "canary_owner_count": 0, "staged_owner_count": 0, "staged_owner_cohort_sha256": EMPTY_COHORT,
        "staged_pilot_owner_count": 1, "staged_pilot_owner_cohort_sha256": cohort_digest,
    }, "paid_500_gateway_mismatch")
    require(matches(re.compile(r"fixlist-dispatch-gateway-[a-z0-9-]{1,32}"), gateway.get("revision")),
            "paid_500_gateway_revision_invalid")

    intake = mapping(packet.get("intake"))
    launcher = routes["startStandardScanJobV9"]
    require_fields(intake, {
        "success": True, "schema_version": "fixlist_staged_v9_intake_readback_v1",
        "build_id": launcher["build_id"], "runtime_activation_id": launcher["runtime_activation_id"],
        "route_name": launcher["route_name"], "release_fingerprint": fingerprint,
        "configured_pipeline_mode": "staged", "staged_rollout_scope": "paid", "staged_500_entitled_enabled": False,
        "staged_pilot_owner_count": 1, "staged_pilot_owner_cohort_sha256": cohort_digest,
        "staged_owner_count": 0, "staged_owner_cohort_sha256": EMPTY_COHORT,
        "paid_dispatch_gateway_origin": gateway_origin, "intake_gate": "enabled", "admission_gate": "enabled",
    }, "paid_500_intake_mismatch")
    require(abs(timestamp(intake.get("observed_at")) - observed) <= CONFIG_MAX_AGE_MS, "paid_500_intake_stale")

    activation = mapping(packet.get("pilot_snapshot"))
    verify_signature({key: value for key, value in activation.items() if key != "proof"}, activation.get("proof"),
                     operator_key, b"fixlist-admission-drain-snapshot-v1", "paid_500_snapshot_signature_invalid")
    require_fields(activation, {"version": ACTIVATION_VERSION, "drain_ready": False, "operator_id": expected["operator_id"]}, "paid_500_snapshot_invalid")
    require(matches(receipt.ID, activation.get("snapshot_id"))
            and matches(receipt.ID, activation.get("operator_id")) and "counts" not in activation,
            "paid_500_snapshot_invalid")
    barrier = mapping(activation.get("barrier"))
    generation, sequence = barrier.get("generation"), barrier.get("claim_sequence")
    require_fields(barrier, {"mode": "open", "current_snapshot_id": activation["snapshot_id"]},
                   "paid_500_barrier_mismatch")
    require(receipt.positive(generation) and type(sequence) is int and sequence >= 0, "paid_500_barrier_invalid")
    boundary = mapping(mapping(activation.get("boundary")).get("published_500_pilot"))
    expiry = intake.get("public_pilot_expires_at")
    require_fields(boundary, {"state": "configured", "source_sha": source, "page_cap": 500, "expires_at": expiry,
                              "owner_count": 1, "owner_cohort_sha256": cohort_digest, "cohort_id": expected["cohort_id"],
                              "release_id": expected["release_id"], "required_launcher_build_id": launcher["build_id"]}, "paid_500_pilot_boundary_mismatch")
    created = activation.get("created_at")
    require(matches(receipt.ID, boundary.get("cohort_id")) and matches(receipt.ID, boundary.get("release_id"))
            and receipt.positive(created) and receipt.positive(expiry)
            and created * 1000 <= observed + CLOCK_SKEW_MS and now < expiry * 1000,
            "paid_500_pilot_boundary_stale")

    require_fields(packet.get("coordinator"), {
        "ok": True, "service": "fixlist-admission-coordinator", "source_sha": source,
        "claim_evidence_version": CLAIM_VERSION, "published_500_pilot_admission": True,
        "published_pilot_launcher_binding": True,
    }, "paid_500_coordinator_mismatch")

    account = mapping(packet.get("account"))
    require_fields(account, {"id": owner, "role": "user"}, "paid_500_account_mismatch")
    grants = packet.get("matching_grants")
    require(isinstance(grants, list) and len(grants) == 1, "paid_500_grant_ambiguous")
    grant = mapping(grants[0])
    address = account.get("email")
    require(isinstance(address, str) and 3 < len(address) <= 254 and "@" in address and address == address.strip().lower(),
            "paid_500_account_address_invalid")
    require_fields(grant, {"id": expected["grant_id"], "owner_user_id": owner, "user_email": address,
                           "page_cap": 500, "has_full_access": True, "access_status": "active",
                           "app_id": APP_ID, "plan_id": "standard150_lifetime"}, "paid_500_grant_mismatch")
    grant_source = grant.get("grant_source")
    require(grant_source in {"stripe_checkout", "manual_grant"}, "paid_500_grant_source_invalid")
    grant_date = grant.get("granted_at" if grant_source == "manual_grant" else "paid_at")
    require(timestamp(grant_date) <= observed + CLOCK_SKEW_MS
            and (grant_source == "manual_grant" or bool(str(grant.get("stripe_checkout_session_id") or "").strip())),
            "paid_500_grant_time_invalid")

    return {
        "observed": observed, "expiry": expiry, "boundary": boundary, "barrier": barrier,
        "gateway_revision": gateway["revision"], "snapshot_id": activation["snapshot_id"],
        "runtime": {"source_sha": source, "release_fingerprint": fingerprint, "service": receipt.WORKER_SERVICE,
                    "revision": revision, "staged_config_sha256": expected["worker_config_sha256"],
                    "pipeline_mode": worker["pipeline_mode"], "staged_owner_cohort_sha256": EMPTY_COHORT},
    }


def exact_target(url):
    return isinstance(url, str) and url.rstrip("/") + "/" == FIXTURE


def validate_browser(browser, run, context, expected, routes, claim_key, now):
    owner, source, fingerprint = expected["owner_user_id"], expected["source_sha"], expected["fingerprint"]
    scan, request, project, fix_list = (run.get(field) for field in ("id", "request_id", "project_id", "fix_list_id"))
    require(all(matches(receipt.ID, item) for item in (scan, request, project, fix_list)),
            "paid_500_saved_identifiers_invalid")
    start, complete, capture, reopened = (timestamp(value) for value in (
        run.get("started_at"), run.get("completed_at"), browser.get("observed_at"), browser.get("history_reopened_at")
    ))
    require(context["observed"] - CLOCK_SKEW_MS <= start < context["expiry"] * 1000
            and start < complete <= reopened <= capture <= now + CLOCK_SKEW_MS and complete - start <= 30 * 60 * 1000,
            "paid_500_browser_timing_mismatch")

    require_fields(run, {
        "owner_user_id": owner, "idempotency_key": request, "scan_mode": "standard_500", "page_cap": 500,
        "pipeline_mode": "staged", "beta_revision_fingerprint": fingerprint, "status": "complete",
        "pages_crawled": 500, "pages_planned": 500, "last_committed_batch": 9,
        "admission_release_state": "released", "release_gate_eligible": True,
        "admission_release_coordinator_request_id": request,
    }, "paid_500_saved_run_mismatch")
    require(receipt.positive(run.get("attempt_count")) and run["attempt_count"] < 2**31
            and exact_target(run.get("website_url"))
            and matches(receipt.SHA256, run.get("authority_proof")), "paid_500_saved_authority_mismatch")
    require(run.get("admission_release_outcome") in {"released", "already_released"}
            and start <= timestamp(run.get("admission_release_reconciled_at")) <= capture + CLOCK_SKEW_MS,
            "paid_500_admission_slot_release_mismatch")
    boundary, barrier = context["boundary"], context["barrier"]
    claim_sequence = run.get("admission_claim_sequence")
    require(receipt.positive(claim_sequence) and claim_sequence > barrier["claim_sequence"], "paid_500_claim_sequence_invalid")
    claim = {
        "version": CLAIM_VERSION, "owner_user_id": owner, "request_id": request,
        "barrier_generation": barrier["generation"], "claim_sequence": claim_sequence,
        "admission_mode": "acceptance_only", "acceptance_cohort_id": boundary["cohort_id"],
        "acceptance_release_id": boundary["release_id"], "acceptance_source_sha": source,
        "acceptance_expires_at": boundary["expires_at"],
    }
    require_fields(run, {**{f"admission_{field}": value for field, value in claim.items()
                            if field not in {"owner_user_id", "request_id", "version", "admission_mode"}},
                         "admission_mode": "acceptance_only", "admission_cohort_evidence_version": CLAIM_VERSION},
                   "paid_500_claim_mismatch")
    verify_signature(claim, run.get("admission_cohort_evidence_proof"), claim_key,
                     b"fixlist-admission-claim-evidence-v1", "paid_500_claim_signature_invalid")

    require_fields(browser, {
        "schema_version": BROWSER_VERSION, "source_sha": source, "owner_user_id": owner, "role": "user",
        "launch_url": PUBLIC_ORIGIN + "/onboarding", "launched_by_form": True, "displayed_page_cap": 500,
        "launch_route": routes["startStandardScanJobV9"]["route_name"], "refreshed_during_progress": True,
        "history_url": f"{PUBLIC_ORIGIN}/dashboard?scan_id={scan}", "reopened_from_history": True,
        "reopened_after_sign_in": True, "result_route": routes["getCustomerScanResultV9"]["route_name"],
    }, "paid_500_published_browser_journey_mismatch")
    require_fields(browser.get("options"), {
        "success": True, "version": "published_scan_options_v1", "launch": "pilot",
        "page_cap": 500, "release_fingerprint": fingerprint,
    }, "paid_500_published_options_mismatch")
    require_fields(browser.get("launch"), {
        "success": True, "accepted": True, "scan_id": scan, "request_id": request, "page_cap": 500,
        "scan_mode": "standard_500", "pipeline_mode": "staged",
    }, "paid_500_published_launch_mismatch")
    require(browser["launch"].get("status") in {"queued", "crawling"}, "paid_500_initial_launch_status_invalid")
    for field in ("saved_projection", "history_projection"):
        projection = mapping(browser.get(field))
        require_fields(projection, {
            "success": True, "access": "full", "authority_verified": True, "release_contract_current": True,
            "scan_id": scan, "fix_list_id": fix_list,
        }, "paid_500_published_report_mismatch")
        require_fields(projection.get("run"), {
            "id": scan, "project_id": project, "page_cap": 500, "scan_mode": "standard_500",
            "pipeline_mode": "staged", "status": "complete", "pages_crawled": 500, "pages_planned": 500,
            "started_at": run["started_at"], "completed_at": run["completed_at"],
            "beta_revision_fingerprint": fingerprint,
        }, "paid_500_published_report_run_mismatch")
        require(exact_target(projection["run"].get("website_url")), "paid_500_published_report_target_mismatch")

    return PaidCanary(scan, run["attempt_count"], hashlib.sha256(request.encode()).hexdigest(),
                       "complete", 500, 500, 10, context["observed"], start, complete, context["runtime"],
                       owner_user_id=owner, project_id=project, target_url=FIXTURE)


class PublishedReceiptStorage(receipt.ReceiptStorage):
    """Download bounded page artifacts using the verified generation as a precondition."""

    def _read_pinned(self, key, generation):
        from google.api_core.exceptions import NotFound, PreconditionFailed

        require(matches(receipt.GENERATION, generation), "paid_500_artifact_generation_invalid")
        blob = self.bucket.blob(key, generation=int(generation))
        try:
            blob.reload(timeout=receipt.READ_TIMEOUT_SECONDS, retry=None)
            require(receipt.positive(blob.size) and blob.size <= MAX_ARTIFACT_BYTES,
                    "paid_500_artifact_too_large")
            raw = blob.download_as_bytes(if_generation_match=int(generation), raw_download=True,
                                         timeout=receipt.READ_TIMEOUT_SECONDS, retry=None)
            require(len(raw) <= MAX_ARTIFACT_BYTES, "paid_500_artifact_too_large")
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as compressed:
                body = compressed.read(MAX_ARTIFACT_BYTES + 1)
            require(len(body) <= MAX_ARTIFACT_BYTES, "paid_500_artifact_too_large")
            return json.loads(body)
        except (NotFound, PreconditionFailed) as exc:
            raise receipt.EvidenceError("paid_500_artifact_changed") from exc
        except (OSError, ValueError) as exc:
            if isinstance(exc, receipt.EvidenceError):
                raise
            raise receipt.EvidenceError("paid_500_artifact_read_failed") from exc

    async def read_pinned(self, key, generation):
        async with self.requests:
            return await asyncio.to_thread(self._read_pinned, key, generation)


class GenerationReadback:
    """Share the exact generation values verified by the existing receipt collector."""

    def __init__(self, storage):
        self.storage = storage
        self.values = {}

    async def read(self, key):
        return await self.storage.read(key)

    async def generation(self, key):
        generation = await self.storage.generation(key)
        self.values[key] = generation
        return generation


FIXTURE_URLS = {FIXTURE} | {
    f"{FIXTURE}{section}/{number}.html"
    for section in SECTIONS for number in range(PAGES_PER_SECTION)
}


def fixture_page_urls(document, count):
    pages = mapping(document).get("pages")
    require(isinstance(pages, list) and len(pages) == count, "paid_500_fixture_page_count_mismatch")
    urls = set()
    for raw_page in pages:
        page = mapping(raw_page)
        url = final_url_identity(page.get("final_url") or page.get("url"))
        require(url in FIXTURE_URLS and type(page.get("status_code")) is int and page["status_code"] == 200
                and final_url_identity(page.get("canonical")) == url, "paid_500_fixture_page_invalid")
        require(url not in urls, "paid_500_fixture_duplicate_page")
        urls.add(url)
    return urls


async def collect_published_receipts(canary, run, storage):
    tracked = GenerationReadback(storage)
    evidence = await receipt.collect(canary, tracked)
    require(evidence["receipt_evidence_verified"] is True,
            "paid_500_worker_receipts_unverified:" + ",".join(evidence["unverified"]))
    prefix = receipt.attempt_prefix(canary.scan_id, canary.attempt)

    async def read_artifact(path):
        key = prefix + path
        return await storage.read_pinned(key, tracked.values[key])

    async def read_unchanged_frontier():
        frontier = await storage.read(prefix + "frontier.json")
        require(frontier is not None and str(frontier.generation) == evidence["frontier_generation"],
                "paid_500_frontier_changed")
        tombstone = "deleted/" + "/".join(prefix.split("/")[:2]) + "/"
        require(await storage.read(tombstone) is None, "workspace_deleted")
        return frontier

    frontier = await read_unchanged_frontier()
    _, _, artifacts = receipt.frontier_layout(canary, frontier.value)
    plan = mapping(await read_artifact("plan.json"))
    request = run["request_id"]
    job = mapping(plan.get("job"))
    require_fields(job, {
        "scan_id": canary.scan_id, "attempt_count": canary.attempt, "request_id": request,
        "idempotency_key": request, "project_id": run["project_id"], "owner_user_id": run["owner_user_id"],
        "scan_mode": "standard_500", "page_cap": 500, "pipeline_mode": "staged",
    }, "paid_500_plan_identity_mismatch")
    require(exact_target(job.get("website_url")) and mapping(plan.get("state")).get("pages") == [],
            "paid_500_plan_initial_state_mismatch")

    previous = set()
    for batch, (_, page_path) in enumerate(artifacts, start=1):
        current = fixture_page_urls(await read_artifact(page_path), batch * 50)
        require(previous < current, "paid_500_batch_page_set_changed")
        previous = current
    result = await read_artifact("result.json.gz")
    require_fields(result, {
        "success": True, "scan_id": canary.scan_id, "request_id": request, "idempotency_key": request,
        "submitted_url": job["website_url"], "scan_mode": "standard_500", "pipeline_mode": "staged",
        "pipeline_limited": False, "page_cap": 500, "pages_crawled": 500,
        "beta_revision_fingerprint": canary.runtime["release_fingerprint"],
    }, "paid_500_worker_result_identity_mismatch")
    require(fixture_page_urls(result, 500) == previous, "paid_500_worker_result_pages_mismatch")
    await read_unchanged_frontier()
    return {**evidence, "verified_committed_batch_sizes": [50] * len(artifacts),
            "checked_distinct_page_count": len(previous), "checked_fixture_page_set_sha256": digest(sorted(previous))}


def read_file(path, limit, *, private=False):
    require(path.is_absolute() and path.resolve(strict=True) == path, "paid_500_input_path_invalid")
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as file:
        mode = os.fstat(file.fileno()).st_mode
        require(stat.S_ISREG(mode) and (not private or stat.S_IMODE(mode) & 0o077 == 0),
                "paid_500_input_permissions_invalid")
        result = file.read(limit + 1)
        require(0 < len(result) <= limit, "paid_500_input_size_invalid")
        return result


def read_packet(path):
    document = json.loads(read_file(path, receipt.MAX_CANARY_BYTES, private=True))
    require(isinstance(document, dict), "paid_500_input_invalid")
    return document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected", type=Path, required=True)
    parser.add_argument("--prerequisites", type=Path, required=True)
    parser.add_argument("--operator-key-file", type=Path, required=True)
    command = parser.add_subparsers(dest="command", required=True)
    command.add_parser("prerequisites", help="Verify the captured readbacks without contacting cloud services")
    collect = command.add_parser("collect", help="Verify an already completed published browser run and read its receipts")
    collect.add_argument("--browser", type=Path, required=True)
    collect.add_argument("--saved-run", type=Path, required=True)
    collect.add_argument("--claim-key-file", type=Path, required=True)
    collect.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        expected = read_packet(args.expected)
        packet = read_packet(args.prerequisites)
        snapshot_key = read_file(args.operator_key_file, 4096, private=True)
        repo = SCANNER_ROOT.parent
        source = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, check=True,
                                text=True, timeout=5).stdout.strip()
        local_fingerprint = json.loads((repo / "data/beta-crawler-revision.json").read_text())["fingerprint"]
        require(expected["source_sha"] == source and expected["fingerprint"] == local_fingerprint,
                "paid_500_checkout_identity_mismatch")
        routes = json.loads((repo / "data/generated-staged-v9-routes.json").read_text())["functions"]
        now = time.time_ns() // 1_000_000
        if args.command == "prerequisites":
            validate_prerequisites(packet, expected, routes, snapshot_key, now)
            print("PUBLISHED_PAID_500_PREREQUISITES_MATCH")
            return 0

        browser, run = read_packet(args.browser), read_packet(args.saved_run)
        claim_key = read_file(args.claim_key_file, 4096, private=True)
        require(not hmac.compare_digest(snapshot_key, claim_key), "paid_500_signing_keys_not_distinct")
        context = validate_prerequisites(packet, expected, routes, snapshot_key, timestamp(run.get("started_at")))
        canary = validate_browser(browser, run, context, expected, routes, claim_key, now)
        output = args.output
        require(output.is_absolute() and output.parent.resolve(strict=True) == output.parent
                and not output.is_relative_to(SCANNER_ROOT.parent) and not output.exists(),
                "paid_500_output_path_invalid")
        require(not os.getenv("STORAGE_EMULATOR_HOST"), "workspace_emulator_refused")
        from google.cloud import storage

        reader = PublishedReceiptStorage(storage.Client().bucket(receipt.BUCKET))
        evidence = asyncio.run(asyncio.wait_for(collect_published_receipts(canary, run, reader),
                                               receipt.COLLECTION_TIMEOUT_SECONDS))
        report = {
            "schema_version": "published_paid_500_receipt_evidence_v1",
            "scope": "named_customer_fixture",
            "public_500_release_approved": False,
            "prerequisite_capture_sha256": digest(packet), "browser_capture_sha256": digest(browser),
            "saved_run_capture_sha256": digest(run), "scan_id": canary.scan_id, "attempt_count": canary.attempt,
            "source_sha": expected["source_sha"], "release_fingerprint": expected["fingerprint"],
            "gateway_revision": context["gateway_revision"], "worker_runtime": canary.runtime,
            "coordinator_snapshot_id": context["snapshot_id"], "barrier_generation": context["barrier"]["generation"],
            "workspace_bucket": receipt.BUCKET, "page_cap": 500, "terminal_status": "complete",
            **evidence,
        }
        with os.fdopen(os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600), "w") as file:
            json.dump(report, file, indent=2, allow_nan=False)
            file.write("\n")
        print("PUBLISHED_PAID_500_RECEIPTS_VERIFIED")
        return 0
    except receipt.EvidenceError as exc:
        print(f"PUBLISHED_PAID_500_BLOCKED: {exc}", file=sys.stderr)
    except (OSError, ValueError, TypeError, KeyError, ImportError, TimeoutError, subprocess.SubprocessError):
        print("PUBLISHED_PAID_500_BLOCKED: input_or_collection_unavailable", file=sys.stderr)
    except Exception:
        print("PUBLISHED_PAID_500_BLOCKED: private_receipts_unavailable", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
