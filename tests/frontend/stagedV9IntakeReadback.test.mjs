import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";
import * as runtimeConfig from "../../base44/functions/fixlistStagedRuntimeControl/runtimeConfig.js";
import * as scanLimits from "../../base44/functions/startStandardScanJobV9/scanLimits.js";
import * as releaseContract from "../../base44/functions/startStandardScanJobV9/generatedReleaseContract.js";
import { FUNCTION_BUILD_ID } from "../../base44/functions/startStandardScanJobV9/generatedBuildId.js";

const entry = new URL("../../base44/functions/startStandardScanJobV9/entry.ts", import.meta.url);
const source = readFileSync(entry, "utf8");
const operatorEntry = new URL("../../base44/functions/fixlistStagedRuntimeControl/entry.ts", import.meta.url);
function compileHandler(text) {
  const compiled = ts.transpileModule(text, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  return new Function("exports", "require", "Deno", compiled);
}
const loadIntake = compileHandler(source);
const loadOperator = compileHandler(readFileSync(operatorEntry, "utf8"));
const owner = { id: "6a498da58ef5cec1f5cd4486", email: "bright4862@gmail.com", role: "admin" };
const london = { id: "6a498732ec779dfaaeab0e54", email: "londonparisbrussels@gmail.com", role: "admin" };
const secondOwner = "ZZ_owner_002";
const action = "staged_runtime_status";
const staged = { SCAN_PIPELINE_MODE: "staged", SCAN_STAGED_OWNER_IDS: owner.id };

function harness({
  user = owner,
  settings = staged,
  gates = { BETA_SCAN_INTAKE_ENABLED: "false", BETA_SCAN_ADMISSION_ENABLED: "true" },
  releaseFingerprint = releaseContract.RELEASE_FINGERPRINT,
  operator = false,
} = {}) {
  const envReads = [];
  const secretReads = [];
  const sideEffects = [];
  function sideEffect(name) {
    sideEffects.push(name);
    throw new Error(`Unexpected call to ${name}`);
  }
  const dependencies = {
    "./scanLimits.js": scanLimits,
    "./runtimeConfig.js": runtimeConfig,
    "./generatedReleaseContract.js": { ...releaseContract, RELEASE_FINGERPRINT: releaseFingerprint },
    "./generatedBuildId.js": { FUNCTION_BUILD_ID },
    "npm:@base44/sdk@0.8.31": {
      createClientFromRequest: () => ({
        auth: { me: async () => user },
        get asServiceRole() { return sideEffect("asServiceRole"); },
        get entities() { return sideEffect("entities"); },
        get functions() { return sideEffect("functions"); },
      }),
    },
    "base44:runtime": { secrets: { get: name => {
      secretReads.push(name);
      if (operator && ["SCAN_PIPELINE_MODE", "SCAN_STAGED_OWNER_IDS"].includes(name)) return settings[name];
      if (name !== "BETA_SCAN_INTAKE_ENABLED" && name !== "BETA_SCAN_ADMISSION_ENABLED") {
        return sideEffect(`secrets.get:${name}`);
      }
      return gates[name];
    } } },
  };
  const handler = {};
  const loadHandler = operator ? loadOperator : loadIntake;
  loadHandler(handler, name => dependencies[name] || new Proxy({}, {
    get: (_, key) => sideEffect(`${name}:${String(key)}`),
  }), { env: { get: name => { envReads.push(name); return settings[name]; } } });
  return {
    envReads,
    secretReads,
    sideEffects,
    async post(body = { action: operator ? "status" : action }) {
      const name = operator ? "fixlistStagedRuntimeControl" : "startStandardScanJobV9";
      const response = await handler.default(new Request(`https://base44.example/api/functions/${name}`, {
        method: "POST",
        body: JSON.stringify(body),
      }));
      return { status: response.status, cacheControl: response.headers.get("cache-control"), body: await response.json() };
    },
  };
}

test("actual V9 intake returns a closed, no-store owner-only settings and release readback", async () => {
  const fixture = harness({ settings: { ...staged, SCAN_STAGED_OWNER_IDS: `${secondOwner},${owner.id}` } });
  const { status, cacheControl, body } = await fixture.post({ data: { action } });
  const hash = createHash("sha256").update(JSON.stringify([owner.id, secondOwner])).digest("hex");
  const activation = source.match(/BASE44_RUNTIME_ACTIVATION_ID\s*=\s*"([^"]+)"/)[1];
  assert.equal(status, 200);
  assert.equal(cacheControl, "no-store");
  assert.ok(Math.abs(Date.now() - Date.parse(body.observed_at)) < 30_000);
  assert.deepEqual(body, {
    success: true,
    schema_version: "fixlist_staged_v9_intake_readback_v1",
    observed_at: body.observed_at,
    build_id: FUNCTION_BUILD_ID,
    runtime_activation_id: activation,
    release_fingerprint: releaseContract.RELEASE_FINGERPRINT,
    configured_pipeline_mode: "staged",
    pipeline_mode: "staged",
    staged_owner_cohort_state: "explicit",
    staged_owner_count: 2,
    staged_owner_cohort_sha256: hash,
    staged_owner_enabled: true,
    intake_gate: "disabled",
    admission_gate: "enabled",
  });
  assert.deepEqual(fixture.envReads.sort(), ["SCAN_PIPELINE_MODE", "SCAN_STAGED_OWNER_IDS"]);
  assert.deepEqual(fixture.secretReads, ["BETA_SCAN_INTAKE_ENABLED", "BETA_SCAN_ADMISSION_ENABLED"]);
  assert.deepEqual(fixture.sideEffects, []);
});

