"""Extended 500 worker pickup: fresh paid entitlement + atomic slot verification.

Fully offline. Coordinator slot/receipt documents come from the REAL
``extended500-admission/core.py`` decision functions (loaded by path), the task
body is captured from the REAL ``service.py`` ``enqueue()`` with stubbed
transports, and a JS-minted grant proves cross-runtime signature parity.
Nothing here reaches Base44, Firestore, Cloud Tasks, Stripe or a website.
These are decision-level proofs; they do not establish IAM, Firestore
serializability or Cloud Tasks delivery semantics.
"""
from __future__ import annotations

import ast
import asyncio
import base64
import copy
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import types

import pytest

from app import extended500_job_admission
from app import extended500_pickup_authorization as pickup
from app.authority_seal import create_authority_seal
from app.extended500_pickup_authorization import (
    ABORT, AUTHORIZED, CLAIMED, CONTINUE, DENY, RETRY, SKIP, UNAVAILABLE,
    AUTHORITY_BASE44_SERVICE_ROLE as B44,
    AUTHORITY_COORDINATOR_FIRESTORE as FS,
    SourceRead,
    authorize_extended500_pickup,
    claim_extended500_pickup,
    decide_extended500_pickup_claim,
    delivery_from_cloud_tasks_headers,
    evaluate_extended500_pickup,
    evaluate_extended500_revalidation,
    revalidate_extended500_pickup,
)

ROOT = Path(__file__).resolve().parents[2]
SERVICE_DIR = ROOT / "extended500-admission"
_spec = importlib.util.spec_from_file_location("extended500_pickup_core", SERVICE_DIR / "core.py")
core = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(core)

KEYS = {
    "EXTENDED500_COORDINATOR_SIGNING_KEY": "coordinator-pickup-fixture-aaaaaaaaaaaaaaaa",
    "EXTENDED500_ENTITLEMENT_SIGNING_KEY": "entitlement-pickup-fixture-bbbbbbbbbbbbbbbb",
    "EXTENDED500_ADMISSION_SIGNING_KEY": "admission-pickup-fixture-cccccccccccccccccc",
    "EXTENDED500_TERMINAL_SIGNING_KEY": "terminal-pickup-fixture-dddddddddddddddddddd",
    "EXTENDED500_TASKS_QUEUE_PATH": "projects/fixlist-test/locations/us-central1/queues/extended500-test",
    "EXTENDED500_WORKER_ORIGIN": "https://worker.example/scan-job-extended500",
    "EXTENDED500_INVOKER_SERVICE_ACCOUNT": "e500-invoker@example.iam.gserviceaccount.com",
    "EXTENDED500_ATOMIC_ADMISSION_ENABLED": "true",
    "EXTENDED500_QUEUE_DISPATCH_ENABLED": "false",
}
KEY = KEYS["EXTENDED500_ADMISSION_SIGNING_KEY"]
QUEUE = KEYS["EXTENDED500_TASKS_QUEUE_PATH"]
STANDARD150_KEY = "standard150-scan-evidence-fixture-" + "e" * 32
NOW = datetime(2026, 10, 29, 15, 0, tzinfo=timezone.utc)
FETCHED = NOW - timedelta(seconds=1)
OWNER, EMAIL = "owner_500", "owner@example.com"
SCAN, PROJECT, REQUEST, IDEM, ACCESS = "scan_500", "project_500", "request_500", "idem_500", "access_500"
SITE = "https://shop.example.com/"


def zulu(moment):
    return moment.isoformat().replace("+00:00", "Z")


# ------------------------------------------------------------------ fixtures --

def scan_run(**over):
    record = {
        "id": SCAN, "scan_id": SCAN, "owner_user_id": OWNER, "project_id": PROJECT,
        "request_id": REQUEST, "idempotency_key": IDEM, "attempt_count": 1,
        "scan_mode": "extended_500", "status": "queued",
        "website_url": SITE, "submitted_url": SITE, "normalized_domain": "shop.example.com",
        "path_prefix": None, "respect_robots_txt": True, "owner_attested_robots_override": False,
        "admission_access_id": ACCESS, "scan_source": "extended500_private_candidate",
    }
    record.update(over)
    return record


def project(**over):
    record = {
        "id": PROJECT, "owner_user_id": OWNER, "website_url": "https://www.shop.example.com",
        "business_name": "Fixture", "subscription_plan": "free", "status": "active",
    }
    record.update(over)
    return record


def user(**over):
    return {"id": OWNER, "email": EMAIL, "role": "user", **over}


def access(**over):
    record = {
        "id": ACCESS, "owner_user_id": OWNER, "user_email": EMAIL,
        "app_id": pickup.EXTENDED500_ACCESS_APP_ID, "plan_id": "extended500_lifetime",
        "access_status": "active", "has_full_access": True, "grant_source": "stripe_checkout",
        "stripe_checkout_session_id": "cs_test_fixture_500", "paid_at": "2026-10-20T10:00:00.000Z",
    }
    record.update(over)
    return record


def grant(*, issued=None, expires=None, key=KEY, **over):
    issued = issued or (NOW - timedelta(seconds=15))
    document = {
        "version": "extended500_preflight_grant_v1", "audience": "fixlist_extended500_worker",
        "canonical_mode": "extended_500", "owner_user_id": OWNER, "scan_id": SCAN,
        "project_id": PROJECT, "request_id": REQUEST, "idempotency_key": IDEM,
        "attempt_count": 1, "website_url": SITE, "path_prefix": None,
        "respect_robots_txt": True, "owner_attested_robots_override": False,
        "issued_at": zulu(issued), "expires_at": zulu(expires or (issued + timedelta(seconds=120))),
    }
    document.update(over)
    return {**document, "proof": create_authority_seal(document, key)}


