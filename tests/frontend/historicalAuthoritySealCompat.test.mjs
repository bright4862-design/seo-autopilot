import assert from "node:assert/strict";
import test from "node:test";

import {
  buildAuthoritySnapshot,
  REVIEW_ATTESTATION_VERSION,
} from "../../base44/functions/persistDurableScanAuthority/authoritySnapshot.js";
import { authorityRowsFromSnapshot } from "../../base44/functions/persistDurableScanAuthority/authorityRows.js";
import {
  createAuthoritySeal,
  verifyAuthoritySeal,
} from "../../base44/functions/persistDurableScanAuthority/authoritySeal.js";
import { authoritySnapshotFromRows } from "../../base44/functions/grokChat/authoritySnapshot.js";
import { authoritySnapshotFromRows as customerSnapshotFromRows } from "../../base44/functions/getCustomerScanResult/projection.js";
import { RELEASE_FINGERPRINT } from "../../src/lib/generatedReleaseContract.js";

/**
 * A sealed result must stay readable after the snapshot shape changes.
 *
 * The authority proof is an HMAC over the whole reconstructed snapshot, so any
 * field added to the snapshot changes the payload for EVERY row, including rows
 * sealed before the field existed. Their stored proof was computed without it,
 * so re-verification fails and getCustomerScanResult answers
 * 409 result_authority_invalid -- "This saved result no longer matches its
 * server authority seal" -- for a result that is perfectly intact.
 *
 * Patch B added coverage fields to the v1 payload and did exactly that to all
 * 30 completed production scans. The fix is version dispatch: the seal version
 * stored on the row decides which payload shape is rebuilt, so a v1 row is
 * always rebuilt as v1 and its proof keeps verifying, while new rows seal under
 * v2 and carry the coverage evidence.
 *
 * Historical rows are reconstruct-only. Nothing here re-seals them.
 */

const SECRET = "historical-compat-secret-never-deployed";
const V1 = "standard_review_snapshot_hmac_v1";
const NOW = "2026-08-21T16:00:00.000Z";

/** Fields Patch B added. A v1 payload must contain none of them. */
const COVERAGE_KEYS = [
  "pages_retained",
  "usable_html_page_count",
  "representative_html_page_count",
  "default_route_page_count",
  "discovery_quality_state",
  "evidence_quality_gate_version",
  "crawl_timing",
  "sampling_evidence",
  "coverage_authority_evidence_version",
  "coverage_authority_evidence",
];

function snapshot() {
  return buildAuthoritySnapshot({
    scan: {
      submitted_url: "https://www.cambridgewine.com/",
      scanner_version: "python_scanner_v3_bounded_request",
      scanner_build_revision: "authenticated_health_probe_v1",
      advanced_scan_backend: "python_scanner_api",
      deno_fallback_used: false,
      beta_revision_fingerprint: RELEASE_FINGERPRINT,
      metadata_evidence_version: "metadata_v1",
      title_evidence_version: "title_v1",
      pages_found: 793,
      pages_crawled: 150,
      crawl_timing: { queue_exhausted: true, sitemap_fetch_count: 4 },
      sampling_evidence: { sitemap_urls_discovered: 793 },
    },
    review: {
      archetype_classifier_version: "archetype_classifier_v9_local_business_hospitality",
      review_version: "python_review_v2_structural_marketplace",
      review_evidence_calibration_version: "review_evidence_calibration_v6_health_score_v2",
      ai_review_backend: "python_review_api",
      python_review_fallback_used: false,
      release_gate_eligible: true,
      score_is_provisional: false,
      evidence_quality_blocking: false,
      beta_revision_fingerprint: RELEASE_FINGERPRINT,
      metadata_evidence_version: "metadata_v1",
      title_evidence_version: "title_v1",
      scan_status: "complete",
      health_score: 57,
      health_grade: "Fair",
      usable_html_page_count: 150,
      representative_html_page_count: 141,
      default_route_page_count: 9,
      discovery_quality_state: "representative",
      evidence_quality_gate_version: "evidence_quality_gate_v1_default_route_dominance",
      coverage_authority_evidence: {
        coverage_authority_evidence_version: "coverage_authority_evidence_v1",
        assessment: "sufficient",
      },
      recommendations: [],
    },
    identity: {
      scan_id: "scan_hist",
      project_id: "proj_hist",
      owner_user_id: "user_hist",
      normalized_domain: "cambridgewine.com",
    },
    userId: "user_hist",
    now: NOW,
  });
}

