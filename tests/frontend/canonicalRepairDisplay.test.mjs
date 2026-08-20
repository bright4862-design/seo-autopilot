import assert from "node:assert/strict";
import test from "node:test";

import { canonicalRepairDisplayModel } from "../../src/lib/canonicalRepairDisplay.js";
import { repairRowModel } from "../../src/lib/repairPresentation.js";

const V2 = "repair_contract_v2_shadow_calibrated";

function persistedV2(overrides = {}) {
  return {
    id: "repair-1",
    rule: "internal_link_redirect",
    repair_contract_version: V2,
    repair_snapshot_contract_version: V2,
    repair_snapshot_contract_complete: true,
    action_priority: "important",
    priority_reason: "Persisted reason.",
    evidence_class: "improvement",
    repair_surface: "shared_navigation",
    affected_pages: ["/a"],
    priority_context: {
      affected_checked: 1,
      checked_eligible: 1,
    },
    repair_verification_state: "ready_to_verify",
    shared_repair_confirmed: false,
    ...overrides,
  };
}

test("canonical normalized row keeps persisted evidence while allowing friendly title copy", () => {
  const original = persistedV2();
  const item = {
    id: "repair-1",
    rule: "internal_link_redirect",
    action_priority: "important",
    title: "Fix the navigation links",
    evidence_class: "confirmed_problem",
    repair_surface: "homepage",
    affected_pages: ["/a", "/b", "/c"],
    priority_context: {
      affected_checked: 3,
      checked_eligible: 3,
    },
    repair_verification_state: "verified_fixed",
    shared_repair_confirmed: true,
    original,
  };

  const model = canonicalRepairDisplayModel(item, repairRowModel(item));

  assert.equal(model.title, "Fix the navigation links");
  assert.equal(model.surface, "Shared navigation");
  assert.equal(model.scope, "1 of 1 relevant pages checked");
  assert.equal(model.reason, "Persisted reason.");
  assert.equal(model.evidenceClass, "improvement");
  assert.equal(model.evidenceLabel, "Improvement");
  assert.equal(model.verification, "Ready to verify with a rescan");
  assert.equal(model.affectedPageCount, 1);
  assert.equal(model.sharedRepairConfirmed, false);
  assert.equal(model.leverage, "");
});

test("browser verification mutation cannot manufacture Verified fixed for a canonical repair", () => {
  const original = persistedV2({ repair_verification_state: "could_not_verify" });
  const item = {
    id: "repair-1",
    rule: "internal_link_redirect",
    action_priority: "important",
    repair_verification_state: "verified_fixed",
    original,
  };

  assert.equal(canonicalRepairDisplayModel(item).verification, "Could not verify");
});

test("browser evidence mutation cannot upgrade a canonical improvement into a confirmed problem", () => {
  const original = persistedV2({ evidence_class: "improvement" });
  const item = {
    id: "repair-1",
    rule: "internal_link_redirect",
    action_priority: "important",
    evidence_class: "confirmed_problem",
    original,
  };

  const model = canonicalRepairDisplayModel(item);
  assert.equal(model.evidenceClass, "improvement");
  assert.equal(model.evidenceLabel, "Improvement");
});

test("canonical review opportunities are labeled only from persisted evidence class", () => {
  const model = canonicalRepairDisplayModel(persistedV2({ evidence_class: "opportunity" }));
  assert.equal(model.evidenceClass, "opportunity");
  assert.equal(model.evidenceLabel, "Review opportunity");
});

test("canonical raw affected-page counts are explicitly qualified as scan evidence", () => {
  const item = persistedV2({
    affected_pages: ["/a", "/b", "/c"],
    priority_context: {},
  });

  assert.equal(
    canonicalRepairDisplayModel(item).scope,
    "3 affected pages found in this scan",
  );
});

test("canonical eligible-denominator scope keeps its stronger checked-page wording", () => {
  assert.equal(
    canonicalRepairDisplayModel(persistedV2()).scope,
    "1 of 1 relevant pages checked",
  );
});

test("canonical technical surface identifiers use customer-readable labels", () => {
  assert.equal(
    canonicalRepairDisplayModel(persistedV2({ repair_surface: "xml_sitemap" })).surface,
    "XML sitemap",
  );
  assert.equal(
    canonicalRepairDisplayModel(persistedV2({ repair_surface: "cms_field" })).surface,
    "CMS field",
  );
  assert.equal(
    canonicalRepairDisplayModel(persistedV2({ repair_surface: "redirect_server_config" })).surface,
    "Redirect/server config",
  );
});

test("legacy rows retain their existing display evidence", () => {
  const legacy = {
    id: "legacy",
    title: "Legacy repair",
    repair_surface: "homepage",
    affected_pages: ["/a", "/b"],
    repair_verification_state: "verified_fixed",
  };

  const model = canonicalRepairDisplayModel(legacy);
  assert.equal(model.surface, "Homepage");
  assert.equal(model.scope, "2 pages");
  assert.equal(model.verification, "Verified fixed");
  assert.equal(model.evidenceLabel, undefined);
});
