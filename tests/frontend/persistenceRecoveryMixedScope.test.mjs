import assert from "node:assert/strict";
import test from "node:test";

import {
  buildAuthoritySnapshot,
  firstFailedAuthorityPredicate,
} from "../../base44/functions/persistDurableScanAuthority/authoritySnapshot.js";
import { authorityRowsFromSnapshot } from "../../base44/functions/persistDurableScanAuthority/authorityRows.js";
import { RELEASE_COMPONENT_VERSIONS, RELEASE_FINGERPRINT } from "../../src/lib/generatedReleaseContract.js";

const REPAIR_CONTRACT = "repair_contract_v2_shadow_calibrated";
const PRIORITY_MODEL = "repair_priority_v2_technical_severity";

function authoritativeScan() {
  return {
    website_url: "https://www.tiqets.com/",
    submitted_url: "https://www.tiqets.com/",
    scanner_version: RELEASE_COMPONENT_VERSIONS.scanner_version,
    scanner_build_revision: RELEASE_COMPONENT_VERSIONS.scanner_build_revision,
    advanced_scan_backend: "python_scanner_api",
    deno_fallback_used: false,
    beta_revision_fingerprint: RELEASE_FINGERPRINT,
    metadata_evidence_version: "metadata_evidence_v1",
    title_evidence_version: "title_evidence_v1",
    pages_found: 5000,
    pages_crawled: 150,
  };
}

function tiqetsCanonicalRepair() {
  const affected = Array.from({ length: 22 }, (unused, index) => `/unknown/${index}`);
  return {
    fix_id: "finding_d66d79070b8b",
    rule: "missing_h1",
    category: "content",
    issue_title: "Repair unknown-family pages",
    plain_english_explanation: "22 affected pages could not be assigned one proven template family.",
    why_it_matters: "The affected pages need one truthful mixed-scope repair.",
    recommended_value: "Review the affected pages as one mixed repair.",
    page_scope: "mixed",
    page_template_family: "mixed",
    affected_pages: affected,
    page_count: 22,
    family_breakdown: { unknown: 22 },
    representative_pages_by_family: { unknown: affected[0] },
    affected_pages_complete: true,
    affected_reported: 22,
    affected_observed: 22,
    affected_eligible: 22,
    checked_eligible: null,
    indexable_affected: 0,
    indexable_checked_eligible: null,
    priority: "high",
    confidence_score: 90,
    repair_contract_version: REPAIR_CONTRACT,
    repair_priority_model_version: PRIORITY_MODEL,
    base_severity: "high",
    technical_severity_source: "scanner_rule",
    evidence_class: "confirmed_problem",
    action_priority: "fix_first",
    action_priority_score: 90,
    priority_reason: "22 checked pages are affected.",
    canonical_action_rank: 1,
    repair_identity_version: "repair_identity_v1",
    repair_fingerprint: "tiqets-production-shape-v1",
    repair_identity_state: "stable",
    repair_identity_stable: true,
    repair_surface: "page_content",
    remediation_family: "missing_h1",
    priority_context: {
      version: "repair_priority_v2",
      base_severity: "high",
      evidence_class: "confirmed_problem",
      action_priority: "fix_first",
      action_priority_score: 90,
      affected_checked: 22,
      checked_eligible: null,
      indexable_affected: 0,
      indexable_checked_eligible: null,
      coverage_scope: "mixed",
    },
  };
}

function authoritativeReview() {
  const canonical = tiqetsCanonicalRepair();
  return {
    archetype_classifier_version: RELEASE_COMPONENT_VERSIONS.archetype_classifier_version,
    review_version: RELEASE_COMPONENT_VERSIONS.review_version,
    review_evidence_calibration_version: RELEASE_COMPONENT_VERSIONS.review_evidence_calibration_version,
    ai_review_backend: "python_review_api",
    python_review_fallback_used: false,
    release_gate_eligible: true,
    score_is_provisional: false,
    evidence_quality_blocking: false,
    beta_revision_fingerprint: RELEASE_FINGERPRINT,
    metadata_evidence_version: "metadata_evidence_v1",
    title_evidence_version: "title_evidence_v1",
    health_score: 70,
    health_grade: "Fair",
    site_fingerprint: {
      coverage_assessment: {
        state: "sufficient",
        coverage_authority_version: "coverage_authority_v1_shared_decision",
      },
    },
    // Deliberately incompatible legacy data: canonical v2 must win.
    recommendations: [{
      fix_id: "legacy-wrong",
      rule: "legacy",
      page_scope: "page",
      affected_pages: [],
      page_count: 1,
      family_breakdown: {},
    }],
    repair_contract_version: REPAIR_CONTRACT,
    repair_snapshot_contract_version: REPAIR_CONTRACT,
    repair_snapshot_contract_complete: true,
    repair_priority_model_version: PRIORITY_MODEL,
    canonical_action_fix_ids: [canonical.fix_id],
    canonical_repairs: [canonical],
  };
}

test("a valid 150-page Tiqets-style result persists mixed canonical authority rows", () => {
  const scan = authoritativeScan();
  const review = authoritativeReview();

  assert.equal(firstFailedAuthorityPredicate(scan, review), "");

  const snapshot = buildAuthoritySnapshot({
    scan,
    review,
    identity: {
      scan_id: "scan-tiqets-recovery",
      project_id: "project-tiqets",
      normalized_domain: "tiqets.com",
    },
    userId: "owner-test",
    now: "2026-08-25T00:00:00.000Z",
  });
  const rows = authorityRowsFromSnapshot(snapshot, {
    fixListId: "fixlist-tiqets-recovery",
    ownerUserId: "owner-test",
    proof: "a".repeat(64),
  });

  assert.equal(snapshot.recommendations.length, 1);
  assert.equal(snapshot.recommendations[0].fix_id, "finding_d66d79070b8b");
  assert.equal(snapshot.recommendations[0].page_scope, "mixed");
  assert.equal(rows.fixItems.length, 1);
  assert.equal(rows.fixItems[0].page_scope, "mixed");
  assert.equal(rows.fixItems[0].fix_id, "finding_d66d79070b8b");
  assert.equal(rows.fixList.repair_snapshot_contract_complete, true);
  assert.equal(rows.scanRun.release_gate_eligible, true);
  assert.equal(rows.scanRun.status, "complete");
  assert.equal(rows.scanRun.beta_revision_fingerprint, RELEASE_FINGERPRINT);
});
