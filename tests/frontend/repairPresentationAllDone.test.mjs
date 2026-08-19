import assert from "node:assert/strict";
import test from "node:test";

import { buildFixListPresentation } from "../../src/lib/repairPresentation.js";
import { REPAIR_PRESENTATION_MODES } from "../../src/lib/repairContractPresentation.js";

const V2 = "repair_contract_v2_shadow_calibrated";

function attestedV2(overrides = {}) {
  return {
    repair_contract_version: V2,
    repair_snapshot_contract_version: V2,
    repair_snapshot_contract_complete: true,
    priority_reason: "Persisted reason for this repair band.",
    ...overrides,
  };
}

test("explicit full-snapshot API stays canonical when every repair is hidden by workflow state", () => {
  const snapshot = [
    attestedV2({ id: "a", action_priority: "fix_first" }),
    attestedV2({ id: "b", action_priority: "important" }),
  ];

  const plan = buildFixListPresentation(snapshot, { visibleItems: [] });

  assert.equal(plan.snapshotCount, 2);
  assert.equal(plan.visibleCount, 0);
  assert.equal(plan.mode, REPAIR_PRESENTATION_MODES.CANONICAL);
  assert.equal(plan.canonical, true);
  assert.equal(plan.sections.length, 0);
  assert.equal(plan.legacyItems.length, 0);
});

test("an empty array by itself never manufactures canonical authority", () => {
  const plan = buildFixListPresentation([]);

  assert.equal(plan.snapshotCount, 0);
  assert.equal(plan.visibleCount, 0);
  assert.equal(plan.mode, REPAIR_PRESENTATION_MODES.LEGACY);
  assert.equal(plan.canonical, false);
});
