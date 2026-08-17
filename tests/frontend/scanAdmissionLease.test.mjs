import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
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
    assert.equal(betaScanAdmissionPolicy().code, "scan_admission_paused");
    values.set("BETA_SCAN_ADMISSION_ENABLED", "true");
    assert.equal(betaScanAdmissionPolicy().code, "scan_admission_configuration_invalid");
    values.set("SCAN_ADMISSION_COORDINATOR_URL", "https://coordinator.example");
    values.set("SCAN_EVIDENCE_SIGNING_KEY", "test-root");
    assert.deepEqual(betaScanAdmissionPolicy(), { ok: true, code: "" });
    values.set("BASE44_ATOMIC_UPDATE_MANY_CONFIRMED", "false");
    assert.deepEqual(betaScanAdmissionPolicy(), { ok: true, code: "" });
  });
  assert.doesNotMatch(admissionSource, /BASE44_ATOMIC_UPDATE_MANY_CONFIRMED|updateMany|scan_claim_/);
  assert.doesNotMatch(entrySource, /bindScanLease|claimScanLease|scan_claim_token/);
  assert.match(entrySource, /claimAdmission\(\{/);
  assert.match(entrySource, /bindAdmission\(\{/);
});

test("no cohort allowlist gates scanning; entitlement is the invitation", () => {
  // The 25-entry BETA_COHORT_ALLOWED_USER_IDS list is gone. It duplicated a
  // decision entitlement already owns, and with 100+ members it would have to
  // be edited on every signup -- silently locking out anyone missing from it.
  const values = new Map([
    ["BETA_SCAN_ADMISSION_ENABLED", "true"],
    ["SCAN_ADMISSION_COORDINATOR_URL", "https://coordinator.example"],
    ["SCAN_EVIDENCE_SIGNING_KEY", "test-root"],
  ]);
  withEnv(values, () => {
    assert.equal(betaScanAdmissionPolicy().ok, true);
    // Setting the retired variable, at any size, changes nothing.
    for (const size of [0, 1, 26, 500]) {
      values.set("BETA_COHORT_ALLOWED_USER_IDS", Array.from({ length: size }, (_, i) => `user-${i + 1}`).join(","));
      assert.deepEqual(betaScanAdmissionPolicy(), { ok: true, code: "" }, `cohort size ${size} must not affect admission`);
    }
  });
  // The policy answers "is admission configured?", never "may this person scan?".
  // Match the env read and the identifier, not prose: the comment above
  // betaScanAdmissionPolicy deliberately names the retired variable to
  // explain why it is gone.
  assert.doesNotMatch(admissionSource, /Deno\.env\.get\("BETA_COHORT_ALLOWED_USER_IDS"\)/);
  assert.doesNotMatch(admissionSource, /MAX_BETA_CUSTOMERS|allowedUserIds/);
  assert.doesNotMatch(entrySource, /scan_not_invited|allowedUserIds/);
  // Entitlement remains the gate, and it still fails closed.
  assert.match(entrySource, /loadPaidEntitlement\(base44, user\)/);
  assert.match(entrySource, /failure_code: entitlement\.failureCode/);
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
