import json
import re
import subprocess
from pathlib import Path

import httpx
import pytest

from app import scan_job
from app.authority_seal import create_authority_seal
from app.generated_v9_worker_runtime import (
    V9_WORKER_FUNCTION_IDENTITIES, V9_WORKER_FUNCTION_ROUTES, V9_WORKER_RELEASE_FINGERPRINT,
)


PROTOCOL = "fixlist_worker_runtime_v1"
KEY = "test-runtime-signing-key"
CONTROL = "durableScanWorkerControlV9"
UNVERIFIED = {"status_code": 503, "body": {"error_code": "worker_runtime_unverified"}}


def signed_receipt(function, request, status, fields=None):
    receipt = {
        "protocol": PROTOCOL,
        "function_name": function,
        "action": request["action"],
        "nonce": request["nonce"],
        **V9_WORKER_FUNCTION_IDENTITIES[function],
        "release_fingerprint": V9_WORKER_RELEASE_FINGERPRINT,
        "http_status": status,
    }
    receipt.update(fields or {})
    return {"receipt": receipt, "proof": create_authority_seal(receipt, KEY)}


@pytest.fixture
def runtime_env(monkeypatch):
    monkeypatch.setenv("SCAN_EVIDENCE_SIGNING_KEY", KEY)
    monkeypatch.setenv("BASE44_API_URL", "https://fixture.example/")
    monkeypatch.setenv("BASE44_APP_ID", "test-app")
    monkeypatch.setattr(scan_job.time, "time", lambda: 1_795_000_123.9)


@pytest.mark.asyncio
@pytest.mark.parametrize("function", [CONTROL, "persistDurableScanAuthorityV9", "persistLimitedScanResultV9"])
async def test_all_v9_routes_wrap_legacy_payload_and_accept_signed_business_errors(runtime_env, function):
    payload = {"proof": "legacy-proof", "scan": {"label": "é 😀"}}
    seen = []

    def send(outgoing):
        assert outgoing.method == "POST"
        assert str(outgoing.url) == f"https://fixture.example/api/apps/test-app/functions/{V9_WORKER_FUNCTION_ROUTES[function]}"
        assert outgoing.headers["X-FixList-Worker"] == scan_job.WORKER_VERSION
        assert "authorization" not in outgoing.headers
        wire = json.loads(outgoing.content)
        assert set(wire) == {"runtime_request", "runtime_proof"}
        request = wire["runtime_request"]
        assert re.fullmatch(r"[0-9a-f]{32}", request["nonce"])
        seen.append(request["nonce"])
        assert request == {
            "protocol": PROTOCOL, "function_name": function, "action": "invoke",
            "nonce": request["nonce"], "issued_at": 1_795_000_123,
            "expected_build_id": V9_WORKER_FUNCTION_IDENTITIES[function]["build_id"],
            "expected_runtime_activation_id": V9_WORKER_FUNCTION_IDENTITIES[function]["runtime_activation_id"],
            "payload": payload,
        }
        assert wire["runtime_proof"] == create_authority_seal(request, KEY)
        return httpx.Response(409, json={"data": {
            "error_code": "superseded_attempt", "_worker_runtime": signed_receipt(function, request, 409),
        }})

    async with httpx.AsyncClient(transport=httpx.MockTransport(send), headers={"Authorization": "Bearer inherited"}) as client:
        for _ in range(2):
            assert await scan_job.invoke_function(client, function, payload) == {
                "status_code": 409, "body": {"error_code": "superseded_attempt"},
            }
    assert len(set(seen)) == 2


@pytest.mark.asyncio
async def test_identity_probe_keeps_verified_receipt_and_sends_no_legacy_payload(runtime_env):
    received = {}

    def send(outgoing):
        wire = json.loads(outgoing.content)
        request = wire["runtime_request"]
        assert request["action"] == "identity" and request["payload"] is None
        assert wire["runtime_proof"] == create_authority_seal(request, KEY)
        received.update(signed_receipt(CONTROL, request, 200))
        return httpx.Response(200, json={"success": True, "_worker_runtime": received})

    async with httpx.AsyncClient(transport=httpx.MockTransport(send)) as client:
        result = await scan_job.probe_worker_runtime_identity(client, CONTROL, timeout=3.0)
    assert result == {"status_code": 200, "body": {"success": True, "_worker_runtime": received}}


