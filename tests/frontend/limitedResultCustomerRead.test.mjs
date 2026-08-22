import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

import { buildCustomerProjection } from "../../base44/functions/getCustomerScanResult/projection.js";
import { RELEASE_FINGERPRINT } from "../../src/lib/generatedReleaseContract.js";

/**
 * Patch C part 2 - the customer can read a limited result, and it never reads
 * as authoritative.
 *
 * Two flags, kept separate the whole way out: authority_verified says this is a
 * release-authoritative record, result_integrity_verified says this provisional
 * record is intact. Collapsing them into one boolean is how a limited scan would
 * quietly get treated as a complete one.
 */

const SOURCE = readFileSync(
  new URL("../../base44/functions/getCustomerScanResult/index.ts", import.meta.url),
  "utf8",
);

function limitedRun(overrides = {}) {
  return {
    id: "scan_tanners",
    project_id: "proj_tanners",
    status: "limited",
    scan_status: "inconclusive_insufficient_evidence",
    release_gate_eligible: false,
    score_is_provisional: true,
    health_score: 48,
    health_grade: "Insufficient evidence",
    limitation: "FixList reviewed 38 of 3,689 discovered pages.",
    beta_revision_fingerprint: RELEASE_FINGERPRINT,
    result_integrity_proof: "d".repeat(64),
    ...overrides,
  };
}

const LIMITED_FIX_LIST = { id: "fl_limited", is_authoritative: false, total_fixes: 2 };
const LIMITED_FIX_ITEMS = [
  { fix_id: "fix_a", issue_title: "First", priority: "high" },
  { fix_id: "fix_b", issue_title: "Second", priority: "medium" },
];

test("a verified limited result returns its evidence to the customer", () => {
  const projection = buildCustomerProjection({
    run: limitedRun(),
    fixList: LIMITED_FIX_LIST,
    fixItems: LIMITED_FIX_ITEMS,
    fullAccess: true,
    authorityVerified: false,
    resultIntegrityVerified: true,
  });

  assert.equal(projection.success, true);
  assert.equal(projection.access, "full");
  assert.equal(projection.fixItems.length, 2, "a limited result must still carry its findings");
  assert.equal(projection.fix_list_id, "fl_limited");
});

test("a limited result never reports itself as authoritative", () => {
  const projection = buildCustomerProjection({
    run: limitedRun(),
    fixList: LIMITED_FIX_LIST,
    fixItems: LIMITED_FIX_ITEMS,
    fullAccess: true,
    authorityVerified: false,
    resultIntegrityVerified: true,
  });

  assert.equal(projection.authority_verified, false);
  assert.equal(projection.result_integrity_verified, true);
  assert.equal(projection.release_contract_current, true);
});

test("an authoritative result is unchanged and is not marked limited", () => {
  const projection = buildCustomerProjection({
    run: { ...limitedRun(), status: "complete", release_gate_eligible: true, score_is_provisional: false },
    fixList: { id: "fl_auth", is_authoritative: true },
    fixItems: LIMITED_FIX_ITEMS,
    fullAccess: true,
    authorityVerified: true,
  });

  assert.equal(projection.authority_verified, true);
  assert.equal(projection.result_integrity_verified, false);
  assert.equal(projection.fixItems.length, 2);
});

test("without paid access a limited result stays locked", () => {
  const projection = buildCustomerProjection({
    run: limitedRun(),
    fixList: LIMITED_FIX_LIST,
    fixItems: LIMITED_FIX_ITEMS,
    fullAccess: false,
    authorityVerified: false,
    resultIntegrityVerified: true,
  });

  assert.equal(projection.access, "locked");
  assert.equal(projection.result_integrity_verified, false);
  assert.deepEqual(projection.fixItems, []);
});

// -------------------------------------------------- the endpoint's guards --

test("the read path verifies the limited proof against its own domain", () => {
  assert.match(SOURCE, /verifyLimitedResultProof\(limitedSnapshot, secret, integrityProof\)/);
  assert.match(SOURCE, /buildLimitedResultSnapshot\(/);
});

test("a limited row carrying an authority proof is refused outright", () => {
  /** Nothing may arrive holding both; that would be a promotion path. */
  assert.match(SOURCE, /run\.release_gate_eligible === true \|\| cleanProof\(run\.authority_proof\)/);
});

test("the limited branch returns authorityVerified false", () => {
  const branch = SOURCE.slice(SOURCE.indexOf('run.status === "limited"'));
  const call = branch.slice(branch.indexOf("buildCustomerProjection({"), branch.indexOf("// Full access"));
  assert.match(call, /authorityVerified: false/);
  assert.match(call, /resultIntegrityVerified: true/);
});
