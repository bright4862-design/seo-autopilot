import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const fixListSource = fs.readFileSync(
  new URL("../../src/pages/FixList.jsx", import.meta.url),
  "utf8",
);

test("customer FixList does not offer local-only completion state", () => {
  assert.doesNotMatch(fixListSource, /\bdoneIds\b/);
  assert.doesNotMatch(fixListSource, /\bsetDoneIds\b/);
  assert.doesNotMatch(fixListSource, /\bmarkDone\b/);
  assert.doesNotMatch(fixListSource, /\bundoDone\b/);
  assert.doesNotMatch(fixListSource, /recommendation_marked_reviewed/);
  assert.doesNotMatch(fixListSource, />\s*Mark as done\s*</);
  assert.doesNotMatch(fixListSource, /SectionEyebrow label="Done"/);
  assert.doesNotMatch(fixListSource, /Every fix is marked done/);
});

test("removing local workflow state does not remove the saved repair work surface", () => {
  assert.match(fixListSource, /const active = recommendations;/);
  assert.match(fixListSource, /snapshotItems:\s*recommendations/);
  assert.match(fixListSource, /visibleItems:\s*active/);
  assert.match(fixListSource, /<RepairWorkSurface/);
  assert.match(fixListSource, /<ExplicitPassedChecks scan=\{scanRecord\}/);
  assert.match(fixListSource, /<CmsPicker selectedCms=\{selectedCms\}/);
  assert.match(fixListSource, /Scan again/);
});
