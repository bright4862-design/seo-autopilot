import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const app = readFileSync("src/App.jsx", "utf8");
const submit = readFileSync("src/components/scan/ScanWebsiteForm.jsx", "utf8");
const fixList = readFileSync("src/pages/FixList.jsx", "utf8");

test("legacy aiReviewScan authority path is unreachable from Standard 150 beta routes", () => {
  assert.doesNotMatch(app, /import\s+CrawlStatus/);
  assert.match(app, /path="\/crawl-status"[\s\S]*?<Navigate to="\/onboarding" replace \/>/);
  assert.doesNotMatch(submit, /functions\.invoke\(["']aiReviewScan["']/);
  assert.doesNotMatch(fixList, /functions\.invoke\(["']aiReviewScan["']/);
});
