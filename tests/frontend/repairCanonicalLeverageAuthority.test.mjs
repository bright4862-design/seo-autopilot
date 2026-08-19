import assert from "node:assert/strict";
import test from "node:test";

import {
  repairLeverageSummary,
  repairRowModel,
} from "../../src/lib/repairPresentation.js";

const V2 = "repair_contract_v2_shadow_calibrated";

function originalV2(overrides = {}) {
  return {
    id: "persisted-repair",
    rule: "internal_link_redirect",
    repair_contract_version: V2,
    repair_snapshot_contract_version: V2,
    repair_snapshot_contract_complete: true,
    action_priority: "important",
    affected_pages: ["/a", "/b"],
    ...overrides,
  };
}

test("browser shared-repair flag cannot manufacture canonical leverage", () => {
  const item = {
    id: "persisted-repair",
    rule: "internal_link_redirect",
    action_priority: "important",
    shared_repair_confirmed: true,
    affected_pages: ["/a", "/b"],
    original: originalV2({ shared_repair_confirmed: false }),
  };

  const model = repairRowModel(item);
  assert.equal(model.sharedRepairConfirmed, false);
  assert.equal(model.leverage, "");
  assert.equal(repairLeverageSummary(item), "");
});

test("persisted canonical shared-repair evidence may show leverage even if normalized flag is absent", () => {
  const item = {
    id: "persisted-repair",
    rule: "internal_link_redirect",
    action_priority: "important",
    affected_pages: ["/a", "/b"],
    original: originalV2({ shared_repair_confirmed: true }),
  };

  const model = repairRowModel(item);
  assert.equal(model.sharedRepairConfirmed, true);
  assert.equal(model.leverage, "One shared change may improve 2 affected pages");
});

test("legacy rows retain their compatibility leverage behavior", () => {
  const legacy = {
    id: "legacy",
    shared_repair_confirmed: true,
    affected_pages: ["/a", "/b"],
  };

  assert.equal(repairRowModel(legacy).sharedRepairConfirmed, true);
  assert.equal(repairLeverageSummary(legacy), "One shared change may improve 2 affected pages");
});
