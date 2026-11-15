import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";
import ts from "typescript";
import { createAuthoritySeal, verifyAuthoritySeal } from "../../base44/functions/persistDurableScanAuthorityV9/authoritySeal.js";

const secret = "offline-worker-runtime-key";
const protocol = "fixlist_worker_runtime_v1";
const workerHeader = "scan_job_worker_v1_cloud_tasks";
const versions = {
  durableScanWorkerControlV9: "durable_standard150_control_v1",
  persistDurableScanAuthorityV9: "durable_standard150_completion_v1",
  persistLimitedScanResultV9: "durable_standard150_limited_v1",
};

function loadHandler(name) {
  const entry = new URL(`../../base44/functions/${name}/entry.ts`, import.meta.url);
  const source = readFileSync(entry, "utf8");
  const load = createRequire(entry);
  const activationId = source.match(/BASE44_RUNTIME_ACTIVATION_ID\s*=\s*"([^"]+)"/)?.[1];
  const { FUNCTION_BUILD_ID: buildId } = load("./generatedBuildId.js");
  const { RELEASE_FINGERPRINT: fingerprint } = load("./generatedReleaseContract.js");
  let handler;
  let sdkCalls = 0;
  let entityReads = 0;
  const sdk = () => {
    sdkCalls++;
    const get = async () => { entityReads++; return null; };
    return { asServiceRole: { entities: { ScanRun: { get }, BusinessProject: { get } } } };
  };
  const dependencies = {
    "npm:@base44/sdk@0.8.40": { createClientFromRequest: sdk },
    "base44:runtime": { secrets: { get: key => key === "SCAN_EVIDENCE_SIGNING_KEY" ? secret : "" } },
  };
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  new Function("exports", "require", "Deno", compiled)(
    {}, key => dependencies[key] ?? load(key), { serve: fn => { handler = fn; } },
  );
  return {
    buildId, activationId, fingerprint,
    calls: () => ({ sdkCalls, entityReads }),
    async post(body, header = workerHeader) {
      const response = await handler(new Request("https://base44.example/worker", {
        method: "POST", headers: { "X-FixList-Worker": header }, body: JSON.stringify(body),
      }));
      return { status: response.status, headers: response.headers, body: await response.json() };
    },
  };
}

async function wrap(harness, name, changes = {}) {
  const request = {
    protocol, function_name: name, action: "identity", nonce: "b".repeat(32),
    issued_at: Math.floor(Date.now() / 1000), expected_build_id: harness.buildId,
    expected_runtime_activation_id: harness.activationId, payload: null, ...changes,
  };
  return { runtime_request: request, runtime_proof: await createAuthoritySeal(request, secret) };
}

async function assertReceipt(response, request, harness) {
  const { receipt, proof } = response.body._worker_runtime;
  assert.deepEqual(receipt, {
    protocol, function_name: request.function_name, action: request.action, nonce: request.nonce,
    build_id: harness.buildId, runtime_activation_id: harness.activationId,
    release_fingerprint: harness.fingerprint, http_status: response.status,
  });
  assert.equal(await verifyAuthoritySeal(receipt, secret, proof), true);
  assert.equal(response.headers.get("cache-control"), "no-store");
}

async function legacyPayload(name) {
  const version = versions[name];
  const document = name === "durableScanWorkerControlV9" ? { version, action: "read", scan_id: "scan_123" } : {
    version, identity: { scan_id: "scan_123", project_id: "project_123", owner_user_id: "owner_123", normalized_domain: "example.com" },
    scan: {}, review: { coverage_state: "limited_coverage", release_gate_eligible: false },
  };
  return { ...document, proof: await createAuthoritySeal(document, secret) };
}

for (const name of Object.keys(versions)) {
  test(`${name} signs exact current identity without creating a service client`, async () => {
    const harness = loadHandler(name);
    const envelope = await wrap(harness, name);
    const response = await harness.post(envelope);
    assert.equal(response.status, 200);
    assert.equal(response.body.success, true);
    await assertReceipt(response, envelope.runtime_request, harness);
    assert.deepEqual(harness.calls(), { sdkCalls: 0, entityReads: 0 });
  });

  test(`${name} fails closed on tampering, stale requests and expected identity mismatch`, async () => {
    const harness = loadHandler(name);
    const envelope = await wrap(harness, name, { action: "invoke", payload: await legacyPayload(name) });
    for (const [invalid, status, header] of [
      [envelope, 403, "wrong-worker"],
      [{ ...envelope, runtime_proof: "0".repeat(64) }, 403],
      [{ ...envelope, version: "legacy-fallback" }, 400],
      [await wrap(harness, "startStandardScanJobV9"), 400],
      [await wrap(harness, name, { nonce: "B".repeat(32) }), 400],
      [await wrap(harness, name, { issued_at: 1 }), 409],
      [await wrap(harness, name, { issued_at: Math.floor(Date.now() / 1000) + 300 }), 409],
    ]) {
      const response = await harness.post(invalid, header);
      assert.equal(response.status, status);
      assert.equal(response.body._worker_runtime, undefined);
    }
    for (const changes of [
      { expected_build_id: "a".repeat(64) }, { expected_runtime_activation_id: "wrong-activation" },
    ]) {
      const mismatch = await wrap(harness, name, { ...envelope.runtime_request, ...changes });
      const response = await harness.post(mismatch);
      assert.equal(response.status, 503);
      assert.equal(response.body.error_code, "worker_runtime_identity_mismatch");
      await assertReceipt(response, mismatch.runtime_request, harness);
    }
    assert.deepEqual(harness.calls(), { sdkCalls: 0, entityReads: 0 });
  });

  test(`${name} dispatches authenticated legacy payloads, and wrapped legacy errors carry receipts`, async () => {
    const harness = loadHandler(name);
    const payload = await legacyPayload(name);
    const invalidInner = await wrap(harness, name, { action: "invoke", payload: { ...payload, proof: "0".repeat(64) } });
    const invalidResponse = await harness.post(invalidInner);
    assert.equal(invalidResponse.status, 409);
    await assertReceipt(invalidResponse, invalidInner.runtime_request, harness);
    assert.deepEqual(harness.calls(), { sdkCalls: 0, entityReads: 0 });

    const wrapped = await wrap(harness, name, { action: "invoke", payload });
    const wrappedResponse = await harness.post(wrapped);
    assert.equal(wrappedResponse.status, 404);
    await assertReceipt(wrappedResponse, wrapped.runtime_request, harness);
    const legacy = await harness.post(payload);
    const { _worker_runtime, ...original } = wrappedResponse.body;
    assert.equal(legacy.status, wrappedResponse.status);
    assert.deepEqual(legacy.body, original);
    assert.equal(harness.calls().sdkCalls, 2);
    assert.ok(harness.calls().entityReads >= 2);
  });
}
