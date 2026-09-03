import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const contract = JSON.parse(fs.readFileSync("data/base44-function-routes.json", "utf8"));
const routes = contract.routes;

const source = (p) => fs.readFileSync(p, "utf8");

test("Base44 scanner route generation is explicit and complete", () => {
  assert.equal(contract.schema_version, "base44_function_routes_v1");
  assert.equal(contract.generation, "v2");
  assert.deepEqual(Object.keys(routes).sort(), [
    "deleteCustomerScanData",
    "durableScanWorkerControl",
    "getCustomerScanResult",
    "persistDurableScanAuthority",
    "persistLimitedScanResult",
    "startStandardScanJob",
  ]);
  for (const [canonical, active] of Object.entries(routes)) {
    assert.equal(active, `${canonical}V2`);
    assert.ok(fs.existsSync(path.join("base44/functions", active, "entry.ts")));
    assert.match(source(path.join("base44/functions", active, "function.jsonc")), new RegExp(`"name"\\s*:\\s*"${active}"`));
  }
});

test("fresh Base44 routes ship the same executable source as their canonical packages", () => {
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
      assert.equal(source(path.join(activeDir, file)), source(path.join(canonicalDir, file)), `${active}/${file}`);
    }
    const canonicalBuild = source(path.join(canonicalDir, "generatedBuildId.js")).match(/FUNCTION_BUILD_ID = "([0-9a-f]{64})"/)?.[1];
    const aliasBuild = source(path.join(activeDir, "generatedBuildId.js")).match(/FUNCTION_BUILD_ID = "([0-9a-f]{64})"/)?.[1];
    assert.equal(aliasBuild, canonicalBuild, active);
  }
});

test("customer and worker call sites use only fresh scanner routes", () => {
  const scanForm = source("src/components/scan/ScanWebsiteForm.jsx");
  const scanRuns = source("src/lib/scanRuns.js");
  const scanHistory = source("src/lib/scanHistory.js");
  const worker = source("scanner-api/app/scan_job.py");

  assert.match(scanForm, /ASYNC_SCAN_JOB_FUNCTION = "startStandardScanJobV2"/);
  assert.match(scanRuns, /"getCustomerScanResultV2"/);
  assert.doesNotMatch(scanRuns, /"getCustomerScanResult"/);
  assert.match(scanHistory, /DELETE_FUNCTION = "deleteCustomerScanDataV2"/);

  for (const name of [
    "durableScanWorkerControlV2",
    "persistDurableScanAuthorityV2",
    "persistLimitedScanResultV2",
  ]) assert.ok(worker.includes(`"${name}"`), name);
  for (const legacy of [
    '"durableScanWorkerControl"',
    '"persistDurableScanAuthority"',
    '"persistLimitedScanResult"',
  ]) assert.ok(!worker.includes(legacy), legacy);
});
