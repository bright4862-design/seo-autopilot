import assert from "node:assert/strict";
import test from "node:test";

import {
  LIMITED_RESULT_INTEGRITY_VERSION,
  LIMITED_RESULT_HMAC_DOMAIN,
  buildLimitedResultSnapshot,
  createLimitedResultProof,
  verifyLimitedResultProof,
  limitedRowsFromSnapshot,
} from "../../base44/functions/persistLimitedScanResult/limitedResultIntegrity.js";
import { createAuthoritySeal, verifyAuthoritySeal } from "../../base44/functions/persistDurableScanAuthority/authoritySeal.js";
import { RELEASE_FINGERPRINT } from "../../src/lib/generatedReleaseContract.js";

/**
 * Patch C part 2 - a truthful result for a scan that is not authoritative.
 *
 * Part 1 makes a thin crawl provisional. On its own that turns Tanners and
 * Decathlon into generic failures: the customer loses evidence that was real
 * and useful, which is worse than the overclaim it replaced.
 *
 * So a limited result gets its own integrity proof rather than a weakened
 * authority seal. The security property is the point: a limited proof must be
 * cryptographically unusable as an authority proof, and the reverse, so no
 * amount of row-shuffling can promote a provisional scan into an authoritative
 * one. That is why the domain label is bound inside the signed payload rather
 * than being a naming convention.
 */

const SECRET = "limited-result-secret-never-deployed";
const NOW = "2026-08-22T02:00:00.000Z";

function snapshot(overrides = {}) {
  return buildLimitedResultSnapshot({
    identity: {
      scan_id: "scan_tanners",
      project_id: "proj_tanners",
      owner_user_id: "user_tanners",
      request_id: "req_1",
      attempt_count: 1,
      normalized_domain: "tanners-wines.co.uk",
    },
    scan: {
      submitted_url: "https://www.tanners-wines.co.uk/",
      scanner_version: "python_scanner_v3_bounded_request",
      scanner_build_revision: "authenticated_health_probe_v1",
      beta_revision_fingerprint: RELEASE_FINGERPRINT,
      worker_source_sha: "1eb20072095dd182fb41e276e57050eee071bd50",
      pages_found: 3689,
      pages_crawled: 38,
    },
    review: {
      scan_status: "inconclusive_insufficient_evidence",
      health_score: 48,
      health_grade: "Insufficient evidence",
      limitation: "FixList reviewed 38 of 3,689 discovered pages.",
      coverage_state: "limited_coverage",
      coverage_reasons: ["retained_pages_below_minimum", "coverage_ratio_below_minimum"],
      coverage_authority_version: "coverage_authority_v1_shared_decision",
      recommendations: [
        { fix_id: "fix_b", issue_title: "Second", priority: "medium", affected_pages: ["/b"] },
        { fix_id: "fix_a", issue_title: "First", priority: "high", affected_pages: ["/a"] },
      ],
      ...overrides,
    },
    now: NOW,
  });
}

// ------------------------------------------------- it is not authority --

test("a limited snapshot never claims authority", () => {
  const { scan, fix_list: fixList } = snapshot();

  assert.equal(scan.status, "limited");
  assert.equal(scan.release_gate_eligible, false);
  assert.equal(scan.score_is_provisional, true);
  assert.equal(fixList.is_authoritative, false);
  assert.ok(!("authority_proof" in scan), "a limited row must not carry an authority proof");
  assert.ok(!("authority_seal_version" in scan));
});

test("a limited proof cannot be used as an authority seal", async () => {
  /** The whole reason the domain label is inside the signed payload. */
  const limited = snapshot();
  const limitedProof = await createLimitedResultProof(limited, SECRET);

  assert.equal(await verifyAuthoritySeal(limited, SECRET, limitedProof), false);
});

test("an authority seal cannot be used as a limited proof", async () => {
  const limited = snapshot();
  const authorityStyleProof = await createAuthoritySeal(limited, SECRET);

  assert.equal(await verifyLimitedResultProof(limited, SECRET, authorityStyleProof), false);
});

test("the signed payload binds the domain label", () => {
  const limited = snapshot();
  assert.equal(limited.integrity_domain, LIMITED_RESULT_HMAC_DOMAIN);
  assert.equal(LIMITED_RESULT_HMAC_DOMAIN, "standard_limited_result_hmac_v1");
  assert.equal(limited.version, LIMITED_RESULT_INTEGRITY_VERSION);
});

// ------------------------------------------------------- it is verifiable --

test("a limited proof verifies its own snapshot", async () => {
  const limited = snapshot();
  const proof = await createLimitedResultProof(limited, SECRET);

  assert.match(proof, /^[a-f0-9]{64}$/);
  assert.equal(await verifyLimitedResultProof(limited, SECRET, proof), true);
});

