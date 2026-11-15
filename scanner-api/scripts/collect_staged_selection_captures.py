#!/usr/bin/env python3
"""Capture selector inputs from the private plans of 50 attested corpus attempts."""

from __future__ import annotations

import argparse
import asyncio
import gzip
import hashlib
import io
import json
import os
import re
import stat
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

SCANNER_ROOT = Path(__file__).resolve().parents[1]
if __name__ == "__main__":
    sys.path.insert(0, str(SCANNER_ROOT))

from app.workspace import attempt_prefix
from scripts import collect_staged_scan_receipts as receipts
from scripts.collect_staged_scan_receipts import EvidenceError, mapping, matches, require

SCHEMA_VERSION = "staged_scan_selection_captures_v1"
SITE_ID = re.compile(r"[A-Za-z0-9_-]{1,80}")
MARKET_HINT = re.compile(r"(?:/[a-z]{2}(?:-[a-z]{2})?){0,2}")
PRIVATE_QUERY_KEY = re.compile(
    r"^(?:x-amz-|x-goog-)|(?:token|secret|password|passwd|credential|signature|session|api[-_]?key|access[-_]?key|jwt|oauth)"
    r"|^(?:auth|authorization|key|sig|sso)$",
    re.I,
)
REFERENCES = {"funbooker", "pretto", "center_street_lending", "norris_wines"}
SITE_CLASSES = {"ecommerce", "content", "local", "mixed"}
EXPECTATIONS = {"complete_500", "complete_below_cap", "throttled_limited"}
MAX_PLAN_COMPRESSED = 16 * 1024 * 1024
MAX_PLAN_BYTES = 64 * 1024 * 1024
MAX_CAPTURE_BYTES = 64 * 1024 * 1024
MAX_URLS = 5000
CORPUS_TIMEOUT_SECONDS = 900


@dataclass(frozen=True)
class JournalAttempt:
    site: dict
    report: dict
    evidence: dict
    canary: receipts.Canary


def read_document(path: Path, *, private: bool) -> tuple[dict, str]:
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    with os.fdopen(os.open(path, flags), "rb") as stream:
        mode = os.fstat(stream.fileno()).st_mode
        require(stat.S_ISREG(mode) and (not private or mode & 0o077 == 0), "local_evidence_path_invalid")
        raw = stream.read(receipts.MAX_CANARY_BYTES + 1)
    require(len(raw) <= receipts.MAX_CANARY_BYTES, "local_evidence_too_large")
    value = json.loads(raw)
    require(isinstance(value, dict), "local_evidence_invalid")
    return value, hashlib.sha256(raw).hexdigest()


def safe_url(value: Any, *, https_required: bool = False, relative_allowed: bool = False) -> str:
    require(isinstance(value, str) and 0 < len(value) <= 8192
            and not re.search(r"[\x00-\x20\x7f\\#]", value), "capture_url_invalid")
    url = urlsplit(value)
    relative = not (url.scheme or url.netloc) and relative_allowed
    require(relative or (url.scheme in ({"https"} if https_required else {"https", "http"})
            and url.hostname and not url.username and url.password is None and "@" not in url.netloc),
            "capture_url_invalid")
    for key, _ in parse_qsl(url.query, keep_blank_values=True, max_num_fields=128):
        require(not PRIVATE_QUERY_KEY.search(key), "capture_url_sensitive")
    return "" if relative else url.hostname.removeprefix("www.").rstrip(".")


