"""Local QA register fixtures exercise both tier gates without live evidence."""

import csv
import hashlib
import io
import json
from datetime import datetime, timedelta, timezone

from scripts import verify_real_site_qa_register as gate
from scripts.collect_published_paid_500 import digest
from tests.test_collect_real_site_scan_receipt import captured_packet

SOURCE, FINGERPRINT, ROUTE = "a" * 40, "b" * 16, "getCustomerScanResultV9Bexample"


def put(root, name, document):
    path = root / name
    path.write_text(json.dumps(document), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(tmp_path, *, completed_caps=(150, 500)):
    rows = []
    now = datetime.now(timezone.utc)
    for index in range(1, 21):
        slot = f"S{index:02}"
        target = f"https://site{index}.example/guide"
        for cap in (150, 500):
            row_id = f"{slot}-{cap}"
            row = dict.fromkeys(gate.REQUIRED_FIELDS, "")
            row.update(register_version="real_site_qa_register_v1", site_slot=slot, row_id=row_id,
                       target_url=target, planned_page_cap=str(cap), planned_scan_mode=f"standard_{cap}")
            rows.append(row)
            if cap not in completed_caps:
                continue
            scan_id = f"test_scan_{index}_{cap}"
            auth = f"{slot}.permission"
            auth_sha = put(tmp_path, auth, {"target": target, "authorized": True})
            capture_ref = f"{row_id}.capture.json"
            packet = captured_packet()
            scope = packet["approved_scope"]
            scope.update(row_id=row_id, page_cap=cap, target_url=target, allowed_url_prefixes=[target],
                         authorization_reference_sha256=auth_sha,
                         authorized_from=(now - timedelta(hours=1)).isoformat(),
                         authorized_until=(now + timedelta(hours=1)).isoformat())
            run = packet["saved_run"]
            run.update(id=scan_id, website_url=target, page_cap=cap, scan_mode=f"standard_{cap}")
            url = f"https://getfixlist.com/dashboard?scan_id={scan_id}"
            packet["browser"].update(history_url=url, result_route=ROUTE)
            packet["browser"]["projection"]["scan_id"] = scan_id
            packet["worker_runtime"].update(source_sha=SOURCE, release_fingerprint=FINGERPRINT)
            inbox = put(tmp_path, capture_ref, packet)
            receipt_ref = f"{row_id}.receipt.json"
            checked = [f"{target}/{i}" for i in range(120)]
            checked_ref = f"{row_id}.checked.json"
            put(tmp_path, checked_ref, checked)
            snapshot = {
                "schema_version": "real_site_qa_receipt_evidence_v1", "scope": "real_site_terminal_receipt",
                "receipt_evidence_verified": True, "worker_runtime_verified": True,
                "qa_row_id": row_id, "input_capture_sha256": inbox, "authorization_reference_sha256": auth_sha,
                "source_sha": SOURCE, "release_fingerprint": FINGERPRINT, "worker_revision": packet["worker_runtime"]["revision"],
                "scan_id": scan_id, "page_cap": cap, "attempt_count": 1, "terminal_status": "complete",
                "terminal_outcome": "complete_queue_exhausted", "duration_seconds": 60, "committed_batch_count": 3,
                "planned_page_count": 130, "checked_distinct_url_count": 120, "usable_html_count": 118,
                "discovered_url_count": 140, "inventory_capped": False, "rate_limit_observed": False,
                "checked_url_set_sha256": digest(sorted(checked)), "receipt_snapshot_sha256": "d" * 64,
                "frontier_generation": "1",
            }
            receipt_sha = put(tmp_path, receipt_ref, snapshot)
            row.update(current_authorization_ref=auth, current_authorization_expires_at=scope["authorized_until"],
                       actual_owner_project_binding_evidence_ref=capture_ref, stage_receipt_evidence_ref=receipt_ref,
                       checked_url_manifest_ref=checked_ref, primary_reviewer="Reviewer 1", independent_auditor="Reviewer 2",
                       critical_high_review_status="complete", independent_audit_status="complete",
                       accuracy_verdict="pass", independent_audit_verdict="pass", tier_acceptance_verdict="pass",
                       planned_candidate_source_sha=SOURCE, actual_source_sha=SOURCE, actual_release_fingerprint=FINGERPRINT,
                       planned_worker_revision=snapshot["worker_revision"], actual_worker_revision=snapshot["worker_revision"],
                       actual_scan_id=scan_id, actual_scan_mode=f"standard_{cap}", actual_submitted_page_cap=str(cap),
                       run_status="complete", terminal_outcome="complete_queue_exhausted", saved_report_url=url,
                       inventory_capped="false", rate_limit_observed="false", inventory_current_verification_status="verified")
            if index <= len(gate.CLASS_FIELDS):
                row[list(gate.CLASS_FIELDS.values())[index - 1]] = "verified"
            for field in gate.COUNTS:
                row[field] = str(snapshot[field])
            for field in gate.REVIEW_COUNTS:
                row[field] = "0"
            hashes = {}
            for field in gate.REVIEW_FILES:
                if row[field]:
                    hashes[field] = hashlib.sha256((tmp_path / row[field]).read_bytes()).hexdigest()
                else:
                    row[field] = f"{row_id}.{field}"
                    hashes[field] = put(tmp_path, row[field], {"row_id": row_id, "file": field})
            row["independent_audit_evidence_ref"] = f"{row_id}.independent.json"
            put(tmp_path, row["independent_audit_evidence_ref"], {
                "schema_version": "real_site_qa_review_attestation_v1", "row_id": row_id, "scan_id": scan_id,
                "source_sha": SOURCE, "primary_reviewer": "Reviewer 1", "independent_auditor": "Reviewer 2",
                "verdict": "pass", "receipt_sha256": receipt_sha,
                "authorization_sha256": auth_sha, "review_evidence_sha256": hashes,
                "reviewed_register_fields": {field: row[field] for field in gate.REVIEWED_FIELDS},
            })
    return rows


def evaluate(rows, path, tier):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=sorted(gate.REQUIRED_FIELDS))
    writer.writeheader()
    writer.writerows(rows)
    return gate.verify_register(stream.getvalue().encode(), path, source=SOURCE,
                                fingerprint=FINGERPRINT, result_route=ROUTE, tier=tier)


