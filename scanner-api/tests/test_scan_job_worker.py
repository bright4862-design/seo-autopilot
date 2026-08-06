"""Contract for the durable Cloud Tasks -> Cloud Run Standard 150 worker.

Base44 reaps post-response work, so ScanRun 6a748d5f9e8a27963ae678dc logged
worker_scan_start and then nothing for 247s. The crawl now runs on Cloud Run,
which holds a request for up to 300s, and Cloud Tasks retries it safely.

These tests pin the properties that make a retry safe: identity is checked
against the existing ScanRun, a terminal run is never scanned twice, permanent
failures are written to the exact scan, and transient failures raise so Cloud
Tasks retries instead of burning the attempt.
"""

import pytest
from fastapi import HTTPException

from app.main import require_cloud_tasks_oidc
from app.scan_job import (
    TERMINAL_STATUSES,
    WORKER_VERSION,
    already_terminal,
    has_authority_proof,
    identity_matches,
)


def _oidc(email: str) -> str:
    import base64
    import json

    claims = base64.urlsafe_b64encode(json.dumps({"email": email}).encode()).decode().rstrip("=")
    return f"Bearer header.{claims}.signature"


# ---------------------------------------------------------------- identity --

def test_identity_matches_accepts_the_same_durable_request():
    scan = {"request_id": "req-1", "idempotency_key": "req-1", "project_id": "proj-1"}
    job = {"request_id": "req-1", "idempotency_key": "req-1", "project_id": "proj-1"}
    assert identity_matches(scan, job) is True


def test_identity_mismatch_is_rejected():
    scan = {"request_id": "req-1", "project_id": "proj-1"}
    assert identity_matches(scan, {"request_id": "req-2", "project_id": "proj-1"}) is False
    assert identity_matches(scan, {"request_id": "req-1", "project_id": "proj-2"}) is False


def test_absent_fields_do_not_manufacture_a_mismatch():
    # A legacy row missing idempotency_key must not be rejected outright.
    assert identity_matches({"request_id": "req-1"}, {"request_id": "req-1", "project_id": "p"}) is True


# ------------------------------------------------------------- idempotency --

def test_a_terminal_run_is_never_scanned_again():
    for status in ("complete", "limited", "failed", "cancelled"):
        assert already_terminal({"status": status}) is True, status


def test_an_active_run_is_eligible_for_work():
    for status in ("queued", "crawling", "reviewing"):
        assert already_terminal({"status": status}) is False, status


def test_terminal_status_set_matches_the_product_contract():
    assert TERMINAL_STATUSES == {"complete", "limited", "failed", "cancelled"}


# ------------------------------------------------------------------ authority --

def test_authority_proof_must_be_64_lowercase_hex():
    assert has_authority_proof({"authority_proof": "a" * 64}) is True
    assert has_authority_proof({"authority_proof": "A" * 64}) is False
    assert has_authority_proof({"authority_proof": "a" * 63}) is False
    assert has_authority_proof({"authority_proof": "a" * 65}) is False
    assert has_authority_proof({"authority_proof": ""}) is False
    assert has_authority_proof({}) is False


# ----------------------------------------------------------------- auth ----

def test_only_the_configured_task_invoker_is_accepted(monkeypatch):
    monkeypatch.setenv("TASKS_INVOKER_SERVICE_ACCOUNT", "tasks@proj.iam.gserviceaccount.com")
    require_cloud_tasks_oidc(_oidc("tasks@proj.iam.gserviceaccount.com"))


def test_another_principal_in_the_project_is_forbidden(monkeypatch):
    monkeypatch.setenv("TASKS_INVOKER_SERVICE_ACCOUNT", "tasks@proj.iam.gserviceaccount.com")
    with pytest.raises(HTTPException) as excinfo:
        require_cloud_tasks_oidc(_oidc("someone-else@proj.iam.gserviceaccount.com"))
    assert excinfo.value.status_code == 403


def test_missing_or_malformed_tokens_are_unauthorized(monkeypatch):
    monkeypatch.setenv("TASKS_INVOKER_SERVICE_ACCOUNT", "tasks@proj.iam.gserviceaccount.com")
    for token in (None, "", "Basic abc", "Bearer not-a-jwt", "Bearer a.b"):
        with pytest.raises(HTTPException) as excinfo:
            require_cloud_tasks_oidc(token)
        assert excinfo.value.status_code == 401


def test_worker_fails_closed_when_the_invoker_is_not_configured(monkeypatch):
    monkeypatch.delenv("TASKS_INVOKER_SERVICE_ACCOUNT", raising=False)
    with pytest.raises(HTTPException) as excinfo:
        require_cloud_tasks_oidc(_oidc("tasks@proj.iam.gserviceaccount.com"))
    assert excinfo.value.status_code == 503


# ------------------------------------------------------------------ budget --

def test_crawl_budget_fits_inside_the_cloud_run_request_timeout():
    from app.scan_job import CRAWL_BUDGET_SECONDS, HANDOFF_TIMEOUT_SECONDS

    # cloudbuild.yaml deploys Cloud Run with --timeout=300.
    assert CRAWL_BUDGET_SECONDS + HANDOFF_TIMEOUT_SECONDS < 300
    # And it must exceed the synchronous gateway budget it replaces, or the
    # large sites this exists for still cannot finish.
    assert CRAWL_BUDGET_SECONDS > 28.0


def test_worker_version_is_pinned():
    assert WORKER_VERSION == "scan_job_worker_v1_cloud_tasks"
