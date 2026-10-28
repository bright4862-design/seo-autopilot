import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import {
  buildExtended500QueuedScanDraft,
  classifyExtended500DraftReplay,
  EXTENDED500_DRAFT_VERSION,
  EXTENDED500_SCAN_MODE,
} from "../../src/lib/extended500ScanRunDraft.js";

const user = { id: "owner_one", email: "owner@example.com" };
const project = { id: "project_one", owner_user_id: user.id, website_url: "https://www.example.com/" };
const access = {
  id: "access_extended", owner_user_id: user.id, user_email: user.email,
  app_id: "6a498732ec779dfaaeab0e53",
  plan_id: "extended500_lifetime",
  access_status: "active", has_full_access: true,
  grant_source: "stripe_checkout", stripe_checkout_session_id: "cs_test_500",
  paid_at: "2026-10-27T12:00:00.000Z",
};
const opts = {
  user, project, accessRows: [access],
  requestId: "req_500_once",
  nowMs: Date.parse("2026-10-28T12:00:00.000Z"),
};
const seed = (overrides = {}) => buildExtended500QueuedScanDraft({ ...opts, ...overrides });

test("draft ScanRun is frozen to paid server-owned project root, with no scan authority", () => {
  const result = seed();
  assert.equal(result.ok, true);
  assert.equal(result.draft_version, EXTENDED500_DRAFT_VERSION);
  assert.deepEqual(result.record, {
    project_id: "project_one",
    owner_user_id: "owner_one",
    website_url: "https://www.example.com/",
    submitted_url: "https://www.example.com/",
    normalized_domain: "example.com",
    scan_mode: EXTENDED500_SCAN_MODE,
    status: "queued",
    scan_source: "extended500_private_candidate",
    request_id: "req_500_once",
    idempotency_key: "req_500_once",
    request_fingerprint: "extended_500|https://www.example.com/|root|respect_robots_txt",
    attempt_count: 1,
    queued_at: "2026-10-28T12:00:00.000Z",
    respect_robots_txt: true,
    owner_attested_robots_override: false,
    admission_access_id: "access_extended",
    pages_found: 0,
    pages_crawled: 0,
    pages_retained: 0,
    release_gate_eligible: false,
    review_confidence_state: "not_reviewed",
  });
  assert.equal("id" in result.record, false, "real ScanRun id must be server assigned");
  assert.equal("authority_proof" in result.record, false);
  assert.equal("admission_claim_token" in result.record, false);
});

test("draft fields exactly exist in Base44 schema; Standard150 remains default", () => {
  const schema = JSON.parse(readFileSync("base44/entities/ScanRun.jsonc", "utf8"));
  const { enum: modes, default: modeDefault } = schema.properties.scan_mode;
  assert.equal(modeDefault, "standard_150");
  assert.deepEqual(modes, [
    "standard_150", "basic", "quick", "deep", "advanced", "extended_500",
  ]);
  const allowedStatuses = schema.properties.status.enum;
  const record = seed().record;
  for (const field of Object.keys(record)) {
    assert.ok(schema.properties[field], `Missing schema property ${field}`);
    const kind = schema.properties[field].type;
    assert.equal(kind, typeof record[field], `Wrong schema type for ${field}`);
  }
  assert.ok(allowedStatuses.includes(record.status));
  assert.equal(schema.rls.create.user_condition.role, "admin",
    "Only a service-role API can write 500 drafts");
  assert.equal(schema.rls.read.user_condition.role, "admin");
  assert.equal(schema.rls.update.user_condition.role, "admin");
});

test("independent paid 500 plan required; Standard150 checkout and manual overrides never qualify", () => {
  for (const rows of [
    [],
    [{ ...access, plan_id: "standard150_lifetime" }],
    [{ ...access, grant_source: "manual_grant" }],
    [{ ...access, grant_source: "owner_test" }],
    [{ ...access, access_status: "pending", has_full_access: false }],
    [{ ...access, access_status: "revoked" }],
    [{ ...access, stripe_checkout_session_id: "" }],
    [{ ...access, paid_at: "" }],
    [{ ...access, owner_user_id: "different" }],
    [{ ...access, user_email: "different@example.com" }],
    [access, { ...access, id: "access2" }],
  ]) assert.equal(seed({ accessRows: rows }).ok, false, JSON.stringify(rows));
  assert.equal(seed({ accessRows: [
    { ...access, id: "standard_paid", plan_id: "standard150_lifetime" },
    access,
  ] }).ok, true, "an independent Standard 150 purchase may coexist");
});

