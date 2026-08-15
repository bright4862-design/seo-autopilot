import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

import { normalizeAttemptCount } from "../../base44/functions/startStandardScanJob/cloudTasks.js";
import { evaluatePaidAccess, uniqueAccessRows } from "../../base44/functions/startStandardScanJob/entitlement.js";
import { betaScanAdmissionPolicy, normalizeAdmissionIdentity, scanIsTerminal } from "../../base44/functions/startStandardScanJob/admission.js";

const entrySource = readFileSync("base44/functions/startStandardScanJob/entry.ts", "utf8");

function matches(record, query) {
  for (const [field, expected] of Object.entries(query || {})) {
    if (record?.[field] !== expected) return false;
  }
  return true;
}

async function importHandler(harnessName) {
  const javascript = ts.transpileModule(entrySource, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  }).outputText.replace(/^import[\s\S]*?;\s*$/gm, "");
  const prelude = `const {
    createClientFromRequest,
    DRAIN_DELAY_SECONDS,
    enqueueScanDrain,
    enqueueScanJob,
    normalizeAttemptCount,
    evaluatePaidAccess,
    uniqueAccessRows,
    betaScanAdmissionPolicy,
    normalizeAdmissionIdentity,
    scanIsTerminal,
    claimAdmission,
    bindAdmission,
    releaseAdmission,
  } = globalThis.${harnessName};`;
  return import(`data:text/javascript;base64,${Buffer.from(`${prelude}\n${javascript}`).toString("base64")}`);
}

function createHarness({ failScanEnqueue = false, createCommitsThenThrows = false } = {}) {
  const access = {
    id: "access-1",
    owner_user_id: "user-1",
    user_email: "paid@example.com",
    access_status: "active",
    has_full_access: true,
    plan_id: "standard150_lifetime",
    grant_source: "stripe_checkout",
    app_id: "6a498732ec779dfaaeab0e53",
    paid_at: "2026-08-14T12:00:00.000Z",
    stripe_checkout_session_id: "cs_paid_1",
  };
  const scans = [];
  const scanTasks = new Set();
  const drainTasks = new Set();
  const releases = [];
  let admission = null;
  let createThrowSpent = false;

  const Access = {
    async filter(query) {
      return matches(access, query) ? [{ ...access }] : [];
    },
  };
  const ScanRun = {
    async filter(query) {
      return scans.filter((scan) => matches(scan, query)).map((scan) => ({ ...scan }));
    },
    async create(fields) {
      const row = { id: `scan-${scans.length + 1}`, ...fields };
      scans.push(row);
      // Simulate Base44 committing the row but losing the create response.
      if (createCommitsThenThrows && !createThrowSpent) {
        createThrowSpent = true;
        throw new Error("lost create response");
      }
      // Yield once so an exact concurrent replay can observe the unbound claim.
      await Promise.resolve();
      return { ...row };
    },
    async update(id, fields) {
      const index = scans.findIndex((scan) => scan.id === id);
      assert.notEqual(index, -1);
      scans[index] = { ...scans[index], ...fields };
      return { ...scans[index] };
    },
    async get(id) {
      const row = scans.find((scan) => scan.id === id);
      return row ? { ...row } : null;
    },
  };
  const BusinessProject = {
    async get(id) {
      return id === "project-1"
        ? { id, owner_user_id: "user-1", website_url: "https://example.com/" }
        : null;
    },
  };
  const base44 = {
    auth: { me: async () => ({ id: "user-1", email: "paid@example.com" }) },
    asServiceRole: { entities: { Access, ScanRun, BusinessProject } },
  };

  async function claimAdmission({ ownerUserId, requestId, requestFingerprint }) {
    if (!admission || admission.state === "released") {
      admission = {
        owner_user_id: ownerUserId,
        request_id: requestId,
        request_fingerprint: requestFingerprint,
        claim_token: "claim-token",
        scan_id: "",
        state: "claimed",
      };
      return { ok: true, outcome: "claimed", claim_token: admission.claim_token, scan_id: "" };
    }
    if (admission.request_id === requestId) {
      if (admission.request_fingerprint !== requestFingerprint) {
        return { ok: false, failureCode: "request_conflict", outcomeUnknown: false };
      }
      return {
        ok: true,
        outcome: "replayed",
        claim_token: admission.claim_token,
        scan_id: admission.scan_id,
      };
    }
    return { ok: false, failureCode: "admission_busy", retryAfterSeconds: 30, outcomeUnknown: false };
  }

  async function bindAdmission({ requestId, claimToken, scanId }) {
    if (!admission || admission.request_id !== requestId || admission.claim_token !== claimToken) {
      return { ok: false, failureCode: "invalid_claim_token", outcomeUnknown: false };
    }
    if (admission.scan_id && admission.scan_id !== scanId) {
      return { ok: false, failureCode: "scan_identity_conflict", outcomeUnknown: false };
    }
    const outcome = admission.scan_id ? "already_bound" : "bound";
    admission.scan_id = scanId;
    admission.state = "bound";
    return { ok: true, outcome, scan_id: scanId };
  }

  async function releaseAdmission({ scanId, terminalStatus }) {
    if (!admission || admission.scan_id !== scanId) {
      return { ok: false, failureCode: "scan_not_bound", outcomeUnknown: false };
    }
    const outcome = admission.state === "released" ? "already_released" : "released";
    admission.state = "released";
    releases.push({ scanId, terminalStatus });
    return { ok: true, outcome };
  }

  return {
    base44,
    scans,
    scanTasks,
    drainTasks,
    releases,
    admission: () => admission && { ...admission },
    globals: {
      createClientFromRequest: () => base44,
      DRAIN_DELAY_SECONDS: 900,
      enqueueScanDrain: async ({ scanId, attemptCount }) => {
        drainTasks.add(`${scanId}:${attemptCount}`);
        return { ok: true, taskName: `drain:${scanId}:${attemptCount}` };
      },
      enqueueScanJob: async ({ scanId, attemptCount }) => {
        if (failScanEnqueue) return { ok: false, failureCode: "tasks_http_403", outcomeUnknown: false };
        scanTasks.add(`${scanId}:${attemptCount}`);
        return { ok: true, taskName: `scan:${scanId}:${attemptCount}` };
      },
      normalizeAttemptCount,
      evaluatePaidAccess,
      uniqueAccessRows,
      betaScanAdmissionPolicy,
      normalizeAdmissionIdentity,
      scanIsTerminal,
      claimAdmission,
      bindAdmission,
      releaseAdmission,
    },
  };
}

