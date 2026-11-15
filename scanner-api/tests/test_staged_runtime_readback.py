import runpy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main, scan_job
from app.generated_v9_worker_runtime import V9_WORKER_FUNCTION_IDENTITIES, V9_WORKER_RELEASE_FINGERPRINT

SOURCE = "a" * 40
REVISION = "fixlist-standard150-worker-00109-rml"
MATCHES = runpy.run_path(str(Path(__file__).parents[2] / "scripts/verify_staged_worker_base44_runtime.py"))[
    "matches_observation"
]


@pytest.fixture
def worker(monkeypatch):
    monkeypatch.setenv("K_SERVICE", "fixlist-standard150-worker")
    monkeypatch.setenv("K_REVISION", REVISION)
    monkeypatch.setenv("SCAN_WORKSPACE_BUCKET", "candidate-workspace")
    monkeypatch.setenv("BASE44_API_URL", "https://base44.app")
    monkeypatch.setenv("BASE44_APP_ID", "6a498732ec779dfaaeab0e53")
    monkeypatch.setattr(main, "WORKER_SOURCE_SHA", SOURCE)
    return TestClient(main.app)


def test_readback_can_only_attest_all_three_exact_worker_routes(worker, monkeypatch):
    probed = []

    async def probe(client, name, *, timeout):
        probed.append(name)
        return {"status_code": 200, "body": {"success": True, "_worker_runtime": {
            "proof": "private-proof",
            "receipt": {
                "protocol": "fixlist_worker_runtime_v1", "action": "identity", "function_name": name,
                "http_status": 200, "release_fingerprint": V9_WORKER_RELEASE_FINGERPRINT,
                "nonce": "private-nonce", **V9_WORKER_FUNCTION_IDENTITIES[name],
            },
        }}}

    monkeypatch.setattr(scan_job, "probe_worker_runtime_identity", probe)
    response = worker.get("/staged/base44-runtime")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert probed == list(V9_WORKER_FUNCTION_IDENTITIES)
    assert "private" not in response.text
    observation = response.json()
    assert MATCHES(observation, source_sha=SOURCE, revision=REVISION)
    assert not MATCHES(observation, source_sha="b" * 40, revision=REVISION)
    observation["functions"][1]["build_id"] = "0" * 64
    assert not MATCHES(observation, source_sha=SOURCE, revision=REVISION)


def test_readback_fails_if_a_writer_cannot_be_verified(worker, monkeypatch):
    async def probe(client, name, *, timeout):
        return {"status_code": 503, "body": {"error_code": "worker_runtime_unverified"}}

    monkeypatch.setattr(scan_job, "probe_worker_runtime_identity", probe)
    response = worker.get("/staged/base44-runtime")
    assert response.status_code == 503
    assert "functions" not in response.json()


@pytest.mark.parametrize(("key", "value", "status"), [
    ("K_SERVICE", "public-scanner", 404),
    ("BASE44_API_URL", "https://another.example", 503),
])
def test_readback_refuses_other_services_and_origins(worker, monkeypatch, key, value, status):
    async def unexpected_probe(*args, **kwargs):
        pytest.fail("runtime probe reached an unapproved target")

    monkeypatch.setenv(key, value)
    monkeypatch.setattr(scan_job, "probe_worker_runtime_identity", unexpected_probe)
    assert worker.get("/staged/base44-runtime").status_code == status
