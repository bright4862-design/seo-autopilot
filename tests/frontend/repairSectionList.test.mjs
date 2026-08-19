import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(
  new URL("../../src/components/fixlist/RepairSectionList.jsx", import.meta.url),
  "utf8",
);

test("canonical section list renders compact repair rows and keeps full detail behind expansion", () => {
  assert.match(source, /CanonicalRepairRow/);
  assert.match(source, /renderDetails=\{\(\) => renderRow\(row, index\)\}/);
  assert.doesNotMatch(source, /customerPriorityLabel/);
  assert.doesNotMatch(source, /priorityBucket/);
  assert.doesNotMatch(source, /fetch\(/);
  assert.doesNotMatch(source, /base44/);
});

test("additional Fix first repairs remain in Fix first behind reversible overflow controls", () => {
  assert.match(source, /section\.key === "fix_first" && showAllFixFirst/);
  assert.match(source, /section\.hiddenRows/);
  assert.match(source, /View \{hiddenCount\} more Fix first/);
  assert.match(source, /setShowAllFixFirst\(true\)/);
  assert.match(source, /Show fewer Fix first repairs/);
  assert.match(source, /setShowAllFixFirst\(false\)/);
});

test("section component consumes already-authoritative sections instead of reranking repairs", () => {
  assert.match(source, /receives already/);
  assert.doesNotMatch(source, /action_priority_score/);
  assert.doesNotMatch(source, /base_severity/);
  assert.doesNotMatch(source, /sort\(/);
});
