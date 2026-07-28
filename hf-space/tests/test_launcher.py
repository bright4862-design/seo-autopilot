from __future__ import annotations

from dataclasses import dataclass

import launcher


@dataclass
class FakeResponse:
    status_code: int
    payload: dict | None = None

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise launcher.requests.HTTPError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return self.payload or {}


def test_scanner_base_url_removes_known_endpoint_suffixes():
    assert launcher.scanner_base_url("https://scanner.example/scan") == "https://scanner.example"
    assert launcher.scanner_base_url("https://scanner.example/health/auth") == "https://scanner.example"
    assert launcher.scanner_base_url("scanner.example") == ""


def test_verifier_rejects_wrong_shared_key(monkeypatch):
    monkeypatch.setenv("SCANNER_API_URL", "https://scanner.example")
    monkeypatch.setenv("SCANNER_API_KEY", "wrong")
    monkeypatch.setattr(
        launcher.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(401),
    )

    connected, detail = launcher.verify_scanner_connection()

    assert connected is False
    assert "rejected" in detail


def test_verifier_waits_for_rollout_then_connects(monkeypatch):
    monkeypatch.setenv("SCANNER_API_URL", "https://scanner.example")
    monkeypatch.setenv("SCANNER_API_KEY", "correct")
    monkeypatch.setenv("SCANNER_VERIFY_ATTEMPTS", "3")
    monkeypatch.setenv("SCANNER_VERIFY_DELAY_SECONDS", "1")
    responses = iter(
        [
            FakeResponse(404),
            FakeResponse(
                200,
                {
                    "authenticated": True,
                    "scanner_build_revision": "authenticated_health_probe_v1",
                },
            ),
        ]
    )
    monkeypatch.setattr(launcher.requests, "get", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr(launcher.time, "sleep", lambda *_: None)

    connected, detail = launcher.verify_scanner_connection()

    assert connected is True
    assert "authenticated_health_probe_v1" in detail
