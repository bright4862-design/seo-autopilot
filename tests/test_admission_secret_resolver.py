from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "resolve_admission_operator_signing_version.py"
SPEC = importlib.util.spec_from_file_location("admission_secret_resolver", MODULE_PATH)
assert SPEC and SPEC.loader
resolver = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(resolver)


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def run_resolver(monkeypatch, capsys, response):
    requested = {}

    def fake_urlopen(request, timeout):
        requested["url"] = request.full_url
        requested["timeout"] = timeout
        return FakeResponse(json.dumps(response).encode("utf-8"))

    monkeypatch.setenv("FIXLIST_ADMISSION_ACCESS_TOKEN", "masked-short-lived-token")
    monkeypatch.setattr(resolver.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        sys,
        "argv",
        [str(MODULE_PATH), "seo-autopilot-501517", "fixlist-admission-operator-signing-key"],
    )
    assert resolver.main() == 0
    return capsys.readouterr(), requested


def test_resolves_project_number_metadata_without_payload(monkeypatch, capsys, tmp_path):
    sentinel = "payload-must-never-appear"
    captured, requested = run_resolver(
        monkeypatch,
        capsys,
        {
            "name": "projects/919035207432/secrets/fixlist-admission-operator-signing-key/versions/7",
            "state": "ENABLED",
            "payload": {"data": sentinel},
        },
    )
    assert captured.out == "7\n"
    assert captured.err == ""
    assert sentinel not in captured.out + captured.err
    assert requested == {
        "url": "https://secretmanager.googleapis.com/v1/projects/seo-autopilot-501517/secrets/fixlist-admission-operator-signing-key/versions/latest",
        "timeout": 20,
    }
    assert not any(path.is_file() for path in tmp_path.iterdir())


def test_resolves_regional_canonical_name(monkeypatch, capsys):
    captured, _ = run_resolver(
        monkeypatch,
        capsys,
        {
            "name": "projects/919035207432/locations/europe-west1/secrets/fixlist-admission-operator-signing-key/versions/12",
            "state": "ENABLED",
        },
    )
    assert captured.out == "12\n"


@pytest.mark.parametrize(
    "response,message",
    [
        (
            {
                "name": "projects/919035207432/secrets/another-secret/versions/3",
                "state": "ENABLED",
            },
            "did not resolve latest",
        ),
        (
            {
                "name": "projects/919035207432/secrets/fixlist-admission-operator-signing-key/versions/3",
                "state": "DISABLED",
            },
            "not enabled",
        ),
    ],
)
def test_fails_closed_for_wrong_secret_or_state(monkeypatch, capsys, response, message):
    monkeypatch.setenv("FIXLIST_ADMISSION_ACCESS_TOKEN", "masked-short-lived-token")
    monkeypatch.setattr(
        resolver.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse(json.dumps(response).encode("utf-8")),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [str(MODULE_PATH), "seo-autopilot-501517", "fixlist-admission-operator-signing-key"],
    )
    with pytest.raises(SystemExit, match=message):
        resolver.main()
    captured = capsys.readouterr()
    assert captured.out == ""


def test_requires_the_dedicated_token(monkeypatch):
    monkeypatch.delenv("FIXLIST_ADMISSION_ACCESS_TOKEN", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [str(MODULE_PATH), "seo-autopilot-501517", "fixlist-admission-operator-signing-key"],
    )
    with pytest.raises(SystemExit, match="token is unavailable"):
        resolver.main()
