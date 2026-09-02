import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

import { normalizeAttemptCount } from "../../base44/functions/startStandardScanJob/cloudTasks.js";
import { evaluatePaidAccess, uniqueAccessRows } from "../../base44/functions/startStandardScanJob/entitlement.js";
import { betaScanAdmissionPolicy, normalizeAdmissionIdentity, scanIsTerminal } from "../../base44/functions/startStandardScanJob/admission.js";
import {
  admissionClaimEvidenceProof,
  verifyAdmissionClaimEvidence,
} from "../../base44/functions/startStandardScanJob/admissionClient.js";
import { RELEASE_COMPONENT_VERSIONS, RELEASE_FINGERPRINT } from "../../base44/functions/startStandardScanJob/generatedReleaseContract.js";

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
    secrets,
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
    admissionClaimEvidenceProof,
    verifyAdmissionClaimEvidence,
    RELEASE_COMPONENT_VERSIONS,
    RELEASE_FINGERPRINT,
  } = globalThis.${harnessName};`;
  return import(`data:text/javascript;base64,${Buffer.from(`${prelude}\n${javascript}`).toString("base64")}`);
}

function createHarness({
  failScanEnqueue = false,
  createCommitsThenThrows = false,
  releaseFails = false,
  corruptCohortProof = false,
} = {}) {
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
  let intakeSecret = "true";
  let admissionSecret = "true";
  let coordinatorSecret = "https://coordinator.example";
  let signingSecret = "test-signing-root";
  let lastClaimEnv = null;
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

  async function claimAdmission({ ownerUserId, requestId, requestFingerprint, env }) {
    lastClaimEnv = {
      coordinator: String(env?.("SCAN_ADMISSION_COORDINATOR_URL") || ""),
      signing: String(env?.("SCAN_EVIDENCE_SIGNING_KEY") || ""),
    };
    if (!admission || admission.state === "released") {
      const cohortEvidence = {
        version: "admission_claim_evidence_v1",
        owner_user_id: ownerUserId,
        request_id: requestId,
        barrier_generation: 4,
        claim_sequence: 23,
        admission_mode: "open",
        acceptance_cohort_id: "",
        acceptance_release_id: "",
        acceptance_source_sha: "",
        acceptance_expires_at: null,
      };
      admission = {
        owner_user_id: ownerUserId,
        request_id: requestId,
        request_fingerprint: requestFingerprint,
        claim_token: "claim-token",
        scan_id: "",
        state: "claimed",
        barrier_generation: 4,
        claim_sequence: 23,
        admission_mode: "open",
        cohort_evidence: cohortEvidence,
        cohort_evidence_proof: "",
        cohort_evidence_proof_promise: admissionClaimEvidenceProof(cohortEvidence, lastClaimEnv.signing),
      };
      admission.cohort_evidence_proof = corruptCohortProof
        ? "0".repeat(64)
        : await admission.cohort_evidence_proof_promise;
      return {
        ok: true,
        outcome: "claimed",
        request_id: requestId,
        claim_token: admission.claim_token,
        scan_id: "",
        barrier_generation: 4,
        claim_sequence: 23,
        admission_mode: "open",
        cohort_evidence: { ...cohortEvidence },
        cohort_evidence_proof: admission.cohort_evidence_proof,
      };
    }
    if (admission.request_id === requestId) {
      if (admission.request_fingerprint !== requestFingerprint) {
        return { ok: false, failureCode: "request_conflict", outcomeUnknown: false };
      }
      if (!admission.cohort_evidence_proof) {
        admission.cohort_evidence_proof = corruptCohortProof
          ? "0".repeat(64)
          : await admission.cohort_evidence_proof_promise;
      }
      return {
        ok: true,
        outcome: "replayed",
        claim_token: admission.claim_token,
        scan_id: admission.scan_id,
        request_id: admission.request_id,
        barrier_generation: admission.barrier_generation,
        claim_sequence: admission.claim_sequence,
        admission_mode: admission.admission_mode,
        cohort_evidence: { ...admission.cohort_evidence },
        cohort_evidence_proof: admission.cohort_evidence_proof,
      };
    }
    return { ok: false, failureCode: "admission_busy", retryAfterSeconds: 30, outcomeUnknown: false };
  }

  async function bindAdmission({ requestId, claimToken, scanId, barrierGeneration }) {
    if (!admission || admission.request_id !== requestId || admission.claim_token !== claimToken) {
      return { ok: false, failureCode: "invalid_claim_token", outcomeUnknown: false };
    }
    if (admission.scan_id && admission.scan_id !== scanId) {
      return { ok: false, failureCode: "scan_identity_conflict", outcomeUnknown: false };
    }
    if (barrierGeneration !== admission.barrier_generation) {
      return { ok: false, failureCode: "barrier_generation_conflict", outcomeUnknown: false };
    }
    const outcome = admission.scan_id ? "already_bound" : "bound";
    admission.scan_id = scanId;
    admission.state = "bound";
    return {
      ok: true,
      outcome,
      request_id: requestId,
      scan_id: scanId,
      barrier_generation: admission.barrier_generation,
      claim_sequence: admission.claim_sequence,
    };
  }

  async function releaseAdmission({ scanId, terminalStatus }) {
    if (releaseFails) {
      return { ok: false, failureCode: "admission_unreachable", outcomeUnknown: true };
    }
    if (!admission || admission.scan_id !== scanId) {
      return { ok: false, failureCode: "scan_not_bound", outcomeUnknown: false };
    }
    const outcome = admission.state === "released" ? "already_released" : "released";
    admission.state = "released";
    releases.push({ scanId, terminalStatus });
    return {
      ok: true,
      outcome,
      request_id: admission.request_id,
      scan_id: scanId,
      barrier_generation: admission.barrier_generation,
      claim_sequence: admission.claim_sequence,
    };
  }

  return {
    base44,
    scans,
    scanTasks,
    drainTasks,
    releases,
    admission: () => admission && { ...admission },
    lastClaimEnv: () => lastClaimEnv && { ...lastClaimEnv },
    setIntakeSecret: (value) => { intakeSecret = String(value ?? ""); },
    setAdmissionSecret: (value) => { admissionSecret = String(value ?? ""); },
    setCoordinatorSecret: (value) => { coordinatorSecret = String(value ?? ""); },
    setSigningSecret: (value) => { signingSecret = String(value ?? ""); },
    globals: {
      createClientFromRequest: () => base44,
      secrets: {
        get: (name) => {
          if (name === "BETA_SCAN_INTAKE_ENABLED") return intakeSecret;
          if (name === "BETA_SCAN_ADMISSION_ENABLED") return admissionSecret;
          if (name === "SCAN_ADMISSION_COORDINATOR_URL") return coordinatorSecret;
          if (name === "SCAN_EVIDENCE_SIGNING_KEY") return signingSecret;
          return "";
        },
      },
      DRAIN_DELAY_SECONDS: 600,
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
      admissionClaimEvidenceProof,
      verifyAdmissionClaimEvidence,
      RELEASE_COMPONENT_VERSIONS,
      RELEASE_FINGERPRINT,
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

test("loaded handler observes mutable intake secret changes on the next request", async () => {
  const restoreEnv = installEnv();
  const harness = createHarness();
  harness.setIntakeSecret("false");
  globalThis.__runtimeIntakeHarness = harness.globals;
  try {
    const { default: handler } = await importHandler("__runtimeIntakeHarness");

    const paused = await invoke(handler, "scanreq_runtime_pause_1");
    const pausedBody = await paused.json();
    assert.equal(paused.status, 503);
    assert.equal(pausedBody.failure_code, "scan_intake_paused");
    assert.equal(harness.scans.length, 0);
    assert.equal(harness.scanTasks.size, 0);
    assert.equal(harness.drainTasks.size, 0);
    assert.equal(harness.admission(), null);

    harness.setIntakeSecret("true");
    const resumed = await invoke(handler, "scanreq_runtime_resume_1");
    const resumedBody = await resumed.json();
    assert.equal(resumed.status, 200);
    assert.equal(resumedBody.accepted, true);
    assert.equal(harness.scans.length, 1);
    assert.equal(harness.scanTasks.size, 1);
    assert.equal(harness.drainTasks.size, 1);
  } finally {
    restoreEnv();
    delete globalThis.__runtimeIntakeHarness;
  }
});

test("loaded handler observes mutable admission connectivity secret changes even when the Deno env snapshot is stale", async () => {
  const restoreEnv = installEnv();
  const priorGet = globalThis.Deno.env.get;
  globalThis.Deno.env.get = (name) => name === "BETA_SCAN_ADMISSION_ENABLED" ? "false" : priorGet(name);
  const harness = createHarness();
  harness.setAdmissionSecret("false");
  globalThis.__runtimeAdmissionHarness = harness.globals;
  try {
    const { default: handler } = await importHandler("__runtimeAdmissionHarness");

    const paused = await invoke(handler, "scanreq_admission_pause_1");
    const pausedBody = await paused.json();
    assert.equal(paused.status, 503);
    assert.equal(pausedBody.failure_code, "scan_admission_paused");
    assert.equal(harness.scans.length, 0);
    assert.equal(harness.scanTasks.size, 0);
    assert.equal(harness.drainTasks.size, 0);
    assert.equal(harness.admission(), null);

    harness.setAdmissionSecret("true");
    const resumed = await invoke(handler, "scanreq_admission_resume_1");
    const resumedBody = await resumed.json();
    assert.equal(resumed.status, 200);
    assert.equal(resumedBody.accepted, true);
    assert.equal(harness.scans.length, 1);
    assert.equal(harness.scanTasks.size, 1);
    assert.equal(harness.drainTasks.size, 1);
  } finally {
    globalThis.Deno.env.get = priorGet;
    delete globalThis.__runtimeAdmissionHarness;
    restoreEnv();
  }
});

test("loaded handler uses request-time coordinator and signing secrets when Deno.env is stale", async () => {
  const restoreEnv = installEnv();
  const priorGet = globalThis.Deno.env.get;
  globalThis.Deno.env.get = (name) => {
    if (name === "SCAN_ADMISSION_COORDINATOR_URL") return "https://stale-coordinator.example";
    if (name === "SCAN_EVIDENCE_SIGNING_KEY") return "stale-process-signing-root";
    return priorGet(name);
  };
  const harness = createHarness();
  harness.setCoordinatorSecret("https://runtime-coordinator.example");
  harness.setSigningSecret("runtime-signing-root");
  globalThis.__runtimeAdmissionConfigHarness = harness.globals;
  try {
    const { default: handler } = await importHandler("__runtimeAdmissionConfigHarness");
    const response = await invoke(handler, "scanreq_runtime_config_1");
    const body = await response.json();

    assert.equal(response.status, 200);
    assert.equal(body.accepted, true);
    assert.deepEqual(harness.lastClaimEnv(), {
      coordinator: "https://runtime-coordinator.example",
      signing: "runtime-signing-root",
    });
    assert.equal(harness.scans.length, 1);
    assert.equal(harness.scanTasks.size, 1);
    assert.equal(harness.drainTasks.size, 1);
  } finally {
    globalThis.Deno.env.get = priorGet;
    delete globalThis.__runtimeAdmissionConfigHarness;
    restoreEnv();
  }
});

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
    assert.equal(harness.scans[0].status, "queued");
    assert.equal(harness.scans[0].started_at, undefined);
    assert.equal(harness.scans[0].admission_claim_token, undefined);
    assert.equal(harness.scans[0].admission_release_state, "pending");
    assert.equal(harness.scans[0].admission_barrier_generation, 4);
    assert.equal(harness.scans[0].admission_claim_sequence, 23);
    assert.equal(harness.scans[0].admission_mode, "open");
    assert.equal(harness.scans[0].admission_cohort_evidence_version, "admission_claim_evidence_v1");
    assert.equal(harness.scans[0].admission_cohort_evidence_proof.length, 64);
    assert.match(harness.scans[0].admission_reconciliation_version, /^admission_reconciliation_v1_/);
    assert.equal(harness.admission().scan_id, "scan-1");
    assert.equal(harness.scanTasks.size, 1);
    assert.equal(harness.drainTasks.size, 1);

    const accepted = bodies.filter((body) => body.accepted === true);
    const pending = bodies.filter((body) => body.failure_code === "scan_admission_pending");
    // The exact replay may observe either side of the create/bind boundary. It
    // may return the canonical row immediately, or a truthful 202 while the
    // first caller finishes binding it. Neither outcome may create a second
    // row/task, and the next replay below must resolve to the canonical row.
    assert.ok(accepted.length === 1 || accepted.length === 2);
    assert.equal(accepted.length + pending.length, 2);
    assert.ok(accepted.every((body) => body.scan_id === "scan-1" && body.scan_run_id === "scan-1"));
    assert.ok(accepted.every((body) => body.status === "queued"));
    if (accepted.length === 2) assert.ok(accepted.some((body) => body.replayed === true));

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

test("an invalid coordinator cohort proof fails before durable creation", async () => {
  const restoreEnv = installEnv();
  const harness = createHarness({ corruptCohortProof: true });
  globalThis.__serverOwnedInvalidProofHarness = harness.globals;
  try {
    const { default: handler } = await importHandler("__serverOwnedInvalidProofHarness");
    const response = await invoke(handler, "scanreq_invalid_proof");
    const body = await response.json();
    assert.equal(response.status, 503);
    assert.equal(body.failure_code, "admission_claim_evidence_invalid");
    assert.equal(harness.scans.length, 0);
  } finally {
    delete globalThis.__serverOwnedInvalidProofHarness;
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
    assert.equal(harness.scans[0].admission_release_state, "released");
    assert.equal(harness.scans[0].admission_release_outcome, "released");
    assert.deepEqual(harness.releases, [{ scanId: "scan-1", terminalStatus: "failed" }]);
    assert.equal(harness.admission().state, "released");
  } finally {
    delete globalThis.__serverOwnedFailureHarness;
    restoreEnv();
  }
});

test("an uncertain dispatcher release remains durably pending for reconciliation", async () => {
  const restoreEnv = installEnv();
  const harness = createHarness({ failScanEnqueue: true, releaseFails: true });
  globalThis.__serverOwnedPendingReleaseHarness = harness.globals;
  try {
    const { default: handler } = await importHandler("__serverOwnedPendingReleaseHarness");
    const response = await invoke(handler, "scanreq_dispatch_release_pending");
    assert.equal(response.status, 503);
    assert.equal(harness.scans[0].status, "failed");
    assert.equal(harness.scans[0].admission_release_state, "pending");
    assert.equal(harness.scans[0].admission_release_failure_code, "admission_unreachable");
  } finally {
    delete globalThis.__serverOwnedPendingReleaseHarness;
    restoreEnv();
  }
});

test("intake pause refuses before coordinator claim or durable writes", async () => {
  const restoreEnv = installEnv();
  const harness = createHarness();
  harness.setIntakeSecret("false");
  let claims = 0;
  const originalClaim = harness.globals.claimAdmission;
  harness.globals.claimAdmission = async (...args) => {
    claims += 1;
    return originalClaim(...args);
  };
  globalThis.__serverOwnedPausedIntakeHarness = harness.globals;
  try {
    const { default: handler } = await importHandler("__serverOwnedPausedIntakeHarness");
    const response = await invoke(handler, "scanreq_paused_intake");
    const body = await response.json();
    assert.equal(response.status, 503);
    assert.equal(body.failure_code, "scan_intake_paused");
    assert.equal(claims, 0);
    assert.equal(harness.scans.length, 0);
    assert.equal(harness.scanTasks.size, 0);
    assert.equal(harness.drainTasks.size, 0);
  } finally {
    delete globalThis.__serverOwnedPausedIntakeHarness;
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

test("two different simultaneous requests from the same owner admit exactly one scan", async () => {
  const restoreEnv = installEnv();
  const harness = createHarness();
  globalThis.__serverOwnedCompetingHarness = harness.globals;
  try {
    const { default: handler } = await importHandler("__serverOwnedCompetingHarness");
    const responses = await Promise.all([
      invoke(handler, "scanreq_competing_a"),
      invoke(handler, "scanreq_competing_b"),
    ]);
    const bodies = await Promise.all(responses.map((response) => response.json()));
    const accepted = bodies.filter((body) => body.accepted === true);
    const refused = bodies.filter((body) => body.failure_code === "scan_admission_busy");

    assert.equal(harness.scans.length, 1, "same owner must never create two active ScanRuns");
    assert.equal(harness.scanTasks.size, 1, "same owner must never enqueue two scan tasks");
    assert.equal(harness.drainTasks.size, 1, "same owner must never enqueue two watchdogs");
    assert.equal(accepted.length, 1, "exactly one competing request may win admission");
    assert.equal(refused.length, 1, "the losing request must fail closed as admission busy");
  } finally {
    delete globalThis.__serverOwnedCompetingHarness;
    restoreEnv();
  }
});
