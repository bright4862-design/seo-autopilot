"""/scan-job must not depend on SCANNER_API_KEY.

The durable worker authenticates with Cloud Run IAM plus
TASKS_INVOKER_SERVICE_ACCOUNT, calls run_scan() directly, and runs the Python
review in-process (scan_job.build_local_review). It never calls
require_scanner_api_key(), so the deployment template does not supply that
secret.

These tests pin both halves of that decision:
  1. /scan-job behaves identically with the scanner key configured or absent.
  2. Removing the key does not open the sibling routes it does protect -- they
     fail closed with 401, because require_scanner_api_key() rejects an empty
     expected key.
"""
import inspect

import pytest
from fastapi.testclient import TestClient

from app import main


client = TestClient(main.app)

# Routes whose only application-level guard is the Cloud Tasks OIDC check.
DURABLE_ROUTES = ("/scan-job", "/scan-job-drain", "/scan-reconcile")

# A schema-valid ScanJobRequest. FastAPI validates the body before the endpoint
# body runs, so an incomplete payload would 422 and never reach the OIDC gate.
VALID_JOBS = {
    "/scan-job": {
        "scan_id": "scan_test_1",
        "request_id": "req_test_1",
        "website_url": "https://example.com",
    },
    "/scan-job-drain": {
        "scan_id": "scan_test_1",
        "request_id": "req_test_1",
        "website_url": "https://example.com",
        "drain_after": "2026-08-11T00:00:00+00:00",
    },
    "/scan-reconcile": {},
}

# Routes guarded by the scanner key. /review additionally requires OIDC.
SCANNER_KEY_ROUTES = (
    ("GET", "/health/auth", None),
    ("POST", "/scan", {"website_url": "https://example.com"}),
    ("POST", "/review", {}),
    ("POST", "/chat", {"message": "hi"}),
)


@pytest.mark.parametrize("route", DURABLE_ROUTES)
@pytest.mark.parametrize("configured_key", ["", "a-configured-scanner-key"])
def test_scan_job_rejects_without_oidc_regardless_of_scanner_key(monkeypatch, configured_key, route):
    """The durable route's outcome must not change with the scanner key."""
    monkeypatch.setattr(main, "SCANNER_API_KEY", configured_key)
    monkeypatch.setenv("TASKS_INVOKER_SERVICE_ACCOUNT", "worker-invoker@example.invalid")

    response = client.post(route, json=VALID_JOBS[route])

    # No Authorization header -> rejected by the OIDC gate, never by the key.
    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"


@pytest.mark.parametrize("route", DURABLE_ROUTES)
def test_scan_job_supplying_the_scanner_key_does_not_grant_access(monkeypatch, route):
    """A valid scanner key must not substitute for the OIDC invoker check."""
    monkeypatch.setattr(main, "SCANNER_API_KEY", "a-configured-scanner-key")
    monkeypatch.setenv("TASKS_INVOKER_SERVICE_ACCOUNT", "worker-invoker@example.invalid")

    response = client.post(
        route,
        json=VALID_JOBS[route],
        headers={"X-Scanner-Key": "a-configured-scanner-key"},
    )

    assert response.status_code == 401


@pytest.mark.parametrize("handler", [main.scan_job, main.scan_job_drain, main.scan_reconcile])
def test_scan_job_handler_does_not_call_require_scanner_api_key(handler):
    """Structural: durable handlers must stay OIDC-only."""
    source = inspect.getsource(handler)
    assert "require_cloud_tasks_oidc" in source
    assert "require_scanner_api_key" not in source


@pytest.mark.parametrize("method,path,payload", SCANNER_KEY_ROUTES)
def test_sibling_routes_fail_closed_when_no_scanner_key_configured(
    monkeypatch, method, path, payload
):
    """Removing the secret must make siblings unusable, never open."""
    monkeypatch.setattr(main, "SCANNER_API_KEY", "")

    response = client.request(method, path, json=payload)

    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"


@pytest.mark.parametrize("method,path,payload", SCANNER_KEY_ROUTES)
def test_sibling_routes_reject_any_supplied_key_when_none_configured(
    monkeypatch, method, path, payload
):
    """An empty expected key must never compare equal to a supplied one."""
    monkeypatch.setattr(main, "SCANNER_API_KEY", "")

    response = client.request(
        method, path, json=payload, headers={"X-Scanner-Key": "anything"}
    )

    assert response.status_code == 401


def test_every_scanner_key_route_is_still_guarded():
    """Guard inventory: catches a new route added without authentication."""
    guarded = {"/health/auth", "/scan", "/review", "/chat"}
    open_routes = {"/health", "/revision"}
    durable = {"/scan-job", "/scan-job-drain", "/scan-reconcile"}

    for route in main.app.routes:
        path = getattr(route, "path", None)
        endpoint = getattr(route, "endpoint", None)
        if path is None or endpoint is None or path in {"/openapi.json", "/docs", "/redoc", "/docs/oauth2-redirect"}:
            continue
        source = inspect.getsource(endpoint)
        if path in guarded:
            assert "require_scanner_api_key" in source, f"{path} lost its scanner-key guard"
        elif path in durable:
            assert "require_cloud_tasks_oidc" in source, f"{path} lost its OIDC guard"
            assert "require_scanner_api_key" not in source, f"{path} gained a scanner-key dependency"
        elif path in open_routes:
            continue
        else:
            raise AssertionError(
                f"unclassified route {path}: add it to this inventory and state its guard"
            )
