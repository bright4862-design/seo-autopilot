import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import {
  issueExtended500Admission,
  extended500CoordinatorSignature,
} from "../../base44/functions/issueExtended500AdmissionV1/handler.js";
import { verifyAuthoritySeal } from "../../base44/functions/issueExtended500AdmissionV1/authoritySeal.js";
import { createHmac } from "node:crypto";

const user = { id: "owner_one", email: "owner@example.com" };
const scan = {
  id: "scan_one", owner_user_id: user.id, project_id: "project_one",
  request_id: "request_one", idempotency_key: "idem_one", attempt_count: 2,
  scan_mode: "extended_500", status: "queued",
  website_url: "https://example.com/", path_prefix: null,
  normalized_domain: "example.com",
  respect_robots_txt: true, owner_attested_robots_override: false,
};
const project = { id: "project_one", owner_user_id: user.id, website_url: "https://example.com/" };
const access = {
  id: "access_one", owner_user_id: user.id, user_email: user.email,
  app_id: "6a498732ec779dfaaeab0e53",
  plan_id: "extended500_lifetime", access_status: "active",
  has_full_access: true, grant_source: "stripe_checkout",
  paid_at: "2026-10-26T19:00:00Z", stripe_checkout_session_id: "cs_test_123",
};
const CONFIG = Object.freeze({
  EXTENDED500_ISSUER_ENABLED: "true",
  EXTENDED500_COORDINATOR_URL: "https://extended500-coordinator.example",
  EXTENDED500_COORDINATOR_SIGNING_KEY: "fixture-coordinator-aaaaaaaaaaaaaaaaaaaa",
  EXTENDED500_ENTITLEMENT_SIGNING_KEY: "fixture-entitlement-bbbbbbbbbbbbbbbbbbb",
  EXTENDED500_ADMISSION_SIGNING_KEY: "fixture-preflight-cccccccccccccccccccc",
});
const CLOCK = Date.parse("2026-10-26T21:00:00.000Z");
const secret = (name) => CONFIG[name] || "";
const plainBody = { scan_id: "scan_one" };

function mock(overrides = {}) {
  const calls = { scan: [], project: [], ownerAccess: [], emailAccess: [], fetch: [] };
  const entities = {
    ScanRun: { async get(id) { calls.scan.push(id); return overrides.scan ?? scan; } },
    BusinessProject: { async get(id) { calls.project.push(id); return overrides.project ?? project; } },
    Access: { async filter(where) {
      if (where.owner_user_id) {
        calls.ownerAccess.push(where.owner_user_id);
        return overrides.ownerRows ?? [access];
      }
      calls.emailAccess.push(where.user_email);
      return overrides.emailRows ?? [access];
    } },
  };
  const fetchImpl = async (url, opts) => {
    calls.fetch.push({ url, opts });
    return { status: 202, async json() {
      return {
        success: true, state: "dispatch_disabled", reserved: true,
        admitted: false, worker_execution_enabled: false, replayed: false,
      };
    } };
  };
  return { calls, entities, fetchImpl };
}
async function callWith(m, other = {}) {
  return issueExtended500Admission({
    body: plainBody, user, entities: m.entities,
    secret, fetchImpl: m.fetchImpl, nowMs: CLOCK, ...other,
  });
}

test("strict authenticated service issuer reads owned ScanRun, project and paid Access from server", async () => {
  const m = mock();
  const result = await callWith(m);
  assert.equal(result.status, 202);
  assert.deepEqual(result.payload, {
    success: true, scan_id: "scan_one", scan_mode: "extended_500",
    reserved: true, admitted: false, worker_execution_enabled: false,
    dispatch_state: "dispatch_disabled", replayed: false,
  });
  assert.deepEqual(m.calls.scan, ["scan_one"]);
  assert.deepEqual(m.calls.project, ["project_one"]);
  assert.deepEqual(m.calls.ownerAccess, [user.id]);
  assert.deepEqual(m.calls.emailAccess, [user.email]);
  assert.equal(m.calls.fetch.length, 1);
  const { url, opts } = m.calls.fetch[0];
  assert.equal(url, "https://extended500-coordinator.example/reserve");
  assert.equal(opts.method, "POST");
  const payload = JSON.parse(opts.body);
  const { proof: ep, ...ent } = payload.entitlement;
  const { proof: gp, ...preflight } = payload.preflight_grant;
  assert.equal(await verifyAuthoritySeal(ent, CONFIG.EXTENDED500_ENTITLEMENT_SIGNING_KEY, ep), true);
  assert.equal(await verifyAuthoritySeal(preflight, CONFIG.EXTENDED500_ADMISSION_SIGNING_KEY, gp), true);
  assert.equal(ent.owner_user_id, user.id);
  assert.equal(ent.attempt_count, 2);
  assert.equal(preflight.request_id, scan.request_id);
  const ts = opts.headers["x-fixlist-timestamp"];
  const derived = createHmac("sha256", CONFIG.EXTENDED500_COORDINATOR_SIGNING_KEY)
    .update("fixlist-extended500-atomic-admission-v1").digest();
  const expected = createHmac("sha256", derived).update(`${ts}\n${opts.body}`).digest("hex");
  assert.equal(opts.headers["x-fixlist-signature"], expected);
  assert.equal(
    await extended500CoordinatorSignature(CONFIG.EXTENDED500_COORDINATOR_SIGNING_KEY, ts, opts.body),
    expected,
  );
  assert.equal(JSON.stringify(result.payload).includes("proof"), false);
  assert.equal(JSON.stringify(result.payload).includes("access_one"), false);
});

