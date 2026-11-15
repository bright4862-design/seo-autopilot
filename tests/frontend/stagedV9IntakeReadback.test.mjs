import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";
import * as runtimeConfig from "../../base44/functions/fixlistStagedRuntimeControl/runtimeConfig.js";
import * as scanLimits from "../../base44/functions/startStandardScanJobV9/scanLimits.js";
import * as admission from "../../base44/functions/startStandardScanJobV9/admission.js";
import * as entitlement from "../../base44/functions/startStandardScanJobV9/entitlement.js";
import { admissionClaimEvidenceProof, verifyAdmissionClaimEvidence } from "../../base44/functions/startStandardScanJobV9/admissionClient.js";
import { enqueueScanDrain, enqueueScanJob, normalizeAttemptCount, paidDispatchGatewayUrl } from "../../base44/functions/startStandardScanJobV9/cloudTasks.js";
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
  launch = {},
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
    "./cloudTasks.js": { paidDispatchGatewayUrl },
    ...launch.modules,
    "./runtimeConfig.js": runtimeConfig,
    "./generatedReleaseContract.js": { ...releaseContract, RELEASE_FINGERPRINT: releaseFingerprint },
    "./generatedBuildId.js": { FUNCTION_BUILD_ID },
    "npm:@base44/sdk@0.8.31": {
      createClientFromRequest: () => ({
        auth: { me: async () => user },
        get asServiceRole() { return launch.entities ? { entities: launch.entities } : sideEffect("asServiceRole"); },
        get entities() { return sideEffect("entities"); },
        get functions() { return sideEffect("functions"); },
      }),
    },
    "base44:runtime": { secrets: { get: name => {
      secretReads.push(name);
      if (operator && ["SCAN_PIPELINE_MODE", "SCAN_STAGED_OWNER_IDS"].includes(name)) return settings[name];
      if (launch.entities && Object.hasOwn(gates, name)) return gates[name];
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
  const gatewayOrigin = "https://fixlist-dispatch-gateway.example.test";
  const fixture = harness({ settings: {
    ...staged, SCAN_STAGED_OWNER_IDS: `${secondOwner},${owner.id}`,
    SCAN_DISPATCH_GATEWAY_URL: gatewayOrigin,
  } });
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
    staged_rollout_scope: "off",
    staged_500_entitled_enabled: false,
    paid_dispatch_gateway_origin: gatewayOrigin,
    pipeline_mode: "staged",
    staged_owner_cohort_state: "explicit",
    staged_owner_count: 2,
    staged_owner_cohort_sha256: hash,
    staged_owner_enabled: true,
    intake_gate: "disabled",
    admission_gate: "enabled",
  });
  assert.deepEqual(fixture.envReads.sort(), [
    "SCAN_DISPATCH_GATEWAY_URL", "SCAN_PIPELINE_MODE", "SCAN_STAGED_500_ENTITLED_ENABLED", "SCAN_STAGED_OWNER_IDS", "SCAN_STAGED_ROLLOUT_SCOPE",
  ]);
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

const paidCustomer = { id: "paid_customer", email: "customer@example.test", role: "user" };
const paidGrant = {
  id: "access_paid",
  app_id: entitlement.ACCESS_APP_ID,
  plan_id: entitlement.ACCESS_PLAN_ID,
  owner_user_id: paidCustomer.id,
  user_email: paidCustomer.email,
  access_status: "active",
  has_full_access: true,
  grant_source: "stripe_checkout",
  stripe_checkout_session_id: "checkout_fixture",
  paid_at: "2026-11-15T00:00:00.000Z",
  page_cap: 150,
};

function launchHarness({
  rows = [paidGrant], rollout = "paid", entitled500 = "true", mode = "staged", cohort = "",
  gateway = "https://dispatch-gateway.example",
} = {}) {
  const settings = {
    ...(rollout === null ? {} : { SCAN_STAGED_ROLLOUT_SCOPE: rollout }),
    ...(entitled500 === null ? {} : { SCAN_STAGED_500_ENTITLED_ENABLED: entitled500 }),
    SCAN_PIPELINE_MODE: mode, SCAN_STAGED_OWNER_IDS: cohort,
    SCAN_TASKS_QUEUE_PATH: "projects/test/locations/europe-west1/queues/scan",
    SCAN_DRAIN_QUEUE_PATH: "projects/test/locations/europe-west1/queues/drain",
    SCAN_WORKER_URL: "https://worker.example/scan-job",
    SCAN_DISPATCH_GATEWAY_URL: gateway,
    TASKS_INVOKER_SERVICE_ACCOUNT: "invoker@example.test",
  };
  const signingKey = "mock admission signing key";
  const gates = {
    BETA_SCAN_INTAKE_ENABLED: "true", BETA_SCAN_ADMISSION_ENABLED: "true",
    SCAN_ADMISSION_COORDINATOR_URL: "https://coordinator.example", SCAN_EVIDENCE_SIGNING_KEY: signingKey,
  };
  const scans = [];
  const dispatched = [];
  const taskTransports = [];
  const calls = [];
  let binding = null;
  let claimEvidence;
  const project = { id: "project_01", owner_user_id: paidCustomer.id, website_url: "https://example.com/" };
  const matches = (row, query) => Object.entries(query).every(([key, value]) => row[key] === value);
  const fixture = harness({
    user: paidCustomer, settings, gates,
    launch: {
      entities: {
        Access: { filter: async query => rows.filter(row => matches(row, query)) },
        BusinessProject: { get: async id => id === project.id ? project : null },
        ScanRun: {
          filter: async query => scans.filter(row => matches(row, query)),
          get: async id => scans.find(row => row.id === id),
          create: async row => {
            calls.push("create");
            const scan = { id: "scan_01", ...row };
            scans.push(scan);
            return scan;
          },
          update: async (id, fields) => Object.assign(scans.find(row => row.id === id), fields),
        },
      },
      modules: {
        "./admission.js": admission,
        "./entitlement.js": entitlement,
        "./admissionClient.js": {
          verifyAdmissionClaimEvidence,
          claimAdmission: async ({ ownerUserId, requestId }) => {
            calls.push("claim");
            const replayed = binding?.request_id === requestId;
            if (!replayed) {
              claimEvidence = {
                version: "admission_claim_evidence_v1", owner_user_id: ownerUserId, request_id: requestId,
                barrier_generation: 4, claim_sequence: 23, admission_mode: "open",
                acceptance_cohort_id: "", acceptance_release_id: "", acceptance_source_sha: "", acceptance_expires_at: null,
              };
              binding = { ...claimEvidence, scan_id: "" };
            }
            return {
              ...binding, ok: true, outcome: replayed ? "replayed" : "claimed", claim_token: "test-claim",
              cohort_evidence: claimEvidence, cohort_evidence_proof: await admissionClaimEvidenceProof(claimEvidence, signingKey),
            };
          },
          statusAdmission: async () => {
            calls.push("status");
            return { ok: true, admission: binding };
          },
          bindAdmission: async ({ scanId }) => {
            calls.push("bind");
            binding.scan_id = scanId;
            return { ...binding, ok: true, outcome: "bound" };
          },
        },
        "./cloudTasks.js": {
          DRAIN_DELAY_SECONDS: 450, normalizeAttemptCount,
          paidDispatchGatewayUrl: () => paidDispatchGatewayUrl(name => settings[name]),
          enqueueScanDrain: async ({ requireGateway }) => {
            taskTransports.push({ stage: "drain", requireGateway });
            return { ok: true };
          },
          enqueueScanJob: async ({ payload, requireGateway }) => {
            taskTransports.push({ stage: "entry", requireGateway });
            dispatched.push(payload);
            return { ok: true };
          },
        },
      },
    },
  });
  const submit = (overrides = {}) => fixture.post({
    request_id: "paid_request_01", project_id: project.id, website_url: project.website_url,
    scan_mode: "standard_500", page_cap: 500, staged_rollout_scope: "paid", ...overrides,
  });
  return { submit, settings, calls, scans, dispatched, taskTransports };
}

test("paid rollout persists and dispatches the verified cap for a regular Stripe customer", async () => {
  for (const cap of [150, 500, "500"]) {
    const { submit, scans, dispatched, taskTransports } = launchHarness({ rows: [{ ...paidGrant, page_cap: cap }] });
    const result = await submit({ scan_mode: "standard_150" });
    const expected = cap === 500 ? 500 : 150;
    assert.equal(result.status, 200, JSON.stringify(result.body));
    assert.equal(result.body.page_cap, expected);
    for (const record of [scans[0], dispatched[0]]) {
      assert.equal(record.page_cap, expected);
      assert.equal(record.pipeline_mode, "staged");
      assert.equal(record.staged_rollout_scope, "paid");
    }
    assert.deepEqual(taskTransports, [{ stage: "drain", requireGateway: true }, { stage: "entry", requireGateway: true }]);
  }
});

test("paid routing accepts a verified manual 500 entitlement and leaves previews and manual 150 on monolith", async () => {
  const manual = { ...paidGrant, grant_source: "manual_grant", granted_at: paidGrant.paid_at };
  const pending = {
    ...paidGrant, access_status: "pending", grant_source: "checkout_pending", has_full_access: false,
    paid_at: "", stripe_checkout_session_id: "", page_cap: 500,
  };
  for (const [row, cap, pipeline] of [
    [{ ...manual, page_cap: 500 }, 500, "staged"],
    [manual, 150, "monolith"],
    [pending, 150, "monolith"],
  ]) {
    const { submit, scans, dispatched } = launchHarness({ rows: [row] });
    const result = await submit();
    assert.equal(result.status, 200, JSON.stringify(result.body));
    for (const record of [scans[0], dispatched[0]]) {
      assert.equal(record.page_cap, cap);
      assert.equal(record.pipeline_mode, pipeline);
      assert.equal(record.staged_rollout_scope, pipeline === "staged" ? "paid" : undefined);
    }
  }
});

test("default-off scope preserves the named pilot and declines a fresh unavailable 500 before any claim", async () => {
  const grant = { ...paidGrant, page_cap: 500, grant_source: "manual_grant", granted_at: paidGrant.paid_at };
  const pilot = launchHarness({ rows: [grant], rollout: null, entitled500: null, cohort: paidCustomer.id });
  assert.equal((await pilot.submit()).body.page_cap, 500);
  assert.equal(pilot.dispatched[0].staged_rollout_scope, undefined);
  assert.ok(pilot.taskTransports.every(task => !task.requireGateway));
  const paused = launchHarness({ rows: [grant], rollout: "off", entitled500: "false" });
  const result = await paused.submit();
  assert.equal(result.status, 503);
  assert.equal(result.body.failure_code, "scan_staged_500_unavailable");
  assert.deepEqual(paused.calls, ["status"]);
  assert.deepEqual(paused.scans, []);
  assert.deepEqual(paused.dispatched, []);
});

test("paid 500 uses an independent strict switch and keeps verified 150 available while off", async () => {
  for (const flag of [null, "False", "false", "TRUE"]) {
    const { settings, calls, submit } = launchHarness({ entitled500: flag, rows: [{ ...paidGrant, page_cap: 500 }] });
    const paused = await submit();
    assert.equal(paused.status, 503);
    assert.equal(paused.body.failure_code, "scan_staged_500_unavailable");
    assert.deepEqual(calls, ["status"]);
    const readback = await harness({ settings }).post();
    assert.equal(readback.body.staged_rollout_scope, "paid");
    assert.equal(readback.body.staged_500_entitled_enabled, false);
  }
  const standard = launchHarness({ entitled500: null });
  assert.equal((await standard.submit()).body.page_cap, 150);
  assert.equal(standard.dispatched[0].staged_rollout_scope, "paid");
  const readback = await harness({ settings: launchHarness().settings }).post();
  assert.equal(readback.body.staged_500_entitled_enabled, true);
});

test("turning off paid scope preserves exact bound replay without another claim or dispatch", async () => {
  const fixture = launchHarness({ rows: [{ ...paidGrant, page_cap: 500 }] });
  const original = await fixture.submit();
  assert.equal(original.status, 200, JSON.stringify(original.body));
  fixture.settings.SCAN_STAGED_ROLLOUT_SCOPE = "off";
  fixture.settings.SCAN_PIPELINE_MODE = "monolith";
  fixture.settings.SCAN_STAGED_500_ENTITLED_ENABLED = "false";
  const replay = await fixture.submit();
  assert.equal(replay.status, 200, JSON.stringify(replay.body));
  assert.equal(replay.body.scan_id, original.body.scan_id);
  assert.equal(replay.body.page_cap, 500);
  assert.equal(replay.body.replayed, true);
  assert.deepEqual(fixture.calls, ["claim", "create", "bind", "status"]);
  assert.equal(fixture.dispatched.length, 1);
  const different = await fixture.submit({ request_id: "paid_request_02" });
  assert.equal(different.body.failure_code, "scan_staged_500_unavailable");
  assert.equal(fixture.dispatched.length, 1);
  fixture.scans[0].admission_cohort_evidence_proof = "0".repeat(64);
  assert.equal((await fixture.submit()).body.failure_code, "scan_staged_500_unavailable");
});

test("turning off paid scope preserves admitted paid 150 without redispatching to an off route", async () => {
  const fixture = launchHarness();
  const original = await fixture.submit();
  assert.equal(original.status, 200, JSON.stringify(original.body));
  fixture.settings.SCAN_STAGED_ROLLOUT_SCOPE = "off";
  fixture.settings.SCAN_PIPELINE_MODE = "monolith";
  fixture.settings.SCAN_STAGED_500_ENTITLED_ENABLED = "false";
  const replay = await fixture.submit();
  assert.equal(replay.status, 200, JSON.stringify(replay.body));
  assert.equal(replay.body.scan_id, original.body.scan_id);
  assert.equal(replay.body.page_cap, 150);
  assert.equal(replay.body.pipeline_mode, "staged");
  assert.equal(replay.body.replayed, true);
  assert.equal(fixture.dispatched.length, 1);
});

test("unknown or inconsistent paid rollout is read back as invalid and blocks before claim", async () => {
  for (const config of [{ rollout: " paid " }, { mode: "monolith" }, { cohort: paidCustomer.id }, { rollout: "off" }]) {
    const fixture = launchHarness(config);
    const result = await fixture.submit();
    assert.equal(result.status, 503);
    assert.equal(result.body.failure_code, "scan_staged_rollout_configuration_invalid");
    assert.deepEqual(fixture.calls, []);
    const status = await harness({ settings: fixture.settings }).post();
    assert.equal(status.body.staged_rollout_scope, "invalid");
    assert.equal(status.body.staged_owner_enabled, false);
    assert.equal(status.body.pipeline_mode, "monolith");
    assert.doesNotMatch(JSON.stringify(status.body), new RegExp(paidCustomer.id));
  }
});

test("duplicate, revoked, and unverified grants fail before the server can choose paid staging", async () => {
  for (const rows of [
    [paidGrant, { ...paidGrant, id: "duplicate_access" }],
    [{ ...paidGrant, access_status: "revoked" }],
    [{ ...paidGrant, stripe_checkout_session_id: "" }],
    [{ ...paidGrant, grant_source: "owner_test", granted_at: paidGrant.paid_at, page_cap: 500 }],
  ]) {
    const fixture = launchHarness({ rows });
    const result = await fixture.submit();
    assert.ok([402, 409].includes(result.status), JSON.stringify(result.body));
    assert.deepEqual(fixture.calls, []);
    assert.deepEqual(fixture.dispatched, []);
  }
});

test("paid intake never claims without a usable configured signed gateway", async () => {
  for (const gateway of ["", "http://dispatch-gateway.example", "https://dispatch-gateway.example/path", "https://u:p@dispatch-gateway.example", "https://dispatch-gateway.example/?debug=1"]) {
    for (const cap of [150, 500]) {
      const fixture = launchHarness({ gateway, rows: [{ ...paidGrant, page_cap: cap }] });
      const result = await fixture.submit();
      assert.equal(result.status, 503, JSON.stringify(result.body));
      assert.equal(result.body.failure_code, "dispatch_gateway_not_configured");
      assert.deepEqual(fixture.calls, ["status"]);
      assert.deepEqual(fixture.scans, []);
      assert.deepEqual(fixture.taskTransports, []);
    }
  }
  const fixture = launchHarness({ rows: [{ ...paidGrant, page_cap: 500 }] });
  const original = await fixture.submit();
  assert.equal(original.status, 200);
  fixture.settings.SCAN_DISPATCH_GATEWAY_URL = "";
  const replay = await fixture.submit();
  assert.equal(replay.status, 200);
  assert.equal(replay.body.scan_id, original.body.scan_id);
  assert.equal(replay.body.replayed, true);
  assert.deepEqual(fixture.calls, ["claim", "create", "bind", "status"]);
  assert.equal(fixture.taskTransports.length, 2);
});

test("paid task transport independently prevents direct Cloud Tasks fallback", async t => {
  const priorDeno = globalThis.Deno;
  const priorFetch = globalThis.fetch;
  t.after(() => {
    if (priorDeno === undefined) delete globalThis.Deno;
    else globalThis.Deno = priorDeno;
    globalThis.fetch = priorFetch;
  });
  const observedEnv = [];
  const requests = [];
  let gateway = "";
  globalThis.Deno = { env: { get: name => {
    observedEnv.push(name);
    return name === "SCAN_DISPATCH_GATEWAY_URL" ? gateway : undefined;
  } } };
  globalThis.fetch = async (url, init) => {
    requests.push([url, init]);
    return Response.json({ error: "invalid_scan_mode" }, { status: 400 });
  };
  const args = {
    queuePath: "projects/test/locations/europe-west1/queues/scan",
    workerUrl: "https://worker.example/scan-job", invokerServiceAccount: "invoker@example.test",
    scanId: "scan_01", attemptCount: 1, signingKey: "mock gateway signing key",
  };
  const payload = { staged_rollout_scope: "paid", scan_mode: "standard_500", page_cap: 500 };
  const entry = () => enqueueScanJob({ ...args, payload });
  const drain = () => enqueueScanDrain({ ...args, payload: {}, requireGateway: true });
  for (const run of [entry, drain]) assert.equal((await run()).failureCode, "dispatch_gateway_not_configured");
  assert.deepEqual(requests, []);
  assert.ok(observedEnv.every(name => name === "SCAN_DISPATCH_GATEWAY_URL"));
  gateway = "https://dispatch-gateway.example/";
  for (const run of [entry, drain]) assert.equal((await run()).failureCode, "dispatch_gateway_invalid_scan_mode");
  assert.equal(requests.length, 2);
  for (const [url, init] of requests) {
    assert.equal(url, "https://dispatch-gateway.example/dispatch");
    assert.equal(init.redirect, "error");
    assert.match(init.headers["x-fixlist-signature"], /^[a-f0-9]{64}$/);
  }
  gateway = "";
  const legacy = await enqueueScanJob({ ...args, payload: { scan_mode: "standard_150" } });
  assert.equal(legacy.failureCode, "tasks_credentials_not_configured");
  assert.ok(observedEnv.includes("GCP_SERVICE_ACCOUNT_KEY"));
});
