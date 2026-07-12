import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = await readFile(
  new URL("../../src/pages/CrawlStatus.jsx", import.meta.url),
  "utf8",
);

test("dashboard invokes the frozen Python-first scanner", () => {
  assert.match(source, /const SCAN_FUNCTION_NAME = "runAdvancedScan"/);
  assert.doesNotMatch(source, /const SCAN_FUNCTION_NAME = "runRealScan"/);
  assert.match(source, /scanMode === "deep" \? 100000 : 70000/);
});

test("Python Review receives the complete scanner evidence contract", () => {
  assert.match(source, /scan:\s*{\s*\.\.\.scanData/);
  assert.doesNotMatch(source, /raw_fixes:\s*mappedSeoIssues/);
  assert.match(source, /125000,\s*"AI review"/);
});

test("authoritative review results and scores are preserved", () => {
  assert.match(source, /selectFinalReviewFixes\s*\(/);
  assert.match(source, /authoritativeHealthScore \?\?\s*computeSimpleHealthScore/);
  assert.doesNotMatch(
    source,
    /mappedSeoIssues\.length > 0 && finalFixes\.length === 0/,
  );
});

test("stored crawl pages preserve scanner indexability", () => {
  assert.match(source, /typeof page\.indexable === "boolean"/);
  assert.match(source, /\? page\.indexable/);
});