test("both runtime probes attest only the authenticated Bright or London administrator's cohort membership", async () => {
  for (const operator of [false, true]) {
    for (const user of [owner, london]) {
      for (const stagedAccount of [owner, london]) {
        const fixture = harness({ user, operator, settings: { ...staged, SCAN_STAGED_OWNER_IDS: stagedAccount.id } });
        const { status, cacheControl, body } = await fixture.post();
        assert.equal(status, 200);
        assert.equal(cacheControl, "no-store");
        assert.equal(body.success, true);
        assert.equal(body.staged_owner_enabled, user.id === stagedAccount.id);
        if (operator) assert.equal(body.owner_match, user.id === stagedAccount.id);
        const serialized = JSON.stringify(body);
        for (const account of [owner, london]) {
          assert.equal(serialized.includes(account.id), false);
          assert.equal(serialized.includes(account.email), false);
        }
        assert.deepEqual(fixture.sideEffects, []);
      }
    }
  }
});

test("both probes reject crossed ID and email pairs and non-admin London before reading settings", async () => {
  for (const operator of [false, true]) {
    for (const user of [
      { ...owner, email: london.email },
      { ...london, email: owner.email },
      { ...london, role: "user" },
      { ...london, id: "unknown_admin" },
    ]) {
      const fixture = harness({ user, operator, settings: { ...staged, SCAN_STAGED_OWNER_IDS: london.id } });
      const { status, body } = await fixture.post();
      assert.equal(status, 403);
      assert.deepEqual(body, { success: false, error_code: "owner_only" });
      assert.deepEqual(fixture.envReads, []);
      assert.deepEqual(fixture.secretReads, []);
      assert.deepEqual(fixture.sideEffects, []);
    }
  }
});

