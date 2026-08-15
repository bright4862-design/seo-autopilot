// Contract for the server-owned scan admission path.
//
// Two things are pinned here that nothing else can pin:
//
//  1. Cross-language signature agreement. The Base44 signer is JavaScript and
//     the coordinator verifier is Python. The expected digests below were
//     produced by the Python implementation in admission-coordinator/main.py,
//     so if either side's derivation drifts, this test fails rather than
//     production returning invalid_signature.
//
//  2. Fail-closed defaults. Admission stays off until BETA_SCAN_ADMISSION_ENABLED
//     is exactly "true", and every entry point refuses while it is off.

import assert from "node:assert/strict";
import test from "node:test";

import {
  ACTION_CONFLICT,
  ACTION_CREATE,
  ACTION_REUSE,
  FAILURE_SCAN_CONFLICT,
  matchingScanRuns,
  normalizeScanIdentity,
  resolveCanonicalScanRun,
} from "../../base44/functions/scanAdmission/canonicalScanRun.js";
import {
  ADMISSION_FLAG,
  ADMISSION_LABEL,
  SAFE_COORDINATOR_ERRORS,
  admissionEnabled,
  admissionSignature,
  bindAdmission,
  claimAdmission,
  releaseAdmission,
} from "../../base44/functions/scanAdmission/admissionClient.js";

const OWNER = "6a498da58ef5cec1f5cd4486";
const REQUEST = "req_alpha";
const SCAN_ID = "6a7f606b1f3c36298704c439";
const OTHER_SCAN_ID = "6a7f518b619f437d8c363983";

function row(overrides = {}) {
  return { id: SCAN_ID, owner_user_id: OWNER, request_id: REQUEST, status: "queued", ...overrides };
}

function offEnv() {
  return "";
}

function onEnv(name) {
  return name === ADMISSION_FLAG ? "true" : "";
}

// --------------------------------------------------------------------------
// Canonical ScanRun resolution
// --------------------------------------------------------------------------

test("zero rows means the server must create exactly one ScanRun", () => {
  const decision = resolveCanonicalScanRun({ rows: [], ownerUserId: OWNER, requestId: REQUEST });
  assert.equal(decision.action, ACTION_CREATE);
  assert.equal(decision.scanId, "");
});

test("one row is adopted instead of creating a second", () => {
  // The partial-failure case: Base44 committed the row but the response was
  // lost, so the retry must recover this exact entity.
  const decision = resolveCanonicalScanRun({ rows: [row()], ownerUserId: OWNER, requestId: REQUEST });
  assert.equal(decision.action, ACTION_REUSE);
  assert.equal(decision.scanId, SCAN_ID);
});

test("two rows for one request fail closed rather than guessing", () => {
  const decision = resolveCanonicalScanRun({
    rows: [row(), row({ id: OTHER_SCAN_ID })],
    ownerUserId: OWNER,
    requestId: REQUEST,
  });
  assert.equal(decision.action, ACTION_CONFLICT);
  assert.equal(decision.failureCode, FAILURE_SCAN_CONFLICT);
  assert.deepEqual(decision.conflictingScanIds, [OTHER_SCAN_ID, SCAN_ID].sort());
});

test("rows belonging to another owner or request are never adopted", () => {
  const rows = [
    row({ id: "wrong_owner", owner_user_id: "6a498da58ef5cec1f5cd4487" }),
    row({ id: "wrong_request", request_id: "req_beta" }),
  ];
  const decision = resolveCanonicalScanRun({ rows, ownerUserId: OWNER, requestId: REQUEST });
  assert.equal(decision.action, ACTION_CREATE);
});

test("a repeated row is counted once, not treated as a conflict", () => {
  const duplicate = row();
  const decision = resolveCanonicalScanRun({ rows: [duplicate, duplicate], ownerUserId: OWNER, requestId: REQUEST });
  assert.equal(decision.action, ACTION_REUSE);
});

test("rows without a server-assigned id are not adoptable", () => {
  assert.deepEqual(matchingScanRuns([row({ id: "" })], { ownerUserId: OWNER, requestId: REQUEST }), []);
});

test("missing identity fails closed instead of matching everything", () => {
  for (const args of [
    { rows: [row()], ownerUserId: "", requestId: REQUEST },
    { rows: [row()], ownerUserId: OWNER, requestId: "" },
  ]) {
    assert.equal(resolveCanonicalScanRun(args).action, ACTION_CONFLICT);
  }
});