test("unowned project, missing/unsafe identity and private-host targets denied", () => {
  for (const p of [
    { ...project, owner_user_id: "other" },
    { ...project, id: "" },
    { ...project, website_url: "http://localhost/" },
    { ...project, website_url: "http://127.0.0.1/" },
    { ...project, website_url: "http://192.168.1.1/" },
    { ...project, website_url: "http://foo.internal/" },
    { ...project, website_url: "https://example.local/" },
    { ...project, website_url: "https://user:pass@example.com/" },
    { ...project, website_url: "https://example.com:8443/" },
    { ...project, website_url: "https://example.com/?token=secret" },
    { ...project, website_url: "https://example.com/blog/" },
    { ...project, website_url: "file:///etc/passwd" },
  ]) assert.equal(seed({ project: p }).ok, false, p.website_url);
  for (const requestId of ["", "../path", "owner/other", "with spaces", "x".repeat(129)]) {
    assert.equal(seed({ requestId }).ok, false, requestId);
  }
  assert.equal(seed({ user: { ...user, id: "other" } }).ok, false);
  assert.equal(seed({ nowMs: NaN }).ok, false);
  assert.equal(seed({ nowMs: -1 }).ok, false);
  assert.equal(seed({ nowMs: 8_640_000_000_000_001 }).ok, false);
});

test("replay is exact, terminals are immutable, absence still REQUIRES atomic creation", () => {
  const draft = seed();
  assert.deepEqual(classifyExtended500DraftReplay(draft, []),
    { ok: true, decision: "requires_atomic_create" });
  const persisted = { ...draft.record, id: "scan_created_server_side" };
  assert.deepEqual(classifyExtended500DraftReplay(draft, [persisted]), {
    ok: true, decision: "matching_existing_scan", scan_id: persisted.id,
  });
  assert.deepEqual(classifyExtended500DraftReplay(draft, [{ ...persisted, status: "failed" }]), {
    ok: true, decision: "terminal_receipt_not_reusable", scan_id: persisted.id,
  });
  assert.deepEqual(classifyExtended500DraftReplay(draft, [{ ...persisted, status: "complete" }]), {
    ok: true, decision: "terminal_receipt_not_reusable", scan_id: persisted.id,
  });
  for (const [field, value] of [
    ["owner_user_id", "other"], ["project_id", "other"],
    ["request_id", "other"], ["attempt_count", 2],
    ["scan_mode", "standard_150"], ["website_url", "https://other.com/"],
    ["normalized_domain", "other.com"],
    ["idempotency_key", "reused_wrong"], ["request_fingerprint", "standard_150|other"],
    ["admission_access_id", "other-access"],
    ["respect_robots_txt", false], ["owner_attested_robots_override", true],
    ["path_prefix", "/hidden"], ["status", "unknown"],
  ]) assert.equal(
    classifyExtended500DraftReplay(draft, [{ ...persisted, [field]: value }]).ok,
    false, field,
  );
  assert.equal(classifyExtended500DraftReplay(draft, [persisted, { ...persisted, id: "scan2" }]).ok, false);
  assert.equal(classifyExtended500DraftReplay({ ok: false }, []).ok, false);
  assert.equal(classifyExtended500DraftReplay(draft, undefined).ok, false);
});

test("the public scanner identity builder, form and Standard150 job route remain 150-only", () => {
  const identity = readFileSync("src/lib/scanRunIdentity.js", "utf8");
  const form = readFileSync("src/components/scan/ScanWebsiteForm.jsx", "utf8");
  const worker = readFileSync("scanner-api/app/main.py", "utf8");
  const issuer = readFileSync("base44/functions/issueExtended500AdmissionV1/entry.ts", "utf8");
  assert.match(identity, /if \(normalizedMode !== STANDARD_SCAN_MODE\)/);
  assert.match(form, /standard_150/);
  assert.match(worker, /Only the Standard 150 scan is available/);
  assert.match(issuer, /EXTENDED500_ISSUER_ENABLED/);
  assert.doesNotMatch(issuer, /Extended500QueuedScanDraft|ScanRun\.create\(/);
  assert.equal(seed().record.release_gate_eligible, false);
});
