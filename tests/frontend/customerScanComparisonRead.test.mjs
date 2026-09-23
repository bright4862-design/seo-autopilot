import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";
import * as projection from "../../base44/functions/getCustomerScanResultV8/projection.js";
import * as limited from "../../base44/functions/getCustomerScanResultV8/limitedResultIntegrity.js";
import * as preview from "../../base44/functions/getCustomerScanResultV8/customerPreviewSeal.js";
import * as compatibility from "../../base44/functions/getCustomerScanResultV8/releaseCompatibility.js";
import * as comparisonReader from "../../base44/functions/getCustomerScanResultV8/comparisonReader.js";
import { requestScanComparison } from "../../base44/functions/getCustomerScanResultV8/comparisonGateway.js";
import { RELEASE_FINGERPRINT } from "../../base44/functions/getCustomerScanResultV8/generatedReleaseContract.js";
import { FUNCTION_BUILD_ID } from "../../base44/functions/getCustomerScanResultV8/generatedBuildId.js";

const SECRET = " comparison-test-key-with-spaces ";
const NOW = Date.parse("2026-09-23T12:00:00Z");
const entrySource = readFileSync("base44/functions/getCustomerScanResultV8/entry.ts", "utf8");
let sequence = 0;

function sign(domain, text) {
  const derived = createHmac("sha256", SECRET).update(domain).digest();
  return createHmac("sha256", derived).update(text).digest("hex");
}

function presentation() {
  return {
    version: "scan_comparison_presentation_v1", previous_scan_id: "previous", current_scan_id: "current",
    headline: "What changed since the previous scan", score_line: "Health score changed from 75 to 72.",
    sample_line: "The assessed sample was 126 pages before and 139 pages now.",
    score_caution: "The sample changed; the score difference alone does not prove improvement or regression.",
    counts: { fixed: 0, still_detected: 0, new_or_came_back: 0, came_back: 0, could_not_verify: 0 },
    new_or_came_back_label: "New or returned candidate", new_or_came_back_is_verified_claim: false,
    score_direction_claim_allowed: false, overall_improvement_or_regression_claim: null,
  };
}

function responseFor(request, mutate = () => {}, { tamper = false } = {}) {
  const payload = {
    version: "scan_comparison_response_v1", nonce: request.nonce,
    current_scan_id: request.expected_current_scan_id, previous_scan_id: request.current_previous_scan_id,
    presentation: presentation(), source_sha: "a".repeat(40), generated_at: NOW / 1_000,
  };
  mutate(payload);
  const proof = sign("fixlist-scan-comparison-response-v1", projection.stableSerialize(payload));
  if (tamper) payload.presentation.counts.fixed = 1;
  return Response.json({ payload, proof });
}

async function sealedRows(id, time) {
  const run = {
    id, project_id: "project", owner_user_id: "owner", website_url: "https://example.com/",
    normalized_domain: "example.com", status: "complete", release_gate_eligible: true,
    score_is_provisional: false, evidence_quality_blocking: false,
    authority_seal_version: "standard_review_snapshot_hmac_v6_report_evidence",
    authority_sealed_at: time, completed_at: time, beta_revision_fingerprint: RELEASE_FINGERPRINT,
    fix_list_id: `list-${id}`, pages_crawled: 139, health_score: 72,
  };
  const fixList = {
    id: run.fix_list_id, scan_run_id: id, project_id: "project", owner_user_id: "owner",
    website_url: run.website_url, is_authoritative: true, score_is_provisional: false,
    total_fixes: 0, health_score: 72,
  };
  const snapshot = projection.authoritySnapshotFromRows({ run, fixList, fixItems: [], userId: "owner" });
  const proof = await projection.createAuthoritySeal(snapshot, SECRET);
  run.authority_proof = proof;
  fixList.authority_proof = proof;
  return { run, fixList, snapshot, proof };
}

async function fixture() {
  const previous = await sealedRows("previous", "2026-09-23T09:00:00Z");
  const current = await sealedRows("current", "2026-09-23T10:00:00Z");
  current.run.previous_scan_id = "previous";
  return { previous, current, paid: true, project: { id: "project", owner_user_id: "owner", website_url: "https://example.com/" } };
}

