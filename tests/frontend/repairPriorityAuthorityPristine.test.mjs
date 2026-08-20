import assert from "node:assert/strict";
import test from "node:test";

import {
  prepareCustomerFixes,
  versionedRepairAuthorityIsPristine,
} from "../../src/lib/fixRanking.js";
import { REPAIR_PRESENTATION_MODES } from "../../src/lib/repairContractPresentation.js";

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

test("same persisted canonical action priority remains pristine after harmless normalization", () => {
  const item = {
    id: "persisted-repair",
    rule: "canonical_missing",
    action_priority: "important",
    title: "Friendlier title",
    original: originalV2(),
  };

  assert.equal(versionedRepairAuthorityIsPristine(item), true);
  const prepared = prepareCustomerFixes([item]);
  assert.equal(prepared[0].repair_snapshot_presentation_mode, REPAIR_PRESENTATION_MODES.CANONICAL);
});

test("omitting the normalized action priority safely falls back to the persisted original value", () => {
  const item = {
    id: "persisted-repair",
    rule: "canonical_missing",
    title: "Friendlier title",
    original: originalV2(),
  };

  assert.equal(versionedRepairAuthorityIsPristine(item), true);
  const prepared = prepareCustomerFixes([item]);
  assert.equal(prepared[0].repair_snapshot_presentation_mode, REPAIR_PRESENTATION_MODES.CANONICAL);
});

test("browser mutation from one valid canonical band to another fails closed", () => {
  const item = {
    id: "persisted-repair",
    rule: "canonical_missing",
    action_priority: "fix_first",
    original: originalV2({ action_priority: "important" }),
  };

  assert.equal(versionedRepairAuthorityIsPristine(item), false);
  const prepared = prepareCustomerFixes([item]);
  assert.equal(prepared[0].repair_snapshot_presentation_mode, REPAIR_PRESENTATION_MODES.UNSUPPORTED);
});

test("camelCase browser mutation cannot override snake_case persisted authority", () => {
  const item = {
    id: "persisted-repair",
    rule: "canonical_missing",
    actionPriority: "review",
    original: originalV2({ action_priority: "important" }),
  };

  assert.equal(versionedRepairAuthorityIsPristine(item), false);
  assert.equal(
    prepareCustomerFixes([item])[0].repair_snapshot_presentation_mode,
    REPAIR_PRESENTATION_MODES.UNSUPPORTED,
  );
});

test("direct canonical rows without a browser-normalization original remain governed by the contract gate", () => {
  const direct = originalV2({ action_priority: "important" });

  assert.equal(versionedRepairAuthorityIsPristine(direct), true);
  assert.equal(
    prepareCustomerFixes([direct])[0].repair_snapshot_presentation_mode,
    REPAIR_PRESENTATION_MODES.CANONICAL,
  );
});