def reviewed_manifest(manifest: dict) -> tuple[int, int]:
    require(manifest.get("schema_version") == "staged_scan_corpus_v1"
            and matches(receipts.SOURCE_SHA, manifest.get("source_sha"))
            and matches(receipts.FINGERPRINT, manifest.get("release_fingerprint")), "corpus_identity_invalid")
    reviewer = manifest.get("reviewed_by")
    reviewed, expires = (receipts.parse_timestamp(manifest.get(key)) for key in ("reviewed_at", "expires_at"))
    require(isinstance(reviewer, str) and reviewer.strip() and reviewed <= time.time_ns() // 1_000_000
            and 0 < expires - reviewed <= 86_400_000, "corpus_review_invalid")
    sites = manifest.get("sites")
    require(isinstance(sites, list) and len(sites) == 50, "corpus_requires_50_sites")
    hosts, markers, classes, expectations = [], [], set(), set()
    for site in sites:
        require(isinstance(site, dict) and matches(SITE_ID, site.get("site_id"))
                and matches(receipts.OWNER_ID, site.get("owner_user_id"))
                and matches(receipts.ID, site.get("project_id"))
                and matches(receipts.ID, site.get("request_id"))
                and len(site["request_id"]) >= 8, "corpus_site_identity_invalid")
        hosts.append(safe_url(site.get("target_url"), https_required=True))
        require(site.get("site_class") in SITE_CLASSES and site.get("expectation") in EXPECTATIONS,
                "corpus_site_class_or_expectation_invalid")
        require("reference_marker" in site and (site["reference_marker"] is None
                or site["reference_marker"] in REFERENCES), "corpus_reference_invalid")
        if site["reference_marker"] is not None:
            markers.append(site["reference_marker"])
        classes.add(site["site_class"])
        expectations.add(site["expectation"])
    require(len(set(hosts)) == 50 and all(len({site[key] for site in sites}) == 50
            for key in ("site_id", "project_id", "request_id")), "corpus_sites_not_distinct")
    require(len(markers) == len(REFERENCES) and set(markers) == REFERENCES and classes == SITE_CLASSES
            and "throttled_limited" in expectations, "corpus_coverage_invalid")
    return reviewed, expires


def attest_local_attempt(
    site: dict, manifest: dict, manifest_sha: str, window: tuple[int, int], journal: Path,
    input_digests: dict[Path, str],
) -> JournalAttempt:
    def read(kind: str) -> tuple[dict, str]:
        file = journal / (site["site_id"] + "." + kind + ".json")
        value, digest = read_document(file, private=True)
        input_digests[file] = digest
        return value, digest

    started, _ = read("started")
    finished, _ = read("finished")
    report, report_sha = read("report")
    evidence, evidence_sha = read("receipt")
    canary = receipts.canary_identity(report)
    for marker in (started, finished):
        require(marker.get("manifest_sha256") == manifest_sha and marker.get("site_id") == site["site_id"]
                and marker.get("request_id") == site["request_id"], "corpus_journal_attempt_mismatch")
    started_ms, finished_ms = (receipts.parse_timestamp(marker.get("observed_at")) for marker in (started, finished))
    provenance = report["provenance"]
    require(window[0] <= started_ms < window[1]
            and started_ms <= canary.observed_ms <= finished_ms
            and canary.completed_ms <= finished_ms + 30_000, "corpus_journal_attempt_time_invalid")
    # A reconciled receipt may be collected after a successful runner exit.
    # Its summary is still bound to the report digest and verified afresh below.
    require(type(finished.get("exit_code")) is int and finished["exit_code"] == 0
            and "exit_signal" in finished and finished["exit_signal"] is None
            and finished.get("report_sha256") == report_sha and "receipt_sha256" in finished
            and finished["receipt_sha256"] in (None, evidence_sha)
            and started.get("prerequisite_sha256") == provenance["prerequisite_sha256"],
            "corpus_journal_evidence_changed")
    require(all(report.get(key) == site[key] for key in ("project_id", "request_id", "target_url"))
            and report.get("expected_owner_user_id") == site["owner_user_id"]
            and all(report.get(key) == manifest[key] for key in ("source_sha", "release_fingerprint")),
            "corpus_scan_report_identity_mismatch")
    expected = site["expectation"]
    if expected == "throttled_limited":
        require(canary.terminal_status == "limited" and report.get("outcome") == "limited_throttled",
                "corpus_scan_outcome_mismatch")
    elif expected == "complete_below_cap":
        sampling = mapping(report.get("selection_coverage"))
        require(canary.terminal_status == "complete" and canary.pages == canary.planned < 500
                and report.get("outcome") == "complete" and report.get("functional_500_verified") is False
                and sampling.get("pages_checked") == canary.planned and sampling.get("inventory_capped") is False
                and type(sampling.get("inventory_urls")) is int and 0 <= sampling["inventory_urls"] < 500
                and matches(receipts.SHA256, sampling.get("sections_sha256")), "corpus_scan_outcome_mismatch")
    else:
        require(canary.terminal_status == "complete" and canary.pages == 500
                and report.get("outcome") == "complete" and report.get("functional_500_verified") is True,
                "corpus_scan_outcome_mismatch")
    header = {
        "schema_version": receipts.EVIDENCE_VERSION, "production_freeze": False,
        "canary_report_sha256": report_sha, "scan_id": canary.scan_id, "attempt_count": canary.attempt,
        "source_sha": manifest["source_sha"], "release_fingerprint": manifest["release_fingerprint"],
        "worker_revision": canary.runtime["revision"], "workspace_bucket": receipts.BUCKET,
        "prerequisite_sha256": provenance["prerequisite_sha256"], "terminal_status": canary.terminal_status,
    }
    require(all(evidence.get(key) == value for key, value in header.items())
            and evidence.get("production_freeze") is False and type(evidence.get("attempt_count")) is int
            and evidence.get("receipt_evidence_verified") is True and evidence.get("worker_runtime_verified") is True
            and evidence.get("unverified") == [] and matches(receipts.GENERATION, evidence.get("frontier_generation"))
            and matches(receipts.SHA256, evidence.get("receipt_snapshot_sha256")), "corpus_receipt_identity_mismatch")
    return JournalAttempt(site, report, evidence, canary)