test("readback distinguishes effective launch routing from malformed or incomplete configuration", async () => {
  for (const [settings, configuredMode, state, enabled] of [
    [staged, "staged", "explicit", true],
    [{ ...staged, SCAN_PIPELINE_MODE: " staged " }, "invalid", "explicit", false],
    [{ ...staged, SCAN_STAGED_OWNER_IDS: ` ${owner.id},${owner.id}` }, "staged", "invalid", true],
    [{ ...staged, SCAN_STAGED_OWNER_IDS: secondOwner }, "staged", "explicit", false],
    [{ SCAN_PIPELINE_MODE: "monolith", SCAN_STAGED_OWNER_IDS: "" }, "monolith", "empty", false],
    [{}, "absent", "absent", false],
  ]) {
    const fixture = harness({ settings });
    const { status, body } = await fixture.post();
    assert.equal(status, 200);
    assert.equal(body.configured_pipeline_mode, configuredMode);
    assert.equal(body.staged_owner_cohort_state, state);
    assert.equal(body.staged_owner_enabled, enabled);
    assert.equal(body.pipeline_mode, enabled ? "staged" : "monolith");
    if (state === "invalid" || state === "absent") {
      assert.equal(body.staged_owner_count, null);
      assert.equal(body.staged_owner_cohort_sha256, null);
    }
    const access = { has_full_access: true, access_status: "active", page_cap: 500 };
    const contract = scanLimits.resolveServerScanContract({ access, ownerUserId: owner.id, env: name => settings[name] });
    assert.equal(contract.pipeline_mode, body.pipeline_mode);
    assert.equal(contract.page_cap, enabled ? 500 : 150);
    if (settings === staged) {
      assert.equal(body.staged_owner_count, 1);
      assert.equal(body.staged_owner_cohort_sha256, createHash("sha256").update(JSON.stringify([owner.id])).digest("hex"));
      const standard = scanLimits.resolveServerScanContract({ ownerUserId: owner.id, env: name => settings[name] });
      assert.deepEqual(standard, { scan_mode: "standard_150", page_cap: 150, pipeline_mode: "staged" });
    }
    assert.deepEqual(fixture.sideEffects, []);
  }
});

test("auth, release and closed request shape reject before any configuration reads or scan activity", async () => {
  const attempts = [
    [harness({ user: null }), undefined, 401],
    [harness({ user: { ...owner, id: "another_admin" } }), undefined, 403],
    [harness({ user: { ...owner, email: "another@example.test" } }), undefined, 403],
    [harness({ user: { ...owner, role: "user" } }), undefined, 403],
    [harness({ releaseFingerprint: "bad-fingerprint" }), undefined, 503],
    [harness(), { action, request_id: "supplied-id", project_id: "supplied-project" }, 400],
    [harness(), { data: { action }, request_id: "supplied-id" }, 400],
    [harness(), { action, data: { request_id: "supplied-id" } }, 400],
    [harness(), { input: { action, request_id: "supplied-id" } }, 400],
  ];
  for (const [fixture, input, expectedStatus] of attempts) {
    const result = await fixture.post(input);
    assert.equal(result.status, expectedStatus);
    assert.equal(result.body.success, false);
    assert.doesNotMatch(JSON.stringify(result.body), /staged_owner|supplied-id|supplied-project/);
    assert.deepEqual(fixture.envReads, []);
    assert.deepEqual(fixture.secretReads, []);
    assert.deepEqual(fixture.sideEffects, []);
  }
});

test("an unreadable intake runtime fails safely and normal launch validation remains available", async () => {
  const unavailable = harness({ settings: new Proxy({}, { get() { throw new Error("private environment value"); } }) });
  const readback = await unavailable.post();
  assert.deepEqual(readback, {
    status: 503,
    cacheControl: "no-store",
    body: { success: false, error_code: "runtime_unavailable" },
  });
  assert.deepEqual(unavailable.sideEffects, []);
  assert.deepEqual(unavailable.secretReads, []);
  const badGates = harness({ gates: {
    BETA_SCAN_INTAKE_ENABLED: "True",
    get BETA_SCAN_ADMISSION_ENABLED() { throw new Error("private secret service error"); },
  } });
  const badGateReadback = await badGates.post();
  assert.equal(badGateReadback.status, 200);
  assert.equal(badGateReadback.body.intake_gate, "unavailable");
  assert.equal(badGateReadback.body.admission_gate, "unavailable");
  assert.doesNotMatch(JSON.stringify(badGateReadback.body), /True|private/);
  assert.deepEqual(badGates.sideEffects, []);
  const customer = harness({ user: { id: "customer_user", email: "customer@example.test", role: "user" } });
  const launch = await customer.post({ scan_mode: "standard_150" });
  assert.equal(launch.status, 400);
  assert.equal(launch.body.error, "A durable request_id is required.");
  assert.deepEqual(customer.envReads, []);
  assert.deepEqual(customer.secretReads, []);
  assert.deepEqual(customer.sideEffects, []);
});
