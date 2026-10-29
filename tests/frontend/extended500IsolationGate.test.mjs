// Lane E: independent, candidate-blind Extended 500 isolation gate (issue #386).
// Candidate: draft PR #377 head 002b84c9b6eaef78babec6081df150f31a000b11.
// Matrix: docs/extended500/lane-e-acceptance-matrix.md.
//
// Offline. Base44, Stripe and the coordinator are in-process fakes; passing here
// proves source decisions only, never deployment, Stripe behaviour or customer
// correctness. RED items use `{ todo: "RED: ..." }` and STILL execute the real
// requirement assertion (node:test todo is non-strict: an unexpected pass does
// not fail CI, so the strict ledger is the pytest xfail set plus the matrix doc).
import assert from "node:assert/strict";
import { readFileSync, readdirSync, existsSync } from "node:fs";
import test from "node:test";

import { createAuthoritySeal } from "../../base44/functions/persistDurableScanAuthority/authoritySeal.js";
import { issueExtended500Admission } from "../../base44/functions/issueExtended500AdmissionV1/handler.js";
import { evaluateExtended500PaidAccess } from "../../base44/functions/issueExtended500AdmissionV1/issuer.js";
import { evaluatePaidAccess, evaluateScanAccess } from "../../base44/functions/startStandardScanJobV8/entitlement.js";
import {
  evaluateExtended500PaidAccess as evaluateSrcLibExtended500PaidAccess,
} from "../../src/lib/extended500EntitlementIssuer.js";
import { buildExtended500QueuedScanDraft } from "../../src/lib/extended500ScanRunDraft.js";
import {
  EXTENDED500_HANDOFF_VERSION,
  verifyExtended500EvidenceHandoff,
} from "../../src/lib/extended500EvidenceHandoff.js";

const CANDIDATE = "002b84c";
const red = (requirement) => `RED: ${requirement} not implemented on candidate ${CANDIDATE}`;
const APP_ID = "6a498732ec779dfaaeab0e53";
const read = (path) => readFileSync(path, "utf8");

const user = { id: "owner_e", email: "owner-e@example.com" };
const std150Paid = {
  id: "access_std150", owner_user_id: user.id, user_email: user.email, app_id: APP_ID,
  plan_id: "standard150_lifetime", access_status: "active", has_full_access: true,
  grant_source: "stripe_checkout", stripe_checkout_session_id: "cs_std150", paid_at: "2026-10-20T10:00:00.000Z",
};
const ext500Paid = {
  ...std150Paid, id: "access_ext500", plan_id: "extended500_lifetime",
  stripe_checkout_session_id: "cs_ext500", paid_at: "2026-10-21T10:00:00.000Z",
};

// Extract a plain-JS top-level function from a Deno source file by brace matching.
function extractFunction(source, name) {
  const start = source.indexOf(`function ${name}(`);
  assert.notEqual(start, -1, `function ${name} not found`);
  let depth = 0;
  // Body starts at the first ") {" after the name (skips destructured parameters).
  for (let i = source.indexOf(") {", start) + 2; i < source.length; i += 1) {
    if (source[i] === "{") depth += 1;
    if (source[i] === "}" && --depth === 0) return source.slice(start, i + 1);
  }
  throw new Error(`unbalanced ${name}`);
}
async function importFunctions(source, names, prelude = "") {
  const body = names.map((name) => extractFunction(source, name)).join("\n");
  const text = `${prelude}\n${body}\nexport { ${names.join(", ")} };`;
  return import(`data:text/javascript;base64,${Buffer.from(text).toString("base64")}`);
}
async function importHandlerWithHarness(source, harnessName) {
  const withoutImports = source.replace(/^import .*;\s*$/gm, "");
  const prelude = `const { createClientFromRequest, Stripe, secrets, console = globalThis.console } = globalThis.${harnessName};`;
  return import(`data:text/javascript;base64,${Buffer.from(`${prelude}\n${withoutImports}`).toString("base64")}`);
}

