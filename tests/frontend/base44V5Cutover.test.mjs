import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const source = (p) => fs.readFileSync(p, "utf8");
const contract = JSON.parse(source("data/base44-function-routes.json"));
const expectedCanonicals = [
  "startStandardScanJob",
  "durableScanWorkerControl",
  "persistDurableScanAuthority",
  "persistLimitedScanResult",
  "getCustomerScanResult",
  "deleteCustomerScanData",
];

test("V5 is the active Base44 generation and V4/V3/V2 remain historical", () => {
  assert.equal(contract.schema_version, "base44_function_routes_v1");
  assert.equal(contract.generation, "v5");
  assert.deepEqual(Object.keys(contract.routes).sort(), [...expectedCanonicals].sort());
  for (const canonical of expectedCanonicals) {
    assert.equal(contract.routes[canonical], `${canonical}V5`);
    assert.equal(contract.historical_routes.v4[canonical], `${canonical}V4`);
    assert.equal(contract.historical_routes.v3[canonical], `${canonical}V3`);
    assert.equal(contract.historical_routes.v2[canonical], `${canonical}V2`);
    assert.ok(fs.existsSync(`base44/functions/${canonical}V5/entry.ts`));
    assert.match(source(`base44/functions/${canonical}V5/function.jsonc`), new RegExp(`"name"\\s*:\\s*"${canonical}V5"`));
  }
});

test("V5 executable packages preserve canonical behavior except fresh activation identity", () => {
  const normalizeActivation = (value) => value.replace(
    /(BASE44_RUNTIME_ACTIVATION_ID\s*=\s*)["'][^"']+["']/g,
    '$1"<deployment-activation-nonce>"',
  );
  const v5OnlyFiles = new Map([
    ["persistDurableScanAuthority", ["customerPreviewSeal.js"]],
    ["getCustomerScanResult", ["customerPreviewSeal.js"]],
  ]);
  const intentionallyChangedInheritedFiles = new Map([
    ["persistDurableScanAuthority", new Set(["entry.ts"])],
    ["getCustomerScanResult", new Set(["entry.ts", "projection.js", "releaseCompatibility.js"])],
  ]);
  for (const canonical of expectedCanonicals) {
    const canonicalDir = `base44/functions/${canonical}`;
    const v5Dir = `base44/functions/${canonical}V5`;
    const filtered = (dir) => fs.readdirSync(dir).filter((name) => !["function.jsonc", "generatedBuildId.js"].includes(name)).sort();
    const canonicalFiles = filtered(canonicalDir);
    const allowedExtras = v5OnlyFiles.get(canonical) || [];
    assert.deepEqual(
      filtered(v5Dir),
      [...canonicalFiles, ...allowedExtras].sort(),
      canonical,
    );
    const intentionalChanges = intentionallyChangedInheritedFiles.get(canonical) || new Set();
    for (const file of canonicalFiles) {
      if (intentionalChanges.has(file)) continue;
      assert.equal(normalizeActivation(source(path.join(v5Dir, file))), normalizeActivation(source(path.join(canonicalDir, file))), `${canonical}V5/${file}`);
    }
    if (allowedExtras.length > 0) {
      const v5Entry = source(path.join(v5Dir, "entry.ts"));
      assert.match(v5Entry, /customerPreviewSeal\.js/, `${canonical}V5 entry must wire the signed preview addition`);
    }
    if (canonical === "getCustomerScanResult") {
      const v5Projection = source(path.join(v5Dir, "projection.js"));
      assert.match(v5Projection, /"preview_example_page"/, "V5 preview projection may expose only its pre-signed example page addition");
      assert.match(source(path.join(v5Dir, "releaseCompatibility.js")), /customer_result_reader_v7_signed_preview_authority/);
    }
  }
});

test("customer and worker active call sites use V5 only", () => {
  const scanForm = source("src/components/scan/ScanWebsiteForm.jsx");
  const scanRuns = source("src/lib/scanRuns.js");
  const scanHistory = source("src/lib/scanHistory.js");
  const worker = source("scanner-api/app/scan_job.py");
  assert.match(scanForm, /ASYNC_SCAN_JOB_FUNCTION = "startStandardScanJobV5"/);
  assert.doesNotMatch(scanForm, /ASYNC_SCAN_JOB_FUNCTION = "startStandardScanJobV4"/);
  assert.match(scanRuns, /"getCustomerScanResultV5"/);
  assert.doesNotMatch(scanRuns, /"getCustomerScanResultV4"/);
  assert.match(scanHistory, /DELETE_FUNCTION = "deleteCustomerScanDataV5"/);
  assert.doesNotMatch(scanHistory, /DELETE_FUNCTION = "deleteCustomerScanDataV4"/);
  for (const name of ["durableScanWorkerControlV5", "persistDurableScanAuthorityV5", "persistLimitedScanResultV5"]) assert.ok(worker.includes(`"${name}"`), name);
  for (const stale of ["durableScanWorkerControlV4", "persistDurableScanAuthorityV4", "persistLimitedScanResultV4"]) assert.ok(!worker.includes(`"${stale}"`), stale);
});

test("V5 preserves verified unpaid teaser and shared $49 two-fix contract", () => {
  const reader = source("base44/functions/getCustomerScanResultV5/entry.ts");
  const projection = source("base44/functions/getCustomerScanResultV5/projection.js");
  const fixListPage = source("src/pages/FixList.jsx");
  const access = source("src/lib/access.js");
  assert.match(reader, /previewAccess:\s*!access\.ok/);
  assert.match(reader, /authorityVerified:\s*true/);
  assert.match(projection, /const PREVIEW_DETAILED_FIX_COUNT = 2;/);
  assert.match(projection, /const PREVIEW_VISIBLE_FIX_COUNT = 2;/);
  assert.match(projection, /\.slice\(0, PREVIEW_VISIBLE_FIX_COUNT\)/);
  assert.match(projection, /previewAccess === true \? "preview" : "locked"/);
  assert.match(fixListPage, /\.slice\(0, 2\)/);
  assert.match(access, /UNLOCK_PRICE_LABEL = "\$49"/);
  assert.match(access, /LOCKED_PREVIEW_FIX_COUNT = 2/);
});
