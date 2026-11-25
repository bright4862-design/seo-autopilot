import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

import { persistExactAdmissionRelease } from "../../base44/functions/persistDurableScanAuthorityV9/admissionRelease.js";
import {
  admissionSignature, releaseAdmission as releaseFromAuthority,
} from "../../base44/functions/persistDurableScanAuthorityV9/admissionClient.js";
import { releaseAdmission as releaseFromReconciler } from "../../base44/functions/durableScanWorkerControlV9/admissionClient.js";
import { reconcileAdmissionReleaseCandidate } from "../../base44/functions/durableScanWorkerControlV9/reconciliation.js";
import * as limitedReleaseContract from "../../base44/functions/persistLimitedScanResultV9/generatedReleaseContract.js";

const coordinator = "https://coordinator.example.test";
const signingKey = "test target cooldown release key";
const observation = {
  target_origin: "https://fixture.example:443", status_code: 429,
  observed_at: 1_790_000_000, retry_after_seconds: 3_600,
};
const env = name => ({
  BETA_SCAN_ADMISSION_ENABLED: "true",
  SCAN_ADMISSION_COORDINATOR_URL: coordinator,
  SCAN_EVIDENCE_SIGNING_KEY: signingKey,
})[name];

function terminalScan(status, cap) {
  return {
    id: "scan_123456", owner_user_id: "owner_1234", request_id: "request_1234",
    idempotency_key: "request_1234", attempt_count: 2, page_cap: cap,
    admission_access_id: "access_1234", admission_barrier_generation: 4,
    admission_claim_sequence: 23, status, admission_release_state: "pending",
    crawl_timing: {
      target_cooldown_publication: { state: "unconfirmed", reason: "publication_unavailable", observation },
    },
  };
}

function scanStore(initial) {
  let scan = structuredClone(initial);
  return {
    async get(id) { assert.equal(id, initial.id); return structuredClone(scan); },
    async update(id, fields) {
      assert.equal(id, initial.id);
      scan = { ...scan, ...structuredClone(fields) };
    },
  };
}

function coordinatorFixture(scan, cooldownOutcome) {
  const calls = [];
  return {
    calls,
    async fetchImpl(url, request) {
      calls.push(url);
      assert.equal(url, coordinator + "/release-with-target-cooldown");
      assert.equal(request.redirect, "error");
      assert.equal(request.headers["x-fixlist-signature"], await admissionSignature(
        signingKey, request.headers["x-fixlist-timestamp"], request.body,
      ));
      assert.deepEqual(JSON.parse(request.body), {
        owner_user_id: scan.owner_user_id,
        scan_id: scan.id,
        terminal_status: scan.status,
        target_cooldown: {
          request_id: scan.request_id, barrier_generation: 4, claim_sequence: 23, observation,
        },
      });
      return Response.json({
        success: true, outcome: "released", scan_id: scan.id,
        request_id: scan.request_id, barrier_generation: 4, claim_sequence: 23,
        ...(cooldownOutcome ? { target_cooldown_outcome: cooldownOutcome } : {}),
      });
    },
  };
}

test("complete and limited persistence hand off the exact cooldown before confirming release", async () => {
  for (const [status, cap] of [["complete", 150], ["limited", 500]]) {
    const scan = terminalScan(status, cap);
    const scans = scanStore(scan);
    const fixture = coordinatorFixture(scan, "recorded");
    const entities = { ScanRun: scans };
    const result = status === "complete"
      ? await persistExactAdmissionRelease({
        entities, scan,
        release: options => releaseFromAuthority({ ...options, env, fetchImpl: fixture.fetchImpl }),
      })
      : await loadLimitedRelease(fixture.fetchImpl)(entities, scan);
    assert.equal(result.ok, true);
    assert.equal(fixture.calls.length, 1);
    const saved = await scans.get(scan.id);
    assert.equal(saved.admission_release_state, "released");
    assert.deepEqual(saved.crawl_timing, scan.crawl_timing);
  }
});

test("a success response without a cooldown receipt leaves the report and release pending", async () => {
  const scan = terminalScan("complete", 500);
  const scans = scanStore(scan);
  const fixture = coordinatorFixture(scan, undefined);
  const result = await persistExactAdmissionRelease({
    entities: { ScanRun: scans }, scan,
    release: options => releaseFromAuthority({ ...options, env, fetchImpl: fixture.fetchImpl }),
  });
  assert.equal(result.ok, false);
  const saved = await scans.get(scan.id);
  assert.equal(saved.status, "complete");
  assert.equal(saved.admission_release_state, "pending");
  assert.deepEqual(saved.crawl_timing, scan.crawl_timing);
});

test("reconciliation replays the cooldown handoff for an already released exact claim", async () => {
  const scan = terminalScan("limited", 150);
  const scans = scanStore(scan);
  const fixture = coordinatorFixture(scan, "unchanged");
  const result = await reconcileAdmissionReleaseCandidate({
    entities: scans, scan,
    statusAdmission: async () => ({
      ok: true, admission: {
        state: "released", scan_id: scan.id, request_id: scan.request_id,
        barrier_generation: 4, claim_sequence: 23,
      },
    }),
    releaseAdmission: options => releaseFromReconciler({ ...options, env, fetchImpl: fixture.fetchImpl }),
  });
  assert.equal(result.ok, true);
  assert.equal(fixture.calls.length, 1);
  assert.equal((await scans.get(scan.id)).admission_release_state, "released");
});

function loadLimitedRelease(fetchImpl) {
  const source = readFileSync(new URL(
    "../../base44/functions/persistLimitedScanResultV9/entry.ts", import.meta.url,
  ), "utf8");
  const compiled = ts.transpileModule(source + "\nexport { persistLimitedAdmissionRelease };", {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const exports = {};
  new Function("exports", "require", "Deno", "fetch", compiled)(exports, name => ({
    "base44:runtime": { secrets: { get: env } },
    "./generatedReleaseContract.js": limitedReleaseContract,
  })[name] || {}, { serve() {} }, fetchImpl);
  return exports.persistLimitedAdmissionRelease;
}
