import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const source = (p) => fs.readFileSync(p, "utf8");
const contract = JSON.parse(source("data/base44-function-routes.json"));
const canonicals = [
  "startStandardScanJob",
  "durableScanWorkerControl",
  "persistDurableScanAuthority",
  "persistLimitedScanResult",
  "getCustomerScanResult",
  "deleteCustomerScanData",
];
const normalizeActivation = (value) => value.replace(
  /(BASE44_RUNTIME_ACTIVATION_ID\s*=\s*)["'][^"']+["']/g,
  '$1"<deployment-activation-nonce>"',
);

test("V8 is active and V7/V6/V5/V4/V3/V2 remain historical", () => {
  assert.equal(contract.schema_version, "base44_function_routes_v1");
  assert.equal(contract.generation, "v8");
  for (const canonical of canonicals) {
    assert.equal(contract.routes[canonical], canonical + "V8");
    assert.equal(contract.historical_routes.v7[canonical], canonical + "V7");
    assert.equal(contract.historical_routes.v6[canonical], canonical + "V6");
    assert.equal(contract.historical_routes.v5[canonical], canonical + "V5");
    assert.equal(contract.historical_routes.v4[canonical], canonical + "V4");
    assert.equal(contract.historical_routes.v3[canonical], canonical + "V3");
    assert.equal(contract.historical_routes.v2[canonical], canonical + "V2");
    assert.ok(fs.existsSync("base44/functions/" + canonical + "V8/entry.ts"));
    assert.match(source("base44/functions/" + canonical + "V8/function.jsonc"), new RegExp('\"name\"\\s*:\\s*\"' + canonical + 'V8\"'));
  }
});

test("V8 packages preserve V7 behavior exactly except route identity", () => {
  for (const canonical of canonicals) {
    const v7dir = "base44/functions/" + canonical + "V7";
    const v8dir = "base44/functions/" + canonical + "V8";
    const v7files = fs.readdirSync(v7dir).sort();
    const v8files = fs.readdirSync(v8dir).sort();
    assert.deepEqual(v8files, v7files, canonical);
    for (const file of v7files) {
      if (file === "generatedBuildId.js") continue;
      let actual = source(path.join(v8dir, file));
      let expected = source(path.join(v7dir, file));
      if (file === "function.jsonc") actual = actual.replace(canonical + "V8", canonical + "V7");
      if (file === "entry.ts" || file === "index.ts") {
        actual = normalizeActivation(actual);
        expected = normalizeActivation(expected);
      }
      assert.equal(actual, expected, canonical + "/" + file);
    }
  }
});

test("active customer and worker call sites use V8 only", () => {
  const scanForm = source("src/components/scan/ScanWebsiteForm.jsx");
  const scanRuns = source("src/lib/scanRuns.js");
  const scanHistory = source("src/lib/scanHistory.js");
  const worker = source("scanner-api/app/scan_job.py");
  const combined = [scanForm, scanRuns, scanHistory, worker].join("\n");
  assert.match(scanForm, /ASYNC_SCAN_JOB_FUNCTION = "startStandardScanJobV8"/);
  assert.match(scanRuns, /"getCustomerScanResultV8"/);
  assert.match(scanHistory, /DELETE_FUNCTION = "deleteCustomerScanDataV8"/);
  for (const name of ["durableScanWorkerControlV8","persistDurableScanAuthorityV8","persistLimitedScanResultV8"]) assert.ok(worker.includes('"' + name + '"'), name);
  for (const stale of canonicals.map((name) => name + "V7")) assert.ok(!combined.includes(stale), stale);
});

test("V7 preserves signed unpaid teaser and shared $49 two-fix contract", () => {
  const reader = source("base44/functions/getCustomerScanResultV8/entry.ts");
  const projection = source("base44/functions/getCustomerScanResultV8/projectionStage1Legacy.js");
  const projectionWrapper = source("base44/functions/getCustomerScanResultV8/projection.js");
  const fixListPage = source("src/pages/FixList.jsx");
  const access = source("src/lib/access.js");
  assert.match(reader, /previewAccess:\s*!access\.ok/);
  assert.match(reader, /authorityVerified:\s*true/);
  assert.match(projection, /const PREVIEW_DETAILED_FIX_COUNT = 2;/);
  assert.match(projection, /const PREVIEW_VISIBLE_FIX_COUNT = 2;/);
  assert.match(projectionWrapper, /projectionStage1Legacy\.js/);
  assert.match(fixListPage, /\.slice\(0, 2\)/);
  assert.match(access, /UNLOCK_PRICE_LABEL = "\$49"/);
  assert.match(access, /LOCKED_PREVIEW_FIX_COUNT = 2/);
});