def task_from_grant(signed):
    # Mirrors extended500-admission/service.py enqueue(); parity is asserted
    # against the real enqueue() body in test_real_coordinator_task_body_*.
    return {
        "scan_mode": "extended_500",
        "scan_id": signed["scan_id"], "request_id": signed["request_id"],
        "idempotency_key": signed["idempotency_key"], "project_id": signed["project_id"],
        "owner_user_id": signed["owner_user_id"], "attempt_count": signed["attempt_count"],
        "website_url": signed["website_url"], "path_prefix": signed["path_prefix"],
        "respect_robots_txt": signed["respect_robots_txt"],
        "owner_attested_robots_override": signed["owner_attested_robots_override"],
        "signed_grant": signed,
    }


def entitlement_claim(**over):
    claim = {
        "version": core.ENTITLEMENT_VERSION, "plan_id": core.PLAN, "scan_mode": core.MODE,
        "entitlement_state": "active_paid", "owner_user_id": OWNER, "scan_id": SCAN,
        "project_id": PROJECT, "request_id": REQUEST, "idempotency_key": IDEM,
        "access_id": ACCESS, "attempt_count": 1,
    }
    claim.update(over)
    return claim


def reservation(state="enqueued", slot=None, **over):
    """Slot+receipt exactly as the coordinator's core.py would write them."""
    decided = core.decide_reservation(slot, None, entitlement_claim(**over), QUEUE, issued_at=1_793_000_000)
    slot_doc, receipt_doc = decided["slot_write"], decided["receipt_write"]
    if state != "reserved":
        moved = core.decide_dispatch_state(slot_doc, receipt_doc, state=state)
        slot_doc, receipt_doc = moved["slot_write"], moved["receipt_write"]
    return slot_doc, receipt_doc


def delivery_for(receipt, **over):
    return {
        "queue_name": "extended500-test", "task_name": receipt["task_name"].rsplit("/", 1)[1],
        "retry_count": 0, "execution_count": 0, **over,
    }


def world():
    slot, receipt = reservation()
    return {
        "task": task_from_grant(grant()), "delivery": delivery_for(receipt),
        "scan": scan_run(), "project": project(), "user": user(), "access": [access()],
        "slots": {OWNER: slot}, "receipts": {receipt["receipt_id"]: receipt},
        "key": KEY, "queue": QUEUE, "now": NOW,
    }


def receipt_of(w):
    return w["receipts"][core.receipt_id({"owner_user_id": OWNER, "request_id": REQUEST})]


class Sources:
    """In-memory authority ports over a world. Records every lookup key."""

    def __init__(self, w, *, labels=None, fail=None, asynchronous=False):
        self.w, self.labels, self.fail = w, labels or {}, fail
        self.asynchronous, self.calls = asynchronous, []

    def _answer(self, method, argument, authority, value):
        self.calls.append((method, argument))
        if self.fail == method:
            raise ConnectionError("fixture transport failure")
        read = SourceRead(self.labels.get(method, authority), copy.deepcopy(value))
        if self.asynchronous:
            async def later():
                return read
            return later()
        return read

    def read_scan_run(self, scan_id):
        scan = self.w["scan"]
        return self._answer("read_scan_run", scan_id, B44,
                            scan if isinstance(scan, dict) and scan.get("id") == scan_id else None)

    def read_business_project(self, project_id):
        record = self.w["project"]
        return self._answer("read_business_project", project_id, B44,
                            record if isinstance(record, dict) and record.get("id") == project_id else None)

    def read_owner_user(self, owner_user_id):
        record = self.w["user"]
        return self._answer("read_owner_user", owner_user_id, B44,
                            record if isinstance(record, dict) and record.get("id") == owner_user_id else None)

    def filter_access_by_owner(self, owner_user_id):
        rows = self.w.get("access_by_owner_override")
        if rows is None:
            rows = [row for row in self.w["access"] if row.get("owner_user_id") == owner_user_id]
        return self._answer("filter_access_by_owner", owner_user_id, B44, rows)

    def filter_access_by_email(self, user_email):
        rows = self.w.get("access_by_email_override")
        if rows is None:
            rows = [row for row in self.w["access"] if row.get("user_email") == user_email]
        return self._answer("filter_access_by_email", user_email, B44, rows)

    def read_owner_slot(self, owner_user_id):
        return self._answer("read_owner_slot", owner_user_id, FS, self.w["slots"].get(owner_user_id))

    def read_request_receipt(self, receipt_id):
        return self._answer("read_request_receipt", receipt_id, FS, self.w["receipts"].get(receipt_id))


def evidence_from(w, at=FETCHED):
    """Complete evidence read with the same server-derived keys as the gatherer."""
    src = Sources(w)
    task = w["task"] if isinstance(w["task"], dict) else {}
    scan = src.read_scan_run(task.get("scan_id"))
    s = scan.value if isinstance(scan.value, dict) else {}
    owner = s.get("owner_user_id") or ""
    owner_user = src.read_owner_user(owner)
    email = (owner_user.value or {}).get("email") or ""
    reads = {
        "scan_run": scan,
        "business_project": src.read_business_project(s.get("project_id")),
        "owner_user": owner_user,
        "access_by_owner": src.filter_access_by_owner(owner),
        "access_by_email": src.filter_access_by_email(email),
        "owner_slot": src.read_owner_slot(owner),
        "request_receipt": src.read_request_receipt(
            pickup.extended500_receipt_id(owner, s.get("request_id") or "")),
    }
    return {name: replace(read, fetched_at=at) for name, read in reads.items()}


def pure(w, evidence=None):
    return evaluate_extended500_pickup(
        w["task"], w["delivery"], evidence if evidence is not None else evidence_from(w),
        grant_signing_key=w["key"], queue_path=w["queue"], now=w["now"],
    )


def gathered(w, sources=None, clock=None):
    return asyncio.run(authorize_extended500_pickup(
        w["task"], w["delivery"], sources or Sources(w),
        grant_signing_key=w["key"], queue_path=w["queue"], clock=clock or (lambda: w["now"]),
    ))


