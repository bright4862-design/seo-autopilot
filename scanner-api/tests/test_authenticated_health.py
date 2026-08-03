import pytest
from fastapi.testclient import TestClient

from app import main


client = TestClient(main.app)

PROTECTED_REQUESTS = (
    ("GET", "/health/auth", None),
    ("POST", "/scan", {"website_url": "https://example.com"}),
    ("POST", "/review", {}),
    ("POST", "/chat", {"message": "What should I fix first?"}),
)


@pytest.mark.parametrize("method,path,payload", PROTECTED_REQUESTS)
@pytest.mark.parametrize(
    ("configured_key", "headers"),
    (
        ("", {}),
        ("", {"X-Scanner-Key": "candidate-secret"}),
        ("expected-secret", {}),
        ("expected-secret", {"X-Scanner-Key": "wrong-secret"}),
    ),
)
def test_protected_endpoints_fail_closed(
    monkeypatch,
    method,
    path,
    payload,
    configured_key,
    headers,
):
    monkeypatch.setattr(main, "SCANNER_API_KEY", configured_key)

    response = client.request(method, path, json=payload, headers=headers)

    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"


def test_authenticated_health_rejects_wrong_key(monkeypatch):
    monkeypatch.setattr(main, "SCANNER_API_KEY", "expected-secret")

    response = client.get(
        "/health/auth",
        headers={"X-Scanner-Key": "wrong-secret"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"


def test_authenticated_health_accepts_matching_key(monkeypatch):
    monkeypatch.setattr(main, "SCANNER_API_KEY", "expected-secret")

    response = client.get(
        "/health/auth",
        headers={"X-Scanner-Key": "expected-secret"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["authenticated"] is True
    assert body["key_required"] is True
    assert body["scanner_build_revision"] == main.SCANNER_BUILD_REVISION


def test_public_health_and_revision_remain_public_when_key_is_missing(monkeypatch):
    monkeypatch.setattr(main, "SCANNER_API_KEY", "")
    monkeypatch.setattr(main, "GROK_PROXY_ENABLED", False)

    health = client.get("/health")
    revision = client.get("/revision")

    assert health.status_code == 200
    assert health.json()["ok"] is True
    assert health.json()["key_required"] is True
    assert health.json()["grok_proxy_enabled"] is False
    assert revision.status_code == 200


def test_chat_disabled_rejects_authenticated_requests_without_provider_call(monkeypatch):
    provider_calls = 0

    async def forbidden_provider_call(message, scan, history):
        nonlocal provider_calls
        provider_calls += 1
        return "This must never be returned."

    monkeypatch.setattr(main, "SCANNER_API_KEY", "expected-secret")
    monkeypatch.setattr(main, "GROK_PROXY_ENABLED", False)
    monkeypatch.setattr(main, "run_grok_chat", forbidden_provider_call)

    response = client.post(
        "/chat",
        json={"message": "What should I fix first?"},
        headers={"X-Scanner-Key": "expected-secret"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Grok is unavailable."
    assert provider_calls == 0


def test_chat_disabled_keeps_unauthenticated_failure_sanitized(monkeypatch):
    provider_calls = 0

    async def forbidden_provider_call(message, scan, history):
        nonlocal provider_calls
        provider_calls += 1
        return "This must never be returned."

    monkeypatch.setattr(main, "SCANNER_API_KEY", "expected-secret")
    monkeypatch.setattr(main, "GROK_PROXY_ENABLED", False)
    monkeypatch.setattr(main, "run_grok_chat", forbidden_provider_call)

    response = client.post(
        "/chat",
        json={"message": "What should I fix first?"},
        headers={"X-Scanner-Key": "wrong-secret"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"
    assert provider_calls == 0


def test_chat_accepts_matching_key_only_when_proxy_enabled(monkeypatch):
    async def completed_chat(message, scan, history):
        return "Grounded answer."

    monkeypatch.setattr(main, "SCANNER_API_KEY", "expected-secret")
    monkeypatch.setattr(main, "GROK_PROXY_ENABLED", True)
    monkeypatch.setattr(main, "run_grok_chat", completed_chat)

    response = client.post(
        "/chat",
        json={"message": "What should I fix first?"},
        headers={"X-Scanner-Key": "expected-secret"},
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "Grounded answer."


def test_scan_accepts_matching_key(monkeypatch):
    async def completed_scan(**kwargs):
        return {"success": True, "pages_crawled": 0, "pages_found": 0, "pages": []}

    async def unchanged_trust(result):
        return result

    monkeypatch.setattr(main, "SCANNER_API_KEY", "expected-secret")
    monkeypatch.setattr(main, "run_scan", completed_scan)
    monkeypatch.setattr(main, "enrich_scan_with_trust_pages", unchanged_trust)

    response = client.post(
        "/scan",
        json={"website_url": "https://example.com"},
        headers={"X-Scanner-Key": "expected-secret"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True


def test_review_accepts_matching_key(monkeypatch):
    monkeypatch.setattr(main, "SCANNER_API_KEY", "expected-secret")
    monkeypatch.setattr(main, "run_review", lambda payload: {"success": True})
    monkeypatch.setattr(main, "apply_trust_discovery_gate", lambda result, payload: result)
    monkeypatch.setattr(main, "apply_review_evidence_calibration", lambda result, payload: result)
    monkeypatch.setattr(main, "apply_evidence_quality_gate", lambda result, payload: result)

    response = client.post(
        "/review",
        json={},
        headers={"X-Scanner-Key": "expected-secret"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
