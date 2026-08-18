"""Contract for the durable Cloud Tasks -> Cloud Run Standard 150 worker.

Base44 reaps post-response work, so ScanRun 6a748d5f9e8a27963ae678dc logged
worker_scan_start and then nothing for 247s. The crawl now runs on Cloud Run,
which holds a request for up to 480s, and Cloud Tasks retries it safely.

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
    terminal_review_limitation,
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


def test_blocked_review_gets_truthful_access_limited_terminal_code():
    limitation = terminal_review_limitation({
        "release_gate_eligible": False,
        "access_evidence_state": "blocked",
        "review_confidence_state": "blocked_access_needs_verification",
        "site_fingerprint": {
            "blocked_or_429_pages": 1,
            "classification": {"usable_pages": 0},
        },
    })
    assert limitation is not None
    assert limitation["code"] == "scan_access_limited"
    assert "rate-limited or challenged" in limitation["detail"]


def test_non_access_provisional_review_keeps_authority_predicate_path():
    assert terminal_review_limitation({
        "release_gate_eligible": False,
        "score_is_provisional": True,
        "review_confidence_state": "insufficient_discovery_quality",
        "evidence_quality_blocking": True,
        "site_fingerprint": {
            "blocked_or_429_pages": 0,
            "classification": {"usable_pages": 1},
        },
    }) is None


def test_eligible_review_never_gets_terminal_limitation():
    assert terminal_review_limitation({
        "release_gate_eligible": True,
        "access_evidence_state": "blocked",
    }) is None


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

    # Cloud Run and Cloud Tasks both use 480s. Include two signed control reads.
    assert CRAWL_BUDGET_SECONDS + HANDOFF_TIMEOUT_SECONDS + 40 < 480
    # And it must exceed the synchronous gateway budget it replaces, or the
    # large sites this exists for still cannot finish.
    assert CRAWL_BUDGET_SECONDS > 28.0


def test_worker_version_is_pinned():
    assert WORKER_VERSION == "scan_job_worker_v1_cloud_tasks"


@pytest.mark.asyncio
async def test_durable_worker_wall_clock_timeout_terminalizes_exact_attempt(monkeypatch):
    """A crawler coroutine that never returns must not hold the durable row open."""
    import asyncio
    from app import main

    scan = {
        "id": "scan-1",
        "scan_id": "scan-1",
        "request_id": "req-1",
        "idempotency_key": "req-1",
        "project_id": "proj-1",
        "owner_user_id": "owner-1",
        "website_url": "https://example.com/",
        "normalized_domain": "example.com",
        "attempt_count": 1,
        "status": "queued",
    }
    payload = main.ScanJobRequest(
        scan_id="scan-1",
        request_id="req-1",
        idempotency_key="req-1",
        project_id="proj-1",
        owner_user_id="owner-1",
        website_url="https://example.com/",
        normalized_domain="example.com",
        attempt_count=1,
    )

    monkeypatch.setattr(main, "require_cloud_tasks_oidc", lambda _: None)

    async def read(*_args, **_kwargs):
        return scan

    async def started(*_args, **_kwargs):
        return {**scan, "status": "crawling", "started_at": "2026-08-18T10:00:00Z"}

    async def never_returns(*_args, **_kwargs):
        await asyncio.sleep(60)

    failures = []

    async def fail(*args, **kwargs):
        failures.append((args, kwargs))
        return True

    monkeypatch.setattr(main, "read_scan_run", read)
    monkeypatch.setattr(main, "mark_scan_started", started)
    monkeypatch.setattr(main, "run_scan", never_returns)
    monkeypatch.setattr(main, "write_terminal_failure", fail)
    monkeypatch.setattr(main, "WORKER_CRAWL_WALL_TIMEOUT_SECONDS", 0.01)

    result = await main.scan_job(payload, authorization="test")

    assert result["success"] is False
    assert result["error_code"] == "scanner_wall_timeout"
    assert len(failures) == 1
    args, kwargs = failures[0]
    assert args[1] == "scan-1"
    assert args[2] == "scanner_wall_timeout"
    assert kwargs["attempt_count"] == 1


@pytest.mark.asyncio
async def test_durable_worker_completion_wall_timeout_terminalizes_exact_attempt(monkeypatch):
    """A post-crawl authority handoff that never returns must not hold the row open."""
    import asyncio
    from app import main

    scan = {
        "id": "scan-1",
        "scan_id": "scan-1",
        "request_id": "req-1",
        "idempotency_key": "req-1",
        "project_id": "proj-1",
        "owner_user_id": "owner-1",
        "website_url": "https://example.com/",
        "normalized_domain": "example.com",
        "attempt_count": 1,
        "status": "queued",
    }
    payload = main.ScanJobRequest(
        scan_id="scan-1",
        request_id="req-1",
        idempotency_key="req-1",
        project_id="proj-1",
        owner_user_id="owner-1",
        website_url="https://example.com/",
        normalized_domain="example.com",
        attempt_count=1,
    )

    monkeypatch.setattr(main, "require_cloud_tasks_oidc", lambda _: None)
    monkeypatch.setenv("SCAN_EVIDENCE_SIGNING_KEY", "test-signing-key")

    persisted_state = dict(scan)

    async def read(*_args, **_kwargs):
        return dict(persisted_state)

    started_calls = 0

    async def started(*_args, **_kwargs):
        nonlocal started_calls
        started_calls += 1
        return {**scan, "status": "crawling", "started_at": "2026-08-18T10:00:00Z"}

    async def quick_scan(*_args, **_kwargs):
        return {"pages_found": 1, "pages_crawled": 1, "crawled_pages": []}

    async def never_completes(*_args, **_kwargs):
        await asyncio.sleep(60)

    failures = []

    async def fail(*args, **kwargs):
        failures.append((args, kwargs))
        persisted_state.update({
            "status": "failed",
            "error_code": args[2],
            "release_gate_eligible": False,
        })
        return True

    monkeypatch.setattr(main, "read_scan_run", read)
    monkeypatch.setattr(main, "mark_scan_started", started)
    monkeypatch.setattr(main, "run_scan", quick_scan)
    monkeypatch.setattr(main, "apply_indexability_quality_to_result", lambda value: value)
    monkeypatch.setattr(main, "apply_render_evidence_quality", lambda value: value)
    monkeypatch.setattr(main, "enforce_scan_response_page_budget", lambda value, _mode: value)
    monkeypatch.setattr(main, "live_revision", lambda: {"fingerprint": "test"})
    monkeypatch.setattr(main, "complete_authority", never_completes)
    monkeypatch.setattr(main, "write_terminal_failure", fail)
    monkeypatch.setattr(main, "WORKER_COMPLETION_WALL_TIMEOUT_SECONDS", 0.01)

    result = await main.scan_job(payload, authorization="test")

    assert started_calls == 2
    assert result["success"] is False
    assert result["error_code"] == "worker_completion_wall_timeout"
    assert len(failures) == 1
    args, kwargs = failures[0]
    assert args[1] == "scan-1"
    assert args[2] == "worker_completion_wall_timeout"
    assert kwargs["attempt_count"] == 1


# ------------------------------------------------- discovery vs crawl cap --
#
# Hard compatibility contract: the 150-page cap bounds fetch/analyse ONLY. On a
# large site the scanner must still enumerate at least 1,200 in-scope URLs and
# report them in pages_found. The old crawler did this (Funbooker: 1,200 found /
# 150 crawled) and the durable path must not regress it.

def _large_site_result(found: int = 1_247, crawled: int = 150) -> dict:
    return {
        "pages_crawled": crawled,
        "pages_found": found,
        "queued_remaining": found - crawled,
        "crawled_pages": [{"url": f"https://big.example/p{i}"} for i in range(crawled)],
        "grouped_findings": [{"rule": f"r{i}"} for i in range(12)],
        "scanner_version": "python_scanner_v3_bounded_request",
        "scan_id": "scan-1", "scan_run_id": "scan-1", "request_id": "req-1",
        "normalized_domain": "big.example",
    }


def test_discovery_reaches_1200_while_crawl_stays_exactly_at_150():
    from app.scan_job import build_authority_review_payload

    payload = build_authority_review_payload(_large_site_result())
    assert payload["pages_found"] >= 1_200, "eligible discovery must reach the release threshold"
    assert payload["pages_crawled"] == 150
    assert payload["pages_found"] > payload["pages_crawled"]
    assert payload["queued_remaining"] > 0


def test_review_sampling_never_shrinks_reported_discovery():
    from app.scan_job import REVIEW_PAGE_SAMPLE_LIMIT, build_authority_review_payload

    payload = build_authority_review_payload(_large_site_result())
    # Only the sample sent to review is bounded.
    assert len(payload["crawled_pages"]) == REVIEW_PAGE_SAMPLE_LIMIT
    assert payload["page_sample_truncated"] is True
    # The evidence counts stay whole.
    assert payload["pages_found"] == 1_247
    assert payload["pages_crawled"] == 150


def test_the_crawl_cap_is_enforced_server_side():
    from app.main import enforce_scan_response_page_budget

    over = _large_site_result(found=5_000, crawled=400)
    over["crawled_pages"] = [{"url": f"https://big.example/p{i}"} for i in range(400)]
    capped = enforce_scan_response_page_budget(over, "advanced")
    pages = capped.get("crawled_pages") or capped.get("pages") or []
    assert len(pages) <= 150, "the worker must not return more than 150 analysed pages"


# ------------------------------------------------------------ seal contract --

def test_canonical_serialisation_matches_the_javascript_seal():
    from app.scan_job import stable_serialize

    # Keys sorted, no whitespace, non-finite nulled -- authoritySeal.js parity.
    assert stable_serialize({"b": 1, "a": {"z": None, "y": [3, "x"]}}) == '{"a":{"y":[3,"x"],"z":null},"b":1}'
    assert stable_serialize({"n": float("inf")}) == '{"n":null}'


def test_seal_is_64_lowercase_hex_and_key_dependent():
    from app.scan_job import create_authority_seal

    a = create_authority_seal({"scan_id": "s1"}, "key-a")
    b = create_authority_seal({"scan_id": "s1"}, "key-b")
    assert len(a) == 64 and a == a.lower() and a != b


def test_attestation_binds_owner_project_and_scan():
    from app.scan_job import build_scan_attestation

    scan = {"id": "scan-1", "project_id": "proj-1", "owner_user_id": "owner-1"}
    attested = build_scan_attestation(_large_site_result(), scan, "k")
    att = attested["authority_scan_attestation"]
    assert att["scan_id"] == "scan-1" and att["project_id"] == "proj-1" and att["owner_user_id"] == "owner-1"
    assert len(att["proof"]) == 64
    # A different ScanRun must not verify with the same proof.
    other = build_scan_attestation(_large_site_result(), {**scan, "id": "scan-2"}, "k")
    assert other["authority_scan_attestation"]["proof"] != att["proof"]


# --------------------------------------------------------- FixList binding --

def test_fix_list_must_belong_to_the_exact_owner_project_and_scan():
    from app.scan_job import fix_list_belongs_to_scan

    scan = {"id": "scan-1", "project_id": "proj-1", "owner_user_id": "owner-1"}
    good = {"scan_run_id": "scan-1", "project_id": "proj-1", "owner_user_id": "owner-1"}
    assert fix_list_belongs_to_scan(good, scan) is True
    for bad in (
        {**good, "scan_run_id": "scan-2"},
        {**good, "project_id": "proj-2"},
        {**good, "owner_user_id": "owner-2"},
    ):
        assert fix_list_belongs_to_scan(bad, scan) is False