class CaptureStorage(receipts.ReceiptStorage):
    """Download a bounded plan only when its current generation matches the receipt."""

    async def read_pinned_plan(self, key: str, generation: str) -> dict:
        async with self.requests:
            return await asyncio.to_thread(self._read_pinned_plan, key, generation)

    def _read_pinned_plan(self, key: str, generation: str) -> dict:
        from google.api_core.exceptions import NotFound, PreconditionFailed

        blob = self.bucket.blob(key)
        try:
            blob.reload(timeout=receipts.READ_TIMEOUT_SECONDS, retry=None)
            require(str(blob.generation) == generation, "plan_generation_changed")
            require(receipts.positive(blob.size) and blob.size <= MAX_PLAN_COMPRESSED, "plan_too_large")
            raw = blob.download_as_bytes(if_generation_match=int(generation), raw_download=True,
                                         timeout=receipts.READ_TIMEOUT_SECONDS, retry=None)
            require(len(raw) <= MAX_PLAN_COMPRESSED, "plan_too_large")
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as compressed:
                content = compressed.read(MAX_PLAN_BYTES + 1)
            require(len(content) <= MAX_PLAN_BYTES, "plan_too_large")
            plan = json.loads(content)
            require(isinstance(plan, dict), "plan_invalid")
            return plan
        except (NotFound, PreconditionFailed) as exc:
            raise EvidenceError("plan_generation_changed") from exc
        except EvidenceError:
            raise
        except Exception as exc:
            raise EvidenceError("plan_read_unavailable") from exc


class AttestedPlanReader:
    def __init__(self, storage: Any, key: str):
        self.storage = storage
        self.plan_key = key
        self.plan_generation = None

    async def read(self, key: str):
        return await self.storage.read(key)

    async def generation(self, key: str):
        generation = await self.storage.generation(key)
        if key == self.plan_key:
            self.plan_generation = generation
        return generation


