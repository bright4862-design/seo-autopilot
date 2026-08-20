import assert from "node:assert/strict";
import test from "node:test";

import {
  repairRowModel,
  sectionCustomerRepairs,
} from "../../src/lib/repairPresentation.js";

const V2 = "repair_contract_v2_shadow_calibrated";

function originalV2(overrides = {}) {
  return {
    id: "persisted-repair",
    rule: "canonical_missing",
    repair_contract_version: V2,
    repair_snapshot_contract_version: V2,
    repair_snapshot_contract_complete: true,
    action_priority: "important",
    priority_reason: "Persisted canonical priority reason.",
    ...overrides,
  };
}

test("canonical row band comes from persisted explicit action priority, not browser priority context", () => {
  const item = {
    id: "persisted-repair",
    rule: "canonical_missing",
    priority_context: { action_priority: "fix_first" },
    original: originalV2({ action_priority: "important" }),
  };

  const model = repairRowModel(item);
  assert.equal(model.actionPriority, "important");
  assert.equal(model.sectionLabel, "Important");
});

test("canonical section placement cannot be changed by browser priority context", () => {
  const item = {
    id: "persisted-repair",
    rule: "canonical_missing",
    priorityContext: { action_priority: "review" },
    original: originalV2({ action_priority: "important" }),
  };

  const sections = sectionCustomerRepairs([item]);
  assert.equal(sections.length, 1);
  assert.equal(sections[0].key, "important");
  assert.equal(sections[0].rows[0].model.actionPriority, "important");
});

test("legacy rows retain the existing contextual priority compatibility path", () => {
  const legacy = {
    id: "legacy",
    priority: "medium",
    priority_context: { action_priority: "review" },
  };

  const model = repairRowModel(legacy);
  assert.equal(model.actionPriority, "review");
});
