import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(
  new URL("../../src/components/scan/ScanWebsiteForm.jsx", import.meta.url),
  "utf8",
);

test("ScanWebsiteForm delegates active-scan presentation to truthful durable progress", () => {
  assert.match(source, /import DurableScanProgressSurface from "@\/components\/scan\/DurableScanProgressSurface"/);
  assert.match(source, /<DurableScanProgressSurface/);
  assert.match(source, /durableScan=\{durableScan\}/);
  assert.match(source, /backgroundExecutionProven=\{Boolean\(watchedScanId\)\}/);
  assert.match(source, /onOpenSavedScan=\{watchedScanId/);
});

test("ScanWebsiteForm does not use discovery or the 150-page cap as a progress denominator", () => {
  assert.doesNotMatch(source, /pages discovered/);
  assert.doesNotMatch(source, /of \$\{STANDARD_SCAN_BUDGET\.max_pages\} checked/);
  assert.doesNotMatch(source, /SCAN_PROGRESS_STEPS/);
  assert.doesNotMatch(source, /scanProgressIndex\(/);
});

test("leave-page reassurance is not promised before durable acceptance", () => {
  assert.doesNotMatch(source, /You can leave this page — we’ll save your list/);
  assert.match(source, /FixList will tell you when it’s safe to leave this page/);
  assert.match(source, /setWatchedScanId\(scanId\)/);
  assert.ok(source.indexOf("setWatchedScanId(scanId)") > source.indexOf("jobData?.accepted === true"));
});