test("default disabled issuer never reads entities or creates a reservation", async () => {
  const m = mock();
  const result = await callWith(m, { secret: () => "" });
  assert.equal(result.status, 503);
  assert.equal(result.payload.code, "extended500_issuer_disabled");
  assert.deepEqual(m.calls, { scan: [], project: [], ownerAccess: [], emailAccess: [], fetch: [] });
});

test("client-supplied entitlements/owner/mode/url/grants are forbidden body fields", async () => {
  for (const extra of [
    { owner_user_id: user.id }, { scan_mode: "extended_500" },
    { entitlement: access }, { preflight_grant: { proof: "fake" } },
    { website_url: "https://another.example/" },
    { idempotency_key: scan.idempotency_key }, { plan_id: "extended500_lifetime" },
  ]) {
    const m = mock();
    const result = await callWith(m, { body: { ...plainBody, ...extra } });
    assert.equal(result.status, 400, JSON.stringify(extra));
    assert.equal(m.calls.fetch.length, 0);
    assert.deepEqual(m.calls.scan, []);
  }
});

test("unowned scans and project/domain mismatch never reach Access or coordinator", async () => {
  for (const overrides of [
    { scan: { ...scan, owner_user_id: "another" } },
    { scan: { ...scan, scan_mode: "standard_150" } },
    { scan: { ...scan, status: "complete" } },
    { scan: { ...scan, attempt_count: 0 } },
    { scan: { ...scan, id: "different" } },
    { scan: { ...scan, idempotency_key: "" } },
    { project: { ...project, owner_user_id: "another" } },
    { project: { ...project, website_url: "https://another.example/" } },
    { scan: { ...scan, normalized_domain: "wrong.example" } },
  ]) {
    const m = mock(overrides);
    const result = await callWith(m);
    assert.equal(result.status, 403, JSON.stringify(overrides));
    assert.equal(m.calls.fetch.length, 0);
    assert.deepEqual(m.calls.ownerAccess, []);
  }
});

test("unpaid, wrong-plan, conflict and missing access fail closed after owned scan checks", async () => {
  for (const overrides of [
    { ownerRows: [{ ...access, plan_id: "standard150_lifetime" }], emailRows: [] },
    { ownerRows: [{ ...access, access_status: "pending" }], emailRows: [] },
    { ownerRows: [{ ...access, grant_source: "manual_grant" }], emailRows: [] },
    { ownerRows: [{ ...access, has_full_access: false }], emailRows: [] },
    { ownerRows: [access, { ...access, id: "access_two" }], emailRows: [] },
    { ownerRows: [], emailRows: [] },
  ]) {
    const m = mock(overrides);
    const result = await callWith(m);
    assert.equal(result.status, 403, JSON.stringify(overrides));
    assert.equal(m.calls.fetch.length, 0);
  }
});

test("one valid Extended 500 entitlement may coexist with a Standard 150 purchase", async () => {
  const m = mock({
    ownerRows: [access, { ...access, id: "access_standard", plan_id: "standard150_lifetime" }],
    emailRows: [access],
  });
  assert.equal((await callWith(m)).status, 202);
  assert.equal(m.calls.fetch.length, 1);
});

test("conflicting duplicate Access lookup, missing signing configuration and coordinator failure fail closed", async () => {
  const m = mock({ ownerRows: [access], emailRows: [{ ...access, has_full_access: false }] });
  assert.equal((await callWith(m)).payload.code, "access_read_conflict");
  assert.equal(m.calls.fetch.length, 0);

  const n = mock();
  const weak = await callWith(n, { secret: (name) => name === "EXTENDED500_ISSUER_ENABLED" ? "true" : "missing" });
  assert.equal(weak.status, 503);
  assert.equal(n.calls.scan.length, 0);

  const p = mock();
  p.fetchImpl = async () => { throw new Error("network"); };
  const uncertain = await callWith(p);
  assert.equal(uncertain.status, 503);
  assert.equal(uncertain.payload.code, "reservation_outcome_unknown_retry_same_scan");

  const o = mock();
  o.fetchImpl = async () => ({ status: 200, async json() {
    return { success: true, admitted: true, reserved: true, worker_execution_enabled: true, state: "enqueued" };
  } });
  assert.equal((await callWith(o)).payload.code, "reservation_not_confirmed");
});

test("new function is not in Standard 150 release manifest and does not use client-side Access claims", () => {
  const release = fs.readFileSync("scripts/base44_release_manifest.mjs", "utf8");
  const entry = fs.readFileSync("base44/functions/issueExtended500AdmissionV1/entry.ts", "utf8");
  assert.equal(release.includes('"issueExtended500AdmissionV1"'), false);
  assert.match(entry, /base44\.auth\.me\(/);
  assert.match(entry, /base44\.asServiceRole\.entities/);
  assert.match(entry, /issueExtended500Admission\(/);
  assert.doesNotMatch(entry, /eval\(|Deno\.env/);
  assert.doesNotMatch(entry, /entitlement:\s*body|accessRows:\s*body/);
});
