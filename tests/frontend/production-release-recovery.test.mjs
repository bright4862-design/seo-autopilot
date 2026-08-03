import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const advanced = readFileSync("base44/functions/runAdvancedScan/entry.ts", "utf8");
const scannerForm = readFileSync("src/components/scan/ScanWebsiteForm.jsx", "utf8");
const fixList = readFileSync("src/pages/FixList.jsx", "utf8");

test("normal scans require Python and do not silently save Deno fallback", () => {
  assert.match(scannerForm, /require_python_scanner: true/);
  assert.match(scannerForm, /allow_deno_fallback: false/);
  assert.match(advanced, /did not save a fallback result/);
  assert.match(advanced, /python_scanner_failure_code/);
  assert.match(advanced, /release_gate_eligible: false/);
});

test("scan results route by exact durable scan ID without browser-result fallback", () => {
  assert.match(scannerForm, /scan_id: scanId/);
  assert.match(scannerForm, /scan_id=\$\{encodeURIComponent\(scanId\)\}/);
  assert.match(scannerForm, /submitLockRef\.current/);
  assert.match(scannerForm, /assertCurrentScanSession\(/);
  assert.doesNotMatch(scannerForm, /localStorage\.(?:getItem|setItem)/);
  assert.match(fixList, /searchParams\.get\("scan_id"\)/);
  assert.match(fixList, /getScanRunWithFixList\(requestedScanId\)/);
  assert.match(fixList, /normalizeDurableScanBundle\(durableBundle\)/);
  assert.match(fixList, /No other scan has been substituted/);
  assert.doesNotMatch(fixList, /readBestScanRecord|loaded_local|localStorage\.(?:getItem|setItem)/);
});

test("merged results preserve authoritative durable release markers", () => {
  assert.match(scannerForm, /const authorityMarkers = buildAuthorityMarkers\(scanData, aiData\)/);
  assert.match(scannerForm, /\.\.\.authorityMarkers/);
  assert.match(scannerForm, /\.\.\.buildDiagnosticAuthorityMarkers\(record\)/);
});
