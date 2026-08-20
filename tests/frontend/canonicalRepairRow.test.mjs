import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(
  new URL("../../src/components/fixlist/CanonicalRepairRow.jsx", import.meta.url),
  "utf8",
);

test("canonical repair row consumes the persisted-authority presentation seam instead of legacy priority labels", () => {
  assert.match(source, /canonicalRepairDisplayModel/);
  assert.match(source, /model\.title/);
  assert.match(source, /model\.surface/);
  assert.match(source, /model\.scope/);
  assert.match(source, /model\.reason/);
  assert.match(source, /model\.verification/);
  assert.doesNotMatch(source, /customerPriorityLabel/);
  assert.doesNotMatch(source, /item\.priority/);
});

test("canonical priority reason is labeled for non-SEO users", () => {
  assert.match(source, /Why this is here ·/);
  assert.match(source, /\{model\.reason\}/);
});

test("canonical repair row is presentation-only and receives optional details from its parent", () => {
  assert.match(source, /typeof renderDetails === "function"/);
  assert.match(source, /renderDetails\(\{ item, model \}\)/);
  assert.doesNotMatch(source, /fetch\(/);
  assert.doesNotMatch(source, /base44/);
  assert.doesNotMatch(source, /ScanRun/);
});

test("repair evidence disclosure has an accessible control-region relationship", () => {
  assert.match(source, /useId/);
  assert.match(source, /aria-controls=\{hasDetails \? disclosureId/);
  assert.match(source, /aria-expanded=\{hasDetails \? open/);
  assert.match(source, /id=\{disclosureId\}/);
  assert.match(source, /role="region"/);
  assert.match(source, /Evidence and steps for/);
  assert.match(source, /Hide evidence & steps/);
});

test("mobile repair disclosure keeps a minimum touch target", () => {
  assert.match(source, /min-h-11/);
});
