import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

import {
  buildLimitedResultSnapshot,
  createLimitedResultProof,
  verifyLimitedResultProof,
  limitedRowsFromSnapshot,
} from "../../base44/functions/persistLimitedScanResult/limitedResultIntegrity.js";
import { buildCustomerProjection } from "../../base44/functions/getCustomerScanResult/projection.js";
import { firstFailedAuthorityPredicate } from "../../base44/functions/persistDurableScanAuthority/authoritySnapshot.js";
import { RELEASE_FINGERPRINT } from "../../src/lib/generatedReleaseContract.js";

/**
 * Patch C - the second half of the end-to-end chain.
 *
 * The fixture is produced by the real Python scanner -> review -> worker chain
 * in scanner-api/tests/test_limited_result_end_to_end.py, which regenerates and
 * compares it on every run so it cannot drift. This file takes that exact
 * envelope the rest of the way: Base44 persistence snapshot, integrity proof,
 * persisted rows, and what the customer finally reads.
 *
 * Testing the seams separately would miss the thing that actually matters --
 * that a limited scan travels a different path from end to end and arrives
 * readable, intact, and not authoritative.
 */

const FIXTURE = JSON.parse(
  readFileSync(new URL("../fixtures/limited-result-end-to-end.json", import.meta.url), "utf8"),
);
const SECRET = "e2e-signing-key-never-deployed";

function snapshotFromFixture() {
  return buildLimitedResultSnapshot({
    identity: FIXTURE.envelope.identity,
    scan: {
      submitted_url: "https://www.tanners-wines.co.uk/",
      beta_revision_fingerprint: RELEASE_FINGERPRINT,
    },
    review: FIXTURE.envelope.review,
    now: "2026-08-22T03:00:00.000Z",
  });
}

test("the pipeline hands over a limited, non-authoritative envelope", () => {
  assert.equal(FIXTURE.coverage_state, "limited_coverage");
  assert.equal(FIXTURE.release_gate_eligible, false);
  assert.equal(FIXTURE.score_is_provisional, true);
  assert.equal(FIXTURE.envelope.version, "durable_standard150_limited_v1");
  assert.ok(FIXTURE.envelope.review.recommendations.length > 0, "there must be evidence worth persisting");
});

test("Base44 authority would refuse this same review outright", () => {
  /** The two paths must disagree about this scan; that is the point. */
  const failed = firstFailedAuthorityPredicate(
    { scanner_version: "python_scanner_v3_bounded_request" },
    { ...FIXTURE.envelope.review, beta_revision_fingerprint: RELEASE_FINGERPRINT },
  );
  assert.notEqual(failed, "", "an authority seal must not be reachable for a limited scan");
});

test("the envelope persists as a verified limited result the customer can read", async () => {
  const snapshot = snapshotFromFixture();
  assert.equal(snapshot.eligible_for_limited_result, true);

  const proof = await createLimitedResultProof(snapshot, SECRET);
  const rows = limitedRowsFromSnapshot(snapshot, { fixListId: "fl_e2e", proof });

  // Persisted state
  assert.equal(rows.scanRun.status, "limited");
  assert.equal(rows.scanRun.release_gate_eligible, false);
  assert.ok(!("authority_proof" in rows.scanRun));
  assert.equal(rows.fixList.is_authoritative, false);
  assert.equal(rows.fixItems.length, FIXTURE.envelope.review.recommendations.length);

  // Read back and verified on the way out
  assert.equal(await verifyLimitedResultProof(snapshot, SECRET, proof), true);

  const projection = buildCustomerProjection({
    run: { id: "scan_e2e", ...rows.scanRun, beta_revision_fingerprint: RELEASE_FINGERPRINT },
    fixList: { id: "fl_e2e", ...rows.fixList },
    fixItems: rows.fixItems,
    fullAccess: true,
    authorityVerified: false,
    resultIntegrityVerified: true,
  });

  assert.equal(projection.success, true);
  assert.equal(projection.authority_verified, false, "a limited result must never read as authoritative");
  assert.equal(projection.result_integrity_verified, true);
  assert.equal(
    projection.fixItems.length,
    FIXTURE.envelope.review.recommendations.length,
    "the customer keeps the evidence the scan actually found",
  );
});

test("the customer sees why the result is limited", () => {
  const snapshot = snapshotFromFixture();

  assert.equal(snapshot.scan.coverage_state, "limited_coverage");
  assert.ok(snapshot.scan.coverage_reasons.length > 0);
  assert.ok(snapshot.scan.limitation, "a limited result without a stated limitation is not truthful");
});

test("tampering anywhere along the chain is caught on read", async () => {
  const snapshot = snapshotFromFixture();
  const proof = await createLimitedResultProof(snapshot, SECRET);

  const promoted = structuredClone(snapshot);
  promoted.scan.coverage_state = "sufficient";
  promoted.scan.release_gate_eligible = true;

  assert.equal(
    await verifyLimitedResultProof(promoted, SECRET, proof),
    false,
    "a limited record must not be promotable by editing the row",
  );
});
