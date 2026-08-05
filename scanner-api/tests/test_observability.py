import json

import pytest
from fastapi.testclient import TestClient

from app.observability import (
    CUSTOMER_SAFE_MESSAGES,
    RequestTimer,
    classify_error,
    customer_safe_error,
    emit,
    review_metrics,
    scan_metrics,
    website_host,
)


def read_log_lines(capsys) -> list[dict]:
    return [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip().startswith("{")]


def test_emit_writes_one_structured_json_line(capsys):
    emit("scan_started", website_host="example.com", scan_mode="advanced")
    lines = read_log_lines(capsys)
    assert len(lines) == 1
    record = lines[0]
    assert record["event"] == "scan_started"
    assert record["severity"] == "INFO"
    assert record["website_host"] == "example.com"
    assert "timestamp" in record


def test_emit_drops_none_fields_and_normalizes_severity(capsys):
    record = emit("x", severity="NOT_A_LEVEL", empty=None, kept=0)
    assert record["severity"] == "INFO"
    assert "empty" not in record
    assert record["kept"] == 0
    read_log_lines(capsys)


def test_website_host_strips_paths_and_handles_garbage():
    assert website_host("https://Example.COM/pricing?utm=1") == "example.com"
    assert website_host("not a url") == ""
    assert website_host(None) == ""


def test_scan_metrics_counts_rate_limits_and_failures():
    result = {
        "success": True,
        "pages_crawled": 4,
        "pages_found": 10,
        "verified_failed_page_count": 1,
        "scanner_version": "python_scanner_v2_contract_parity",
        "crawled_pages": [
            {"status_code": 200},
            {"status_code": 429},
            {"status_code": 429},
            {"status_code": 503},
        ],
    }
    metrics = scan_metrics(result)
    assert metrics["rate_limited_pages"] == 2
    assert metrics["server_error_pages"] == 1
    assert metrics["failed_pages"] == 1
    assert metrics["success"] is True
    assert metrics["pages_crawled"] == 4


def test_review_metrics_reads_health_report_fallbacks():
    metrics = review_metrics({
        "review_version": "python_review_v1_archetype_templates",
        "website_health_report": {"scan_status": "complete", "health_score": 82},
        "cleaned_fixes": [{"id": "a"}, {"id": "b"}],
    })
    assert metrics["scan_status"] == "complete"
    assert metrics["health_score"] == 82
    assert metrics["finding_count"] == 2


@pytest.mark.parametrize("exc,expected", [
    (TimeoutError("read timed out"), "timeout"),
    (ValueError("bad url"), "invalid_input"),
    (ConnectionError("connection refused"), "upstream_unavailable"),
    (RuntimeError("boom"), "internal_error"),
])
def test_classify_error(exc, expected):
    assert classify_error(exc) == expected


def test_customer_safe_error_hides_internals_but_logs_them(capsys):
    secret = "psycopg2 auth against 10.1.2.3 failed"
    body = customer_safe_error(RuntimeError(secret), endpoint="scan")
    # Response body: safe message + correlation id, no internals.
    assert body["success"] is False
    assert body["error"] == CUSTOMER_SAFE_MESSAGES["internal_error"]
    assert secret not in json.dumps(body)
    assert len(body["error_id"]) == 12
    # Log line: full detail with the same correlation id.
    [record] = read_log_lines(capsys)
    assert record["severity"] == "ERROR"
    assert record["error_id"] == body["error_id"]
    assert secret in record["error_detail"]


def test_request_timer_emits_started_and_completed_with_duration(capsys):
    timer = RequestTimer("scan", website_host="example.com", scan_mode="deep")
    timer.completed(success=True, pages_crawled=3)
    started, completed = read_log_lines(capsys)
    assert started["event"] == "scan_started"
    assert completed["event"] == "scan_completed"
    assert completed["duration_ms"] >= 0
    assert completed["website_host"] == "example.com"
    assert completed["pages_crawled"] == 3


