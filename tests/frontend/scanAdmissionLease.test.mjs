import assert from "node:assert/strict";
import test from "node:test";

import {
  MAX_BETA_CUSTOMERS,
  betaScanAdmissionPolicy,
  bindScanLease,
  claimScanLease,
  decideScanLease,
} from "../../base44/functions/startStandardScanJob/admission.js";

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

function atomicAccess(initial) {
  let row = structuredClone(initial);
  return {
    async get(id) {
      return id === row.id ? structuredClone(row) : null;
    },
    async updateMany(query, update) {
      if (!matches(row, query)) return { success: true, updated: 0 };
      row = { ...row, ...(update?.$set || {}) };
      return { success: true, updated: 1 };
    },
    snapshot() {
      return structuredClone(row);
    },
  };
}

const identity = {
  request_id: "scanreq_request_1",
  idempotency_key: "scanreq_request_1",
  request_fingerprint: "standard_150|https://example.com/",
};

test("scan admission is default-off and refuses an unconfirmed Base44 atomic primitive", () => {
  const priorDeno = globalThis.Deno;
  const values = new Map();
  globalThis.Deno = { env: { get: (name) => values.get(name) } };
  try {
    assert.equal(MAX_BETA_CUSTOMERS, 25);
    assert.equal(betaScanAdmissionPolicy().code, "scan_admission_paused");
    values.set("BETA_SCAN_ADMISSION_ENABLED", "true");
    values.set("BETA_COHORT_ALLOWED_USER_IDS", "user-1");
    assert.equal(betaScanAdmissionPolicy().code, "scan_atomic_admission_unconfirmed");
    values.set("BASE44_ATOMIC_UPDATE_MANY_CONFIRMED", "true");
    assert.deepEqual(betaScanAdmissionPolicy(), { ok: true, code: "", allowedUserIds: ["user-1"] });
    values.set(
      "BETA_COHORT_ALLOWED_USER_IDS",
      Array.from({ length: 26 }, (_, index) => `user-${index + 1}`).join(","),
    );
    assert.equal(betaScanAdmissionPolicy().code, "scan_admission_configuration_invalid");
  } finally {
    if (priorDeno === undefined) delete globalThis.Deno;
    else globalThis.Deno = priorDeno;
  }
});

test("two same-request claimers elect one leader and the loser waits", async () => {
  const Access = atomicAccess({ id: "access-1" });
  const access = await Access.get("access-1");
  const [left, right] = await Promise.all([
    claimScanLease({ accessEntity: Access, access, identity, nowMs: 1_786_732_000_000, claimToken: "claim-left" }),
    claimScanLease({ accessEntity: Access, access, identity, nowMs: 1_786_732_000_000, claimToken: "claim-right" }),
  ]);
  assert.deepEqual([left.action, right.action].sort(), ["leader", "pending"]);
  assert.equal(Access.snapshot().scan_claim_request_id, identity.request_id);
});

test("different requests for one owner elect one leader and return busy to the loser", async () => {
  const Access = atomicAccess({ id: "access-1", scan_claim_token: "" });
  const access = await Access.get("access-1");
  const other = {
    request_id: "scanreq_request_2",
    idempotency_key: "scanreq_request_2",
    request_fingerprint: "standard_150|https://other.example/",
  };
  const [left, right] = await Promise.all([
    claimScanLease({ accessEntity: Access, access, identity, nowMs: 1_786_732_000_000, claimToken: "claim-left" }),
    claimScanLease({ accessEntity: Access, access, identity: other, nowMs: 1_786_732_000_000, claimToken: "claim-right" }),
  ]);
  assert.equal([left, right].filter((value) => value.action === "leader").length, 1);
  assert.equal([left, right].filter((value) => value.action === "busy").length, 1);
});

test("a conflicting fingerprint cannot reuse a request ID", () => {
  const access = {
    id: "access-1",
    scan_claim_token: "claim-1",
    scan_claim_request_id: identity.request_id,
    scan_claim_fingerprint: identity.request_fingerprint,
    scan_claim_scan_id: "scan-1",
    scan_claim_expires_at: "2026-08-14T15:30:00.000Z",
  };
  const decision = decideScanLease(access, {
    ...identity,
    request_fingerprint: "standard_150|https://evil.example/",
  }, Date.parse("2026-08-14T15:00:00.000Z"));
  assert.deepEqual(decision, { action: "conflict", code: "scan_request_identity_conflict" });
});

test("only the elected claim token can bind the canonical ScanRun", async () => {
  const Access = atomicAccess({
    id: "access-1",
    scan_claim_token: "claim-winner",
    scan_claim_request_id: identity.request_id,
    scan_claim_fingerprint: identity.request_fingerprint,
    scan_claim_scan_id: "",
    scan_claim_expires_at: "2026-08-14T15:30:00.000Z",
  });
  assert.equal(await bindScanLease({
    accessEntity: Access,
    accessId: "access-1",
    claimToken: "claim-loser",
    scanId: "scan-loser",
  }), false);
  assert.equal(await bindScanLease({
    accessEntity: Access,
    accessId: "access-1",
    claimToken: "claim-winner",
    scanId: "scan-winner",
  }), true);
  assert.equal(Access.snapshot().scan_claim_scan_id, "scan-winner");
});
