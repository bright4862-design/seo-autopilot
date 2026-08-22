import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync("src/pages/FixList.jsx", "utf8");

test("scan coverage copy pluralizes page counts", () => {
  const summary = source.match(/function getBestSummary[\s\S]*?\n\}/)?.[0] || "";
  assert.match(summary, /Number\(count\) === 1 \? "page" : "pages"/);
  assert.doesNotMatch(summary, /formatCount\(pagesFound\)\} pages/);
  assert.doesNotMatch(summary, /formatCount\(pagesScanned\)\} representative pages/);
});
