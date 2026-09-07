import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import ts from "typescript";
import { execFileSync } from "node:child_process";
import { normalizeScopeOrigin } from "../../src/lib/focusedScanScope.js";

const contract = JSON.parse(fs.readFileSync("data/base44-function-routes.json", "utf8"));
const routes = contract.routes;

const source = (p) => fs.readFileSync(p, "utf8");

test("every V3 effective handler returns its expected runtime identity before authentication", async () => {
  for (const active of Object.values(routes)) {
    const root = path.resolve("base44/functions", active);
    const cache = new Map();
    let handler;
    const forbidden = () => { throw new Error("GET identity probe must not access authentication or secrets"); };
    const deno = { serve: (fn) => { handler = fn; }, env: { get: forbidden } };
    function load(file) {
      if (cache.has(file)) return cache.get(file).exports;
      const module = { exports: {} };
      cache.set(file, module);
      const javascript = ts.transpileModule(source(file), {
        compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
      }).outputText;
      const requireLocal = (specifier) => {
        if (specifier.startsWith("npm:@base44/sdk@")) return { createClientFromRequest: forbidden };
        if (specifier === "base44:runtime") return { secrets: { get: forbidden } };
        assert.ok(specifier.startsWith("./"), `unexpected dependency: ${specifier}`);
        const dependency = path.resolve(path.dirname(file), specifier);
        assert.ok(dependency.startsWith(`${root}${path.sep}`));
        return load(dependency);
      };
      new Function("require", "module", "exports", "Deno", javascript)(requireLocal, module, module.exports, deno);
      return module.exports;
    }
    const entry = load(path.join(root, "entry.ts"));
    handler ||= entry.default;
    assert.equal(typeof handler, "function", active);
    const response = await handler(new Request("https://identity.example", { method: "GET" }));
    assert.equal(response.status, 405, active);
    const body = await response.json();
    for (const [field, option] of [["build_id", "--build-id"], ["runtime_activation_id", "--activation-id"]]) {
      const expected = execFileSync(process.execPath, ["scripts/generate_release_contracts.mjs", option, active], { encoding: "utf8" }).trim();
      assert.equal(body[field], expected, `${active} effective ${field}`);
    }
  }
});

test("Base44 scanner route generation is explicit and complete", () => {
  assert.equal(contract.schema_version, "base44_function_routes_v1");
  assert.equal(contract.generation, "v3");
  assert.deepEqual(Object.keys(routes).sort(), [
    "deleteCustomerScanData",
    "durableScanWorkerControl",
    "getCustomerScanResult",
    "persistDurableScanAuthority",
    "persistLimitedScanResult",
    "startStandardScanJob",
  ]);
  for (const [canonical, active] of Object.entries(routes)) {
    assert.equal(active, `${canonical}V3`);
    assert.ok(fs.existsSync(path.join("base44/functions", active, "entry.ts")));
    assert.match(source(path.join("base44/functions", active, "function.jsonc")), new RegExp(`"name"\\s*:\\s*"${active}"`));
  }
});

test("fresh Base44 routes ship the same executable source as their canonical packages", () => {
  const withoutActivationNonce = (value) => value.replace(
    /(BASE44_RUNTIME_ACTIVATION_ID\s*=\s*)["'][^"']+["']/g,
    '$1"<deployment-activation-nonce>"',
  );
  for (const [canonical, active] of Object.entries(routes)) {
    const canonicalDir = path.join("base44/functions", canonical);
    const activeDir = path.join("base44/functions", active);
    const canonicalFiles = fs.readdirSync(canonicalDir)
      .filter((name) => !["function.jsonc", "generatedBuildId.js"].includes(name))
      .sort();
    const activeFiles = fs.readdirSync(activeDir)
      .filter((name) => !["function.jsonc", "generatedBuildId.js"].includes(name))
      .sort();
    assert.deepEqual(activeFiles, canonicalFiles, active);
    for (const file of canonicalFiles) {
      assert.equal(
        withoutActivationNonce(source(path.join(activeDir, file))),
        withoutActivationNonce(source(path.join(canonicalDir, file))),
        `${active}/${file}`,
      );
    }
    const canonicalBuild = source(path.join(canonicalDir, "generatedBuildId.js")).match(/FUNCTION_BUILD_ID = "([0-9a-f]{64})"/)?.[1];
    const aliasBuild = source(path.join(activeDir, "generatedBuildId.js")).match(/FUNCTION_BUILD_ID = "([0-9a-f]{64})"/)?.[1];
    assert.equal(aliasBuild, canonicalBuild, active);
  }
});

