import test from "node:test";
import assert from "node:assert/strict";

import { getPriorityLabel } from "../../src/lib/friendlyLabels.js";
import { normalizeActionPriority, normalizeReviewScope } from "../../src/lib/reviewContract.js";

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

test("sitewide scope does not masquerade as a template family", () => {
  assert.deepEqual(
    normalizeReviewScope({ page_scope: "sitewide", page_template_family: "loan_program", affected_pages: ["/a", "/b"] }, "standard"),
    { page_scope: "sitewide", page_template_family: "" },
  );
});

test("cross-cutting evidence keeps the mixed compatibility marker", () => {
  assert.deepEqual(
    normalizeReviewScope({ page_template_family: "mixed", affected_pages: ["/a", "/b"] }, "standard"),
    { page_scope: "cross_cutting", page_template_family: "mixed" },
  );
});

test("normal reviewed findings retain their family", () => {
  assert.deepEqual(
    normalizeReviewScope({ page_scope: "family", page_template_family: "loan_program", affected_pages: ["/a", "/b"] }, "standard"),
    { page_scope: "family", page_template_family: "loan_program" },
  );
});