function installEnv() {
  const priorDeno = globalThis.Deno;
  const env = new Map([
    ["BETA_SCAN_ADMISSION_ENABLED", "true"],
    ["BETA_COHORT_ALLOWED_USER_IDS", "user-1"],
    ["SCAN_ADMISSION_COORDINATOR_URL", "https://coordinator.example"],
    ["SCAN_EVIDENCE_SIGNING_KEY", "test-signing-root"],
    ["SCAN_TASKS_QUEUE_PATH", "projects/test/locations/europe-west1/queues/standard150"],
    ["SCAN_DRAIN_QUEUE_PATH", "projects/test/locations/europe-west1/queues/standard150-drain"],
    ["SCAN_WORKER_URL", "https://worker.example/scan-job"],
    ["TASKS_INVOKER_SERVICE_ACCOUNT", "invoker@test.iam.gserviceaccount.com"],
  ]);
  globalThis.Deno = { env: { get: (name) => env.get(name) } };
  return () => {
    if (priorDeno === undefined) delete globalThis.Deno;
    else globalThis.Deno = priorDeno;
  };
}

function invoke(handler, requestId = "scanreq_request_1", websiteUrl = "https://example.com/") {
  return handler(new Request("https://function.example", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      request_id: requestId,
      idempotency_key: requestId,
      project_id: "project-1",
      website_url: websiteUrl,
      submitted_url: websiteUrl,
      scan_mode: "standard_150",
    }),
  }));
}

