// Focused coverage for the scan-recovery boundary after the customer path moved
// from runAdvancedScan to runStandard150Scan.
//
// scanStorageRecovery.js cannot be imported directly under `node --test`: it
// resolves "@/..." aliases and installs browser storage/function boundaries at
// module load. So instead of asserting on source text alone, this test extracts
// the two pieces that carry the risk -- the page-limit table and the gateway
// dispatch set -- and executes them, which is what proves the rename did not
// silently disable the boundary.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const recoverySource = readFileSync(
  new URL("../../src/lib/scanStorageRecovery.js", import.meta.url),
  "utf8",
);
const scanFormSource = readFileSync(
  new URL("../../src/components/scan/ScanWebsiteForm.jsx", import.meta.url),
  "utf8",
);

function extract(pattern, label) {
  const match = recoverySource.match(pattern);
  assert.ok(match, `could not extract ${label} from scanStorageRecovery.js`);
  return match[0];
}

// Rebuild pageLimit() and SCAN_GATEWAY_FUNCTIONS in an isolated scope and run them.
const recoveryHarness = new Function(`
  ${extract(/const PAGE_LIMITS = \{[^}]*\};/, "PAGE_LIMITS")}
  ${extract(/const SCAN_GATEWAY_FUNCTIONS = new Set\(\[[^\]]*\]\);/, "SCAN_GATEWAY_FUNCTIONS")}
  ${extract(/function pageLimit\(scanMode\) \{[\s\S]*?\n\}/, "pageLimit")}
  return { pageLimit, SCAN_GATEWAY_FUNCTIONS };
`)();

const { pageLimit, SCAN_GATEWAY_FUNCTIONS } = recoveryHarness;

test("the active Standard 150 form uses server-owned admission instead of the legacy scanner recovery boundary", () => {
  assert.equal(SCAN_GATEWAY_FUNCTIONS.has("runStandard150Scan"), true);
  assert.match(scanFormSource, /const ASYNC_SCAN_JOB_FUNCTION = "startStandardScanJob"/);
  assert.match(scanFormSource, /submitStandardScanJob\(scanPayload\)/);
  assert.doesNotMatch(scanFormSource, /\bSTANDARD_SCANNER_FUNCTION\b|\bAI_REVIEW_FUNCTION\b/,
    "retired scanner/review constants must not survive in the active customer form");
});

test("the boundary still fires for the legacy gateway while it remains deployed", () => {
  assert.equal(SCAN_GATEWAY_FUNCTIONS.has("runAdvancedScan"), true);
});

test("the boundary does not fire for unrelated functions", () => {
  for (const other of ["aiReviewScan", "generateReport", "startCrawl", "stripeWebhook"]) {
    assert.equal(SCAN_GATEWAY_FUNCTIONS.has(other), false);
  }
});

test("standard_150 enforces a 150 page cap", () => {
  assert.equal(pageLimit("standard_150"), 150);
});

test("the standard_150 cap does not depend on the unknown-mode fallback", () => {
  // Regression guard: standard_150 must be an explicit key, not a value that
  // happens to be right because it falls through to the advanced default.
  assert.match(recoverySource, /standard_150: 150/);
});

test("historical Quick/Deep/Advanced records stay readable at their own caps", () => {
  assert.equal(pageLimit("quick"), 40);
  assert.equal(pageLimit("deep"), 85);
  assert.equal(pageLimit("basic"), 25);
  assert.equal(pageLimit("advanced"), 150);
});

test("missing or unknown modes fall back to the Standard 150 cap", () => {
  assert.equal(pageLimit(""), 150);
  assert.equal(pageLimit(undefined), 150);
  assert.equal(pageLimit(null), 150);
  assert.equal(pageLimit("some_future_mode"), 150);
});

test("mode matching is case-insensitive", () => {
  assert.equal(pageLimit("STANDARD_150"), 150);
  assert.equal(pageLimit("Quick"), 40);
});
