// The Access-row admission lease is retired.
//
// It claimed admission with Access.updateMany() and read "updated === 1" as a
// compare-and-set. Base44 documents updateMany's matched/updated counts but not
// transactional, compare-and-set or linearizable semantics, so that read cannot
// elect exactly one winner across tabs. Admission authority moved to the
// Firestore coordinator.
//
// This file used to assert that the lease worked. It now asserts that it is
// disabled, that its retired semantics are still documented, and that the
// admission policy gates on coordinator configuration instead of on an
// unproven Base44 primitive.

import assert from "node:assert/strict";
import test from "node:test";

import {
  MAX_BETA_CUSTOMERS,
  betaScanAdmissionPolicy,
  bindScanLease,
  claimScanLease,
  decideScanLease,
  legacyAccessLeaseEnabled,
} from "../../base44/functions/startStandardScanJob/admission.js";

function withDenoEnv(values, run) {
  const priorDeno = globalThis.Deno;
  const map = new Map(Object.entries(values));
  globalThis.Deno = { env: { get: (name) => map.get(name) } };
  try {
    return run(map);
  } finally {
    if (priorDeno === undefined) delete globalThis.Deno;
    else globalThis.Deno = priorDeno;
  }
}

const identity = {
  request_id: "scanreq_request_1",
  idempotency_key: "scanreq_request_1",
  request_fingerprint: "standard_150|https://example.com/",
};

const activeLease = {
  id: "access-1",
  scan_claim_token: "claim-winner",
  scan_claim_request_id: identity.request_id,
  scan_claim_fingerprint: identity.request_fingerprint,
  scan_claim_scan_id: "",
  scan_claim_expires_at: "2026-08-14T15:30:00.000Z",
};

function unusableAccessEntity() {
  return {
    async get() {
      throw new Error("the retired lease must not read Access");
    },
    async updateMany() {
      throw new Error("the retired lease must not write Access");
    },
  };
}

test("admission is default-off and gates on coordinator configuration", () => {
  withDenoEnv({}, (values) => {
    assert.equal(MAX_BETA_CUSTOMERS, 25);
    assert.equal(betaScanAdmissionPolicy().code, "scan_admission_paused");

    values.set("BETA_SCAN_ADMISSION_ENABLED", "true");
    values.set("BETA_COHORT_ALLOWED_USER_IDS", "user-1");
    // The gate is the coordinator, not BASE44_ATOMIC_UPDATE_MANY_CONFIRMED.
    assert.equal(betaScanAdmissionPolicy().code, "scan_admission_coordinator_unconfigured");

    values.set("SCAN_ADMISSION_COORDINATOR_URL", "https://coordinator.example");
    assert.deepEqual(betaScanAdmissionPolicy(), { ok: true, code: "", allowedUserIds: ["user-1"] });
  });
});

test("the retired Base44 atomic flag no longer grants admission", () => {
  withDenoEnv({
    BETA_SCAN_ADMISSION_ENABLED: "true",
    BETA_COHORT_ALLOWED_USER_IDS: "user-1",
    BASE44_ATOMIC_UPDATE_MANY_CONFIRMED: "true",
  }, () => {
    // Setting the old flag must not substitute for a configured coordinator.
    assert.equal(betaScanAdmissionPolicy().code, "scan_admission_coordinator_unconfigured");
  });
});

test("the 25-seat cohort cap is still enforced", () => {
  withDenoEnv({
    BETA_SCAN_ADMISSION_ENABLED: "true",
    SCAN_ADMISSION_COORDINATOR_URL: "https://coordinator.example",
    BETA_COHORT_ALLOWED_USER_IDS: Array.from({ length: 26 }, (_, i) => `user-${i + 1}`).join(","),
  }, () => {
    assert.equal(betaScanAdmissionPolicy().code, "scan_admission_configuration_invalid");
  });
});

test("the legacy lease is disabled by default", () => {
  withDenoEnv({}, () => assert.equal(legacyAccessLeaseEnabled(), false));
  // An unreadable environment must also leave it off rather than throw.
  const priorDeno = globalThis.Deno;
  delete globalThis.Deno;
  try {
    assert.equal(legacyAccessLeaseEnabled(), false);
  } finally {
    if (priorDeno !== undefined) globalThis.Deno = priorDeno;
  }
});

test("claimScanLease refuses without touching Access", async () => {
  const result = await claimScanLease({
    accessEntity: unusableAccessEntity(),
    access: { id: "access-1" },
    identity,
    nowMs: 1_786_732_000_000,
    claimToken: "claim-left",
  });
  assert.deepEqual(result, { action: "unavailable", code: "scan_admission_legacy_lease_disabled" });
});

test("bindScanLease refuses without touching Access", async () => {
  const bound = await bindScanLease({
    accessEntity: unusableAccessEntity(),
    accessId: "access-1",
    claimToken: "claim-winner",
    scanId: "scan-winner",
  });
  assert.equal(bound, false);
});

test("a refused claim can never be read as electing a leader", async () => {
  // The caller branches on action === "leader" before creating a ScanRun, so
  // the retired path must never produce that value.
  for (const access of [{ id: "access-1" }, structuredClone(activeLease)]) {
    const result = await claimScanLease({
      accessEntity: unusableAccessEntity(),
      access,
      identity,
      nowMs: 1_786_732_000_000,
      claimToken: "claim-any",
    });
    assert.notEqual(result.action, "leader");
    assert.notEqual(result.action, "reuse");
  }
});

test("the retired lease semantics stay documented in the pure decision", () => {
  // decideScanLease performs no I/O, so it remains callable as the record of
  // what the old path decided. A reused request id with a different
  // fingerprint was, and still is, a conflict.
  const decision = decideScanLease(
    { ...activeLease, scan_claim_scan_id: "scan-1" },
    { ...identity, request_fingerprint: "standard_150|https://evil.example/" },
    Date.parse("2026-08-14T15:00:00.000Z"),
  );
  assert.deepEqual(decision, { action: "conflict", code: "scan_request_identity_conflict" });
});
