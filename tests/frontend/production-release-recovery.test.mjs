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

test("scan results are stored and routed by stable scan ID", () => {
  assert.match(scannerForm, /const SCAN_RECORD_PREFIX = "seo_autopilot:scan:"/);
  assert.match(scannerForm, /scan_id: scanId/);
  assert.match(scannerForm, /scan_id=\$\{encodeURIComponent\(scanId\)\}/);
  assert.match(scannerForm, /localStorage\.setItem\(`\$\{SCAN_RECORD_PREFIX\}\$\{stableScanId\}`/);
  assert.doesNotMatch(scannerForm, /function clearPreviousDashboardScan/);
  assert.match(fixList, /searchParams\.get\("scan_id"\)/);
  assert.match(fixList, /readBestScanRecord\(requestedScanId\)/);
});
