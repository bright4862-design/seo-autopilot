import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync("src/pages/FixList.jsx", "utf8");

test("the customer summary counts the rendered Fix first band", () => {
  const summary = source.match(/function getBestSummary[\s\S]*?\n\}/)?.[0] || "";

  assert.match(summary, /priorityBucket\(item\) === "fix_first"/);
  assert.match(summary, /in Fix first/);
  assert.doesNotMatch(summary, /\["critical", "high"\]\.includes\(item\.priority\)/);
  assert.doesNotMatch(summary, /should be handled first/);
});
