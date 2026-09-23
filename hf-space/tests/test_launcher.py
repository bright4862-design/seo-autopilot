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
    assert launcher.scanner_base_url("https://scanner.example/chat") == "https://scanner.example"
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


def test_direct_model_fallback_is_disabled_before_ui_import(monkeypatch):
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", '{"private_key":"must-not-be-used"}')
    monkeypatch.delenv("FIXLIST_HF_DIRECT_MODEL_DISABLED", raising=False)

    launcher.disable_direct_model_fallback()

    assert launcher.os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"] == ""
    assert launcher.os.environ["FIXLIST_HF_DIRECT_MODEL_DISABLED"] == "1"


def test_main_disables_direct_model_fallback_even_when_scanner_is_unavailable(monkeypatch):
    monkeypatch.setenv("SCANNER_API_KEY", "candidate")
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", '{"private_key":"legacy-direct-model"}')
    monkeypatch.setattr(
        launcher,
        "verify_scanner_connection",
        lambda: (False, "scanner unavailable"),
    )
    observed: dict[str, str] = {}

    def fake_run_path(*args, **kwargs):
        del args, kwargs
        observed["scanner_key"] = launcher.os.environ.get("SCANNER_API_KEY", "<missing>")
        observed["service_account"] = launcher.os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "<missing>")
        observed["direct_model_disabled"] = launcher.os.environ.get("FIXLIST_HF_DIRECT_MODEL_DISABLED", "")
        return {}

    monkeypatch.setattr(launcher.runpy, "run_path", fake_run_path)

    launcher.main()

    assert observed == {
        "scanner_key": "",
        "service_account": "",
        "direct_model_disabled": "1",
    }


def test_main_preserves_verified_scanner_key_but_still_removes_direct_provider_credentials(monkeypatch):
    monkeypatch.setenv("SCANNER_API_KEY", "verified-key")
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", '{"private_key":"legacy-direct-model"}')
    monkeypatch.setattr(
        launcher,
        "verify_scanner_connection",
        lambda: (True, "Scanner authenticated (revision)"),
    )
    observed: dict[str, str] = {}

    def fake_run_path(*args, **kwargs):
        del args, kwargs
        observed["scanner_key"] = launcher.os.environ.get("SCANNER_API_KEY", "<missing>")
        observed["service_account"] = launcher.os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "<missing>")
        observed["direct_model_disabled"] = launcher.os.environ.get("FIXLIST_HF_DIRECT_MODEL_DISABLED", "")
        return {}

    monkeypatch.setattr(launcher.runpy, "run_path", fake_run_path)

    launcher.main()

    assert observed == {
        "scanner_key": "verified-key",
        "service_account": "",
        "direct_model_disabled": "1",
    }