def capture_fields(attempt: JournalAttempt, plan: dict) -> dict:
    canary, site = attempt.canary, attempt.site
    job, state = mapping(plan.get("job")), mapping(plan.get("state"))
    require(job.get("scan_id") == canary.scan_id and type(job.get("attempt_count")) is int
            and job["attempt_count"] == canary.attempt and job.get("scan_mode") == "standard_500"
            and job.get("page_cap") == 500 and job.get("website_url") == site["target_url"]
            and all(job.get(key) == site[key] for key in ("owner_user_id", "request_id", "project_id")),
            "plan_attempt_identity_mismatch")
    start = state.get("start_url")
    require(state.get("checkpoint_version") == "scan_state_v1_wall_clock"
            and state.get("scan_mode") == "standard_500" and state.get("job_mode") is True
            and state.get("max_pages") == 500 and start == site["target_url"], "plan_state_identity_mismatch")
    stamp = state.get("selection_captured_at")
    market = state.get("selection_preferred_market")
    require(isinstance(stamp, str) and stamp and matches(MARKET_HINT, market), "plan_exact_selector_inputs_missing")
    captured = datetime.fromisoformat(stamp)
    selection_ms = receipts.parse_timestamp(stamp)
    began = receipts.parse_timestamp(state.get("scan_started_wall_clock"))
    require(canary.started_ms - 30_000 <= began <= selection_ms <= canary.completed_ms + 30_000,
            "plan_selector_time_invalid")
    sitemap, links = (state.get(field) for field in ("sitemap_urls", "homepage_links"))
    require(all(isinstance(values, list) and len(values) <= MAX_URLS for values in (sitemap, links)),
            "plan_inventory_invalid")
    expected_host = safe_url(start, https_required=True)
    for urls, relative_allowed in ((sitemap, True), (links, False)):
        for url in urls:
            host = safe_url(url, relative_allowed=relative_allowed)
            require(not host or host == expected_host, "plan_inventory_origin_mismatch")
        require(len(set(urls)) == len(urls), "plan_inventory_invalid")
    diagnostics = state.get("sitemap_diagnostics")
    require(isinstance(diagnostics, dict), "plan_inventory_invalid")
    dates, capped = diagnostics.get("sitemap_lastmod", {}), diagnostics.get("inventory_capped", False)
    require(isinstance(dates, dict) and dates.keys() <= set(sitemap)
            and all(isinstance(value, str) and 0 < len(value) <= 128 for value in dates.values())
            and type(capped) is bool, "plan_inventory_invalid")
    # The importance scorer ignores unparseable lastmod strings. Preserve only
    # its effective dates so arbitrary sitemap text cannot escape the plan.
    valid_dates = {}
    for url, value in dates.items():
        try:
            date = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            if date.tzinfo is not None:
                date.astimezone(timezone.utc)
        except (ValueError, OverflowError):
            continue
        valid_dates[url] = value
    return {
        "site_id": site["site_id"], "start_url": start, "captured_at": captured.astimezone(timezone.utc).isoformat(),
        "sitemap_urls": sitemap, "homepage_links": links, "sitemap_lastmod": valid_dates,
        "preferred_market": market, "inventory_capped": capped,
        "terminal_anchor": {
            "scan_id": canary.scan_id, "attempt_count": canary.attempt,
            "frontier_generation": attempt.evidence["frontier_generation"],
            "receipt_snapshot_sha256": attempt.evidence["receipt_snapshot_sha256"],
        },
    }


async def capture_attempt(attempt: JournalAttempt, storage: Any) -> dict:
    prefix = attempt_prefix(attempt.canary.scan_id, attempt.canary.attempt)
    plan_key, frontier_key = prefix + "plan.json", prefix + "frontier.json"
    tombstone = "deleted/" + "/".join(prefix.split("/")[:2]) + "/"
    reader = AttestedPlanReader(storage, plan_key)
    fresh = await receipts.collect(attempt.canary, reader)
    require(fresh["receipt_evidence_verified"] is True
            and json.dumps(fresh, sort_keys=True) == json.dumps({
                key: attempt.evidence.get(key) for key in fresh
            }, sort_keys=True), "corpus_receipt_snapshot_changed")
    generation = reader.plan_generation
    require(matches(receipts.GENERATION, generation), "plan_generation_unverified")
    plan = await storage.read_pinned_plan(plan_key, generation)
    plan_generation, frontier_generation, deletion = await asyncio.gather(
        storage.generation(plan_key), storage.generation(frontier_key), storage.read(tombstone),
    )
    require(deletion is None and plan_generation == generation
            and frontier_generation == fresh["frontier_generation"], "workspace_changed_during_capture")
    return capture_fields(attempt, plan)


