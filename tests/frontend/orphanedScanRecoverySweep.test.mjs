// Browser surfaces may explain a busy admission, but terminal ScanRun state is
// server-owned. The stale-row recovery helper can remain as legacy/internal
// code, but customer pages must never invoke it.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const scanForm = readFileSync("src/components/scan/ScanWebsiteForm.jsx", "utf8");
const fixList = readFileSync("src/pages/FixList.jsx", "utf8");
const scanRuns = readFileSync("src/lib/scanRuns.js", "utf8");

test("legacy orphan recovery helper remains bounded to stale active runs", () => {
  assert.match(scanRuns, /export async function recoverOrphanedScanRuns/);
  assert.match(scanRuns, /ACTIVE_SCAN_RUN_STATUSES\.has/);
  assert.match(scanRuns, /isStaleActiveScanRun/);
  assert.match(scanRuns, /PROTECTED_SCAN_STATUSES = new Set\(\["complete", "limited"\]\)/);
});

test("customer pages do not terminalize server-owned scans", () => {
  assert.doesNotMatch(scanForm, /recoverOrphanedScanRuns/);
  assert.doesNotMatch(fixList, /recoverOrphanedScanRuns/);
});

test("a busy-account refusal offers a way to reach the running scan", () => {
  assert.match(scanForm, /scan_admission_busy/);
  assert.match(scanForm, /setErrorAction\("open_dashboard"\)/);
  assert.match(scanForm, /Open my scans/);
});

test("browser recovery never invents a successful result", () => {
  const helper = scanRuns.match(/export async function recoverOrphanedScanRuns[\s\S]*?\n\}/)?.[0] || "";
  assert.doesNotMatch(helper, /status:\s*["']complete["']/);
  assert.doesNotMatch(helper, /release_gate_eligible:\s*true/);
});