def authorized_binding(w=None):
    decision = pure(w or world())
    assert decision.outcome == AUTHORIZED, decision
    return decision


# ----------------------------------------------------------- mutation helpers --

def resign(w, **over):
    w["task"] = task_from_grant(grant(**over))


def set_task(w, **over):
    w["task"].update(over)


def set_scan(w, **over):
    w["scan"].update(over)


def set_access(w, **over):
    w["access"][0].update(over)


def replace_slot_and_receipt(w, slot, receipt):
    w["slots"][OWNER] = slot
    w["receipts"][receipt["receipt_id"]] = receipt


def released(w):
    receipt = receipt_of(w)
    out = core.decide_release(w["slots"][OWNER], receipt, core.canonical_request(entitlement_claim()),
                              terminal_status="complete", verified_terminal=True, released_at=1_793_000_100)
    replace_slot_and_receipt(w, out["slot_write"], out["receipt_write"])


def rebound_to_newer_request(w):
    released(w)
    newer_slot, newer_receipt = reservation(
        slot=w["slots"][OWNER], request_id="request_501", scan_id="scan_501", idempotency_key="idem_501")
    replace_slot_and_receipt(w, newer_slot, newer_receipt)


def slot_points_elsewhere_while_receipt_active(w):
    other_slot, _ = reservation(request_id="request_other", scan_id="scan_other", idempotency_key="idem_other")
    w["slots"][OWNER] = other_slot


def already_claimed(w, *, slot_too=True):
    claim = {"version": pickup.PICKUP_CLAIM_VERSION, "execution_id": "exec_first"}
    receipt_of(w)["pickup_claim"] = claim
    if slot_too:
        w["slots"][OWNER]["pickup_claim"] = dict(claim)


def access_replaced_and_scan_rebound(w):
    set_access(w, id="access_new")
    set_scan(w, admission_access_id="access_new")


POSITIVE = [
    pytest.param(lambda w: None, False, id="fresh-grant-fresh-entitlement"),
    pytest.param(lambda w: resign(w, issued=NOW - timedelta(hours=3)), True,
                 id="expired-grant-after-queue-delay-authorized-by-fresh-reads"),
    pytest.param(lambda w: resign(w, issued=NOW - timedelta(days=30)), True, id="paused-queue-30-day-delay"),
    pytest.param(lambda w: replace_slot_and_receipt(w, *reservation("reserved")), False,
                 id="receipt-reserved-dispatch-update-lost"),
    pytest.param(lambda w: replace_slot_and_receipt(w, *reservation("dispatch_unknown")), False,
                 id="receipt-dispatch-unknown"),
    pytest.param(lambda w: w["access"].append(access(id="access_150", plan_id="standard150_lifetime")), False,
                 id="standard150-paid-row-may-coexist"),
    pytest.param(lambda w: w["user"].update(email="Owner@Example.com"), False,
                 id="email-compared-case-insensitively"),
]


@pytest.mark.parametrize(("mutate", "expired"), POSITIVE)
def test_positive_pickup_matrix(mutate, expired):
    w = world()
    mutate(w)
    decision, via_ports = pure(w), gathered(w)
    assert decision.outcome == AUTHORIZED, decision
    assert (via_ports.outcome, via_ports.reason) == (decision.outcome, decision.reason)
    assert decision.grant_expired is expired
    assert decision.execution_enabled is False and via_ports.execution_enabled is False
    binding = decision.binding
    assert binding["owner_user_id"] == OWNER and binding["access_id"] == ACCESS
    assert binding["receipt_id"] == receipt_of(w)["receipt_id"] if w["receipts"] else True
    assert binding["grant_expired_at_pickup"] is expired
    with pytest.raises(TypeError):
        binding["owner_user_id"] = "owner_other"  # immutable server-derived binding


