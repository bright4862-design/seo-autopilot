import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import ts from "typescript";
import { execFileSync } from "node:child_process";
import { admissionClaimEvidenceProof } from "../../base44/functions/startStandardScanJobV8/admissionClient.js";
import { normalizeScopeOrigin } from "../../src/lib/focusedScanScope.js";

const contract = JSON.parse(fs.readFileSync("data/base44-function-routes.json", "utf8"));
const routes = contract.routes;

const source = (p) => fs.readFileSync(p, "utf8");

function loadRoute(active, provided, deno) {
  const root = path.resolve("base44/functions", active);
  const cache = new Map();
  function load(file) {
    if (cache.has(file)) return cache.get(file).exports;
    const module = { exports: {} };
    cache.set(file, module);
    const javascript = ts.transpileModule(source(file), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    }).outputText;
    const requireLocal = (specifier) => {
      const external = specifier.startsWith("npm:@base44/sdk@") ? "npm:@base44/sdk" : specifier;
      if (Object.hasOwn(provided, external)) return provided[external];
      assert.ok(specifier.startsWith("./"), `unexpected dependency: ${specifier}`);
      const dependency = path.resolve(path.dirname(file), specifier);
      assert.ok(dependency.startsWith(`${root}${path.sep}`));
      return load(dependency);
    };
    new Function("require", "module", "exports", "Deno", javascript)(requireLocal, module, module.exports, deno);
    return module.exports;
  }
  return load(path.join(root, "entry.ts")).default;
}

test("every active V8 effective handler returns its expected runtime identity before authentication", async () => {
  for (const active of Object.values(routes)) {
    let handler;
    const forbidden = () => { throw new Error("GET identity probe must not access authentication or secrets"); };
    const deno = { serve: (fn) => { handler = fn; }, env: { get: forbidden } };
    const defaultHandler = loadRoute(active, {
      "npm:@base44/sdk": { createClientFromRequest: forbidden },
      "base44:runtime": { secrets: { get: forbidden } },
    }, deno);
    handler ||= defaultHandler;
    assert.equal(typeof handler, "function", active);
    const response = await handler(new Request("https://identity.example", { method: "GET" }));
    assert.equal(response.status, 405, active);
    const body = await response.json();
    // Production kept serving this pre-report activation after reporting the
    // new package as unchanged. Every active handler must leave that generation.
    assert.notEqual(body.runtime_activation_id, `${active}-fresh-20260907-v1`,
      `${active} must not reuse the stale pre-report runtime activation`);
    for (const [field, option] of [["build_id", "--build-id"], ["runtime_activation_id", "--activation-id"]]) {
      const expected = execFileSync(process.execPath, ["scripts/generate_release_contracts.mjs", option, active], { encoding: "utf8" }).trim();
      assert.equal(body[field], expected, `${active} effective ${field}`);
    }
  }
});

