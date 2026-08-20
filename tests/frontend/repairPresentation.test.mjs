import assert from "node:assert/strict";
import test from "node:test";

import { prepareCustomerFixes } from "../../src/lib/fixRanking.js";
import {
  buildFixListPresentation,
  repairRowModel,
  repairScopeSummary,
  sectionCustomerRepairs,
} from "../../src/lib/repairPresentation.js";
import { REPAIR_PRESENTATION_MODES } from "../../src/lib/repairContractPresentation.js";

const V2 = "repair_contract_v2_shadow_calibrated";

function attestedV2(overrides = {}) {
  return {
    repair_contract_version: V2,
    repair_snapshot_contract_version: V2,
    repair_snapshot_contract_complete: true,
    priority_reason: "Persisted canonical priority reason.",
    evidence_class: "confirmed_problem",
    ...overrides,
  };
}


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


test("incomparable versioned history is presented as could not compare", () => {
  const model = repairRowModel({
    id: "history",
    action_priority: "important",
    repair_verification_state: "could_not_verify",
    comparison_contract_state: "incomparable",
  });

  assert.equal(model.verification, "Could not compare");
});


test("ordinary verification uncertainty remains could not verify", () => {
  const model = repairRowModel({
    id: "history",
    action_priority: "important",
    repair_verification_state: "could_not_verify",
  });

  assert.equal(model.verification, "Could not verify");
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


test("canonical sections activate only for a fully snapshot-attested persisted repair contract", () => {
  const plan = buildFixListPresentation([
    attestedV2({
      id: "urgent",
      title: "Fix homepage noindex",
      action_priority: "fix_first",
    }),
    attestedV2({
      id: "important",
      title: "Fix redirected navigation",
      action_priority: "important",
    }),
  ]);

  assert.equal(plan.mode, REPAIR_PRESENTATION_MODES.CANONICAL);
  assert.equal(plan.canonical, true);
  assert.equal(plan.unsupported, false);
  assert.equal(plan.legacyItems.length, 0);
  assert.equal(plan.sections.map((section) => section.key).join(","), "fix_first,important");
});


test("supported row contracts without snapshot attestation stay legacy", () => {
  const plan = buildFixListPresentation([
    { id: "row-only", repair_contract_version: V2, action_priority: "fix_first" },
  ]);
  assert.equal(plan.mode, REPAIR_PRESENTATION_MODES.LEGACY);
  assert.equal(plan.canonical, false);
  assert.equal(plan.sections.length, 0);
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
  const canonical = attestedV2({
    id: "new",
    action_priority: "fix_first",
  });
  const legacy = { id: "old", priority: "high" };
  const plan = buildFixListPresentation([canonical, legacy]);

  assert.equal(plan.mode, REPAIR_PRESENTATION_MODES.LEGACY);
  assert.equal(plan.canonical, false);
  assert.equal(plan.sections.length, 0);
  assert.deepEqual(plan.legacyItems, [canonical, legacy]);
});


test("explicit workflow filters cannot change durable snapshot repair-contract authority", () => {
  const canonicalA = attestedV2({ id: "canonical-a", action_priority: "fix_first" });
  const canonicalB = attestedV2({ id: "canonical-b", action_priority: "important" });
  const legacyIncompatible = { id: "legacy", priority: "high" };
  const snapshot = [canonicalA, canonicalB, legacyIncompatible];

  // Simulate the incompatible card being marked Done. It disappears from the
  // visible work queue, but remains part of the immutable saved FixList snapshot.
  const plan = buildFixListPresentation(snapshot, {
    visibleItems: [canonicalA, canonicalB],
    initialFixFirstLimit: 3,
  });

  assert.equal(plan.snapshotCount, 3);
  assert.equal(plan.visibleCount, 2);
  assert.equal(plan.mode, REPAIR_PRESENTATION_MODES.LEGACY);
  assert.equal(plan.canonical, false);
  assert.equal(plan.sections.length, 0);
  assert.deepEqual(plan.legacyItems, [canonicalA, canonicalB]);
});


test("current FixList prepare/filter path keeps hidden incompatible rows in snapshot authority", () => {
  const canonicalA = attestedV2({
    id: "canonical-a",
    rule: "canonical_missing",
    page_template_family: "product_page",
    recommendation: "Add a self canonical",
    action_priority: "fix_first",
  });
  const canonicalB = attestedV2({
    id: "canonical-b",
    rule: "redirect_chain",
    page_template_family: "homepage",
    recommendation: "Point directly to the final URL",
    action_priority: "important",
  });
  const legacy = {
    id: "legacy",
    rule: "missing_h1",
    page_template_family: "guide_article",
    recommendation: "Add an H1",
    priority: "high",
  };

  const prepared = prepareCustomerFixes([canonicalA, canonicalB, legacy]);
  assert.ok(prepared.every((item) => item.repair_snapshot_presentation_mode === REPAIR_PRESENTATION_MODES.LEGACY));

  // This mirrors the current page: Done state filters the already-prepared list,
  // then buildFixListPresentation receives only active rows.
  const visible = prepared.filter((item) => item.id !== "legacy");
  const plan = buildFixListPresentation(visible, { initialFixFirstLimit: 3 });

  assert.equal(visible.length, 2);
  assert.equal(plan.mode, REPAIR_PRESENTATION_MODES.LEGACY);
  assert.equal(plan.canonical, false);
  assert.equal(plan.sections.length, 0);
  assert.deepEqual(plan.legacyItems.map((item) => item.id), ["canonical-a", "canonical-b"]);
});


test("current FixList prepare/filter path keeps canonical authority when the full snapshot is attested", () => {
  const snapshot = [
    attestedV2({
      id: "a",
      rule: "canonical_missing",
      page_template_family: "product_page",
      recommendation: "Add canonical",
      action_priority: "fix_first",
    }),
    attestedV2({
      id: "b",
      rule: "redirect_chain",
      page_template_family: "homepage",
      recommendation: "Remove redirect hop",
      action_priority: "important",
    }),
  ];
  const prepared = prepareCustomerFixes(snapshot);
  assert.ok(prepared.every((item) => item.repair_snapshot_presentation_mode === REPAIR_PRESENTATION_MODES.CANONICAL));

  const visible = prepared.filter((item) => item.id !== "b");
  const plan = buildFixListPresentation(visible);
  assert.equal(plan.mode, REPAIR_PRESENTATION_MODES.CANONICAL);
  assert.equal(plan.canonical, true);
  assert.equal(plan.sections.length, 1);
  assert.equal(plan.sections[0].key, "fix_first");
});