NEGATIVE = [
    # Entitlement state: only an active Stripe-paid extended500_lifetime row.
    pytest.param(lambda w: set_access(w, access_status="revoked"), DENY, "entitlement_revoked", id="revoked"),
    pytest.param(lambda w: set_access(w, access_status="pending"), DENY, "entitlement_pending", id="pending"),
    pytest.param(lambda w: set_access(w, access_status="refunded"), DENY, "entitlement_refunded", id="refunded"),
    pytest.param(lambda w: set_access(w, refunded_at="2026-10-28T00:00:00Z"), DENY,
                 "entitlement_refunded_or_revoked", id="refund-marker"),
    pytest.param(lambda w: set_access(w, grant_source="owner_test"), DENY, "owner_test_access_not_paid",
                 id="owner-test"),
    pytest.param(lambda w: set_access(w, grant_source="manual_grant"), DENY, "manual_access_not_paid",
                 id="manual-grant"),
    pytest.param(lambda w: set_access(w, grant_source="checkout_pending"), DENY, "entitlement_pending",
                 id="checkout-pending"),
    pytest.param(lambda w: set_access(w, has_full_access=False), DENY, "entitlement_inactive",
                 id="no-full-access"),
    pytest.param(lambda w: set_access(w, stripe_checkout_session_id=""), DENY, "access_not_stripe_paid",
                 id="missing-stripe-session"),
    pytest.param(lambda w: set_access(w, plan_id="standard150_lifetime"), DENY,
                 "standard150_access_cannot_authorize_extended500", id="standard150-grant-only"),
    pytest.param(lambda w: w.update(access=[]), DENY, "extended500_paid_access_required", id="no-access"),
    pytest.param(lambda w: w["access"].append(access(id="access_501")), DENY, "duplicate_extended500_access",
                 id="duplicate-500-rows"),
    pytest.param(lambda w: set_access(w, owner_user_id="owner_other"), DENY, "access_owner_mismatch",
                 id="access-of-other-owner-same-email"),
    pytest.param(lambda w: set_access(w, app_id="another_app"), DENY, "access_app_mismatch", id="other-app"),
    pytest.param(lambda w: w["user"].update(email="new@example.com"), DENY, "access_owner_mismatch",
                 id="owner-email-changed-since-purchase"),
    pytest.param(lambda w: w.update(access_by_email_override=[access(has_full_access=False)]), DENY,
                 "access_read_conflict", id="two-reads-disagree-on-same-access-id"),
    pytest.param(lambda w: set_access(w, id="access_new"), DENY, "entitlement_rebound",
                 id="access-row-replaced"),
    pytest.param(access_replaced_and_scan_rebound, DENY, "reservation_fingerprint_mismatch",
                 id="access-and-scan-rebound-after-reservation"),
    # Foreign owner / project: fresh records win over the signed claim.
    pytest.param(lambda w: resign(w, owner_user_id="owner_other"), DENY, "owner_mismatch",
                 id="signed-for-other-owner"),
    pytest.param(lambda w: resign(w, project_id="project_other"), DENY, "project_mismatch",
                 id="signed-for-other-project"),
    pytest.param(lambda w: w["project"].update(owner_user_id="owner_other"), DENY, "project_owner_mismatch",
                 id="project-of-other-owner"),
    pytest.param(lambda w: w["project"].update(website_url="https://elsewhere.example.org/"), DENY,
                 "project_domain_mismatch", id="customer-changed-project-url"),
    pytest.param(lambda w: w.update(project=None), DENY, "project_not_found", id="project-deleted"),
    pytest.param(lambda w: w.update(user=None), DENY, "owner_not_found", id="owner-deleted"),
    # Wrong mode / Standard 150 artifacts.
    pytest.param(lambda w: set_task(w, scan_mode="standard_150"), DENY, "task_mode_invalid",
                 id="standard150-task-body"),
    pytest.param(lambda w: set_scan(w, scan_mode="standard_150"), DENY, "scan_mode_not_extended500",
                 id="standard150-scanrun"),
    pytest.param(lambda w: resign(w, canonical_mode="standard_150"), DENY, "grant_mode_invalid",
                 id="grant-for-standard150-mode"),
    pytest.param(lambda w: resign(w, key=STANDARD150_KEY), DENY, "grant_signature_invalid",
                 id="grant-signed-with-standard150-key"),
    # Tampering and client-supplied authority.
    pytest.param(lambda w: w["task"]["signed_grant"].update(proof="0" * 64), DENY, "grant_signature_invalid",
                 id="forged-proof"),
    pytest.param(lambda w: w["task"]["signed_grant"].update(owner_user_id="owner_other"), DENY,
                 "grant_signature_invalid", id="grant-field-edited-without-resign"),
    pytest.param(lambda w: set_task(w, website_url="https://evil.example.net/"), DENY, "grant_task_mismatch",
                 id="task-body-target-edited"),
    pytest.param(lambda w: set_task(w, owner_user_id="owner_other"), DENY, "grant_task_mismatch",
                 id="task-body-owner-edited"),
    pytest.param(lambda w: set_task(w, entitlement_state="active_paid"), DENY, "task_shape_invalid",
                 id="client-paid-flag-in-task"),
    pytest.param(lambda w: set_task(w, plan_id="extended500_lifetime", has_full_access=True), DENY,
                 "task_shape_invalid", id="client-plan-in-task"),
    pytest.param(lambda w: resign(w, audience="fixlist_standard150_worker"), DENY, "grant_context_invalid",
                 id="grant-other-audience"),
    pytest.param(lambda w: w["task"]["signed_grant"].update(extra=True), DENY, "grant_shape_invalid",
                 id="grant-extra-field"),
    pytest.param(lambda w: resign(w, issued=NOW + timedelta(seconds=5)), DENY, "grant_issued_in_future",
                 id="grant-from-future"),
    pytest.param(lambda w: resign(w, issued=NOW - timedelta(seconds=60), expires=NOW + timedelta(seconds=600)),
                 DENY, "grant_time_invalid", id="grant-window-over-300s"),
    pytest.param(lambda w: resign(w, issued=NOW - timedelta(days=32)), DENY, "task_older_than_queue_retention",
                 id="body-older-than-cloud-tasks-retention"),
    # Delayed / duplicate / superseded / replayed deliveries.
    pytest.param(lambda w: set_scan(w, attempt_count=2), SKIP, "superseded_attempt", id="newer-attempt-exists"),
    pytest.param(lambda w: resign(w, attempt_count=2), DENY, "attempt_ahead_of_run", id="attempt-ahead-of-run"),
    pytest.param(lambda w: set_scan(w, status="cancelled"), SKIP, "run_already_terminal",
                 id="delayed-after-terminal"),
    pytest.param(lambda w: set_scan(w, status="crawling"), SKIP, "run_already_started",
                 id="duplicate-after-start"),
    pytest.param(lambda w: set_scan(w, status="paused"), DENY, "run_status_invalid", id="unknown-status"),
    pytest.param(already_claimed, SKIP, "already_picked_up", id="duplicate-delivery-already-picked-up"),
    pytest.param(lambda w: already_claimed(w, slot_too=False), DENY, "reservation_integrity_mismatch",
                 id="claim-marker-on-one-document-only"),
    pytest.param(released, SKIP, "reservation_released", id="delayed-after-verified-release"),
    pytest.param(rebound_to_newer_request, SKIP, "reservation_released", id="owner-moved-to-newer-request"),
    pytest.param(slot_points_elsewhere_while_receipt_active, DENY, "owner_slot_rebound",
                 id="slot-not-owned-by-this-request"),
    pytest.param(lambda w: w["slots"][OWNER].update(state="released"), DENY, "owner_slot_stale",
                 id="stale-slot-status-released"),
    pytest.param(lambda w: w["slots"][OWNER].update(state="dispatch_unknown"), DENY, "owner_slot_stale",
                 id="stale-slot-status-diverged"),
    pytest.param(lambda w: w["slots"].clear(), DENY, "owner_slot_missing", id="no-slot"),
    pytest.param(lambda w: w["receipts"].clear(), DENY, "reservation_receipt_missing",
                 id="task-without-reservation"),
    pytest.param(lambda w: receipt_of(w).update(state="mystery"), DENY, "reservation_state_invalid",
                 id="receipt-state-unknown"),
    pytest.param(lambda w: w["delivery"].update(task_name=w["delivery"]["task_name"][:-1] + "2"), DENY,
                 "delivery_task_mismatch", id="delivery-not-coordinator-task-name"),
    pytest.param(lambda w: w["delivery"].update(queue_name="scan-jobs"), DENY, "delivery_task_mismatch",
                 id="delivered-from-standard150-queue"),
    pytest.param(lambda w: w.update(delivery={}), DENY, "delivery_metadata_missing", id="no-delivery-headers"),
    pytest.param(lambda w: w.update(queue=QUEUE.replace("extended500-test", "extended500-other")), DENY,
                 "reservation_task_mismatch", id="receipt-for-other-queue"),
    # Source path / host and frozen policy.
    pytest.param(lambda w: set_scan(w, website_url="https://shop.example.com/other/"), DENY, "target_mismatch",
                 id="frozen-target-differs"),
    pytest.param(lambda w: set_scan(w, path_prefix="/private/"), DENY, "scope_mismatch", id="frozen-scope-differs"),
    pytest.param(lambda w: set_scan(w, normalized_domain="elsewhere.example.org"), DENY, "domain_mismatch",
                 id="normalized-domain-differs"),
    pytest.param(lambda w: set_scan(w, respect_robots_txt=False, owner_attested_robots_override=True), DENY,
                 "robots_policy_mismatch", id="robots-policy-differs"),
    pytest.param(lambda w: (resign(w, website_url="http://localhost/"),
                            set_scan(w, website_url="http://localhost/", normalized_domain=""),
                            w["project"].update(website_url="http://localhost/")),
                 DENY, "target_not_public", id="non-public-host"),
    pytest.param(lambda w: set_scan(w, admission_access_id=None), DENY, "scan_access_provenance_missing",
                 id="scan-without-access-provenance"),
    pytest.param(lambda w: set_scan(w, access_evidence_state="paid", admission_access_id=None), DENY,
                 "scan_access_provenance_missing", id="scan-paid-hint-is-not-authority"),
    pytest.param(lambda w: (w.update(access=[]), w["project"].update(subscription_plan="done_for_you")), DENY,
                 "extended500_paid_access_required", id="project-plan-is-not-authority"),
    pytest.param(lambda w: w.update(scan=None), RETRY, "scan_run_unavailable", id="scanrun-not-readable"),
    pytest.param(lambda w: w.update(key="short"), RETRY, "grant_signing_unavailable", id="worker-key-missing"),
    pytest.param(lambda w: w.update(queue="projects/p/locations/l/queues/scan-jobs"), RETRY,
                 "worker_queue_configuration_invalid", id="worker-configured-with-150-queue"),
]


