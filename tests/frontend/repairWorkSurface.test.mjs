import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(
  new URL("../../src/components/fixlist/RepairWorkSurface.jsx", import.meta.url),
  "utf8",
);

test("repair work surface delegates canonical active repairs to the compact queue", () => {
  assert.match(source, /presentation\?\.canonical === true && visibleCount > 0/);
  assert.match(source, /<RepairSectionList sections=\{presentation\.sections \|\| \[\]\} renderRow=\{renderRow\} \/>/);
});

test("all-done state requires every saved repair to be explicitly marked done", () => {
  assert.match(source, /snapshotCount > 0/);
  assert.match(source, /visibleCount === 0/);
  assert.match(source, /doneCount === snapshotCount/);
  assert.match(source, /<RepairWorkflowCompleteState/);
  assert.doesNotMatch(source, /all clear|verified fixed|everything is fixed/i);
});

test("zero-repair state delegates to the explicit evidence contract", () => {
  assert.match(source, /if \(snapshotCount === 0\)/);
  assert.match(source, /<ZeroRepairState scan=\{scan\} repairCount=\{0\} \/>/);
});

test("repair work surface is presentation-only and cannot become a second authority", () => {
  assert.doesNotMatch(source, /fetch\(/);
  assert.doesNotMatch(source, /base44/);
  assert.doesNotMatch(source, /rankFixesForCustomer|prepareCustomerFixes|priorityBucket|sectionCustomerRepairs/);
  assert.doesNotMatch(source, /update\(|create\(|delete\(/);
});
