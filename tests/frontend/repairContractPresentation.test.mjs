import assert from "node:assert/strict";
import test from "node:test";

import {
  REPAIR_PRESENTATION_MODES,
  canConsumeCanonicalActionPriority,
  canonicalActionBandOrderIsValid,
  explicitCanonicalActionPriorityOf,
  explicitCanonicalPriorityReasonOf,
  repairContractVersionOf,
  repairPresentationContract,
  repairPresentationMode,
  repairSnapshotContractComplete,
  repairSnapshotContractVersionOf,
  repairSnapshotPresentationMode,
} from "../../src/lib/repairContractPresentation.js";

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

test("calibrated repair contract may consume canonical action priority only with snapshot attestation", () => {
  const item = attestedV2({ action_priority: "important" });
  assert.equal(repairContractVersionOf(item), V2);
  assert.equal(repairSnapshotContractVersionOf(item), V2);
  assert.equal(repairSnapshotContractComplete(item), true);
  assert.equal(explicitCanonicalActionPriorityOf(item), "important");
  assert.equal(explicitCanonicalPriorityReasonOf(item), "Persisted reason for this repair band.");
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

test("fully attested v2 row without persisted priority reason fails closed", () => {
  const contract = repairPresentationContract(attestedV2({
    action_priority: "important",
    priority_reason: "",
  }));
  assert.equal(contract.priorityReason, "");
  assert.equal(contract.mode, REPAIR_PRESENTATION_MODES.UNSUPPORTED);
  assert.equal(contract.canonicalActionPriorityAllowed, false);
});

test("browser priority context cannot substitute for missing canonical priority reason", () => {
  const item = attestedV2({
    action_priority: "important",
    priority_reason: "",
    priority_context: { priority_reason: "Browser/context fallback" },
  });
  assert.equal(explicitCanonicalPriorityReasonOf(item), "");
  assert.equal(repairPresentationMode(item), REPAIR_PRESENTATION_MODES.UNSUPPORTED);
});

test("persisted original priority reason wins over normalized browser copy", () => {
  const item = {
    action_priority: "important",
    priority_reason: "Browser-mutated reason",
    original: attestedV2({
      action_priority: "important",
      priority_reason: "Persisted explanation",
    }),
  };
  assert.equal(explicitCanonicalPriorityReasonOf(item), "Persisted explanation");
  assert.equal(repairPresentationMode(item), REPAIR_PRESENTATION_MODES.CANONICAL);
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

test("canonical snapshot band order must already match the UI section order", () => {
  const valid = [
    attestedV2({ id: "a", action_priority: "fix_first" }),
    attestedV2({ id: "b", action_priority: "fix_first" }),
    attestedV2({ id: "c", action_priority: "important" }),
    attestedV2({ id: "d", action_priority: "improve" }),
    attestedV2({ id: "e", action_priority: "review" }),
  ];

  assert.equal(canonicalActionBandOrderIsValid(valid), true);
  assert.equal(repairSnapshotPresentationMode(valid), REPAIR_PRESENTATION_MODES.CANONICAL);
});

test("interleaved canonical bands fail closed instead of being silently reordered by sections", () => {
  const interleaved = [
    attestedV2({ id: "important-first", action_priority: "important" }),
    attestedV2({ id: "fix-first-later", action_priority: "fix_first" }),
  ];

  assert.equal(canonicalActionBandOrderIsValid(interleaved), false);
  assert.equal(repairSnapshotPresentationMode(interleaved), REPAIR_PRESENTATION_MODES.UNSUPPORTED);
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
  assert.equal(
    explicitCanonicalPriorityReasonOf({ original: { priority_reason: "Persisted" } }),
    "Persisted",
  );
});