test("malformed row collections are tolerated", () => {
  for (const rows of [null, undefined, "nope", [null, 7, "x"]]) {
    assert.equal(resolveCanonicalScanRun({ rows, ownerUserId: OWNER, requestId: REQUEST }).action, ACTION_CREATE);
  }
});

test("scan identity is normalized to the server-assigned entity id", () => {
  // scan_id arriving on the row is advisory; entity.id is the only identity
  // Base44 guarantees, and it is the one a browser could never choose.
  const normalized = normalizeScanIdentity({ id: SCAN_ID, scan_id: "browser-chosen-id" });
  assert.equal(normalized.ok, true);
  assert.equal(normalized.scanId, SCAN_ID);
  assert.equal(normalized.scanRun.scan_id, SCAN_ID);
});

test("an entity without an id cannot become canonical", () => {
  assert.equal(normalizeScanIdentity({ scan_id: "browser-chosen-id" }).ok, false);
  assert.equal(normalizeScanIdentity(null).failureCode, "admission_scan_id_missing");
});

// --------------------------------------------------------------------------
// Cross-language signing
// --------------------------------------------------------------------------

test("the JavaScript signer matches the Python verifier byte for byte", async () => {
  const body = JSON.stringify({ owner_user_id: OWNER, request_id: REQUEST });
  const signature = await admissionSignature("unit-test-signing-root", "1760000000", body);
  assert.equal(signature, "00b8acd4a0c03f68a3cf36f5749fb68debe3948a7c1c3600bb0905c069e70689");
});

test("an admission signature cannot authenticate against the dispatch gateway", async () => {
  const body = JSON.stringify({ owner_user_id: OWNER, request_id: REQUEST });
  const admissionSig = await admissionSignature("unit-test-signing-root", "1760000000", body);
  const gatewaySig = "d4c4e1119c2eb4728f7b96af89b139d90f6bf4cc33363ee0861682726145fd9a";
  assert.notEqual(admissionSig, gatewaySig);
});

test("the admission label is domain-separated from the gateway label", () => {
  assert.equal(ADMISSION_LABEL, "fixlist-admission-coordinator-v1");
  assert.notEqual(ADMISSION_LABEL, "fixlist-dispatch-gateway-v1");
});

test("the signature covers the timestamp, so a replay at another time fails", async () => {
  const body = JSON.stringify({ owner_user_id: OWNER });
  const first = await admissionSignature("root", "1760000000", body);
  const second = await admissionSignature("root", "1760000001", body);
  assert.notEqual(first, second);
});

// --------------------------------------------------------------------------
// Fail-closed configuration
// --------------------------------------------------------------------------

test("admission is disabled unless the flag is exactly true", () => {
  assert.equal(admissionEnabled(onEnv), true);
  for (const value of ["", "false", "1", "TRUE", "True", "yes", " true"]) {
    assert.equal(admissionEnabled(() => value), false, `flag value ${JSON.stringify(value)} must not enable admission`);
  }
});

test("every admission entry point refuses while the flag is off", async () => {
  const calls = [
    claimAdmission({ ownerUserId: OWNER, requestId: REQUEST, requestFingerprint: "fp", env: offEnv }),
    bindAdmission({ ownerUserId: OWNER, requestId: REQUEST, claimToken: "t", scanId: SCAN_ID, env: offEnv }),
    releaseAdmission({ ownerUserId: OWNER, scanId: SCAN_ID, terminalStatus: "complete", env: offEnv }),
  ];
  for (const result of await Promise.all(calls)) {
    assert.equal(result.ok, false);
    assert.equal(result.failureCode, "admission_disabled");
    assert.equal(result.outcomeUnknown, false);
  }
});

test("a missing coordinator URL fails closed rather than defaulting", async () => {
  const result = await claimAdmission({
    ownerUserId: OWNER,
    requestId: REQUEST,
    requestFingerprint: "fp",
    env: onEnv,
    coordinatorUrl: "",
    signingKey: "root",
  });
  assert.equal(result.ok, false);
  assert.equal(result.failureCode, "admission_not_configured");
});

// --------------------------------------------------------------------------
// Coordinator responses
// --------------------------------------------------------------------------