/** A row as it was persisted before the coverage fields existed. */
async function historicalV1Row() {
  const legacy = structuredClone(snapshot());
  legacy.version = V1;
  for (const key of COVERAGE_KEYS) delete legacy.scan[key];

  const proof = await createAuthoritySeal(legacy, SECRET);
  const rows = authorityRowsFromSnapshot(legacy, {
    fixListId: "fl_hist",
    ownerUserId: "user_hist",
    proof,
  });
  return { legacy, proof, rows };
}

// ------------------------------------------------------ historical rows --

test("a v1-sealed result still verifies after the snapshot gained coverage fields", async () => {
  const { proof, rows } = await historicalV1Row();

  const rebuilt = authoritySnapshotFromRows({
    scan: { id: "scan_hist", project_id: "proj_hist", ...rows.scanRun },
    fixList: { id: "fl_hist", ...rows.fixList },
    fixItems: rows.fixItems,
    userId: "user_hist",
  });

  assert.equal(
    await verifyAuthoritySeal(rebuilt, SECRET, proof),
    true,
    "a historical result must not become 409 result_authority_invalid",
  );
});

test("the customer projection also still verifies a v1-sealed result", async () => {
  const { proof, rows } = await historicalV1Row();

  const rebuilt = customerSnapshotFromRows({
    run: { id: "scan_hist", project_id: "proj_hist", ...rows.scanRun },
    fixList: { id: "fl_hist", ...rows.fixList },
    fixItems: rows.fixItems,
    userId: "user_hist",
  });

  assert.equal(await verifyAuthoritySeal(rebuilt, SECRET, proof), true);
});

test("rebuilding a v1 row never introduces a field the v1 seal did not cover", async () => {
  const { legacy, rows } = await historicalV1Row();

  const rebuilt = authoritySnapshotFromRows({
    scan: { id: "scan_hist", project_id: "proj_hist", ...rows.scanRun },
    fixList: { id: "fl_hist", ...rows.fixList },
    fixItems: rows.fixItems,
    userId: "user_hist",
  });

  assert.deepEqual(Object.keys(rebuilt.scan).sort(), Object.keys(legacy.scan).sort());
});

// ------------------------------------------------------------ new rows --

test("new rows seal under the coverage attestation version", () => {
  assert.equal(REVIEW_ATTESTATION_VERSION, "standard_review_snapshot_hmac_v2_coverage");
  assert.equal(snapshot().version, "standard_review_snapshot_hmac_v2_coverage");
});

test("a v2-sealed result verifies and carries the coverage evidence", async () => {
  const fresh = snapshot();
  const proof = await createAuthoritySeal(fresh, SECRET);
  const rows = authorityRowsFromSnapshot(fresh, {
    fixListId: "fl_new",
    ownerUserId: "user_hist",
    proof,
  });

  const rebuilt = authoritySnapshotFromRows({
    scan: { id: "scan_hist", project_id: "proj_hist", ...rows.scanRun },
    fixList: { id: "fl_new", ...rows.fixList },
    fixItems: rows.fixItems,
    userId: "user_hist",
  });

  assert.equal(await verifyAuthoritySeal(rebuilt, SECRET, proof), true);
  assert.equal(rebuilt.scan.usable_html_page_count, 150);
  assert.equal(rebuilt.scan.coverage_authority_evidence.assessment, "sufficient");
});

test("a v1 proof cannot verify a v2 payload", async () => {
  /** The versions must be genuinely distinct domains, not cosmetic labels. */
  const { legacy, proof } = await historicalV1Row();
  const upgraded = structuredClone(legacy);
  upgraded.version = "standard_review_snapshot_hmac_v2_coverage";

  assert.equal(await verifyAuthoritySeal(upgraded, SECRET, proof), false);
});
