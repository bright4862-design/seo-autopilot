import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

const packageUrl = new URL("../../base44/functions/durableScanWorkerControlV9/", import.meta.url);
const source = readFileSync(new URL("entry.ts", packageUrl), "utf8");
const paths = [...new Set([...source.matchAll(/from "(\.\/[^"]+)"/g)].map(([, path]) => path))];
const modules = Object.fromEntries(await Promise.all(paths.map(async (path) => [
  path, await import(new URL(path, packageUrl)),
])));
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const load = new Function("exports", "require", "Deno", compiled);
const secret = "target-contact-bridge-test-key";
const { createAuthoritySeal, verifyAuthoritySeal } = modules["./authoritySeal.js"];
const { admissionSignature } = modules["./admissionClient.js"];
const serviceUrl = "https://coordinator.example.test";
const now = () => Math.floor(Date.now() / 1000);
const identity = {
  scan_id: "scan_test", project_id: "project_test", owner_user_id: "owner_test",
  request_id: "request_test", idempotency_key: "request_test", normalized_domain: "example.test", attempt_count: 1,
};
const claim = {
  owner_user_id: identity.owner_user_id, scan_id: identity.scan_id, request_id: identity.request_id,
  attempt_count: 1, barrier_generation: 4, claim_sequence: 12, scan_target_origin: "https://example.test:443",
  target_origin: "https://www.example.test:443", delivery_id: "1".repeat(32),
};

function fixture(t, { scanExists = true, scanAttempt = 1, upstream } = {}) {
  const requests = [];
  const website_url = "https://example.test/";
  const entities = {
    ScanRun: { get: async () => scanExists ? {
      ...identity, id: identity.scan_id, status: "crawling", pipeline_mode: "staged", website_url,
      attempt_count: scanAttempt, admission_barrier_generation: 4, admission_claim_sequence: 12,
      admission_target_origin: claim.scan_target_origin,
    } : null },
    BusinessProject: { get: async () => ({ id: identity.project_id, website_url, owner_user_id: identity.owner_user_id }) },
  };
  const dependencies = {
    ...modules,
    "npm:@base44/sdk@0.8.40": { createClientFromRequest: () => ({ asServiceRole: { entities } }) },
    "base44:runtime": { secrets: { get: (name) => ({
      SCAN_EVIDENCE_SIGNING_KEY: secret, SCAN_ADMISSION_COORDINATOR_URL: serviceUrl,
    })[name] } },
  };
  t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(options.redirect, "error");
    assert.equal(options.headers["x-fixlist-signature"], await admissionSignature(
      secret, options.headers["x-fixlist-timestamp"], options.body,
    ));
    requests.push([url, JSON.parse(options.body)]);
    return upstream();
  });
  let handler;
  load({}, (name) => {
    assert.ok(Object.hasOwn(dependencies, name), `Unexpected dependency ${name}`);
    return dependencies[name];
  }, { serve: (callback) => { handler = callback; }, env: { get: () => "" } });
  return { requests, invoke: (document) => handler(new Request("https://worker.example.test/", {
    method: "POST",
    headers: { "content-type": "application/json", "X-FixList-Worker": "scan_job_worker_v1_cloud_tasks" },
    body: JSON.stringify(document),
  })) };
}

async function envelope(action, targetContact, { wrap = true } = {}) {
  const body = {
    version: "durable_standard150_control_v1", action,
    scan_id: identity.scan_id, identity, failure: null, target_contact: targetContact,
  };
  const payload = { ...body, proof: await createAuthoritySeal(body, secret) };
  if (!wrap) return payload;
  const runtime_request = {
    protocol: "fixlist_worker_runtime_v1", function_name: "durableScanWorkerControlV9", action: "invoke",
    nonce: "2".repeat(32), issued_at: now(), payload,
    expected_build_id: modules["./generatedBuildId.js"].FUNCTION_BUILD_ID,
    expected_runtime_activation_id: "durableScanWorkerControlV9-staged-runtime-20261111-v3",
  };
  return { runtime_request, runtime_proof: await createAuthoritySeal(runtime_request, secret) };
}

test("exact V9 relays a redirect-origin acquire through the signed coordinator", async (t) => {
  const client = fixture(t, { upstream: () => Response.json({ success: true, outcome: "acquired", seconds_remaining: 103 }) });
  const contact = { ...claim, delivery_cutoff: now() + 120 };
  const response = await client.invoke(await envelope("acquire_target_contact", contact));
  assert.equal(response.status, 200);
  const body = await response.json();
  assert.equal(body.seconds_remaining, 103);
  assert.equal(await verifyAuthoritySeal(body._worker_runtime.receipt, secret, body._worker_runtime.proof), true);
  assert.deepEqual(client.requests, [[serviceUrl + "/acquire-target-contact", { ...contact, action: "acquire_target_contact_v1" }]]);
});

test("legacy envelopes and superseded attempts cannot reach the coordinator", async (t) => {
  const client = fixture(t, { scanAttempt: 2, upstream: () => assert.fail("A refused request reached the coordinator") });
  const contact = { ...claim, delivery_cutoff: now() + 120 };
  const unwrapped = await client.invoke(await envelope("acquire_target_contact", contact, { wrap: false }));
  assert.equal(unwrapped.status, 403);
  assert.equal((await unwrapped.json()).error_code, "worker_runtime_required");
  const old = await client.invoke(await envelope("acquire_target_contact", contact));
  assert.equal(old.status, 409);
  assert.equal((await old.json()).error_code, "superseded_attempt");
  assert.deepEqual(client.requests, []);
});

test("settlement still reaches the exact historical grant after the Base44 row is gone", async (t) => {
  const client = fixture(t, { scanExists: false, upstream: () => Response.json({ success: true, outcome: "protection_retained" }) });
  const contact = { ...claim, receipt: { drained_at: now(), observation: null } };
  const response = await client.invoke(await envelope("settle_target_contact", contact));
  assert.equal(response.status, 200);
  assert.equal((await response.json()).outcome, "protection_retained");
  assert.deepEqual(client.requests, [[serviceUrl + "/settle-target-contact", { ...contact, action: "settle_target_contact_v1" }]]);
});