test("customer and worker call sites use only V3 scanner routes", () => {
  const scanForm = source("src/components/scan/ScanWebsiteForm.jsx");
  const scanRuns = source("src/lib/scanRuns.js");
  const scanHistory = source("src/lib/scanHistory.js");
  const worker = source("scanner-api/app/scan_job.py");

  assert.match(scanForm, /ASYNC_SCAN_JOB_FUNCTION = "startStandardScanJobV3"/);
  assert.doesNotMatch(scanForm, /ASYNC_SCAN_JOB_FUNCTION = "startStandardScanJobV2"/);
  assert.match(scanRuns, /"getCustomerScanResultV3"/);
  assert.doesNotMatch(scanRuns, /"getCustomerScanResultV2"/);
  assert.match(scanHistory, /DELETE_FUNCTION = "deleteCustomerScanDataV3"/);
  assert.doesNotMatch(scanHistory, /DELETE_FUNCTION = "deleteCustomerScanDataV2"/);

  for (const name of [
    "durableScanWorkerControlV3",
    "persistDurableScanAuthorityV3",
    "persistLimitedScanResultV3",
  ]) assert.ok(worker.includes(`"${name}"`), name);
  for (const stale of [
    '"durableScanWorkerControlV2"',
    '"persistDurableScanAuthorityV2"',
    '"persistLimitedScanResultV2"',
  ]) assert.ok(!worker.includes(stale), stale);
});

test("V3 routes have distinct activation identities and exact release verification", () => {
  const markers = new Set();
  for (const canonical of Object.keys(routes)) {
    const active = `${canonical}V3`;
    const marker = (name) => source(`base44/functions/${name}/entry.ts`)
      .match(/BASE44_RUNTIME_ACTIVATION_ID\s*=\s*["']([^"']+)["']/)?.[1];
    assert.ok(fs.existsSync(`base44/functions/${active}/entry.ts`), `${active} must exist`);
    const activation = marker(active);
    assert.match(activation, /^[A-Za-z0-9._-]{1,120}$/);
    assert.notEqual(activation, marker(canonical));
    assert.notEqual(activation, marker(`${canonical}V2`));
    assert.ok(!markers.has(activation), `${active} needs a unique activation identity`);
    markers.add(activation);
    for (const file of [
      "scripts/deploy-base44-beta-functions.sh",
      "scripts/deploy-base44-beta-site.sh",
      "scripts/verify-base44-functions.sh",
      "scripts/base44_release_manifest.mjs",
    ]) {
      assert.ok(source(file).includes(active), `${file} must enumerate ${active}`);
      assert.ok(!source(file).includes(`${canonical}V2`), `${file} must retire the old active route`);
    }
  }
});

test("V3 cutover preserves the current Standard 150 scope contract", () => {
  const scanForm = source("src/components/scan/ScanWebsiteForm.jsx");
  const scanSchema = JSON.parse(source("base44/entities/ScanRun.jsonc"));
  const startV3 = source("base44/functions/startStandardScanJobV3/entry.ts");

  // A submitted subdomain remains a valid exact website origin.
  assert.equal(normalizeScopeOrigin("https://blog.example.com/docs"), "https://blog.example.com");

  // The release still does not broaden one scan across sibling subdomains.
  assert.deepEqual(scanSchema.properties.scope_type.enum, ["", "path_prefix"]);
  assert.equal(startV3.includes('scope_type: "subdomain"'), false);

  // Standard 150 remains Standard 150; the route rename cannot raise the cap.
  assert.match(scanForm, /const STANDARD_SCAN_MODE = "standard_150"/);
  assert.match(scanForm, /max_pages:\s*150/);
});
