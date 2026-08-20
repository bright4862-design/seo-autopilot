import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const rowSource = fs.readFileSync(
  new URL("../../src/components/fixlist/CanonicalRepairRow.jsx", import.meta.url),
  "utf8",
);
const sectionSource = fs.readFileSync(
  new URL("../../src/components/fixlist/RepairSectionList.jsx", import.meta.url),
  "utf8",
);

test("canonical row makes evidence a secondary explicit drill-down", () => {
  assert.match(rowSource, /Evidence & steps/);
  assert.match(rowSource, /Hide evidence & steps/);
  assert.match(rowSource, /border-l border-hairline-soft/);
  assert.match(rowSource, /aria-expanded/);
  assert.doesNotMatch(rowSource, /customerPriorityLabel/);
  assert.doesNotMatch(rowSource, /item\.priority/);
});

test("mobile repair rows stay compact while preserving readable desktop spacing", () => {
  assert.match(rowSource, /py-3\.5/);
  assert.match(rowSource, /sm:py-4/);
  assert.match(sectionSource, /mt-10 sm:mt-12/);
  assert.match(sectionSource, /mt-10 first:mt-0 sm:mt-12/);
});

test("canonical work surface leads with the FixList and separates workflow from verification", () => {
  assert.match(sectionSource, />\s*Your FixList\s*</);
  assert.match(sectionSource, /verifies changes only after a later comparable scan/);
  assert.match(sectionSource, /\{repairCount\} remaining/);
  assert.match(sectionSource, /<h3/);
});

test("priority bands explain customer intent without exposing scoring internals", () => {
  assert.match(sectionSource, /fix_first: "Start here\."/);
  assert.match(sectionSource, /important: "Significant repairs to tackle next\."/);
  assert.match(sectionSource, /improve: "Useful improvements after the important work\."/);
  assert.match(sectionSource, /review: "Worth checking; these may need your judgment\."/);
  assert.doesNotMatch(sectionSource, /action_priority_score/);
  assert.doesNotMatch(sectionSource, /base_severity/);
});

test("section counts describe repairs instead of exposing an unlabeled number", () => {
  assert.match(sectionSource, /totalCount === 1 \? "repair" : "repairs"/);
  assert.match(sectionSource, /View \{hiddenCount\} more Fix first/);
});
