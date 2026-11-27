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

function writer(version, fault = "create") {
  const entry = new URL(`../../base44/functions/persistDurableScanAuthorityV${version}/entry.ts`, import.meta.url);
  const load = createRequire(entry);
  const source = ts.transpileModule(readFileSync(entry, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const { AUTHORITY_CONTRACT } = load("./authoritySnapshot.js");
  const { RELEASE_COMPONENT_VERSIONS } = load("./generatedReleaseContract.js");
  const seal = load("./authoritySeal.js");
  const fixLists = [];
  const calls = [];
  function storageCall(operation) {
    calls.push(operation);
    if (operation === fault) {
      throw Object.assign(new Error("fixture-private-contents"), { status: 413, name: "fixture-private-name" });
    }
  }
  const entities = {
    ScanRun: { get: async () => scan },
    BusinessProject: { get: async () => scan },
    FixList: {
      filter: async () => { storageCall("filter"); return fixLists; },
      create: async row => { storageCall("create"); fixLists.push(row); return row; },
    },
  };
  const dependencies = {
    "npm:@base44/sdk@0.8.40": { createClientFromRequest: () => ({ asServiceRole: { entities } }) },
    "base44:runtime": { secrets: { get: () => secret } },
  };
  if (fault === "sign") {
    dependencies["./authoritySeal.js"] = {
      ...seal, createAuthoritySeal: () => { throw new TypeError("fixture-private-key-details"); },
    };
  }
  const logs = [];
  let handler;
  new Function("exports", "require", "Deno", "console", source)(
    {}, key => dependencies[key] ?? load(key), { serve: fn => { handler = fn; } },
    { error: (...fields) => logs.push(fields) },
  );
  return {
    logs, calls, fixLists,
    async post(review = {}, validProof = true) {
      const identity = { ...scan, scan_id: scan.id, normalized_domain: "fixture.test" };
      const document = {
        version: "durable_standard150_completion_v1", identity,
        scan: {
          ...scan, scan_id: scan.id, normalized_domain: "fixture.test", pages_crawled: 150,
          scanner_version: AUTHORITY_CONTRACT.scanner_version, scanner_build_revision: AUTHORITY_CONTRACT.scanner_build_revision,
          beta_revision_fingerprint: AUTHORITY_CONTRACT.beta_revision_fingerprint, advanced_scan_backend: "python_scanner_api",
          metadata_evidence_version: "metadata_v1", title_evidence_version: "title_v1", worker_peak_memory_bytes: 1_000_000,
        },
        review: {
          ...AUTHORITY_CONTRACT, release_gate_eligible: true, score_is_provisional: false, evidence_quality_blocking: false,
          ai_review_backend: "python_review_api", python_review_fallback_used: false,
          site_fingerprint: { coverage_assessment: { state: "sufficient", coverage_authority_version: "coverage_v1" } },
          coverage_authority_evidence: { assessment: "sufficient", coverage_authority_evidence_version: "coverage_v1" },
          classification_integrity: {
            version: RELEASE_COMPONENT_VERSIONS.acceptance_evidence_version,
            state: "classified", verdict: "classified", classifier_version: AUTHORITY_CONTRACT.archetype_classifier_version,
            evidence_sufficiency: "sufficient", usable_pages: 150, complete_small_site_inventory: false,
          },
          ...review,
        },
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

const genericFailure = {
  status: 500,
  body: { success: false, error_code: "durable_authority_failed", error: "The durable scan authority could not be saved." },
};

for (const version of [8, 9]) {
  for (const [operation, stage, expectedCalls] of [
    ["filter", "lookup_fix_list", ["filter"]],
    ["create", "create_fix_list", ["filter", "create"]],
  ]) {
    test(`V${version} reports the failed FixList ${operation} operation when no report was saved`, async () => {
      const fixture = writer(version, operation);
      assert.deepEqual(await fixture.post(), genericFailure);
      assert.deepEqual(fixture.calls, expectedCalls);
      assert.deepEqual(fixture.fixLists, []);
      assert.deepEqual(fixture.logs, [
        ["persistDurableScanAuthority failed", JSON.stringify({ stage, failure_type: "upstream_http", upstream_status: 413 })],
      ]);
    });
  }

  test(`V${version} distinguishes snapshot construction, signing, and an invalid envelope`, async () => {
    const fixture = writer(version, "sign");
    assert.deepEqual(await fixture.post({ stage3_authority_claim: { scan_id: "fixture-private-claim" } }), genericFailure);
    assert.deepEqual(await fixture.post(), genericFailure);
    assert.equal((await fixture.post({}, false)).status, 409);
    assert.deepEqual(fixture.calls, []);
    assert.deepEqual(fixture.logs, [
      ["persistDurableScanAuthority failed", JSON.stringify({ stage: "build_snapshot", failure_type: "stage3_delivery" })],
      ["persistDurableScanAuthority failed", JSON.stringify({ stage: "sign_snapshot", failure_type: "type_error" })],
    ]);
  });
}
