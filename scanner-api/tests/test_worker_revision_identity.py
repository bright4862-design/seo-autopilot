"""Read-only runtime identity must name its executing Cloud Run revision.

No scan, auth mutation, or network access: only the FastAPI identity endpoint.
"""

from fastapi.testclient import TestClient

from app import main
from app.beta_revision import live_revision


def test_revision_reports_the_cloud_run_runtime_not_request_metadata(monkeypatch):
    monkeypatch.setenv("K_REVISION", "fixlist-standard150-worker-00110-probe")
    monkeypatch.setattr(main, "WORKER_SOURCE_SHA", "a" * 40)
    response = TestClient(main.app).get("/revision", headers={"x-worker-revision": "forged-client-revision"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["worker_revision"] == "fixlist-standard150-worker-00110-probe"
    assert payload["source_sha"] == "a" * 40
    for field in ("fingerprint", "schema_version", "component_versions"):
        assert payload[field] == live_revision()[field]


def test_revision_does_not_fabricate_runtime_identity_when_not_in_cloud_run(monkeypatch):
    monkeypatch.delenv("K_REVISION", raising=False)
    response = TestClient(main.app).get("/revision")
    assert response.status_code == 200
    assert response.json()["worker_revision"] == ""  # operator must fail closed