async function launchCachedV8({ scan = null, cap = 500, invalidProof = false } = {}) {
  const user = { id: "fixture_owner", email: "owner@example.test" };
  const project = { id: "project_fixture", owner_user_id: user.id, website_url: "https://example.test/", site_owner_attestation: "not_owner" };
  const requestId = "request_cached_v8";
  const signingKey = "fixture-signing-key";
  const calls = [];
  const evidence = {
    version: "admission_claim_evidence_v1", owner_user_id: user.id, request_id: requestId,
    barrier_generation: 4, claim_sequence: 9, admission_mode: "open",
    acceptance_cohort_id: "", acceptance_release_id: "", acceptance_source_sha: "", acceptance_expires_at: null,
  };
  const proof = await admissionClaimEvidenceProof(evidence, signingKey);
  const scanId = "cached_scan_fixture";
  const saved = scan && {
    id: scanId, scan_id: scanId, owner_user_id: user.id, project_id: project.id, request_id: requestId,
    idempotency_key: requestId, website_url: project.website_url, scan_mode: "standard_150",
    request_fingerprint: `standard150:${Buffer.from(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(`standard_150|${project.website_url}|robots:respect`))).toString("hex")}`,
    admission_barrier_generation: 4, admission_claim_sequence: 9, admission_mode: "open",
    admission_cohort_evidence_version: evidence.version, admission_cohort_evidence_proof: invalidProof ? "0".repeat(64) : proof,
    respect_robots_txt: true, owner_attested_robots_override: false, site_ownership_answer: "not_owner",
    site_ownership_policy_version: "owner_managed_robots_v1", ...scan,
  };
  const grant = {
    id: "access_fixture", owner_user_id: user.id, user_email: user.email, page_cap: cap,
    has_full_access: true, access_status: "active", plan_id: "standard150_lifetime", app_id: "6a498732ec779dfaaeab0e53",
    grant_source: "manual_grant", granted_at: "2026-11-01T12:00:00.000Z",
  };
  const env = {
    BETA_SCAN_INTAKE_ENABLED: "true", BETA_SCAN_ADMISSION_ENABLED: "true",
    SCAN_ADMISSION_COORDINATOR_URL: "https://admission.example.test", SCAN_EVIDENCE_SIGNING_KEY: signingKey,
    SCAN_TASKS_QUEUE_PATH: "queue", SCAN_DRAIN_QUEUE_PATH: "drain", SCAN_WORKER_URL: "https://worker.example.test/scan-job",
    TASKS_INVOKER_SERVICE_ACCOUNT: "ignored-fixture",
  };
  const entities = {
    Access: { filter: async () => [grant] },
    BusinessProject: { get: async () => project },
    ScanRun: { filter: async () => [], get: async id => id === scanId ? saved : null },
  };
  const { verifyAdmissionClaimEvidence } = await import("../../base44/functions/startStandardScanJobV8/admissionClient.js");
  const post = loadRoute("startStandardScanJobV8", {
    "npm:@base44/sdk": { createClientFromRequest: () => ({ auth: { me: async () => user }, asServiceRole: { entities } }) },
    "base44:runtime": { secrets: { get: name => env[name] } },
    "./admissionClient.js": {
      verifyAdmissionClaimEvidence,
      statusAdmission: async () => {
        calls.push("status");
        return { ok: true, admission: saved ? { ...evidence, scan_id: scanId } : {} };
      },
      claimAdmission: async () => {
        calls.push("claim");
        return { ok: false, failureCode: "admission_busy" };
      },
    },
    "./cloudTasks.js": {
      DRAIN_DELAY_SECONDS: 450, normalizeAttemptCount: () => 1,
      enqueueScanDrain: async () => { calls.push("drain"); return { ok: true }; },
      enqueueScanJob: async () => { calls.push("dispatch"); return { ok: true }; },
    },
  }, { env: { get: name => env[name] } });
  const response = await post(new Request("https://example.test/V8", {
    method: "POST", body: JSON.stringify({ request_id: requestId, project_id: project.id, website_url: project.website_url }),
  }));
  return { status: response.status, body: await response.json(), calls };
}

test("a fresh 500 holder using cached V8 gets a refresh response before any admission claim", async () => {
  const result = await launchCachedV8();
  assert.equal(result.status, 409, JSON.stringify(result.body));
  assert.equal(result.body.failure_code, "scan_client_refresh_required");
  assert.match(result.body.error, /Refresh FixList/);
  assert.deepEqual(result.calls, ["status"]);

  const standard = await launchCachedV8({ cap: 150 });
  assert.equal(standard.status, 429);
  assert.deepEqual(standard.calls, ["claim"]);
});

test("cached V8 preserves an exact 150 retry or terminal status while refusing saved 500 and invalid proofs", async () => {
  const retry = await launchCachedV8({ scan: { status: "queued" } });
  assert.equal(retry.status, 200, JSON.stringify(retry.body));
  assert.equal(retry.body.replayed, true);
  assert.deepEqual(retry.calls, ["status", "drain", "dispatch"]);

  for (const scan of [{ status: "complete" }, { status: "reviewing", page_cap: 150, pipeline_mode: "staged" }]) {
    const readback = await launchCachedV8({ scan });
    assert.equal(readback.status, 200, JSON.stringify(readback.body));
    assert.equal(readback.body.status, scan.status);
    assert.deepEqual(readback.calls, ["status"]);
  }
  for (const result of [
    await launchCachedV8({ scan: { status: "queued", scan_mode: "standard_500", page_cap: 500 } }),
    await launchCachedV8({ scan: { status: "queued" }, invalidProof: true }),
  ]) {
    assert.equal(result.body.failure_code, "scan_client_refresh_required", JSON.stringify(result.body));
    assert.deepEqual(result.calls, ["status"]);
  }
});

