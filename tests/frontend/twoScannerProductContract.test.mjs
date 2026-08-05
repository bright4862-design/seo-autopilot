// Standard 150 is the only customer scan. This file replaces the retired
// two-scanner picker contract: it now proves the single-product contract.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const scanFormSource = readFileSync(
  new URL("../../src/components/scan/ScanWebsiteForm.jsx", import.meta.url),
  "utf8",
);
const scanRunIdentitySource = readFileSync(
  new URL("../../src/lib/scanRunIdentity.js", import.meta.url),
  "utf8",
);
const scanRunsSource = readFileSync(
  new URL("../../src/lib/scanRuns.js", import.meta.url),
  "utf8",
);
const scanRunSchema = JSON.parse(readFileSync(
  new URL("../../base44/entities/ScanRun.jsonc", import.meta.url),
  "utf8",
));

test("exactly one customer scanner is presented, and it is Standard 150", () => {
  assert.match(scanFormSource, /Standard · 150/);
  assert.equal(scanFormSource.match(/Standard · 150/g).length, 1);
  // No picker: no mode list, no mode array, no mode setter.
  assert.doesNotMatch(scanFormSource, /const SCAN_MODES/);
  assert.doesNotMatch(scanFormSource, /Scan size/);
  assert.doesNotMatch(scanFormSource, /setScanMode/);
});

test("Premium 5,000 is not a selectable scan mode", () => {
  assert.doesNotMatch(scanFormSource, /premium_5000/);
  assert.doesNotMatch(scanFormSource, /Premium · 5,000/);
  // A "coming soon" note elsewhere is allowed; a selectable control is not.
  assert.doesNotMatch(scanFormSource, /onClick=\{\(\) => setScanMode/);
});

test("legacy scan modes are absent from the customer scan component", () => {
  // Comments may name a legacy mode to explain why it is gone; code may not.
  const code = scanFormSource
    .split("\n")
    .filter((line) => !/^\s*(\/\/|\*|\/\*)/.test(line))
    .join("\n");
  for (const legacy of [/"quick"/, /"basic"/, /"deep"/, /"advanced"/, /"full_site"/, /Quick check/, /Full site/]) {
    assert.doesNotMatch(code, legacy);
  }
});

test("standard_150 is the submitted customer mode", () => {
  assert.match(scanFormSource, /const STANDARD_SCAN_MODE = "standard_150"/);
  assert.match(scanFormSource, /const scanMode = STANDARD_SCAN_MODE/);
  assert.match(scanFormSource, /scan_mode: scanMode/);
  // The frontend must never send the Python compatibility alias.
  assert.doesNotMatch(scanFormSource, /scan_mode: "advanced"/);
});

test("standard_150 is the persisted and canonical customer mode", () => {
  assert.match(scanRunIdentitySource, /export const STANDARD_SCAN_MODE = "standard_150"/);
  assert.match(scanRunIdentitySource, /String\(value \|\| STANDARD_SCAN_MODE\)/);
  assert.match(scanRunIdentitySource, /mode === "advanced" \? STANDARD_SCAN_MODE : mode/);
  assert.match(scanRunsSource, /scan_mode: normalizeScanMode\(run\.scan_mode\)/);
  assert.doesNotMatch(scanRunsSource, /scan_mode: run\.scan_mode \|\| "advanced"/);
});

test("the durable schema accepts new Standard 150 scans without breaking legacy history", () => {
  const modeSchema = scanRunSchema.properties.scan_mode;
  assert.equal(modeSchema.default, "standard_150");
  assert.ok(modeSchema.enum.includes("standard_150"));
  for (const legacyMode of ["basic", "quick", "deep", "advanced"]) {
    assert.ok(modeSchema.enum.includes(legacyMode));
  }
});

test("historical non-advanced records stay readable as their original mode", () => {
  // normalizeScanMode only rewrites the retired "advanced" alias; quick/basic/
  // deep must survive so old records still load.
  assert.doesNotMatch(scanRunIdentitySource, /mode === "quick" \?/);
  assert.doesNotMatch(scanRunIdentitySource, /mode === "deep" \?/);
  assert.doesNotMatch(scanRunIdentitySource, /mode === "basic" \?/);
});

test("the customer request requires Python and forbids the Deno fallback", () => {
  assert.match(scanFormSource, /require_python_scanner: true/);
  assert.match(scanFormSource, /allow_deno_fallback: false/);
  assert.doesNotMatch(scanFormSource, /require_python_scanner: false/);
  assert.doesNotMatch(scanFormSource, /allow_deno_fallback: true/);
});

test("robots are always respected", () => {
  assert.match(scanFormSource, /respect_robots_txt: true/);
  assert.doesNotMatch(scanFormSource, /respect_robots_txt: false/);
});

test("the page cap is 150 and is not customer-controlled", () => {
  assert.match(scanFormSource, /const STANDARD_SCAN_BUDGET = Object\.freeze\(\{ max_pages: 150/);
  assert.match(scanFormSource, /const safeScanBudget = STANDARD_SCAN_BUDGET/);
  assert.match(scanFormSource, /max_pages: safeScanBudget\.max_pages/);
  // The retired per-mode budget helper must be gone.
  assert.doesNotMatch(scanFormSource, /function getSafeScanBudget/);
  assert.doesNotMatch(scanFormSource, /max_pages: 85/);
  assert.doesNotMatch(scanFormSource, /max_pages: 40/);
});

test("the customer scan is routed to the Standard 150 Python-only gateway", () => {
  assert.match(scanFormSource, /const STANDARD_SCANNER_FUNCTION = "runStandard150Scan"/);
  assert.match(scanFormSource, /callBase44Function\(STANDARD_SCANNER_FUNCTION, scanPayload\)/);
  assert.doesNotMatch(scanFormSource, /"runAdvancedScan"/);
});

test("scan identity, duplicate-submit protection and failure handling stay intact", () => {
  assert.match(scanFormSource, /submitLockRef/);
  assert.match(scanFormSource, /requestEpochRef/);
  assert.match(scanFormSource, /await beginScanRun/);
  assert.match(scanFormSource, /canonicalMode: scanMode/);
  // Identity must be persisted before any scanner network work.
  assert.ok(
    scanFormSource.indexOf("await beginScanRun")
      < scanFormSource.indexOf("callBase44Function(STANDARD_SCANNER_FUNCTION"),
  );
  // A failed scan must not leave a stale result behind.
  assert.match(scanFormSource, /clear_previous_scan: true/);
  assert.match(scanFormSource, /failScanRun/);
});
