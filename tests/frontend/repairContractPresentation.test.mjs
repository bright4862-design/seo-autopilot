import assert from "node:assert/strict";
import test from "node:test";

import {
  REPAIR_PRESENTATION_MODES,
  canConsumeCanonicalActionPriority,
  repairContractVersionOf,
  repairPresentationContract,
  repairPresentationMode,
} from "../../src/lib/repairContractPresentation.js";

test("supported repair contract may consume persisted canonical action priority", () => {
  const item = {
    repair_contract_version: "repair_contract_v1_shadow",
    action_priority: "important",
  };
  assert.equal(repairContractVersionOf(item), "repair_contract_v1_shadow");
  assert.equal(repairPresentationMode(item), REPAIR_PRESENTATION_MODES.CANONICAL);
  assert.equal(canConsumeCanonicalActionPriority(item), true);
});

test("historical repair with no contract remains frozen legacy presentation", () => {
  const item = { priority: "critical", action_priority: "fix_first" };
  const contract = repairPresentationContract(item);
  assert.equal(contract.mode, REPAIR_PRESENTATION_MODES.LEGACY);
  assert.equal(contract.frozenLegacyPresentation, true);
  assert.equal(contract.canonicalActionPriorityAllowed, false);
});

test("unknown future repair contract fails closed instead of being reinterpreted", () => {
  const item = {
    repair_contract_version: "repair_contract_v99_future",
    action_priority: "fix_first",
  };
  const contract = repairPresentationContract(item);
  assert.equal(contract.mode, REPAIR_PRESENTATION_MODES.UNSUPPORTED);
  assert.equal(contract.unsupported, true);
  assert.equal(contract.canonicalActionPriorityAllowed, false);
});

test("camelCase and nested historical shapes resolve contract version deterministically", () => {
  assert.equal(
    repairContractVersionOf({ repairContractVersion: "repair_contract_v1_shadow" }),
    "repair_contract_v1_shadow",
  );
  assert.equal(
    repairContractVersionOf({ original: { repair_contract_version: "repair_contract_v1_shadow" } }),
    "repair_contract_v1_shadow",
  );
});