test("Base44 scanner route generation is explicit and complete", () => {
  assert.equal(contract.schema_version, "base44_function_routes_v1");
  assert.equal(contract.generation, "v8");
  assert.deepEqual(Object.keys(routes).sort(), [
    "deleteCustomerScanData",
    "durableScanWorkerControl",
    "getCustomerScanResult",
    "persistDurableScanAuthority",
    "persistLimitedScanResult",
    "startStandardScanJob",
  ]);
  for (const [canonical, active] of Object.entries(routes)) {
    assert.equal(active, `${canonical}V8`);
    assert.ok(fs.existsSync(path.join("base44/functions", active, "entry.ts")));
    assert.match(source(path.join("base44/functions", active, "function.jsonc")), new RegExp(`"name"\\s*:\\s*"${active}"`));
  }
});

test("fresh Base44 routes preserve canonical source outside preview, Stage 3, and comparison additions", () => {
  const withoutActivationNonce = (value) => value.replace(
    /(BASE44_RUNTIME_ACTIVATION_ID\s*=\s*)["'][^"']+["']/g,
    '$1"<deployment-activation-nonce>"',
  );
  const v7OnlyFiles = new Map([
    ["persistDurableScanAuthority", [
      "authoritySnapshotStage1Legacy.js",
      "comparisonEvidence.js",
      "customerPreviewSeal.js",
      "customerPreviewSealStage1Legacy.js",
      "stage3V7Delivery.js",
      "stage3V7DeliveryStrict.js",
    ]],
    ["getCustomerScanResult", [
      "comparisonEvidence.js",
      "comparisonGateway.js",
      "comparisonReader.js",
      "customerPreviewSeal.js",
      "projectionStage1Legacy.js",
      "stage3V7Delivery.js",
    ]],
  ]);
  const intentionallyChangedInheritedFiles = new Map([
    ["startStandardScanJob", new Set(["entry.ts"])],
    ["persistDurableScanAuthority", new Set(["entry.ts", "authoritySnapshot.js"])],
    ["getCustomerScanResult", new Set(["entry.ts", "projection.js", "releaseCompatibility.js"])],
  ]);
  for (const [canonical, active] of Object.entries(routes)) {
    const canonicalDir = path.join("base44/functions", canonical);
    const activeDir = path.join("base44/functions", active);
    const canonicalFiles = fs.readdirSync(canonicalDir)
      .filter((name) => !["function.jsonc", "generatedBuildId.js"].includes(name))
      .sort();
    const activeFiles = fs.readdirSync(activeDir)
      .filter((name) => !["function.jsonc", "generatedBuildId.js"].includes(name))
      .sort();
    const allowedExtras = v7OnlyFiles.get(canonical) || [];
    assert.deepEqual(activeFiles, [...canonicalFiles, ...allowedExtras].sort(), active);
    const intentionalChanges = intentionallyChangedInheritedFiles.get(canonical) || new Set();
    for (const file of canonicalFiles) {
      if (intentionalChanges.has(file)) continue;
      assert.equal(
        withoutActivationNonce(source(path.join(activeDir, file))),
        withoutActivationNonce(source(path.join(canonicalDir, file))),
        `${active}/${file}`,
      );
    }
    if (allowedExtras.length > 0) {
      assert.match(source(path.join(activeDir, "entry.ts")), /customerPreviewSeal\.js/, `${active} must wire the signed preview helper`);
    }
    if (canonical === "getCustomerScanResult") {
      assert.match(source(path.join(activeDir, "entry.ts")), /readCustomerScanComparison\(\{/);
      assert.match(source(path.join(activeDir, "comparisonGateway.js")), /fixlist-scan-comparison-response-v1/);
      assert.match(source(path.join(activeDir, "projectionStage1Legacy.js")), /"preview_example_page"/);
      assert.match(source(path.join(activeDir, "projection.js")), /projectionStage1Legacy\.js/);
      assert.match(source(path.join(activeDir, "releaseCompatibility.js")), /customer_result_reader_v9_published_route_identity/);
    }
  }
});

test("customer and worker call sites use only V8 scanner routes", () => {
  const scanForm = source("src/components/scan/ScanWebsiteForm.jsx");
  const scanRuns = source("src/lib/scanRuns.js");
  const scanHistory = source("src/lib/scanHistory.js");
  const worker = source("scanner-api/app/scan_job.py");

  assert.match(scanForm, /ASYNC_SCAN_JOB_FUNCTION = "startStandardScanJobV8"/);
  assert.doesNotMatch(scanForm, /ASYNC_SCAN_JOB_FUNCTION = "startStandardScanJobV2"/);
  assert.match(scanRuns, /"getCustomerScanResultV8"/);
  assert.doesNotMatch(scanRuns, /"getCustomerScanResultV2"/);
  assert.match(scanHistory, /DELETE_FUNCTION = "deleteCustomerScanDataV8"/);
  assert.doesNotMatch(scanHistory, /DELETE_FUNCTION = "deleteCustomerScanDataV2"/);

  for (const name of [
    "durableScanWorkerControlV8",
    "persistDurableScanAuthorityV8",
    "persistLimitedScanResultV8",
  ]) assert.ok(worker.includes(`"${name}"`), name);
  for (const stale of [
    '"durableScanWorkerControlV2"',
    '"persistDurableScanAuthorityV2"',
    '"persistLimitedScanResultV2"',
  ]) assert.ok(!worker.includes(stale), stale);
});

test("V4 routes keep distinct historical activation identities and are retired from active deployment", () => {
  const markers = new Set();
  for (const canonical of Object.keys(routes)) {
    const historical = `${canonical}V4`;
    const marker = (name) => source(`base44/functions/${name}/entry.ts`)
      .match(/BASE44_RUNTIME_ACTIVATION_ID\s*=\s*["']([^"']+)["']/)?.[1];
    assert.ok(fs.existsSync(`base44/functions/${historical}/entry.ts`), `${historical} must remain for historical reads`);
    const activation = marker(historical);
    assert.match(activation, /^[A-Za-z0-9._-]{1,120}$/);
    assert.notEqual(activation, marker(canonical));
    assert.notEqual(activation, marker(`${canonical}V3`));
    assert.notEqual(activation, marker(`${canonical}V2`));
    assert.ok(!markers.has(activation), `${historical} needs a unique activation identity`);
    markers.add(activation);
    for (const file of [
      "scripts/deploy-base44-beta-functions.sh",
      "scripts/deploy-base44-beta-site.sh",
      "scripts/verify-base44-functions.sh",
      "scripts/base44_release_manifest.mjs",
    ]) {
      assert.ok(!source(file).includes(historical), `${file} must not deploy retired ${historical}`);
      assert.ok(!source(file).includes(`${canonical}V2`), `${file} must keep V2 retired`);
    }
  }
});

test("V4 cutover preserves the current Standard 150 scope contract", () => {
  const scanForm = source("src/components/scan/ScanWebsiteForm.jsx");
  const scanSchema = JSON.parse(source("base44/entities/ScanRun.jsonc"));
  const startV4 = source("base44/functions/startStandardScanJobV4/entry.ts");

  // A submitted subdomain remains a valid exact website origin.
  assert.equal(normalizeScopeOrigin("https://blog.example.com/docs"), "https://blog.example.com");

  // The release still does not broaden one scan across sibling subdomains.
  assert.deepEqual(scanSchema.properties.scope_type.enum, ["", "path_prefix"]);
  assert.equal(startV4.includes('scope_type: "subdomain"'), false);

  // Standard 150 remains Standard 150; the route rename cannot raise the cap.
  assert.match(scanForm, /const STANDARD_SCAN_MODE = "standard_150"/);
  assert.match(scanForm, /max_pages:\s*150/);
});
