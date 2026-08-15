import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

import {
  betaScanAdmissionPolicy,
  bindScanLease,
  claimScanLease,
  normalizeAdmissionIdentity,
  scanIsTerminal,
} from "../../base44/functions/startStandardScanJob/admission.js";
import { normalizeAttemptCount } from "../../base44/functions/startStandardScanJob/cloudTasks.js";
import {
  evaluatePaidAccess,
  uniqueAccessRows,
} from "../../base44/functions/startStandardScanJob/entitlement.js";

const entrySource = readFileSync("base44/functions/startStandardScanJob/entry.ts", "utf8");

function matches(record, query) {
  for (const [field, expected] of Object.entries(query || {})) {
    if (field === "$or") {
      if (!expected.some((candidate) => matches(record, candidate))) return false;
    } else if (expected && typeof expected === "object" && "$exists" in expected) {
      if (Object.hasOwn(record, field) !== expected.$exists) return false;
    } else if (record[field] !== expected) return false;
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
    bindAdmission,
    claimAdmission,
    releaseAdmission,
    normalizeScanIdentity,
  } = globalThis.${harnessName};`;
  return import(`data:text/javascript;base64,${Buffer.from(`${prelude}\n${javascript}`).toString("base64")}`);
}

test("the server creates and returns the canonical ScanRun while concurrent retries share one task path", async () => {
  const priorDeno = globalThis.Deno;
  const env = new Map([
    ["BETA_SCAN_ADMISSION_ENABLED", "true"],
    ["SCAN_ADMISSION_COORDINATOR_URL", "https://coordinator.example"],
    ["SCAN_EVIDENCE_SIGNING_KEY", "harness-signing-root"],
    ["BETA_COHORT_ALLOWED_USER_IDS", "user-1"],
    ["SCAN_TASKS_QUEUE_PATH", "projects/test/locations/europe-west1/queues/standard150"],
    ["SCAN_WORKER_URL", "https://worker.example/scan-job"],
    ["TASKS_INVOKER_SERVICE_ACCOUNT", "invoker@test.iam.gserviceaccount.com"],
  ]);
  globalThis.Deno = { env: { get: (name) => env.get(name) } };

  let access = {
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

  const Access = {
    async filter(query) {
      return matches(access, query) ? [{ ...access }] : [];
    },
    async get(id) {
      return id === access.id ? { ...access } : null;
    },
    async updateMany(query, update) {
      if (!matches(access, query)) return { success: true, updated: 0 };
      access = { ...access, ...(update?.$set || {}) };
      return { success: true, updated: 1 };
    },
  };
  const ScanRun = {
    async filter(query) {
      return scans.filter((scan) => matches(scan, query)).map((scan) => ({ ...scan }));
    },
    async create(fields) {
      const row = { id: `scan-${scans.length + 1}`, ...fields };
      scans.push(row);
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
  // Stands in for the Firestore admission coordinator. One document, and the
  // same rules the real transaction applies: a fresh claim wins, an identical
  // request replays onto it, a different request is busy, and a reused request
  // id carrying different work is a conflict.
  let admissionDoc = null;
  const coordinator = {
    async claim({ ownerUserId, requestId, requestFingerprint }) {
      if (!admissionDoc || admissionDoc.state === "released") {
        admissionDoc = {
          owner_user_id: ownerUserId,
          request_id: requestId,
          request_fingerprint: requestFingerprint,
          claim_token: `tok-${requestId}`,
          scan_id: "",
          state: "claimed",
        };
        return { ok: true, outcome: "claimed", claim_token: admissionDoc.claim_token, scan_id: "" };
      }
      if (admissionDoc.request_id !== requestId) {
        return { ok: false, failureCode: "admission_busy", retryAfterSeconds: 5, outcomeUnknown: false };
      }
      if (admissionDoc.request_fingerprint !== requestFingerprint) {
        return { ok: false, failureCode: "request_conflict", outcomeUnknown: false };
      }
      return {
        ok: true,
        outcome: "replayed",
        claim_token: admissionDoc.claim_token,
        scan_id: admissionDoc.scan_id,
      };
    },
    async bind({ requestId, claimToken, scanId }) {
      if (!admissionDoc || admissionDoc.request_id !== requestId) {
        return { ok: false, failureCode: "claim_not_found", outcomeUnknown: false };
      }
      if (admissionDoc.claim_token !== claimToken) {
        return { ok: false, failureCode: "invalid_claim_token", outcomeUnknown: false };
      }
      if (admissionDoc.scan_id === scanId) return { ok: true, outcome: "already_bound", scan_id: scanId };
      if (admissionDoc.scan_id) {
        return { ok: false, failureCode: "scan_identity_conflict", outcomeUnknown: false };
      }
      admissionDoc.scan_id = scanId;
      admissionDoc.state = "bound";
      return { ok: true, outcome: "bound", scan_id: scanId };
    },
    async release({ scanId, terminalStatus }) {
      if (!admissionDoc || admissionDoc.scan_id !== scanId) {
        return { ok: false, failureCode: "scan_identity_conflict", outcomeUnknown: false };
      }
      admissionDoc.state = "released";
      admissionDoc.terminal_status = terminalStatus;
      return { ok: true, outcome: "released" };
    },
    doc: () => admissionDoc,
  };

  globalThis.__serverOwnedAdmissionHarness = {
    claimAdmission: (args) => coordinator.claim(args),
    bindAdmission: (args) => coordinator.bind(args),
    releaseAdmission: (args) => coordinator.release(args),
    normalizeScanIdentity: (entity) => {
      const id = String(entity?.id || "").trim();
      return id
        ? { ok: true, failureCode: "", scanId: id, scanRun: { ...entity, scan_id: id } }
        : { ok: false, failureCode: "admission_scan_id_missing", scanId: "", scanRun: null };
    },
    createClientFromRequest: () => base44,
    DRAIN_DELAY_SECONDS: 900,
    enqueueScanDrain: async ({ scanId, attemptCount }) => {
      drainTasks.add(`${scanId}:${attemptCount}`);
      return { ok: true, taskName: `drain:${scanId}:${attemptCount}` };
    },
    enqueueScanJob: async ({ scanId, attemptCount }) => {
      scanTasks.add(`${scanId}:${attemptCount}`);
      return { ok: true, taskName: `scan:${scanId}:${attemptCount}` };
    },
    normalizeAttemptCount,
    evaluatePaidAccess,
    uniqueAccessRows,
    betaScanAdmissionPolicy,
    bindScanLease,
    claimScanLease,
    normalizeAdmissionIdentity,
    scanIsTerminal,
  };

  try {
    const { default: handler } = await importHandler("__serverOwnedAdmissionHarness");
    const invoke = (requestId = "scanreq_request_1", websiteUrl = "https://example.com/") => handler(new Request("https://function.example", {
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

    const firstPair = await Promise.all([invoke(), invoke()]);
    const firstBodies = await Promise.all(firstPair.map((response) => response.json()));
    assert.ok(firstPair.every((response) => [200, 202].includes(response.status)));
    assert.equal(scans.length, 1);
    assert.equal(scans[0].owner_user_id, "user-1");
    assert.equal(scans[0].scan_id, "scan-1");
    assert.equal(coordinator.doc().scan_id, "scan-1");
    assert.equal(coordinator.doc().state, "bound");

    const replay = await invoke();
    const replayBody = await replay.json();
    assert.equal(replay.status, 200);
    assert.equal(replayBody.accepted, true);
    assert.equal(replayBody.scan_id, "scan-1");
    assert.equal(replayBody.scan_run_id, "scan-1");
    assert.equal(replayBody.replayed, true);
    assert.equal(scans.length, 1);
    assert.equal(scanTasks.size, 1);
    assert.equal(drainTasks.size, 1);

    const conflictingReplay = await invoke("scanreq_request_1", "https://example.com/other");
    const conflictingReplayBody = await conflictingReplay.json();
    assert.equal(conflictingReplay.status, 409);
    assert.equal(conflictingReplayBody.failure_code, "scan_request_identity_conflict");
    assert.equal(scans.length, 1);

    const competing = await invoke("scanreq_request_2");
    const competingBody = await competing.json();
    assert.equal(competing.status, 429);
    assert.equal(competingBody.failure_code, "scan_admission_busy");
    assert.equal(scans.length, 1);

    const acceptedBodies = [...firstBodies, replayBody].filter((body) => body.accepted === true);
    assert.ok(acceptedBodies.every((body) => body.scan_id === "scan-1"));
  } finally {
    delete globalThis.__serverOwnedAdmissionHarness;
    if (priorDeno === undefined) delete globalThis.Deno;
    else globalThis.Deno = priorDeno;
  }
});
