import assert from "node:assert/strict";
import test from "node:test";

import {
  buildFixListPresentation,
  repairRowModel,
  repairScopeSummary,
  sectionCustomerRepairs,
} from "../../src/lib/repairPresentation.js";
import { REPAIR_PRESENTATION_MODES } from "../../src/lib/repairContractPresentation.js";


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


test("canonical sections activate only for a fully supported persisted repair contract", () => {
  const plan = buildFixListPresentation([
    {
      id: "urgent",
      title: "Fix homepage noindex",
      repair_contract_version: "repair_contract_v1_shadow",
      action_priority: "fix_first",
    },
    {
      id: "important",
      title: "Fix redirected navigation",
      repair_contract_version: "repair_contract_v1_shadow",
      action_priority: "important",
    },
  ]);

  assert.equal(plan.mode, REPAIR_PRESENTATION_MODES.CANONICAL);
  assert.equal(plan.canonical, true);
  assert.equal(plan.unsupported, false);
  assert.equal(plan.legacyItems.length, 0);
  assert.equal(plan.sections.map((section) => section.key).join(","), "fix_first,important");
});


test("historical repairs without a contract stay in frozen legacy presentation", () => {
  const legacyItems = [
    { id: "old-high", priority: "high", action_priority: "review" },
    { id: "old-low", priority: "low", action_priority: "fix_first" },
  ];
  const plan = buildFixListPresentation(legacyItems);

  assert.equal(plan.mode, REPAIR_PRESENTATION_MODES.LEGACY);
  assert.equal(plan.canonical, false);
  assert.equal(plan.sections.length, 0);
  assert.deepEqual(plan.legacyItems, legacyItems);
});


test("unknown future contracts fail closed instead of being silently re-ranked", () => {
  const item = {
    id: "future",
    repair_contract_version: "repair_contract_v9_future",
    action_priority: "fix_first",
  };
  const plan = buildFixListPresentation([item]);

  assert.equal(plan.mode, REPAIR_PRESENTATION_MODES.UNSUPPORTED);
  assert.equal(plan.unsupported, true);
  assert.equal(plan.sections.length, 0);
  assert.deepEqual(plan.legacyItems, [item]);
});


test("mixed historical and canonical rows use one legacy authority for the whole saved list", () => {
  const canonical = {
    id: "new",
    repair_contract_version: "repair_contract_v1_shadow",
    action_priority: "fix_first",
  };
  const legacy = { id: "old", priority: "high" };
  const plan = buildFixListPresentation([canonical, legacy]);

  assert.equal(plan.mode, REPAIR_PRESENTATION_MODES.LEGACY);
  assert.equal(plan.canonical, false);
  assert.equal(plan.sections.length, 0);
  assert.deepEqual(plan.legacyItems, [canonical, legacy]);
});
