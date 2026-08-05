import json

from fastapi.testclient import TestClient


def _events(capsys):
    return [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")]


def test_scan_echoes_identity_and_logs_it(monkeypatch, capsys):
    from app import main

    async def completed_scan(**kwargs):
        return {
            "success": True,
            "scanner_version": "python_scanner_v3_bounded_request",
            "pages_crawled": 1,
            "pages_found": 1,
            "pages": [{"url": "https://example.com", "final_url": "https://www.example.com/"}],
        }

    async def unchanged_trust(result):
        return result

    monkeypatch.setattr(main, "run_scan", completed_scan)
    monkeypatch.setattr(main, "enrich_scan_with_trust_pages", unchanged_trust)
    monkeypatch.setattr(main, "SCANNER_API_KEY", "test-scanner-key")
    response = TestClient(main.app).post(
        "/scan",
        json={
            "website_url": "https://example.com",
            "submitted_url": "example.com",
            "request_id": "req-1",
            "idempotency_key": "req-1",
            "scan_id": "scan-1",
            "scan_run_id": "scan-1",
            "respect_robots_txt": True,
        },
        headers={"X-Scanner-Key": "test-scanner-key"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["request_id"] == "req-1"
    assert body["idempotency_key"] == "req-1"
    assert body["scan_id"] == body["scan_run_id"] == "scan-1"
    assert body["submitted_url"] == "example.com"
    assert body["final_url"] == "https://www.example.com/"
    assert body["normalized_domain"] == "www.example.com"
    assert body["respect_robots_txt"] is True
    events = _events(capsys)
    assert {event.get("request_id") for event in events} == {"req-1"}
    assert {event.get("scan_id") for event in events} == {"scan-1"}


def test_scan_failure_keeps_identity(monkeypatch, capsys):
    from app import main

    async def exploding_scan(**kwargs):
        raise RuntimeError("internal detail")

    monkeypatch.setattr(main, "run_scan", exploding_scan)
    monkeypatch.setattr(main, "SCANNER_API_KEY", "test-scanner-key")
    response = TestClient(main.app).post(
        "/scan",
        json={
            "website_url": "https://example.com",
            "request_id": "req-fail",
            "idempotency_key": "req-fail",
            "scan_id": "scan-fail",
        },
        headers={"X-Scanner-Key": "test-scanner-key"},
    )
    body = response.json()
    assert body["success"] is False
    assert body["request_id"] == "req-fail"
    assert body["scan_id"] == body["scan_run_id"] == "scan-fail"
    _events(capsys)


def test_scan_rejects_conflicting_key_and_robots_bypass(monkeypatch):
    from app import main

    monkeypatch.setattr(main, "SCANNER_API_KEY", "test-scanner-key")
    client = TestClient(main.app)
    conflict = client.post("/scan", json={
        "website_url": "https://example.com",
        "request_id": "req-1",
        "idempotency_key": "req-2",
    }, headers={"X-Scanner-Key": "test-scanner-key"})
    assert conflict.status_code == 409

    bypass = client.post("/scan", json={
        "website_url": "https://example.com",
        "respect_robots_txt": False,
    }, headers={"X-Scanner-Key": "test-scanner-key"})
    assert bypass.status_code == 400


def test_scan_passes_request_scoped_timeout_to_scanner(monkeypatch, capsys):
    from app import main

    captured = {}

    async def completed_scan(**kwargs):
        captured.update(kwargs)
        return {
            "success": True,
            "scanner_version": "python_scanner_v3_bounded_request",
            "pages_crawled": 1,
            "pages_found": 1,
            "pages": [{"url": "https://example.com", "final_url": "https://example.com/"}],
        }

    async def unchanged_trust(result):
        return result

    monkeypatch.setattr(main, "run_scan", completed_scan)
    monkeypatch.setattr(main, "enrich_scan_with_trust_pages", unchanged_trust)
    monkeypatch.setattr(main, "SCANNER_API_KEY", "test-scanner-key")
    response = TestClient(main.app).post(
        "/scan",
        json={
            "website_url": "https://example.com",
            "request_id": "req-budget",
            "idempotency_key": "req-budget",
            "scan_id": "scan-budget",
            "advisory_crawl_timeout_ms": 40_000,
        },
        headers={"X-Scanner-Key": "test-scanner-key"},
    )
    assert response.status_code == 200
    assert captured["timeout_seconds"] == 40.0
    assert response.json()["requested_crawl_timeout_ms"] == 40_000
    _events(capsys)
