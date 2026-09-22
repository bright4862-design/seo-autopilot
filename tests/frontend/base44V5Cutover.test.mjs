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

test("V5 remains available only as the immediately historical Base44 generation", () => {
  assert.equal(contract.generation, "v8");
  for (const canonical of canonicals) {
    assert.equal(contract.historical_routes.v5[canonical], canonical + "V5");
    assert.ok(fs.existsSync("base44/functions/" + canonical + "V5/entry.ts"));
    assert.match(
      source("base44/functions/" + canonical + "V5/function.jsonc"),
      new RegExp('"name"\\s*:\\s*"' + canonical + 'V5"'),
    );
    assert.equal(contract.routes[canonical], canonical + "V7");
  }
});

test("active customer and worker call sites no longer target V5", () => {
  const combined = [
    source("src/components/scan/ScanWebsiteForm.jsx"),
    source("src/lib/scanRuns.js"),
    source("src/lib/scanHistory.js"),
    source("scanner-api/app/scan_job.py"),
  ].join("\n");
  for (const canonical of canonicals) {
    assert.doesNotMatch(combined, new RegExp(canonical + "V5"), canonical);
  }
});

test("historical V5 reader still carries signed preview authority support", () => {
  const reader = source("base44/functions/getCustomerScanResultV5/entry.ts");
  const projection = source("base44/functions/getCustomerScanResultV5/projection.js");
  assert.match(reader, /authorityVerified:\s*true/);
  assert.match(projection, /const PREVIEW_DETAILED_FIX_COUNT = 2;/);
  assert.match(projection, /const PREVIEW_VISIBLE_FIX_COUNT = 2;/);
});
