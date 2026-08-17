// An abandoned ScanRun stays "active" forever on its own and holds the
// account's admission lease, which makes every new scan get refused with
// "Another scan is already running for this account." The sweep must therefore
// be wired into the surfaces a customer actually opens, and the refusal must
// offer a destination instead of dead-ending.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const scanForm = readFileSync("src/components/scan/ScanWebsiteForm.jsx", "utf8");
const fixList = readFileSync("src/pages/FixList.jsx", "utf8");
const scanRuns = readFileSync("src/lib/scanRuns.js", "utf8");

test("recoverOrphanedScanRuns still exists and only closes stale active runs", () => {
  assert.match(scanRuns, /export async function recoverOrphanedScanRuns/);
  assert.match(scanRuns, /ACTIVE_SCAN_RUN_STATUSES\.has/);
  assert.match(scanRuns, /isStaleActiveScanRun/);
  // Terminal rows carry persisted evidence and must never be rewritten.
  assert.match(scanRuns, /PROTECTED_SCAN_STATUSES = new Set\(\["complete", "limited"\]\)/);
});

test("the scan form sweeps orphaned runs on load", () => {
  assert.match(scanForm, /recoverOrphanedScanRuns/);
  assert.match(
    scanForm,
    /useEffect\(\(\) => \{\s*recoverOrphanedScanRuns\(\{ projectId: project\?\.id \|\| "" \}\);/,
  );
});

test("the result surface sweeps orphaned runs before listing saved scans", () => {
  const sweepIndex = fixList.indexOf("recoverOrphanedScanRuns({ projectId: project.id })");
  const listIndex = fixList.indexOf("listScanRuns(project.id");
  assert.ok(sweepIndex > 0, "FixList must sweep orphaned runs");
  assert.ok(listIndex > sweepIndex, "the sweep must run before the history read");
});

test("a busy-account refusal offers a way to reach the running scan", () => {
  assert.match(scanForm, /scan_admission_busy/);
  assert.match(scanForm, /setErrorAction\("open_dashboard"\)/);
  assert.match(scanForm, /Open my scans/);
});

test("the sweep never invents a successful result", () => {
  for (const forbidden of ["status: \"complete\"", "release_gate_eligible: true"]) {
    assert.ok(
      !scanRuns.includes(`recoverOrphanedScanRuns`) || !scanRuns.includes(forbidden),
      `recovery must not write ${forbidden}`,
    );
  }
});