test("two exact concurrent tabs share one canonical ScanRun and one deterministic task path", async () => {
  const restoreEnv = installEnv();
  const harness = createHarness();
  globalThis.__serverOwnedAdmissionHarness = harness.globals;
  try {
    const { default: handler } = await importHandler("__serverOwnedAdmissionHarness");
    const responses = await Promise.all([invoke(handler), invoke(handler)]);
    const bodies = await Promise.all(responses.map((response) => response.json()));

    assert.equal(harness.scans.length, 1);
    assert.equal(harness.scans[0].id, "scan-1");
    assert.equal(harness.scans[0].scan_id, "scan-1");
    assert.equal(harness.scans[0].owner_user_id, "user-1");
    assert.equal(harness.scans[0].admission_claim_token, undefined);
    assert.equal(harness.admission().scan_id, "scan-1");
    assert.equal(harness.scanTasks.size, 1);
    assert.equal(harness.drainTasks.size, 1);

    const accepted = bodies.filter((body) => body.accepted === true);
    assert.equal(accepted.length, 2);
    assert.ok(accepted.every((body) => body.scan_id === "scan-1" && body.scan_run_id === "scan-1"));
    assert.ok(accepted.some((body) => body.replayed === true));

    const replay = await invoke(handler);
    const replayBody = await replay.json();
    assert.equal(replay.status, 200);
    assert.equal(replayBody.accepted, true);
    assert.equal(replayBody.scan_id, "scan-1");
    assert.equal(replayBody.scan_run_id, "scan-1");
    assert.equal(replayBody.replayed, true);
    assert.equal(harness.scans.length, 1);
    assert.equal(harness.scanTasks.size, 1);

    const conflict = await invoke(handler, "scanreq_request_1", "https://example.com/other");
    assert.equal(conflict.status, 409);
    assert.equal((await conflict.json()).failure_code, "scan_request_identity_conflict");

    const competing = await invoke(handler, "scanreq_request_2");
    assert.equal(competing.status, 429);
    assert.equal((await competing.json()).failure_code, "scan_admission_busy");
  } finally {
    delete globalThis.__serverOwnedAdmissionHarness;
    restoreEnv();
  }
});

test("a lost Base44 create response recovers the committed entity and normalizes scan_id to entity.id", async () => {
  const restoreEnv = installEnv();
  const harness = createHarness({ createCommitsThenThrows: true });
  globalThis.__serverOwnedLostCreateHarness = harness.globals;
  try {
    const { default: handler } = await importHandler("__serverOwnedLostCreateHarness");
    const response = await invoke(handler, "scanreq_lost_create_1");
    const body = await response.json();
    assert.equal(response.status, 200);
    assert.equal(body.accepted, true);
    assert.equal(body.scan_id, "scan-1");
    assert.equal(harness.scans.length, 1);
    assert.equal(harness.scans[0].scan_id, "scan-1");
    assert.equal(harness.admission().scan_id, "scan-1");
  } finally {
    delete globalThis.__serverOwnedLostCreateHarness;
    restoreEnv();
  }
});

test("a definite dispatch failure terminalizes the exact server-owned run and releases admission", async () => {
  const restoreEnv = installEnv();
  const harness = createHarness({ failScanEnqueue: true });
  globalThis.__serverOwnedFailureHarness = harness.globals;
  try {
    const { default: handler } = await importHandler("__serverOwnedFailureHarness");
    const response = await invoke(handler, "scanreq_dispatch_fail_1");
    const body = await response.json();
    assert.equal(response.status, 503);
    assert.equal(body.accepted, false);
    assert.equal(harness.scans.length, 1);
    assert.equal(harness.scans[0].status, "failed");
    assert.equal(harness.scans[0].error_code, "tasks_http_403");
    assert.deepEqual(harness.releases, [{ scanId: "scan-1", terminalStatus: "failed" }]);
    assert.equal(harness.admission().state, "released");
  } finally {
    delete globalThis.__serverOwnedFailureHarness;
    restoreEnv();
  }
});

test("the production entry never persists the coordinator claim token or uses Access.updateMany admission", () => {
  assert.doesNotMatch(entrySource, /admission_claim_token|scan_claim_token|bindScanLease|claimScanLease/);
  assert.doesNotMatch(entrySource, /\.Access\.updateMany|Access\.updateMany/);
  assert.match(entrySource, /claimAdmission\(\{/);
  assert.match(entrySource, /bindAdmission\(\{/);
  assert.match(entrySource, /releaseAdmission\(\{/);
});
