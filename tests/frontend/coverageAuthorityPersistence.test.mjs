import assert from "node:assert/strict";
import test from "node:test";

import { buildAuthoritySnapshot } from "../../base44/functions/persistDurableScanAuthority/authoritySnapshot.js";
import { authorityRowsFromSnapshot } from "../../base44/functions/persistDurableScanAuthority/authorityRows.js";
import { RELEASE_FINGERPRINT } from "../../src/lib/generatedReleaseContract.js";

/**
 * Patch B - the durable record must be able to explain its own coverage.
 *
 * Every completed ScanRun in the 50-site audit carried
 * usable_html_page_count == 0 and representative_html_page_count == 0 while
 * claiming evidence quality 100 with reason representative_html_evidence.
 * The counts are not wrong in the review; the snapshot simply never writes
 * them, so the schema defaults of 0 survive into the sealed row. The result is
 * a durable record that asserts a quality verdict and drops the evidence for
 * it, which is what made Tanners (38/3,689), Decathlon (40/1,374) and Habito
 * (1 page) impossible to explain after the fact.
 *
 * Every field asserted below already exists in base44/entities/ScanRun.jsonc.
 * This is a persistence gap, not a schema change -- except for the coverage
 * assessment itself, which is new and versioned.
 *
 * Authority is deliberately untouched: the same snapshot must still seal as
 * complete and release-eligible exactly as it does today.
 *
 * Evidence: docs/audit/2026-08-21-production-50-site/
 */

const NOW = "2026-08-21T18:00:00.000Z";

const COVERAGE_EVIDENCE = {
  coverage_authority_evidence_version: "coverage_authority_evidence_v1",
  assessment: "insufficient_sample",
  would_gate_as_insufficient: true,
  reasons: ["retained_pages_below_minimum", "coverage_ratio_below_minimum"],
  inventory: {
    discovered_target: 3689,
    attempted: 38,
    retained_usable_html: 38,
    retained_representative_html: 31,
    default_route_pages: 7,
    final_url_duplicates_deduped: 0,
    queued_remaining: 0,
    coverage_ratio: 0.0103,
  },
  terminal_reason: "queue_exhausted",
  inventory_proof: { positively_established: true, sitemap_failed: false },
  thresholds: { min_retained_pages: 50, min_retained_ratio: 0.1, min_inventory_for_ratio_test: 100 },
};

function snapshot({ review: reviewOverrides = {}, scan: scanOverrides = {} } = {}) {
  return buildAuthoritySnapshot({
    scan: {
      submitted_url: "https://www.tanners-wines.co.uk/",
      scanner_version: "python_scanner_v3_bounded_request",
      scanner_build_revision: "authenticated_health_probe_v1",
      advanced_scan_backend: "python_scanner_api",
      deno_fallback_used: false,
      beta_revision_fingerprint: RELEASE_FINGERPRINT,
      metadata_evidence_version: "metadata_v1",
      title_evidence_version: "title_v1",
      pages_found: 3689,
      pages_crawled: 38,
      sampling_evidence: { sitemap_urls_discovered: 3689, sitemap_urls_sampled: 149 },
      crawl_timing: { queue_exhausted: true, failed_fetch_count: 0, sitemap_fetch_count: 4 },
      ...scanOverrides,
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
      health_score: 67,
      health_grade: "Fair",
      evidence_quality_state: "representative",
      evidence_quality_score: 100,
      evidence_quality_reasons: ["representative_html_evidence"],
      discovery_quality_state: "representative",
      representative_html_page_count: 31,
      usable_html_page_count: 38,
      default_route_page_count: 7,
      evidence_quality_gate_version: "evidence_quality_gate_v1_default_route_dominance",
      coverage_authority_evidence: COVERAGE_EVIDENCE,
      recommendations: [],
      ...reviewOverrides,
    },
    identity: {
      scan_id: "scan_tanners",
      project_id: "project_tanners",
      owner_user_id: "user_tanners",
      normalized_domain: "tanners-wines.co.uk",
    },
    userId: "user_tanners",
    now: NOW,
  });
}

// ------------------------------------- the counts that justify the verdict --

test("the sealed scan carries the page counts its quality verdict rests on", () => {
  const { scan } = snapshot();

  assert.equal(scan.usable_html_page_count, 38);
  assert.equal(scan.representative_html_page_count, 31);
  assert.equal(scan.default_route_page_count, 7);
  assert.equal(scan.pages_retained, 38);
});

test("the sealed scan carries the discovery state and gate version", () => {
  const { scan } = snapshot();

  assert.equal(scan.discovery_quality_state, "representative");
  assert.equal(scan.evidence_quality_gate_version, "evidence_quality_gate_v1_default_route_dominance");
});

test("the sealed scan retains crawl timing and sampling evidence", () => {
  const { scan } = snapshot();

  assert.equal(scan.crawl_timing.queue_exhausted, true);
  assert.equal(scan.crawl_timing.sitemap_fetch_count, 4);
  assert.equal(scan.sampling_evidence.sitemap_urls_discovered, 3689);
});

test("a quality score can no longer be sealed without its supporting counts", () => {
  /** The exact production contradiction: score 100, counts 0. */
  const { scan } = snapshot();
  if (Number(scan.evidence_quality_score) >= 80) {
    assert.ok(
      Number(scan.usable_html_page_count) > 0,
      "a representative-evidence score was sealed with zero usable pages",
    );
  }
});

// -------------------------------------------------- the coverage assessment --

test("the coverage assessment is sealed with the scan", () => {
  const { scan } = snapshot();

  assert.equal(scan.coverage_authority_evidence_version, "coverage_authority_evidence_v1");
  assert.equal(scan.coverage_authority_evidence.assessment, "insufficient_sample");
  assert.equal(scan.coverage_authority_evidence.inventory.discovered_target, 3689);
  assert.equal(scan.coverage_authority_evidence.inventory.retained_usable_html, 38);
  assert.deepEqual(scan.coverage_authority_evidence.thresholds, COVERAGE_EVIDENCE.thresholds);
});

test("the assessment survives onto the persisted ScanRun row", () => {
  const rows = authorityRowsFromSnapshot(snapshot(), {
    fixListId: "fixlist_tanners",
    ownerUserId: "user_tanners",
    proof: "a".repeat(64),
  });

  assert.equal(rows.scanRun.coverage_authority_evidence.assessment, "insufficient_sample");
  assert.equal(rows.scanRun.usable_html_page_count, 38);
});

test("a review with no coverage assessment seals without inventing one", () => {
  const { scan } = snapshot({ review: { coverage_authority_evidence: undefined } });

  assert.ok(
    scan.coverage_authority_evidence === undefined
      || Object.keys(scan.coverage_authority_evidence).length === 0,
    "an absent assessment must not be fabricated",
  );
});

// ------------------------------------------------------ authority untouched --

test("persisting the diagnostics does not change what the snapshot asserts", () => {
  /**
   * Patch B is diagnostics only. An advisory of insufficient_sample rides
   * along on a scan that still seals exactly as complete and release-eligible.
   * Acting on it is a later patch.
   */
  const { scan } = snapshot();

  assert.equal(scan.status, "complete");
  assert.equal(scan.release_gate_eligible, true);
  assert.equal(scan.score_is_provisional, false);
  assert.equal(scan.evidence_quality_blocking, false);
  assert.equal(scan.health_score, 67);
  assert.equal(scan.coverage_authority_evidence.would_gate_as_insufficient, true);
});
