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
  // The selection card is gone: with a single scanner there is nothing to
  // select, and a highlighted "chosen" card implied a choice that never
  // existed. Scope is now stated once, as plain text.
  assert.match(scanFormSource, /Scan depth: up to 150 pages · respects robots\.txt · read-only/);
  assert.equal(scanFormSource.match(/SCAN_SPEC_LINE/g).length, 2); // definition + single render
  assert.doesNotMatch(scanFormSource, /Standard · 150/);
  // No picker: no mode list, no mode array, no mode setter.
  assert.doesNotMatch(scanFormSource, /const SCAN_MODES/);
  assert.doesNotMatch(scanFormSource, /Scan size/);
  assert.doesNotMatch(scanFormSource, /setScanMode/);
});

test("no selectable scan-size control exists in the rendered DOM", () => {
  // The only <select> on the page is the optional CMS field.
  assert.equal((scanFormSource.match(/<select/g) || []).length, 1);
  assert.match(scanFormSource, /id="fixlist-cms"/);
  assert.doesNotMatch(scanFormSource, /type="range"|role="slider"|<Slider/);
  for (const legacy of ["Quick", "Basic", "Deep", "Advanced", "Full Site"]) {
    assert.doesNotMatch(
      scanFormSource,
      new RegExp(`>\\s*${legacy}\\b|"${legacy}"\\s*[,}\\]]`),
      `legacy scan-size string must not render: ${legacy}`,
    );
  }
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

test("the customer scan is routed through the Standard 150 server admission dispatcher", () => {
  assert.match(scanFormSource, /const ASYNC_SCAN_JOB_FUNCTION = "startStandardScanJob"/);
  assert.match(scanFormSource, /submitStandardScanJob\(scanPayload\)/);
  assert.match(scanFormSource, /require_python_scanner: true/);
  assert.match(scanFormSource, /allow_deno_fallback: false/);
  assert.doesNotMatch(scanFormSource, /const STANDARD_SCANNER_FUNCTION|callBase44Function\(STANDARD_SCANNER_FUNCTION/);
});

test("scan identity and duplicate-submit protection stay intact while failure ownership is server-side", () => {
  assert.match(scanFormSource, /submitLockRef/);
  assert.match(scanFormSource, /requestEpochRef/);
  assert.match(scanFormSource, /const requestId = createScanRequestId\(\)/);
  assert.match(scanFormSource, /canonicalMode: scanMode/);
  assert.match(scanFormSource, /assertServerAdmissionIdentity\(jobData/);
  assert.match(scanFormSource, /clear_previous_scan: true/);
  const submitStart = scanFormSource.indexOf("async function handleSubmit");
  const submitEnd = scanFormSource.indexOf("\n  return (", submitStart);
  const submitSource = scanFormSource.slice(submitStart, submitEnd);
  assert.doesNotMatch(submitSource, /beginScanRun|failScanRun|cancelScanRun|completeScanRun/);
  assert.match(submitSource, /async_job_browser_error_no_terminal_write/);
});
