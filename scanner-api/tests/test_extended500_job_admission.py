"""Adversarial Extended 500 policy and disabled read-only worker preflight.

No real ScanRun, entitlement issuer, crawl, billing or persistence is used.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from app.authority_seal import create_authority_seal
from app.extended500_job_admission import (
    EXTENDED500_GRANT_AUDIENCE,
    EXTENDED500_GRANT_VERSION,
    evaluate_extended500_preflight,
)
from app import main as main_module


KEY = "fixture-dedicated-admission-key-" + "b" * 32
NOW = datetime(2026, 10, 26, 20, 0, tzinfo=timezone.utc)


def _job():
    return {
        "scan_id": "scan-ext500-one",
        "request_id": "request-ext500-one",
        "idempotency_key": "idem-ext500-one",
        "project_id": "project-ext500-one",
        "owner_user_id": "owner-ext500-one",
        "attempt_count": 3,
        "website_url": "https://example.com/store/",
        "path_prefix": "/store/",
        "scan_mode": "extended_500",
        "respect_robots_txt": True,
        "owner_attested_robots_override": False,
    }


def _frozen(job=None):
    job = job or _job()
    return {
        "id": job["scan_id"],
        "request_id": job["request_id"],
        "idempotency_key": job["idempotency_key"],
        "project_id": job["project_id"],
        "owner_user_id": job["owner_user_id"],
        "attempt_count": job["attempt_count"],
        "website_url": job["website_url"],
        "normalized_domain": "example.com",
        "path_prefix": job["path_prefix"],
        "scan_mode": "extended_500",
        "status": "queued",
        "respect_robots_txt": True,
        "owner_attested_robots_override": False,
    }


def _grant(job=None, *, issued=None, expires=None, **replacements):
    job = job or _job()
    document = {
        "version": EXTENDED500_GRANT_VERSION,
        "audience": EXTENDED500_GRANT_AUDIENCE,
        "canonical_mode": "extended_500",
        "scan_id": job["scan_id"],
        "owner_user_id": job["owner_user_id"],
        "project_id": job["project_id"],
        "request_id": job["request_id"],
        "idempotency_key": job["idempotency_key"],
        "attempt_count": job["attempt_count"],
        "website_url": job["website_url"],
        "path_prefix": job["path_prefix"],
        "respect_robots_txt": job["respect_robots_txt"],
        "owner_attested_robots_override": job["owner_attested_robots_override"],
        "issued_at": (issued or (NOW - timedelta(seconds=15))).isoformat().replace("+00:00", "Z"),
        "expires_at": (expires or (NOW + timedelta(seconds=120))).isoformat().replace("+00:00", "Z"),
    }
    document.update(replacements)
    return {**document, "proof": create_authority_seal(document, KEY)}


def test_exact_server_minted_grant_is_necessary_but_never_sufficient_to_crawl():
    job = _job()
    decision = evaluate_extended500_preflight(job, _frozen(), _grant(), KEY, now=NOW)
    assert decision == "verified_read_only"
    assert _frozen()["scan_mode"] == "extended_500"


@pytest.mark.parametrize(("field", "value", "denial"), [
    ("scan_mode", "standard_150", "mode_not_frozen"),
    ("scan_id", "scan-other", "scan_identity_mismatch"),
    ("request_id", "other", "owner_request_identity_mismatch"),
    ("idempotency_key", "other", "owner_request_identity_mismatch"),
    ("project_id", "other", "owner_request_identity_mismatch"),
    ("owner_user_id", "other", "owner_request_identity_mismatch"),
    ("attempt_count", 2, "superseded_attempt"),
    ("attempt_count", True, "attempt_invalid"),
    ("attempt_count", 0, "attempt_invalid"),
    ("website_url", "https://other.com/store/", "target_mismatch"),
    ("path_prefix", "/", "scope_mismatch"),
    ("respect_robots_txt", False, "robots_policy_mismatch"),
    ("respect_robots_txt", 1, "robots_policy_invalid"),
    ("owner_attested_robots_override", True, "robots_policy_mismatch"),
])
def test_task_cannot_override_frozen_scan_identity(field, value, denial):
    job = _job()
    job[field] = value
    assert evaluate_extended500_preflight(job, _frozen(), _grant(), KEY, now=NOW) == denial


@pytest.mark.parametrize(("field", "value", "denial"), [
    ("scan_mode", "standard_150", "mode_not_frozen"),
    ("status", "complete", "run_not_queued"),
    ("status", "crawling", "run_not_queued"),
    ("attempt_count", 4, "superseded_attempt"),
    ("request_id", None, "owner_request_identity_mismatch"),
    ("owner_user_id", None, "owner_request_identity_mismatch"),
    ("idempotency_key", None, "owner_request_identity_mismatch"),
    ("path_prefix", "/private/", "scope_mismatch"),
    ("website_url", "https://example.com/private/", "target_mismatch"),
    ("normalized_domain", "elsewhere.example", "domain_mismatch"),
    ("owner_attested_robots_override", True, "robots_policy_mismatch"),
])
def test_cached_or_other_mode_scan_cannot_authorize_claim(field, value, denial):
    frozen = _frozen()
    frozen[field] = value
    assert evaluate_extended500_preflight(_job(), frozen, _grant(), KEY, now=NOW) == denial


@pytest.mark.parametrize(("value", "denial"), [
    ({"canonical_mode": "standard_150"}, "grant_mode_invalid"),
    ({"audience": "fixlist_standard150_worker"}, "grant_context_invalid"),
    ({"scan_id": "other"}, "grant_identity_mismatch"),
    ({"project_id": "other"}, "grant_identity_mismatch"),
    ({"attempt_count": 2}, "grant_identity_mismatch"),
    ({"attempt_count": True}, "grant_identity_mismatch"),
    ({"website_url": "https://example.com/other"}, "grant_identity_mismatch"),
    ({"respect_robots_txt": False}, "grant_identity_mismatch"),
    ({"respect_robots_txt": 1}, "grant_identity_mismatch"),
    ({"owner_attested_robots_override": 0}, "grant_identity_mismatch"),
])
def test_even_validly_signed_other_identity_or_purpose_grant_is_denied(value, denial):
    assert evaluate_extended500_preflight(
        _job(), _frozen(), _grant(**value), KEY, now=NOW,
    ) == denial


def test_expired_future_or_overlong_grant_and_signature_tampering_fail_closed():
    cases = [
        _grant(expires=NOW - timedelta(seconds=1)),
        _grant(issued=NOW + timedelta(seconds=1)),
        _grant(issued=NOW - timedelta(seconds=500)),
        _grant(issued=NOW + timedelta(seconds=1), expires=NOW + timedelta(seconds=8)),
    ]
    for grant in cases:
        assert evaluate_extended500_preflight(_job(), _frozen(), grant, KEY, now=NOW) == "grant_expired_or_out_of_window"

    tampered = _grant()
    tampered["owner_user_id"] = "different-owner"
    assert evaluate_extended500_preflight(_job(), _frozen(), tampered, KEY, now=NOW) == "grant_identity_mismatch"
    tampered = _grant()
    tampered["proof"] = "0" * 64
    assert evaluate_extended500_preflight(_job(), _frozen(), tampered, KEY, now=NOW) == "grant_signature_invalid"
    assert evaluate_extended500_preflight(_job(), _frozen(), _grant(), "short", now=NOW) == "grant_signing_unavailable"
    malformed = _grant()
    malformed["new_untrusted_field"] = True
    assert evaluate_extended500_preflight(_job(), _frozen(), malformed, KEY, now=NOW) == "grant_shape_invalid"


def test_preflight_route_defaults_disabled_and_never_reads_or_crawls(monkeypatch):
    monkeypatch.delenv("FIXLIST_EXTENDED500_PREFLIGHT_ENABLED", raising=False)
    monkeypatch.setattr(main_module, "require_cloud_tasks_oidc", lambda _token: None)

    async def refuse_read(_client, _scan_id):
        raise AssertionError("read_scan_run must not run when disabled")

    async def refuse_crawl(**_kwargs):
        raise AssertionError("preflight must never crawl")

    monkeypatch.setattr(main_module, "read_scan_run", refuse_read)
    monkeypatch.setattr(main_module, "run_scan", refuse_crawl)
    with TestClient(main_module.app) as client:
        response = client.post("/scan-job-extended500-preflight", json={
            **_job(), "signed_grant": _grant(),
        })
    assert response.status_code == 503
    assert "disabled" in response.json()["detail"]


def test_enabled_preflight_reads_only_and_never_grants_admission(monkeypatch):
    monkeypatch.setenv("FIXLIST_EXTENDED500_PREFLIGHT_ENABLED", "true")
    monkeypatch.setenv("EXTENDED500_ADMISSION_SIGNING_KEY", KEY)
    token_seen = []

    def verify_header(token):
        token_seen.append(token)
        if token != "Bearer test-oidc-under-IAM":
            raise HTTPException(status_code=401, detail="Unauthorized")

    async def read_only(_client, scan_id):
        assert scan_id == _job()["scan_id"]
        return _frozen()

    async def refuse_crawl(**_kwargs):
        raise AssertionError("preflight must never crawl")

    monkeypatch.setattr(main_module, "require_cloud_tasks_oidc", verify_header)
    monkeypatch.setattr(main_module, "read_scan_run", read_only)
    monkeypatch.setattr(main_module, "run_scan", refuse_crawl)
    with TestClient(main_module.app) as client:
        payload = {**_job(), "signed_grant": _grant(
            issued=datetime.now(timezone.utc) - timedelta(seconds=15),
            expires=datetime.now(timezone.utc) + timedelta(seconds=120),
        )}
        response = client.post(
            "/scan-job-extended500-preflight", json=payload,
            headers={"authorization": "Bearer test-oidc-under-IAM"},
        )
        denied = client.post(
            "/scan-job-extended500-preflight",
            json={**payload, "scan_mode": "standard_150"},
            headers={"authorization": "Bearer test-oidc-under-IAM"},
        )
        missing_header = client.post("/scan-job-extended500-preflight", json=payload)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "verified": True, "admitted": False, "execution_enabled": False,
        "scan_mode": "extended_500",
        "scan_id": "scan-ext500-one",
        "reason": "atomic_admission_and_persistence_not_implemented",
    }
    assert denied.status_code == 409
    assert denied.json()["detail"] == "mode_not_frozen"
    assert missing_header.status_code == 401
    assert token_seen == [
        "Bearer test-oidc-under-IAM",
        "Bearer test-oidc-under-IAM",
        None,
    ]
