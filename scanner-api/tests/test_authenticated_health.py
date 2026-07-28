from fastapi.testclient import TestClient

from app import main


client = TestClient(main.app)


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
    assert body["scanner_build_revision"] == "authenticated_health_probe_v1"


def test_authenticated_health_supports_unkeyed_local_mode(monkeypatch):
    monkeypatch.setattr(main, "SCANNER_API_KEY", "")

    response = client.get("/health/auth")

    assert response.status_code == 200
    body = response.json()
    assert body["authenticated"] is True
    assert body["key_required"] is False
