import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";
import * as runtimeConfig from "../../base44/functions/fixlistStagedRuntimeControl/runtimeConfig.js";
import * as scanLimits from "../../base44/functions/startStandardScanJobV9/scanLimits.js";
import * as admission from "../../base44/functions/startStandardScanJobV9/admission.js";
import * as entitlement from "../../base44/functions/startStandardScanJobV9/entitlement.js";
import * as admissionClient from "../../base44/functions/startStandardScanJobV9/admissionClient.js";
import { admissionClaimEvidenceProof, verifyAdmissionClaimEvidence } from "../../base44/functions/startStandardScanJobV9/admissionClient.js";
import { enqueueScanDrain, enqueueScanJob, normalizeAttemptCount, stagedDispatchGatewayUrl } from "../../base44/functions/startStandardScanJobV9/cloudTasks.js";
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
    "./cloudTasks.js": { stagedDispatchGatewayUrl },
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
      if (["SCAN_STAGED_PILOT_OWNER_IDS", "SCAN_PUBLIC_PILOT_EXPIRES_AT",
        "SCAN_STAGED_500_ELIGIBLE_ADMISSION_ENABLED"].includes(name)) return gates[name];
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
      const result = { status: response.status, cacheControl: response.headers.get("cache-control"), body: await response.json() };
      const retryAfter = response.headers.get("retry-after");
      return retryAfter === null ? result : { ...result, retryAfter };
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
    legacy_staged_500_entitled_enabled: false,
    staged_pilot_owner_count: 0,
    staged_pilot_owner_cohort_sha256: createHash("sha256").update("[]").digest("hex"),
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
    "SCAN_DISPATCH_GATEWAY_URL", "SCAN_PIPELINE_MODE", "SCAN_PUBLIC_PILOT_EXPIRES_AT",
    "SCAN_STAGED_500_ENTITLED_ENABLED", "SCAN_STAGED_OWNER_IDS", "SCAN_STAGED_ROLLOUT_SCOPE",
  ]);
  assert.deepEqual(fixture.secretReads, ["SCAN_STAGED_500_ELIGIBLE_ADMISSION_ENABLED", "SCAN_STAGED_PILOT_OWNER_IDS", "BETA_SCAN_INTAKE_ENABLED", "BETA_SCAN_ADMISSION_ENABLED"]);
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
  gateway = "https://dispatch-gateway.example", claimFailure, echoClaimOrigin = false, omitPersistedOrigin = false,
  publicPilotExpiresAt, acknowledgePilot = true, pilotOwners, pilotClaimCap, claimMode, user = paidCustomer,
  acknowledgeCap = true, invalidClaimProof = false, interruptBeforeDrain = false,
  acknowledgeEligible500 = true, legacyEntitled500 = "false",
} = {}) {
  const settings = {
    ...(rollout === null ? {} : { SCAN_STAGED_ROLLOUT_SCOPE: rollout }),
    SCAN_STAGED_500_ENTITLED_ENABLED: legacyEntitled500,
    SCAN_PIPELINE_MODE: mode, SCAN_STAGED_OWNER_IDS: cohort,
    SCAN_TASKS_QUEUE_PATH: "projects/test/locations/europe-west1/queues/scan",
    SCAN_DRAIN_QUEUE_PATH: "projects/test/locations/europe-west1/queues/drain",
    SCAN_WORKER_URL: "https://worker.example/scan-job",
    SCAN_DISPATCH_GATEWAY_URL: gateway,
    TASKS_INVOKER_SERVICE_ACCOUNT: "invoker@example.test",
  };
  if (publicPilotExpiresAt !== undefined) settings.SCAN_PUBLIC_PILOT_EXPIRES_AT = publicPilotExpiresAt;
  if (pilotOwners !== undefined) settings.SCAN_STAGED_PILOT_OWNER_IDS = pilotOwners;
  const signingKey = "mock admission signing key";
  const gates = {
    BETA_SCAN_INTAKE_ENABLED: "true", BETA_SCAN_ADMISSION_ENABLED: "true",
    SCAN_ADMISSION_COORDINATOR_URL: "https://coordinator.example", SCAN_EVIDENCE_SIGNING_KEY: signingKey,
    SCAN_STAGED_PILOT_OWNER_IDS: pilotOwners, SCAN_PUBLIC_PILOT_EXPIRES_AT: publicPilotExpiresAt,
    SCAN_STAGED_500_ELIGIBLE_ADMISSION_ENABLED: entitled500,
  };
  const scans = [];
  const dispatched = [];
  const taskTransports = [];
  const calls = [];
  const admittedOrigins = [];
  const claimRequests = [];
  let binding = null;
  let claimEvidence;
  const project = { id: "project_01", owner_user_id: user.id, website_url: "https://example.com/" };
  const matches = (row, query) => Object.entries(query).every(([key, value]) => row[key] === value);
  const fixture = harness({
    user, settings, gates,
    launch: {
      entities: {
        Access: {
          filter: async query => rows.filter(row => matches(row, query)),
          create: async row => {
            calls.push("create_preview_access");
            const created = { id: "new_preview_access", ...row };
            rows.push(created);
            return created;
          },
        },
        BusinessProject: { get: async id => id === project.id ? project : null },
        ScanRun: {
          filter: async query => scans.filter(row => matches(row, query)),
          get: async id => scans.find(row => row.id === id),
          create: async row => {
            calls.push("create");
            const scan = { id: "scan_01", ...row };
            if (omitPersistedOrigin) delete scan.admission_target_origin;
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
          ...admissionClient,
          verifyAdmissionClaimEvidence,
          claimAdmission: async ({
            ownerUserId, requestId, targetOrigin, pilotLauncherBuildId, pilotPageCap, pilotReplayOnly,
            standard150LauncherBuildId, standard500LauncherBuildId,
          }) => {
            claimRequests.push({
              pilotLauncherBuildId, pilotPageCap, ...(pilotReplayOnly ? { pilotReplayOnly } : {}),
              ...(standard150LauncherBuildId ? { standard150LauncherBuildId } : {}),
              ...(standard500LauncherBuildId ? { standard500LauncherBuildId } : {}),
            });
            calls.push("claim");
            admittedOrigins.push(targetOrigin);
            if (claimFailure) return claimFailure;
            const replayed = binding?.request_id === requestId;
            if (pilotReplayOnly && !replayed) {
              return { ok: false, status: 423, failureCode: "scan_intake_paused" };
            }
            if (!replayed) {
              const mode = claimMode ?? (pilotLauncherBuildId || standard500LauncherBuildId ? "acceptance_only" : "open");
              const cohortKind = mode === "acceptance_only" ? (pilotLauncherBuildId ? "pilot" : "eligible500") : "";
              claimEvidence = {
                version: "admission_claim_evidence_v1", owner_user_id: ownerUserId, request_id: requestId,
                barrier_generation: 4, claim_sequence: 23, admission_mode: mode,
                acceptance_cohort_id: cohortKind ? `${cohortKind}_cohort` : "",
                acceptance_release_id: cohortKind ? `${cohortKind}_release` : "",
                acceptance_source_sha: cohortKind ? "a".repeat(40) : "",
                acceptance_expires_at: cohortKind ? Number(publicPilotExpiresAt ?? 1800000000) : null,
              };
              binding = {
                ...claimEvidence, scan_id: "",
                ...(echoClaimOrigin ? { target_origin: targetOrigin } : {}),
                ...(acknowledgePilot && pilotLauncherBuildId ? { pilot_launcher_build_id: pilotLauncherBuildId } : {}),
                ...(acknowledgeEligible500 && standard500LauncherBuildId
                  ? { standard_500_launcher_build_id: standard500LauncherBuildId } : {}),
                ...(acknowledgeCap && (pilotClaimCap ?? pilotPageCap) !== undefined ? { pilot_page_cap: pilotClaimCap ?? pilotPageCap } : {}),
              };
            }
            return {
              ...binding, ok: true, outcome: replayed ? "replayed" : "claimed", claim_token: "test-claim",
              cohort_evidence: claimEvidence,
              cohort_evidence_proof: invalidClaimProof ? "0".repeat(64) : await admissionClaimEvidenceProof(claimEvidence, signingKey),
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
          stagedDispatchGatewayUrl: () => stagedDispatchGatewayUrl(name => settings[name]),
          enqueueScanDrain: async ({ requireGateway }) => {
            if (interruptBeforeDrain) {
              interruptBeforeDrain = false;
              throw new Error("fixture interruption after binding and before enqueue");
            }
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
  return { submit, settings, gates, calls, scans, dispatched, taskTransports, admittedOrigins, claimRequests,
    options: () => fixture.post({ action: "published_scan_options" }) };
}

test("V9 target cooldown returns a generic 429 before accepting a paid or preview scan", async () => {
  const pendingPreview = {
    id: "pending_01", owner_user_id: paidCustomer.id, user_email: paidCustomer.email,
    access_status: "pending", has_full_access: false, plan_id: entitlement.ACCESS_PLAN_ID,
    grant_source: "checkout_pending", app_id: entitlement.ACCESS_APP_ID,
  };
  for (const grant of [{ ...paidGrant, page_cap: 150 }, { ...paidGrant, page_cap: 500 }, pendingPreview]) {
    const fixture = launchHarness({
      rows: [grant],
      claimFailure: { ok: false, status: 429, failureCode: "target_cooldown_active", retryAfterSeconds: 3600 },
    });
    const result = await fixture.submit({
      website_url: "https://WWW.example.com:8443/test?location=local",
      target_origin: "https://unrelated.example:443",
    });
    assert.deepEqual(fixture.admittedOrigins, ["https://www.example.com:8443"]);
    assert.equal(result.status, 429);
    assert.equal(result.retryAfter, "3600");
    assert.equal(result.body.success, false);
    assert.equal(result.body.accepted, false);
    assert.equal(result.body.failure_code, "target_cooldown_active");
    assert.equal(result.body.retry_after, 3600);
    assert.equal(result.body.retry_after_seconds, 3600);
    assert.match(result.body.error, /site.*wait/i);
    assert.deepEqual(fixture.calls, ["claim"]);
    assert.deepEqual(fixture.scans, []);
    assert.deepEqual(fixture.dispatched, []);
    assert.deepEqual(fixture.taskTransports, []);
  }
});

test("V9 target cooldown opt-in is durable only for a confirmed coordinator lease", async () => {
  for (const echoClaimOrigin of [false, true]) {
    const fixture = launchHarness({ echoClaimOrigin });
    const launched = await fixture.submit({
      target_origin: "https://unrelated.example:443",
      admission_target_origin: "https://unrelated.example:443",
    });
    assert.equal(launched.status, 200);
    assert.equal(fixture.scans.length, 1);
    assert.equal(fixture.scans[0].admission_target_origin, echoClaimOrigin ? "https://example.com:443" : undefined);
    const replay = await fixture.submit();
    assert.equal(replay.status, 200);
    assert.equal(replay.body.replayed, true);
    assert.equal(fixture.scans.length, 1);
  }
});

test("V9 target cooldown never dispatches a new-era row missing its confirmed origin", async () => {
  const fixture = launchHarness({ echoClaimOrigin: true, omitPersistedOrigin: true });
  const missing = await fixture.submit();
  assert.equal(missing.status, 503);
  assert.equal(missing.body.failure_code, "admission_target_origin_not_saved");
  const replay = await fixture.submit();
  assert.equal(replay.status, 202);
  assert.equal(replay.body.failure_code, "scan_admission_pending");
  assert.deepEqual(fixture.calls, ["claim", "create", "claim"]);
  assert.equal(fixture.scans.length, 1);
  assert.deepEqual(fixture.taskTransports, []);
});

test("V9 sends the target cooldown key and exact 150 launcher through the signed claim transport", async () => {
  const signingKey = "claim test key";
  const options = {
    ownerUserId: "owner_123", requestId: "request_123", requestFingerprint: "fingerprint",
    coordinatorUrl: "https://coordinator.example", signingKey,
    env: () => "true",
  };
  const requests = [];
  const fetchImpl = async (url, request) => {
    assert.equal(url, "https://coordinator.example/claim");
    const expected = await admissionClient.admissionSignature(
      signingKey, request.headers["x-fixlist-timestamp"], request.body,
    );
    assert.equal(request.headers["x-fixlist-signature"], expected);
    requests.push(JSON.parse(request.body));
    return Response.json({ success: false, error: "target_cooldown_active", retry_after_seconds: 19 }, { status: 429, headers: { "Retry-After": "19" } });
  };
  const result = await admissionClient.claimAdmission({
    ...options, targetOrigin: "https://example.com:443", standard150LauncherBuildId: FUNCTION_BUILD_ID, fetchImpl,
  });
  assert.equal(requests[0].target_origin, "https://example.com:443");
  assert.equal(requests[0].standard_150_launcher_build_id, FUNCTION_BUILD_ID);
  assert.equal(result.failureCode, "target_cooldown_active");
  assert.equal(result.retryAfterSeconds, 19);
  await admissionClient.claimAdmission({ ...options, fetchImpl });
  assert.equal(Object.hasOwn(requests[1], "target_origin"), false);
  assert.equal(Object.hasOwn(requests[1], "standard_150_launcher_build_id"), false);
});

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
  assert.deepEqual(pilot.taskTransports, [{ stage: "drain", requireGateway: true }, { stage: "entry", requireGateway: true }]);
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
    const { settings, gates, calls, submit } = launchHarness({ entitled500: flag, rows: [{ ...paidGrant, page_cap: 500 }] });
    const paused = await submit();
    assert.equal(paused.status, 503);
    assert.equal(paused.body.failure_code, "scan_staged_500_unavailable");
    assert.deepEqual(calls, ["status"]);
    const readback = await harness({ settings, gates }).post();
    assert.equal(readback.body.staged_rollout_scope, "paid");
    assert.equal(readback.body.staged_500_entitled_enabled, false);
  }
  const standard = launchHarness({ entitled500: null });
  assert.equal((await standard.submit()).body.page_cap, 150);
  assert.equal(standard.dispatched[0].staged_rollout_scope, "paid");
  const { settings, gates } = launchHarness();
  const readback = await harness({ settings, gates }).post();
  assert.equal(readback.body.staged_500_entitled_enabled, true);
});

test("turning off paid scope preserves exact bound replay without another claim or dispatch", async () => {
  const fixture = launchHarness({ rows: [{ ...paidGrant, page_cap: 500 }] });
  const original = await fixture.submit();
  assert.equal(original.status, 200, JSON.stringify(original.body));
  fixture.settings.SCAN_STAGED_ROLLOUT_SCOPE = "off";
  fixture.settings.SCAN_PIPELINE_MODE = "monolith";
  fixture.gates.SCAN_STAGED_500_ELIGIBLE_ADMISSION_ENABLED = "false";
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

test("broad 500 only sends and accepts typed admission on the new mutable entitlement switch", async () => {
  const access = [{ ...paidGrant, page_cap: 500 }];
  const legacy = launchHarness({ rows: access, entitled500: null, legacyEntitled500: "true" });
  assert.equal((await legacy.submit()).body.failure_code, "scan_staged_500_unavailable");
  assert.equal(legacy.claimRequests.length, 0);

  for (const config of [{ acknowledgeEligible500: false }, { claimMode: "open" }]) {
    const unsupported = launchHarness({ rows: access, ...config });
    assert.equal((await unsupported.submit()).body.failure_code, "admission_claim_evidence_invalid");
    assert.equal(unsupported.scans.length, 0);
    assert.equal(unsupported.dispatched.length, 0);
  }

  const enabled = launchHarness({ rows: access });
  assert.equal((await enabled.submit()).body.page_cap, 500);
  assert.deepEqual(enabled.claimRequests[0], {
    pilotLauncherBuildId: undefined, pilotPageCap: undefined, standard500LauncherBuildId: FUNCTION_BUILD_ID,
  });

  const held = launchHarness({
    rows: access, claimFailure: { ok: false, status: 423, failureCode: "scan_intake_paused" },
  });
  assert.equal((await held.submit()).body.failure_code, "scan_staged_500_unavailable");
  assert.equal(held.scans.length, 0);
  assert.equal(held.dispatched.length, 0);

  const elevated = { ...paidCustomer, role: "admin" };
  const admin = launchHarness({ rows: access, user: elevated });
  assert.equal((await admin.submit()).body.failure_code, "scan_staged_500_unavailable");
  assert.equal(admin.claimRequests.length, 0);
});


test("turning off paid scope preserves admitted paid 150 without redispatching to an off route", async () => {
  const fixture = launchHarness();
  const original = await fixture.submit();
  assert.equal(original.status, 200, JSON.stringify(original.body));
  fixture.settings.SCAN_STAGED_ROLLOUT_SCOPE = "off";
  fixture.settings.SCAN_PIPELINE_MODE = "monolith";
  fixture.gates.SCAN_STAGED_500_ELIGIBLE_ADMISSION_ENABLED = "false";
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
    const status = await harness({ settings: fixture.settings, gates: fixture.gates }).post();
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

test("staged intake never claims without a usable configured signed gateway", async () => {
  const routes = [
    {},
    { rollout: null, entitled500: null, cohort: paidCustomer.id },
  ];
  for (const gateway of ["", "http://dispatch-gateway.example", "https://dispatch-gateway.example/path", "https://u:p@dispatch-gateway.example", "https://dispatch-gateway.example/?debug=1"]) {
    for (const route of routes) {
      for (const cap of [150, 500]) {
        const fixture = launchHarness({ ...route, gateway, rows: [{ ...paidGrant, page_cap: cap }] });
        const result = await fixture.submit();
        assert.equal(result.status, 503, JSON.stringify(result.body));
        assert.equal(result.body.failure_code, "dispatch_gateway_not_configured");
        assert.deepEqual(fixture.calls, ["status"]);
        assert.deepEqual(fixture.scans, []);
        assert.deepEqual(fixture.taskTransports, []);
      }
    }
  }
  for (const route of routes) {
    const fixture = launchHarness({ ...route, rows: [{ ...paidGrant, page_cap: 500 }] });
    const original = await fixture.submit();
    assert.equal(original.status, 200);
    fixture.settings.SCAN_DISPATCH_GATEWAY_URL = "";
    const replay = await fixture.submit();
    assert.equal(replay.status, 200);
    assert.equal(replay.body.scan_id, original.body.scan_id);
    assert.equal(replay.body.replayed, true);
    assert.deepEqual(fixture.calls, ["claim", "create", "bind", "status"]);
    assert.equal(fixture.taskTransports.length, 2);
  }
});

test("staged task transport independently prevents direct Cloud Tasks fallback", async t => {
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
  const ownerPayload = { pipeline_mode: "staged", scan_mode: "standard_150", page_cap: 150 };
  const attempts = [
    () => enqueueScanJob({ ...args, payload }),
    () => enqueueScanDrain({ ...args, payload: {}, requireGateway: true }),
    () => enqueueScanJob({ ...args, payload: ownerPayload }),
    () => enqueueScanDrain({ ...args, payload: ownerPayload }),
  ];
  for (const run of attempts) assert.equal((await run()).failureCode, "dispatch_gateway_not_configured");
  assert.deepEqual(requests, []);
  assert.ok(observedEnv.every(name => name === "SCAN_DISPATCH_GATEWAY_URL"));
  gateway = "https://dispatch-gateway.example/";
  for (const run of attempts) assert.equal((await run()).failureCode, "dispatch_gateway_invalid_scan_mode");
  assert.equal(requests.length, attempts.length);
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

function namedPilot(options = {}) {
  return launchHarness({
    rollout: "off", entitled500: "false", cohort: paidCustomer.id,
    publicPilotExpiresAt: String(Math.floor(Date.now() / 1000) + 3600),
    ...options,
  });
}

test("published scan options attest the ordinary owner's 150 or 500 cap without writing any rows", async () => {
  for (const cap of [150, 500]) {
    const fixture = namedPilot({ rows: [{ ...paidGrant, page_cap: cap }] });
    const result = await fixture.options();
    assert.equal(result.status, 200);
    assert.equal(result.cacheControl, "no-store");
    assert.deepEqual(result.body, {
      success: true, version: "published_scan_options_v1", launch: "pilot", page_cap: cap,
      release_fingerprint: releaseContract.RELEASE_FINGERPRINT,
    });
    assert.deepEqual(fixture.calls, []);
  }
});

test("an old or unlisted client cannot use the pilot launcher to create a scan", async () => {
  const unlisted = namedPilot({ cohort: "other_customer" });
  const options = await unlisted.options();
  assert.equal(options.body.launch, "legacy");
  assert.equal(options.body.page_cap, 150);
  for (const fixture of [unlisted, namedPilot({ publicPilotExpiresAt: "0" }), namedPilot()]) {
    const result = await fixture.submit();
    assert.equal(result.status, 409);
    assert.deepEqual(fixture.calls, []);
    assert.deepEqual(fixture.scans, []);
  }
});

test("active named customer launches at the confirmed cap, and expiry or forged cap prevents new writes", async () => {
  for (const cap of [150, 500]) {
    const fixture = namedPilot({ rows: [{ ...paidGrant, page_cap: cap }] });
    const mismatch = await fixture.submit({ published_pilot_page_cap: cap === 150 ? 500 : 150 });
    assert.equal(mismatch.status, 409);
    assert.equal(mismatch.body.failure_code, "scan_limit_changed");
    assert.deepEqual(fixture.calls, []);
    const accepted = await fixture.submit({ published_pilot_page_cap: cap });
    assert.equal(accepted.body.accepted, true);
    assert.equal(accepted.body.page_cap, cap);
    assert.equal(fixture.scans[0].pipeline_mode, "staged");
    assert.equal(fixture.dispatched[0].page_cap, cap);
    assert.deepEqual(fixture.claimRequests, [{
      pilotLauncherBuildId: FUNCTION_BUILD_ID, pilotPageCap: cap === 150 ? 150 : undefined,
    }]);
  }
  const stale = namedPilot();
  assert.equal((await stale.options()).body.launch, "pilot");
  stale.settings.SCAN_PUBLIC_PILOT_EXPIRES_AT = "0";
  assert.notEqual((await stale.submit({ published_pilot_page_cap: 150 })).body.accepted, true);
  assert.deepEqual(stale.claimRequests, [{ pilotLauncherBuildId: FUNCTION_BUILD_ID, pilotPageCap: 150, pilotReplayOnly: true }]);
  assert.deepEqual(stale.scans, []);
  const freshPreview = namedPilot({ rows: [], publicPilotExpiresAt: "0" });
  assert.notEqual((await freshPreview.submit({ published_pilot_page_cap: 150 })).body.accepted, true);
  assert.deepEqual(freshPreview.calls, ["claim"]);
  assert.deepEqual(freshPreview.scans, []);
  const legacyRow = namedPilot();
  assert.equal((await legacyRow.submit({ published_pilot_page_cap: 150, scan_id: "legacy_01" })).status, 409);
  assert.deepEqual(legacyRow.calls, []);
});

test("a held named 150 launch can recover the same bound request interrupted before enqueue", async () => {
  const fixture = namedPilot({ interruptBeforeDrain: true });
  const original = await fixture.submit({ published_pilot_page_cap: 150 });
  assert.equal(original.status, 500);
  assert.deepEqual(fixture.calls, ["claim", "create", "bind"]);
  assert.deepEqual(fixture.dispatched, []);
  fixture.settings.SCAN_PUBLIC_PILOT_EXPIRES_AT = "0";
  assert.equal((await fixture.options()).body.launch, "paused");
  const replay = await fixture.submit({ published_pilot_page_cap: 150 });
  assert.equal(replay.body.accepted, true);
  assert.equal(replay.body.replayed, true);
  assert.equal(replay.body.scan_id, fixture.scans[0].id);
  assert.equal(fixture.scans.length, 1);
  assert.equal(fixture.dispatched[0].attempt_count, 1);
  assert.deepEqual(fixture.claimRequests.at(-1),
    { pilotLauncherBuildId: FUNCTION_BUILD_ID, pilotPageCap: 150, pilotReplayOnly: true });
});

test("a coordinator must confirm the current build and typed 150 pilot cap", async () => {
  for (const overrides of [{ acknowledgePilot: false }, { acknowledgeCap: false }, { pilotClaimCap: "150" }, { pilotClaimCap: 500 }]) {
    const fixture = namedPilot(overrides);
    const result = await fixture.submit({ published_pilot_page_cap: 150 });
    assert.equal(result.status, 503);
    assert.equal(result.body.failure_code, "admission_claim_evidence_invalid");
    assert.deepEqual(fixture.calls, ["claim"]);
    assert.deepEqual(fixture.scans, []);
    assert.deepEqual(fixture.dispatched, []);
  }
});

test("the authenticated operator can read the exact pilot expiry or verify a hold", async () => {
  const expiry = String(Math.floor(Date.now() / 1000) + 1800);
  for (const value of [expiry, "0"]) {
    const response = await harness({ settings: { ...staged, SCAN_PUBLIC_PILOT_EXPIRES_AT: value } }).post();
    assert.equal(response.body.public_pilot_expires_at, Number(value));
  }
  const paid = launchHarness({ publicPilotExpiresAt: "0" });
  assert.equal((await paid.submit()).body.accepted, true);
});


function paidNamedPilot(options = {}) {
  return launchHarness({
    rollout: "paid", entitled500: "false", pilotOwners: paidCustomer.id,
    publicPilotExpiresAt: String(Math.floor(Date.now() / 1000) + 3600),
    rows: [{ ...paidGrant, page_cap: 500 }], ...options,
  });
}

test("a named paid 500 pilot and public paid 150 share the canonical staged dispatch contract", async () => {
  const pilot = paidNamedPilot();
  assert.equal((await pilot.options()).body.launch, "pilot");
  assert.equal((await pilot.options()).body.page_cap, 500);
  assert.deepEqual(pilot.calls, []);
  const accepted = await pilot.submit({ published_pilot_page_cap: 500 });
  assert.equal(accepted.status, 200, JSON.stringify(accepted.body));
  assert.equal(accepted.body.page_cap, 500);
  assert.deepEqual(pilot.claimRequests, [{ pilotLauncherBuildId: FUNCTION_BUILD_ID, pilotPageCap: 500 }]);
  assert.equal(pilot.scans[0].admission_mode, "acceptance_only");
  for (const row of [pilot.scans[0], pilot.dispatched[0]]) {
    assert.equal(row.page_cap, 500);
    assert.equal(row.pipeline_mode, "staged");
    assert.equal(row.staged_rollout_scope, "paid");
  }
  const normal = paidNamedPilot({ pilotOwners: "other_customer", rows: [{ ...paidGrant, page_cap: 150 }] });
  assert.equal((await normal.options()).body.page_cap, 150);
  assert.equal((await normal.options()).body.launch, "legacy");
  assert.equal((await normal.submit()).body.accepted, true);
  assert.equal(normal.scans[0].admission_mode, "open");
  assert.equal(normal.dispatched[0].staged_rollout_scope, "paid");
  assert.equal(normal.dispatched[0].pipeline_mode, "staged");
  assert.equal(normal.dispatched[0].page_cap, 150);
  assert.notEqual(normal.scans[0].request_fingerprint, pilot.scans[0].request_fingerprint);
  assert.deepEqual(normal.claimRequests, [
    { pilotLauncherBuildId: undefined, pilotPageCap: undefined, standard150LauncherBuildId: FUNCTION_BUILD_ID },
  ]);
});

test("paid pilot permission requires an ordinary named customer, an active verified 500 grant and exact browser marker", async () => {
  for (const overrides of [
    { pilotOwners: "other_customer" },
    { user: { ...paidCustomer, role: "admin" } },
    { rows: [{ ...paidGrant, page_cap: 150 }] },
    { rows: [{ ...paidGrant, page_cap: 500, access_status: "revoked" }] },
    { rows: [{ ...paidGrant, page_cap: 500, stripe_checkout_session_id: "" }] },
  ]) {
    const fixture = paidNamedPilot(overrides);
    const result = await fixture.submit({ published_pilot_page_cap: 500 });
    assert.equal(result.body.accepted, false, JSON.stringify(result.body));
    assert.deepEqual(fixture.scans, []);
    assert.deepEqual(fixture.dispatched, []);
    assert.equal(fixture.calls.includes("claim"), false);
  }
  for (const marker of [undefined, 150, "500", 501]) {
    const fixture = paidNamedPilot();
    const result = await fixture.submit(marker === undefined ? {} : { published_pilot_page_cap: marker });
    assert.notEqual(result.body.accepted, true);
    assert.deepEqual(fixture.scans, []);
    assert.equal(fixture.calls.includes("claim"), false);
  }
  const manual = paidNamedPilot({ rows: [{ ...paidGrant, page_cap: 500, grant_source: "manual_grant", granted_at: paidGrant.paid_at }] });
  assert.equal((await manual.submit({ published_pilot_page_cap: 500 })).body.accepted, true);
});

test("named 150 customers retain their existing staged paid path and never see an elevated option", async () => {
  for (const expiry of ["0", String(Math.floor(Date.now() / 1000) + 3600)]) {
    const fixture = paidNamedPilot({ rows: [{ ...paidGrant, page_cap: 150 }], publicPilotExpiresAt: expiry });
    assert.equal((await fixture.options()).body.launch, "legacy");
    assert.equal((await fixture.options()).body.page_cap, 150);
    assert.equal((await fixture.submit()).body.accepted, true);
    assert.equal(fixture.dispatched[0].staged_rollout_scope, "paid");
    assert.deepEqual(fixture.claimRequests, [
      { pilotLauncherBuildId: undefined, pilotPageCap: undefined, standard150LauncherBuildId: FUNCTION_BUILD_ID },
    ]);
  }
});

test("broad entitled 500 cannot pass an ordinary Standard 150 launcher attestation", async () => {
  const fixture = launchHarness({ rows: [{ ...paidGrant, page_cap: 500 }] });
  const result = await fixture.submit({ standard_150_launcher_build_id: FUNCTION_BUILD_ID });
  assert.equal(result.body.accepted, true, JSON.stringify(result.body));
  assert.equal(result.body.page_cap, 500);
  assert.deepEqual(fixture.claimRequests, [{
    pilotLauncherBuildId: undefined, pilotPageCap: undefined, standard500LauncherBuildId: FUNCTION_BUILD_ID,
  }]);
});

test("an administrator's 150 launch carries no ordinary Standard 150 attestation", async () => {
  const fixture = launchHarness({ user: { ...paidCustomer, role: "admin" } });
  const result = await fixture.submit();
  assert.equal(result.body.accepted, true, JSON.stringify(result.body));
  assert.equal(result.body.page_cap, 150);
  assert.deepEqual(fixture.claimRequests, [{ pilotLauncherBuildId: undefined, pilotPageCap: undefined }]);
});

test("a paid pilot claim must echo the exact cap and launcher build with signed acceptance-only evidence", async () => {
  for (const overrides of [
    { pilotClaimCap: 150 }, { pilotClaimCap: "500" }, { pilotClaimCap: false },
    { acknowledgePilot: false }, { acknowledgeCap: false }, { claimMode: "open" }, { invalidClaimProof: true },
  ]) {
    const fixture = paidNamedPilot(overrides);
    const result = await fixture.submit({ published_pilot_page_cap: 500 });
    assert.equal(result.status, 503, JSON.stringify(result.body));
    assert.equal(result.body.failure_code, "admission_claim_evidence_invalid");
    assert.deepEqual(fixture.calls, ["claim"]);
    assert.deepEqual(fixture.scans, []);
    assert.deepEqual(fixture.dispatched, []);
  }
  const exclusive = namedPilot();
  assert.equal((await exclusive.submit({ published_pilot_page_cap: 150 })).body.accepted, true);
  assert.deepEqual(exclusive.claimRequests, [{ pilotLauncherBuildId: FUNCTION_BUILD_ID, pilotPageCap: 150 }]);
});

test("a paid pilot expiry hold keeps public 150 open and only replays previously admitted 500 requests", async () => {
  const fixture = paidNamedPilot();
  const original = await fixture.submit({ published_pilot_page_cap: 500 });
  assert.equal(original.body.accepted, true);
  fixture.gates.SCAN_PUBLIC_PILOT_EXPIRES_AT = "0";
  assert.notEqual(fixture.settings.SCAN_PUBLIC_PILOT_EXPIRES_AT, "0");
  assert.equal((await fixture.options()).body.launch, "paused");
  const replay = await fixture.submit({ published_pilot_page_cap: 500 });
  assert.equal(replay.body.scan_id, original.body.scan_id);
  assert.equal(replay.body.replayed, true, JSON.stringify(replay.body));
  const fresh = await fixture.submit({ request_id: "paid_request_02", published_pilot_page_cap: 500 });
  assert.notEqual(fresh.body.accepted, true);
  assert.equal(fixture.scans.length, 1);
  assert.deepEqual(new Set(fixture.dispatched.map(row => `${row.scan_id}:${row.attempt_count}`)),
    new Set([`${original.body.scan_id}:1`]));
  assert.deepEqual(fixture.claimRequests, [
    { pilotLauncherBuildId: FUNCTION_BUILD_ID, pilotPageCap: 500 },
    ...Array.from({ length: 2 }, () => ({ pilotLauncherBuildId: FUNCTION_BUILD_ID, pilotPageCap: 500, pilotReplayOnly: true })),
  ]);
  const normal = paidNamedPilot({ pilotOwners: "other_customer", publicPilotExpiresAt: "0", rows: [{ ...paidGrant, page_cap: 150 }] });
  assert.equal((await normal.submit()).body.accepted, true);
  assert.equal(normal.dispatched[0].staged_rollout_scope, "paid");
});

test("a paid pilot interruption after binding and before enqueue recovers the original attempt after hold", async () => {
  const fixture = paidNamedPilot({ interruptBeforeDrain: true });
  const original = await fixture.submit({ published_pilot_page_cap: 500 });
  assert.equal(original.status, 500);
  assert.deepEqual(fixture.calls, ["claim", "create", "bind"]);
  assert.deepEqual(fixture.taskTransports, []);
  fixture.gates.SCAN_PUBLIC_PILOT_EXPIRES_AT = "0";
  const replay = await fixture.submit({ published_pilot_page_cap: 500 });
  assert.equal(replay.body.accepted, true, JSON.stringify(replay.body));
  assert.equal(replay.body.replayed, true);
  assert.equal(replay.body.scan_id, fixture.scans[0].id);
  assert.equal(fixture.scans.length, 1);
  assert.deepEqual(fixture.calls, ["claim", "create", "bind", "claim"]);
  assert.deepEqual(fixture.taskTransports, [{ stage: "drain", requireGateway: true }, { stage: "entry", requireGateway: true }]);
  assert.equal(fixture.dispatched[0].attempt_count, 1);
});

test("malformed or conflicting paid pilot lists stop 500 without interrupting paid 150", async () => {
  for (const overrides of [
    { pilotOwners: "*" }, { pilotOwners: "short" }, { pilotOwners: " user_123" },
    { pilotOwners: "user_123," }, { pilotOwners: "user_123,user_123" },
    { pilotOwners: "user_001,user_002,user_003,user_004,user_005,user_006" },
    { entitled500: "true" },
  ]) {
    const fixture = paidNamedPilot(overrides);
    const result = await fixture.submit({ published_pilot_page_cap: 500 });
    assert.equal(result.body.failure_code, "scan_pilot_unavailable", JSON.stringify(overrides));
    assert.notEqual((await fixture.submit()).body.accepted, true);
    assert.deepEqual(fixture.calls, ["status"]);
    assert.deepEqual(fixture.scans, []);
    const standard = paidNamedPilot({ ...overrides, rows: [{ ...paidGrant, page_cap: 150 }] });
    assert.equal((await standard.options()).body.page_cap, 150);
    assert.equal((await standard.submit()).body.accepted, true);
    assert.equal(standard.dispatched[0].staged_rollout_scope, "paid");
    assert.equal(standard.dispatched[0].page_cap, 150);
  }
  const invalidPaidCohort = paidNamedPilot({ cohort: "other_customer" });
  assert.equal((await invalidPaidCohort.submit()).body.failure_code, "scan_staged_rollout_configuration_invalid");
  assert.deepEqual(invalidPaidCohort.calls, []);
  const oldCohort = paidNamedPilot();
  oldCohort.settings.SCAN_PIPELINE_OWNER_IDS = "other_customer";
  assert.equal((await oldCohort.submit()).body.failure_code, "scan_staged_rollout_configuration_invalid");
  assert.deepEqual(oldCohort.calls, []);
});

test("the real signed claim transport carries only the supplied bounded pilot cap", async () => {
  const calls = [];
  const env = name => ({ BETA_SCAN_ADMISSION_ENABLED: "true", SCAN_ADMISSION_COORDINATOR_URL: "https://coordinator.example", SCAN_EVIDENCE_SIGNING_KEY: "test-key" })[name];
  for (const cap of [150, 500]) {
    await admissionClient.claimAdmission({ ownerUserId: paidCustomer.id, requestId: "request_01", requestFingerprint: "f".repeat(64),
      pilotLauncherBuildId: FUNCTION_BUILD_ID, pilotPageCap: cap, env, fetchImpl: async (_url, options) => {
        calls.push(JSON.parse(options.body)); return Response.json({ ok: true });
      } });
    assert.equal(calls.at(-1).pilot_launcher_build_id, FUNCTION_BUILD_ID);
    assert.equal(calls.at(-1).pilot_page_cap, cap);
  }
});

test("paid pilot runtime readback attests a sorted bounded cohort without disclosing account IDs", async () => {
  const base = { SCAN_PIPELINE_MODE: "staged", SCAN_STAGED_ROLLOUT_SCOPE: "paid", SCAN_PUBLIC_PILOT_EXPIRES_AT: "0" };
  for (const cohort of [undefined, "", "pilot_user_b,pilot_user_a", "bad,", "duplicate_user,duplicate_user"]) {
    const settings = { ...base, SCAN_STAGED_PILOT_OWNER_IDS: "stale_pilot", SCAN_PUBLIC_PILOT_EXPIRES_AT: "1900000000" };
    const gates = { SCAN_STAGED_PILOT_OWNER_IDS: cohort, SCAN_PUBLIC_PILOT_EXPIRES_AT: "0" };
    const result = await harness({ settings, gates }).post();
    assert.equal(result.status, 200);
    assert.equal(result.body.public_pilot_expires_at, 0);
    const valid = cohort !== "bad," && cohort !== "duplicate_user,duplicate_user";
    const ids = cohort ? cohort.split(",").sort() : [];
    assert.equal(result.body.staged_pilot_owner_count, valid ? ids.length : null);
    assert.equal(result.body.staged_pilot_owner_cohort_sha256,
      valid ? createHash("sha256").update(JSON.stringify(ids)).digest("hex") : null);
    assert.equal(result.body.staged_rollout_scope, "paid");
    assert.doesNotMatch(JSON.stringify(result.body), /pilot_user|duplicate_user/);
  }
});
