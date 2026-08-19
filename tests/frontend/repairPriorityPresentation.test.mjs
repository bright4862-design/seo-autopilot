import assert from "node:assert/strict";
import test from "node:test";

import {
  mergeSameActionFixes,
  prepareCustomerFixes,
  priorityBucket,
  rankFixesForCustomer,
} from "../../src/lib/fixRanking.js";
import { REPAIR_PRESENTATION_MODES } from "../../src/lib/repairContractPresentation.js";

const V2 = "repair_contract_v2_shadow_calibrated";

function attestedV2(overrides = {}) {
  return {
    repair_contract_version: V2,
    repair_snapshot_contract_version: V2,
    repair_snapshot_contract_complete: true,
    ...overrides,
  };
}


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


test("fully canonical v2 snapshot bypasses browser merge and ranking", () => {
  const first = attestedV2({
    id: "server-second-band",
    rule: "missing_h1",
    page_template_family: "product_page",
    recommended_value: "Add one clear H1.",
    action_priority: "important",
    action_priority_score: 100,
    affected_pages: ["/products/a"],
  });
  const second = attestedV2({
    id: "server-first-band",
    rule: "missing_h1",
    page_template_family: "product_page",
    recommended_value: "Add one clear H1.",
    action_priority: "fix_first",
    action_priority_score: 9999,
    affected_pages: ["/products/b"],
  });

  const prepared = prepareCustomerFixes([first, second]);

  assert.deepEqual(prepared.map((item) => item.id), ["server-second-band", "server-first-band"]);
  assert.equal(prepared.length, 2, "browser must not merge canonical persisted repairs");
  assert.ok(prepared.every((item) => item.repair_snapshot_presentation_mode === REPAIR_PRESENTATION_MODES.CANONICAL));
  assert.ok(prepared.every((item) => item.groupedFindingCount === undefined));
});


test("unsupported versioned snapshot also bypasses browser synthesis", () => {
  const prepared = prepareCustomerFixes([
    {
      id: "v1-a",
      repair_contract_version: "repair_contract_v1_shadow",
      rule: "missing_h1",
      page_template_family: "product_page",
      recommended_value: "Add one clear H1.",
      affected_pages: ["/a"],
    },
    {
      id: "v1-b",
      repair_contract_version: "repair_contract_v1_shadow",
      rule: "missing_h1",
      page_template_family: "product_page",
      recommended_value: "Add one clear H1.",
      affected_pages: ["/b"],
    },
  ]);

  assert.deepEqual(prepared.map((item) => item.id), ["v1-a", "v1-b"]);
  assert.equal(prepared.length, 2);
  assert.ok(prepared.every((item) => item.repair_snapshot_presentation_mode === REPAIR_PRESENTATION_MODES.UNSUPPORTED));
});


test("mixed or transitional versioned snapshot preserves persisted rows even when presentation falls back to legacy", () => {
  const prepared = prepareCustomerFixes([
    {
      id: "transitional-v2",
      repair_contract_version: V2,
      rule: "missing_h1",
      page_template_family: "product_page",
      recommended_value: "Add one clear H1.",
      affected_pages: ["/a"],
    },
    {
      id: "historical-row",
      priority: "high",
      rule: "missing_h1",
      page_template_family: "product_page",
      recommended_value: "Add one clear H1.",
      affected_pages: ["/b"],
    },
  ]);

  assert.deepEqual(prepared.map((item) => item.id), ["transitional-v2", "historical-row"]);
  assert.equal(prepared.length, 2);
  assert.ok(prepared.every((item) => item.repair_snapshot_presentation_mode === REPAIR_PRESENTATION_MODES.LEGACY));
});


test("true unversioned legacy snapshots retain historical browser synthesis", () => {
  const prepared = prepareCustomerFixes([
    {
      id: "legacy-low",
      priority: "low",
      rule: "missing_h1",
      page_template_family: "product_page",
      recommended_value: "Add one clear H1.",
      affected_pages: ["/a"],
    },
    {
      id: "legacy-high",
      priority: "high",
      rule: "canonical_missing",
      page_template_family: "homepage",
      recommended_value: "Add canonical.",
      affected_pages: ["/"],
    },
  ]);

  assert.deepEqual(prepared.map((item) => item.id), ["legacy-high", "legacy-low"]);
  assert.ok(prepared.every((item) => item.repair_snapshot_presentation_mode === REPAIR_PRESENTATION_MODES.LEGACY));
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