function fakeFetch(status, body) {
  return async (url, init) => {
    fakeFetch.lastUrl = url;
    fakeFetch.lastInit = init;
    return {
      ok: status >= 200 && status < 300,
      status,
      json: async () => body,
    };
  };
}

const enabled = { env: onEnv, coordinatorUrl: "https://coordinator.example", signingKey: "root" };

test("a winning claim is returned with its token", async () => {
  const result = await claimAdmission({
    ownerUserId: OWNER,
    requestId: REQUEST,
    requestFingerprint: "fp",
    ...enabled,
    fetchImpl: fakeFetch(200, { success: true, outcome: "claimed", claim_token: "tok", scan_id: "" }),
  });
  assert.equal(result.ok, true);
  assert.equal(result.outcome, "claimed");
  assert.equal(result.claim_token, "tok");
  assert.equal(fakeFetch.lastUrl, "https://coordinator.example/claim");
  assert.equal(fakeFetch.lastInit.headers["x-fixlist-signature"].length, 64);
});

test("a busy coordinator surfaces the retry hint and creates nothing", async () => {
  const result = await claimAdmission({
    ownerUserId: OWNER,
    requestId: REQUEST,
    requestFingerprint: "fp",
    ...enabled,
    fetchImpl: fakeFetch(429, { success: false, error: "admission_busy", retry_after_seconds: 42 }),
  });
  assert.equal(result.ok, false);
  assert.equal(result.failureCode, "admission_busy");
  assert.equal(result.retryAfterSeconds, 42);
  assert.equal(result.outcomeUnknown, false);
});

test("a rebind of the same scan reports already_bound", async () => {
  const result = await bindAdmission({
    ownerUserId: OWNER,
    requestId: REQUEST,
    claimToken: "tok",
    scanId: SCAN_ID,
    ...enabled,
    fetchImpl: fakeFetch(200, { success: true, outcome: "already_bound", scan_id: SCAN_ID }),
  });
  assert.equal(result.ok, true);
  assert.equal(result.outcome, "already_bound");
});

test("a 4xx is a decision, so the outcome is known to be 'nothing happened'", async () => {
  const result = await bindAdmission({
    ownerUserId: OWNER,
    requestId: REQUEST,
    claimToken: "tok",
    scanId: SCAN_ID,
    ...enabled,
    fetchImpl: fakeFetch(409, { success: false, error: "scan_identity_conflict" }),
  });
  assert.equal(result.outcomeUnknown, false);
  assert.equal(result.failureCode, "scan_identity_conflict");
});

test("a 5xx leaves the outcome unknown", async () => {
  const result = await bindAdmission({
    ownerUserId: OWNER,
    requestId: REQUEST,
    claimToken: "tok",
    scanId: SCAN_ID,
    ...enabled,
    fetchImpl: fakeFetch(503, { success: false, error: "coordinator_unavailable" }),
  });
  assert.equal(result.outcomeUnknown, true);
});

test("a network failure leaves the outcome unknown rather than assuming failure", async () => {
  const result = await releaseAdmission({
    ownerUserId: OWNER,
    scanId: SCAN_ID,
    terminalStatus: "complete",
    ...enabled,
    fetchImpl: async () => { throw new Error("connection reset"); },
  });
  assert.equal(result.ok, false);
  assert.equal(result.outcomeUnknown, true);
  assert.equal(result.failureCode, "admission_unreachable");
});

test("an unrecognised upstream error never becomes a control-flow value", async () => {
  const result = await claimAdmission({
    ownerUserId: OWNER,
    requestId: REQUEST,
    requestFingerprint: "fp",
    ...enabled,
    fetchImpl: fakeFetch(400, { success: false, error: "../../etc/passwd" }),
  });
  assert.equal(result.failureCode, "coordinator_rejected");
  assert.equal(SAFE_COORDINATOR_ERRORS.has("../../etc/passwd"), false);
});

test("the safe error set covers every code the coordinator can return", () => {
  for (const code of [
    "admission_busy", "request_conflict", "scan_identity_conflict", "invalid_claim_token",
    "claim_expired", "claim_not_found", "not_terminal_status", "scan_not_bound",
    "coordinator_unavailable", "invalid_signature", "stale_request",
  ]) {
    assert.equal(SAFE_COORDINATOR_ERRORS.has(code), true, `${code} must be a recognised coordinator error`);
  }
});
