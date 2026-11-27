#!/usr/bin/env python3
"""Check the private real-site QA register against one approved release."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import stat
import subprocess
import sys
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

SCANNER_ROOT = Path(__file__).resolve().parents[1]
if __name__ == "__main__":
    sys.path.insert(0, str(SCANNER_ROOT))

from scripts import collect_real_site_scan_receipt as real
from scripts import collect_staged_scan_receipts as receipt
from scripts.collect_published_paid_500 import digest, require_fields

COUNTS = (
    "discovered_url_count", "checked_distinct_url_count", "usable_html_count",
    "planned_page_count", "committed_batch_count", "duration_seconds",
)
REVIEW_COUNTS = (
    "critical_group_count", "critical_groups_reviewed", "critical_false_positive_count", "critical_unresolved_count",
    "high_group_count", "high_groups_reviewed", "high_false_positive_count", "high_unresolved_count",
    "lower_priority_groups_sampled", "passed_pages_sampled", "missed_seeded_defect_count",
)
REVIEW_FILES = (
    "class_evidence_ref", "checked_url_manifest_ref", "discovered_url_manifest_ref",
    "finding_review_evidence_ref", "sample_method_ref", "seeded_control_evidence_ref",
)
CLASS_FIELDS = {
    "multilingual": "multilingual_evidence_status",
    "javascript_search_or_forms": "javascript_search_or_forms_evidence_status",
    "store_locator": "store_locator_evidence_status",
    "conventional_html": "conventional_html_evidence_status",
}
REVIEWED_FIELDS = (
    *REVIEW_COUNTS, *CLASS_FIELDS.values(), "inventory_current_verification_status",
    "critical_high_review_status", "accuracy_verdict", "independent_audit_status",
    "independent_audit_verdict", "tier_acceptance_verdict",
)
REQUIRED_FIELDS = frozenset({
    "register_version", "site_slot", "row_id", "target_url", "planned_scan_mode", "planned_page_cap",
    "current_authorization_ref", "current_authorization_expires_at", "actual_owner_project_binding_evidence_ref",
    "stage_receipt_evidence_ref", "independent_audit_evidence_ref", "primary_reviewer", "independent_auditor",
    "critical_high_review_status", "independent_audit_status", "accuracy_verdict", "independent_audit_verdict",
    "tier_acceptance_verdict", "planned_candidate_source_sha", "actual_source_sha", "actual_release_fingerprint",
    "planned_worker_revision", "actual_worker_revision", "actual_scan_id", "actual_scan_mode", "actual_submitted_page_cap",
    "run_status", "terminal_outcome", "saved_report_url", "inventory_capped", "rate_limit_observed",
    "inventory_current_verification_status", *CLASS_FIELDS.values(), *COUNTS, *REVIEW_COUNTS, *REVIEW_FILES,
})
MAX_FILE_BYTES = 16 * 1024 * 1024
SLOTS = [f"S{index:02}" for index in range(1, 21)]
require, mapping, matches, positive = receipt.require, receipt.mapping, receipt.matches, receipt.positive


def read_bounded(path):
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW), "rb") as file:
        require(stat.S_ISREG(os.fstat(file.fileno()).st_mode), "evidence_unavailable")
        data = file.read(MAX_FILE_BYTES + 1)
    require(0 < len(data) <= MAX_FILE_BYTES, "evidence_size_invalid")
    return data


def evidence_file(directory, row, field):
    require(bool(row[field].strip()), "evidence_reference_missing")
    path = (directory / row[field]).resolve(strict=True)
    require(path.is_relative_to(directory) and path != directory, "evidence_outside_private_directory")
    return read_bounded(path)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def json_object(data):
    value = json.loads(data)
    require(isinstance(value, dict), "evidence_document_invalid")
    return value


def manifest_rows(raw):
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
    fields = reader.fieldnames or []
    require(REQUIRED_FIELDS <= set(fields) and len(fields) == len(set(fields)), "register_columns_invalid")
    rows = list(reader)
    require(len(rows) == 40 and all(None not in row and all(value is not None for value in row.values())
                                   for row in rows), "register_pairs_invalid")
    by_id = {row["row_id"]: row for row in rows}
    require(len(by_id) == 40, "register_pairs_invalid")
    hosts = set()
    for slot in SLOTS:
        targets = []
        for cap in (150, 500):
            row = by_id.get(f"{slot}-{cap}", {})
            require_fields(row, {
                "register_version": "real_site_qa_register_v1", "site_slot": slot,
                "planned_page_cap": str(cap), "planned_scan_mode": f"standard_{cap}",
            }, "register_pairs_invalid")
            targets.append(row["target_url"])
        require(targets[0] == targets[1], "register_pair_target_mismatch")
        hosts.add(real.url_parts(targets[0])[0].removeprefix("www."))
    require(len(hosts) == 20, "register_hosts_not_distinct")
    return by_id


def verify_run(row, captured, snapshot, *, cap, source, fingerprint, result_route):
    scope, runtime, run, browser = (mapping(captured.get(name)) for name in (
        "approved_scope", "worker_runtime", "saved_run", "browser",
    ))
    scan = row["actual_scan_id"]
    require(matches(receipt.ID, scan), "scan_identity_missing")
    require_fields(scope, {"row_id": row["row_id"], "page_cap": cap, "target_url": row["target_url"],
                           "expected_outcome": row["terminal_outcome"]}, "captured_scope_mismatch")
    require_fields(runtime, {"source_sha": source, "release_fingerprint": fingerprint,
                             "revision": row["actual_worker_revision"]}, "captured_runtime_mismatch")
    require_fields(run, {
        "id": scan, "owner_user_id": scope.get("owner_user_id"), "project_id": scope.get("project_id"),
        "website_url": scope["target_url"], "page_cap": cap, "scan_mode": f"standard_{cap}",
        "pipeline_mode": "staged", "status": row["run_status"], "beta_revision_fingerprint": fingerprint,
        "admission_release_state": "released",
    }, "captured_run_mismatch")
    require(positive(run.get("attempt_count")) and matches(receipt.OWNER_ID, scope.get("owner_user_id"))
            and matches(receipt.ID, scope.get("project_id")), "captured_run_mismatch")
    require_fields(browser, {
        "owner_user_id": scope["owner_user_id"], "role": "user", "result_route": result_route,
        "history_url": f"https://getfixlist.com/dashboard?scan_id={scan}",
    }, "captured_history_mismatch")
    require(row["saved_report_url"] == browser["history_url"], "saved_report_reference_mismatch")
    require_fields(snapshot, {
        "source_sha": source, "release_fingerprint": fingerprint, "scan_id": scan,
        "attempt_count": run["attempt_count"], "page_cap": cap, "terminal_status": run["status"],
        "terminal_outcome": row["terminal_outcome"], "worker_revision": row["actual_worker_revision"],
    }, "receipt_release_or_attempt_mismatch")
    require(row["planned_worker_revision"] == snapshot["worker_revision"]
            and matches(receipt.WORKER_REVISION, snapshot["worker_revision"])
            and row["actual_submitted_page_cap"] == str(cap) and row["actual_scan_mode"] == f"standard_{cap}"
            and run["status"] in {"complete", "limited"} and snapshot["terminal_outcome"] in real.OUTCOMES,
            "register_attempt_mismatch")
    stamp = receipt.parse_timestamp
    start, end = stamp(run.get("started_at")), stamp(run.get("completed_at"))
    expires = stamp(scope.get("authorized_until"))
    require(stamp(scope.get("authorized_from")) <= start < end <= expires
            and expires == stamp(row["current_authorization_expires_at"]), "approved_window_mismatch")
    prefixes, path = scope.get("allowed_url_prefixes"), scope.get("path_prefix")
    require(isinstance(prefixes, list) and 0 < len(prefixes) <= 8
            and isinstance(path, str) and path.startswith("/") and real.within_scope(scope["target_url"], prefixes),
            "captured_scope_mismatch")
    scope_hash = digest({"target_url": scope["target_url"], "path_prefix": path,
                         "allowed_url_prefixes": sorted(set(prefixes))})
    return scope_hash


def verify_review(row, directory, receipt_sha, authorization_sha):
    primary, auditor = (row[key].strip() for key in ("primary_reviewer", "independent_auditor"))
    require(primary and auditor and primary.casefold() != auditor.casefold(), "separate_reviewer_record_missing")
    require(all(row[key] == "complete" for key in ("critical_high_review_status", "independent_audit_status"))
            and all(row[key] == "pass" for key in ("accuracy_verdict", "independent_audit_verdict",
                                                   "tier_acceptance_verdict")), "qa_review_decision_pending")
    require(all(row[key].isascii() and row[key].isdigit() for key in REVIEW_COUNTS), "qa_review_counts_missing")
    counts = {key: int(row[key]) for key in REVIEW_COUNTS}
    for severity in ("critical", "high"):
        require(counts[f"{severity}_groups_reviewed"] == counts[f"{severity}_group_count"]
                and counts[f"{severity}_false_positive_count"] + counts[f"{severity}_unresolved_count"]
                <= counts[f"{severity}_groups_reviewed"], "critical_high_review_incomplete")
    files = {field: evidence_file(directory, row, field) for field in REVIEW_FILES}
    review = evidence_file(directory, row, "independent_audit_evidence_ref")
    require_fields(json_object(review), {
        "schema_version": "real_site_qa_review_attestation_v1", "row_id": row["row_id"],
        "scan_id": row["actual_scan_id"], "source_sha": row["actual_source_sha"],
        "primary_reviewer": primary, "independent_auditor": auditor, "verdict": row["independent_audit_verdict"],
        "receipt_sha256": receipt_sha, "authorization_sha256": authorization_sha,
        "review_evidence_sha256": {field: sha256(data) for field, data in files.items()},
        "reviewed_register_fields": {field: row[field] for field in REVIEWED_FIELDS},
    }, "review_attestation_mismatch")
    checked = json.loads(files["checked_url_manifest_ref"])
    require(isinstance(checked, list) and all(isinstance(url, str) for url in checked)
            and len(checked) == len(set(checked)), "checked_manifest_invalid")
    return sha256(review), checked


def verify_row(row, directory, *, cap, source, fingerprint, result_route):
    require(bool(row["current_authorization_ref"].strip()), "current_authorization_missing")
    require(row["run_status"] in {"complete", "limited"}, "current_run_missing")
    require(row["planned_candidate_source_sha"] == row["actual_source_sha"] == source
            and row["actual_release_fingerprint"] == fingerprint, "register_release_mismatch")
    authorization_sha = sha256(evidence_file(directory, row, "current_authorization_ref"))
    capture_raw = evidence_file(directory, row, "actual_owner_project_binding_evidence_ref")
    receipt_raw = evidence_file(directory, row, "stage_receipt_evidence_ref")
    captured, snapshot = json_object(capture_raw), json_object(receipt_raw)
    require_fields(captured, {"schema_version": real.INPUT_VERSION}, "capture_schema_mismatch")
    require_fields(snapshot, {
        "schema_version": real.EVIDENCE_VERSION, "scope": "real_site_terminal_receipt",
        "qa_row_id": row["row_id"], "receipt_evidence_verified": True, "worker_runtime_verified": True,
        "input_capture_sha256": sha256(capture_raw), "authorization_reference_sha256": authorization_sha,
    }, "scope_receipt_mismatch")
    require(mapping(captured.get("approved_scope")).get("authorization_reference_sha256") == authorization_sha
            and matches(receipt.SHA256, snapshot.get("receipt_snapshot_sha256"))
            and matches(receipt.GENERATION, snapshot.get("frontier_generation")), "scope_receipt_mismatch")
    scope_hash = verify_run(row, captured, snapshot, cap=cap, source=source, fingerprint=fingerprint,
                            result_route=result_route)
    for field in COUNTS:
        actual = snapshot.get(field)
        types = (int, float) if field == "duration_seconds" else (int,)
        require(type(actual) in types and Decimal(str(actual)).is_finite()
                and Decimal(row[field]) == Decimal(str(actual)) >= 0, "receipt_measurements_mismatch")
    require(0 <= snapshot["usable_html_count"] <= snapshot["checked_distinct_url_count"]
            <= snapshot["planned_page_count"] <= cap, "receipt_measurements_mismatch")
    require(row["inventory_current_verification_status"] == "verified", "inventory_review_missing")
    for field in ("inventory_capped", "rate_limit_observed"):
        require(type(snapshot.get(field)) is bool and row[field] == str(snapshot[field]).lower(),
                "receipt_measurements_mismatch")
    review_sha, checked = verify_review(row, directory, sha256(receipt_raw), authorization_sha)
    require(len(checked) == snapshot["checked_distinct_url_count"]
            and digest(sorted(checked)) == snapshot.get("checked_url_set_sha256"), "checked_manifest_receipt_mismatch")
    return {
        "row_id": row["row_id"], "scan_id": snapshot["scan_id"], "scope_sha256": scope_hash,
        "receipt_sha256": sha256(receipt_raw), "review_sha256": review_sha,
        "discovered_url_count": snapshot["discovered_url_count"],
    }


def verify_register(raw, directory, *, source, fingerprint, result_route, tier):
    by_id = manifest_rows(raw)
    caps = (150,) if tier == 150 else (150, 500)
    approved, pending = {}, {}
    for slot in SLOTS:
        for cap in caps:
            row_id = f"{slot}-{cap}"
            try:
                approved[row_id] = verify_row(by_id[row_id], directory, cap=cap, source=source,
                                               fingerprint=fingerprint, result_route=result_route)
            except receipt.EvidenceError as exc:
                pending[row_id] = str(exc)
            except (OSError, TypeError, ValueError, InvalidOperation, KeyError):
                pending[row_id] = "evidence_missing_or_unreadable"
        left, right = (approved.get(f"{slot}-{cap}") for cap in (150, 500))
        if left and right and left["scope_sha256"] != right["scope_sha256"]:
            pending.update({item["row_id"]: "paired_scope_mismatch" for item in (left, right)})
    duplicates = Counter(item["scan_id"] for item in approved.values())
    for row_id, item in approved.items():
        if duplicates[item["scan_id"]] > 1:
            pending[row_id] = "duplicate_scan_attempt"
    verified_rows = [item for row_id, item in sorted(approved.items()) if row_id not in pending]
    class_coverage, missing_classes, inventories = {}, {}, {}
    for cap in caps:
        lane = [item for item in verified_rows if item["row_id"].endswith(f"-{cap}")]
        coverage = {name: any(by_id[item["row_id"]][field] == "verified" for item in lane)
                    for name, field in CLASS_FIELDS.items()}
        class_coverage[str(cap)] = coverage
        missing_classes[str(cap)] = [name for name, covered in coverage.items() if not covered]
        observed = [item["discovered_url_count"] for item in lane]
        inventories[str(cap)] = {"minimum": min(observed, default=None), "maximum": max(observed, default=None)}
    verified = not pending and not any(missing_classes.values())
    register_sha = sha256(raw)
    binding = {"register_sha256": register_sha, "source_sha": source, "release_fingerprint": fingerprint,
               "tier": tier, "rows": verified_rows}
    return {
        "schema_version": "real_site_qa_register_verification_v1", "verified": verified,
        "source_sha": source, "release_fingerprint": fingerprint, "tier": tier,
        "verification_scope": "private_evidence_completeness_and_recorded_reviewer_attestations",
        "release_authorization_verified": False, "register_sha256": register_sha,
        "required_rows": 20 * len(caps), "completed_rows": len(verified_rows),
        "missing_rows": [{"row_id": key, "reason": reason} for key, reason in sorted(pending.items())],
        "missing_classes": missing_classes,
        "technical_class_coverage": class_coverage, "observed_inventory_range": inventories,
        "verification_sha256": digest(binding) if verified else None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--register", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--tier", type=int, choices=(150, 500), required=True)
    args = parser.parse_args()
    try:
        require(matches(receipt.SOURCE_SHA, args.source_sha), "candidate_source_invalid")
        source = args.source_sha
        record = subprocess.run(["git", "show", f"{source}:data/beta-crawler-revision.json"], cwd=SCANNER_ROOT.parent,
                                capture_output=True, timeout=5, check=True)
        fingerprint = json_object(record.stdout)["fingerprint"]
        route = real.released_result_route(source, fingerprint)
        directory = args.evidence_dir.resolve(strict=True)
        require(directory.is_dir(), "private_evidence_directory_missing")
        result = verify_register(read_bounded(args.register.resolve(strict=True)), directory, source=source,
                                 fingerprint=fingerprint, result_route=route, tier=args.tier)
        print(json.dumps(result, indent=2))
        return 0 if result["verified"] else 1
    except receipt.EvidenceError as exc:
        print(f"REAL_SITE_QA_REGISTER_BLOCKED: {exc}", file=sys.stderr)
    except (OSError, TypeError, ValueError, KeyError, subprocess.SubprocessError):
        print("REAL_SITE_QA_REGISTER_BLOCKED: input_unavailable", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