@pytest.mark.parametrize(("mutate", "outcome", "reason"), NEGATIVE)
def test_negative_pickup_matrix(mutate, outcome, reason):
    w = world()
    mutate(w)
    decision, via_ports = pure(w), gathered(w)
    assert (decision.outcome, decision.reason) == (outcome, reason)
    assert (via_ports.outcome, via_ports.reason) == (outcome, reason)
    assert decision.binding is None and via_ports.binding is None
    assert decision.execution_enabled is False


def stamp(evidence, name, **changes):
    evidence[name] = replace(evidence[name], **changes)


EVIDENCE_NEGATIVE = [
    pytest.param(lambda e: stamp(e, "scan_run", fetched_at=NOW - timedelta(seconds=31)), RETRY,
                 "scan_run_stale", id="stale-scanrun-read"),
    pytest.param(lambda e: stamp(e, "request_receipt", fetched_at=NOW + timedelta(seconds=1)), RETRY,
                 "request_receipt_stale", id="future-dated-read"),
    pytest.param(lambda e: stamp(e, "owner_slot", fetched_at=None), DENY, "owner_slot_freshness_unproven",
                 id="unstamped-read"),
    pytest.param(lambda e: stamp(e, "access_by_owner", authority="base44_customer_session"), DENY,
                 "access_by_owner_not_service_owned", id="customer-session-access-read"),
    pytest.param(lambda e: stamp(e, "request_receipt", authority=B44), DENY,
                 "request_receipt_not_service_owned", id="receipt-not-from-coordinator"),
    pytest.param(lambda e: e.update(owner_slot={"state": "enqueued"}), DENY, "owner_slot_provenance_invalid",
                 id="raw-dict-not-a-source-read"),
    pytest.param(lambda e: e.pop("owner_user"), DENY, "evidence_incomplete", id="missing-source"),
    pytest.param(lambda e: stamp(e, "access_by_email", value=None), RETRY, "access_read_unavailable",
                 id="access-read-not-a-list"),
]


@pytest.mark.parametrize(("mutate", "outcome", "reason"), EVIDENCE_NEGATIVE)
def test_source_provenance_and_freshness_matrix(mutate, outcome, reason):
    w = world()
    evidence = evidence_from(w)
    mutate(evidence)
    decision = pure(w, evidence)
    assert (decision.outcome, decision.reason) == (outcome, reason)


def test_naive_clock_is_refused():
    w = world()
    w["now"] = NOW.replace(tzinfo=None)
    assert pure(w).reason == "clock_invalid"


# ------------------------------------------------------- gatherer behaviour --

def test_lookup_keys_come_from_fresh_scanrun_and_user_not_task_body():
    w = world()
    src = Sources(w)
    assert gathered(w, src).outcome == AUTHORIZED
    assert src.calls == [
        ("read_scan_run", SCAN),
        ("read_business_project", PROJECT),
        ("read_owner_user", OWNER),
        ("filter_access_by_owner", OWNER),
        ("filter_access_by_email", EMAIL),
        ("read_owner_slot", OWNER),
        ("read_request_receipt", core.receipt_id({"owner_user_id": OWNER, "request_id": REQUEST})),
    ]