def load_journal(manifest_path: Path, journal: Path) -> tuple[str, list[JournalAttempt], dict[Path, str]]:
    manifest, manifest_sha = read_document(manifest_path, private=False)
    window = reviewed_manifest(manifest)
    lock = journal / ".corpus.lock"
    require(not os.path.lexists(lock), "corpus_journal_locked")
    manifest_marker = journal / "manifest.sha256.json"
    binding, digest = read_document(manifest_marker, private=True)
    require(binding.get("manifest_sha256") == manifest_sha, "corpus_manifest_digest_mismatch")
    inputs = {manifest_path: manifest_sha, manifest_marker: digest}
    attempts = [attest_local_attempt(site, manifest, manifest_sha, window, journal, inputs)
                for site in manifest["sites"]]
    require(len({attempt.canary.scan_id for attempt in attempts}) == 50, "corpus_scan_ids_not_distinct")
    return manifest_sha, attempts, inputs


async def capture_all(attempts: list[JournalAttempt], storage: Any) -> list[dict]:
    captures = []
    total = 0
    for attempt in attempts:
        result = await asyncio.wait_for(capture_attempt(attempt, storage), receipts.COLLECTION_TIMEOUT_SECONDS)
        total += len(json.dumps(result, separators=(",", ":"), allow_nan=False))
        require(total < MAX_CAPTURE_BYTES, "capture_output_too_large")
        captures.append(result)
    return captures


def publish_private(output: Path, contents: dict) -> None:
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(contents, stream, separators=(",", ":"), allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
            os.link(temporary, output)
        finally:
            temporary.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--evidence-dir", dest="journal", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        require(args.manifest.is_absolute() and args.manifest.resolve(strict=True) == args.manifest
                and args.journal.is_absolute() and args.journal.is_dir()
                and args.journal.resolve(strict=True) == args.journal, "input_path_invalid")
        output = args.output
        require(output.is_absolute() and output.parent.is_dir()
                and output.parent.resolve(strict=True) == output.parent
                and not any((parent / ".git").exists() for parent in output.parents)
                and not output.is_relative_to(SCANNER_ROOT.parent)
                and not os.path.lexists(output), "output_path_invalid")
        manifest_sha, attempts, inputs = load_journal(args.manifest, args.journal)
        require(not os.getenv("STORAGE_EMULATOR_HOST"), "workspace_emulator_refused")
        from google.cloud import storage

        reader = CaptureStorage(storage.Client().bucket(receipts.BUCKET))
        sites = asyncio.run(asyncio.wait_for(capture_all(attempts, reader), CORPUS_TIMEOUT_SECONDS))
        require(not os.path.lexists(args.journal / ".corpus.lock"), "corpus_journal_locked")
        for path, digest in inputs.items():
            _, actual = read_document(path, private=path != args.manifest)
            require(actual == digest, "corpus_journal_evidence_changed")
        publish_private(output, {"schema_version": SCHEMA_VERSION,
                                 "corpus_manifest_sha256": manifest_sha, "sites": sites})
        print("STAGED_SELECTION_CAPTURES_SAVED count=50")
        return 0
    except EvidenceError as exc:
        print(f"STAGED_SELECTION_CAPTURES_BLOCKED: {exc}", file=sys.stderr)
    except Exception:
        print("STAGED_SELECTION_CAPTURES_BLOCKED: input_output_or_workspace_unavailable", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
