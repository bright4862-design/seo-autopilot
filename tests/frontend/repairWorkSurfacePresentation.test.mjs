import assert from "node:assert/strict";
import test from "node:test";

import { buildRepairWorkSurfacePresentation } from "../../src/lib/repairWorkSurfacePresentation.js";
import { REPAIR_PRESENTATION_MODES } from "../../src/lib/repairContractPresentation.js";

const V2 = "repair_contract_v2_shadow_calibrated";

function canonical(overrides = {}) {
  return {
    id: "repair-a",
    repair_contract_version: V2,
    repair_snapshot_contract_version: V2,
    repair_snapshot_contract_complete: true,
    action_priority: "fix_first",
    priority_reason: "Persisted reason.",
    evidence_class: "confirmed_problem",
    ...overrides,
  };
}

test("full saved snapshot owns authority while visible repairs stay a separate workflow subset", () => {
  const a = canonical({ id: "a", action_priority: "fix_first" });
  const b = canonical({ id: "b", action_priority: "important" });

  const result = buildRepairWorkSurfacePresentation({
    snapshotItems: [a, b],
    visibleItems: [a],
    doneIds: ["b"],
    scan: { id: "scan-1" },
  });

  assert.equal(result.presentation.mode, REPAIR_PRESENTATION_MODES.CANONICAL);
  assert.equal(result.presentation.snapshotCount, 2);
  assert.equal(result.presentation.visibleCount, 1);
  assert.equal(result.presentation.sections.length, 1);
  assert.equal(result.presentation.sections[0].key, "fix_first");
  assert.equal(result.markedDoneCount, 1);
  assert.equal(result.scan.id, "scan-1");
});

test("unknown or duplicate Done IDs cannot inflate workflow completion", () => {
  const snapshot = [canonical({ id: "a" }), canonical({ id: "b", action_priority: "important" })];

  const result = buildRepairWorkSurfacePresentation({
    snapshotItems: snapshot,
    visibleItems: [],
    doneIds: ["a", "a", "not-in-snapshot", ""],
  });

  assert.equal(result.presentation.snapshotCount, 2);
  assert.equal(result.presentation.visibleCount, 0);
  assert.equal(result.markedDoneCount, 1);
});

test("mixed saved snapshot remains non-canonical even if the incompatible row is hidden", () => {
  const canonicalRow = canonical({ id: "new" });
  const legacyRow = { id: "old", priority: "high" };

  const result = buildRepairWorkSurfacePresentation({
    snapshotItems: [canonicalRow, legacyRow],
    visibleItems: [canonicalRow],
    doneIds: ["old"],
  });

  assert.equal(result.presentation.mode, REPAIR_PRESENTATION_MODES.LEGACY);
  assert.equal(result.presentation.canonical, false);
  assert.equal(result.markedDoneCount, 1);
});

test("migration seam does not infer visible rows from the full snapshot", () => {
  const result = buildRepairWorkSurfacePresentation({
    snapshotItems: [canonical({ id: "a" })],
  });

  assert.equal(result.presentation.snapshotCount, 1);
  assert.equal(result.presentation.visibleCount, 0);
});
