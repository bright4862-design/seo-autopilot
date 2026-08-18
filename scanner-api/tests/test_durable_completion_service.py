"""Regression contract for the signed durable worker boundaries."""

from pathlib import Path

from app.scan_job import (
    COMPLETION_VERSION,
    CONTROL_VERSION,
    WORKER_VERSION,
    _service_headers,
    build_completion_envelope,
    build_control_envelope,
    create_authority_seal,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_SOURCE = REPO_ROOT / "base44/functions/persistDurableScanAuthority/index.ts"
CONTROL_SOURCE = REPO_ROOT / "base44/functions/durableScanWorkerControl/index.ts"
WORKER_SOURCE = REPO_ROOT / "scanner-api/app/scan_job.py"


def _scan_result() -> dict:
    return {
        "scanner_version": "python_scanner_v3_bounded_request",
        "scanner_build_revision": "authenticated_health_probe_v1",
        "advanced_scan_backend": "python_scanner_api",
        "deno_fallback_used": False,
        "beta_revision_fingerprint": "03dbfa67f4b708cf",
        "request_id": "req-1",
        "idempotency_key": "req-1",
        "scan_id": "scan-1",
        "scan_run_id": "scan-1",
        "submitted_url": "https://big.example/",
        "website_url": "https://big.example/",
        "final_url": "https://big.example/page-1",
        "normalized_domain": "big.example",
        "pages_found": 1_247,
        "pages_crawled": 150,
        "crawled_pages": [],
    }


def _review() -> dict:
    return {
        "review_version": "python_review_v2_structural_marketplace",
        "review_evidence_calibration_version": "review_evidence_calibration_v6_health_score_v2",
        "archetype_classifier_version": "archetype_classifier_v9_local_business_hospitality",
        "ai_review_backend": "python_review_api",
        "python_review_fallback_used": False,
        "release_gate_eligible": True,
        "score_is_provisional": False,
        "evidence_quality_blocking": False,
        "beta_revision_fingerprint": "03dbfa67f4b708cf",
        "metadata_evidence_version": "metadata-v1",
        "title_evidence_version": "title-v1",
        "recommendations": [],
    }


def test_completion_envelope_binds_owner_scan_project_request_and_review():
    scan = {
        "id": "scan-1",
        "project_id": "project-1",
        "owner_user_id": "owner-1",
        "request_id": "req-1",
        "idempotency_key": "req-1",
        "attempt_count": 2,
    }
    envelope = build_completion_envelope(scan, _scan_result(), _review(), "secret")
    assert envelope["version"] == COMPLETION_VERSION
    assert envelope["identity"] == {
        "owner_user_id": "owner-1",
        "scan_id": "scan-1",
        "project_id": "project-1",
        "request_id": "req-1",
        "idempotency_key": "req-1",
        "normalized_domain": "big.example",
        "attempt_count": "2",
    }
    signed = {key: envelope[key] for key in ("version", "identity", "scan", "review")}
    assert envelope["proof"] == create_authority_seal(signed, "secret")
    assert len(envelope["proof"]) == 64


def test_review_changes_the_completion_proof():
    scan = {
        "id": "scan-1", "project_id": "project-1", "owner_user_id": "owner-1",
        "request_id": "req-1", "idempotency_key": "req-1",
    }
    first = build_completion_envelope(scan, _scan_result(), _review(), "secret")
    changed = {**_review(), "health_score": 77}
    second = build_completion_envelope(scan, _scan_result(), changed, "secret")
    assert first["proof"] != second["proof"]


def test_control_envelopes_bind_action_scan_and_failure():
    read = build_control_envelope("read", "secret", scan_id="scan-1")
    sweep = build_control_envelope("sweep", "secret")
    assert sweep["version"] == CONTROL_VERSION
    assert sweep["action"] == "sweep"
    assert sweep["scan_id"] is None and sweep["identity"] is None and sweep["failure"] is None
    assert len(sweep["proof"]) == 64
    assert read["version"] == CONTROL_VERSION
    assert read["action"] == "read"
    assert read["scan_id"] == "scan-1"
    assert len(read["proof"]) == 64

    identity = {
        "owner_user_id": "owner-1",
        "scan_id": "scan-1",
        "project_id": "project-1",
        "request_id": "req-1",
        "idempotency_key": "req-1",
        "normalized_domain": "big.example",
    }
    start = build_control_envelope("start", "secret", identity=identity)
    assert start["action"] == "start"
    assert start["identity"] == identity
    assert len(start["proof"]) == 64

    failure = build_control_envelope(
        "fail", "secret", identity=identity,
        failure={"code": "scanner_failed", "detail": "Stopped."},
    )
    changed = build_control_envelope(
        "fail", "secret", identity=identity,
        failure={"code": "scanner_failed", "detail": "Different."},
    )
    assert failure["proof"] != changed["proof"]


def test_worker_function_headers_do_not_claim_external_service_role():
    headers = _service_headers()
    assert headers["X-FixList-Worker"] == WORKER_VERSION
    assert headers["content-type"] == "application/json"
    assert "Base44-Service-Authorization" not in headers
    assert "Base44-App-Id" not in headers
    assert "authorization" not in headers


def test_hosted_functions_use_supported_service_role_and_signed_envelopes():
    persistence = SERVICE_SOURCE.read_text(encoding="utf-8")
    control = CONTROL_SOURCE.read_text(encoding="utf-8")
    for source in (persistence, control):
        assert "auth.me" not in source
        assert "createClientFromRequest(req)" in source
        assert ".asServiceRole.entities" in source
        assert "Base44-Service-Authorization" not in source
        assert 'X-FixList-Worker' in source
        assert "verifyAuthoritySeal" in source
    assert "validateCurrentIdentity" in persistence
    assert "validateBoundIdentity" in control
    assert '["start", "fail"].includes(action)' in control
    assert 'action === "sweep"' in control
    assert 'reconcileDurableScans(entities)' in control
    assert 'status: "crawling"' in control
    assert 'started_at:' in control


def test_authority_is_verified_before_paid_independent_terminal_completion():
    source = SERVICE_SOURCE.read_text(encoding="utf-8")
    assert "entities.Access" not in source
    assert "scans_used" not in source
    stage_index = source.index("await entities.ScanRun.update(identity.scan_id, stagedScanFields)")
    verify_index = source.index("const authorityStaged = Boolean(")
    terminal_index = source.index("await entities.ScanRun.update(identity.scan_id, scanRunFields)")
    assert stage_index < verify_index < terminal_index
    assert source.count("await assertAttemptStillActive(") >= 2
    assert "terminal_authority_rejected" in source
    assert "await entities.ScanRun.update(identity.scan_id, rows.scanRun)" not in source
    assert "const { attempt_count: _stagedAttempt, ...scanRunFields } = rows.scanRun" in source
    assert 'status: "reviewing"' in source
    assert 'release_gate_eligible: false' in source
    assert 'persistedScan?.status === "complete"' in source
    assert "fixListVerified: true" in source
    assert "allowanceConsumed: false" in source


def test_worker_uses_only_signed_hosted_boundaries():
    source = WORKER_SOURCE.read_text(encoding="utf-8")
    assert 'invoke_function(client, "persistDurableScanAuthority", envelope)' in source
    assert 'invoke_function(client, "durableScanWorkerControl", envelope' in source
    assert "/entities/" not in source
    assert "Base44-Service-Authorization" not in source
    assert 'invoke_function(client, "aiReviewScan"' not in source
    assert 'invoke_function(client, "persistScanAuthority"' not in source
    assert "build_local_review" in source
    assert 'build_control_envelope("start"' in source
    assert "mark_scan_started" in source
    assert 'build_control_envelope("sweep"' in source
    assert "reconcile_stale_scans" in source
    assert 'get("fixListVerified") is not True' in source


def test_durable_worker_stamps_python_backend_authority_markers():
    source = (REPO_ROOT / "scanner-api/app/main.py").read_text(encoding="utf-8")
    durable = source.split('@app.post("/scan-job")', 1)[1].split('@app.post("/scan-job-drain")', 1)[0]
    assert '"advanced_scan_backend": "python_scanner_api"' in durable
    assert '"deno_fallback_used": False' in durable
    assert "complete_authority(client, scan, result, signing_key)" in durable
    assert "timeout=WORKER_COMPLETION_WALL_TIMEOUT_SECONDS" in durable
    assert durable.index('"advanced_scan_backend": "python_scanner_api"') < durable.index("complete_authority(client, scan, result, signing_key)")