def test_tampered_task_never_triggers_an_authority_read():
    w = world()
    set_task(w, owner_user_id="owner_other")
    src = Sources(w)
    assert gathered(w, src).reason == "grant_task_mismatch"
    assert src.calls == []


def test_foreign_owner_stops_before_any_access_or_reservation_read():
    w = world()
    resign(w, owner_user_id="owner_attacker")
    src = Sources(w)
    assert gathered(w, src).reason == "owner_mismatch"
    assert src.calls == [("read_scan_run", SCAN)]


def test_transient_port_failure_is_retry_without_side_effect():
    w = world()
    decision = gathered(w, Sources(w, fail="read_owner_slot"))
    assert (decision.outcome, decision.reason) == (RETRY, "source_unavailable:read_owner_slot")


def test_async_ports_and_label_enforcement():
    w = world()
    assert gathered(w, Sources(w, asynchronous=True)).outcome == AUTHORIZED
    labelled = Sources(w, labels={"read_owner_slot": "cached_replica"})
    assert gathered(w, labelled).reason == "owner_slot_not_service_owned"


def test_port_returning_raw_record_is_refused():
    w = world()

    class Raw(Sources):
        def read_business_project(self, project_id):
            return copy.deepcopy(self.w["project"])

    assert gathered(w, Raw(w)).reason == "business_project_provenance_invalid"


def test_slow_reads_make_early_evidence_stale_and_force_retry():
    w = world()
    ticks = iter(NOW + timedelta(seconds=6 * index) for index in range(100))
    decision = gathered(w, clock=lambda: next(ticks))
    assert (decision.outcome, decision.reason) == (RETRY, "scan_run_stale")


def test_cloud_tasks_headers_map_to_delivery_context():
    _, receipt = reservation()
    headers = {
        "X-CloudTasks-QueueName": "extended500-test",
        "X-CloudTasks-TaskName": receipt["task_name"].rsplit("/", 1)[1],
        "X-CloudTasks-TaskRetryCount": "2", "X-CloudTasks-TaskExecutionCount": "bogus",
    }
    delivery = delivery_from_cloud_tasks_headers(headers)
    assert delivery == {
        "queue_name": "extended500-test", "task_name": receipt["task_name"].rsplit("/", 1)[1],
        "retry_count": 2, "execution_count": None,
    }
    w = world()
    w["delivery"] = delivery
    assert pure(w).outcome == AUTHORIZED


# --------------------------------------------------------- atomic pickup claim --

class MemoryCoordinator:
    """Serialized stand-in for a Firestore transaction (NOT real isolation)."""

    def __init__(self, w):
        self.w, self.lock, self.commits = w, threading.Lock(), 0

    def transact_pickup_claim(self, *, owner_user_id, receipt_id, decide):
        with self.lock:
            result = decide(copy.deepcopy(self.w["slots"].get(owner_user_id)),
                            copy.deepcopy(self.w["receipts"].get(receipt_id)))
            if result["outcome"] == CLAIMED:
                self.w["slots"][owner_user_id] = result["slot_write"]
                self.w["receipts"][receipt_id] = result["receipt_write"]
                self.commits += 1
            return result


def claim(port, decision, execution_id="exec_alpha"):
    return asyncio.run(claim_extended500_pickup(port, decision, execution_id=execution_id, clock=lambda: NOW))


def test_claim_marks_both_documents_and_core_transitions_preserve_it():
    w = world()
    port = MemoryCoordinator(w)
    result = claim(port, authorized_binding(w))
    assert (result.outcome, result.reason) == (CLAIMED, "pickup_claimed")
    assert result.execution_enabled is False
    slot, receipt = w["slots"][OWNER], receipt_of(w)
    assert slot["pickup_claim"] == receipt["pickup_claim"] == dict(result.pickup_claim)
    assert slot["state"] == receipt["state"] == "enqueued"  # core state machine untouched
    # A late dispatch update and the verified release both spread the dicts.
    late = core.decide_dispatch_state(slot, receipt, state="enqueued")
    assert late["slot_write"]["pickup_claim"]["execution_id"] == "exec_alpha"
    done = core.decide_release(slot, receipt, core.canonical_request(entitlement_claim()),
                               terminal_status="complete", verified_terminal=True, released_at=1)
    assert done["receipt_write"]["pickup_claim"]["execution_id"] == "exec_alpha"
    # The coordinator still treats an issuer retry as a plain replay and may
    # re-enqueue the same name (see proposed core.py patch); pickup refuses it.
    assert core.decide_reservation(slot, receipt, entitlement_claim(), QUEUE, issued_at=2)["outcome"] == "replayed"
    replay = pure(w)
    assert (replay.outcome, replay.reason) == (SKIP, "already_picked_up")


def test_concurrent_duplicate_deliveries_have_exactly_one_claim_winner():
    w = world()
    port = MemoryCoordinator(w)
    decisions = [pure(w) for _ in range(8)]  # all evaluated before any claim
    assert all(decision.outcome == AUTHORIZED for decision in decisions)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda item: claim(port, item[1], f"exec_{item[0]}"), enumerate(decisions)))
    winners = [result for result in results if result.outcome == CLAIMED]
    assert len(winners) == 1 and port.commits == 1
    assert sorted(result.reason for result in results if result.outcome != CLAIMED) == ["already_picked_up"] * 7


def test_same_executor_retry_after_unknown_commit_is_idempotent():
    w = world()
    port, decision = MemoryCoordinator(w), authorized_binding(w)
    assert claim(port, decision).reason == "pickup_claimed"
    again = claim(port, decision)
    assert (again.outcome, again.reason) == (CLAIMED, "already_claimed_by_self")
    assert port.commits == 1
    assert claim(port, decision, "exec_beta").reason == "already_picked_up"


