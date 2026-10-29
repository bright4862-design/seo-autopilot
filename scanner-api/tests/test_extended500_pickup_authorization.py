"""Adversarial offline tests for private Extended 500 pickup read boundary.

All reader values emulate authenticated service-role reads. These tests do NOT
verify real Base44 credentials, Firestore transactionality or Cloud Run IAM.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.authority_seal import create_authority_seal
from app.extended500_pickup_authorization import authorize_extended500_pickup

KEY = "pickup-preflight-root-key-not-for-production-00001"
QUEUE = "projects/test-project/locations/us-central1/queues/extended500-private"
NOW = datetime(2026, 10, 29, 12, 10, tzinfo=timezone.utc)


def iso(moment):
    return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def fingerprint(scan):
    request = {
        "owner_user_id": scan["owner_user_id"],
        "scan_id": scan["id"],
        "project_id": scan["project_id"],
        "request_id": scan["request_id"],
        "idempotency_key": scan["idempotency_key"],
        "access_id": scan["admission_access_id"],
        "attempt_count": scan["attempt_count"],
    }
    return hashlib.sha256(json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def sign(grant):
    grant["proof"] = create_authority_seal({k: v for k, v in grant.items() if k != "proof"}, KEY)


class FreshReader:
    def __init__(self, scan, project, access_rows, slot, receipt):
        self.scan, self.project, self.rows = scan, project, access_rows
        self.slot, self.receipt = slot, receipt
        self.pickup_claim = None
        self.calls = []
        self.fail_method = None

    def _read(self, method, key, value):
        self.calls.append((method, key))
        if self.fail_method == method:
            raise RuntimeError("transient service-role failure")
        return deepcopy(value)

    def read_scanrun(self, scan_id):
        return self._read("scan", scan_id, self.scan)

    def read_project(self, project_id):
        return self._read("project", project_id, self.project)

    def read_access_rows(self, owner_id):
        return self._read("access", owner_id, self.rows)

    def read_owner_slot(self, owner_id):
        return self._read("slot", owner_id, self.slot)

    def read_request_receipt(self, receipt_id):
        return self._read("receipt", receipt_id, self.receipt)

    def read_pickup_claim(self, receipt_id):
        return self._read("claim", receipt_id, self.pickup_claim)


def fixture():
    owner, project, scan_id, request = "owner_1", "project_1", "scan_1", "request_1"
    site = "https://www.customer-site.com/"
    scan = dict(id=scan_id, owner_user_id=owner, project_id=project,
                request_id=request, idempotency_key=request, attempt_count=1,
                scan_mode="extended_500", status="queued", website_url=site,
                submitted_url=site, normalized_domain="customer-site.com",
                request_fingerprint=f"extended_500|{site}|root|respect_robots_txt",
                scan_source="extended500_private_candidate", path_prefix=None,
                respect_robots_txt=True, owner_attested_robots_override=False,
                admission_access_id="access_1")
    task = dict(scan_mode="extended_500", scan_id=scan_id, owner_user_id=owner,
                project_id=project, request_id=request, idempotency_key=request,
                attempt_count=1, website_url=site, path_prefix=None,
                respect_robots_txt=True, owner_attested_robots_override=False)
    grant = dict(version="extended500_preflight_grant_v1",
                 audience="fixlist_extended500_worker", canonical_mode="extended_500",
                 **{k: task[k] for k in task if k != "scan_mode"},
                 issued_at=iso(NOW - timedelta(minutes=10)),
                 expires_at=iso(NOW - timedelta(minutes=8)))
    sign(grant)
    task["signed_grant"] = grant
    access = dict(id="access_1", owner_user_id=owner,
                  user_email="customer@example.com", app_id="6a498732ec779dfaaeab0e53",
                  plan_id="extended500_lifetime", access_status="active",
                  has_full_access=True, grant_source="stripe_checkout",
                  stripe_checkout_session_id="cs_test_123",
                  paid_at="2026-10-28T12:00:00.000Z")
    rid = hashlib.sha256(f"{owner}\n{request}".encode()).hexdigest()
    task_name = f"{QUEUE}/tasks/extended500-{rid}-a1"
    slot = dict(schema="extended500_owner_slot_v1", owner_user_id=owner,
                receipt_id=rid, request_id=request, scan_id=scan_id,
                attempt_count=1, state="enqueued", issued_at=100)
    receipt = dict(schema="extended500_request_receipt_v1", receipt_id=rid,
                   fingerprint=fingerprint(scan), owner_user_id=owner,
                   request_id=request, scan_id=scan_id, attempt_count=1,
                   task_name=task_name, state="enqueued", issued_at=100)
    reader = FreshReader(scan, dict(id=project, owner_user_id=owner,
                                   website_url=site, status="active"),
                         [access], slot, receipt)
    return task, reader, task_name


def run(task, reader, name, **overrides):
    params = dict(signing_key=KEY, queue_path=QUEUE, trusted_task_name=name,
                  verified_private_invoker=True, feature_enabled=True, now=NOW)
    params.update(overrides)
    return authorize_extended500_pickup(task, reader, **params)


def test_expired_issuance_grant_is_only_identity_not_durable_authority():
    task, reader, name = fixture()
    result = run(task, reader, name)
    assert result.code == "ready_for_atomic_claim"
    assert result.ready_for_atomic_claim is True
    assert result.execution_allowed is False
    assert result.task_name == name
    assert [name for name, _ in reader.calls] == ["scan", "project", "access", "slot", "receipt", "claim"]


def test_revocation_after_queueing_is_denied_on_fresh_read():
    task, reader, name = fixture()
    assert run(task, reader, name).ready_for_atomic_claim
    reader.rows[0]["access_status"] = "revoked"
    assert run(task, reader, name).code == "paid_access_not_active"


def test_existing_standard150_paid_access_may_coexist():
    task, reader, name = fixture()
    reader.rows.append(dict(id="access_150", plan_id="standard150_lifetime"))
    assert run(task, reader, name).ready_for_atomic_claim


def test_existing_claim_replay_denied_even_if_all_other_reads_still_valid():
    task, reader, name = fixture()
    reader.pickup_claim = {"schema": "extended500_pickup_claim_v1", "state": "claimed"}
    assert run(task, reader, name).code == "pickup_replay_or_claim_conflict"


def test_no_read_only_verdict_can_authorize_execution():
    task, reader, name = fixture()
    assert run(task, reader, name).execution_allowed is False
    reader.pickup_claim = {"state": "claimed"}
    assert run(task, reader, name).execution_allowed is False


@pytest.mark.parametrize("field,value", [
    ("scan_mode", "standard_150"), ("scan_mode", "advanced"),
    ("scan_id", "foreign_scan"), ("project_id", "foreign_project"),
    ("owner_user_id", "foreign_owner"), ("request_id", "foreign_request"),
    ("idempotency_key", "other_request"), ("attempt_count", 2),
    ("attempt_count", True), ("attempt_count", 1.0),
    ("website_url", "https://evil.com/"),
    ("website_url", "http://127.0.0.1/"),
    ("website_url", "https://customer-site.com/admin"),
    ("website_url", "https://customer-site.com:444/"),
    ("path_prefix", "/secret"),
    ("respect_robots_txt", False),
    ("owner_attested_robots_override", True),
])
def test_task_mutations_fail_closed(field, value):
    task, reader, name = fixture()
    task[field] = value
    assert not run(task, reader, name).ready_for_atomic_claim


@pytest.mark.parametrize("field,value", [
    ("scan_mode", "standard_150"), ("status", "crawling"),
    ("status", "complete"), ("status", "failed"),
    ("owner_user_id", "foreign_owner"), ("project_id", "foreign_project"),
    ("request_id", "foreign_request"), ("idempotency_key", "foreign_key"),
    ("attempt_count", 2), ("attempt_count", True),
    ("website_url", "https://evil.com/"),
    ("submitted_url", "https://evil.com/"),
    ("normalized_domain", "evil.com"),
    ("request_fingerprint", "forged"),
    ("scan_source", "browser"), ("path_prefix", "/"),
    ("respect_robots_txt", False),
    ("owner_attested_robots_override", True),
    ("admission_access_id", "foreign_access"),
])
def test_durable_scan_mutations_fail_closed(field, value):
    task, reader, name = fixture()
    reader.scan[field] = value
    assert not run(task, reader, name).ready_for_atomic_claim


@pytest.mark.parametrize("field,value", [
    ("owner_user_id", "other_owner"), ("id", "other_project"),
    ("website_url", "https://other-site.com/"),
    ("status", "paused"), ("status", "archived"),
])
def test_project_mutations_fail_closed(field, value):
    task, reader, name = fixture()
    reader.project[field] = value
    assert run(task, reader, name).code == "project_not_owned_or_active"


@pytest.mark.parametrize("field,value", [
    ("id", "other_access"), ("owner_user_id", "other_owner"),
    ("app_id", "wrong_app"), ("plan_id", "standard150_lifetime"),
    ("access_status", "pending"), ("access_status", "revoked"),
    ("has_full_access", False), ("has_full_access", 1),
    ("grant_source", "owner_test"), ("grant_source", "manual"),
    ("stripe_checkout_session_id", ""), ("paid_at", "not-a-date"),
    ("user_email", ""),
])
def test_access_mutations_fail_closed(field, value):
    task, reader, name = fixture()
    reader.rows[0][field] = value
    assert not run(task, reader, name).ready_for_atomic_claim


@pytest.mark.parametrize("record,field,value", [
    ("slot", "schema", "wrong"), ("receipt", "schema", "wrong"),
    ("slot", "owner_user_id", "other"), ("receipt", "owner_user_id", "other"),
    ("slot", "receipt_id", "other"), ("receipt", "receipt_id", "other"),
    ("slot", "request_id", "other"), ("receipt", "request_id", "other"),
    ("slot", "scan_id", "other"), ("receipt", "scan_id", "other"),
    ("slot", "attempt_count", 2), ("receipt", "attempt_count", True),
    ("receipt", "fingerprint", "0" * 64),
    ("receipt", "task_name", "forged"),
    ("slot", "state", "reserved"), ("receipt", "state", "reserved"),
    ("slot", "state", "released"), ("receipt", "state", "released"),
    ("slot", "state", "dispatch_unknown"),
])
def test_reservation_mutations_fail_closed(record, field, value):
    task, reader, name = fixture()
    getattr(reader, record)[field] = value
    assert not run(task, reader, name).ready_for_atomic_claim


def test_matching_dispatch_unknown_is_allowed_for_uncertain_cloud_tasks_result():
    task, reader, name = fixture()
    reader.slot["state"] = reader.receipt["state"] = "dispatch_unknown"
    assert run(task, reader, name).ready_for_atomic_claim


def test_tampered_signed_grant_denied():
    task, reader, name = fixture()
    task["signed_grant"]["proof"] = "0" * 64
    assert run(task, reader, name).code == "grant_signature_invalid"


def test_validly_resigned_grant_with_wrong_task_identity_denied():
    task, reader, name = fixture()
    task["signed_grant"]["project_id"] = "foreign_project"
    sign(task["signed_grant"])
    assert run(task, reader, name).code == "grant_identity_mismatch"


@pytest.mark.parametrize("change", ["future", "too_old", "overlong", "bad_expiry"])
def test_invalid_grant_time_denied(change):
    task, reader, name = fixture()
    grant = task["signed_grant"]
    if change == "future":
        grant["issued_at"] = iso(NOW + timedelta(minutes=1))
        grant["expires_at"] = iso(NOW + timedelta(minutes=3))
    elif change == "too_old":
        grant["issued_at"] = iso(NOW - timedelta(days=8))
        grant["expires_at"] = iso(NOW - timedelta(days=8) + timedelta(minutes=2))
    elif change == "overlong":
        grant["expires_at"] = iso(NOW)
    else:
        grant["expires_at"] = "bad-time"
    sign(grant)
    assert not run(task, reader, name).ready_for_atomic_claim


@pytest.mark.parametrize("method", ["scan", "project", "access", "slot", "receipt", "claim"])
def test_service_read_failures_fail_closed(method):
    task, reader, name = fixture()
    reader.fail_method = method
    assert run(task, reader, name).code == "durable_authority_unavailable"


def test_missing_records_and_duplicate_access_denied():
    for record in ("scan", "project", "slot", "receipt"):
        task, reader, name = fixture()
        setattr(reader, record, None)
        assert not run(task, reader, name).ready_for_atomic_claim
    task, reader, name = fixture()
    reader.rows.append(deepcopy(reader.rows[0]))
    assert run(task, reader, name).code == "paid_access_missing_or_duplicate"


@pytest.mark.parametrize("overrides", [
    {"feature_enabled": False}, {"verified_private_invoker": False},
    {"queue_path": "projects/test/locations/us/queues/standard150"},
    {"trusted_task_name": "forged"}, {"signing_key": "short"},
    {"now": datetime(2026, 10, 29, 12, 10)},
])
def test_boundary_gates_fail_closed(overrides):
    task, reader, name = fixture()
    assert not run(task, reader, name, **overrides).ready_for_atomic_claim


def test_feature_off_never_reads_authority():
    task, reader, name = fixture()
    assert run(task, reader, name, feature_enabled=False).code == "pickup_disabled"
    assert reader.calls == []


def test_task_shape_extra_paid_flag_is_not_authority():
    task, reader, name = fixture()
    task["paid"] = True
    assert run(task, reader, name).code == "task_shape_invalid"


def test_task_name_is_deterministic_not_task_body_claim():
    task, reader, name = fixture()
    assert run(task, reader, name, trusted_task_name=name.replace("-a1", "-a2")).code == "task_name_mismatch"


def test_task_grant_is_not_sufficient_after_paid_record_is_removed():
    task, reader, name = fixture()
    reader.rows.clear()
    assert run(task, reader, name).code == "paid_access_missing_or_duplicate"