// ---------------------------------------------------------------------------
// ISO: Standard 150 surfaces refuse Extended 500 and vice versa
// ---------------------------------------------------------------------------
test("iso: Standard 150 start function and Cloud Tasks builder pin standard_150 (source assertion)", () => {
  const entry = read("base44/functions/startStandardScanJobV8/entry.ts");
  assert.match(entry, /const PUBLIC_SCAN_MODE = "standard_150";/);
  assert.match(entry, /if \(requestedMode !== PUBLIC_SCAN_MODE\)/);
  assert.doesNotMatch(entry, /extended_500|extended500/);
  const gateway = read("dispatch-gateway/main.py");
  assert.match(gateway, /if job\.get\("scan_mode"\) != "standard_150":/);
  const manifest = read("scripts/base44_release_manifest.mjs");
  assert.equal(/issueExtended500AdmissionV1|extended500/i.test(manifest), false);
});

test("iso: product entitlement matrix — each policy accepts only its own paid plan", () => {
  const cases = [
    { row: std150Paid, std150: true, ext500: false },
    { row: ext500Paid, std150: false, ext500: true },
    { row: { ...ext500Paid, grant_source: "manual_grant", granted_at: "2026-10-21T10:00:00.000Z" }, std150: false, ext500: false },
    { row: { ...ext500Paid, grant_source: "owner_test", granted_at: "2026-10-21T10:00:00.000Z" }, std150: false, ext500: false },
    { row: { ...ext500Paid, access_status: "pending", has_full_access: false }, std150: false, ext500: false },
    { row: { ...ext500Paid, app_id: "other_app" }, std150: false, ext500: false },
  ];
  for (const { row, std150, ext500 } of cases) {
    assert.equal(evaluatePaidAccess({ rows: [row], user }).ok, std150, `150 ${JSON.stringify(row)}`);
    assert.equal(evaluateExtended500PaidAccess({ user, accessRows: [row] }).ok, ext500, `500 ${JSON.stringify(row)}`);
  }
});

test("iso: Standard 150 paid customer who also holds an Extended 500 grant keeps Standard 150 access",
  { todo: red("cross-product Access coexistence in Standard 150 evaluatePaidAccess/evaluateScanAccess (any 2nd Access row => paid_access_conflict)") },
  () => {
    assert.equal(evaluateExtended500PaidAccess({ user, accessRows: [std150Paid, ext500Paid] }).ok, true);
    const scan = evaluateScanAccess({ rows: [std150Paid, ext500Paid], user, priorRuns: [] });
    assert.equal(scan.ok, true, `Standard 150 customer locked out: ${scan.failureCode}`);
    assert.equal(scan.preview, false);
  });

// ---------------------------------------------------------------------------
// PAY: Standard 150 payment contract ($49), webhook idempotency, no 500 grants
// ---------------------------------------------------------------------------
const webhookSource = read("base44/functions/stripeWebhook/entry.ts");
const checkoutSource = read("base44/functions/createAccessCheckout/entry.ts");

function webhookHarness(initialRows) {
  const state = { rows: initialRows.map((row) => ({ ...row })), reads: 0, updates: [] };
  const base44 = { asServiceRole: { entities: { Access: {
    async filter(query) {
      state.reads += 1;
      return state.rows.filter((row) => (query.owner_user_id && row.owner_user_id === query.owner_user_id)
        || (query.user_email && row.user_email === query.user_email)).map((row) => ({ ...row }));
    },
    async update(id, fields) {
      state.updates.push({ id, fields });
      state.rows = state.rows.map((row) => (row.id === id ? { ...row, ...fields } : row));
      return state.rows.find((row) => row.id === id);
    },
  } } } };
  class FakeStripe {
    constructor() { this.webhooks = { constructEventAsync: async (body) => JSON.parse(body) }; }
  }
  return { state, harness: { createClientFromRequest: () => base44, Stripe: FakeStripe,
    secrets: { get: () => "lane-e-secret" }, console: { error() {}, warn() {} } } };
}
function paidEvent(sessionId, metadata = {}, overrides = {}) {
  return {
    id: `evt_${sessionId}`, type: "checkout.session.completed", created: 1_793_000_000,
    data: { object: {
      id: sessionId, payment_status: "paid", amount_total: 4900, currency: "usd",
      customer_email: user.email, client_reference_id: user.id, payment_intent: `pi_${sessionId}`,
      metadata: { base44_app_id: APP_ID, plan_id: "standard150_lifetime", access_id: "access_pending",
        owner_user_id: user.id, user_email: user.email, ...metadata },
      ...overrides,
    } },
  };
}
async function runWebhook(rows, events) {
  const { state, harness } = webhookHarness(rows);
  globalThis.__laneEWebhookHarness = harness;
  try {
    const { default: handler } = await importHandlerWithHarness(webhookSource, "__laneEWebhookHarness");
    const replies = [];
    for (const event of events) {
      const response = await handler(new Request("https://function.test", {
        method: "POST", headers: { "stripe-signature": "sig" }, body: JSON.stringify(event),
      }));
      replies.push({ status: response.status, body: await response.json() });
    }
    return { state, replies };
  } finally {
    delete globalThis.__laneEWebhookHarness;
  }
}
const pending150 = {
  id: "access_pending", owner_user_id: user.id, user_email: user.email, app_id: APP_ID,
  plan_id: "standard150_lifetime", access_status: "pending", has_full_access: false,
  grant_source: "checkout_pending", stripe_checkout_session_id: "cs_first",
};