test("tampering with a persisted fix invalidates the proof", async () => {
  const limited = snapshot();
  const proof = await createLimitedResultProof(limited, SECRET);

  const tampered = structuredClone(limited);
  tampered.recommendations[0].issue_title = "attacker changed this";

  assert.equal(await verifyLimitedResultProof(tampered, SECRET, proof), false);
});

test("changing the coverage reason invalidates the proof", async () => {
  /** The limitation is the point of the record; it must be bound. */
  const limited = snapshot();
  const proof = await createLimitedResultProof(limited, SECRET);

  const tampered = structuredClone(limited);
  tampered.scan.coverage_state = "sufficient";

  assert.equal(await verifyLimitedResultProof(tampered, SECRET, proof), false);
});

test("the payload binds identity, release markers and source sha", () => {
  const limited = snapshot();

  assert.equal(limited.scan_id, "scan_tanners");
  assert.equal(limited.project_id, "proj_tanners");
  assert.equal(limited.owner_user_id, "user_tanners");
  assert.equal(limited.request_id, "req_1");
  assert.equal(limited.attempt_count, 1);
  assert.equal(limited.release_fingerprint, RELEASE_FINGERPRINT);
  assert.equal(limited.scan.worker_source_sha, "1eb20072095dd182fb41e276e57050eee071bd50");
});

// -------------------------------------------------------------- it is stable --

test("the snapshot is deterministic and fix order is fixed", async () => {
  const first = snapshot();
  const second = snapshot();

  assert.deepEqual(second, first);
  assert.deepEqual(first.recommendations.map((fix) => fix.fix_id), ["fix_a", "fix_b"]);
  assert.equal(await createLimitedResultProof(first, SECRET), await createLimitedResultProof(second, SECRET));
});

test("a replayed persist reuses the stored timestamp rather than reseeding it", () => {
  /** Idempotency: a retry must reach the same proof, not a second row. */
  const first = snapshot();
  const replay = buildLimitedResultSnapshot({
    identity: {
      scan_id: "scan_tanners", project_id: "proj_tanners", owner_user_id: "user_tanners",
      request_id: "req_1", attempt_count: 1, normalized_domain: "tanners-wines.co.uk",
    },
    scan: {
      submitted_url: "https://www.tanners-wines.co.uk/",
      scanner_version: "python_scanner_v3_bounded_request",
      scanner_build_revision: "authenticated_health_probe_v1",
      beta_revision_fingerprint: RELEASE_FINGERPRINT,
      worker_source_sha: "1eb20072095dd182fb41e276e57050eee071bd50",
      pages_found: 3689, pages_crawled: 38,
    },
    review: {
      scan_status: "inconclusive_insufficient_evidence", health_score: 48,
      health_grade: "Insufficient evidence",
      limitation: "FixList reviewed 38 of 3,689 discovered pages.",
      coverage_state: "limited_coverage",
      coverage_reasons: ["retained_pages_below_minimum", "coverage_ratio_below_minimum"],
      coverage_authority_version: "coverage_authority_v1_shared_decision",
      recommendations: [
        { fix_id: "fix_b", issue_title: "Second", priority: "medium", affected_pages: ["/b"] },
        { fix_id: "fix_a", issue_title: "First", priority: "high", affected_pages: ["/a"] },
      ],
    },
    now: NOW,
  });

  assert.deepEqual(replay, first);
});

// ------------------------------------------------------------- the rows --

test("persisted rows carry the integrity proof and never an authority proof", () => {
  const limited = snapshot();
  const rows = limitedRowsFromSnapshot(limited, {
    fixListId: "fl_limited",
    proof: "c".repeat(64),
  });

  assert.equal(rows.scanRun.status, "limited");
  assert.equal(rows.scanRun.result_integrity_proof, "c".repeat(64));
  assert.equal(rows.scanRun.result_integrity_version, LIMITED_RESULT_INTEGRITY_VERSION);
  assert.equal(rows.scanRun.release_gate_eligible, false);
  assert.ok(!("authority_proof" in rows.scanRun));

  assert.equal(rows.fixList.is_authoritative, false);
  assert.equal(rows.fixList.result_integrity_proof, "c".repeat(64));
  assert.ok(!("authority_proof" in rows.fixList));

  for (const item of rows.fixItems) {
    assert.equal(item.result_integrity_proof, "c".repeat(64));
    assert.equal(item.fix_list_id, "fl_limited");
    assert.ok(!("authority_proof" in item));
  }
});

test("a scan with no useful evidence yields no limited result at all", () => {
  /** Zero usable HTML stays a failure. A limited result needs real evidence. */
  assert.equal(snapshot({ recommendations: [] }).recommendations.length, 0);
  assert.equal(
    buildLimitedResultSnapshot({
      identity: { scan_id: "s", project_id: "p", owner_user_id: "o", request_id: "r", attempt_count: 1 },
      scan: {},
      review: { recommendations: [] },
      now: NOW,
    }).eligible_for_limited_result,
    false,
  );
});
