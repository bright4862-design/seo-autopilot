import assert from "node:assert/strict";
import test from "node:test";

import {
  repairRowModel,
  repairScopeSummary,
  sectionCustomerRepairs,
} from "../../src/lib/repairPresentation.js";


test("sample-qualified searchable coverage is shown without implying whole-site coverage", () => {
  const item = {
    id: "canonicals",
    title: "Fix product-page canonicals",
    action_priority: "fix_first",
    page_template_family: "product_page",
    priority_reason: "18 of 20 searchable product pages checked are affected.",
    priority_context: {
      indexable_affected: 18,
      indexable_checked_eligible: 20,
      affected_checked: 18,
      checked_eligible: 24,
    },
  };

  const model = repairRowModel(item);
  assert.equal(model.sectionLabel, "Fix first");
  assert.equal(model.surface, "Product pages");
  assert.equal(model.scope, "18 of 20 searchable pages checked");
  assert.equal(model.reason, "18 of 20 searchable product pages checked are affected.");
});


test("raw affected-page fallback stays simple when eligible denominator is unknown", () => {
  assert.equal(repairScopeSummary({ affected_pages: ["/a", "/b", "/c"] }), "3 pages");
});


test("fix-first section shows three initially without demoting additional urgent work", () => {
  const items = Array.from({ length: 5 }, (_, index) => ({
    id: `urgent-${index + 1}`,
    title: `Urgent ${index + 1}`,
    action_priority: "fix_first",
  }));
  items.push({ id: "later", title: "Later", action_priority: "improve" });

  const sections = sectionCustomerRepairs(items, { initialFixFirstLimit: 3 });
  const urgent = sections.find((section) => section.key === "fix_first");
  const improve = sections.find((section) => section.key === "improve");

  assert.equal(urgent.totalCount, 5);
  assert.equal(urgent.rows.length, 3);
  assert.equal(urgent.hiddenCount, 2);
  assert.equal(urgent.hiddenRows.length, 2);
  assert.equal(improve.totalCount, 1);
});


test("repair leverage is display metadata only when explicitly confirmed", () => {
  const unconfirmed = repairRowModel({
    id: "pattern",
    title: "Fix redirected navigation links",
    action_priority: "important",
    affected_pages: ["/a", "/b"],
    shared_repair_confirmed: false,
  });
  const confirmed = repairRowModel({
    id: "shared",
    title: "Fix redirected navigation links",
    action_priority: "important",
    affected_pages: ["/a", "/b"],
    repair_surface: "shared_navigation",
    shared_repair_confirmed: true,
  });

  assert.equal(unconfirmed.sharedRepairConfirmed, false);
  assert.equal(confirmed.sharedRepairConfirmed, true);
  assert.equal(confirmed.surface, "Shared Navigation");
});