def test_release_marker_endpoints_are_consistent():
    from app import main

    client = TestClient(main.app)
    health = client.get("/health").json()
    revision = client.get("/revision").json()

    assert health["archetype_classifier_version"] == "archetype_classifier_v9_local_business_hospitality"
    assert health["beta_revision_fingerprint"] == "51c813a6219b4e70"
    assert health["review_version"] == "python_review_v2_structural_marketplace"
    assert health["review_evidence_calibration_version"] == "review_evidence_calibration_v5_utility_redirect"
    assert health["scanner_build_revision"] == "authenticated_health_probe_v1"
    assert revision["fingerprint"] == health["beta_revision_fingerprint"]
    assert revision["component_versions"]["archetype_classifier_version"] == health["archetype_classifier_version"]
    assert revision["component_versions"]["review_version"] == health["review_version"]
    assert revision["component_versions"]["review_evidence_calibration_version"] == health["review_evidence_calibration_version"]
    assert revision["component_versions"]["scanner_build_revision"] == health["scanner_build_revision"]
    assert revision["component_versions"]["artifact_filter_version"] == "artifact_filter_v4_wordpress_route_noise"
    assert revision["component_versions"]["redirect_evidence_version"] == "redirect_evidence_v3_origin_alias_identity"


def test_scan_endpoint_returns_customer_safe_envelope_on_crash(monkeypatch, capsys):
    from app import main

    async def exploding_scan(**kwargs):
        raise RuntimeError("internal stack detail the customer must not see")

    monkeypatch.setattr(main, "run_scan", exploding_scan)
    monkeypatch.setattr(main, "SCANNER_API_KEY", "test-scanner-key")
    client = TestClient(main.app)
    response = client.post(
        "/scan",
        json={"website_url": "https://example.com"},
        headers={"X-Scanner-Key": "test-scanner-key"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["error"] == CUSTOMER_SAFE_MESSAGES["internal_error"]
    assert "stack detail" not in json.dumps(body)
    assert body["error_id"]
    events = [record["event"] for record in read_log_lines(capsys)]
    assert "scan_started" in events
    assert "request_failed" in events


def test_scan_endpoint_returns_beta_revision_fingerprint(monkeypatch, capsys):
    from app import main

    async def completed_scan(**kwargs):
        return {"success": True, "pages_crawled": 0, "pages_found": 0, "pages": []}

    async def unchanged_trust(result):
        return result

    monkeypatch.setattr(main, "run_scan", completed_scan)
    monkeypatch.setattr(main, "enrich_scan_with_trust_pages", unchanged_trust)
    monkeypatch.setattr(main, "SCANNER_API_KEY", "test-scanner-key")
    client = TestClient(main.app)
    response = client.post(
        "/scan",
        json={"website_url": "https://example.com"},
        headers={"X-Scanner-Key": "test-scanner-key"},
    )
    assert response.status_code == 200
    assert response.json()["beta_revision_fingerprint"] == "51c813a6219b4e70"
    assert response.json()["scanner_build_revision"] == "authenticated_health_probe_v1"
    read_log_lines(capsys)


def test_review_endpoint_logs_completion_metrics(monkeypatch, capsys):
    from app import main

    monkeypatch.setattr(main, "run_review", lambda payload: {
        "review_version": "r1",
        "scan_status": "complete",
        "health_score": 90,
        "cleaned_fixes": [],
    })
    monkeypatch.setattr(main, "apply_trust_discovery_gate", lambda result, payload: result)
    monkeypatch.setattr(main, "apply_review_evidence_calibration", lambda result, payload: result)
    monkeypatch.setattr(main, "apply_evidence_quality_gate", lambda result, payload: result)
    monkeypatch.setattr(main, "SCANNER_API_KEY", "test-scanner-key")
    client = TestClient(main.app)
    response = client.post(
        "/review",
        json={"website_url": "https://example.com"},
        headers={"X-Scanner-Key": "test-scanner-key"},
    )
    assert response.status_code == 200
    assert response.json()["beta_revision_fingerprint"] == "51c813a6219b4e70"
    completed = [record for record in read_log_lines(capsys) if record["event"] == "review_completed"]
    assert len(completed) == 1
    assert completed[0]["scan_status"] == "complete"
    assert completed[0]["health_score"] == 90
    assert "beta_revision_fingerprint" in completed[0]
