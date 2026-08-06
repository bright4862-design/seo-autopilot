"""Regression contract for the service-only durable completion boundary."""

from pathlib import Path

from app.scan_job import (
    COMPLETION_VERSION,
    WORKER_VERSION,
    _service_headers,
    build_completion_envelope,
    create_authority_seal,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_SOURCE = REPO_ROOT / "base44/functions/persistDurableScanAuthority/index.ts"


def _scan_result() -> dict:
    return {
        "scanner_version": "python_scanner_v3_bounded_request",
        "scanner_build_revision": "authenticated_health_probe_v1",
        "advanced_scan_backend": "python_scanner_api",
        "deno_fallback_used": False,
        "beta_revision_fingerprint": "51c813a6219b4e70",
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
        "review_evidence_calibration_version": "review_evidence_calibration_v5_utility_redirect",
        "archetype_classifier_version": "archetype_classifier_v9_local_business_hospitality",
        "ai_review_backend": "python_review_api",
        "python_review_fallback_used": False,
        "release_gate_eligible": True,
        "score_is_provisional": False,
        "evidence_quality_blocking": False,
        "beta_revision_fingerprint": "51c813a6219b4e70",
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


def test_base44_service_token_is_normalized_and_worker_marked(monkeypatch):
    monkeypatch.setenv("BASE44_SERVICE_TOKEN", "service-token")
    monkeypatch.setenv("BASE44_APP_ID", "app-1")
    headers = _service_headers()
    assert headers["Base44-Service-Authorization"] == "Bearer service-token"
    assert headers["Base44-App-Id"] == "app-1"
    assert headers["X-FixList-Worker"] == WORKER_VERSION


def test_service_function_does_not_depend_on_browser_auth():
    source = SERVICE_SOURCE.read_text(encoding="utf-8")
    assert "auth.me" not in source
    assert 'X-FixList-Worker' in source
    assert 'Base44-Service-Authorization' in source
    assert 'verifyAuthoritySeal(signedDocument' in source
    assert 'validateCurrentIdentity' in source


def test_authority_is_verified_before_allowance_and_terminal_completion():
    source = SERVICE_SOURCE.read_text(encoding="utf-8")
    assert "Math.max(FREE_SCAN_CONSUMED_VALUE" in source
    assert "scans_used: used" in source
    assert "scans_used + 1" not in source
    stage_index = source.index("await entities.ScanRun.update(identity.scan_id, stagedScanFields)")
    verify_index = source.index("const authorityStaged = Boolean(")
    allowance_index = source.index("await ensureAllowanceConsumed")
    terminal_index = source.index("await entities.ScanRun.update(identity.scan_id, rows.scanRun)")
    assert stage_index < verify_index < allowance_index < terminal_index
    assert 'status: "reviewing"' in source
    assert 'release_gate_eligible: false' in source
    assert 'persistedScan?.status === "complete"' in source


def test_worker_uses_new_service_boundary_not_user_functions():
    source = (REPO_ROOT / "scanner-api/app/scan_job.py").read_text(encoding="utf-8")
    assert 'invoke_function(client, "persistDurableScanAuthority", envelope)' in source
    assert 'invoke_function(client, "aiReviewScan"' not in source
    assert 'invoke_function(client, "persistScanAuthority"' not in source
    assert "build_local_review" in source
