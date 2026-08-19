import assert from "node:assert/strict";
import test from "node:test";

import {
  REPAIR_PRESENTATION_MODES,
  canConsumeCanonicalActionPriority,
  explicitCanonicalActionPriorityOf,
  repairContractVersionOf,
  repairPresentationContract,
  repairPresentationMode,
  repairSnapshotContractComplete,
  repairSnapshotContractVersionOf,
} from "../../src/lib/repairContractPresentation.js";

const V2 = "repair_contract_v2_shadow_calibrated";

function attestedV2(overrides = {}) {
  return {
    repair_contract_version: V2,
    repair_snapshot_contract_version: V2,
    repair_snapshot_contract_complete: true,
    ...overrides,
  };
}

test("calibrated repair contract may consume canonical action priority only with snapshot attestation", () => {
  const item = attestedV2({ action_priority: "important" });
  assert.equal(repairContractVersionOf(item), V2);
  assert.equal(repairSnapshotContractVersionOf(item), V2);
  assert.equal(repairSnapshotContractComplete(item), true);
  assert.equal(explicitCanonicalActionPriorityOf(item), "important");
  assert.equal(repairPresentationMode(item), REPAIR_PRESENTATION_MODES.CANONICAL);
  assert.equal(canConsumeCanonicalActionPriority(item), true);
});

test("fully attested v2 row without persisted action priority fails closed", () => {
  const contract = repairPresentationContract(attestedV2({ priority: "critical" }));
  assert.equal(contract.actionPriority, "");
  assert.equal(contract.mode, REPAIR_PRESENTATION_MODES.UNSUPPORTED);
  assert.equal(contract.canonicalActionPriorityAllowed, false);
  assert.equal(contract.unsupported, true);
});

test("invalid canonical action priority fails closed instead of falling back to severity", () => {
  const contract = repairPresentationContract(attestedV2({
    priority: "critical",
    action_priority: "urgent_now",
  }));
  assert.equal(contract.actionPriority, "");
  assert.equal(contract.mode, REPAIR_PRESENTATION_MODES.UNSUPPORTED);
  assert.equal(contract.canonicalActionPriorityAllowed, false);
});

test("normalized camelCase canonical action priority remains explicit authority", () => {
  const item = attestedV2({ actionPriority: "fix_first" });
  assert.equal(explicitCanonicalActionPriorityOf(item), "fix_first");
  assert.equal(repairPresentationMode(item), REPAIR_PRESENTATION_MODES.CANONICAL);
});

test("supported row contract without snapshot attestation remains frozen legacy", () => {
  const item = {
    repair_contract_version: V2,
    action_priority: "fix_first",
  };
  const contract = repairPresentationContract(item);
  assert.equal(contract.mode, REPAIR_PRESENTATION_MODES.LEGACY);
  assert.equal(contract.frozenLegacyPresentation, true);
  assert.equal(contract.canonicalActionPriorityAllowed, false);
});

test("incomplete snapshot attestation cannot activate canonical UI", () => {
  const item = {
    repair_contract_version: V2,
    repair_snapshot_contract_version: V2,
    repair_snapshot_contract_complete: false,
    action_priority: "fix_first",
  };
  assert.equal(repairPresentationMode(item), REPAIR_PRESENTATION_MODES.LEGACY);
});

test("mismatched row and snapshot contracts fail closed", () => {
  const item = {
    repair_contract_version: V2,
    repair_snapshot_contract_version: "repair_contract_v1_shadow",
    repair_snapshot_contract_complete: true,
    action_priority: "fix_first",
  };
  const contract = repairPresentationContract(item);
  assert.equal(contract.mode, REPAIR_PRESENTATION_MODES.UNSUPPORTED);
  assert.equal(contract.unsupported, true);
});

test("superseded v1 shadow contract fails closed rather than activating canonical UI", () => {
  const item = {
    repair_contract_version: "repair_contract_v1_shadow",
    action_priority: "fix_first",
  };
  const contract = repairPresentationContract(item);
  assert.equal(contract.mode, REPAIR_PRESENTATION_MODES.UNSUPPORTED);
  assert.equal(contract.unsupported, true);
  assert.equal(contract.canonicalActionPriorityAllowed, false);
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

test("camelCase and nested historical shapes resolve contract fields deterministically", () => {
  assert.equal(
    repairContractVersionOf({ repairContractVersion: V2 }),
    V2,
  );
  assert.equal(
    repairContractVersionOf({ original: { repair_contract_version: V2 } }),
    V2,
  );
  assert.equal(
    repairSnapshotContractVersionOf({ repairSnapshotContractVersion: V2 }),
    V2,
  );
  assert.equal(
    repairSnapshotContractComplete({ original: { repair_snapshot_contract_complete: true } }),
    true,
  );
  assert.equal(
    explicitCanonicalActionPriorityOf({ original: { action_priority: "review" } }),
    "review",
  );
});
