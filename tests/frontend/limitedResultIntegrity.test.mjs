import assert from "node:assert/strict";
import test from "node:test";

import {
  LIMITED_RESULT_INTEGRITY_VERSION,
  LIMITED_RESULT_INTEGRITY_VERSION_V1,
  LIMITED_RESULT_INTEGRITY_VERSION_V2,
  LIMITED_RESULT_INTEGRITY_VERSION_V3,
  LIMITED_RESULT_HMAC_DOMAIN,
  LIMITED_RESULT_HMAC_DOMAIN_V1,
  LIMITED_RESULT_HMAC_DOMAIN_V2,
  LIMITED_RESULT_HMAC_DOMAIN_V3,
  buildLimitedResultSnapshot,
  createLimitedResultProof,
  verifyLimitedResultProof,
  limitedRowsFromSnapshot,
} from "../../base44/functions/persistLimitedScanResult/limitedResultIntegrity.js";
import { createAuthoritySeal, verifyAuthoritySeal } from "../../base44/functions/persistDurableScanAuthority/authoritySeal.js";
import {
  buildLimitedResultSnapshot as buildCustomerLimitedResultSnapshot,
  verifyLimitedResultProof as verifyCustomerLimitedResultProof,
} from "../../base44/functions/getCustomerScanResult/limitedResultIntegrity.js";
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

function snapshot(overrides = {}, version = LIMITED_RESULT_INTEGRITY_VERSION) {
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
    version,
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
  assert.equal(LIMITED_RESULT_HMAC_DOMAIN, "standard_limited_result_hmac_v4_focused_scope_effective_path");
  assert.equal(limited.version, LIMITED_RESULT_INTEGRITY_VERSION);
});

test("historical v1 limited results retain their original proof domain and shape", async () => {
  const historical = snapshot({}, LIMITED_RESULT_INTEGRITY_VERSION_V1);
  const proof = await createLimitedResultProof(historical, SECRET);

  assert.equal(historical.version, "standard_limited_result_integrity_v1");
  assert.equal(historical.integrity_domain, LIMITED_RESULT_HMAC_DOMAIN_V1);
  assert.equal("classification_integrity" in historical.scan, false);
  assert.equal("worker_peak_memory_bytes" in historical.scan, false);
  assert.equal(await verifyLimitedResultProof(historical, SECRET, proof), true);
});

test("historical v2 limited results retain the acceptance-evidence proof domain without scope fields", async () => {
  const historical = snapshot({}, LIMITED_RESULT_INTEGRITY_VERSION_V2);
  const proof = await createLimitedResultProof(historical, SECRET);

  assert.equal(historical.version, "standard_limited_result_integrity_v2_acceptance_evidence");
  assert.equal(historical.integrity_domain, LIMITED_RESULT_HMAC_DOMAIN_V2);
  assert.equal("scope_type" in historical.scan, false);
  assert.equal("requested_path_prefix" in historical.scan, false);
  assert.equal(await verifyLimitedResultProof(historical, SECRET, proof), true);
});

test("historical v3 focused results keep the old scope shape without an effective path", async () => {
  const historical = buildLimitedResultSnapshot({
    identity: {
      scan_id: "scan_hist_v3",
      project_id: "proj_hist_v3",
      owner_user_id: "user_hist_v3",
      request_id: "req_hist_v3",
      attempt_count: 1,
      normalized_domain: "example.com",
    },
    scan: {
      submitted_url: "https://example.com/fr/",
      beta_revision_fingerprint: RELEASE_FINGERPRINT,
      scope_type: "path_prefix",
      parent_scan_id: "parent_hist",
      requested_origin: "https://example.com",
      requested_path_prefix: "/fr",
      path_prefix: "/fr",
      effective_path_prefix: "/de",
      discovered_from: "sitemap",
      user_confirmed: true,
    },
    review: {
      scan_status: "inconclusive_insufficient_evidence",
      recommendations: [{ fix_id: "fix_hist", issue_title: "Historical", priority: "medium" }],
    },
    now: NOW,
    version: LIMITED_RESULT_INTEGRITY_VERSION_V3,
  });
  const proof = await createLimitedResultProof(historical, SECRET);

  assert.equal(historical.integrity_domain, LIMITED_RESULT_HMAC_DOMAIN_V3);
  assert.equal(historical.scan.requested_path_prefix, "/fr");
  assert.equal("effective_path_prefix" in historical.scan, false);
  assert.equal(await verifyLimitedResultProof(historical, SECRET, proof), true);
});

test("current focused limited results bind requested and effective path prefixes end to end", async () => {
  const current = buildLimitedResultSnapshot({
    identity: {
      scan_id: "scan_scope_v4",
      project_id: "proj_scope_v4",
      owner_user_id: "user_scope_v4",
      request_id: "req_scope_v4",
      attempt_count: 1,
      normalized_domain: "example.com",
    },
    scan: {
      submitted_url: "https://example.com/fr/",
      beta_revision_fingerprint: RELEASE_FINGERPRINT,
      scope_type: "path_prefix",
      parent_scan_id: "parent_scope",
      requested_origin: "https://example.com",
      requested_path_prefix: "/fr",
      path_prefix: "/fr",
      effective_path_prefix: "/de",
      discovered_from: "sitemap",
      user_confirmed: true,
    },
    review: {
      scan_status: "inconclusive_insufficient_evidence",
      limitation: "The verified landing redirect changed the effective market scope.",
      coverage_state: "limited_coverage",
      recommendations: [{ fix_id: "fix_scope", issue_title: "Scoped finding", priority: "medium" }],
    },
    now: NOW,
  });
  const proof = await createLimitedResultProof(current, SECRET);
  const rows = limitedRowsFromSnapshot(current, { fixListId: "fl_scope_v4", proof });

  assert.equal(current.scan.requested_path_prefix, "/fr");
  assert.equal(current.scan.effective_path_prefix, "/de");
  assert.equal(rows.scanRun.requested_path_prefix, "/fr");
  assert.equal(rows.scanRun.effective_path_prefix, "/de");

  const reconstructed = buildCustomerLimitedResultSnapshot({
    identity: {
      scan_id: current.scan_id,
      project_id: current.project_id,
      owner_user_id: current.owner_user_id,
      request_id: current.request_id,
      attempt_count: current.attempt_count,
      normalized_domain: current.normalized_domain,
    },
    scan: rows.scanRun,
    review: {
      scan_status: rows.scanRun.scan_status,
      health_score: rows.scanRun.health_score,
      health_grade: rows.scanRun.health_grade,
      limitation: rows.scanRun.limitation,
      coverage_state: rows.scanRun.coverage_state,
      coverage_reasons: rows.scanRun.coverage_reasons,
      coverage_authority_version: rows.scanRun.coverage_authority_version,
      recommendations: rows.fixItems,
    },
    now: current.sealed_at,
    version: current.version,
  });

  assert.deepEqual(reconstructed, current);
  assert.equal(await verifyCustomerLimitedResultProof(reconstructed, SECRET, proof), true);

  const tampered = structuredClone(current);
  tampered.scan.effective_path_prefix = "/shop";
  assert.equal(await verifyLimitedResultProof(tampered, SECRET, proof), false);
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
