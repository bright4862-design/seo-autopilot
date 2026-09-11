from fastapi.testclient import TestClient


def test_owner_attested_scan_can_disable_robots_and_passes_policy_to_scanner(monkeypatch):
    from app import main

    captured = {}

    async def completed_scan(**kwargs):
        captured.update(kwargs)
        return {
            "success": True,
            "scanner_version": "python_scanner_v3_bounded_request",
            "pages_crawled": 1,
            "pages_found": 1,
            "pages": [{"url": "https://example.com/", "final_url": "https://example.com/"}],
        }

    async def unchanged_trust(result):
        return result

    monkeypatch.setattr(main, "run_scan", completed_scan)
    monkeypatch.setattr(main, "enrich_scan_with_trust_pages", unchanged_trust)
    monkeypatch.setattr(main, "SCANNER_API_KEY", "test-scanner-key")

    response = TestClient(main.app).post(
        "/scan",
        json={
            "website_url": "https://example.com/",
            "request_id": "req-owner",
            "idempotency_key": "req-owner",
            "scan_id": "scan-owner",
            "scan_mode": "advanced",
            "respect_robots_txt": False,
            "owner_attested_robots_override": True,
        },
        headers={"X-Scanner-Key": "test-scanner-key"},
    )

    assert response.status_code == 200
    assert captured["respect_robots_txt"] is False
    body = response.json()
    assert body["respect_robots_txt"] is False
    assert body["owner_attested_robots_override"] is True


def test_robots_override_without_owner_attestation_is_rejected(monkeypatch):
    from app import main

    monkeypatch.setattr(main, "SCANNER_API_KEY", "test-scanner-key")
    response = TestClient(main.app).post(
        "/scan",
        json={
            "website_url": "https://example.com/",
            "respect_robots_txt": False,
            "owner_attested_robots_override": False,
        },
        headers={"X-Scanner-Key": "test-scanner-key"},
    )

    assert response.status_code == 400


def test_default_standard_scan_still_respects_robots(monkeypatch):
    from app import main

    captured = {}

    async def completed_scan(**kwargs):
        captured.update(kwargs)
        return {
            "success": True,
            "scanner_version": "python_scanner_v3_bounded_request",
            "pages_crawled": 1,
            "pages_found": 1,
            "pages": [{"url": "https://example.com/", "final_url": "https://example.com/"}],
        }

    async def unchanged_trust(result):
        return result

    monkeypatch.setattr(main, "run_scan", completed_scan)
    monkeypatch.setattr(main, "enrich_scan_with_trust_pages", unchanged_trust)
    monkeypatch.setattr(main, "SCANNER_API_KEY", "test-scanner-key")

    response = TestClient(main.app).post(
        "/scan",
        json={
            "website_url": "https://example.com/",
            "request_id": "req-default",
            "idempotency_key": "req-default",
            "scan_id": "scan-default",
        },
        headers={"X-Scanner-Key": "test-scanner-key"},
    )

    assert response.status_code == 200
    assert captured["respect_robots_txt"] is True
    assert response.json()["respect_robots_txt"] is True
