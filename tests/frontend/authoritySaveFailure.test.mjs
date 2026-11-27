import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";
import ts from "typescript";

const secret = "offline-synthetic-save-key";
const scan = {
  id: "fixture-scan", project_id: "fixture-project", owner_user_id: "fixture-owner",
  request_id: "fixture-request", idempotency_key: "fixture-request", website_url: "https://fixture.test",
  respect_robots_txt: true, owner_attested_robots_override: false, status: "reviewing",
  started_at: "2026-01-01T00:00:00.000Z", attempt_count: 1,
};

function writer(version) {
  const entry = new URL(`../../base44/functions/persistDurableScanAuthorityV${version}/entry.ts`, import.meta.url);
  const load = createRequire(entry);
  const source = ts.transpileModule(readFileSync(entry, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const snapshot = load("./authoritySnapshot.js");
  const simulateSdkError = () => {
    throw Object.assign(new Error("fixture-private-contents"), { status: 413, name: "fixture-private-name" });
  };
  const entities = {
    ScanRun: { get: async () => scan },
    BusinessProject: { get: async () => scan },
    FixList: { filter: async () => [], create: simulateSdkError },
  };
  const dependencies = {
    "npm:@base44/sdk@0.8.40": { createClientFromRequest: () => ({ asServiceRole: { entities } }) },
    "base44:runtime": { secrets: { get: () => secret } },
    "./authoritySnapshot.js": {
      ...snapshot,
      firstFailedAuthorityPredicate: () => "",
      hasCompleteAcceptanceEvidence: () => true,
      buildAuthoritySnapshot: options => options.review.stage3_authority_claim
        ? snapshot.buildAuthoritySnapshot(options) : {},
    },
    "./authorityRows.js": { authorityRowsFromSnapshot: () => ({ fixList: {} }) },
  };
  const logs = [];
  let handler;
  new Function("exports", "require", "Deno", "console", source)(
    {}, key => dependencies[key] ?? load(key), { serve: fn => { handler = fn; } },
    { error: (...fields) => logs.push(fields) },
  );
  return {
    logs,
    async post(review, validProof = true) {
      const identity = { ...scan, scan_id: scan.id, normalized_domain: "fixture.test" };
      const document = {
        version: "durable_standard150_completion_v1", identity, review,
        scan: { ...scan, scan_id: scan.id, normalized_domain: "fixture.test", pages_crawled: 150 },
      };
      const proof = validProof ? await load("./authoritySeal.js").createAuthoritySeal(document, secret) : "0".repeat(64);
      const response = await handler(new Request("https://fixture.test/writer", {
        method: "POST", headers: { "X-FixList-Worker": "scan_job_worker_v1_cloud_tasks" },
        body: JSON.stringify({ ...document, proof }),
      }));
      return { status: response.status, body: await response.json() };
    },
  };
}

for (const version of [8, 9]) {
  test(`V${version} distinguishes a snapshot rejection from an SDK write failure without leaking either exception`, async () => {
    const fixture = writer(version);
    for (const review of [{ stage3_authority_claim: { scan_id: "fixture-private-claim" } }, {}]) {
      assert.deepEqual(await fixture.post(review), {
        status: 500,
        body: { success: false, error_code: "durable_authority_failed", error: "The durable scan authority could not be saved." },
      });
    }
    assert.equal((await fixture.post({}, false)).status, 409);
    assert.deepEqual(fixture.logs, [
      ["persistDurableScanAuthority failed", JSON.stringify({ stage: "build_snapshot", failure_type: "stage3_delivery" })],
      ["persistDurableScanAuthority failed", JSON.stringify({ stage: "upsert_fix_list", failure_type: "upstream_http", upstream_status: 413 })],
    ]);
  });
}
