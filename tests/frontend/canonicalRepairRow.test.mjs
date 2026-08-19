import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(
  new URL("../../src/components/fixlist/CanonicalRepairRow.jsx", import.meta.url),
  "utf8",
);

test("canonical repair row consumes the presentation model instead of legacy priority labels", () => {
  assert.match(source, /repairRowModel/);
  assert.match(source, /model\.title/);
  assert.match(source, /model\.surface/);
  assert.match(source, /model\.scope/);
  assert.match(source, /model\.reason/);
  assert.match(source, /model\.verification/);
  assert.doesNotMatch(source, /customerPriorityLabel/);
  assert.doesNotMatch(source, /item\.priority/);
});

test("canonical repair row is presentation-only and receives optional details from its parent", () => {
  assert.match(source, /typeof renderDetails === "function"/);
  assert.match(source, /renderDetails\(\{ item, model \}\)/);
  assert.doesNotMatch(source, /fetch\(/);
  assert.doesNotMatch(source, /base44/);
  assert.doesNotMatch(source, /ScanRun/);
});
