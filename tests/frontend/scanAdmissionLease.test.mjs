import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  MAX_BETA_CUSTOMERS,
  betaScanAdmissionPolicy,
  normalizeAdmissionIdentity,
} from "../../base44/functions/startStandardScanJob/admission.js";

const admissionSource = readFileSync("base44/functions/startStandardScanJob/admission.js", "utf8");
const entrySource = readFileSync("base44/functions/startStandardScanJob/entry.ts", "utf8");
const clientSource = readFileSync("base44/functions/startStandardScanJob/admissionClient.js", "utf8");

function withEnv(values, fn) {
  const priorDeno = globalThis.Deno;
  globalThis.Deno = { env: { get: (name) => values.get(name) } };
  try { return fn(); }
  finally {
    if (priorDeno === undefined) delete globalThis.Deno;
    else globalThis.Deno = priorDeno;
  }
}

test("scan admission is default-off and requires the coordinator, not an unproven Base44 atomic primitive", () => {
  const values = new Map();
  withEnv(values, () => {
    assert.equal(MAX_BETA_CUSTOMERS, 25);
    assert.equal(betaScanAdmissionPolicy().code, "scan_admission_paused");
    values.set("BETA_SCAN_ADMISSION_ENABLED", "true");
    values.set("BETA_COHORT_ALLOWED_USER_IDS", "user-1");
    assert.equal(betaScanAdmissionPolicy().code, "scan_admission_configuration_invalid");
    values.set("SCAN_ADMISSION_COORDINATOR_URL", "https://coordinator.example");
    values.set("SCAN_EVIDENCE_SIGNING_KEY", "test-root");
    assert.deepEqual(betaScanAdmissionPolicy(), { ok: true, code: "", allowedUserIds: ["user-1"] });
    values.set("BASE44_ATOMIC_UPDATE_MANY_CONFIRMED", "false");
    assert.deepEqual(betaScanAdmissionPolicy(), { ok: true, code: "", allowedUserIds: ["user-1"] });
  });
  assert.doesNotMatch(admissionSource, /BASE44_ATOMIC_UPDATE_MANY_CONFIRMED|updateMany|scan_claim_/);
  assert.doesNotMatch(entrySource, /bindScanLease|claimScanLease|scan_claim_token/);
  assert.match(entrySource, /claimAdmission\(\{/);
  assert.match(entrySource, /bindAdmission\(\{/);
});

test("cohort stays capped at 25 exact users", () => {
  const values = new Map([
    ["BETA_SCAN_ADMISSION_ENABLED", "true"],
    ["SCAN_ADMISSION_COORDINATOR_URL", "https://coordinator.example"],
    ["SCAN_EVIDENCE_SIGNING_KEY", "test-root"],
  ]);
  withEnv(values, () => {
    values.set("BETA_COHORT_ALLOWED_USER_IDS", Array.from({ length: 25 }, (_, i) => `user-${i + 1}`).join(","));
    assert.equal(betaScanAdmissionPolicy().ok, true);
    values.set("BETA_COHORT_ALLOWED_USER_IDS", Array.from({ length: 26 }, (_, i) => `user-${i + 1}`).join(","));
    assert.equal(betaScanAdmissionPolicy().code, "scan_admission_configuration_invalid");
  });
});

test("request identity is exact and bounded before coordinator admission", () => {
  const good = normalizeAdmissionIdentity({
    request_id: "scanreq_request_1",
    idempotency_key: "scanreq_request_1",
    request_fingerprint: `standard150:${"a".repeat(64)}`,
  });
  assert.equal(good.ok, true);
  assert.equal(normalizeAdmissionIdentity({ ...good, idempotency_key: "scanreq_other" }).code, "scan_request_identity_conflict");
  assert.equal(normalizeAdmissionIdentity({ request_id: "short", idempotency_key: "short", request_fingerprint: "fp" }).ok, false);
});

test("only a fresh coordinator claim may create; unbound exact replays recover or return pending", () => {
  const freshIndex = entrySource.indexOf('claim.outcome === "replayed" && !claimedScanId');
  const createIndex = entrySource.indexOf("recoverOrCreateServerScan({", freshIndex);
  assert.ok(freshIndex > -1);
  assert.ok(createIndex > freshIndex);
  const replayBlock = entrySource.slice(freshIndex, createIndex);
  assert.match(replayBlock, /recoverExistingServerScan\(\{/);
  assert.match(replayBlock, /code: "scan_admission_pending"/);
  assert.doesNotMatch(replayBlock, /\.create\(/);
  assert.match(clientSource, /return callCoordinator\("\/claim"/);
});