def test_claim_refuses_changed_reservation_and_unknown_port_outcomes():
    w = world()
    decision = authorized_binding(w)
    released(w)
    assert claim(MemoryCoordinator(w), decision).reason == "reservation_released"

    w = world()
    decision = authorized_binding(w)
    slot_points_elsewhere_while_receipt_active(w)
    assert claim(MemoryCoordinator(w), decision).reason == "owner_slot_rebound"

    class Exploding:
        def transact_pickup_claim(self, **_kwargs):
            raise TimeoutError("commit outcome unknown")

    class Fabricating:
        def transact_pickup_claim(self, **_kwargs):
            return {"outcome": CLAIMED, "pickup_claim": {"execution_id": "exec_alpha"}}

    for port in (Exploding(), Fabricating()):
        result = claim(port, authorized_binding(world()))
        assert (result.outcome, result.reason) == (RETRY, "claim_outcome_unknown")
    assert claim(MemoryCoordinator(world()), pickup.PickupDecision(SKIP, "superseded_attempt")).outcome == DENY
    assert claim(MemoryCoordinator(world()), authorized_binding(), "bad id!").reason == "execution_id_invalid"
    assert decide_extended500_pickup_claim({}, {}, {"version": pickup.PICKUP_AUTHORIZATION_VERSION},
                                           execution_id="exec_alpha", claimed_at=NOW)["outcome"] == DENY


# ----------------------------------------------------- mid-crawl revalidation --

def picked_up_world():
    w = world()
    decision = authorized_binding(w)
    assert claim(MemoryCoordinator(w), decision).outcome == CLAIMED
    set_scan(w, status="crawling")
    return w, decision.binding


def revalidate(w, binding, execution_id="exec_alpha", sources=None):
    return asyncio.run(revalidate_extended500_pickup(
        binding, sources or Sources(w), execution_id=execution_id, clock=lambda: NOW))


def test_revalidation_continues_while_everything_still_authorizes():
    w, binding = picked_up_world()
    for status in ("crawling", "reviewing"):
        set_scan(w, status=status)
        decision = evaluate_extended500_revalidation(binding, evidence_from(w), execution_id="exec_alpha", now=NOW)
        assert (decision.outcome, decision.reason) == (CONTINUE, "fresh_authorization_still_valid")
        assert decision.may_continue and decision.execution_enabled is False
        assert revalidate(w, binding).outcome == CONTINUE


REVALIDATION_NEGATIVE = [
    pytest.param(lambda w: set_access(w, access_status="revoked"), ABORT, "entitlement_revoked",
                 id="revoked-after-pickup"),
    pytest.param(lambda w: set_access(w, refunded_at="2026-10-29T15:00:00Z"), ABORT,
                 "entitlement_refunded_or_revoked", id="refunded-after-pickup"),
    pytest.param(lambda w: set_access(w, grant_source="manual_grant"), ABORT, "manual_access_not_paid",
                 id="regranted-manually-after-pickup"),
    pytest.param(access_replaced_and_scan_rebound, ABORT, "entitlement_rebound", id="access-rebound-mid-crawl"),
    pytest.param(lambda w: set_scan(w, attempt_count=2), ABORT, "superseded_attempt", id="superseded-mid-crawl"),
    pytest.param(lambda w: set_scan(w, status="cancelled"), ABORT, "run_already_terminal",
                 id="cancelled-mid-crawl"),
    pytest.param(lambda w: set_scan(w, owner_user_id="owner_other"), ABORT, "owner_mismatch",
                 id="scan-owner-changed"),
    pytest.param(lambda w: w["project"].update(owner_user_id="owner_other"), ABORT, "project_owner_mismatch",
                 id="project-transferred"),
    pytest.param(released, ABORT, "reservation_released", id="released-mid-crawl"),
    pytest.param(lambda w: (receipt_of(w)["pickup_claim"].update(execution_id="exec_other"),
                            w["slots"][OWNER]["pickup_claim"].update(execution_id="exec_other")),
                 ABORT, "pickup_claim_lost", id="claim-owned-by-other-executor"),
    pytest.param(lambda w: receipt_of(w).pop("pickup_claim"), ABORT, "pickup_claim_lost",
                 id="claim-never-committed"),
    pytest.param(lambda w: w.update(scan=None), UNAVAILABLE, "scan_run_unavailable", id="scanrun-unreadable"),
]


@pytest.mark.parametrize(("mutate", "outcome", "reason"), REVALIDATION_NEGATIVE)
def test_revalidation_detects_changes_after_pickup(mutate, outcome, reason):
    w, binding = picked_up_world()
    mutate(w)
    decision = evaluate_extended500_revalidation(binding, evidence_from(w), execution_id="exec_alpha", now=NOW)
    assert (decision.outcome, decision.reason) == (outcome, reason)
    assert not decision.may_continue
    via_ports = revalidate(w, binding)
    assert (via_ports.outcome, via_ports.reason) == (outcome, reason)


def test_revalidation_is_fail_closed_on_transport_binding_and_executor_errors():
    w, binding = picked_up_world()
    failed = revalidate(w, binding, sources=Sources(w, fail="filter_access_by_owner"))
    assert (failed.outcome, failed.reason) == (UNAVAILABLE, "source_unavailable:filter_access_by_owner")
    assert not failed.may_continue
    assert revalidate(w, binding, execution_id="exec_beta").reason == "pickup_claim_lost"
    forged = {**dict(binding), "access_id": "access_other"}
    assert revalidate(w, forged).reason == "entitlement_rebound"
    assert revalidate(w, {**dict(binding), "extra": 1}).reason == "binding_invalid"
    assert evaluate_extended500_revalidation(binding, evidence_from(w), execution_id="exec_alpha",
                                             now=NOW.replace(tzinfo=None)).reason == "clock_invalid"