test("pay: $49 is the single Standard 150 price across UI, checkout and webhook", () => {
  assert.match(read("src/lib/access.js"), /export const UNLOCK_PRICE_LABEL = "\$49";/);
  assert.match(webhookSource, /const EXPECTED_AMOUNT = 4900;/);
  assert.match(webhookSource, /const EXPECTED_CURRENCY = "usd";/);
  assert.match(checkoutSource, /line_items: \[\{ price: STRIPE_PRICE_ID, quantity: 1 \}\]/);
  assert.match(checkoutSource, /const PLAN_ID = "standard150_lifetime";/);
});

test("pay: webhook grants exactly once, replays/duplicate payments never re-grant, and the grant is never Extended 500", async () => {
  const { state, replies } = await runWebhook([pending150], [
    paidEvent("cs_first"), paidEvent("cs_first"), paidEvent("cs_second"),
    paidEvent("cs_wrong_amount", {}, { amount_total: 9900 }),
    paidEvent("cs_eur", {}, { currency: "eur" }),
    paidEvent("cs_unpaid", {}, { payment_status: "unpaid" }),
  ]);
  assert.deepEqual(replies.map((r) => r.status), [200, 200, 200, 400, 400, 200]);
  assert.deepEqual(replies[1].body, { received: true, replay: true });
  assert.deepEqual(replies[2].body, { received: true, duplicate_payment: true });
  assert.equal(replies[3].body.error, "checkout_amount_mismatch");
  assert.equal(replies[4].body.error, "checkout_currency_mismatch");
  assert.equal(state.updates.length, 1);
  assert.equal(state.updates[0].fields.plan_id, "standard150_lifetime");
  const granted = state.rows[0];
  assert.equal(evaluatePaidAccess({ rows: [granted], user }).ok, true);
  assert.equal(evaluateExtended500PaidAccess({ user, accessRows: [granted] }).ok, false);
});

test("pay: a paid session claiming the Extended 500 plan is refused before any Access read or write", async () => {
  for (const metadata of [{ plan_id: "extended500_lifetime" }, { plan_id: "extended500_lifetime", access_id: "access_ext500" }]) {
    const { state, replies } = await runWebhook([pending150], [paidEvent("cs_ext500", metadata)]);
    assert.equal(replies[0].status, 400);
    assert.equal(replies[0].body.error, "checkout_plan_mismatch");
    assert.equal(state.reads, 0);
    assert.equal(state.updates.length, 0);
  }
});

test("pay: a paid Standard 150 checkout still grants once when the customer also holds an Extended 500 row",
  { todo: red("Standard 150 webhook/checkout tolerating a coexisting extended500_lifetime Access row (today: 400 checkout_access_conflict after payment)") },
  async () => {
    const { state, replies } = await runWebhook([pending150, ext500Paid], [paidEvent("cs_first")]);
    assert.equal(replies[0].status, 200, JSON.stringify(replies[0].body));
    assert.equal(state.updates.length, 1);
  });

