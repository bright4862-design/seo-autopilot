import test from "node:test";
import assert from "node:assert/strict";

import { getPriorityLabel } from "../../src/lib/friendlyLabels.js";
import { normalizeActionPriority } from "../../src/lib/reviewContract.js";

test("compact actions preserve critical priority", () => {
  assert.equal(normalizeActionPriority("critical"), "critical");
  assert.equal(normalizeActionPriority("high"), "high");
  assert.equal(normalizeActionPriority("medium"), "medium");
  assert.equal(normalizeActionPriority("low"), "low");
});

test("unknown compact action priorities fall back safely", () => {
  assert.equal(normalizeActionPriority("urgent"), "medium");
  assert.equal(normalizeActionPriority(""), "medium");
});

test("the customer-facing label contract accepts critical", () => {
  assert.equal(getPriorityLabel("critical"), "High impact");
  assert.equal(getPriorityLabel("high"), "High impact");
});
