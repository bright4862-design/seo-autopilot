import assert from "node:assert/strict";
import fs from "node:fs";
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

test("V6 remains available as the immediately historical Base44 generation after the V7 cutover", () => {
  assert.equal(contract.schema_version, "base44_function_routes_v1");
  assert.equal(contract.generation, "v7");
  for (const canonical of canonicals) {
    assert.equal(contract.historical_routes.v6[canonical], canonical + "V6");
    assert.equal(contract.routes[canonical], canonical + "V7");
    assert.ok(fs.existsSync("base44/functions/" + canonical + "V6/entry.ts"));
    assert.match(
      source("base44/functions/" + canonical + "V6/function.jsonc"),
      new RegExp('"name"\\s*:\\s*"' + canonical + 'V6"'),
    );
  }
});

test("active customer and worker call sites no longer target V6", () => {
  const combined = [
    source("src/components/scan/ScanWebsiteForm.jsx"),
    source("src/lib/scanRuns.js"),
    source("src/lib/scanHistory.js"),
    source("scanner-api/app/scan_job.py"),
  ].join("\n");
  for (const canonical of canonicals) assert.doesNotMatch(combined, new RegExp(canonical + "V6"), canonical);
});

test("historical V6 reader retains the signed preview contract", () => {
  const reader = source("base44/functions/getCustomerScanResultV6/entry.ts");
  const projection = source("base44/functions/getCustomerScanResultV6/projection.js");
  assert.match(reader, /authorityVerified:\s*true/);
  assert.match(projection, /const PREVIEW_DETAILED_FIX_COUNT = 2;/);
  assert.match(projection, /const PREVIEW_VISIBLE_FIX_COUNT = 2;/);
});