test("pay: an Extended 500 purchase path (dedicated price, checkout, verified webhook) exists",
  { todo: red("extended500_lifetime Stripe SKU, checkout and paid webhook") },
  () => {
    const functions = readdirSync("base44/functions").filter((name) => name !== "issueExtended500AdmissionV1");
    const sellers = functions.filter((name) => {
      const path = `base44/functions/${name}/entry.ts`;
      return existsSync(path) && /extended500_lifetime/.test(read(path)) && /Stripe/.test(read(path));
    });
    assert.ok(sellers.length > 0, "no Base44 function can sell or grant extended500_lifetime");
  });

// ---------------------------------------------------------------------------
// F: false success / 500-vs-150 evidence separation
// ---------------------------------------------------------------------------
const SECRET = "lane-e-handoff-secret-not-production";
const frozen500 = {
  scan_mode: "extended_500", owner_user_id: "owner_e", id: "scan_e", project_id: "project_e",
  request_id: "req_e", idempotency_key: "idem_e", normalized_domain: "example.com", attempt_count: 1,
};
async function handoff(pages) {
  const payload = {
    version: EXTENDED500_HANDOFF_VERSION,
    identity: { canonical_mode: "extended_500", owner_user_id: "owner_e", scan_id: "scan_e",
      project_id: "project_e", request_id: "req_e", idempotency_key: "idem_e",
      normalized_domain: "example.com", attempt_count: "1" },
    scan: { canonical_mode: "extended_500", scan_id: "scan_e", request_id: "req_e", idempotency_key: "idem_e",
      normalized_domain: "example.com", pages_found: pages.length, pages_crawled: pages.length,
      scan_coverage: { urls_attempted: pages.length, usable_html_pages: pages.length, unique_retained_destinations: pages.length },
      scanner_source_sha: "a".repeat(40), beta_revision_fingerprint: "b".repeat(16), pages },
    review: { review_status: "not_reviewed", pages_reviewed: 0, release_gate_eligible: false },
  };
  return { ...payload, proof: await createAuthoritySeal(payload, SECRET) };
}
const page = (i, extra = {}) => ({ url: `https://example.com/p${i}`, final_url: `https://example.com/p${i}`, status_code: 200, ...extra });

test("f: the 500 verifier only ever stages unreviewed evidence and refuses Standard 150 envelopes", async () => {
  const ok = await verifyExtended500EvidenceHandoff(await handoff([page(1), page(2)]), frozen500, SECRET);
  assert.deepEqual(ok, { valid: true, state: "unreviewed_evidence_only", pages_retained: 2 });
  const std150 = { version: "durable_standard150_completion_v1", identity: {}, scan: {}, review: {} };
  const signed150 = { ...std150, proof: await createAuthoritySeal(std150, SECRET) };
  assert.equal((await verifyExtended500EvidenceHandoff(signed150, frozen500, SECRET)).valid, false);
  for (const review of [
    { review_status: "reviewed", pages_reviewed: 0, release_gate_eligible: false },
    { review_status: "not_reviewed", pages_reviewed: 2, release_gate_eligible: false },
    { review_status: "not_reviewed", pages_reviewed: 0, release_gate_eligible: true },
  ]) {
    const { proof: _p, ...body } = await handoff([page(1)]);
    const forged = { ...body, review };
    const out = await verifyExtended500EvidenceHandoff({ ...forged, proof: await createAuthoritySeal(forged, SECRET) }, frozen500, SECRET);
    assert.deepEqual(out, { valid: false, reason: "premature_authority_claim" });
  }
  // Standard 150 persistence only accepts its own completion version (version gate + HMAC).
  const v8 = read("base44/functions/persistDurableScanAuthorityV8/entry.ts");
  assert.match(v8, /const COMPLETION_VERSION = "durable_standard150_completion_v1";/);
  assert.match(v8, /body\?\.version !== COMPLETION_VERSION \|\| !proof \|\| !await verifyAuthoritySeal/);
  assert.notEqual(EXTENDED500_HANDOFF_VERSION, "durable_standard150_completion_v1");
});

