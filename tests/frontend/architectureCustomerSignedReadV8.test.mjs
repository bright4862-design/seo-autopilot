import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

import { buildAuthoritySnapshot } from "../../base44/functions/persistDurableScanAuthorityV8/authoritySnapshot.js";
import { authorityRowsFromSnapshot } from "../../base44/functions/persistDurableScanAuthorityV8/authorityRows.js";
import { createAuthoritySeal } from "../../base44/functions/persistDurableScanAuthorityV8/authoritySeal.js";
import * as reader from "../../base44/functions/getCustomerScanResultV8/projection.js";
import * as limited from "../../base44/functions/getCustomerScanResultV8/limitedResultIntegrity.js";
import * as previews from "../../base44/functions/getCustomerScanResultV8/customerPreviewSeal.js";
import * as compatibility from "../../base44/functions/getCustomerScanResultV8/releaseCompatibility.js";
import { RELEASE_FINGERPRINT } from "../../base44/functions/getCustomerScanResultV8/generatedReleaseContract.js";
import { FUNCTION_BUILD_ID } from "../../base44/functions/getCustomerScanResultV8/generatedBuildId.js";

const APP = "6a498732ec779dfaaeab0e53";
const OWNER = "architecture_test_owner";
const PROJECT = "architecture_test_project";
const SCAN = "architecture_test_scan";
const SECRET = "architecture-roundtrip-test-key-not-a-runtime-secret";
const entrySource = readFileSync("base44/functions/getCustomerScanResultV8/entry.ts", "utf8");

function scannerFixture() {
  const stdout = execFileSync(
    "python", ["scanner-api/scripts/architecture_customer_contract_fixture.py"],
    { encoding: "utf8", cwd: process.cwd(),
      env: { ...process.env, PYTHONPATH: ["scanner-api", process.env.PYTHONPATH].filter(Boolean).join(":") } },
  );
  return JSON.parse(stdout.trim());
}

function recordMatches(record, query = {}) {
  return Object.entries(query).every(([key, value]) => record?.[key] === value);
}

async function signedRows(fixture) {
  const review = {
    ...fixture.review,
    archetype_classifier_version: "archetype_classifier_v10_structural_finance_member_retail",
    review_version: "python_review_v2_structural_marketplace",
    review_evidence_calibration_version: "review_evidence_calibration_v6_health_score_v2",
    ai_review_backend: "python_review_api",
    python_review_fallback_used: false,
    release_gate_eligible: true,
    score_is_provisional: false,
    evidence_quality_blocking: false,
    beta_revision_fingerprint: RELEASE_FINGERPRINT,
    scan_status: "complete",
    health_score: 77,
    health_grade: "Good",
  };
  const scan = {
    website_url: "https://example.com/",
    scanner_version: "python_scanner_v5_observed_finding_identity",
    scanner_build_revision: "authenticated_health_probe_v1",
    scanner_wrapper_version: "runStandard150Scan_v1_python_required",
    advanced_scan_backend: "python_scanner_api",
    deno_fallback_used: false,
    beta_revision_fingerprint: RELEASE_FINGERPRINT,
    pages_found: 2,
    pages_crawled: 2,
  };
  const snapshot = buildAuthoritySnapshot({
    scan, review, identity: {
      scan_id: SCAN, project_id: PROJECT, normalized_domain: "example.com",
      owner_user_id: OWNER,
    },
    userId: OWNER, now: "2026-10-30T18:30:00.000Z",
  });
  assert.equal(snapshot.fix_list.repair_snapshot_contract_complete, true);
  const proof = await createAuthoritySeal(snapshot, SECRET);
  const rows = authorityRowsFromSnapshot(snapshot, {
    fixListId: "architecture_test_fixlist", ownerUserId: OWNER, proof,
  });
  return {
    snapshot,
    run: { id: SCAN, project_id: PROJECT, owner_user_id: OWNER, ...rows.scanRun },
    fixList: { id: "architecture_test_fixlist", ...rows.fixList },
    fixItems: rows.fixItems.map((item, index) => ({ id: `persisted_test_${index}`, ...item })).reverse(),
  };
}

let invocation = 0;
async function invokeV8(fixture, {
  signedMutation = () => {}, signedIn = true, caller = OWNER,
  paid = true, key = SECRET,
} = {}) {
  const state = await signedRows(fixture);
  signedMutation(state);
  const paidAccess = {
    id: "test_access", owner_user_id: OWNER,
    user_email: "architecture-test@example.com",
    access_status: "active", has_full_access: true,
    app_id: APP, plan_id: "standard150_lifetime",
    grant_source: "manual_grant", granted_at: "2026-10-30T17:30:00.000Z",
  };
  const mock = {
    auth: { me: async () => signedIn ? {
      id: caller, email: "architecture-test@example.com",
    } : null },
    asServiceRole: { entities: {
      ScanRun: { get: async (id) => id === SCAN ? structuredClone(state.run) : null },
      BusinessProject: { get: async (id) => id === PROJECT
        ? { id: PROJECT, owner_user_id: OWNER, website_url: "https://example.com/" } : null },
      Access: { filter: async (query) => paid && recordMatches(paidAccess, query)
        ? [structuredClone(paidAccess)] : [] },
      FixList: {
        get: async (id) => id === state.fixList.id ? structuredClone(state.fixList) : null,
        filter: async () => [structuredClone(state.fixList)],
      },
      FixItem: { filter: async () => structuredClone(state.fixItems) },
    } },
  };
  const name = `__architectureSignedReadHarness_${++invocation}`;
  let handler;
  const previousDeno = globalThis.Deno;
  const js = ts.transpileModule(entrySource, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  }).outputText.replace(/^import[\s\S]*?;\s*$/gm, "");
  globalThis.Deno = { env: { get: () => "" }, serve: (value) => { handler = value; } };
  globalThis[name] = {
    createClientFromRequest: () => mock,
    secrets: { get: (keyName) => keyName === "SCAN_EVIDENCE_SIGNING_KEY" ? key : "" },
    ...reader, ...limited, ...previews, ...compatibility,
    RELEASE_FINGERPRINT, FUNCTION_BUILD_ID,
    // The comparison branch is not exercised in this test.
    validComparisonRequest: () => false,
    unavailableScanComparison: () => ({}),
    readCustomerScanComparison: () => ({}),
    requestScanComparison: () => ({}),
  };
  try {
    const prelude = `const { ${Object.keys(globalThis[name]).join(",")} } = globalThis.${name};`;
    await import(`data:text/javascript;base64,${Buffer.from(`${prelude}\n${js}\n// harness:${name}`).toString("base64")}`);
    assert.equal(typeof handler, "function", "actual V8 entry did not bind a handler");
    const response = await handler(new Request("https://function.example", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ action: "get", scan_id: SCAN }),
    }));
    return { status: response.status, body: await response.json(), state };
  } finally {
    delete globalThis[name];
    if (previousDeno === undefined) delete globalThis.Deno;
    else globalThis.Deno = previousDeno;
  }
}