def test_150_can_pass_while_20_planned_500_rows_are_pending(tmp_path):
    rows = fixture(tmp_path, completed_caps=(150,))
    first = evaluate(rows, tmp_path, 150)
    assert first["verified"] is True
    assert first["completed_rows"] == 20
    all_tiers = evaluate(rows, tmp_path, 500)
    assert all_tiers["verified"] is False
    assert all_tiers["required_rows"] == 40
    assert len(all_tiers["missing_rows"]) == 20


def test_all_40_rows_bind_their_exact_scoped_release_and_reviews(tmp_path):
    rows = fixture(tmp_path)
    result = evaluate(rows, tmp_path, 500)
    assert result["verified"] is True
    assert result["completed_rows"] == 40
    assert result["observed_inventory_range"]["500"] == {"minimum": 140, "maximum": 140}
    assert all(result["technical_class_coverage"]["150"].values())
    assert result["release_authorization_verified"] is False
    assert result["verification_sha256"]
    (tmp_path / rows[1]["finding_review_evidence_ref"]).write_text("changed after review", encoding="utf-8")
    changed = evaluate(rows, tmp_path, 500)
    assert changed["missing_rows"] == [{"row_id": "S01-500", "reason": "review_attestation_mismatch"}]


def test_pending_register_reports_20_or_40_missing_without_opening_files(tmp_path):
    rows = fixture(tmp_path, completed_caps=())
    assert len(evaluate(rows, tmp_path, 150)["missing_rows"]) == 20
    assert len(evaluate(rows, tmp_path, 500)["missing_rows"]) == 40


def test_different_physical_permission_bytes_block_the_pair(tmp_path):
    rows = fixture(tmp_path)
    (tmp_path / rows[0]["current_authorization_ref"]).write_text("different permission", encoding="utf-8")
    result = evaluate(rows, tmp_path, 500)
    assert result["missing_rows"] == [
        {"row_id": "S01-150", "reason": "scope_receipt_mismatch"},
        {"row_id": "S01-500", "reason": "scope_receipt_mismatch"},
    ]


def test_exact_scope_is_paired_even_when_each_cap_has_complete_local_evidence(tmp_path):
    rows = fixture(tmp_path)
    row = rows[1]
    capture = json.loads((tmp_path / row["actual_owner_project_binding_evidence_ref"]).read_text())
    capture["approved_scope"]["allowed_url_prefixes"] = [row["target_url"], "https://redirect.example/"]
    capture_sha = put(tmp_path, row["actual_owner_project_binding_evidence_ref"], capture)
    snapshot = json.loads((tmp_path / row["stage_receipt_evidence_ref"]).read_text())
    snapshot["input_capture_sha256"] = capture_sha
    receipt_sha = put(tmp_path, row["stage_receipt_evidence_ref"], snapshot)
    audit = json.loads((tmp_path / row["independent_audit_evidence_ref"]).read_text())
    audit["receipt_sha256"] = receipt_sha
    put(tmp_path, row["independent_audit_evidence_ref"], audit)
    result = evaluate(rows, tmp_path, 500)
    assert result["missing_rows"] == [
        {"row_id": "S01-150", "reason": "paired_scope_mismatch"},
        {"row_id": "S01-500", "reason": "paired_scope_mismatch"},
    ]


def test_stale_source_and_missing_class_are_reported_separately(tmp_path):
    rows = fixture(tmp_path)
    rows[0]["actual_source_sha"] = "e" * 40
    result = evaluate(rows, tmp_path, 150)
    assert result["missing_rows"] == [{"row_id": "S01-150", "reason": "register_release_mismatch"}]
    assert result["missing_classes"]["150"] == ["multilingual"]


def test_reviewed_counts_and_class_text_cannot_change_after_second_review(tmp_path):
    rows = fixture(tmp_path)
    rows[0]["lower_priority_groups_sampled"] = "3"
    rows[2]["multilingual_evidence_status"] = "verified"
    result = evaluate(rows, tmp_path, 150)
    assert result["missing_rows"] == [
        {"row_id": "S01-150", "reason": "review_attestation_mismatch"},
        {"row_id": "S02-150", "reason": "review_attestation_mismatch"},
    ]
