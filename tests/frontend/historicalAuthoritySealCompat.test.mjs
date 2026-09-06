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
const V2 = "standard_review_snapshot_hmac_v2_coverage";
const V3 = "standard_review_snapshot_hmac_v3_acceptance_evidence";
const V4 = "standard_review_snapshot_hmac_v4_focused_scope";
const V5 = "standard_review_snapshot_hmac_v5_score_explanation";
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

const ACCEPTANCE_KEYS = [
  "classification_integrity",
  "classification_verdict",
  "peak_memory_bytes",
  "worker_peak_memory_bytes",
];

const SCOPE_KEYS = [
  "scope_type",
  "parent_scan_id",
  "requested_origin",
  "requested_path_prefix",
  "discovered_from",
  "user_confirmed",
];

/** The field v5 added: where the health score's points went. */
const SCORE_EXPLANATION_KEYS = ["health_score_explanation"];

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
  for (const key of [...COVERAGE_KEYS, ...ACCEPTANCE_KEYS, ...SCOPE_KEYS, ...SCORE_EXPLANATION_KEYS]) delete legacy.scan[key];

  const proof = await createAuthoritySeal(legacy, SECRET);
  const rows = authorityRowsFromSnapshot(legacy, {
    fixListId: "fl_hist",
    ownerUserId: "user_hist",
    proof,
  });
  return { legacy, proof, rows };
}

/** A row sealed after coverage v2 but before acceptance-evidence v3. */
async function historicalV2Row() {
  const legacy = structuredClone(snapshot());
  legacy.version = V2;
  for (const key of [...ACCEPTANCE_KEYS, ...SCOPE_KEYS, ...SCORE_EXPLANATION_KEYS]) delete legacy.scan[key];

  const proof = await createAuthoritySeal(legacy, SECRET);
  const rows = authorityRowsFromSnapshot(legacy, {
    fixListId: "fl_v2",
    ownerUserId: "user_hist",
    proof,
  });
  return { legacy, proof, rows };
}

/** A row sealed under acceptance-evidence v3, before focused scope v4. */
async function historicalV3Row() {
  const legacy = structuredClone(snapshot());
  legacy.version = V3;
  for (const key of [...SCOPE_KEYS, ...SCORE_EXPLANATION_KEYS]) delete legacy.scan[key];

  const proof = await createAuthoritySeal(legacy, SECRET);
  const rows = authorityRowsFromSnapshot(legacy, {
    fixListId: "fl_v3",
    ownerUserId: "user_hist",
    proof,
  });
  return { legacy, proof, rows };
}

/** A row sealed under focused scope v4, before the score explanation v5. */
async function historicalV4Row() {
  const legacy = structuredClone(snapshot());
  legacy.version = V4;
  for (const key of SCORE_EXPLANATION_KEYS) delete legacy.scan[key];

  const proof = await createAuthoritySeal(legacy, SECRET);
  const rows = authorityRowsFromSnapshot(legacy, {
    fixListId: "fl_v4",
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

test("new rows seal under the score-explanation attestation version", () => {
  assert.equal(REVIEW_ATTESTATION_VERSION, V5);
  assert.equal(snapshot().version, V5);
});

test("a historical v2-sealed result still verifies and carries coverage evidence", async () => {
  const { proof, rows } = await historicalV2Row();

  const rebuilt = authoritySnapshotFromRows({
    scan: { id: "scan_hist", project_id: "proj_hist", ...rows.scanRun },
    fixList: { id: "fl_v2", ...rows.fixList },
    fixItems: rows.fixItems,
    userId: "user_hist",
  });

  assert.equal(await verifyAuthoritySeal(rebuilt, SECRET, proof), true);
  assert.equal(rebuilt.scan.usable_html_page_count, 150);
  assert.equal(rebuilt.scan.coverage_authority_evidence.assessment, "sufficient");
});

test("a historical v4-sealed result still verifies without a score explanation", async () => {
  // The row this release supersedes. Every completed production scan before
  // today is one of these, so the assertion that matters is that adding the
  // breakdown did not silently invalidate all of them.
  const { legacy, proof, rows } = await historicalV4Row();
  const rebuilt = customerSnapshotFromRows({
    run: { id: "scan_hist", project_id: "proj_hist", ...rows.scanRun },
    fixList: { id: "fl_v4", ...rows.fixList },
    fixItems: rows.fixItems,
    userId: "user_hist",
  });

  assert.equal(await verifyAuthoritySeal(rebuilt, SECRET, proof), true);
  assert.ok(!("health_score_explanation" in rebuilt.scan),
    "a v4 row must not gain the field its seal did not cover");
  assert.ok(!("health_score_explanation" in legacy.scan));
  // The v4 fields it does carry are still there.
  assert.equal(rebuilt.scan.scope_type, legacy.scan.scope_type);
  assert.equal(rebuilt.scan.usable_html_page_count, 150);
});

test("a historical v3-sealed result still verifies without focused-scope fields", async () => {
  const { legacy, proof, rows } = await historicalV3Row();
  const rebuilt = authoritySnapshotFromRows({
    scan: { id: "scan_hist", project_id: "proj_hist", ...rows.scanRun },
    fixList: { id: "fl_v3", ...rows.fixList },
    fixItems: rows.fixItems,
    userId: "user_hist",
  });
  assert.deepEqual(Object.keys(rebuilt.scan).sort(), Object.keys(legacy.scan).sort());
  assert.equal(await verifyAuthoritySeal(rebuilt, SECRET, proof), true);
});

test("a v1 proof cannot verify a v3 payload", async () => {
  /** The versions must be genuinely distinct domains, not cosmetic labels. */
  const { legacy, proof } = await historicalV1Row();
  const upgraded = structuredClone(legacy);
  upgraded.version = V3;

  assert.equal(await verifyAuthoritySeal(upgraded, SECRET, proof), false);
});