test("f: Standard 150 persistence refuses a completion for a frozen extended_500 ScanRun",
  { todo: red("frozen scan_mode check in persistDurableScanAuthorityV8 validateCurrentIdentity") },
  async () => {
    const v8 = read("base44/functions/persistDurableScanAuthorityV8/entry.ts");
    const { validateCurrentIdentity } = await importFunctions(v8,
      ["validateCurrentIdentity", "robotsPolicyMatches", "recordOwnedById", "normalizeDomain", "cleanText", "cleanId"],
      "class RequestProblem extends Error { constructor(status, code, message) { super(message); this.status = status; this.code = code; } }");
    const scan = { id: "scan_e", project_id: "project_e", owner_user_id: "owner_e", website_url: "https://example.com/",
      scan_mode: "extended_500", respect_robots_txt: true, owner_attested_robots_override: false };
    const project = { id: "project_e", owner_user_id: "owner_e", website_url: "https://example.com/" };
    const identity = { scan_id: "scan_e", project_id: "project_e", owner_user_id: "owner_e",
      normalized_domain: "example.com", request_id: "req_e", idempotency_key: "idem_e" };
    const scanResult = { scan_id: "scan_e", request_id: "req_e", idempotency_key: "idem_e",
      website_url: "https://example.com/", respect_robots_txt: true, owner_attested_robots_override: false };
    // Control: the extracted function is live code and does reject a real mismatch.
    assert.throws(() => validateCurrentIdentity({ scan, project, identity, scanResult: { ...scanResult, request_id: "x" } }));
    assert.throws(() => validateCurrentIdentity({ scan, project, identity, scanResult }),
      "Standard 150 persistence accepted a completion for an extended_500 ScanRun");
  });

test("p: the 500 verifier refuses signed pages carrying raw HTML or main text",
  { todo: red("receiving-side page privacy enforcement in verifyExtended500EvidenceHandoff") },
  async () => {
    for (const extra of [{ main_text: "private" }, { html: "<html>" }, { raw_html: "<html>" }, { _reachability_links: [] }]) {
      const out = await verifyExtended500EvidenceHandoff(await handoff([page(1, extra)]), frozen500, SECRET);
      assert.equal(out.valid, false, JSON.stringify(extra));
    }
  });

// ---------------------------------------------------------------------------
// ISS: Base44 issuer — disabled default, owner/paid mismatch, no false success
// ---------------------------------------------------------------------------
const CONFIG = {
  EXTENDED500_ISSUER_ENABLED: "true",
  EXTENDED500_COORDINATOR_URL: "https://extended500-coordinator.example",
  EXTENDED500_COORDINATOR_SIGNING_KEY: "lane-e-coordinator-aaaaaaaaaaaaaaaaaaaa",
  EXTENDED500_ENTITLEMENT_SIGNING_KEY: "lane-e-entitlement-bbbbbbbbbbbbbbbbbbb",
  EXTENDED500_ADMISSION_SIGNING_KEY: "lane-e-admission-cccccccccccccccccccccc",
};
const issuerScan = {
  id: "scan_e", owner_user_id: user.id, project_id: "project_e", request_id: "req_e",
  idempotency_key: "idem_e", attempt_count: 1, scan_mode: "extended_500", status: "queued",
  website_url: "https://example.com/", path_prefix: null, normalized_domain: "example.com",
  respect_robots_txt: true, owner_attested_robots_override: false,
};
function issuerCall({ ownerRows = [ext500Paid], emailRows = [ext500Paid], config = CONFIG, reply } = {}) {
  const fetches = [];
  const entities = {
    ScanRun: { async get() { return issuerScan; } },
    BusinessProject: { async get() { return { id: "project_e", owner_user_id: user.id, website_url: "https://example.com/" }; } },
    Access: { async filter(where) { return where.owner_user_id ? ownerRows : emailRows; } },
  };
  const fetchImpl = async (url, opts) => {
    fetches.push({ url, opts });
    const r = reply || { status: 202, body: { success: true, state: "dispatch_unknown", reserved: true, admitted: false, worker_execution_enabled: false } };
    return { status: r.status, async json() { return r.body; } };
  };
  return issueExtended500Admission({ body: { scan_id: "scan_e" }, user, entities,
    secret: (name) => config[name] || "", fetchImpl, nowMs: Date.parse("2026-10-29T12:00:00.000Z") })
    .then((result) => ({ result, fetches }));
}