# --------------------------------------------------------------- parity / isolation --

def test_receipt_fingerprint_and_task_name_are_byte_identical_to_coordinator_core():
    request = core.canonical_request(entitlement_claim(attempt_count=7))
    rid = pickup.extended500_receipt_id(request["owner_user_id"], request["request_id"])
    assert rid == core.receipt_id(request)
    assert pickup.extended500_request_fingerprint(request) == core.fingerprint(request)
    assert pickup.extended500_task_name(QUEUE, rid, 7) == core.task_name(QUEUE, request)
    assert pickup.ACTIVE_RESERVATION_STATES == core.ACTIVE_STATES
    assert (pickup.RECEIPT_SCHEMA, pickup.SLOT_SCHEMA, pickup.TASK_PREFIX) == (
        core.RECEIPT_SCHEMA, core.SLOT_SCHEMA, core.TASK_PREFIX)
    assert pickup.GRANT_FIELDS == extended500_job_admission._GRANT_FIELDS


def _load_service(monkeypatch):
    """Load the real coordinator with stub Flask/Firestore (no network)."""
    monkeypatch.syspath_prepend(str(SERVICE_DIR))
    for key, value in KEYS.items():
        monkeypatch.setenv(key, value)
    fake_flask = types.ModuleType("flask")

    class FakeFlask:
        def __init__(self, _name):
            self.config = {}

        def get(self, _path):
            return lambda handler: handler

        def post(self, _path):
            return lambda handler: handler

    fake_flask.Flask, fake_flask.jsonify, fake_flask.request = FakeFlask, (lambda value: value), None
    monkeypatch.setitem(sys.modules, "flask", fake_flask)
    import google
    cloud = types.ModuleType("google.cloud")
    cloud.__path__ = []
    firestore = types.ModuleType("google.cloud.firestore")
    firestore.Client = object
    firestore.transactional = lambda func: func
    cloud.firestore = firestore
    monkeypatch.setitem(sys.modules, "google.cloud", cloud)
    monkeypatch.setitem(sys.modules, "google.cloud.firestore", firestore)
    monkeypatch.setattr(google, "cloud", cloud, raising=False)
    spec = importlib.util.spec_from_file_location("extended500_pickup_service", SERVICE_DIR / "service.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_real_coordinator_task_body_is_accepted_verbatim_and_shape_matches(monkeypatch):
    service = _load_service(monkeypatch)
    assert pickup.GRANT_FIELDS == service.GRANT_KEYS | {"proof"}
    signed = grant()
    request = core.canonical_request(entitlement_claim())
    name = service.core.task_name(service.QUEUE_PATH, request)

    class Credentials:
        valid, token = True, "fixture-token"

    captured = []

    class Response:
        ok, status_code = True, 200

    monkeypatch.setattr(service.google.auth, "default", lambda **_: (Credentials(), None))
    monkeypatch.setattr(service.requests, "post",
                        lambda url, **kwargs: captured.append(kwargs["json"]["task"]) or Response())
    monkeypatch.setattr(service, "QUEUE_ENABLED", True)
    monkeypatch.setattr(service, "WORKER_READY", True)
    assert service.enqueue(request, signed, name) == "enqueued"
    body = json.loads(base64.b64decode(captured[0]["httpRequest"]["body"]))
    assert set(body) == pickup.TASK_FIELDS
    assert body == task_from_grant(signed)
    w = world()
    w["task"], w["delivery"] = body, delivery_for(receipt_of(w))
    assert captured[0]["name"] == receipt_of(w)["task_name"]
    assert pure(w).outcome == AUTHORIZED


def test_js_minted_grant_verifies_in_python_pickup_even_after_expiry():
    fixture = {
        "user": user(), "scan": scan_run(), "access": access(),
        "nowMs": int((NOW - timedelta(minutes=10)).timestamp() * 1000),
    }
    script = """
import { mintExtended500AdmissionEvidence } from './src/lib/extended500EntitlementIssuer.js';
const f = JSON.parse(process.env.PICKUP_FIXTURE);
const out = await mintExtended500AdmissionEvidence({
  user: f.user, scan: f.scan, accessRows: [f.access], nowMs: f.nowMs,
  entitlementSigningKey: process.env.ENTITLEMENT_KEY, grantSigningKey: process.env.GRANT_KEY,
});
process.stdout.write(JSON.stringify(out));
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script], cwd=ROOT, text=True, capture_output=True,
        check=True, timeout=25,
        env={**os.environ, "PICKUP_FIXTURE": json.dumps(fixture),
             "ENTITLEMENT_KEY": KEYS["EXTENDED500_ENTITLEMENT_SIGNING_KEY"], "GRANT_KEY": KEY},
    )
    minted = json.loads(result.stdout)
    assert minted["ok"] is True, minted
    w = world()
    w["task"] = task_from_grant(minted["preflight_grant"])
    decision = pure(w)
    assert decision.outcome == AUTHORIZED and decision.grant_expired is True
    w["task"]["signed_grant"]["attempt_count"] = 2
    w["task"]["attempt_count"] = 2
    assert pure(w).reason == "grant_signature_invalid"


def test_module_is_pure_unwired_and_isolated_from_standard150():
    source_path = Path(pickup.__file__)
    tree = ast.parse(source_path.read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(("." * node.level) + (node.module or ""))
    assert imported <= {
        "__future__", "dataclasses", "datetime", "hashlib", "hmac", "inspect", "json", "re",
        "types", "typing", "urllib.parse", ".authority_seal", ".extended500_job_admission",
    }, imported
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert not names & {"run_scan", "mark_scan_started", "identity_matches", "read_scan_run", "httpx"}
    main_source = (ROOT / "scanner-api" / "app" / "main.py").read_text()
    assert "extended500_pickup_authorization" not in main_source
    assert "standard_150" not in source_path.read_text()
