import assert from "node:assert/strict";
import test from "node:test";

import {
  mergeSameActionFixes,
  priorityBucket,
  rankFixesForCustomer,
} from "../../src/lib/fixRanking.js";


test("contextual action priority outranks raw page count", () => {
  const ranked = rankFixesForCustomer([
    {
      id: "volume",
      priority: "high",
      action_priority: "important",
      action_priority_score: 3300,
      affected_pages: Array.from({ length: 80 }, (_, index) => `/archive/${index}`),
    },
    {
      id: "indexing",
      priority: "critical",
      action_priority: "fix_first",
      action_priority_score: 4410,
      affected_pages: ["/"],
    },
  ]);

  assert.equal(ranked[0].id, "indexing");
  assert.equal(ranked[1].id, "volume");
});


test("action score only orders repairs inside the same action band", () => {
  const ranked = rankFixesForCustomer([
    { id: "low-score-fix-first", priority: "high", action_priority: "fix_first", action_priority_score: 4010 },
    { id: "high-score-important", priority: "critical", action_priority: "important", action_priority_score: 9999 },
  ]);

  assert.equal(ranked[0].id, "low-score-fix-first");
});


test("page family plus identical recommendation does not imply one shared implementation change", () => {
  const merged = mergeSameActionFixes([
    {
      id: "a",
      rule: "missing_h1",
      page_template_family: "product_page",
      recommended_value: "Add one clear H1.",
      affected_pages: ["/products/a"],
      priority: "medium",
    },
    {
      id: "b",
      rule: "missing_h1",
      page_template_family: "product_page",
      recommended_value: "Add one clear H1.",
      affected_pages: ["/products/b"],
      priority: "medium",
    },
  ]);

  assert.equal(merged.length, 1);
  assert.equal(merged[0].groupedFindingCount, 2);
  assert.equal(merged[0].sharedRepairConfirmed, false);
  assert.match(merged[0].groupingExplanation, /has not assumed that one implementation change fixes every page/i);
  assert.doesNotMatch(merged[0].groupingExplanation, /one shared change may improve/i);
});


test("explicit shared repair evidence permits leverage language", () => {
  const merged = mergeSameActionFixes([
    {
      id: "a",
      rule: "internal_link_redirect",
      page_template_family: "navigation",
      recommended_value: "Point shared navigation links at the final URL.",
      affected_pages: ["/a"],
      priority: "high",
      shared_repair_confirmed: true,
    },
    {
      id: "b",
      rule: "internal_link_redirect",
      page_template_family: "navigation",
      recommended_value: "Point shared navigation links at the final URL.",
      affected_pages: ["/b"],
      priority: "high",
      shared_repair_confirmed: true,
    },
  ]);

  assert.equal(merged.length, 1);
  assert.equal(merged[0].sharedRepairConfirmed, true);
  assert.match(merged[0].groupingExplanation, /one shared change may improve 2 affected pages/i);
});


test("legacy section buckets stay unchanged until the FixList page migration", () => {
  assert.equal(priorityBucket("critical"), "fix_first");
  assert.equal(priorityBucket("high"), "fix_first");
  assert.equal(priorityBucket("medium"), "improve_next");
  assert.equal(priorityBucket("low"), "worth_checking");
});


test("object bucket reads the new contextual action priority", () => {
  assert.equal(priorityBucket({ priority: "critical", action_priority: "important" }), "important");
  assert.equal(priorityBucket({ priority: "medium", action_priority: "review" }), "review");
});