@pytest.mark.asyncio
async def test_python_invoke_round_trips_actual_javascript_runtime_proof(runtime_env, tmp_path):
    root = Path(__file__).resolve().parents[2]
    deployed = tmp_path / "deploy"
    subprocess.run(["node", "scripts/materialize-base44-staged-functions.mjs", str(deployed)],
                   capture_output=True, cwd=root, check=True, timeout=10)
    package = deployed / "base44/functions" / V9_WORKER_FUNCTION_ROUTES[CONTROL]
    script = r'''
import { readFileSync } from "node:fs";
import { webcrypto } from "node:crypto";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
const packageFile = name => pathToFileURL(join(process.argv[1], name));
const { handleWorkerRuntime } = await import(packageFile("workerRuntime.js"));
const { createAuthoritySeal, verifyAuthoritySeal } = await import(packageFile("authoritySeal.js"));
const { FUNCTION_BUILD_ID } = await import(packageFile("generatedBuildId.js"));
const { RELEASE_FINGERPRINT } = await import(packageFile("generatedReleaseContract.js"));
const source = readFileSync(packageFile("entry.ts"), "utf8");
const activation = source.match(/BASE44_RUNTIME_ACTIVATION_ID\s*=\s*"([^"]+)"/)[1];
const response = await handleWorkerRuntime(JSON.parse(readFileSync(0, "utf8")), {
  function_name: "durableScanWorkerControlV9", build_id: FUNCTION_BUILD_ID,
  release_fingerprint: RELEASE_FINGERPRINT, runtime_activation_id: activation,
}, "test-runtime-signing-key", {
  sign: (body, key) => createAuthoritySeal(body, key, webcrypto),
  verify: (body, key, proof) => verifyAuthoritySeal(body, key, proof, webcrypto),
}, payload => Response.json({ success: true, echoed: payload.scan.label }, { status: 202 }));
process.stdout.write(JSON.stringify({ status: response.status, body: await response.json() }));
'''
    async def send(outgoing):
        issued_at = json.loads(outgoing.content)["runtime_request"]["issued_at"]
        clock = f"Date.now = () => {issued_at * 1000};\n"
        result = subprocess.run(
            ["node", "--input-type=module", "-e", clock + script, str(package)], input=outgoing.content,
            capture_output=True, cwd=root, check=True, timeout=10,
        )
        response = json.loads(result.stdout)
        return httpx.Response(response["status"], json=response["body"])

    async with httpx.AsyncClient(transport=httpx.MockTransport(send)) as client:
        result = await scan_job.invoke_function(client, CONTROL, {"proof": "legacy-proof", "scan": {"label": "é 😀"}})
    assert result == {"status_code": 202, "body": {"success": True, "echoed": "é 😀"}}


@pytest.mark.asyncio
@pytest.mark.parametrize("variant", [
    "missing_receipt", "malformed_receipt", "invalid_proof", "http_status", "http_status_type", "build_id", "runtime_activation_id",
    "release_fingerprint", "nonce", "action", "function_name", "protocol", "extra_field", "malformed_json",
])
async def test_wrong_or_unproven_v9_response_is_a_retryable_503(runtime_env, variant):
    def send(outgoing):
        request = json.loads(outgoing.content)["runtime_request"]
        wire = {"success": True, "internal_detail": "unverified-body-not-for-caller"}
        if variant == "malformed_json":
            return httpx.Response(200, text="not json")
        if variant == "malformed_receipt":
            wire["_worker_runtime"] = True
        elif variant != "missing_receipt":
            different = {
                "invalid_proof": {},
                "http_status": {"http_status": 201},
                "http_status_type": {"http_status": 200.0},
            }.get(variant, {variant: "different"})
            wire["_worker_runtime"] = signed_receipt(CONTROL, request, 200, different)
            if variant == "invalid_proof":
                wire["_worker_runtime"]["proof"] = "0" * 64
        return httpx.Response(200, json=wire)

    async with httpx.AsyncClient(transport=httpx.MockTransport(send)) as client:
        assert await scan_job.invoke_function(client, CONTROL, {"proof": "legacy-proof"}) == UNVERIFIED


@pytest.mark.asyncio
async def test_missing_v9_identity_or_key_fails_before_sending_and_v8_keeps_legacy_wire(runtime_env, monkeypatch):
    payload = {"proof": "legacy-proof", "action": "read"}
    seen = []

    def send(outgoing):
        seen.append(outgoing.url.path)
        assert json.loads(outgoing.content) == payload
        return httpx.Response(202, json={"data": {"success": True}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(send)) as client:
        with monkeypatch.context() as isolated:
            isolated.delenv("SCAN_EVIDENCE_SIGNING_KEY")
            assert await scan_job.invoke_function(client, CONTROL, payload) == UNVERIFIED
        with monkeypatch.context() as isolated:
            isolated.setattr(scan_job, "V9_WORKER_FUNCTION_IDENTITIES", {})
            assert await scan_job.invoke_function(client, CONTROL, payload) == UNVERIFIED
        monkeypatch.setattr(scan_job, "V9_WORKER_FUNCTION_ROUTES", {CONTROL: CONTROL})
        assert await scan_job.invoke_function(client, CONTROL, payload) == UNVERIFIED
        assert await scan_job.probe_worker_runtime_identity(client, "durableScanWorkerControlV8") == UNVERIFIED
        assert await scan_job.invoke_function(client, "durableScanWorkerControlV8", payload) == {
            "status_code": 202, "body": {"success": True},
        }
    assert seen == ["/api/apps/test-app/functions/durableScanWorkerControlV8"]