test("iss: issuer enables only on exact 'true' and never reports success for non-confirmed reservations", async () => {
  for (const flag of ["TRUE", "True", "1", "yes", ""]) {
    const { result, fetches } = await issuerCall({ config: { ...CONFIG, EXTENDED500_ISSUER_ENABLED: flag } });
    assert.equal(result.payload.code, "extended500_issuer_disabled", flag);
    assert.equal(fetches.length, 0);
  }
  for (const reply of [
    { status: 409, body: { success: false, state: "terminal_replay", admitted: false } },
    { status: 409, body: { success: false, error: "owner_slot_busy" } },
    { status: 503, body: { success: false, error: "extended500_dispatch_not_ready" } },
    { status: 200, body: { success: true, state: "enqueued", reserved: true, admitted: true, worker_execution_enabled: false } },
    { status: 200, body: { success: true, state: "complete", reserved: true, admitted: false, worker_execution_enabled: false } },
  ]) {
    const { result } = await issuerCall({ reply });
    assert.equal(result.payload.success, false, JSON.stringify(reply));
    assert.equal(result.payload.code, "reservation_not_confirmed");
  }
  const { result } = await issuerCall();
  assert.equal(result.payload.admitted, false);
  const wire = JSON.stringify(result.payload);
  for (const secret of ["proof", "access_ext500", ...Object.values(CONFIG).slice(2)]) assert.equal(wire.includes(secret), false, secret);
});

test("own: a second Extended 500 row reachable by email (other owner) fails closed before the coordinator", async () => {
  const foreign = { ...ext500Paid, id: "access_foreign", owner_user_id: "someone_else" };
  for (const rows of [{ emailRows: [ext500Paid, foreign] }, { ownerRows: [], emailRows: [foreign] }, { ownerRows: [ext500Paid, { ...ext500Paid, id: "access_dup" }] }]) {
    const { result, fetches } = await issuerCall(rows);
    assert.equal(result.status, 403, JSON.stringify(rows));
    assert.equal(fetches.length, 0);
  }
});

test("iss: coordinator call is time-bounded (abort signal) so an unknown outcome is reported promptly",
  { todo: red("explicit timeout/AbortSignal on the issuer's coordinator fetch") },
  async () => {
    const { fetches } = await issuerCall();
    assert.equal(fetches.length, 1);
    assert.ok(fetches[0].opts.signal instanceof AbortSignal, "coordinator fetch has no timeout signal");
  });

test("iss: the deployed package policy is byte-identical to the independently tested src/lib policy", () => {
  const strip = (text) => text.split("\n").filter((line) => !line.startsWith("//") && !line.startsWith("import ")).join("\n");
  assert.equal(strip(read("base44/functions/issueExtended500AdmissionV1/issuer.js")), strip(read("src/lib/extended500EntitlementIssuer.js")));
  assert.equal(read("base44/functions/issueExtended500AdmissionV1/authoritySeal.js"), read("base44/functions/persistDurableScanAuthority/authoritySeal.js"));
});

test("reopen: a customer result reader can reopen a reviewed Extended 500 result",
  { todo: red("CUSTOMER_REOPENED: getCustomerScanResult support for reviewed extended_500 authority") },
  () => {
    const readers = readdirSync("base44/functions").filter((name) => /^getCustomerScanResult/.test(name));
    assert.ok(readers.length > 0);
    assert.ok(readers.some((name) => /extended_500/.test(read(`base44/functions/${name}/entry.ts`))),
      "no customer reader understands extended_500");
  });

// ---------------------------------------------------------------------------
// Owner-authored source-bound gates (commit fefe61a), kept verbatim in a block scope.
// ---------------------------------------------------------------------------
{
  const evaluateExtended500PaidAccess = evaluateSrcLibExtended500PaidAccess;
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
}
