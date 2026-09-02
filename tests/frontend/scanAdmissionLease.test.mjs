import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  betaScanAdmissionPolicy,
  normalizeAdmissionIdentity,
  scanIntakeEnabled,
} from "../../base44/functions/startStandardScanJob/admission.js";
import {
  admissionClaimEvidenceProof,
  admissionSignature,
  claimAdmission,
  verifyAdmissionClaimEvidence,
} from "../../base44/functions/startStandardScanJob/admissionClient.js";

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
    assert.equal(betaScanAdmissionPolicy(undefined, "").code, "scan_intake_paused");
    assert.equal(betaScanAdmissionPolicy("true", "").code, "scan_admission_paused");
    values.set("BETA_SCAN_ADMISSION_ENABLED", "true");
    assert.equal(betaScanAdmissionPolicy("true", "true").code, "scan_admission_configuration_invalid");
    values.set("SCAN_ADMISSION_COORDINATOR_URL", "https://coordinator.example");
    values.set("SCAN_EVIDENCE_SIGNING_KEY", "test-root");
    assert.deepEqual(betaScanAdmissionPolicy("true", "true"), { ok: true, code: "" });
    values.set("BETA_COHORT_ALLOWED_USER_IDS", Array.from({ length: 150 }, (_, i) => `user-${i + 1}`).join(","));
    assert.deepEqual(betaScanAdmissionPolicy("true", "true"), { ok: true, code: "" });
    values.set("BASE44_ATOMIC_UPDATE_MANY_CONFIRMED", "false");
    assert.deepEqual(betaScanAdmissionPolicy("true", "true"), { ok: true, code: "" });
  });
  assert.doesNotMatch(admissionSource, /BASE44_ATOMIC_UPDATE_MANY_CONFIRMED|updateMany|scan_claim_/);
  assert.doesNotMatch(entrySource, /bindScanLease|claimScanLease|scan_claim_token/);
  assert.match(entrySource, /claimAdmission\(\{/);
  assert.match(entrySource, /bindAdmission\(\{/);
});

test("new intake is independently fail-closed and observes mutable runtime secret values without module reload", () => {
  const values = new Map([
    ["BETA_SCAN_ADMISSION_ENABLED", "true"],
    ["SCAN_ADMISSION_COORDINATOR_URL", "https://coordinator.example"],
    ["SCAN_EVIDENCE_SIGNING_KEY", "test-root"],
  ]);
  let runtimeIntake = "";
  withEnv(values, () => {
    assert.equal(scanIntakeEnabled(runtimeIntake), false);
    assert.equal(betaScanAdmissionPolicy(runtimeIntake, "true").code, "scan_intake_paused");
    runtimeIntake = "true";
    assert.equal(scanIntakeEnabled(runtimeIntake), true);
    assert.equal(betaScanAdmissionPolicy(runtimeIntake, "true").ok, true);
    runtimeIntake = "TRUE";
    assert.equal(scanIntakeEnabled(runtimeIntake), false);
  });
  assert.doesNotMatch(admissionSource, /Deno\.env\.get\("BETA_SCAN_INTAKE_ENABLED"\)/);
  assert.doesNotMatch(admissionSource, /Deno\.env\.get\("BETA_SCAN_ADMISSION_ENABLED"\)/);
  assert.match(entrySource, /secrets\.get\("BETA_SCAN_INTAKE_ENABLED"\)/);
  assert.match(entrySource, /secrets\.get\("BETA_SCAN_ADMISSION_ENABLED"\)/);
  assert.match(entrySource, /betaScanAdmissionPolicy\(mutableScanIntakeValue\(\), mutableScanAdmissionValue\(\)\)/);
  assert.match(clientSource, /BETA_SCAN_ADMISSION_ENABLED/);
});

test("scan admission does not use the static cohort list as a membership gate", () => {
  const values = new Map([
    ["BETA_SCAN_ADMISSION_ENABLED", "true"],
    ["SCAN_ADMISSION_COORDINATOR_URL", "https://coordinator.example"],
    ["SCAN_EVIDENCE_SIGNING_KEY", "test-root"],
  ]);
  withEnv(values, () => {
    assert.equal(betaScanAdmissionPolicy("true", "true").ok, true);
    values.set("BETA_COHORT_ALLOWED_USER_IDS", "malformed/not-a-user-id");
    assert.equal(betaScanAdmissionPolicy("true", "true").ok, true);
  });
  assert.doesNotMatch(admissionSource, /BETA_COHORT_ALLOWED_USER_IDS/);
});

test("claim admission uses request-time coordinator URL and signing key instead of a stale module env snapshot", async () => {
  const priorDeno = globalThis.Deno;
  const stale = new Map([
    ["BETA_SCAN_ADMISSION_ENABLED", "true"],
    ["SCAN_ADMISSION_COORDINATOR_URL", "https://stale-coordinator.example"],
    ["SCAN_EVIDENCE_SIGNING_KEY", "stale-signing-root"],
  ]);
  const live = new Map([
    ["BETA_SCAN_ADMISSION_ENABLED", "true"],
    ["SCAN_ADMISSION_COORDINATOR_URL", "https://live-coordinator.example"],
    ["SCAN_EVIDENCE_SIGNING_KEY", "live-signing-root"],
  ]);
  globalThis.Deno = { env: { get: (name) => stale.get(name) } };

  let seenUrl = "";
  let seenInit = null;
  try {
    const result = await claimAdmission({
      ownerUserId: "user-1",
      requestId: "scanreq_runtime_config_1",
      requestFingerprint: `standard150:${"a".repeat(64)}`,
      env: (name) => String(live.get(name) ?? ""),
      fetchImpl: async (url, init) => {
        seenUrl = String(url);
        seenInit = init;
        return new Response(JSON.stringify({
          success: false,
          error: "scan_intake_paused",
        }), {
          status: 423,
          headers: { "content-type": "application/json" },
        });
      },
    });

    assert.equal(result.ok, false);
    assert.equal(result.failureCode, "scan_intake_paused");
    assert.equal(seenUrl, "https://live-coordinator.example/claim");

    const timestamp = String(seenInit?.headers?.["x-fixlist-timestamp"] || "");
    const payloadText = String(seenInit?.body || "");
    const expected = await admissionSignature("live-signing-root", timestamp, payloadText);
    assert.equal(seenInit?.headers?.["x-fixlist-signature"], expected);
  } finally {
    if (priorDeno === undefined) delete globalThis.Deno;
    else globalThis.Deno = priorDeno;
  }
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

test("acceptance cohort evidence is HMAC verified before persistence", async () => {
  const evidence = {
    version: "admission_claim_evidence_v1",
    owner_user_id: "user-1",
    request_id: "scanreq_request_1",
    barrier_generation: 4,
    claim_sequence: 23,
    admission_mode: "acceptance_only",
    acceptance_cohort_id: "cohort-1",
    acceptance_release_id: "release-1",
    acceptance_source_sha: "a".repeat(40),
    acceptance_expires_at: 1_800_000_000,
  };
  const signingKey = "test-signing-root";
  const proof = await admissionClaimEvidenceProof(evidence, signingKey);
  assert.equal(proof.length, 64);
  assert.equal(await verifyAdmissionClaimEvidence({ evidence, proof, signingKey }), true);
  assert.equal(await verifyAdmissionClaimEvidence({
    evidence: { ...evidence, acceptance_release_id: "tampered" },
    proof,
    signingKey,
  }), false);
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