async function invoke({ mutate = () => {}, body = { action: "compare", scan_id: "current" }, gateway = responseFor,
  gatewayUrl = "https://gateway.example", signingKey = SECRET, deadlineMs = 8_000 } = {}) {
  const rows = await fixture();
  await mutate(rows);
  const reads = [];
  const requests = [];
  const access = { id: "access", owner_user_id: "owner", user_email: "paid@example.com", access_status: "active", has_full_access: true,
    plan_id: "standard150_lifetime", grant_source: "manual_grant", app_id: "6a498732ec779dfaaeab0e53", granted_at: "2026-09-22T09:00:00Z" };
  const entities = {
    ScanRun: { get: async (id) => { reads.push(id); return [rows.current.run, rows.previous.run].find((row) => row.id === id) || null; } },
    BusinessProject: { get: async () => rows.project },
    Access: { filter: async () => rows.paid ? [access] : [] },
    FixList: { get: async (id) => [rows.current.fixList, rows.previous.fixList].find((row) => row.id === id) || null },
    FixItem: { filter: async () => [] },
  };
  const harness = {
    ...projection, ...limited, ...preview, ...compatibility, ...comparisonReader,
    RELEASE_FINGERPRINT, FUNCTION_BUILD_ID,
    createClientFromRequest: () => ({ auth: { me: async () => ({ id: "owner", email: "paid@example.com" }) }, asServiceRole: { entities } }),
    secrets: { get: () => signingKey },
    requestScanComparison: (args) => requestScanComparison({ ...args, now: () => NOW, deadlineMs, fetchImpl: async (url, init) => {
      assert.equal(url, "https://gateway.example/compare");
      assert.equal(init.redirect, "error");
      assert.equal(init.headers["x-fixlist-signature"], sign("fixlist-scan-comparison-request-v1", `${init.headers["x-fixlist-timestamp"]}\n${init.body}`));
      const payload = JSON.parse(init.body);
      requests.push(payload);
      return gateway(payload);
    } }),
  };
  const name = `__comparisonReaderHarness${++sequence}`;
  const javascript = ts.transpileModule(entrySource, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText.replace(/^import[\s\S]*?;\s*$/gm, "");
  let handler;
  const previousDeno = globalThis.Deno;
  globalThis.Deno = { env: { get: () => gatewayUrl }, serve: (value) => { handler = value; } };
  globalThis[name] = harness;
  try {
    const source = `const { ${Object.keys(harness).join(",")} } = globalThis.${name};\n${javascript}\n// ${name}`;
    await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
    const response = await handler(new Request("https://reader.example", { method: "POST", body: JSON.stringify(body) }));
    return { status: response.status, result: await response.json(), requests, reads, rows };
  } finally {
    delete globalThis[name];
    if (previousDeno === undefined) delete globalThis.Deno;
    else globalThis.Deno = previousDeno;
  }
}

test("actual V8 compare handler verifies both sealed row sets and returns only the signed presentation", async () => {
  const { result, requests } = await invoke();
  assert.equal(result.comparison_verified, true);
  assert.equal(result.comparison_status, "ready");
  assert.equal(result.support_reference, undefined);
  assert.equal(result.comparison.new_or_came_back_label, "Unmatched or returned findings");
  assert.deepEqual(Object.keys(result).sort(), ["comparison", "comparison_status", "comparison_verified", "scan_id", "success"]);
  assert.equal(requests.length, 1);
  assert.equal(requests[0].expected_owner_user_id, "owner");
  assert.equal(requests[0].current_previous_scan_id, "previous");
  assert.equal(requests[0].previous_snapshot.scan_id, "previous");
  assert.equal(requests[0].current_snapshot.scan_id, "current");
});

for (const key of ["previous_scan_id", "previous_proof", "previous_snapshot", "owner_user_id", "scan_run_id"]) {
  test(`compare rejects customer-supplied ${key} before reading rows`, async () => {
    const { status, result, reads, requests } = await invoke({ body: { action: "compare", scan_id: "current", [key]: "spoofed" } });
    assert.equal(status, 400);
    assert.equal(result.error_code, "comparison_request_invalid");
    assert.deepEqual(reads, []);
    assert.deepEqual(requests, []);
  });
}

for (const [label, mutate, forbiddenPriorRead, reference = "CMP-PREVIOUS"] of [
  ["unpaid owner", (rows) => { rows.paid = false; }, true, "CMP-ACCESS"],
  ["limited current scan", (rows) => { rows.current.run.status = "limited"; }, true, "CMP-CURRENT"],
  ["running current scan", (rows) => { rows.current.run.status = "crawling"; }, true, "CMP-CURRENT"],
  ["legacy current owner", (rows) => { delete rows.current.run.owner_user_id; rows.current.run.created_by_id = "owner"; }, true, "CMP-ACCESS"],
  ["prior does not exist", (rows) => { rows.previous.run.id = "missing"; }],
  ["prior owned by another account", (rows) => { rows.previous.run.owner_user_id = "other"; }],
  ["prior from another project", (rows) => { rows.previous.run.project_id = "other"; }],
  ["prior limited", (rows) => { rows.previous.run.status = "limited"; }],
  ["corrupt current HMAC", (rows) => { rows.current.run.health_score = 99; }, true, "CMP-CURRENT"],
  ["corrupt prior HMAC", (rows) => { rows.previous.run.health_score = 99; }],
  ["unreadable prior release", (rows) => { rows.previous.run.beta_revision_fingerprint = "d".repeat(16); }],
  ["prior project URL differs", (rows) => { rows.previous.run.website_url = "https://other.example/"; }],
  ["invalid server pointer", (rows) => { rows.current.run.previous_scan_id = { id: "previous" }; }, true],
  ["invalid falsy server pointer", (rows) => { rows.current.run.previous_scan_id = 0; }, true],
]) {
  test(`compare remains unavailable for ${label}`, async () => {
    const { result, requests, reads } = await invoke({ mutate });
    assert.deepEqual(result, { success: true, scan_id: "current", comparison_verified: false, comparison_status: "unavailable", support_reference: reference });
    assert.deepEqual(requests, []);
    if (forbiddenPriorRead) assert.deepEqual(reads, ["current"]);
  });
}

for (const [label, mutate] of [
  ["different signed origin", (row) => { row.run.website_url = "https://www.example.com/"; row.fixList.website_url = row.run.website_url; }],
  ["different signed path scope", (row) => { Object.assign(row.run, { scope_type: "path_prefix", requested_path_prefix: "/shop/", user_confirmed: true }); }],
  ["later prior seal", (row) => { row.run.authority_sealed_at = "2026-09-23T11:00:00Z"; row.run.completed_at = row.run.authority_sealed_at; }],
]) {
  test(`signed prior snapshot with ${label} cannot be compared`, async () => {
    const { result, requests } = await invoke({ mutate: async (rows) => {
      mutate(rows.previous);
      const snapshot = projection.authoritySnapshotFromRows({ run: rows.previous.run, fixList: rows.previous.fixList, fixItems: [], userId: "owner" });
      const proof = await projection.createAuthoritySeal(snapshot, SECRET);
      rows.previous.run.authority_proof = proof;
      rows.previous.fixList.authority_proof = proof;
    } });
    assert.equal(result.comparison_status, "unavailable");
    assert.equal(result.support_reference, "CMP-SCOPE");
    assert.deepEqual(requests, []);
  });
}

test("first authoritative scan reports no previous scan without calling the gateway", async () => {
  const { result, requests } = await invoke({ mutate: (rows) => { delete rows.current.run.previous_scan_id; } });
  assert.equal(result.comparison_status, "no_previous_scan");
  assert.equal(result.support_reference, undefined);
  assert.equal(result.comparison_verified, false);
  assert.deepEqual(requests, []);
});

test("comparison failures do not affect the normal saved-result read", async () => {
  const { result, requests } = await invoke({ body: { action: "get", scan_id: "current" }, gateway: () => { throw new Error("offline"); } });
  assert.equal(result.authority_verified, true);
  assert.equal(result.success, true);
  assert.deepEqual(requests, []);
});

for (const [label, gateway] of [
  ["malformed JSON", () => new Response("{private-invalid-json")],
  ["wrong nonce", (request) => responseFor(request, (payload) => { payload.nonce = "0".repeat(32); })],
  ["stale response", (request) => responseFor(request, (payload) => { payload.generated_at -= 301; })],
  ["future response", (request) => responseFor(request, (payload) => { payload.generated_at += 301; })],
  ["wrong current scan", (request) => responseFor(request, (payload) => { payload.current_scan_id = "another"; })],
  ["wrong previous scan", (request) => responseFor(request, (payload) => { payload.previous_scan_id = "another"; })],
  ["invalid source SHA", (request) => responseFor(request, (payload) => { payload.source_sha = "unknown"; })],
  ["tampered proof", (request) => responseFor(request, undefined, { tamper: true })],
  ["extra private presentation data", (request) => responseFor(request, (payload) => { payload.presentation.previous_proof = "private"; })],
  ["directional score claim", (request) => responseFor(request, (payload) => { payload.presentation.score_line = "SEO got worse by 3 points."; })],
  ["inconsistent counts", (request) => responseFor(request, (payload) => { payload.presentation.counts.came_back = 1; })],
  ["oversized chunked response", () => new Response("x".repeat(65_537))],
  ["oversized declared response", () => new Response("{}", { headers: { "content-length": "65537" } })],
]) {
  test(`compare fails closed on ${label}`, async () => {
    const { result } = await invoke({ gateway });
    assert.equal(result.comparison_status, "unavailable");
    assert.equal(result.comparison_verified, false);
    assert.equal(result.comparison, undefined);
    assert.equal(result.support_reference, "CMP-RESPONSE");
  });
}

test("the comparison request is bounded before network I/O", async () => {
  let calls = 0;
  await assert.rejects(requestScanComparison({
    gatewayUrl: "https://gateway.example", signingKey: SECRET,
    pair: { expected_owner_user_id: "owner", expected_project_id: "project", expected_current_scan_id: "current",
      current_previous_scan_id: "previous", previous_snapshot: { large: "x".repeat(4_100_000) }, previous_proof: "a".repeat(64),
      current_snapshot: {}, current_proof: "b".repeat(64) },
    fetchImpl: async () => { calls += 1; return new Response(); },
  }), (error) => error.support_reference === "CMP-GATEWAY-LIMIT");
  assert.equal(calls, 0);
});

test("comparison transport aborts an unresponsive gateway at its deadline", async () => {
  const rows = await fixture();
  let aborted = false;
  await assert.rejects(requestScanComparison({
    gatewayUrl: "https://gateway.example", signingKey: SECRET, deadlineMs: 5,
    pair: { expected_owner_user_id: "owner", expected_project_id: "project", expected_current_scan_id: "current",
      current_previous_scan_id: "previous", previous_snapshot: rows.previous.snapshot, previous_proof: rows.previous.proof,
      current_snapshot: rows.current.snapshot, current_proof: rows.current.proof },
    fetchImpl: (_url, init) => new Promise((_resolve, reject) => {
      init.signal.addEventListener("abort", () => { aborted = true; reject(new Error("deadline")); }, { once: true });
    }),
  }), (error) => error.support_reference === "CMP-TIMEOUT" && !error.message.includes("deadline"));
  assert.equal(aborted, true);
});


for (const [status, expected] of [
  [401, "CMP-GATEWAY-AUTH"], [403, "CMP-GATEWAY-AUTH"], [404, "CMP-GATEWAY-ROUTE"],
  [413, "CMP-GATEWAY-LIMIT"], [422, "CMP-GATEWAY-INPUT"], [429, "CMP-GATEWAY-BUSY"],
  [500, "CMP-GATEWAY-ERROR"], [503, "CMP-GATEWAY-ERROR"],
]) {
  test(`unavailable gateway HTTP ${status} has a bounded support reference without reflecting its body`, async () => {
    const { result } = await invoke({ gateway: () => new Response("private-response-with-proof-and-url", { status }) });
    assert.equal(result.support_reference, expected);
    assert.equal(result.comparison_verified, false);
    assert.equal(result.comparison_status, "unavailable");
    assert.equal(JSON.stringify(result).includes("private-response"), false);
  });
}

for (const gatewayUrl of ["", "not a URL", "http://gateway.example", "https://gateway.example/dispatch", "https://gateway.example/?private=1"]) {
  test(`unusable gateway configuration is classified before network I/O: ${gatewayUrl}`, async () => {
    const { result, requests } = await invoke({ gatewayUrl });
    assert.equal(result.support_reference, "CMP-CONFIG");
    assert.deepEqual(requests, []);
  });
}

for (const thrown of [new Error("private-key-and-url"), "private-string", null, { support_reference: "CMP-CONFIG", message: "private-object" }]) {
  test("unknown network throwables cannot select or leak a support reference", async () => {
    const { result } = await invoke({ gateway: () => { throw thrown; } });
    assert.equal(result.support_reference, "CMP-NETWORK");
    assert.equal(JSON.stringify(result).includes("private"), false);
  });
}


function transportPair(rows) {
  return {
    expected_owner_user_id: "owner", expected_project_id: "project", expected_current_scan_id: "current",
    current_previous_scan_id: "previous", previous_snapshot: rows.previous.snapshot, previous_proof: rows.previous.proof,
    current_snapshot: rows.current.snapshot, current_proof: rows.current.proof,
  };
}

test("missing transport key is a configuration failure before network I/O", async () => {
  const rows = await fixture();
  let calls = 0;
  await assert.rejects(requestScanComparison({
    gatewayUrl: "https://gateway.example", signingKey: "", pair: transportPair(rows),
    fetchImpl: async () => { calls += 1; return new Response(); },
  }), (error) => error.support_reference === "CMP-CONFIG");
  assert.equal(calls, 0);
});

test("invalid transport input has a fixed reference and no original serialization exception", async () => {
  const rows = await fixture();
  const circular = transportPair(rows);
  circular.current_snapshot.circular = circular.current_snapshot;
  for (const pair of [{ private: "private-pair" }, circular]) {
    let calls = 0;
    await assert.rejects(requestScanComparison({
      gatewayUrl: "https://gateway.example", signingKey: SECRET, pair,
      fetchImpl: async () => { calls += 1; return new Response(); },
    }), (error) => error.support_reference === "CMP-GATEWAY-INPUT" && !error.message.includes("private") && error.cause === undefined);
    assert.equal(calls, 0);
  }
});

for (const [stage, reference] of [["current", "CMP-CURRENT"], ["prior-load", "CMP-PREVIOUS"], ["prior-verify", "CMP-PREVIOUS"], ["gateway", "CMP-GATEWAY-ERROR"]]) {
  test(`unknown throwables at ${stage} cannot leak or change the reader's bounded failure stage`, async () => {
    const rows = await fixture();
    const throwable = { message: "private-exception", support_reference: "CMP-CONFIG", snapshot: { proof: "private-proof" } };
    const result = await comparisonReader.readCustomerScanComparison({
      run: rows.current.run, user: { id: "owner" }, project: rows.project, access: { ok: true },
      loadRun: async () => { if (stage === "prior-load") throw throwable; return rows.previous.run; },
      readVerifiedSnapshot: async (run) => {
        if ((stage === "current" && run.id === "current") || (stage === "prior-verify" && run.id === "previous")) throw throwable;
        return run.id === "current" ? rows.current : rows.previous;
      },
      requestComparison: async () => { throw throwable; },
    });
    assert.deepEqual(result, { success: true, scan_id: "current", comparison_verified: false,
      comparison_status: "unavailable", support_reference: reference });
  });
}

test("unknown support reference values are never reflected", () => {
  const result = comparisonReader.unavailableScanComparison("current", "private-untrusted-value");
  assert.equal(result.support_reference, "CMP-CURRENT");
  assert.equal(JSON.stringify(result).includes("private"), false);
});
