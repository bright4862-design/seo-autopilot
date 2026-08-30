import assert from "node:assert/strict";
import test from "node:test";

import {
  REPAIR_DELTA_PRESENTATION_VERSION,
  repairDeltaPresentation,
} from "../../src/lib/repairDeltaPresentation.js";

// The differential rescan is a claim about what changed on the customer's site,
// so every guard here is about refusing to make that claim without standing.
// The server already draws the line: a repair_fingerprint is marked
// repair_identity_stable only with a rule, an explicit implementation surface
// and an explicit remediation family, and a provisional one is documented as
// "not eligible for automatic verified_fixed".

function repair(fingerprint, { stable = true, rule = "missing_h1" } = {}) {
  return {
    fix_id: `fix_${fingerprint}`,
    rule,
    repair_fingerprint: fingerprint,
    repair_identity_stable: stable,
    repair_identity_state: stable ? "stable" : "provisional",
  };
}

function scan(id, repairs, extra = {}) {
  return {
    id,
    status: "complete",
    repair_snapshot_contract_complete: true,
    canonical_repairs: repairs,
    ...extra,
  };
}

const PREVIOUS = scan("scan_a", [repair("f1"), repair("f2"), repair("f3")]);

function current(repairs, extra = {}) {
  return scan("scan_b", repairs, { previous_scan_id: "scan_a", ...extra });
}

test("a rescan reports fixed, introduced and persisting repairs", () => {
  const delta = repairDeltaPresentation({
    current: current([repair("f2"), repair("f3"), repair("f4")]),
    previous: PREVIOUS,
  });

  assert.equal(delta.version, REPAIR_DELTA_PRESENTATION_VERSION);
  assert.equal(delta.state, "verified_repair_delta");
  assert.equal(delta.comparedAgainstScanId, "scan_a");
  assert.deepEqual(delta.fixed.map((r) => r.repair_fingerprint), ["f1"]);
  assert.deepEqual(delta.introduced.map((r) => r.repair_fingerprint), ["f4"]);
  assert.deepEqual(delta.persisting.map((r) => r.repair_fingerprint), ["f2", "f3"]);
  assert.equal(delta.comparisonClaimAllowed, true);
});

test("a first scan has nothing to compare against", () => {
  const first = scan("scan_b", [repair("f1")]);
  assert.equal(repairDeltaPresentation({ current: first, previous: null }), null);
});

test("only the declared parent scan may be compared against", () => {
  // Comparing against some other scan would attribute its repairs to this lineage.
  const unrelated = scan("scan_zzz", [repair("f1")]);
  assert.equal(
    repairDeltaPresentation({ current: current([repair("f2")]), previous: unrelated }),
    null,
  );
});

test("a provisional identity is counted but never claimed as fixed", () => {
  const delta = repairDeltaPresentation({
    current: current([repair("f2")]),
    previous: scan("scan_a", [repair("f1", { stable: false }), repair("f2")]),
  });

  assert.deepEqual(delta.fixed, [], "an unstable identity cannot be reported as fixed");
  assert.equal(delta.unverifiedCount, 1);
  assert.equal(delta.persistingCount, 1);
});

test("a provisional identity is never claimed as newly introduced", () => {
  const delta = repairDeltaPresentation({
    current: current([repair("f1"), repair("f9", { stable: false })]),
    previous: scan("scan_a", [repair("f1")]),
  });

  assert.deepEqual(delta.introduced, []);
  assert.equal(delta.unverifiedCount, 1);
});

test("a scan that did not complete cannot retire a repair", () => {
  // Absence in an incomplete scan means it never looked, not that it is fixed.
  for (const broken of [
    current([], { status: "limited" }),
    current([], { status: "failed" }),
    current([], { status: "queued" }),
    current([], { repair_snapshot_contract_complete: false }),
  ]) {
    assert.equal(repairDeltaPresentation({ current: broken, previous: PREVIOUS }), null);
  }
});

test("an incomplete previous scan cannot be a baseline", () => {
  const partial = scan("scan_a", [repair("f1")], { status: "limited" });
  assert.equal(
    repairDeltaPresentation({ current: current([repair("f1")]), previous: partial }),
    null,
  );
});

test("everything fixed reports an empty current set, not a missing comparison", () => {
  const delta = repairDeltaPresentation({ current: current([]), previous: PREVIOUS });

  assert.equal(delta.fixedCount, 3);
  assert.equal(delta.introducedCount, 0);
  assert.equal(delta.persistingCount, 0);
});

test("rescan_of_scan_id is honoured as lineage alongside previous_scan_id", () => {
  const viaRescanField = scan("scan_b", [repair("f1")], { rescan_of_scan_id: "scan_a" });
  const delta = repairDeltaPresentation({ current: viaRescanField, previous: PREVIOUS });

  assert.equal(delta.comparedAgainstScanId, "scan_a");
});

test("duplicate fingerprints in one scan are counted once", () => {
  const delta = repairDeltaPresentation({
    current: current([repair("f1"), repair("f1")]),
    previous: scan("scan_a", [repair("f1")]),
  });

  assert.equal(delta.persistingCount, 1);
  assert.equal(delta.introducedCount, 0);
});

test("the pass does not mutate its inputs", () => {
  const before = current([repair("f4")]);
  const snapshot = JSON.stringify(before);
  repairDeltaPresentation({ current: before, previous: PREVIOUS });
  assert.equal(JSON.stringify(before), snapshot);
});