const fixture = scannerFixture();
test("Python canonical repair producer yields two structurally ranked repairs", () => {
  assert.deepEqual(fixture.expected_ids, ["hub_canonical", "leaf_canonical"]);
  assert.ok(fixture.expected_scores[0] > fixture.expected_scores[1]);
  assert.equal(fixture.expected_architecture_versions.length, 2);
});

test("actual V8 reader authenticates owner, verifies persisted HMAC and preserves Python action order", async () => {
  const { status, body, state } = await invokeV8(fixture);
  assert.equal(status, 200, JSON.stringify(body));
  assert.equal(body.success, true);
  assert.equal(body.authority_verified, true);
  assert.deepEqual(body.fixItems.map((item) => item.fix_id), fixture.expected_ids);
  assert.deepEqual(body.fixItems.map((item) => item.action_priority_score), fixture.expected_scores);
  assert.deepEqual(body.fixItems.map((item) => item.canonical_action_rank), [1, 2]);
  assert.equal(body.fixList?.repair_snapshot_contract_complete, true);
  assert.deepEqual(state.fixList.canonical_action_fix_ids, fixture.expected_ids);
  const reconstructed = reader.authoritySnapshotFromRows({
    run: state.run, fixList: state.fixList, fixItems: state.fixItems, userId: OWNER,
  });
  assert.deepEqual(reconstructed, state.snapshot);
  assert.equal(await reader.verifyAuthoritySeal(reconstructed, SECRET, state.run.authority_proof), true);
});

for (const [label, options, status, code] of [
  ["unauthenticated request", { signedIn: false }, 401, "unauthorized"],
  ["wrong owner", { caller: "unrelated_owner" }, 404, "scan_not_found"],
  ["wrong authority key", { key: "wrong-test-secret" }, 409, "result_authority_invalid"],
  ["modified persisted score", {
    signedMutation: (x) => { x.fixItems[0].action_priority_score += 15; },
  }, 409, "result_authority_invalid"],
  ["modified priority reason", {
    signedMutation: (x) => { x.fixItems[0].priority_reason = "Changed outside seal"; },
  }, 409, "result_authority_invalid"],
  ["modified canonical rank", {
    signedMutation: (x) => { x.fixItems[0].canonical_action_rank = 3; },
  }, 409, "result_authority_invalid"],
  ["modified FixList ordering", {
    signedMutation: (x) => { x.fixList.canonical_action_fix_ids.reverse(); },
  }, 409, "result_authority_invalid"],
]) {
  test(`V8 signed customer read rejects ${label}`, async () => {
    const { status: actual, body } = await invokeV8(fixture, options);
    assert.equal(actual, status, JSON.stringify(body));
    assert.equal(body.success, false);
    assert.equal(body.error_code, code);
    assert.equal(body.fixItems, undefined);
  });
}

test("unpaid owner sees only the bounded two-fix preview, never signed full repair details", async () => {
  const { status, body } = await invokeV8(fixture, { paid: false });
  assert.equal(status, 200, JSON.stringify(body));
  assert.ok(body.fixItems.length <= 2);
  assert.ok(body.fixItems.length > 0);
  for (const item of body.fixItems) {
    assert.equal(item.action_priority_score, undefined);
    assert.equal(item.priority_reason, undefined);
    assert.equal(item.affected_pages, undefined);
    assert.equal(item.priority_context, undefined);
    assert.equal(item.canonical_action_rank, undefined);
    assert.equal(item.repair_fingerprint, undefined);
    assert.equal(item.repair_identity_version, undefined);
  }
});

test("existing signed contract drops unsanctioned architecture evidence instead of publishing it", async () => {
  const { state, body, status } = await invokeV8(fixture);
  assert.equal(status, 200);
  assert.ok(fixture.review.canonical_repairs[0].priority_context.architecture_role_counts);
  assert.equal(state.fixItems[0].priority_context.architecture_role_counts, undefined);
  assert.equal(body.fixItems[0].priority_context?.architecture_role_counts, undefined);
  // Follow-up: only a new versioned, writer/reader-paired signed contract may
  // expose these fields. Their absence is a blocked release gate, not a pass.
});
