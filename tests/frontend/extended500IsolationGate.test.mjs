// Independent, source-bound Extended 500 release negative matrix.
// A passing test is an isolation gate, NOT proof that the product is deployable.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  evaluateExtended500PaidAccess,
} from "../../src/lib/extended500EntitlementIssuer.js";
import {
  buildExtended500QueuedScanDraft,
} from "../../src/lib/extended500ScanRunDraft.js";

const read = (path) => readFileSync(path, "utf8");
const user = { id: "owner500", email: "customer@example.com" };
const project = { id: "project500", owner_user_id: user.id, website_url: "https://example.com/" };
const valid = {
  id: "paid500", app_id: "6a498732ec779dfaaeab0e53",
  owner_user_id: user.id, user_email: user.email,
  plan_id: "extended500_lifetime", access_status: "active",
  has_full_access: true, grant_source: "stripe_checkout",
  stripe_checkout_session_id: "cs_500paid",
  paid_at: "2026-10-29T00:00:00Z",
};

test("public Standard 150 checkout and webhook may not silently grant the unready 500 tier", () => {
  const checkout = read("base44/functions/createAccessCheckout/entry.ts");
  const webhook = read("base44/functions/stripeWebhook/entry.ts");
  const identity = read("src/lib/scanRunIdentity.js");
  assert.match(checkout, /const PLAN_ID = "standard150_lifetime"/);
  assert.match(webhook, /const PLAN_ID = "standard150_lifetime"/);
  assert.match(checkout, /const STRIPE_PRICE_ID = "price_1UFXgX4DcTLS57kiIag23r8C"/);
  assert.match(webhook, /const EXPECTED_AMOUNT = 4900/);
  assert.doesNotMatch(checkout, /extended500_lifetime/);
  assert.doesNotMatch(webhook, /extended500_lifetime/);
  assert.match(identity, /if \(normalizedMode !== STANDARD_SCAN_MODE\)/);
});

test("Extended 500 schema addition alone does not change public default or admin-only writes", () => {
  const scan = JSON.parse(read("base44/entities/ScanRun.jsonc"));
  assert.equal(scan.properties.scan_mode.default, "standard_150");
  assert.ok(scan.properties.scan_mode.enum.includes("extended_500"));
  for(const permission of ["create", "read", "update", "delete"]){
    assert.equal(scan.rls[permission].user_condition.role, "admin");
  }
  const http = read("scanner-api/app/main.py");
  assert.doesNotMatch(http, /@app\.(?:post|route)\(["']\/scan-job-extended500["']/);
  assert.match(http, /\/scan-job-extended500-preflight/);
  assert.match(http, /Only the Standard 150 scan is available/);
});

test("paid Access permits exactly one independent 500 grant; no 150/manual/pending upgrade", () => {
  const rows = [
    [], [{ ...valid, plan_id: "standard150_lifetime" }],
    [{ ...valid, grant_source: "owner_test" }],
    [{ ...valid, grant_source: "manual_grant" }],
    [{ ...valid, has_full_access: false }],
    [{ ...valid, access_status: "pending" }],
    [{ ...valid, access_status: "revoked" }],
    [{ ...valid, stripe_checkout_session_id: "bad session" }],
    [{ ...valid, owner_user_id: "other" }],
    [valid, { ...valid, id: "second_paid500" }],
  ];
  for (const row of rows) {
    assert.equal(evaluateExtended500PaidAccess({ user, accessRows: row }).ok, false,
      JSON.stringify(row).slice(0, 120));
  }
  assert.equal(evaluateExtended500PaidAccess({
    user, accessRows: [valid, { ...valid, id: "standard150_paid", plan_id: "standard150_lifetime" }],
  }).ok, true);
});

test("untrusted project, access or URL cannot create even a private 500 ScanRun draft", () => {
  const make = (overrides) => buildExtended500QueuedScanDraft({
    user, project, accessRows: [valid], requestId: "request500", nowMs: Date.now(), ...overrides,
  });
  for (const changes of [
    { user: { ...user, id: "attacker" } },
    { project: { ...project, owner_user_id: "attacker" } },
    { project: { ...project, website_url: "http://localhost/" } },
    { project: { ...project, website_url: "https://example.com/private/" } },
    { project: { ...project, website_url: "https://example.com/?token=secret" } },
    { accessRows: [{ ...valid, access_status: "pending" }] },
    { accessRows: [{ ...valid, plan_id: "standard150_lifetime" }] },
  ]) assert.equal(make(changes).ok, false, JSON.stringify(changes));
  const draft = make({});
  assert.equal(draft.record.release_gate_eligible, false);
  assert.equal(draft.record.scan_mode, "extended_500");
  assert.equal(draft.record.respect_robots_txt, true);
  assert.equal(draft.record.owner_attested_robots_override, false);
});

test("owner-only Extended 500 service gates default disabled; absence of worker prevents reservation", () => {
  const coordinator = read("extended500-admission/service.py");
  const issuer = read("base44/functions/issueExtended500AdmissionV1/handler.js");
  assert.match(coordinator, /ENABLED = os\.getenv\("EXTENDED500_ATOMIC_ADMISSION_ENABLED", ""\)\.lower\(\) == "true"/);
  assert.match(coordinator, /QUEUE_ENABLED = os\.getenv\("EXTENDED500_QUEUE_DISPATCH_ENABLED", ""\)\.lower\(\) == "true"/);
  assert.match(coordinator, /WORKER_READY = os\.getenv\("EXTENDED500_WORKER_READY", ""\)\.lower\(\) == "true"/);
  assert.match(coordinator, /if not QUEUE_ENABLED or not WORKER_READY:/);
  assert.match(issuer, /EXTENDED500_ISSUER_ENABLED/);
  assert.match(issuer, /Object\.keys\(body\)\.length !== 1/);
  assert.doesNotMatch(issuer, /ScanRun\.create\(/);
});

test("unreviewed 500 evidence cannot masquerade as final customer authority", () => {
  const py = read("scanner-api/app/extended500_evidence_handoff.py");
  const js = read("src/lib/extended500EvidenceHandoff.js");
  assert.match(py, /EXTENDED500_HANDOFF_VERSION = "extended500_evidence_handoff_v1_unreviewed"/);
  assert.match(py, /"review_status": "not_reviewed"/);
  assert.match(py, /"release_gate_eligible": False/);
  assert.match(js, /review\.review_status !== "not_reviewed"/);
  assert.match(js, /return \{ valid: true, state: "unreviewed_evidence_only"/);
  const publicWriter = read("base44/functions/persistDurableScanAuthorityV8/entry.ts");
  assert.doesNotMatch(publicWriter, /extended500_evidence_handoff_v1_unreviewed/);
});
